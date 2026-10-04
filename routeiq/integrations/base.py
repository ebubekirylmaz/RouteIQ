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


def record_from_row(row):
    human = row["final_label"] is not None
    return {
        "request_id": row["id"],
        "text": row["text"],
        "label": row["final_label"] if human else row["label"],
        "confidence": row["confidence"],
        "tier": "human" if human else row["tier"],
        "source": "human_review" if human else "cascade",
    }