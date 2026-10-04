from dataclasses import dataclass
from typing import Protocol


@dataclass
class Prediction:
    label: str
    confidence: float
    cost_usd: float = 0.0


class Classifier(Protocol):
    def classify(self, text: str, labels: list[str]) -> Prediction: ...