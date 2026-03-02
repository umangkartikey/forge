from abc import ABC, abstractmethod

class ForgeModule(ABC):
    name = "base"
    version = "0.1"
    author = "unknown"
    description = "Base module"

    @abstractmethod
    def run(self, target, context):
        """
        Must return:
        {
            "success": bool,
            "data": dict,
            "confidence": float (0-1)
        }
        """
        pass