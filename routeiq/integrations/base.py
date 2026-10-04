from typing import Protocol


class Integration(Protocol):
    def send(self, record: dict) -> None: ...


def make_record(request_id, text, result, source):
    return {
        "request_id": request_id,
        "text": text,
        "label": result.label,
        "confidence": result.confidence,
        "tier": result.tier,
        "source": source,
    }