"""
AlertX — Threat Analysis Agent
Assigns a severity score to each incident based on type,
confidence, and contextual signals (person count, object count).
"""

from typing import Any, Dict
from agents.base_agent import BaseAgent
from backend.config import CROWD_THRESHOLD


# Base severity weights by incident type
SEVERITY_WEIGHTS = {
    "fire": 0.90,
    "weapon": 0.95,
    "fight": 0.85,
    "vehicle": 0.60,
    "crowd": 0.55,
    "disturbance": 0.70,
}


class ThreatAnalysisAgent(BaseAgent):
    """
    Enriches each incident with a 0-1 severity score.
    Score = base_weight × confidence × context_multiplier
    """

    def __init__(self):
        super().__init__("threat_analysis")

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        incidents = data.get("incidents", [])
        person_count = data.get("person_count", 0)

        for inc in incidents:
            base = SEVERITY_WEIGHTS.get(inc["type"], 0.50)
            confidence = inc["confidence"]

            # Context multiplier
            multiplier = 1.0

            # More people → higher perceived threat
            if person_count > CROWD_THRESHOLD:
                multiplier += 0.15

            # Multiple objects of same incident type
            if inc.get("count", 1) > 2:
                multiplier += 0.10

            # High-confidence boosts slightly
            if confidence > 0.80:
                multiplier += 0.05

            severity_score = min(base * confidence * multiplier, 1.0)
            inc["severity_score"] = round(severity_score, 3)

        data["incidents"] = incidents
        self._processed_count += 1
        self.logger.debug(f"Threat analysis complete for {len(incidents)} incident(s)")
        return data
