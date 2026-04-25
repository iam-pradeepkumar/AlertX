"""
AlertX — Decision Agent
Assigns priority levels (LOW, MEDIUM, HIGH, CRITICAL) based on severity scores.
"""

from typing import Any, Dict
from agents.base_agent import BaseAgent
from backend.config import SEVERITY_THRESHOLDS


class DecisionAgent(BaseAgent):
    """
    Maps severity_score → priority level using configured thresholds.
    Also generates a human-readable summary for each incident.
    """

    def __init__(self):
        super().__init__("decision")

    def _score_to_priority(self, score: float) -> str:
        if score >= SEVERITY_THRESHOLDS["CRITICAL"]:
            return "CRITICAL"
        elif score >= SEVERITY_THRESHOLDS["HIGH"]:
            return "HIGH"
        elif score >= SEVERITY_THRESHOLDS["MEDIUM"]:
            return "MEDIUM"
        return "LOW"

    def _build_summary(self, inc: dict) -> str:
        itype = inc["type"].upper()
        conf = int(inc["confidence"] * 100)
        count = inc.get("count", 1)
        persons = inc.get("person_count", 0)

        parts = [f"{itype} detected"]
        if count > 1:
            parts.append(f"({count} objects)")
        parts.append(f"@ {conf}% confidence")
        if persons > 0:
            parts.append(f"| {persons} person(s) in frame")
        return " ".join(parts)

    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        incidents = data.get("incidents", [])

        for inc in incidents:
            score = inc.get("severity_score", 0)
            inc["priority"] = self._score_to_priority(score)
            inc["severity_label"] = self._score_to_priority(score)
            inc["summary"] = self._build_summary(inc)

        data["incidents"] = incidents
        self._processed_count += 1
        self.logger.debug(f"Priority assigned to {len(incidents)} incident(s)")
        return data
