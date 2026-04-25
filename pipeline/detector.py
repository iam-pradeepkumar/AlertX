"""
AlertX — YOLO Detector
Wraps Ultralytics YOLO inference for CPU-optimised detection.
Returns structured detection results, not raw tensors.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import numpy as np

from backend.config import (
    YOLO_MODEL,
    YOLO_CONF_THRESHOLD,
    YOLO_IOU_THRESHOLD,
    INCIDENT_CLASS_MAP,
    CROWD_THRESHOLD,
    WEAPON_CONF_THRESHOLD,
)

logger = logging.getLogger("alertx.detector")


@dataclass
class Detection:
    """Single bounding-box detection."""
    class_name: str
    confidence: float
    bbox: tuple  # (x1, y1, x2, y2)
    incident_type: str = ""


@dataclass
class FrameResult:
    """All detections + derived incidents for one frame."""
    detections: List[Detection] = field(default_factory=list)
    incidents: List[dict] = field(default_factory=list)
    annotated_frame: Optional[np.ndarray] = None
    inference_ms: float = 0.0
    person_count: int = 0
    screenshot_path: Optional[str] = None # Path to saved image of the incident


class YOLODetector:
    """Lightweight wrapper around Ultralytics YOLO with temporal fight detection."""

    def __init__(self, model_name="yolov8n.pt"): # Reverted to Nano for speed on cloud
        self.model_name = model_name
        self._model = None
        self._model_path = model_name
        self._loaded = False
        # Temporal buffers for scuffle consistency
        self._interaction_history = []  # List of bools for recent frames
        self._max_history = 10

    def load(self):
        """Lazy-load model to save memory at import time."""
        if self._loaded:
            return
        try:
            import torch
            from ultralytics import YOLO
            
            # ─────────────────────────────────────────────────────────
            # FIX: PyTorch 2.6+ security change (Weights only load failed)
            # Temporary monkeypatch to allow loading official YOLO weights
            # ─────────────────────────────────────────────────────────
            _original_load = torch.load
            try:
                # Force weights_only=False for the duration of model loading
                torch.load = lambda *args, **kwargs: _original_load(*args, **{**kwargs, 'weights_only': False})
                self._model = YOLO(self._model_path)
            finally:
                # Restore original torch.load
                torch.load = _original_load

            self._loaded = True
            logger.info(f"YOLO model loaded: {self._model_path}")
        except Exception as e:
            logger.error(f"Failed to load YOLO model: {e}")
            raise

    def detect(self, frame: np.ndarray) -> FrameResult:
        """
        Run detection on a single frame.
        Returns FrameResult with detections, incidents, annotated frame.
        """
        if not self._loaded:
            self.load()

        result = FrameResult()
        t0 = time.time()
        
        # --- OPTIMIZATION: Ultra-low resolution for cloud ---
        # Resizing here makes everything below (contrast, AI) 4x faster
        frame = cv2.resize(frame, (320, 240), interpolation=cv2.INTER_AREA)

        # --- LIGHT PRE-PROCESSING (Handling watermarks efficiently) ---
        # Contrast boost is cheap (fast), Sharpening is expensive (slow).
        alpha = 1.2 # Contrast
        beta = 5    # Brightness
        enhanced_frame = cv2.convertScaleAbs(frame, alpha=alpha, beta=beta)

        # Run inference (CPU, no grad)
        results = self._model(
            enhanced_frame,
            conf=YOLO_CONF_THRESHOLD,
            iou=YOLO_IOU_THRESHOLD,
            verbose=False,
            device="cpu",
            imgsz=320,
        )

        result.inference_ms = round((time.time() - t0) * 1000, 1)

        if not results or len(results) == 0:
            result.annotated_frame = frame
            return result

        r = results[0]
        names = r.names  # {0: 'person', 1: 'bicycle', ...}

        person_count = 0

        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            class_name = names.get(cls_id, "unknown")
            bbox = tuple(box.xyxy[0].tolist())

            # Map to incident type
            incident_type = INCIDENT_CLASS_MAP.get(class_name, "")

            det = Detection(
                class_name=class_name,
                confidence=conf,
                bbox=bbox,
                incident_type=incident_type,
            )
            result.detections.append(det)

            if class_name == "person":
                person_count += 1

        result.person_count = person_count

        # ── Derive incidents ──────────────────
        incident_map = {}
        
        # 1. Process standard incident types from map
        for det in result.detections:
            # We skip "vehicle" and "person" here as they are handled by specialized heuristics below
            if det.incident_type and det.incident_type not in ["vehicle", "person"]:
                
                # SPECIAL RULE: Weapons need higher confidence to avoid crowd noise (phones, bags)
                if det.incident_type == "weapon" and det.confidence < WEAPON_CONF_THRESHOLD:
                    continue

                key = det.incident_type
                if key not in incident_map or det.confidence > incident_map[key]["confidence"]:
                    incident_map[key] = {
                        "type": det.incident_type,
                        "confidence": det.confidence,
                        "class_name": det.class_name,
                        "count": 1,
                    }
                else:
                    incident_map[key]["count"] += 1

        # 2. Crowd detection
        if person_count >= CROWD_THRESHOLD:
            incident_map["crowd"] = {
                "type": "crowd",
                "confidence": min(0.5 + (person_count / 40.0), 0.98),
                "class_name": "person",
                "count": person_count,
            }

        # 3. Physical Interaction / Fight Heuristic (TEMPORAL)
        # Inspired by CNN-LSTM: Look for sustained interaction
        persons = [d for d in result.detections if d.class_name == "person"]
        instant_interaction = False
        max_overlap = 0.0
        
        if len(persons) >= 2:
            for i in range(len(persons)):
                for j in range(i + 1, len(persons)):
                    overlap = self._calculate_overlap(persons[i].bbox, persons[j].bbox)
                    if overlap > 0.22: # Scuffle threshold
                        instant_interaction = True
                        max_overlap = max(max_overlap, overlap)
        
        # Maintain history
        self._interaction_history.append(instant_interaction)
        if len(self._interaction_history) > self._max_history:
            self._interaction_history.pop(0)
            
        # Verify if interaction is sustained (e.g. 50% of recent frames)
        sustained_interaction = sum(self._interaction_history) >= (self._max_history // 3)
        
        if sustained_interaction and max_overlap > 0:
            incident_map["fight"] = {
                "type": "fight",
                "confidence": min(0.4 + max_overlap + (sum(self._interaction_history) / 20.0), 0.99),
                "class_name": "person",
                "count": len(persons),
            }

        # 4. Vehicle Accident Heuristic (Multi-factor collision detection)
        vehicles = [d for d in result.detections if d.incident_type == "vehicle"]
        persons = [d for d in result.detections if d.class_name == "person"]
        accident_detected = False
        max_v_overlap = 0.0
        accident_desc = ""

        # Case A: Vehicle-Vehicle Collision
        if len(vehicles) >= 2:
            for i in range(len(vehicles)):
                for j in range(i + 1, len(vehicles)):
                    v_overlap = self._calculate_overlap(vehicles[i].bbox, vehicles[j].bbox)
                    if v_overlap > 0.12: # Significant overlap between moving vehicles
                        accident_detected = True
                        max_v_overlap = max(max_v_overlap, v_overlap)
                        accident_desc = "Vehicle-Vehicle Collision"
            
        # Case B: Vehicle-Pedestrian Collision (High priority)
        if not accident_detected and len(vehicles) > 0 and len(persons) > 0:
            for v in vehicles:
                for p in persons:
                    vp_overlap = self._calculate_overlap(v.bbox, p.bbox)
                    if vp_overlap > 0.35: # INCREASED: Less sensitive to avoid crowd noise
                        accident_detected = True
                        max_v_overlap = max(max_v_overlap, vp_overlap + 0.1) 
                        accident_desc = "Pedestrian Accident"

        if accident_detected:
            incident_map["accident"] = {
                "type": "accident",
                "confidence": min(0.6 + max_v_overlap, 0.99),
                "class_name": accident_desc,
                "count": 1,
            }

        result.incidents = list(incident_map.values())

        # Annotated frame
        result.annotated_frame = r.plot()

        return result

    def _calculate_overlap(self, bbox1: tuple, bbox2: tuple) -> float:
        """Calculate Intersection over Minimum Area (IoM) for scuffle detection."""
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2

        # Intersection
        xi1 = max(x1_1, x1_2)
        yi1 = max(y1_1, y1_2)
        xi2 = min(x2_1, x2_2)
        yi2 = min(y2_1, y2_2)

        if xi2 <= xi1 or yi2 <= yi1:
            return 0.0

        inter_area = (xi2 - xi1) * (yi2 - yi1)
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        
        # Using Intersection over Minimum Area - better for occlusion/scuffles
        return inter_area / min(area1, area2)

    @property
    def is_loaded(self) -> bool:
        return self._loaded
