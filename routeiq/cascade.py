import time
from dataclasses import dataclass


@dataclass
class RouteResult:
    label: str | None
    confidence: float
    tier: str | None
    action: str
    cost_usd: float
    latency_ms: float
    error: str | None = None


def route(text, labels, tiers):
    if not tiers:
        raise ValueError("no tiers configured")
    start = time.perf_counter()
    total_cost = 0.0

    pred = None
    used_tier = None
    error = None

    for tier, clf in tiers:
        try:
            p = clf.classify(text, labels)
        except Exception as e:
            error = f"{tier['name']}: {e}"
            continue
        pred, used_tier = p, tier
        total_cost += p.cost_usd
        if p.confidence >= tier["accept_threshold"]:
            action = "accepted"
            break
    else:
        action = "human_review"

    latency_ms = (time.perf_counter() - start) * 1000
    return RouteResult(
        label=pred.label if pred else None,
        confidence=pred.confidence if pred else 0.0,
        tier=used_tier["name"] if used_tier else None,
        action=action,
        cost_usd=total_cost,
        latency_ms=latency_ms,
        error=error,
    )
