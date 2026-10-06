from routeiq.schemas import MAX_TEXT_LENGTH, ConfigResponse, LabelInfo, TierInfo
from routeiq.redact import redact_urls
from routeiq.schemas import RequestItem


def request_item(row):
    return RequestItem(
        id=row["id"],
        created_at=row["created_at"],
        text=row["text"],
        label=row["label"],
        confidence=row["confidence"],
        tier=row["tier"],
        action=row["action"],
        cost_usd=row["cost_usd"],
        latency_ms=row["latency_ms"],
        degraded=row["error"] is not None,
        review_status=row["review_status"],
        final_label=row["final_label"],
        resolved_at=row["resolved_at"],
        delivery_status=row["delivery_status"],
        delivery_error=redact_urls(row["delivery_error"]),
        delivered_at=row["delivered_at"],
    )

def describe_config(config=None, labels=None, tiers=None, demo=None):
    """`demo` is the DemoSettings of the public demo, or None."""
    max_text_length = demo.max_text if demo is not None else MAX_TEXT_LENGTH
    if config is not None:
        descriptions = config.get("label_descriptions") or {}
        return ConfigResponse(
            domain=config["domain"],
            task=config.get("task"),
            labels=[LabelInfo(name=name, description=descriptions.get(name)) for name in config["labels"]],
            tiers=[
                TierInfo(
                    name=tier["name"],
                    model=tier["model"],
                    model_id=tier.get("model_id"),
                    accept_threshold=tier["accept_threshold"],
                )
                for tier in config["tiers"]
            ],
            target_type=(config.get("target") or {}).get("type"),
            data_source=config.get("data_source"),
            examples=list(config.get("examples") or []),
            demo=demo is not None,
            max_text_length=max_text_length,
        )
    return ConfigResponse(
        domain=None,
        task=None,
        labels=[LabelInfo(name=name, description=None) for name in labels or []],
        tiers=[
            TierInfo(name=tier["name"], model=tier.get("model"), model_id=None,
                     accept_threshold=tier["accept_threshold"])
            for tier, _ in tiers or []
        ],
        target_type=None,
        data_source=None,
        examples=[],
        demo=demo is not None,
        max_text_length=max_text_length,
    )