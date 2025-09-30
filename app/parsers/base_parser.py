from abc import ABC, abstractmethod

class BaseParser(ABC):
    @abstractmethod
    def parse(self, text: str, metadata: dict | None = None) -> dict: ...
