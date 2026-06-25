from __future__ import annotations

import copy
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from supply_intel.db.postgres import PostgresConnection, connect_postgres
from supply_intel.db.repositories.evidence import FileEvidenceStore, PostgresEvidenceStore
from supply_intel.entity_resolution.service import (
    CanonicalEntity,
    EntityAlias,
    HumanFeedback,
    HumanReviewTask,
)
from supply_intel.models.agents import AgentFinding
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.documents import DocumentChunk, EvidenceSpan
from supply_intel.models.extraction import EntityMention, ExtractionRun
from supply_intel.models.graph import GraphNodeUpsert, GraphRelationshipUpsert
from supply_intel.models.infra import MCPAuditLog, OperationalMetric
from supply_intel.models.risk import (
    RiskAlert,
    RiskCandidate,
    RiskCase,
    RiskFeatureSnapshot,
    RiskVerdict,
)
from supply_intel.models.source import (
    IngestionError,
    RawDocument,
    SourceConfig,
    SourceCursor,
    SourceHealth,
    SourceRun,
)
from supply_intel.settings import Settings


class PostgresEvidenceSyncSummary(StrictBaseModel):
    backend: str = "postgres"
    source_ids: list[str]
    rows_by_collection: dict[str, int] = Field(default_factory=dict)
    inserted_by_collection: dict[str, int] = Field(default_factory=dict)

    @property
    def total_rows(self) -> int:
        return sum(self.rows_by_collection.values())

    @property
    def total_inserted(self) -> int:
        return sum(self.inserted_by_collection.values())


@dataclass(frozen=True)
class LocalEvidenceSyncRows:
    configs: list[SourceConfig]
    source_ids: list[str]
    collections: dict[str, list[dict[str, Any]]]


def plan_local_evidence_to_postgres(
    *,
    settings: Settings,
    configs: Iterable[SourceConfig],
) -> PostgresEvidenceSyncSummary:
    sync_rows = collect_local_evidence_sync_rows(
        local_store=FileEvidenceStore(settings.data_dir),
        configs=list(configs),
    )
    return PostgresEvidenceSyncSummary(
        source_ids=sync_rows.source_ids,
        rows_by_collection={
            "data_sources": len(sync_rows.configs),
            **{collection: len(rows) for collection, rows in sync_rows.collections.items()},
        },
        inserted_by_collection={
            "data_sources": 0,
            **{collection: 0 for collection in sync_rows.collections},
        },
    )


async def sync_local_evidence_to_postgres(
    *,
    settings: Settings,
    configs: Iterable[SourceConfig],
    connection: PostgresConnection | None = None,
) -> PostgresEvidenceSyncSummary:
    raw_connection: PostgresConnection | None = None
    if connection is None:
        raw_connection = await connect_postgres(settings)
        connection = raw_connection
    try:
        return await sync_local_evidence_to_postgres_store(
            local_store=FileEvidenceStore(settings.data_dir),
            postgres_store=PostgresEvidenceStore(connection),
            configs=list(configs),
        )
    finally:
        if raw_connection is not None:
            await raw_connection.close()


async def sync_local_evidence_to_postgres_store(
    *,
    local_store: FileEvidenceStore,
    postgres_store: PostgresEvidenceStore,
    configs: list[SourceConfig],
) -> PostgresEvidenceSyncSummary:
    sync_rows = collect_local_evidence_sync_rows(local_store=local_store, configs=configs)
    summary = PostgresEvidenceSyncSummary(source_ids=sync_rows.source_ids)
    for config in sync_rows.configs:
        inserted = await postgres_store.register_source(config)
        _record(summary, "data_sources", inserted)

    source_run_ids = await _sync_collection_with_id_map(
        summary,
        collection="source_runs",
        rows=sync_rows.collections["source_runs"],
        model=SourceRun,
        writer=postgres_store.write_source_run,
    )
    raw_document_ids = await _sync_collection_with_id_map(
        summary,
        collection="raw_documents",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["raw_documents"],
            field_maps={"source_run_id": source_run_ids},
        ),
        model=RawDocument,
        writer=postgres_store.write_raw_document,
    )
    document_chunk_ids = await _sync_collection_with_id_map(
        summary,
        collection="document_chunks",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["document_chunks"],
            field_maps={"raw_document_id": raw_document_ids},
        ),
        model=DocumentChunk,
        writer=postgres_store.write_chunk,
    )
    extraction_run_ids = await _sync_collection_with_id_map(
        summary,
        collection="extraction_runs",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["extraction_runs"],
            field_maps={
                "raw_document_id": raw_document_ids,
                "document_chunk_id": document_chunk_ids,
            },
        ),
        model=ExtractionRun,
        writer=postgres_store.write_extraction_run,
    )
    evidence_span_ids = await _sync_collection_with_id_map(
        summary,
        collection="evidence_spans",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["evidence_spans"],
            field_maps={
                "raw_document_id": raw_document_ids,
                "document_chunk_id": document_chunk_ids,
                "extraction_run_id": extraction_run_ids,
            },
        ),
        model=EvidenceSpan,
        writer=postgres_store.write_evidence_span,
    )
    canonical_entity_ids = await _sync_collection_with_id_map(
        summary,
        collection="canonical_entities",
        rows=sync_rows.collections["canonical_entities"],
        model=CanonicalEntity,
        writer=postgres_store.write_canonical_entity,
    )
    await _sync_collection(
        summary,
        collection="entity_aliases",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["entity_aliases"],
            field_maps={
                "canonical_entity_id": canonical_entity_ids,
                "evidence_span_id": evidence_span_ids,
            },
        ),
        model=EntityAlias,
        writer=postgres_store.write_entity_alias,
    )
    await _sync_collection(
        summary,
        collection="entity_mentions",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["entity_mentions"],
            field_maps={
                "raw_document_id": raw_document_ids,
                "document_chunk_id": document_chunk_ids,
                "extraction_run_id": extraction_run_ids,
                "evidence_span_id": evidence_span_ids,
                "canonical_entity_id": canonical_entity_ids,
            },
        ),
        model=EntityMention,
        writer=postgres_store.write_entity_mention,
    )
    await _sync_collection(
        summary,
        collection="source_cursors",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["source_cursors"],
            field_maps={"updated_by_run_id": source_run_ids},
        ),
        model=SourceCursor,
        writer=postgres_store.write_source_cursor,
    )
    await _sync_collection(
        summary,
        collection="graph_node_upserts",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["graph_node_upserts"],
            field_maps={
                "source_document_id": raw_document_ids,
                "evidence_span_id": evidence_span_ids,
                "extraction_run_id": extraction_run_ids,
            },
        ),
        model=GraphNodeUpsert,
        writer=postgres_store.write_graph_node,
    )
    await _sync_collection(
        summary,
        collection="graph_relationship_upserts",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["graph_relationship_upserts"],
            nested_field_maps={
                "properties": {
                    "source_document_id": raw_document_ids,
                    "evidence_span_id": evidence_span_ids,
                    "extraction_run_id": extraction_run_ids,
                }
            },
        ),
        model=GraphRelationshipUpsert,
        writer=postgres_store.write_graph_relationship,
    )
    await _sync_collection(
        summary,
        collection="risk_candidates",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["risk_candidates"],
            list_field_maps={"evidence_span_ids": evidence_span_ids},
            nested_field_maps={"scope": {"entity_id": canonical_entity_ids}},
        ),
        model=RiskCandidate,
        writer=postgres_store.write_risk_candidate,
    )
    risk_case_ids = await _sync_collection_with_id_map(
        summary,
        collection="risk_cases",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["risk_cases"],
            field_maps={"scope_entity_id": canonical_entity_ids},
        ),
        model=RiskCase,
        writer=postgres_store.write_risk_case,
    )
    remapped_risk_case_rows = _rows_with_uuid_remaps(
        sync_rows.collections["risk_feature_snapshots"],
        field_maps={
            "risk_case_id": risk_case_ids,
            "scope_entity_id": canonical_entity_ids,
        },
        list_field_maps={"evidence_span_ids": evidence_span_ids},
    )
    await _sync_collection(
        summary,
        collection="risk_feature_snapshots",
        rows=remapped_risk_case_rows,
        model=RiskFeatureSnapshot,
        writer=postgres_store.write_risk_feature_snapshot,
    )
    await _sync_collection(
        summary,
        collection="risk_verdicts",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["risk_verdicts"],
            field_maps={"risk_case_id": risk_case_ids},
            list_field_maps={"evidence_span_ids": evidence_span_ids},
        ),
        model=RiskVerdict,
        writer=postgres_store.write_risk_verdict,
    )
    await _sync_collection(
        summary,
        collection="agent_findings",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["agent_findings"],
            field_maps={"risk_case_id": risk_case_ids},
            list_field_maps={"evidence_span_ids": evidence_span_ids},
        ),
        model=AgentFinding,
        writer=postgres_store.write_agent_finding,
    )
    await _sync_collection(
        summary,
        collection="risk_alerts",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["risk_alerts"],
            field_maps={"risk_case_id": risk_case_ids},
        ),
        model=RiskAlert,
        writer=postgres_store.write_risk_alert,
    )
    ingestion_error_ids = await _sync_collection_with_id_map(
        summary,
        collection="ingestion_errors",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["ingestion_errors"],
            field_maps={
                "source_run_id": source_run_ids,
                "raw_document_id": raw_document_ids,
            },
        ),
        model=IngestionError,
        writer=postgres_store.write_ingestion_error,
    )
    human_feedback_target_ids = {
        "raw_documents": raw_document_ids,
        "document_chunks": document_chunk_ids,
        "extraction_runs": extraction_run_ids,
        "evidence_spans": evidence_span_ids,
        "canonical_entities": canonical_entity_ids,
        "risk_cases": risk_case_ids,
        "ingestion_errors": ingestion_error_ids,
    }
    human_review_task_ids = await _sync_collection_with_id_map(
        summary,
        collection="human_review_queue",
        rows=_rows_with_human_review_task_remaps(
            sync_rows.collections["human_review_queue"],
            target_id_maps=human_feedback_target_ids,
            evidence_span_ids=evidence_span_ids,
        ),
        model=HumanReviewTask,
        writer=postgres_store.write_human_review_task,
    )
    await _sync_collection(
        summary,
        collection="human_feedback",
        rows=_rows_with_human_feedback_remaps(
            sync_rows.collections["human_feedback"],
            target_id_maps=human_feedback_target_ids,
            human_review_task_ids=human_review_task_ids,
        ),
        model=HumanFeedback,
        writer=postgres_store.write_human_feedback,
    )
    await _sync_collection(
        summary,
        collection="mcp_audit_log",
        rows=sync_rows.collections["mcp_audit_log"],
        model=MCPAuditLog,
        writer=postgres_store.write_mcp_audit_log,
    )
    await _sync_collection(
        summary,
        collection="ops_metrics",
        rows=sync_rows.collections["ops_metrics"],
        model=OperationalMetric,
        writer=postgres_store.write_operational_metric,
    )
    await _sync_collection(
        summary,
        collection="source_health",
        rows=_rows_with_uuid_remaps(
            sync_rows.collections["source_health"],
            field_maps={"last_error_id": ingestion_error_ids},
        ),
        model=SourceHealth,
        writer=postgres_store.write_source_health,
    )
    return summary


def collect_local_evidence_sync_rows(
    *,
    local_store: FileEvidenceStore,
    configs: list[SourceConfig],
) -> LocalEvidenceSyncRows:
    source_ids = sorted({config.source_id for config in configs})
    raw_document_rows = _rows_for_sources(local_store, "raw_documents", source_ids)
    raw_document_ids = _ids(raw_document_rows)

    document_chunk_rows = _rows_by_field(
        local_store,
        "document_chunks",
        "raw_document_id",
        raw_document_ids,
    )
    extraction_run_rows = _rows_by_field(
        local_store,
        "extraction_runs",
        "raw_document_id",
        raw_document_ids,
    )
    extraction_run_ids = _ids(extraction_run_rows)
    evidence_span_rows = _evidence_rows_for_source(
        local_store=local_store,
        source_ids=source_ids,
        raw_document_ids=raw_document_ids,
    )
    evidence_span_ids = _ids(evidence_span_rows)

    entity_mention_rows = _entity_mentions_for_source(
        local_store=local_store,
        raw_document_ids=raw_document_ids,
        evidence_span_ids=evidence_span_ids,
    )
    entity_alias_rows = _entity_aliases_for_source(
        local_store=local_store,
        source_ids=source_ids,
        evidence_span_ids=evidence_span_ids,
        canonical_entity_ids=_field_values(entity_mention_rows, "canonical_entity_id"),
    )
    canonical_entity_ids = _field_values(
        entity_mention_rows,
        "canonical_entity_id",
    ) | _field_values(entity_alias_rows, "canonical_entity_id")
    canonical_entity_rows = _rows_by_field(
        local_store,
        "canonical_entities",
        "id",
        canonical_entity_ids,
    )

    graph_node_rows = _graph_nodes_for_source(
        local_store=local_store,
        raw_document_ids=raw_document_ids,
        evidence_span_ids=evidence_span_ids,
        extraction_run_ids=extraction_run_ids,
    )
    graph_node_keys = {
        str(row["graph_node_key"]) for row in graph_node_rows if row.get("graph_node_key")
    }
    graph_relationship_rows = _graph_relationships_for_source(
        local_store=local_store,
        raw_document_ids=raw_document_ids,
        evidence_span_ids=evidence_span_ids,
        extraction_run_ids=extraction_run_ids,
        graph_node_keys=graph_node_keys,
    )

    risk_rows = _risk_rows_for_source(
        local_store=local_store,
        evidence_span_ids=evidence_span_ids,
        graph_node_keys=graph_node_keys,
    )
    relevant_target_ids = (
        raw_document_ids
        | _ids(document_chunk_rows)
        | extraction_run_ids
        | evidence_span_ids
        | canonical_entity_ids
        | _ids(risk_rows["risk_cases"])
        | _ids(risk_rows["risk_feature_snapshots"])
        | _ids(risk_rows["risk_verdicts"])
        | _ids(risk_rows["agent_findings"])
        | _ids(risk_rows["risk_alerts"])
    )

    return LocalEvidenceSyncRows(
        configs=configs,
        source_ids=source_ids,
        collections={
            "source_runs": _rows_for_sources(local_store, "source_runs", source_ids),
            "raw_documents": raw_document_rows,
            "document_chunks": document_chunk_rows,
            "extraction_runs": extraction_run_rows,
            "evidence_spans": evidence_span_rows,
            "canonical_entities": canonical_entity_rows,
            "entity_aliases": entity_alias_rows,
            "entity_mentions": entity_mention_rows,
            "source_cursors": _rows_for_sources(local_store, "source_cursors", source_ids),
            "graph_node_upserts": graph_node_rows,
            "graph_relationship_upserts": graph_relationship_rows,
            "risk_candidates": risk_rows["risk_candidates"],
            "risk_cases": risk_rows["risk_cases"],
            "risk_feature_snapshots": risk_rows["risk_feature_snapshots"],
            "risk_verdicts": risk_rows["risk_verdicts"],
            "agent_findings": risk_rows["agent_findings"],
            "risk_alerts": risk_rows["risk_alerts"],
            "ingestion_errors": _rows_for_sources(local_store, "ingestion_errors", source_ids),
            "human_review_queue": _rows_by_field(
                local_store,
                "human_review_queue",
                "target_id",
                relevant_target_ids,
            ),
            "human_feedback": _rows_by_field(
                local_store,
                "human_feedback",
                "target_id",
                relevant_target_ids,
            ),
            "mcp_audit_log": local_store.read_collection("mcp_audit_log"),
            "ops_metrics": _rows_for_sources(local_store, "ops_metrics", source_ids),
            "source_health": _rows_for_sources(local_store, "source_health", source_ids),
        },
    )


async def _sync_collection[ModelT: BaseModel](
    summary: PostgresEvidenceSyncSummary,
    *,
    collection: str,
    rows: list[dict[str, Any]],
    model: type[ModelT],
    writer: Callable[[ModelT], Awaitable[bool]],
) -> None:
    for row in rows:
        inserted = await writer(model.model_validate(row))
        _record(summary, collection, inserted)
    summary.rows_by_collection.setdefault(collection, 0)
    summary.inserted_by_collection.setdefault(collection, 0)


async def _sync_collection_with_id_map[ModelT: BaseModel](
    summary: PostgresEvidenceSyncSummary,
    *,
    collection: str,
    rows: list[dict[str, Any]],
    model: type[ModelT],
    writer: Callable[[ModelT], Awaitable[bool]],
) -> dict[UUID, UUID]:
    id_map: dict[UUID, UUID] = {}
    for row in rows:
        instance = model.model_validate(row)
        original_id = getattr(instance, "id", None)
        inserted = await writer(instance)
        returned_id = getattr(instance, "id", None)
        if isinstance(original_id, UUID) and isinstance(returned_id, UUID):
            id_map[original_id] = returned_id
        _record(summary, collection, inserted)
    summary.rows_by_collection.setdefault(collection, 0)
    summary.inserted_by_collection.setdefault(collection, 0)
    return id_map


def _rows_with_uuid_remaps(
    rows: list[dict[str, Any]],
    *,
    field_maps: dict[str, dict[UUID, UUID]] | None = None,
    list_field_maps: dict[str, dict[UUID, UUID]] | None = None,
    nested_field_maps: dict[str, dict[str, dict[UUID, UUID]]] | None = None,
) -> list[dict[str, Any]]:
    remapped_rows = [copy.deepcopy(row) for row in rows]
    for row in remapped_rows:
        for field, id_map in (field_maps or {}).items():
            row[field] = _remap_uuid_value(row.get(field), id_map)
        for field, id_map in (list_field_maps or {}).items():
            row[field] = _remap_uuid_list(row.get(field), id_map)
        for parent, child_maps in (nested_field_maps or {}).items():
            child = row.get(parent)
            if not isinstance(child, dict):
                continue
            for field, id_map in child_maps.items():
                child[field] = _remap_uuid_value(child.get(field), id_map)
    return remapped_rows


def _rows_with_human_feedback_remaps(
    rows: list[dict[str, Any]],
    *,
    target_id_maps: dict[str, dict[UUID, UUID]],
    human_review_task_ids: dict[UUID, UUID] | None = None,
) -> list[dict[str, Any]]:
    remapped_rows = [copy.deepcopy(row) for row in rows]
    for row in remapped_rows:
        target_table = str(row.get("target_table", ""))
        id_map = target_id_maps.get(target_table)
        if id_map is not None:
            row["target_id"] = _remap_uuid_value(row.get("target_id"), id_map)
        metadata = row.get("metadata")
        if isinstance(metadata, dict) and human_review_task_ids is not None:
            review_task_id = metadata.get("human_review_task_id")
            if review_task_id is not None:
                metadata["human_review_task_id"] = str(
                    _remap_uuid_value(review_task_id, human_review_task_ids)
                )
    return remapped_rows


def _rows_with_human_review_task_remaps(
    rows: list[dict[str, Any]],
    *,
    target_id_maps: dict[str, dict[UUID, UUID]],
    evidence_span_ids: dict[UUID, UUID],
) -> list[dict[str, Any]]:
    remapped_rows = [copy.deepcopy(row) for row in rows]
    for row in remapped_rows:
        target_table = str(row.get("target_table", ""))
        id_map = target_id_maps.get(target_table)
        if id_map is not None:
            row["target_id"] = _remap_uuid_value(row.get("target_id"), id_map)
        row["evidence_span_ids"] = _remap_uuid_list(row.get("evidence_span_ids"), evidence_span_ids)
    return remapped_rows


def _remap_uuid_list(value: object, id_map: dict[UUID, UUID]) -> object:
    if not isinstance(value, list):
        return value
    return [_remap_uuid_value(item, id_map) for item in value]


def _remap_uuid_value(value: object, id_map: dict[UUID, UUID]) -> object:
    if value is None:
        return None
    try:
        parsed = UUID(str(value))
    except ValueError:
        return value
    return str(id_map.get(parsed, parsed))


def _record(summary: PostgresEvidenceSyncSummary, collection: str, inserted: bool) -> None:
    summary.rows_by_collection[collection] = summary.rows_by_collection.get(collection, 0) + 1
    if inserted:
        summary.inserted_by_collection[collection] = (
            summary.inserted_by_collection.get(collection, 0) + 1
        )
    else:
        summary.inserted_by_collection.setdefault(collection, 0)


def _rows_for_sources(
    local_store: FileEvidenceStore,
    collection: str,
    source_ids: list[str],
) -> list[dict[str, Any]]:
    requested = set(source_ids)
    return [
        row
        for row in local_store.read_collection(collection)
        if str(row.get("source_id", "")) in requested
    ]


def _rows_by_field(
    local_store: FileEvidenceStore,
    collection: str,
    field: str,
    values: set[str],
) -> list[dict[str, Any]]:
    if not values:
        return []
    return [row for row in local_store.read_collection(collection) if str(row.get(field)) in values]


def _ids(rows: list[dict[str, Any]]) -> set[str]:
    return _field_values(rows, "id")


def _field_values(rows: list[dict[str, Any]], field: str) -> set[str]:
    return {str(row[field]) for row in rows if row.get(field) is not None}


def _evidence_rows_for_source(
    *,
    local_store: FileEvidenceStore,
    source_ids: list[str],
    raw_document_ids: set[str],
) -> list[dict[str, Any]]:
    requested = set(source_ids)
    return [
        row
        for row in local_store.read_collection("evidence_spans")
        if str(row.get("source_id", "")) in requested
        or str(row.get("raw_document_id", "")) in raw_document_ids
    ]


def _entity_mentions_for_source(
    *,
    local_store: FileEvidenceStore,
    raw_document_ids: set[str],
    evidence_span_ids: set[str],
) -> list[dict[str, Any]]:
    return [
        row
        for row in local_store.read_collection("entity_mentions")
        if str(row.get("raw_document_id", "")) in raw_document_ids
        or str(row.get("evidence_span_id", "")) in evidence_span_ids
    ]


def _entity_aliases_for_source(
    *,
    local_store: FileEvidenceStore,
    source_ids: list[str],
    evidence_span_ids: set[str],
    canonical_entity_ids: set[str],
) -> list[dict[str, Any]]:
    requested = set(source_ids)
    return [
        row
        for row in local_store.read_collection("entity_aliases")
        if str(row.get("source_id", "")) in requested
        or str(row.get("evidence_span_id", "")) in evidence_span_ids
        or str(row.get("canonical_entity_id", "")) in canonical_entity_ids
    ]


def _graph_nodes_for_source(
    *,
    local_store: FileEvidenceStore,
    raw_document_ids: set[str],
    evidence_span_ids: set[str],
    extraction_run_ids: set[str],
) -> list[dict[str, Any]]:
    return [
        row
        for row in local_store.read_collection("graph_node_upserts")
        if str(row.get("source_document_id", "")) in raw_document_ids
        or str(row.get("evidence_span_id", "")) in evidence_span_ids
        or str(row.get("extraction_run_id", "")) in extraction_run_ids
    ]


def _graph_relationships_for_source(
    *,
    local_store: FileEvidenceStore,
    raw_document_ids: set[str],
    evidence_span_ids: set[str],
    extraction_run_ids: set[str],
    graph_node_keys: set[str],
) -> list[dict[str, Any]]:
    return [
        row
        for row in local_store.read_collection("graph_relationship_upserts")
        if _relationship_properties_match_source(
            row,
            raw_document_ids=raw_document_ids,
            evidence_span_ids=evidence_span_ids,
            extraction_run_ids=extraction_run_ids,
        )
        or str(row.get("from_key", "")) in graph_node_keys
        or str(row.get("to_key", "")) in graph_node_keys
    ]


def _relationship_properties_match_source(
    row: dict[str, Any],
    *,
    raw_document_ids: set[str],
    evidence_span_ids: set[str],
    extraction_run_ids: set[str],
) -> bool:
    properties = row.get("properties")
    if not isinstance(properties, dict):
        return False
    return (
        str(properties.get("source_document_id", "")) in raw_document_ids
        or str(properties.get("evidence_span_id", "")) in evidence_span_ids
        or str(properties.get("extraction_run_id", "")) in extraction_run_ids
    )


def _risk_rows_for_source(
    *,
    local_store: FileEvidenceStore,
    evidence_span_ids: set[str],
    graph_node_keys: set[str],
) -> dict[str, list[dict[str, Any]]]:
    risk_candidate_rows = local_store.read_collection("risk_candidates")
    risk_case_rows = local_store.read_collection("risk_cases")
    risk_feature_snapshot_rows = local_store.read_collection("risk_feature_snapshots")
    risk_verdict_rows = local_store.read_collection("risk_verdicts")
    agent_finding_rows = local_store.read_collection("agent_findings")

    risk_case_ids = {
        str(row["id"])
        for row in risk_case_rows
        if row.get("id") is not None and str(row.get("graph_node_key", "")) in graph_node_keys
    }
    for rows in [risk_feature_snapshot_rows, risk_verdict_rows, agent_finding_rows]:
        risk_case_ids |= {
            str(row["risk_case_id"])
            for row in rows
            if row.get("risk_case_id") is not None
            and _row_evidence_overlaps(row, evidence_span_ids)
        }

    filtered_risk_cases = [row for row in risk_case_rows if str(row.get("id", "")) in risk_case_ids]
    risk_case_ids |= _ids(filtered_risk_cases)
    filtered_features = [
        row
        for row in risk_feature_snapshot_rows
        if str(row.get("risk_case_id", "")) in risk_case_ids
        or _row_evidence_overlaps(row, evidence_span_ids)
    ]
    filtered_verdicts = [
        row
        for row in risk_verdict_rows
        if str(row.get("risk_case_id", "")) in risk_case_ids
        or _row_evidence_overlaps(row, evidence_span_ids)
    ]
    filtered_findings = [
        row
        for row in agent_finding_rows
        if str(row.get("risk_case_id", "")) in risk_case_ids
        or _row_evidence_overlaps(row, evidence_span_ids)
    ]
    risk_case_ids |= _field_values(filtered_features, "risk_case_id")
    risk_case_ids |= _field_values(filtered_verdicts, "risk_case_id")
    risk_case_ids |= _field_values(filtered_findings, "risk_case_id")

    return {
        "risk_candidates": [
            row
            for row in risk_candidate_rows
            if _risk_candidate_matches_source(
                row,
                evidence_span_ids=evidence_span_ids,
                graph_node_keys=graph_node_keys,
            )
        ],
        "risk_cases": [row for row in risk_case_rows if str(row.get("id", "")) in risk_case_ids],
        "risk_feature_snapshots": filtered_features,
        "risk_verdicts": filtered_verdicts,
        "agent_findings": filtered_findings,
        "risk_alerts": _rows_by_field(local_store, "risk_alerts", "risk_case_id", risk_case_ids),
    }


def _risk_candidate_matches_source(
    row: dict[str, Any],
    *,
    evidence_span_ids: set[str],
    graph_node_keys: set[str],
) -> bool:
    scope = row.get("scope")
    if isinstance(scope, dict) and str(scope.get("graph_key", "")) in graph_node_keys:
        return True
    return _row_evidence_overlaps(row, evidence_span_ids)


def _row_evidence_overlaps(row: dict[str, Any], evidence_span_ids: set[str]) -> bool:
    values = row.get("evidence_span_ids")
    if not isinstance(values, list):
        return False
    return any(str(value) in evidence_span_ids for value in values)
