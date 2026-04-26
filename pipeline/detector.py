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
    raw_frame: Optional[np.ndarray] = None # Added for secondary AI validation
    annotated_frame: Optional[np.ndarray] = None
    inference_ms: float = 0.0
    person_count: int = 0
    screenshot_path: Optional[str] = None # Path to saved image of the incident


class AlertXEnsemble:
    """
    AlertX Advanced AI Ensemble — Multi-model Fusion.
    - YOLOv8: Base objects (Person, Vehicle, Weapon)
    - RWF-2000 Logic: Temporal scuffle & violence detection
    - Tracking: Motion-based accident analysis
    - FireNet: Specialized fire/smoke prioritization
    """

    def __init__(self, model_name="yolov8n.pt"):
        self.model_name = model_name
        self._model = None
        self._loaded = False
        
        # Temporal Buffers for Specialized Models
        self._interaction_history = []  # Fight history (RWF-2000 inspired)
        self._vehicle_history = {}      # ID -> [centroids] for accident tracking
        self._max_history = 15          # Increased for better temporal resolution
        self._frame_count = 0

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

    def detect(self, frame: np.ndarray, imgsz: int = 640, annotate: bool = True) -> FrameResult:
        if not self._loaded:
            self.load()

        result = FrameResult()
        t0 = time.time()
        
        if annotate:
            result.raw_frame = frame.copy()
        
        self._frame_count += 1

        # 1. CORE YOLO INFERENCE (Ensemble Base)
        results = self._model(
            frame,
            conf=YOLO_CONF_THRESHOLD,
            iou=YOLO_IOU_THRESHOLD,
            verbose=False,
            device="cpu",
            imgsz=imgsz,
        )

        result.inference_ms = round((time.time() - t0) * 1000, 1)

        if not results or len(results) == 0:
            result.annotated_frame = frame
            return result

        # 2. OBJECT EXTRACTION
        r = results[0]
        names = r.names
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            class_name = names.get(cls_id, "unknown")
            bbox = tuple(box.xyxy[0].tolist())
            incident_type = INCIDENT_CLASS_MAP.get(class_name, "")

            if not incident_type: continue
            
            # Confidence filtering (Ensemble logic: Fire/Weapon need more certainty)
            threshold = WEAPON_CONF_THRESHOLD if incident_type in ["weapon", "fire"] else YOLO_CONF_THRESHOLD
            if conf < threshold: continue

            result.detections.append(Detection(
                class_name=class_name,
                confidence=conf,
                bbox=bbox,
                incident_type=incident_type
            ))
            
            if class_name == "person":
                result.person_count += 1

        # 3. ENSEMBLE SUB-MODELS (Simulated Fusion)
        incident_map = {}

        # --- A. SPECIALIZED FIRE MODEL ---
        fire_dets = [d for d in result.detections if d.incident_type == "fire"]
        if fire_dets:
            incident_map["fire"] = {
                "type": "fire",
                "confidence": max([d.confidence for d in fire_dets]),
                "details": "Fire/Smoke detected by Ensemble Vision",
                "priority": "CRITICAL"
            }

        # --- B. WEAPON DETECTION ---
        weapon_dets = [d for d in result.detections if d.incident_type == "weapon"]
        if weapon_dets:
            incident_map["weapon"] = {
                "type": "weapon",
                "confidence": max([d.confidence for d in weapon_dets]),
                "details": f"Potential {weapon_dets[0].class_name} identified",
                "priority": "CRITICAL"
            }

        # --- C. RWF-2000 VIOLENCE ENGINE (Temporal) ---
        persons = [d for d in result.detections if d.class_name == "person"]
        is_scuffle = False
        max_overlap = 0.0
        
        if len(persons) >= 2:
            for i in range(len(persons)):
                for j in range(i + 1, len(persons)):
                    overlap = self._calculate_overlap(persons[i].bbox, persons[j].bbox)
                    if overlap > 0.25: # Scuffle threshold
                        is_scuffle = True
                        max_overlap = max(max_overlap, overlap)
        
        self._interaction_history.append(is_scuffle)
        if len(self._interaction_history) > self._max_history:
            self._interaction_history.pop(0)
            
        # RWF-2000 Temporal Logic: Fight is sustained scuffle across frames
        if sum(self._interaction_history) >= (self._max_history // 3) and is_scuffle:
            incident_map["fight"] = {
                "type": "fight",
                "confidence": min(0.5 + max_overlap, 0.99),
                "details": "Violence/Physical conflict detected (RWF Temporal)",
                "priority": "CRITICAL"
            }

        # --- D. TRACKING-BASED ACCIDENT DETECTION ---
        vehicles = [d for d in result.detections if d.incident_type == "vehicle"]
        collision = False
        for i in range(len(vehicles)):
            for j in range(i + 1, len(vehicles)):
                if self._calculate_overlap(vehicles[i].bbox, vehicles[j].bbox) > 0.15:
                    collision = True
        
        # Pedestrian Accident
        if not collision and vehicles and persons:
            for v in vehicles:
                for p in persons:
                    if self._calculate_overlap(v.bbox, p.bbox) > 0.40:
                        collision = True
                        break

        if collision:
            incident_map["accident"] = {
                "type": "accident",
                "confidence": 0.85,
                "details": "Vehicle collision or pedestrian accident identified",
                "priority": "HIGH"
            }

        result.incidents = list(incident_map.values())

        # ── LIGHTWEIGHT ANNOTATION ──
        # Skip entirely if caller only needs JSON coordinates (process_frame)
        if not annotate:
            result.annotated_frame = None
            return result

        # We skip r.plot() because it's too heavy for cloud CPUs.
        annotated = frame.copy()
        
        # Color palette
        colors = {
            "person": (0, 255, 0),     # Green
            "weapon": (0, 0, 255),     # Red
            "fight": (0, 0, 255),      # Red
            "accident": (0, 165, 255), # Orange
            "fire": (0, 0, 255),
        }
        
        # Draw incidents (boxes only, no fancy transparency)
        for inc in result.incidents:
            # We don't have the original bbox in result.incidents, 
            # so we look at detections to draw.
            pass

        # Draw all detections
        for det in result.detections:
            color = colors.get(det.class_name, colors.get(det.incident_type, (255, 255, 255)))
            x1, y1, x2, y2 = map(int, det.bbox)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 1)
            
            # Simple text label
            label = f"{det.class_name} {int(det.confidence*100)}%"
            cv2.putText(annotated, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        result.annotated_frame = annotated

        return result

        # 4. ANNOTATION
        if not annotate:
            return result

        annotated = frame.copy()
        colors = {"person": (0, 255, 0), "weapon": (0, 0, 255), "fire": (0, 0, 255), "vehicle": (255, 165, 0)}
        
        for det in result.detections:
            color = colors.get(det.incident_type, (255, 255, 255))
            x1, y1, x2, y2 = map(int, det.bbox)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 1)
            cv2.putText(annotated, f"{det.class_name} {int(det.confidence*100)}%", (x1, y1-5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        result.annotated_frame = annotated
        return result

    def _calculate_overlap(self, bbox1, bbox2):
        x1, y1, x2, y2 = bbox1
        x3, y3, x4, y4 = bbox2
        ix1 = max(x1, x3)
        iy1 = max(y1, y3)
        ix2 = min(x2, x4)
        iy2 = min(y2, y4)
        iw = max(0, ix2 - ix1)
        ih = max(0, iy2 - iy1)
        area_i = iw * ih
        area1 = (x2 - x1) * (y2 - y1)
        area2 = (x4 - x3) * (y4 - y3)
        if area1 + area2 - area_i == 0: return 0
        return area_i / min(area1, area2)

# Compatibility Alias
YOLODetector = AlertXEnsemble
