"""
AlertX — Base Agent
Abstract base class for all agents in the multi-agent pipeline.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseAgent(ABC):
    """
    Every agent:
    - has a name
    - processes structured event data
    - returns structured event data
    - logs its actions
    """

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"alertx.agent.{name}")
        self._processed_count = 0

    @abstractmethod
    def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming event data and return enriched data.
        Each agent adds its own fields to the data dict.
        """
        ...

    @property
    def stats(self) -> Dict:
        return {
            "name": self.name,
            "processed": self._processed_count,
        }

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name}>"
