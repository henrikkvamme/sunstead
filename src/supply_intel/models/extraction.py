from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from supply_intel.models.base import EvidenceSpanCandidate, TimestampedModel, VersionedModel
from supply_intel.models.events import (
    DisasterEvent,
    LogisticsPressureObservation,
    NewsEvent,
    PriceObservation,
    RecallEvent,
    RegulatoryEvent,
    ShortageEvent,
    StrikeEvent,
    TradeFlowObservation,
    TrendSignalObservation,
)
from supply_intel.models.medical import ExtractedRelationship, MedicalEntity


class MedicalExtractionOutput(VersionedModel):
    entities: list[MedicalEntity] = Field(default_factory=list)
    regulatory_events: list[RegulatoryEvent] = Field(default_factory=list)
    recall_events: list[RecallEvent] = Field(default_factory=list)
    shortage_events: list[ShortageEvent] = Field(default_factory=list)
    news_events: list[NewsEvent] = Field(default_factory=list)
    disaster_events: list[DisasterEvent] = Field(default_factory=list)
    strike_events: list[StrikeEvent] = Field(default_factory=list)
    price_observations: list[PriceObservation] = Field(default_factory=list)
    trade_flow_observations: list[TradeFlowObservation] = Field(default_factory=list)
    logistics_pressure_observations: list[LogisticsPressureObservation] = Field(
        default_factory=list
    )
    trend_signal_observations: list[TrendSignalObservation] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpanCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExtractionRun(TimestampedModel):
    raw_document_id: UUID | None = None
    document_chunk_id: UUID | None = None
    agent_name: str
    agent_version: str
    model_name: str
    prompt_hash: str
    input_hash: str
    output_schema: str
    output_schema_version: int = 1
    status: Literal["pending", "running", "succeeded", "failed"]
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    usage: dict[str, object] = Field(default_factory=dict)
    raw_output: dict[str, object] | None = None
    validated_output: dict[str, object] | None = None
    error: str | None = None
    correlation_id: UUID = Field(default_factory=uuid4)
    idempotency_key: str


class EntityMention(TimestampedModel):
    raw_document_id: UUID
    document_chunk_id: UUID | None = None
    extraction_run_id: UUID | None = None
    evidence_span_id: UUID | None = None
    entity_type: str
    mention_text: str
    normalized_mention: str
    candidate_external_ids: dict[str, str] = Field(default_factory=dict)
    canonical_entity_id: UUID | None = None
    resolution_status: Literal["unresolved", "resolved", "conflict", "needs_human_review"]
    resolution_confidence: float | None = Field(default=None, ge=0, le=1)
    resolution_method: str | None = None
    needs_review: bool = False
