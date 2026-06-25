from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from supply_intel.models.base import TimestampedModel, VersionedModel

Severity = Literal["critical", "high", "medium", "low", "info"]


class RiskScope(VersionedModel):
    type: str
    graph_key: str | None = None
    entity_id: UUID | None = None


class RiskCandidate(TimestampedModel):
    candidate_key: str
    risk_type: str
    scope: RiskScope
    signals: list[dict[str, object]] = Field(default_factory=list)
    initial_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    evidence_span_ids: list[UUID] = Field(default_factory=list)


class RiskCase(TimestampedModel):
    case_key: str
    title: str
    risk_type: str
    scope_type: str
    scope_entity_id: UUID | None = None
    graph_node_key: str | None = None
    status: Literal[
        "candidate",
        "investigating",
        "watch",
        "confirmed",
        "dismissed",
        "resolved",
        "needs_human_review",
    ]
    severity: Severity
    risk_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    component_scores: dict[str, float] = Field(default_factory=dict)
    opened_at: datetime
    closed_at: datetime | None = None
    latest_verdict_id: UUID | None = None


class RiskFeatureSnapshot(TimestampedModel):
    risk_case_id: UUID
    case_key: str
    scope_type: str
    scope_entity_id: UUID | None = None
    graph_node_key: str | None = None
    feature_name: str
    value: float
    window: str = "point_in_time"
    evidence_span_ids: list[UUID] = Field(default_factory=list)
    computed_at: datetime
    feature_version: str = "risk_features.v1"


class RiskVerdict(TimestampedModel):
    risk_case_id: UUID
    verdict_type: Literal["confirmed_risk", "possible_risk", "watch", "dismissed", "resolved"]
    severity: Severity
    risk_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    summary: str
    key_drivers: list[str] = Field(default_factory=list)
    affected_entities: list[dict[str, object]] = Field(default_factory=list)
    evidence_span_ids: list[UUID] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    next_review_at: datetime | None = None


class RiskAlert(TimestampedModel):
    alert_key: str
    risk_case_id: UUID
    alert_type: str
    severity: Severity
    status: Literal["open", "acknowledged", "resolved"]
    title: str
    body: str
    channels: list[str] = Field(default_factory=list)
    payload: dict[str, object] = Field(default_factory=dict)
    first_emitted_at: datetime
    last_emitted_at: datetime
