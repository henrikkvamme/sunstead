from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from supply_intel.models.base import StrictBaseModel, TimestampedModel, VersionedModel

SafetyLevel = Literal[
    "safe_read",
    "safe_write_dev",
    "migration_write",
    "production_change",
    "credential_access",
]
CloudBootstrapMode = Literal["local", "aiven", "hybrid"]


class AivenProject(StrictBaseModel):
    project_name: str
    default_cloud: str | None = None


class AivenServiceRef(StrictBaseModel):
    project: str
    service_name: str
    service_type: str
    state: str | None = None


class AivenServiceSpec(VersionedModel):
    project: str
    service_name: str
    plan: str
    cloud: str
    environment: str = "dev-cloud"
    user_config: dict[str, object] = Field(default_factory=dict)


class PostgresServiceSpec(AivenServiceSpec):
    service_type: Literal["pg"] = "pg"
    required_extensions: list[str] = Field(default_factory=lambda: ["vector", "pg_trgm"])


class KafkaServiceSpec(AivenServiceSpec):
    service_type: Literal["kafka"] = "kafka"
    kafka_rest: bool = False
    schema_registry: bool = False


class GrafanaServiceSpec(AivenServiceSpec):
    service_type: Literal["grafana"] = "grafana"


class KafkaTopicSpec(VersionedModel):
    topic_name: str
    partitions: int = Field(ge=1)
    replication: int = Field(ge=1)
    cleanup_policy: Literal["delete", "compact", "compact,delete"] = "delete"
    retention_hours: int | None = Field(default=None, ge=1)
    config: dict[str, object] = Field(default_factory=dict)


class KafkaTopicBootstrapResult(VersionedModel):
    topic_name: str
    backend: Literal["dry_run", "aiven_mcp", "direct_admin"]
    status: Literal["planned", "created", "already_exists", "ensured"]
    partitions: int
    replication: int
    config: dict[str, object] = Field(default_factory=dict)


class QueryResult(VersionedModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, object]] = Field(default_factory=list)
    row_count: int = Field(ge=0)


class KafkaRecord(VersionedModel):
    key: str | None = None
    value: dict[str, object]
    headers: dict[str, str] = Field(default_factory=dict)


class ProduceResult(VersionedModel):
    topic: str
    produced: int = Field(ge=0)


class ConsumeResult(VersionedModel):
    topic: str
    records: list[KafkaRecord] = Field(default_factory=list)


class MetricsSnapshot(VersionedModel):
    service_name: str
    period: str
    metrics: dict[str, object] = Field(default_factory=dict)


class OperationalMetric(TimestampedModel):
    metric_name: str
    metric_value: float
    service: str
    idempotency_key: str
    unit: str | None = None
    source_id: str | None = None
    topic: str | None = None
    consumer_group: str | None = None
    correlation_id: UUID | None = None
    causation_id: UUID | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    tags: dict[str, str] = Field(default_factory=dict)


class LogEntry(VersionedModel):
    timestamp: datetime | None = None
    level: str | None = None
    message: str
    metadata: dict[str, object] = Field(default_factory=dict)


class LogBatch(VersionedModel):
    service_name: str
    entries: list[LogEntry] = Field(default_factory=list)


class LocalBootstrapSummary(VersionedModel):
    compose_file: str
    services: list[str] = Field(default_factory=list)
    topic_count: int = Field(ge=0)
    cypher_migrations: list[str] = Field(default_factory=list)
    dashboard_definitions: list[str] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    apply: bool = False


class LocalBootstrapResult(VersionedModel):
    summary: LocalBootstrapSummary
    status: Literal["started", "failed"]
    returncode: int
    stdout: str = ""
    stderr: str = ""


class GrafanaDashboardProvisionResult(VersionedModel):
    uid: str
    title: str | None = None
    status: str
    url: str | None = None
    version: int | None = None
    path: str | None = None


class GrafanaDatasourceProvisionResult(VersionedModel):
    uid: str
    name: str
    status: Literal["created", "updated"]
    datasource_id: int | None = None


class MCPAuditAction(VersionedModel):
    controller: str
    action: str
    safety_level: SafetyLevel
    project: str | None = None
    service_name: str | None = None
    request: dict[str, object]
    response_summary: dict[str, object] | None = None
    status: Literal["planned", "succeeded", "failed", "blocked", "requires_approval"] = "planned"
    destructive: bool = False
    requires_approval: bool = False
    approval_id: UUID | None = None
    actor: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    error: str | None = None


class MCPAuditLog(TimestampedModel):
    controller: str
    action: str
    project: str | None = None
    service_name: str | None = None
    request: dict[str, object]
    response_summary: dict[str, object] | None = None
    status: Literal["planned", "succeeded", "failed", "blocked", "requires_approval"]
    destructive: bool = False
    approval_id: UUID | None = None
    actor: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    error: str | None = None


def mcp_audit_log_from_action(action: MCPAuditAction) -> MCPAuditLog:
    metadata: dict[str, object] = {
        "safety_level": action.safety_level,
        "requires_approval": action.requires_approval,
    }
    return MCPAuditLog(
        controller=action.controller,
        action=action.action,
        project=action.project,
        service_name=action.service_name,
        request=action.request,
        response_summary=action.response_summary,
        status=action.status,
        destructive=action.destructive,
        approval_id=action.approval_id,
        actor=action.actor,
        started_at=action.started_at,
        finished_at=action.finished_at,
        error=action.error,
        metadata=metadata,
    )


class CloudBootstrapFallbackAction(VersionedModel):
    capability: str
    preferred_mcp_action: str
    fallback: str
    command: str | None = None
    requires_credentials: bool = False


class CloudBootstrapServicePlan(VersionedModel):
    service_role: Literal["postgres", "kafka", "grafana", "neo4j"]
    target: Literal["aiven", "local", "deferred"]
    service_name: str | None = None
    required: bool = True
    status: Literal["configured", "missing_decision", "planned", "deferred"]
    notes: list[str] = Field(default_factory=list)


class CloudBootstrapPlan(VersionedModel):
    mode: CloudBootstrapMode
    environment: str
    project: str | None = None
    topic_count: int = Field(ge=0)
    required_postgres_extensions: list[str] = Field(default_factory=list)
    services: list[CloudBootstrapServicePlan] = Field(default_factory=list)
    mcp_actions: list[MCPAuditAction] = Field(default_factory=list)
    fallback_actions: list[CloudBootstrapFallbackAction] = Field(default_factory=list)
    required_decisions: list[str] = Field(default_factory=list)
    ready_to_apply: bool = False
