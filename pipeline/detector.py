"""
AlertX — YOLO Detector
Wraps Ultralytics YOLO inference for CPU-optimised detection.
Returns structured detection results, not raw tensors.
"""

import logging
import time
import os
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import numpy as np
import torch

from backend.config import (
    YOLO_MODEL,
    YOLO_CONF_THRESHOLD,
    YOLO_IOU_THRESHOLD,
    INCIDENT_CLASS_MAP,
    CROWD_THRESHOLD,
    WEAPON_CONF_THRESHOLD,
    BASE_DIR,
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
    - YOLOv8n: Base objects
    - best.pt: Weapon detection
    - fightdetection.h5: Violence detection
    """

    def __init__(self, model_name="yolov8n.pt"):
        self.model_name = model_name
        self._loaded = False
        
        # State across frames for staggered detection
        self._frame_count = 0
        self._last_boxes = []
        self._last_person_count = 0
        self._last_weapon = False
        self._pred_buffer = deque(maxlen=10)
        self._violence_threshold = 0.6
        self._img_size = 128
        self._last_event = "SAFE"

        # Models
        self.object_model = None
        self.weapon_model = None
        self.weapon_ok = False
        self.fight_model = None

    def load(self):
        """Lazy-load models to save memory at import time."""
        if self._loaded:
            return
        try:
            from ultralytics import YOLO
            import tensorflow as tf
            from tensorflow.keras.models import load_model
            
            # Use GPU if possible
            device = "cuda" if torch.cuda.is_available() else "cpu"
            
            ai_model_dir = os.path.join(BASE_DIR, "AI-model")
            
            _original_load = torch.load
            try:
                # Force weights_only=False for the duration of model loading
                torch.load = lambda *args, **kwargs: _original_load(*args, **{**kwargs, 'weights_only': False})
                
                # Load Object Model
                obj_path = os.path.join(ai_model_dir, "yolov8n.pt")
                self.object_model = YOLO(obj_path)
                
                # Load Weapon Model
                weapon_path = os.path.join(ai_model_dir, "best.pt")
                try:
                    if os.path.exists(weapon_path):
                        self.weapon_model = YOLO(weapon_path)
                        self.weapon_ok = True
                except Exception as we:
                    logger.warning(f"Could not load weapon model: {we}")

                # Load Fight Model
                fight_path = os.path.join(ai_model_dir, "fightdetection.h5")
                if os.path.exists(fight_path):
                    self.fight_model = load_model(fight_path, compile=False)
                    
            finally:
                # Restore original torch.load
                torch.load = _original_load

            self._loaded = True
            logger.info("All Custom AI models loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load AI models: {e}")
            raise

    def preprocess(self, frame):
        img = cv2.resize(frame, (self._img_size, self._img_size))
        img = img / 255.0
        return np.reshape(img, (1, self._img_size, self._img_size, 3))

    def detect(self, frame: np.ndarray, imgsz: int = 640, annotate: bool = True) -> FrameResult:
        if not self._loaded:
            self.load()

        result = FrameResult()
        t0 = time.time()
        
        if annotate:
            result.raw_frame = frame.copy()
            
        frame_h, frame_w = frame.shape[:2]
        small = cv2.resize(frame, (320, 320))
        
        self._frame_count += 1
        
        # -------------------------------
        # ROTATING MODEL EXECUTION
        # -------------------------------

        # 1. OBJECT DETECTION
        if self._frame_count % 3 == 0:
            results = self.object_model(small, verbose=False)
            new_boxes = []
            person_count = 0
            
            for r in results:
                for box in r.boxes:
                    conf = float(box.conf[0])
                    if conf < 0.5:
                        continue
                        
                    label = self.object_model.names[int(box.cls[0])]
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    # scale from 320 back to original frame size
                    x1 = int(x1 * frame_w / 320)
                    x2 = int(x2 * frame_w / 320)
                    y1 = int(y1 * frame_h / 320)
                    y2 = int(y2 * frame_h / 320)
                    
                    new_boxes.append((x1, y1, x2, y2, label, conf))
                    
                    if label == "person":
                        person_count += 1
                        
            if new_boxes:
                self._last_boxes = new_boxes
            self._last_person_count = person_count

        # 2. WEAPON DETECTION
        if self.weapon_ok and self._frame_count % 3 == 1:
            self._last_weapon = False
            results = self.weapon_model(small, verbose=False)
            
            for r in results:
                for box in r.boxes:
                    if float(box.conf[0]) > 0.5:
                        self._last_weapon = True

        # 3. VIOLENCE DETECTION
        if self.fight_model is not None and self._frame_count % 3 == 2:
            for (x1, y1, x2, y2, label, conf) in self._last_boxes:
                if label == "person":
                    crop = frame[y1:y2, x1:x2]
                    if crop.size == 0:
                        continue
                    try:
                        pred = float(self.fight_model.predict(self.preprocess(crop), verbose=0)[0][0])
                        self._pred_buffer.append(pred)
                    except Exception as e:
                        pass # Ignore prediction errors on bad crops

        result.inference_ms = round((time.time() - t0) * 1000, 1)
        
        # -------------------------------
        # BUILD RESULTS FROM STATE
        # -------------------------------
        for (x1, y1, x2, y2, label, conf) in self._last_boxes:
            incident_type = INCIDENT_CLASS_MAP.get(label, "")
            result.detections.append(Detection(
                class_name=label,
                confidence=conf,
                bbox=(x1, y1, x2, y2),
                incident_type=incident_type
            ))
            
        result.person_count = self._last_person_count
        
        # -------------------------------
        # DECISION LOGIC
        # -------------------------------
        violence_flag = False
        if len(self._pred_buffer) > 0:
            if sum(self._pred_buffer)/len(self._pred_buffer) > self._violence_threshold and self._last_person_count >= 2:
                violence_flag = True

        incident_map = {}
        
        if self._last_weapon:
            incident_map["weapon"] = {
                "type": "weapon",
                "confidence": 0.9,
                "details": "Weapon detected by Custom Model",
                "priority": "CRITICAL"
            }
            self._last_event = "WEAPON"
            
        elif violence_flag:
            incident_map["fight"] = {
                "type": "fight",
                "confidence": sum(self._pred_buffer)/len(self._pred_buffer),
                "details": "Violence detected by Custom Keras Model",
                "priority": "CRITICAL"
            }
            self._last_event = "VIOLENCE"
            
        elif self._last_person_count >= 4:
            incident_map["anomaly"] = {
                "type": "anomaly",
                "confidence": 0.8,
                "details": f"Crowd detected ({self._last_person_count} persons)",
                "priority": "MEDIUM"
            }
            self._last_event = "CROWD"
            
        else:
            self._last_event = "SAFE"

        result.incidents = list(incident_map.values())

        # -------------------------------
        # ANNOTATION
        # -------------------------------
        if not annotate:
            return result

        annotated = frame.copy()
        
        for det in result.detections:
            color = (0, 0, 255) if self._last_event != "SAFE" else (0, 255, 0)
            x1, y1, x2, y2 = map(int, det.bbox)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated, f"{det.class_name} {int(det.confidence*100)}%", (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # BIG ALERT TEXT
        event_color = (0, 0, 255) if self._last_event != "SAFE" else (0, 255, 0)
        cv2.putText(annotated, self._last_event, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.5, event_color, 4)
        cv2.putText(annotated, f"People: {self._last_person_count}", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

        result.annotated_frame = annotated
        return result

    @property
    def is_loaded(self) -> bool:
        return self._loaded

# Compatibility Alias
YOLODetector = AlertXEnsemble
