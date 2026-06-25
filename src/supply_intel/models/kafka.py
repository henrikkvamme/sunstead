from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field

from supply_intel.models.base import StrictBaseModel, VersionedModel
from supply_intel.models.risk import RiskScope


class EventSource(StrictBaseModel):
    service: str
    source_id: str | None = None
    instance_id: str | None = None


class TraceMetadata(StrictBaseModel):
    trace_id: UUID = Field(default_factory=uuid4)
    span_id: UUID = Field(default_factory=uuid4)
    source_run_id: UUID | None = None
    raw_document_id: UUID | None = None


class EventEnvelope(VersionedModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    source: EventSource
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID = Field(default_factory=uuid4)
    causation_id: UUID | None = None
    idempotency_key: str
    trace: TraceMetadata = Field(default_factory=TraceMetadata)
    payload: dict[str, Any]


class IngestJobPayload(VersionedModel):
    source_id: str
    source_run_id: UUID
    run_type: Literal["scheduled", "manual", "backfill", "replay", "test"]
    cursor: dict[str, Any] = Field(default_factory=dict)
    config_hash: str
    requested_at: datetime


class RawDocumentCreatedPayload(VersionedModel):
    source_id: str
    source_run_id: UUID
    raw_document_id: UUID
    source_url: str | None = None
    content_hash: str
    content_type: str | None = None
    fetched_at: datetime


class DocumentParsedPayload(VersionedModel):
    raw_document_id: UUID
    document_chunk_ids: list[UUID] = Field(default_factory=list)
    parser_profile: str
    chunk_count: int = Field(ge=0)


class ExtractionCompletedPayload(VersionedModel):
    extraction_run_id: UUID
    raw_document_id: UUID
    document_chunk_id: UUID | None = None
    agent_name: str
    output_schema: str
    entity_mention_ids: list[UUID] = Field(default_factory=list)
    evidence_span_ids: list[UUID] = Field(default_factory=list)
    status: str


class GraphNodeUpsertPayload(VersionedModel):
    graph_node_key: str
    labels: list[str]
    properties: dict[str, Any] = Field(default_factory=dict)
    source_document_id: UUID | None = None
    evidence_span_id: UUID | None = None
    extraction_run_id: UUID | None = None
    confidence: float = Field(ge=0, le=1)


class GraphRelationshipUpsertPayload(VersionedModel):
    relationship_key: str
    from_key: str
    to_key: str
    relationship_type: str
    properties: dict[str, Any]


class RiskCaseCreatedPayload(VersionedModel):
    risk_case_id: UUID
    case_key: str
    risk_type: str
    severity: str
    status: str
    risk_score: float
    confidence: float
    evidence_span_ids: list[UUID] = Field(default_factory=list)


class RiskCandidatePayload(VersionedModel):
    candidate_key: str
    risk_type: str
    scope: RiskScope
    signals: list[dict[str, Any]] = Field(default_factory=list)
    initial_score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    evidence_span_ids: list[UUID] = Field(default_factory=list)


class RiskVerdictPayload(VersionedModel):
    risk_case_id: UUID
    verdict_type: str
    severity: str
    risk_score: float
    confidence: float
    summary: str
    evidence_span_ids: list[UUID] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class RiskAlertPayload(VersionedModel):
    alert_key: str
    risk_case_id: UUID
    alert_type: str
    severity: str
    status: str
    title: str
    channels: list[str] = Field(default_factory=list)


class AgentFindingPayload(VersionedModel):
    risk_case_id: UUID
    agent_name: str
    model_name: str
    prompt_hash: str
    input_hash: str
    output_schema: str
    output_schema_version: int
    finding_type: str
    finding_id: UUID
    evidence_span_ids: list[UUID] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    status: str


class AgentAuditLogPayload(VersionedModel):
    risk_case_id: UUID
    case_key: str
    action: str
    agent_names: list[str] = Field(default_factory=list)
    finding_ids: list[UUID] = Field(default_factory=list)
    status: str


class DashboardGraphChatAnsweredPayload(VersionedModel):
    audit_id: UUID
    selected_node_id: str | None = None
    requested_node_id: str | None = None
    input_hash: str = Field(min_length=64, max_length=64)
    input_length: int = Field(ge=0)
    output_hash: str = Field(min_length=64, max_length=64)
    output_schema: str
    output_schema_version: int
    graph_stats: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    neighbor_node_ids: list[str] = Field(default_factory=list)
    related_node_ids: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, str]] = Field(default_factory=list)
    safety: dict[str, object] = Field(default_factory=dict)
    status: str


class OpsMetricPayload(VersionedModel):
    metric_name: str
    metric_value: float
    service: str
    idempotency_key: str
    unit: str | None = None
    source_id: str | None = None
    topic: str | None = None
    consumer_group: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DeadLetterPayload(VersionedModel):
    original_topic: str
    original_key: str | None = None
    consumer_group: str | None = None
    stage: str
    error_type: str
    error_message: str
    retryable: bool
    original_event: dict[str, Any] | None = None
    original_value: str | None = None
    failed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventProcessingResult(VersionedModel):
    status: Literal["processed", "deadlettered"]
    topic: str
    event_id: UUID | None = None
    committed: bool
    deadletter_topic: str | None = None
