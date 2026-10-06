from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


MAX_TEXT_LENGTH = 5000


class RouteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_LENGTH)


class ReviewDecision(BaseModel):
    label: str


class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str

class RequestItem(BaseModel):
    id: int
    created_at: datetime
    text: str
    label: str | None
    confidence: float | None
    tier: str | None
    action: Literal["accepted", "human_review"]
    cost_usd: float | None
    latency_ms: float | None
    degraded: bool
    review_status: Literal["pending", "resolved"] | None
    final_label: str | None
    resolved_at: datetime | None
    delivery_status: Literal["pending", "sent", "failed"] | None
    delivery_error: str | None
    delivered_at: datetime | None

class ReviewerAgreement(BaseModel):
    resolved: int
    agreed: int
    rate: float | None = Field(
        description=(
            "Share of human-reviewed requests where the reviewer kept the model's suggestion. "
            "Only requests the model was unsure about are reviewed, so this is NOT the model's "
            "overall accuracy."
        )
    )

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
    data_source: Literal["public", "synthetic", "private"] | None
    examples: list[str]
    demo: bool = Field(description="True in the public demo: its data is reset regularly and sending texts is limited.")
    max_text_length: int = Field(description="The longest text POST /route accepts here, in characters.")

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
    reviewer_agreement: ReviewerAgreement
    review: ReviewCounts
    degraded: int
    cost_usd: float
    latency_ms: LatencyStats
    delivery: DeliveryCounts

class TimeseriesPoint(BaseModel):
    start: datetime
    requests: int
    accepted: int
    human_review: int
    cost_usd: float
    avg_latency_ms: float


class TimeseriesResponse(BaseModel):
    bucket: Literal["hour", "day"]
    since: datetime
    until: datetime
    points: list[TimeseriesPoint]


class EvaluationTier(BaseModel):
    name: str
    accept_threshold: float


class EvaluationSetup(BaseModel):
    name: str
    description: str
    accuracy: float
    accuracy_low: float = Field(description="Lower end of the 95% (Wilson) interval of the accuracy.")
    accuracy_high: float = Field(description="Upper end of the 95% (Wilson) interval of the accuracy.")
    macro_f1: float
    cost_per_1k_usd: float
    p50_ms: float
    p95_ms: float
    assumes_reviewer_always_right: bool = Field(
        description="True when the figure counts every request sent to a person as answered correctly."
    )


class CascadeGroup(BaseModel):
    kind: Literal["accepted", "human_review"]
    tier: str | None = Field(description="The tier that accepted the examples. Null for the ones sent to a person.")
    count: int
    correct: int = Field(description="How many of them got the true label. For human review: the model's suggestion.")


class CascadeBreakdown(BaseModel):
    groups: list[CascadeGroup]
    escalated: int = Field(description="Examples that needed more than one tier.")


class CalibrationBin(BaseModel):
    lower: float
    upper: float
    n: int
    mean_confidence: float
    accuracy: float


class TierCalibration(BaseModel):
    tier: str
    ece: float = Field(description="Expected calibration error: 0 means the confidence is what it claims to be.")
    bins: list[CalibrationBin]


class EvaluationResponse(BaseModel):
    """An offline measurement on labeled examples, not on live traffic."""
    domain: str
    split: str
    n: int
    data_source: Literal["public", "synthetic", "private"] | None
    tiers: list[EvaluationTier]
    setups: list[EvaluationSetup]
    cascade: CascadeBreakdown
    calibration: list[TierCalibration]

