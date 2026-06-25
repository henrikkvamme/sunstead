from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel

from supply_intel.db.postgres import PostgresConnection
from supply_intel.entity_resolution.service import (
    CanonicalEntity,
    EntityAlias,
    HumanFeedback,
    HumanReviewTask,
    human_feedback_from_review_task,
)
from supply_intel.models.agents import AgentFinding
from supply_intel.models.documents import DocumentChunk, EvidenceSpan
from supply_intel.models.extraction import EntityMention, ExtractionRun
from supply_intel.models.graph import GraphNodeUpsert, GraphRelationshipUpsert
from supply_intel.models.infra import MCPAuditLog, OperationalMetric
from supply_intel.models.kafka import EventEnvelope
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
    SourceRegistryAudit,
    SourceRun,
)

ModelT = TypeVar("ModelT", bound=BaseModel)
COMPLETED_SOURCE_RUN_STATUSES = {"succeeded", "failed"}


def _json_default(value: object) -> str:
    return str(value)


def _jsonb(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, default=_json_default, sort_keys=True)


def _pgvector(value: Sequence[float] | None) -> str | None:
    if value is None:
        return None
    return "[" + ",".join(format(float(item), ".12g") for item in value) + "]"


class HasMutableId(Protocol):
    id: UUID


def _assign_returned_id(model: HasMutableId, value: object) -> None:
    model.id = value if isinstance(value, UUID) else UUID(str(value))


def _inserted(row: dict[str, Any]) -> bool:
    return bool(row["inserted"])


def _source_run_should_update_health(run: SourceRun, row: dict[str, Any]) -> bool:
    if run.status not in COMPLETED_SOURCE_RUN_STATUSES:
        return False
    return _inserted(row) or row.get("previous_status") != run.status


def source_health_from_run(run: SourceRun, current: SourceHealth | None = None) -> SourceHealth:
    finished_at = run.finished_at or datetime.now(UTC)
    metrics: dict[str, object] = {
        "documents_seen": run.documents_seen,
        "documents_created": run.documents_created,
        "documents_unchanged": run.documents_unchanged,
        "error_count": run.error_count,
        "run_type": run.run_type,
        "source_run_id": str(run.id),
    }
    if run.status == "succeeded":
        return SourceHealth(
            source_id=run.source_id,
            status="healthy",
            last_success_at=finished_at,
            last_failure_at=current.last_failure_at if current else None,
            consecutive_failures=0,
            freshness_lag_seconds=0,
            metrics=metrics,
        )
    consecutive_failures = (current.consecutive_failures if current else 0) + 1
    return SourceHealth(
        source_id=run.source_id,
        status="failing",
        last_success_at=current.last_success_at if current else None,
        last_failure_at=finished_at,
        consecutive_failures=consecutive_failures,
        freshness_lag_seconds=current.freshness_lag_seconds if current else None,
        metrics=metrics,
    )


class FileEvidenceStore:
    """Small local evidence store used before PostgreSQL is bootstrapped."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, collection: str, model: BaseModel) -> None:
        path = self.root / f"{collection}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(model.model_dump(mode="json"), default=_json_default) + "\n")

    def replace_collection(self, collection: str, rows: Sequence[BaseModel]) -> None:
        path = self.root / f"{collection}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row.model_dump(mode="json"), default=_json_default) + "\n")

    def read_collection(self, collection: str) -> list[dict[str, Any]]:
        path = self.root / f"{collection}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def raw_document_exists(self, source_id: str, dedupe_key: str, content_hash: str) -> bool:
        for row in self.read_collection("raw_documents"):
            if (
                row["source_id"] == source_id
                and row["dedupe_key"] == dedupe_key
                and row["content_hash"] == content_hash
            ):
                return True
        return False

    def write_source_run(self, run: SourceRun) -> None:
        self.append("source_runs", run)
        if run.status in COMPLETED_SOURCE_RUN_STATUSES:
            self.write_source_health(
                source_health_from_run(run, self.current_source_health(run.source_id))
            )

    def current_source_health(self, source_id: str) -> SourceHealth | None:
        for row in reversed(self.read_collection("source_health")):
            if row["source_id"] == source_id:
                return SourceHealth.model_validate(row)
        return None

    def write_source_health(self, health: SourceHealth) -> bool:
        existing = self.current_source_health(health.source_id)
        rows = [
            SourceHealth.model_validate(row)
            for row in self.read_collection("source_health")
            if row["source_id"] != health.source_id
        ]
        rows.append(health)
        self.replace_collection("source_health", rows)
        return existing is None

    def upsert_registered_source(
        self,
        config: SourceConfig,
    ) -> Literal["created", "updated", "unchanged"]:
        result: Literal["created", "updated", "unchanged"] = "created"
        registered: list[SourceConfig] = []
        for row in self.read_collection("registered_sources"):
            existing = SourceConfig.model_validate(row)
            if existing.source_id != config.source_id:
                registered.append(existing)
                continue
            result = "unchanged" if existing == config else "updated"
        registered.append(config)
        self.replace_collection("registered_sources", registered)
        return result

    def write_source_registry_audit(self, record: SourceRegistryAudit) -> bool:
        self.append("source_registry_audit", record)
        return True

    def current_source_cursor(
        self,
        source_id: str,
        cursor_name: str = "default",
    ) -> SourceCursor | None:
        for row in reversed(self.read_collection("source_cursors")):
            if row["source_id"] == source_id and row["cursor_name"] == cursor_name:
                return SourceCursor.model_validate(row)
        return None

    def write_source_cursor(self, cursor: SourceCursor) -> bool:
        existing = self.current_source_cursor(cursor.source_id, cursor.cursor_name)
        rows = [
            SourceCursor.model_validate(row)
            for row in self.read_collection("source_cursors")
            if row["source_id"] != cursor.source_id or row["cursor_name"] != cursor.cursor_name
        ]
        rows.append(cursor)
        self.replace_collection("source_cursors", rows)
        return existing is None

    def write_raw_document(self, document: RawDocument) -> bool:
        if self.raw_document_exists(document.source_id, document.dedupe_key, document.content_hash):
            return False
        self.append("raw_documents", document)
        return True

    def write_chunk(self, chunk: DocumentChunk) -> None:
        self.append("document_chunks", chunk)

    def write_evidence_span(self, span: EvidenceSpan) -> bool:
        for row in self.read_collection("evidence_spans"):
            if row["raw_document_id"] == str(span.raw_document_id) and row["hash"] == span.hash:
                _assign_returned_id(span, row["id"])
                return False
        self.append("evidence_spans", span)
        return True

    def write_extraction_run(self, run: ExtractionRun) -> bool:
        for row in self.read_collection("extraction_runs"):
            if (
                row["agent_name"] == run.agent_name
                and row["agent_version"] == run.agent_version
                and row["input_hash"] == run.input_hash
                and row["prompt_hash"] == run.prompt_hash
                and row["output_schema_version"] == run.output_schema_version
            ):
                _assign_returned_id(run, row["id"])
                return False
        self.append("extraction_runs", run)
        return True

    def find_extraction_run(
        self,
        *,
        agent_name: str,
        agent_version: str,
        input_hash: str,
        prompt_hash: str,
        output_schema_version: int,
    ) -> ExtractionRun | None:
        for row in self.read_collection("extraction_runs"):
            if (
                row["agent_name"] == agent_name
                and row["agent_version"] == agent_version
                and row["input_hash"] == input_hash
                and row["prompt_hash"] == prompt_hash
                and row["output_schema_version"] == output_schema_version
            ):
                return ExtractionRun.model_validate(row)
        return None

    def write_ingestion_error(self, error: IngestionError) -> bool:
        for row in self.read_collection("ingestion_errors"):
            if (
                row["source_id"] == error.source_id
                and row.get("source_run_id")
                == (str(error.source_run_id) if error.source_run_id else None)
                and row.get("raw_document_id")
                == (str(error.raw_document_id) if error.raw_document_id else None)
                and row["stage"] == error.stage
                and row["error_type"] == error.error_type
                and row["message"] == error.message
            ):
                _assign_returned_id(error, row["id"])
                return False
        self.append("ingestion_errors", error)
        return True

    def write_canonical_entity(self, entity: CanonicalEntity) -> bool:
        for row in self.read_collection("canonical_entities"):
            if (
                row["entity_type"] == entity.entity_type
                and row["canonical_key"] == entity.canonical_key
            ):
                return False
        self.append("canonical_entities", entity)
        return True

    def write_entity_alias(self, alias: EntityAlias) -> bool:
        for row in self.read_collection("entity_aliases"):
            if (
                row["canonical_entity_id"] == str(alias.canonical_entity_id)
                and row["normalized_alias"] == alias.normalized_alias
                and row["alias_type"] == alias.alias_type
            ):
                return False
        self.append("entity_aliases", alias)
        return True

    def write_entity_mention(self, mention: EntityMention) -> bool:
        for row in self.read_collection("entity_mentions"):
            if (
                row["raw_document_id"] == str(mention.raw_document_id)
                and row["document_chunk_id"] == str(mention.document_chunk_id)
                and row["evidence_span_id"] == str(mention.evidence_span_id)
                and row["entity_type"] == mention.entity_type
                and row["normalized_mention"] == mention.normalized_mention
            ):
                return False
        self.append("entity_mentions", mention)
        return True

    def write_human_review_task(self, task: HumanReviewTask) -> bool:
        for row in self.read_collection("human_review_queue"):
            if row["target_table"] == task.target_table and row["target_id"] == str(task.target_id):
                return False
        self.append("human_review_queue", task)
        self.write_human_feedback(human_feedback_from_review_task(task))
        return True

    def write_human_feedback(self, feedback: HumanFeedback) -> bool:
        for row in self.read_collection("human_feedback"):
            if (
                row["target_table"] == feedback.target_table
                and row["target_id"] == str(feedback.target_id)
                and row["feedback_type"] == feedback.feedback_type
                and row["decision"] == feedback.decision
            ):
                _assign_returned_id(feedback, row["id"])
                return False
        self.append("human_feedback", feedback)
        return True

    def resolve_human_review_task(self, task_id: UUID) -> HumanReviewTask | None:
        tasks = [
            HumanReviewTask.model_validate(row)
            for row in self.read_collection("human_review_queue")
        ]
        resolved: HumanReviewTask | None = None
        for index, task in enumerate(tasks):
            if task.id == task_id:
                resolved = task.model_copy(
                    update={
                        "status": "resolved",
                        "updated_at": datetime.now(UTC),
                    }
                )
                tasks[index] = resolved
                break
        if resolved is None:
            return None
        self.replace_collection("human_review_queue", tasks)
        return resolved

    def write_agent_finding(self, finding: AgentFinding) -> bool:
        for row in self.read_collection("agent_findings"):
            if (
                row["risk_case_id"] == str(finding.risk_case_id)
                and row["agent_name"] == finding.agent_name
                and row["finding_type"] == finding.finding_type
            ):
                _assign_returned_id(finding, row["id"])
                return False
        self.append("agent_findings", finding)
        return True

    def write_graph_node(self, upsert: GraphNodeUpsert) -> bool:
        for row in self.read_collection("graph_node_upserts"):
            if (
                row["graph_node_key"] == upsert.graph_node_key
                and row.get("source_document_id")
                == (str(upsert.source_document_id) if upsert.source_document_id else None)
                and row.get("evidence_span_id")
                == (str(upsert.evidence_span_id) if upsert.evidence_span_id else None)
                and row.get("extraction_run_id")
                == (str(upsert.extraction_run_id) if upsert.extraction_run_id else None)
            ):
                return False
        self.append("graph_node_upserts", upsert)
        return True

    def write_graph_relationship(self, upsert: GraphRelationshipUpsert) -> bool:
        for row in self.read_collection("graph_relationship_upserts"):
            properties = row.get("properties", {})
            if not isinstance(properties, dict):
                properties = {}
            if (
                row["relationship_key"] == upsert.relationship_key
                and properties.get("evidence_span_id")
                == (
                    str(upsert.properties.evidence_span_id)
                    if upsert.properties.evidence_span_id
                    else None
                )
                and properties.get("extraction_run_id")
                == (
                    str(upsert.properties.extraction_run_id)
                    if upsert.properties.extraction_run_id
                    else None
                )
            ):
                return False
        self.append("graph_relationship_upserts", upsert)
        return True

    def write_risk_candidate(self, candidate: RiskCandidate) -> bool:
        for row in self.read_collection("risk_candidates"):
            if row["candidate_key"] == candidate.candidate_key:
                _assign_returned_id(candidate, row["id"])
                return False
        self.append("risk_candidates", candidate)
        return True

    def write_risk_case(self, risk_case: RiskCase) -> bool:
        for row in self.read_collection("risk_cases"):
            if row["case_key"] == risk_case.case_key:
                _assign_returned_id(risk_case, row["id"])
                return False
        self.append("risk_cases", risk_case)
        return True

    def write_risk_feature_snapshot(self, snapshot: RiskFeatureSnapshot) -> bool:
        for row in self.read_collection("risk_feature_snapshots"):
            if (
                row["risk_case_id"] == str(snapshot.risk_case_id)
                and row["feature_name"] == snapshot.feature_name
                and row["feature_version"] == snapshot.feature_version
                and row["window"] == snapshot.window
            ):
                _assign_returned_id(snapshot, row["id"])
                return False
        self.append("risk_feature_snapshots", snapshot)
        return True

    def write_risk_verdict(self, verdict: RiskVerdict) -> bool:
        verdict_key = verdict.metadata.get("verdict_key")
        for row in self.read_collection("risk_verdicts"):
            metadata = row.get("metadata", {})
            if (
                verdict_key is not None
                and isinstance(metadata, dict)
                and metadata.get("verdict_key") == verdict_key
            ):
                _assign_returned_id(verdict, row["id"])
                return False
            if verdict_key is None and (
                row["risk_case_id"] == str(verdict.risk_case_id)
                and row["verdict_type"] == verdict.verdict_type
            ):
                _assign_returned_id(verdict, row["id"])
                return False
        self.append("risk_verdicts", verdict)
        return True

    def write_risk_alert(self, alert: RiskAlert) -> bool:
        alerts = [RiskAlert.model_validate(row) for row in self.read_collection("risk_alerts")]
        for index, existing in enumerate(alerts):
            if existing.alert_key == alert.alert_key:
                alert.id = existing.id
                alert.first_emitted_at = existing.first_emitted_at
                alert.created_at = existing.created_at
                alerts[index] = alert
                self.replace_collection("risk_alerts", alerts)
                return False
        self.append("risk_alerts", alert)
        return True

    def write_event(self, event: EventEnvelope) -> bool:
        for row in self.read_collection("events"):
            if row["idempotency_key"] == event.idempotency_key:
                event.event_id = UUID(str(row["event_id"]))
                return False
        self.append("events", event)
        return True

    def write_mcp_audit_log(self, record: MCPAuditLog) -> bool:
        self.append("mcp_audit_log", record)
        return True

    def write_operational_metric(self, metric: OperationalMetric) -> bool:
        for row in self.read_collection("ops_metrics"):
            if row["idempotency_key"] == metric.idempotency_key:
                _assign_returned_id(metric, row["id"])
                return False
        self.append("ops_metrics", metric)
        return True


class PostgresEvidenceStore:
    """Durable evidence repository backed by the PostgreSQL evidence schema."""

    def __init__(self, connection: PostgresConnection) -> None:
        self.connection = connection

    async def register_source(self, config: SourceConfig) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO data_sources (
              source_id, name, source_type, adapter_type, base_url, config,
              parser_profile, priority, cadence_seconds, enabled, auth_ref,
              rate_limit, robots_policy, license_notes, compliance_notes,
              schema_version, metadata, updated_at
            )
            VALUES (
              $1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11,
              $12::jsonb, $13::jsonb, $14, $15, $16, $17::jsonb, $18
            )
            ON CONFLICT (source_id) DO UPDATE SET
              name = EXCLUDED.name,
              source_type = EXCLUDED.source_type,
              adapter_type = EXCLUDED.adapter_type,
              base_url = EXCLUDED.base_url,
              config = EXCLUDED.config,
              parser_profile = EXCLUDED.parser_profile,
              priority = EXCLUDED.priority,
              cadence_seconds = EXCLUDED.cadence_seconds,
              enabled = EXCLUDED.enabled,
              auth_ref = EXCLUDED.auth_ref,
              rate_limit = EXCLUDED.rate_limit,
              robots_policy = EXCLUDED.robots_policy,
              license_notes = EXCLUDED.license_notes,
              compliance_notes = EXCLUDED.compliance_notes,
              schema_version = EXCLUDED.schema_version,
              metadata = EXCLUDED.metadata,
              updated_at = EXCLUDED.updated_at
            RETURNING id, (xmax = 0) AS inserted
            """,
            config.source_id,
            config.name,
            config.source_type,
            config.adapter,
            config.base_url,
            _jsonb(config),
            config.parser.profile,
            config.priority,
            config.cadence_seconds,
            config.enabled,
            config.auth.env,
            _jsonb(config.rate_limit),
            _jsonb(
                {
                    "robots": config.compliance.robots,
                    "pii_expected": config.compliance.pii_expected,
                    "data_minimization": config.compliance.data_minimization,
                }
            ),
            config.compliance.license_notes,
            config.compliance.retention_notes,
            config.schema_version,
            _jsonb({}),
            datetime.now(UTC),
        )
        if row is None:
            raise RuntimeError(f"Source registration returned no row for {config.source_id}")
        return _inserted(row)

    async def write_source_run(self, run: SourceRun) -> bool:
        row = await self.connection.fetchrow(
            """
            WITH existing AS (
              SELECT status AS previous_status
              FROM source_runs
              WHERE source_id = $2 AND idempotency_key = $14
            ),
            upserted AS (
              INSERT INTO source_runs (
                id, source_id, run_type, status, started_at, finished_at,
                cursor_before, cursor_after, documents_seen, documents_created,
                documents_unchanged, error_count, correlation_id, idempotency_key,
                schema_version, metadata, created_at, updated_at
              )
              VALUES (
                $1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10,
                $11, $12, $13, $14, $15, $16::jsonb, $17, $18
              )
              ON CONFLICT (source_id, idempotency_key) DO UPDATE SET
                status = EXCLUDED.status,
                finished_at = EXCLUDED.finished_at,
                cursor_after = EXCLUDED.cursor_after,
                documents_seen = EXCLUDED.documents_seen,
                documents_created = EXCLUDED.documents_created,
                documents_unchanged = EXCLUDED.documents_unchanged,
                error_count = EXCLUDED.error_count,
                metadata = EXCLUDED.metadata,
                updated_at = EXCLUDED.updated_at
              RETURNING id, (xmax = 0) AS inserted
            )
            SELECT upserted.id, upserted.inserted, existing.previous_status
            FROM upserted
            LEFT JOIN existing ON true
            """,
            run.id,
            run.source_id,
            run.run_type,
            run.status,
            run.started_at,
            run.finished_at,
            _jsonb(run.cursor_before),
            _jsonb(run.cursor_after),
            run.documents_seen,
            run.documents_created,
            run.documents_unchanged,
            run.error_count,
            run.correlation_id,
            run.idempotency_key,
            run.schema_version,
            _jsonb(run.metadata),
            run.created_at,
            run.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Source run write returned no row for {run.idempotency_key}")
        _assign_returned_id(run, row["id"])
        if _source_run_should_update_health(run, row):
            await self.write_source_health(source_health_from_run(run))
        return _inserted(row)

    async def write_source_health(self, health: SourceHealth) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO source_health (
              id, source_id, status, last_success_at, last_failure_at,
              consecutive_failures, freshness_lag_seconds, last_error_id,
              metrics, schema_version, metadata, created_at, updated_at
            )
            VALUES (
              $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10,
              $11::jsonb, $12, $13
            )
            ON CONFLICT (source_id) DO UPDATE SET
              status = EXCLUDED.status,
              last_success_at = COALESCE(EXCLUDED.last_success_at, source_health.last_success_at),
              last_failure_at = COALESCE(EXCLUDED.last_failure_at, source_health.last_failure_at),
              consecutive_failures = CASE
                WHEN EXCLUDED.status = 'failing' THEN source_health.consecutive_failures + 1
                ELSE 0
              END,
              freshness_lag_seconds = EXCLUDED.freshness_lag_seconds,
              last_error_id = COALESCE(EXCLUDED.last_error_id, source_health.last_error_id),
              metrics = EXCLUDED.metrics,
              metadata = EXCLUDED.metadata,
              updated_at = EXCLUDED.updated_at
            RETURNING id, (xmax = 0) AS inserted
            """,
            health.id,
            health.source_id,
            health.status,
            health.last_success_at,
            health.last_failure_at,
            health.consecutive_failures,
            health.freshness_lag_seconds,
            health.last_error_id,
            _jsonb(health.metrics),
            health.schema_version,
            _jsonb(health.metadata),
            health.created_at,
            health.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Source health write returned no row for {health.source_id}")
        _assign_returned_id(health, row["id"])
        return _inserted(row)

    async def current_source_cursor(
        self,
        source_id: str,
        cursor_name: str = "default",
    ) -> SourceCursor | None:
        row = await self.connection.fetchrow(
            """
            SELECT id, source_id, cursor_name, cursor_state, watermark, etag,
              last_content_hash, updated_by_run_id, schema_version, metadata,
              created_at, updated_at
            FROM source_cursors
            WHERE source_id = $1 AND cursor_name = $2
            """,
            source_id,
            cursor_name,
        )
        if row is None:
            return None
        return SourceCursor.model_validate(dict(row))

    async def write_source_cursor(self, cursor: SourceCursor) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO source_cursors (
              id, source_id, cursor_name, cursor_state, watermark, etag,
              last_content_hash, updated_by_run_id, schema_version, metadata,
              created_at, updated_at
            )
            VALUES (
              $1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10::jsonb,
              $11, $12
            )
            ON CONFLICT (source_id, cursor_name) DO UPDATE SET
              cursor_state = EXCLUDED.cursor_state,
              watermark = EXCLUDED.watermark,
              etag = EXCLUDED.etag,
              last_content_hash = EXCLUDED.last_content_hash,
              updated_by_run_id = EXCLUDED.updated_by_run_id,
              schema_version = EXCLUDED.schema_version,
              metadata = EXCLUDED.metadata,
              updated_at = EXCLUDED.updated_at
            RETURNING id, (xmax = 0) AS inserted
            """,
            cursor.id,
            cursor.source_id,
            cursor.cursor_name,
            _jsonb(cursor.cursor_state),
            cursor.watermark,
            cursor.etag,
            cursor.last_content_hash,
            cursor.updated_by_run_id,
            cursor.schema_version,
            _jsonb(cursor.metadata),
            cursor.created_at,
            cursor.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Source cursor write returned no row for {cursor.source_id}")
        _assign_returned_id(cursor, row["id"])
        return _inserted(row)

    async def write_raw_document(self, document: RawDocument) -> bool:
        row = await self.connection.fetchrow(
            """
            WITH inserted AS (
              INSERT INTO raw_documents (
                id, source_id, source_run_id, source_url, canonical_url, request,
                response_headers, http_status, content_type, content_length,
                content_hash, payload_storage, payload_bytes, payload_text, payload_uri,
                source_published_at, source_updated_at, fetched_at, dedupe_key,
                raw_metadata, schema_version, metadata, created_at, updated_at
              )
              VALUES (
                $1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20::jsonb,
                $21, $22::jsonb, $23, $24
              )
              ON CONFLICT (source_id, dedupe_key, content_hash) DO NOTHING
              RETURNING id, true AS inserted
            )
            SELECT id, inserted FROM inserted
            UNION ALL
            SELECT id, false AS inserted
            FROM raw_documents
            WHERE source_id = $2 AND dedupe_key = $19 AND content_hash = $11
              AND NOT EXISTS (SELECT 1 FROM inserted)
            LIMIT 1
            """,
            document.id,
            document.source_id,
            document.source_run_id,
            document.source_url,
            document.canonical_url,
            _jsonb(document.request),
            _jsonb(document.response_headers),
            document.http_status,
            document.content_type,
            document.content_length,
            document.content_hash,
            document.payload_storage,
            document.payload_bytes,
            document.payload_text,
            document.payload_uri,
            document.source_published_at,
            document.source_updated_at,
            document.fetched_at,
            document.dedupe_key,
            _jsonb(document.raw_metadata),
            document.schema_version,
            _jsonb(document.metadata),
            document.created_at,
            document.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Raw document write returned no row for {document.dedupe_key}")
        _assign_returned_id(document, row["id"])
        return _inserted(row)

    async def write_chunk(self, chunk: DocumentChunk) -> bool:
        row = await self.connection.fetchrow(
            """
            WITH inserted AS (
              INSERT INTO document_chunks (
                id, raw_document_id, chunk_index, chunk_type, title, text,
                structured_data, char_start, char_end, page_number, section_path,
                embedding, embedding_model, content_hash, schema_version, metadata,
                created_at, updated_at
              )
              VALUES (
                $1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11,
                $12::vector, $13, $14, $15, $16::jsonb, $17, $18
              )
              ON CONFLICT (raw_document_id, chunk_index, content_hash) DO NOTHING
              RETURNING id, true AS inserted
            )
            SELECT id, inserted FROM inserted
            UNION ALL
            SELECT id, false AS inserted
            FROM document_chunks
            WHERE raw_document_id = $2 AND chunk_index = $3 AND content_hash = $14
              AND NOT EXISTS (SELECT 1 FROM inserted)
            LIMIT 1
            """,
            chunk.id,
            chunk.raw_document_id,
            chunk.chunk_index,
            chunk.chunk_type,
            chunk.title,
            chunk.text,
            _jsonb(chunk.structured_data),
            chunk.char_start,
            chunk.char_end,
            chunk.page_number,
            chunk.section_path,
            _pgvector(chunk.embedding),
            chunk.embedding_model,
            chunk.content_hash,
            chunk.schema_version,
            _jsonb(chunk.metadata),
            chunk.created_at,
            chunk.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Document chunk write returned no row for {chunk.content_hash}")
        _assign_returned_id(chunk, row["id"])
        return _inserted(row)

    async def write_evidence_span(self, span: EvidenceSpan) -> bool:
        row = await self.connection.fetchrow(
            """
            WITH inserted AS (
              INSERT INTO evidence_spans (
                id, raw_document_id, document_chunk_id, extraction_run_id,
                source_id, source_url, quote, normalized_text, char_start, char_end,
                page_number, table_ref, confidence, evidence_type, hash,
                schema_version, metadata, created_at, updated_at
              )
              VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb,
                $13, $14, $15, $16, $17::jsonb, $18, $19
              )
              ON CONFLICT (raw_document_id, hash) DO NOTHING
              RETURNING id, true AS inserted
            )
            SELECT id, inserted FROM inserted
            UNION ALL
            SELECT id, false AS inserted
            FROM evidence_spans
            WHERE raw_document_id = $2 AND hash = $15
              AND NOT EXISTS (SELECT 1 FROM inserted)
            LIMIT 1
            """,
            span.id,
            span.raw_document_id,
            span.document_chunk_id,
            span.extraction_run_id,
            span.source_id,
            span.source_url,
            span.quote,
            span.normalized_text,
            span.char_start,
            span.char_end,
            span.page_number,
            _jsonb(span.table_ref),
            span.confidence,
            span.evidence_type,
            span.hash,
            span.schema_version,
            _jsonb(span.metadata),
            span.created_at,
            span.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Evidence span write returned no row for {span.hash}")
        _assign_returned_id(span, row["id"])
        return _inserted(row)

    async def write_extraction_run(self, run: ExtractionRun) -> bool:
        row = await self.connection.fetchrow(
            """
            WITH inserted AS (
              INSERT INTO extraction_runs (
                id, raw_document_id, document_chunk_id, agent_name, agent_version,
                model_name, prompt_hash, input_hash, output_schema,
                output_schema_version, status, started_at, finished_at, usage,
                raw_output, validated_output, error, correlation_id,
                idempotency_key, schema_version, metadata, created_at, updated_at
              )
              VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                $14::jsonb, $15::jsonb, $16::jsonb, $17, $18, $19, $20,
                $21::jsonb, $22, $23
              )
              ON CONFLICT (
                agent_name, agent_version, input_hash, prompt_hash, output_schema_version
              ) DO NOTHING
              RETURNING id, true AS inserted
            )
            SELECT id, inserted FROM inserted
            UNION ALL
            SELECT id, false AS inserted
            FROM extraction_runs
            WHERE agent_name = $4 AND agent_version = $5 AND input_hash = $8
              AND prompt_hash = $7 AND output_schema_version = $10
              AND NOT EXISTS (SELECT 1 FROM inserted)
            LIMIT 1
            """,
            run.id,
            run.raw_document_id,
            run.document_chunk_id,
            run.agent_name,
            run.agent_version,
            run.model_name,
            run.prompt_hash,
            run.input_hash,
            run.output_schema,
            run.output_schema_version,
            run.status,
            run.started_at,
            run.finished_at,
            _jsonb(run.usage),
            _jsonb(run.raw_output),
            _jsonb(run.validated_output),
            run.error,
            run.correlation_id,
            run.idempotency_key,
            run.schema_version,
            _jsonb(run.metadata),
            run.created_at,
            run.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Extraction run write returned no row for {run.input_hash}")
        _assign_returned_id(run, row["id"])
        return _inserted(row)

    async def write_ingestion_error(self, error: IngestionError) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO ingestion_errors (
              id, source_id, source_run_id, raw_document_id, stage, error_type,
              message, details, retryable, occurred_at, schema_version, metadata,
              created_at, updated_at
            )
            VALUES (
              $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10, $11,
              $12::jsonb, $13, $14
            )
            RETURNING id, true AS inserted
            """,
            error.id,
            error.source_id,
            error.source_run_id,
            error.raw_document_id,
            error.stage,
            error.error_type,
            error.message,
            _jsonb(error.details),
            error.retryable,
            error.occurred_at,
            error.schema_version,
            _jsonb(error.metadata),
            error.created_at,
            error.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Ingestion error write returned no row for {error.source_id}")
        _assign_returned_id(error, row["id"])
        return _inserted(row)

    async def write_canonical_entity(self, entity: CanonicalEntity) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO canonical_entities (
              id, entity_type, canonical_key, display_name, normalized_name,
              external_ids, attributes, confidence, status, needs_review,
              review_reason, schema_version, metadata, created_at, updated_at
            )
            VALUES (
              $1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, $10,
              $11, $12, $13::jsonb, $14, $15
            )
            ON CONFLICT (entity_type, canonical_key) DO UPDATE SET
              display_name = EXCLUDED.display_name,
              normalized_name = EXCLUDED.normalized_name,
              external_ids = EXCLUDED.external_ids,
              attributes = EXCLUDED.attributes,
              confidence = EXCLUDED.confidence,
              status = EXCLUDED.status,
              needs_review = canonical_entities.needs_review OR EXCLUDED.needs_review,
              review_reason = COALESCE(EXCLUDED.review_reason, canonical_entities.review_reason),
              metadata = EXCLUDED.metadata,
              updated_at = EXCLUDED.updated_at
            RETURNING id, (xmax = 0) AS inserted
            """,
            entity.id,
            entity.entity_type,
            entity.canonical_key,
            entity.display_name,
            entity.normalized_name,
            _jsonb(entity.external_ids),
            _jsonb(entity.attributes),
            entity.confidence,
            entity.status,
            entity.needs_review,
            entity.review_reason,
            entity.schema_version,
            _jsonb(entity.metadata),
            entity.created_at,
            entity.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Canonical entity write returned no row for {entity.canonical_key}")
        _assign_returned_id(entity, row["id"])
        return _inserted(row)

    async def write_entity_alias(self, alias: EntityAlias) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO entity_aliases (
              id, canonical_entity_id, alias, normalized_alias, alias_type,
              source_id, evidence_span_id, confidence, schema_version, metadata,
              created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, $12)
            ON CONFLICT (canonical_entity_id, normalized_alias, alias_type) DO UPDATE SET
              alias = EXCLUDED.alias,
              source_id = COALESCE(EXCLUDED.source_id, entity_aliases.source_id),
              evidence_span_id = COALESCE(
                EXCLUDED.evidence_span_id,
                entity_aliases.evidence_span_id
              ),
              confidence = GREATEST(entity_aliases.confidence, EXCLUDED.confidence),
              metadata = EXCLUDED.metadata,
              updated_at = EXCLUDED.updated_at
            RETURNING id, (xmax = 0) AS inserted
            """,
            alias.id,
            alias.canonical_entity_id,
            alias.alias,
            alias.normalized_alias,
            alias.alias_type,
            alias.source_id,
            alias.evidence_span_id,
            alias.confidence,
            alias.schema_version,
            _jsonb(alias.metadata),
            alias.created_at,
            alias.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Entity alias write returned no row for {alias.normalized_alias}")
        _assign_returned_id(alias, row["id"])
        return _inserted(row)

    async def write_entity_mention(self, mention: EntityMention) -> bool:
        row = await self.connection.fetchrow(
            """
            WITH existing AS (
              SELECT id
              FROM entity_mentions
              WHERE raw_document_id = $2
                AND document_chunk_id IS NOT DISTINCT FROM $3
                AND evidence_span_id IS NOT DISTINCT FROM $5
                AND entity_type = $6
                AND normalized_mention = $8
            ),
            inserted AS (
              INSERT INTO entity_mentions (
                id, raw_document_id, document_chunk_id, extraction_run_id,
                evidence_span_id, entity_type, mention_text, normalized_mention,
                candidate_external_ids, canonical_entity_id, resolution_status,
                resolution_confidence, resolution_method, needs_review,
                schema_version, metadata, created_at, updated_at
              )
              SELECT
                $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11,
                $12, $13, $14, $15, $16::jsonb, $17, $18
              WHERE NOT EXISTS (SELECT 1 FROM existing)
              RETURNING id, true AS inserted
            )
            SELECT id, inserted FROM inserted
            UNION ALL
            SELECT id, false AS inserted FROM existing
            LIMIT 1
            """,
            mention.id,
            mention.raw_document_id,
            mention.document_chunk_id,
            mention.extraction_run_id,
            mention.evidence_span_id,
            mention.entity_type,
            mention.mention_text,
            mention.normalized_mention,
            _jsonb(mention.candidate_external_ids),
            mention.canonical_entity_id,
            mention.resolution_status,
            mention.resolution_confidence,
            mention.resolution_method,
            mention.needs_review,
            mention.schema_version,
            _jsonb(mention.metadata),
            mention.created_at,
            mention.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Entity mention write returned no row for {mention.mention_text}")
        _assign_returned_id(mention, row["id"])
        return _inserted(row)

    async def write_human_review_task(self, task: HumanReviewTask) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO human_review_queue (
              id, target_table, target_id, review_type, reason, status, priority,
              evidence_span_ids, schema_version, metadata, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, $12)
            ON CONFLICT (target_table, target_id) DO UPDATE SET
              review_type = EXCLUDED.review_type,
              reason = EXCLUDED.reason,
              status = EXCLUDED.status,
              priority = EXCLUDED.priority,
              evidence_span_ids = EXCLUDED.evidence_span_ids,
              metadata = EXCLUDED.metadata,
              updated_at = EXCLUDED.updated_at
            RETURNING id, (xmax = 0) AS inserted
            """,
            task.id,
            task.target_table,
            task.target_id,
            task.review_type,
            task.reason,
            task.status,
            task.priority,
            task.evidence_span_ids,
            task.schema_version,
            _jsonb(task.metadata),
            task.created_at,
            task.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Human review task write returned no row for {task.target_id}")
        _assign_returned_id(task, row["id"])
        return _inserted(row)

    async def read_human_review_tasks(
        self,
        *,
        status: Literal["open", "resolved"] | None = None,
    ) -> list[HumanReviewTask]:
        rows = await self.connection.fetch(
            """
            SELECT
              id, target_table, target_id, review_type, reason, status, priority,
              evidence_span_ids, schema_version, metadata, created_at, updated_at
            FROM human_review_queue
            WHERE ($1::text IS NULL OR status = $1)
            ORDER BY priority, created_at DESC
            """,
            status,
        )
        return [HumanReviewTask.model_validate(dict(row)) for row in rows]

    async def read_human_review_task(self, task_id: UUID) -> HumanReviewTask | None:
        row = await self.connection.fetchrow(
            """
            SELECT
              id, target_table, target_id, review_type, reason, status, priority,
              evidence_span_ids, schema_version, metadata, created_at, updated_at
            FROM human_review_queue
            WHERE id = $1
            """,
            task_id,
        )
        return HumanReviewTask.model_validate(dict(row)) if row is not None else None

    async def resolve_human_review_task(self, task_id: UUID) -> HumanReviewTask | None:
        row = await self.connection.fetchrow(
            """
            UPDATE human_review_queue
            SET status = 'resolved', updated_at = $2
            WHERE id = $1
            RETURNING
              id, target_table, target_id, review_type, reason, status, priority,
              evidence_span_ids, schema_version, metadata, created_at, updated_at
            """,
            task_id,
            datetime.now(UTC),
        )
        return HumanReviewTask.model_validate(dict(row)) if row is not None else None

    async def write_human_feedback(self, feedback: HumanFeedback) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO human_feedback (
              id, target_table, target_id, feedback_type, decision, comment,
              reviewer, before_value, after_value, metadata, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10::jsonb, $11)
            RETURNING id, true AS inserted
            """,
            feedback.id,
            feedback.target_table,
            feedback.target_id,
            feedback.feedback_type,
            feedback.decision,
            feedback.comment,
            feedback.reviewer,
            _jsonb(feedback.before_value),
            _jsonb(feedback.after_value),
            _jsonb(feedback.metadata),
            feedback.created_at,
        )
        if row is None:
            raise RuntimeError(f"Human feedback write returned no row for {feedback.target_id}")
        _assign_returned_id(feedback, row["id"])
        return _inserted(row)

    async def write_agent_finding(self, finding: AgentFinding) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO agent_findings (
              id, risk_case_id, agent_name, agent_version, model_name, prompt_hash,
              input_hash, output_schema, output_schema_version, usage, finding_type,
              finding, evidence_span_ids, confidence, critic_status, status, error,
              correlation_id, schema_version, metadata, created_at, updated_at
            )
            VALUES (
              $1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11,
              $12::jsonb, $13, $14, $15, $16, $17, $18, $19, $20::jsonb,
              $21, $22
            )
            ON CONFLICT (id) DO UPDATE SET
              model_name = EXCLUDED.model_name,
              prompt_hash = EXCLUDED.prompt_hash,
              input_hash = EXCLUDED.input_hash,
              output_schema = EXCLUDED.output_schema,
              output_schema_version = EXCLUDED.output_schema_version,
              usage = EXCLUDED.usage,
              finding = EXCLUDED.finding,
              evidence_span_ids = EXCLUDED.evidence_span_ids,
              confidence = EXCLUDED.confidence,
              critic_status = EXCLUDED.critic_status,
              status = EXCLUDED.status,
              error = EXCLUDED.error,
              metadata = EXCLUDED.metadata,
              updated_at = EXCLUDED.updated_at
            RETURNING id, (xmax = 0) AS inserted
            """,
            finding.id,
            finding.risk_case_id,
            finding.agent_name,
            finding.agent_version,
            finding.model_name,
            finding.prompt_hash,
            finding.input_hash,
            finding.output_schema,
            finding.output_schema_version,
            _jsonb(finding.usage),
            finding.finding_type,
            _jsonb(finding.finding),
            finding.evidence_span_ids,
            finding.confidence,
            finding.critic_status,
            finding.status,
            finding.error,
            finding.correlation_id,
            finding.schema_version,
            _jsonb(finding.metadata),
            finding.created_at,
            finding.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Agent finding write returned no row for {finding.id}")
        _assign_returned_id(finding, row["id"])
        return _inserted(row)

    async def write_graph_node(self, upsert: GraphNodeUpsert) -> bool:
        label_or_type = ":".join(upsert.labels)
        return await self._write_graph_audit(
            upsert_type="node",
            graph_key=upsert.graph_node_key,
            label_or_type=label_or_type,
            payload=upsert,
            cypher_template="MERGE (n {graph_node_key: $graph_node_key}) SET n += $properties",
            idempotency_key=(
                f"graph:node:{upsert.graph_node_key}:"
                f"{upsert.source_document_id}:{upsert.evidence_span_id}:{upsert.extraction_run_id}"
            ),
        )

    async def write_graph_relationship(self, upsert: GraphRelationshipUpsert) -> bool:
        return await self._write_graph_audit(
            upsert_type="relationship",
            graph_key=upsert.relationship_key,
            label_or_type=upsert.relationship_type,
            payload=upsert,
            cypher_template=(
                "MATCH (a {graph_node_key: $from_key}), (b {graph_node_key: $to_key}) "
                "MERGE (a)-[r:$relationship_type {relationship_key: $relationship_key}]->(b) "
                "SET r += $properties"
            ),
            idempotency_key=f"graph:relationship:{upsert.relationship_key}",
        )

    async def _write_graph_audit(
        self,
        *,
        upsert_type: str,
        graph_key: str,
        label_or_type: str,
        payload: BaseModel,
        cypher_template: str,
        idempotency_key: str,
    ) -> bool:
        row = await self.connection.fetchrow(
            """
            WITH inserted AS (
              INSERT INTO graph_upsert_audit (
                upsert_type, graph_key, neo4j_label_or_type, payload,
                cypher_template, status, started_at, idempotency_key
              )
              VALUES ($1, $2, $3, $4::jsonb, $5, 'pending', $6, $7)
              ON CONFLICT (idempotency_key) DO NOTHING
              RETURNING id, true AS inserted
            )
            SELECT id, inserted FROM inserted
            UNION ALL
            SELECT id, false AS inserted
            FROM graph_upsert_audit
            WHERE idempotency_key = $7 AND NOT EXISTS (SELECT 1 FROM inserted)
            LIMIT 1
            """,
            upsert_type,
            graph_key,
            label_or_type,
            _jsonb(payload),
            cypher_template,
            datetime.now(UTC),
            idempotency_key,
        )
        if row is None:
            raise RuntimeError(f"Graph audit write returned no row for {idempotency_key}")
        return _inserted(row)

    async def write_mcp_audit_log(self, record: MCPAuditLog) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO mcp_audit_log (
              id, controller, action, project, service_name, request,
              response_summary, status, destructive, approval_id, actor,
              started_at, finished_at, error, schema_version, metadata,
              created_at, updated_at
            )
            VALUES (
              $1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, $10,
              $11, $12, $13, $14, $15, $16::jsonb, $17, $18
            )
            RETURNING id, true AS inserted
            """,
            record.id,
            record.controller,
            record.action,
            record.project,
            record.service_name,
            _jsonb(record.request),
            _jsonb(record.response_summary),
            record.status,
            record.destructive,
            record.approval_id,
            record.actor,
            record.started_at,
            record.finished_at,
            record.error,
            record.schema_version,
            _jsonb(record.metadata),
            record.created_at,
            record.updated_at,
        )
        if row is None:
            raise RuntimeError(f"MCP audit write returned no row for {record.action}")
        _assign_returned_id(record, row["id"])
        return _inserted(row)

    async def write_operational_metric(self, metric: OperationalMetric) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO ops_metrics (
              id, metric_name, metric_value, unit, service, source_id, topic,
              consumer_group, correlation_id, causation_id, observed_at, tags,
              idempotency_key, schema_version, metadata, created_at, updated_at
            )
            VALUES (
              $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb,
              $13, $14, $15::jsonb, $16, $17
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING id, (xmax = 0) AS inserted
            """,
            metric.id,
            metric.metric_name,
            metric.metric_value,
            metric.unit,
            metric.service,
            metric.source_id,
            metric.topic,
            metric.consumer_group,
            metric.correlation_id,
            metric.causation_id,
            metric.observed_at,
            _jsonb(metric.tags),
            metric.idempotency_key,
            metric.schema_version,
            _jsonb(metric.metadata),
            metric.created_at,
            metric.updated_at,
        )
        if row is None:
            return False
        _assign_returned_id(metric, row["id"])
        return _inserted(row)

    async def write_risk_candidate(self, candidate: RiskCandidate) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO risk_candidates (
              id, candidate_key, risk_type, scope, signals, initial_score,
              confidence, evidence_span_ids, schema_version, metadata,
              created_at, updated_at
            )
            VALUES (
              $1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8::uuid[],
              $9, $10::jsonb, $11, $12
            )
            ON CONFLICT (candidate_key) DO UPDATE SET
              risk_type = EXCLUDED.risk_type,
              scope = EXCLUDED.scope,
              signals = EXCLUDED.signals,
              initial_score = EXCLUDED.initial_score,
              confidence = EXCLUDED.confidence,
              evidence_span_ids = EXCLUDED.evidence_span_ids,
              metadata = EXCLUDED.metadata,
              updated_at = EXCLUDED.updated_at
            RETURNING id, (xmax = 0) AS inserted
            """,
            candidate.id,
            candidate.candidate_key,
            candidate.risk_type,
            _jsonb(candidate.scope),
            _jsonb(candidate.signals),
            candidate.initial_score,
            candidate.confidence,
            candidate.evidence_span_ids,
            candidate.schema_version,
            _jsonb(candidate.metadata),
            candidate.created_at,
            candidate.updated_at,
        )
        if row is None:
            raise RuntimeError(
                f"Risk candidate write returned no row for {candidate.candidate_key}"
            )
        _assign_returned_id(candidate, row["id"])
        return _inserted(row)

    async def write_risk_case(self, risk_case: RiskCase) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO risk_cases (
              id, case_key, title, risk_type, scope_type, scope_entity_id,
              graph_node_key, status, severity, risk_score, confidence,
              component_scores, opened_at, updated_at, closed_at,
              latest_verdict_id, schema_version, metadata, created_at
            )
            VALUES (
              $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb,
              $13, $14, $15, $16, $17, $18::jsonb, $19
            )
            ON CONFLICT (case_key) DO UPDATE SET
              title = EXCLUDED.title,
              status = EXCLUDED.status,
              severity = EXCLUDED.severity,
              risk_score = EXCLUDED.risk_score,
              confidence = EXCLUDED.confidence,
              component_scores = EXCLUDED.component_scores,
              updated_at = EXCLUDED.updated_at,
              closed_at = EXCLUDED.closed_at,
              latest_verdict_id = EXCLUDED.latest_verdict_id,
              metadata = EXCLUDED.metadata
            RETURNING id, (xmax = 0) AS inserted
            """,
            risk_case.id,
            risk_case.case_key,
            risk_case.title,
            risk_case.risk_type,
            risk_case.scope_type,
            risk_case.scope_entity_id,
            risk_case.graph_node_key,
            risk_case.status,
            risk_case.severity,
            risk_case.risk_score,
            risk_case.confidence,
            _jsonb(risk_case.component_scores),
            risk_case.opened_at,
            risk_case.updated_at,
            risk_case.closed_at,
            risk_case.latest_verdict_id,
            risk_case.schema_version,
            _jsonb(risk_case.metadata),
            risk_case.created_at,
        )
        if row is None:
            raise RuntimeError(f"Risk case write returned no row for {risk_case.case_key}")
        _assign_returned_id(risk_case, row["id"])
        return _inserted(row)

    async def write_risk_feature_snapshot(self, snapshot: RiskFeatureSnapshot) -> bool:
        row = await self.connection.fetchrow(
            """
            WITH inserted AS (
              INSERT INTO risk_feature_snapshots (
                id, risk_case_id, case_key, scope_type, scope_entity_id,
                graph_node_key, feature_name, value, "window", evidence_span_ids,
                computed_at, feature_version, schema_version, metadata,
                created_at, updated_at
              )
              VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                $13, $14::jsonb, $15, $16
              )
              ON CONFLICT (risk_case_id, feature_name, feature_version, "window") DO UPDATE SET
                value = EXCLUDED.value,
                evidence_span_ids = EXCLUDED.evidence_span_ids,
                computed_at = EXCLUDED.computed_at,
                metadata = EXCLUDED.metadata,
                updated_at = EXCLUDED.updated_at
              RETURNING id, true AS inserted
            )
            SELECT id, inserted FROM inserted
            UNION ALL
            SELECT id, false AS inserted
            FROM risk_feature_snapshots
            WHERE risk_case_id = $2
              AND feature_name = $7
              AND feature_version = $12
              AND "window" = $9
              AND NOT EXISTS (SELECT 1 FROM inserted)
            LIMIT 1
            """,
            snapshot.id,
            snapshot.risk_case_id,
            snapshot.case_key,
            snapshot.scope_type,
            snapshot.scope_entity_id,
            snapshot.graph_node_key,
            snapshot.feature_name,
            snapshot.value,
            snapshot.window,
            snapshot.evidence_span_ids,
            snapshot.computed_at,
            snapshot.feature_version,
            snapshot.schema_version,
            _jsonb(snapshot.metadata),
            snapshot.created_at,
            snapshot.updated_at,
        )
        if row is None:
            raise RuntimeError(
                f"Risk feature snapshot write returned no row for {snapshot.feature_name}"
            )
        _assign_returned_id(snapshot, row["id"])
        return _inserted(row)

    async def write_risk_verdict(self, verdict: RiskVerdict) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO risk_verdicts (
              id, risk_case_id, verdict_type, severity, risk_score, confidence,
              summary, key_drivers, affected_entities, evidence_span_ids,
              limitations, recommended_actions, next_review_at, schema_version,
              metadata, created_at, updated_at
            )
            VALUES (
              $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10,
              $11::jsonb, $12::jsonb, $13, $14, $15::jsonb, $16, $17
            )
            ON CONFLICT (id) DO UPDATE SET
              verdict_type = EXCLUDED.verdict_type,
              severity = EXCLUDED.severity,
              risk_score = EXCLUDED.risk_score,
              confidence = EXCLUDED.confidence,
              summary = EXCLUDED.summary,
              key_drivers = EXCLUDED.key_drivers,
              affected_entities = EXCLUDED.affected_entities,
              evidence_span_ids = EXCLUDED.evidence_span_ids,
              limitations = EXCLUDED.limitations,
              recommended_actions = EXCLUDED.recommended_actions,
              next_review_at = EXCLUDED.next_review_at,
              metadata = EXCLUDED.metadata,
              updated_at = EXCLUDED.updated_at
            RETURNING id, (xmax = 0) AS inserted
            """,
            verdict.id,
            verdict.risk_case_id,
            verdict.verdict_type,
            verdict.severity,
            verdict.risk_score,
            verdict.confidence,
            verdict.summary,
            _jsonb(verdict.key_drivers),
            _jsonb(verdict.affected_entities),
            verdict.evidence_span_ids,
            _jsonb(verdict.limitations),
            _jsonb(verdict.recommended_actions),
            verdict.next_review_at,
            verdict.schema_version,
            _jsonb(verdict.metadata),
            verdict.created_at,
            verdict.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Risk verdict write returned no row for {verdict.id}")
        _assign_returned_id(verdict, row["id"])
        return _inserted(row)

    async def write_risk_alert(self, alert: RiskAlert) -> bool:
        row = await self.connection.fetchrow(
            """
            INSERT INTO risk_alerts (
              id, alert_key, risk_case_id, alert_type, severity, status,
              title, body, channels, payload, first_emitted_at, last_emitted_at,
              schema_version, metadata, created_at, updated_at
            )
            VALUES (
              $1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb,
              $11, $12, $13, $14::jsonb, $15, $16
            )
            ON CONFLICT (alert_key) DO UPDATE SET
              severity = EXCLUDED.severity,
              status = EXCLUDED.status,
              title = EXCLUDED.title,
              body = EXCLUDED.body,
              channels = EXCLUDED.channels,
              payload = EXCLUDED.payload,
              last_emitted_at = EXCLUDED.last_emitted_at,
              metadata = EXCLUDED.metadata,
              updated_at = EXCLUDED.updated_at
            RETURNING id, (xmax = 0) AS inserted
            """,
            alert.id,
            alert.alert_key,
            alert.risk_case_id,
            alert.alert_type,
            alert.severity,
            alert.status,
            alert.title,
            alert.body,
            _jsonb(alert.channels),
            _jsonb(alert.payload),
            alert.first_emitted_at,
            alert.last_emitted_at,
            alert.schema_version,
            _jsonb(alert.metadata),
            alert.created_at,
            alert.updated_at,
        )
        if row is None:
            raise RuntimeError(f"Risk alert write returned no row for {alert.alert_key}")
        _assign_returned_id(alert, row["id"])
        return _inserted(row)
