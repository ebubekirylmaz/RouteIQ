from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class ReviewDecision(BaseModel):
    label: str


class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str


class LabelInfo(BaseModel):
    name: str
    description: str | None


class TierInfo(BaseModel):
    name: str
    model: str | None
    model_id: str | None
    accept_threshold: float


class ConfigResponse(BaseModel):
    domain: str | None
    task: str | None
    labels: list[LabelInfo]
    tiers: list[TierInfo]
    target_type: str | None

class RouteResponse(BaseModel):
    label: str | None
    confidence: float
    tier: str | None
    action: Literal["accepted", "human_review"]
    cost_usd: float
    latency_ms: float
    degraded: bool
    request_id: int


class ReviewItem(BaseModel):
    id: int
    created_at: datetime
    text: str
    suggested_label: str | None
    confidence: float | None
    tier: str | None


class ReviewResolved(BaseModel):
    id: int
    status: Literal["resolved"]
    final_label: str


class RetryResult(BaseModel):
    retried: int
    sent: int
    failed: int


class LatencyStats(BaseModel):
    avg: float
    p95: float


class ReviewCounts(BaseModel):
    pending: int
    resolved: int


class DeliveryCounts(BaseModel):
    pending: int
    sent: int
    failed: int
    retryable: int


class StatsResponse(BaseModel):
    requests: int
    accepted_by_tier: dict[str, int]
    human_review: int
    review: ReviewCounts
    degraded: int
    cost_usd: float
    latency_ms: LatencyStats
    delivery: DeliveryCounts