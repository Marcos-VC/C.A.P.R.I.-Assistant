from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseSkill(ABC):
    name: str
    description: str

    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        pass
