"""
AlertX — Detection Agent
Takes raw frame results from YOLO, normalises them into structured events.
"""

from typing import Any, Dict
from datetime import datetime
from agents.base_agent import BaseAgent


class DetectionAgent(BaseAgent):
    """
    Consumes FrameResult from the detector and emits a list of
    normalised incident dicts for downstream agents.
    """

    def __init__(self):
        super().__init__("detection")

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Input:  {"frame_result": FrameResult, "source": str, "frame_index": int}
        Output: {"incidents": [...], ...pass-through fields}
        """
        frame_result = data.get("frame_result")
        if frame_result is None:
            return data

        incidents = []
        for inc in frame_result.incidents:
            incidents.append({
                "type": inc["type"],
                "confidence": inc["confidence"],
                "class_name": inc["class_name"],
                "count": inc.get("count", 1),
                "person_count": frame_result.person_count,
                "inference_ms": frame_result.inference_ms,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        data["incidents"] = incidents
        data["detection_count"] = len(frame_result.detections)
        data["person_count"] = frame_result.person_count
        self._processed_count += 1
        self.logger.debug(f"Detected {len(incidents)} incident(s) in frame")
        return data
