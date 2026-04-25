"""
AlertX — Learning Agent
Logs all detections to a JSONL file for future analysis / model improvement.
This is a lightweight "learning" mechanism — no auto-retraining.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict

from agents.base_agent import BaseAgent
from backend.config import LEARNING_LOG


class LearningAgent(BaseAgent):
    """
    Appends every processed event to a JSONL log file.
    This log can be used offline to:
    - Identify false positives
    - Find patterns in detections
    - Curate training data for model improvement
    """

    def __init__(self):
        super().__init__("learning")
        os.makedirs(os.path.dirname(LEARNING_LOG), exist_ok=True)

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        incidents = data.get("incidents", [])
        if not incidents:
            return data

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "source": data.get("source", "unknown"),
            "frame_index": data.get("frame_index", 0),
            "person_count": data.get("person_count", 0),
            "detection_count": data.get("detection_count", 0),
            "incidents": incidents,
        }

        try:
            with open(LEARNING_LOG, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except IOError as e:
            self.logger.error(f"Failed to write learning log: {e}")

        self._processed_count += 1
        self.logger.debug(f"Logged {len(incidents)} incident(s) for learning")
        return data
