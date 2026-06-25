from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, ValidationError

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.events.envelope import build_event
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.kafka import DashboardGraphChatAnsweredPayload, EventEnvelope

DASHBOARD_GRAPH_CHAT_TOPIC = "dashboard.graph_chat_answered"
DASHBOARD_GRAPH_CHAT_SERVICE = "dashboard-graph-chat"
DASHBOARD_GRAPH_CHAT_AUDIT_FILENAME = "dashboard_graph_chat_audit.jsonl"


class DashboardGraphChatGraphStats(StrictBaseModel):
    curated_nodes: int = Field(alias="curatedNodes", ge=0)
    edges: int = Field(ge=0)
    live_sources: int = Field(default=0, alias="liveSources", ge=0)
    nodes: int = Field(ge=0)
    platform_edges: int = Field(alias="platformEdges", ge=0)
    platform_nodes: int = Field(alias="platformNodes", ge=0)
    source_graph_nodes: int = Field(default=0, alias="sourceGraphNodes", ge=0)
    source_graph_relationships: int = Field(
        default=0,
        alias="sourceGraphRelationships",
        ge=0,
    )
    watch_signals: int = Field(default=0, alias="watchSignals", ge=0)

    def payload_dict(self) -> dict[str, int]:
        return {
            "curated_nodes": self.curated_nodes,
            "edges": self.edges,
            "live_sources": self.live_sources,
            "nodes": self.nodes,
            "platform_edges": self.platform_edges,
            "platform_nodes": self.platform_nodes,
            "source_graph_nodes": self.source_graph_nodes,
            "source_graph_relationships": self.source_graph_relationships,
            "watch_signals": self.watch_signals,
        }


class DashboardGraphChatAuditMetadata(StrictBaseModel):
    graph_data_mode: Literal["curated_fallback", "platform_snapshot"] = Field(alias="graphDataMode")
    output_mode: Literal["deterministic_graph_summary"] = Field(alias="outputMode")
    live_sources: int = Field(default=0, alias="liveSources", ge=0)
    platform_edges: int = Field(alias="platformEdges", ge=0)
    platform_nodes: int = Field(alias="platformNodes", ge=0)
    snapshot_generated_at: datetime | None = Field(default=None, alias="snapshotGeneratedAt")
    snapshot_mode: Literal["file_snapshot", "neo4j_snapshot", "none", "unknown_snapshot"] = Field(
        default="unknown_snapshot",
        alias="snapshotMode",
    )
    source_graph_nodes: int = Field(default=0, alias="sourceGraphNodes", ge=0)
    source_graph_relationships: int = Field(
        default=0,
        alias="sourceGraphRelationships",
        ge=0,
    )
    watch_signals: int = Field(default=0, alias="watchSignals", ge=0)

    def payload_dict(self) -> dict[str, object]:
        return {
            "graph_data_mode": self.graph_data_mode,
            "output_mode": self.output_mode,
            "live_sources": self.live_sources,
            "platform_edges": self.platform_edges,
            "platform_nodes": self.platform_nodes,
            "snapshot_generated_at": (
                _as_utc(self.snapshot_generated_at).isoformat().replace("+00:00", "Z")
                if self.snapshot_generated_at
                else None
            ),
            "snapshot_mode": self.snapshot_mode,
            "source_graph_nodes": self.source_graph_nodes,
            "source_graph_relationships": self.source_graph_relationships,
            "watch_signals": self.watch_signals,
        }


class DashboardGraphChatSafety(StrictBaseModel):
    advice_scope: Literal["supply_chain_intelligence_only"] = Field(alias="adviceScope")
    clinical_advice: bool = Field(alias="clinicalAdvice")
    patient_identifiable_data: bool = Field(alias="patientIdentifiableData")

    def payload_dict(self) -> dict[str, object]:
        return {
            "advice_scope": self.advice_scope,
            "clinical_advice": self.clinical_advice,
            "patient_identifiable_data": self.patient_identifiable_data,
        }


class DashboardGraphChatSourceRef(StrictBaseModel):
    meta: str
    title: str
    url: str

    def payload_dict(self) -> dict[str, str]:
        return {"meta": self.meta, "title": self.title, "url": self.url}


class DashboardGraphChatAuditRecord(StrictBaseModel):
    audit_id: UUID = Field(alias="auditId")
    audit_type: Literal["dashboard.graph_chat_answer"] = Field(alias="auditType")
    correlation_id: UUID = Field(alias="correlationId")
    created_at: datetime = Field(alias="createdAt")
    event_type: Literal["dashboard.graph_chat_answered"] = Field(alias="eventType")
    graph_stats: DashboardGraphChatGraphStats = Field(alias="graphStats")
    idempotency_key: str = Field(alias="idempotencyKey", min_length=1)
    input_hash: str = Field(alias="inputHash", min_length=64, max_length=64)
    input_length: int = Field(alias="inputLength", ge=0)
    metadata: DashboardGraphChatAuditMetadata
    neighbor_node_ids: list[str] = Field(alias="neighborNodeIds")
    node_id: str | None = Field(default=None, alias="nodeId")
    output_hash: str = Field(alias="outputHash", min_length=64, max_length=64)
    output_schema: Literal["SupplyGraphQuestionResponse"] = Field(alias="outputSchema")
    output_schema_version: Literal[1] = Field(alias="outputSchemaVersion")
    related_node_ids: list[str] = Field(alias="relatedNodeIds")
    safety: DashboardGraphChatSafety
    selected_node_id: str | None = Field(alias="selectedNodeId")
    service: Literal["dashboard-graph-chat"]
    source_refs: list[DashboardGraphChatSourceRef] = Field(alias="sourceRefs")
    status: Literal["succeeded"]
    topic: Literal["dashboard.graph_chat_answered"]


class DashboardGraphChatAuditImportSummary(StrictBaseModel):
    audit_path: str
    audit_rows_seen: int
    events_created: int
    events_skipped: int
    event_ids: list[UUID]


def default_dashboard_graph_chat_audit_path(data_dir: Path) -> Path:
    return data_dir / DASHBOARD_GRAPH_CHAT_AUDIT_FILENAME


def dashboard_graph_chat_payload_from_audit(
    audit: DashboardGraphChatAuditRecord | Mapping[str, Any],
) -> DashboardGraphChatAnsweredPayload:
    record = _coerce_audit_record(audit)
    return DashboardGraphChatAnsweredPayload(
        audit_id=record.audit_id,
        selected_node_id=record.selected_node_id,
        requested_node_id=record.node_id,
        input_hash=record.input_hash,
        input_length=record.input_length,
        output_hash=record.output_hash,
        output_schema=record.output_schema,
        output_schema_version=record.output_schema_version,
        graph_stats=record.graph_stats.payload_dict(),
        metadata=record.metadata.payload_dict(),
        neighbor_node_ids=record.neighbor_node_ids,
        related_node_ids=record.related_node_ids,
        source_refs=[source_ref.payload_dict() for source_ref in record.source_refs],
        safety=record.safety.payload_dict(),
        status=record.status,
    )


def dashboard_graph_chat_event_from_audit(
    audit: DashboardGraphChatAuditRecord | Mapping[str, Any],
) -> EventEnvelope:
    record = _coerce_audit_record(audit)
    payload = dashboard_graph_chat_payload_from_audit(record)
    event = build_event(
        event_type=DASHBOARD_GRAPH_CHAT_TOPIC,
        service=record.service,
        payload=payload.model_dump(mode="json"),
        idempotency_key=f"{DASHBOARD_GRAPH_CHAT_TOPIC}:{record.audit_id}",
        source_id="dashboard_graph_chat_audit_jsonl",
        correlation_id=record.correlation_id,
    )
    event.emitted_at = _as_utc(record.created_at)
    return event


def iter_dashboard_graph_chat_audit_records(
    audit_path: Path,
) -> Iterator[DashboardGraphChatAuditRecord]:
    if not audit_path.exists():
        return
    with audit_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except JSONDecodeError as exc:
                raise ValueError(f"{audit_path}:{line_number} contains invalid JSON") from exc
            try:
                yield DashboardGraphChatAuditRecord.model_validate(row)
            except ValidationError as exc:
                raise ValueError(
                    f"{audit_path}:{line_number} is not a dashboard graph-chat audit row"
                ) from exc


def import_dashboard_graph_chat_audit_events(
    *,
    audit_path: Path,
    store: FileEvidenceStore,
) -> DashboardGraphChatAuditImportSummary:
    rows_seen = 0
    events_created = 0
    events_skipped = 0
    event_ids: list[UUID] = []

    for record in iter_dashboard_graph_chat_audit_records(audit_path):
        rows_seen += 1
        event = dashboard_graph_chat_event_from_audit(record)
        if store.write_event(event):
            events_created += 1
        else:
            events_skipped += 1
        event_ids.append(event.event_id)

    return DashboardGraphChatAuditImportSummary(
        audit_path=str(audit_path),
        audit_rows_seen=rows_seen,
        events_created=events_created,
        events_skipped=events_skipped,
        event_ids=event_ids,
    )


def _coerce_audit_record(
    audit: DashboardGraphChatAuditRecord | Mapping[str, Any],
) -> DashboardGraphChatAuditRecord:
    if isinstance(audit, DashboardGraphChatAuditRecord):
        return audit
    return DashboardGraphChatAuditRecord.model_validate(audit)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
