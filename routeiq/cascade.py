import time
from dataclasses import dataclass


@dataclass
class RouteResult:
    label: str
    confidence: float
    tier: str
    action: str
    cost_usd: float
    latency_ms: float

def route(text, labels, tiers):
    if not tiers:
        raise ValueError("no tiers configured")
    start = time.perf_counter()
    total_cost = 0.0

    for tier, clf in tiers:
        pred = clf.classify(text, labels)
        total_cost += pred.cost_usd
        if pred.confidence >= tier["accept_threshold"]:
            action = "accepted"
            break
    else:
        action = "human_review"

    latency_ms = (time.perf_counter() - start) * 1000
    return RouteResult(
        label=pred.label,
        confidence=pred.confidence,
        tier=tier["name"],
        action=action,
        cost_usd=total_cost,
        latency_ms=latency_ms,
    )