import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from supply_intel.db.repositories.evidence import PostgresEvidenceStore
from supply_intel.entity_resolution.service import (
    CanonicalEntity,
    EntityAlias,
    HumanFeedback,
    HumanReviewTask,
)
from supply_intel.models.agents import AgentFinding
from supply_intel.models.documents import DocumentChunk
from supply_intel.models.extraction import EntityMention
from supply_intel.models.graph import GraphNodeUpsert
from supply_intel.models.infra import MCPAuditLog, OperationalMetric
from supply_intel.models.risk import RiskCandidate, RiskFeatureSnapshot, RiskScope
from supply_intel.models.source import IngestionError, RawDocument, SourceCursor, SourceRun
from supply_intel.sources.registry import load_source_config

EXPECTED_SOURCE_RUN_HEALTH_WRITES = 2
RISK_FEATURE_VALUE = 0.98


class FakePostgresConnection:
    def __init__(self, rows: list[dict[str, Any] | None]) -> None:
        self.rows = rows
        self.fetches: list[tuple[str, tuple[object, ...]]] = []
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append((query, args))
        return "OK"

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        self.fetches.append((query, args))
        return self.rows.pop(0)

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        self.fetches.append((query, args))
        rows = self.rows.pop(0)
        assert isinstance(rows, list)
        return rows


async def test_postgres_store_registers_source_with_upsert() -> None:
    connection = FakePostgresConnection([{"id": uuid4(), "inserted": True}])
    store = PostgresEvidenceStore(connection)
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))

    inserted = await store.register_source(config)

    assert inserted is True
    query, args = connection.fetches[0]
    assert "INSERT INTO data_sources" in query
    assert "ON CONFLICT (source_id) DO UPDATE" in query
    config_payload = args[5]
    assert isinstance(config_payload, str)
    assert json.loads(config_payload)["source_id"] == "openfda_drug_ndc"
    assert args[10] == "OPENFDA_API_KEY"


async def test_postgres_store_raw_document_returns_existing_id_on_dedupe() -> None:
    existing_id = uuid4()
    connection = FakePostgresConnection([{"id": existing_id, "inserted": False}])
    store = PostgresEvidenceStore(connection)
    run = SourceRun(
        source_id="openfda_drug_ndc",
        run_type="manual",
        status="running",
        idempotency_key="run-1",
    )
    document = RawDocument(
        source_id="openfda_drug_ndc",
        source_run_id=run.id,
        source_url="https://api.fda.gov/drug/ndc.json",
        canonical_url="https://api.fda.gov/drug/ndc.json",
        request={"method": "GET"},
        response_headers={},
        http_status=200,
        content_type="application/json",
        content_length=2,
        content_hash="hash-1",
        payload_storage="inline",
        payload_text="{}",
        fetched_at=datetime.now(UTC),
        dedupe_key="0002-8215",
        raw_metadata={"source_name": "openFDA Drug NDC"},
    )

    inserted = await store.write_raw_document(document)

    assert inserted is False
    assert document.id == existing_id
    query, _ = connection.fetches[0]
    assert "ON CONFLICT (source_id, dedupe_key, content_hash) DO NOTHING" in query
    assert "SELECT id, false AS inserted" in query


async def test_postgres_store_raw_document_writes_payload_bytes() -> None:
    document_id = uuid4()
    connection = FakePostgresConnection([{"id": document_id, "inserted": True}])
    store = PostgresEvidenceStore(connection)
    run = SourceRun(
        source_id="openfda_drug_ndc",
        run_type="manual",
        status="running",
        idempotency_key="run-1",
    )
    payload = b"%PDF-1.7\nbinary-\xff\n"
    document = RawDocument(
        source_id="openfda_drug_ndc",
        source_run_id=run.id,
        source_url="https://example.test/file.pdf",
        canonical_url="https://example.test/file.pdf",
        request={"method": "GET"},
        response_headers={"content-type": "application/pdf"},
        http_status=200,
        content_type="application/pdf",
        content_length=len(payload),
        content_hash="hash-1",
        payload_storage="inline",
        payload_bytes=payload,
        fetched_at=datetime.now(UTC),
        dedupe_key="https://example.test/file.pdf",
        raw_metadata={"source_name": "openFDA Drug NDC"},
    )

    inserted = await store.write_raw_document(document)

    assert inserted is True
    query, args = connection.fetches[0]
    assert "payload_bytes" in query
    assert args[12] == payload
    assert args[13] is None


async def test_postgres_store_completed_source_run_updates_source_health() -> None:
    source_run_id = uuid4()
    source_health_id = uuid4()
    connection = FakePostgresConnection(
        [
            {"id": source_run_id, "inserted": True},
            {"id": source_health_id, "inserted": True},
        ]
    )
    store = PostgresEvidenceStore(connection)
    run = SourceRun(
        id=source_run_id,
        source_id="openfda_drug_ndc",
        run_type="manual",
        status="succeeded",
        finished_at=datetime.now(UTC),
        documents_seen=1,
        documents_created=1,
        idempotency_key="run-success",
    )

    inserted = await store.write_source_run(run)

    assert inserted is True
    assert len(connection.fetches) == EXPECTED_SOURCE_RUN_HEALTH_WRITES
    source_run_query, _ = connection.fetches[0]
    source_health_query, args = connection.fetches[1]
    assert "INSERT INTO source_runs" in source_run_query
    assert "INSERT INTO source_health" in source_health_query
    assert "ON CONFLICT (source_id) DO UPDATE" in source_health_query
    assert args[1] == "openfda_drug_ndc"
    assert args[2] == "healthy"
    assert json.loads(args[8])["documents_created"] == 1


async def test_postgres_store_writes_source_cursor_with_upsert() -> None:
    cursor_id = uuid4()
    source_run_id = uuid4()
    connection = FakePostgresConnection([{"id": cursor_id, "inserted": True}])
    store = PostgresEvidenceStore(connection)
    cursor = SourceCursor(
        id=cursor_id,
        source_id="openfda_drug_ndc",
        cursor_state={"skip": 1000},
        watermark=datetime(2026, 6, 24, tzinfo=UTC),
        etag='"v1"',
        last_content_hash="hash-1",
        updated_by_run_id=source_run_id,
    )

    inserted = await store.write_source_cursor(cursor)

    assert inserted is True
    query, args = connection.fetches[0]
    assert "INSERT INTO source_cursors" in query
    assert "ON CONFLICT (source_id, cursor_name) DO UPDATE" in query
    assert args[1] == "openfda_drug_ndc"
    assert args[2] == "default"
    assert json.loads(args[3]) == {"skip": 1000}
    assert args[5] == '"v1"'
    assert args[7] == source_run_id


async def test_postgres_store_writes_document_chunk_embedding_vector() -> None:
    chunk_id = uuid4()
    connection = FakePostgresConnection([{"id": chunk_id, "inserted": True}])
    store = PostgresEvidenceStore(connection)
    chunk = DocumentChunk(
        id=chunk_id,
        raw_document_id=uuid4(),
        chunk_index=0,
        chunk_type="json_record",
        text="embedded chunk",
        embedding=[0.1, 0.2],
        embedding_model="text-embedding-test",
        content_hash="chunk-hash",
    )

    inserted = await store.write_chunk(chunk)

    assert inserted is True
    query, args = connection.fetches[0]
    assert "embedding, embedding_model" in query
    assert "$12::vector" in query
    assert args[11] == "[0.1,0.2]"
    assert args[12] == "text-embedding-test"


async def test_postgres_store_reads_current_source_cursor() -> None:
    cursor_id = uuid4()
    source_run_id = uuid4()
    connection = FakePostgresConnection(
        [
            {
                "id": cursor_id,
                "source_id": "openfda_drug_ndc",
                "cursor_name": "default",
                "cursor_state": {"skip": 1000},
                "watermark": datetime(2026, 6, 24, tzinfo=UTC),
                "etag": '"v1"',
                "last_content_hash": "hash-1",
                "updated_by_run_id": source_run_id,
                "schema_version": 1,
                "metadata": {},
                "created_at": datetime(2026, 6, 24, tzinfo=UTC),
                "updated_at": datetime(2026, 6, 24, tzinfo=UTC),
            }
        ]
    )
    store = PostgresEvidenceStore(connection)

    cursor = await store.current_source_cursor("openfda_drug_ndc")

    assert cursor is not None
    assert cursor.id == cursor_id
    assert cursor.cursor_state == {"skip": 1000}
    assert cursor.updated_by_run_id == source_run_id
    query, args = connection.fetches[0]
    assert "FROM source_cursors" in query
    assert args == ("openfda_drug_ndc", "default")


async def test_postgres_store_replayed_failed_source_run_does_not_update_source_health() -> None:
    source_run_id = uuid4()
    connection = FakePostgresConnection(
        [{"id": source_run_id, "inserted": False, "previous_status": "failed"}]
    )
    store = PostgresEvidenceStore(connection)
    run = SourceRun(
        id=source_run_id,
        source_id="openfda_drug_ndc",
        run_type="manual",
        status="failed",
        finished_at=datetime.now(UTC),
        error_count=1,
        idempotency_key="run-failed",
    )

    inserted = await store.write_source_run(run)

    assert inserted is False
    assert len(connection.fetches) == 1
    source_run_query, _ = connection.fetches[0]
    assert "previous_status" in source_run_query


async def test_postgres_store_graph_audit_payload_keeps_evidence_provenance() -> None:
    connection = FakePostgresConnection([{"id": uuid4(), "inserted": True}])
    store = PostgresEvidenceStore(connection)
    source_document_id = uuid4()
    evidence_span_id = uuid4()
    extraction_run_id = uuid4()
    node = GraphNodeUpsert(
        graph_node_key="Drug:ndc_product:0002-8215",
        labels=["Drug"],
        properties={"display_name": "Example drug"},
        source_document_id=source_document_id,
        evidence_span_id=evidence_span_id,
        extraction_run_id=extraction_run_id,
        confidence=0.96,
    )

    inserted = await store.write_graph_node(node)

    assert inserted is True
    query, args = connection.fetches[0]
    assert "INSERT INTO graph_upsert_audit" in query
    payload = args[3]
    assert isinstance(payload, str)
    decoded = json.loads(payload)
    assert decoded["source_document_id"] == str(source_document_id)
    assert decoded["evidence_span_id"] == str(evidence_span_id)
    assert decoded["extraction_run_id"] == str(extraction_run_id)
    assert args[6] == (
        "graph:node:Drug:ndc_product:0002-8215:"
        f"{source_document_id}:{evidence_span_id}:{extraction_run_id}"
    )


async def test_postgres_store_writes_mcp_audit_log() -> None:
    audit_id = uuid4()
    connection = FakePostgresConnection([{"id": audit_id, "inserted": True}])
    store = PostgresEvidenceStore(connection)
    record = MCPAuditLog(
        controller="aiven_mcp",
        action="ensure_kafka_topic",
        project="demo",
        service_name="kafka-dev",
        request={"topic_name": "risk.alerts"},
        response_summary={"status": "ensured"},
        status="succeeded",
        metadata={"safety_level": "migration_write"},
    )

    inserted = await store.write_mcp_audit_log(record)

    assert inserted is True
    assert record.id == audit_id
    query, args = connection.fetches[0]
    assert "INSERT INTO mcp_audit_log" in query
    assert args[1] == "aiven_mcp"
    assert args[2] == "ensure_kafka_topic"
    assert json.loads(args[5])["topic_name"] == "risk.alerts"
    assert json.loads(args[6])["status"] == "ensured"
    assert args[7] == "succeeded"


async def test_postgres_store_writes_operational_metric_idempotently() -> None:
    metric_id = uuid4()
    connection = FakePostgresConnection([{"id": metric_id, "inserted": True}])
    store = PostgresEvidenceStore(connection)
    correlation_id = uuid4()
    causation_id = uuid4()
    metric = OperationalMetric(
        metric_name="events_produced_total",
        metric_value=1,
        service="scheduler",
        source_id="openfda_drug_ndc",
        topic="ingest.jobs",
        unit="count",
        idempotency_key=f"ops.metrics:events_produced_total:ingest.jobs:{causation_id}",
        correlation_id=correlation_id,
        causation_id=causation_id,
        tags={"event_type": "ingest.jobs"},
    )

    inserted = await store.write_operational_metric(metric)

    assert inserted is True
    assert metric.id == metric_id
    query, args = connection.fetches[0]
    assert "INSERT INTO ops_metrics" in query
    assert "ON CONFLICT (idempotency_key) DO NOTHING" in query
    assert args[1] == "events_produced_total"
    assert args[4] == "scheduler"
    assert args[6] == "ingest.jobs"
    assert args[8] == correlation_id
    assert args[9] == causation_id
    assert json.loads(args[11]) == {"event_type": "ingest.jobs"}


async def test_postgres_store_writes_risk_candidate_with_upsert() -> None:
    candidate_id = uuid4()
    evidence_span_id = uuid4()
    connection = FakePostgresConnection([{"id": candidate_id, "inserted": True}])
    store = PostgresEvidenceStore(connection)
    candidate = RiskCandidate(
        candidate_key="risk_candidate:recall_quality:Recall:openfda:abc",
        risk_type="recall_quality",
        scope=RiskScope(type="Recall", graph_key="Recall:openfda:abc"),
        signals=[{"classification": "Class II", "affected_relationships": 2}],
        initial_score=75.0,
        confidence=0.9,
        evidence_span_ids=[evidence_span_id],
    )

    inserted = await store.write_risk_candidate(candidate)

    assert inserted is True
    assert candidate.id == candidate_id
    query, args = connection.fetches[0]
    assert "INSERT INTO risk_candidates" in query
    assert "ON CONFLICT (candidate_key) DO UPDATE" in query
    assert args[1] == "risk_candidate:recall_quality:Recall:openfda:abc"
    scope = json.loads(args[3])
    assert scope["type"] == "Recall"
    assert scope["graph_key"] == "Recall:openfda:abc"
    assert json.loads(args[4])[0]["classification"] == "Class II"
    assert args[7] == [evidence_span_id]


async def test_postgres_store_writes_typed_ingestion_error() -> None:
    error_id = uuid4()
    connection = FakePostgresConnection([{"id": error_id, "inserted": True}])
    store = PostgresEvidenceStore(connection)
    source_run_id = uuid4()
    raw_document_id = uuid4()
    error = IngestionError(
        source_id="openfda_drug_ndc",
        source_run_id=source_run_id,
        raw_document_id=raw_document_id,
        stage="extractor",
        error_type="ValidationError",
        message="agent output failed validation",
        details={"document_chunk_id": str(uuid4())},
        retryable=True,
    )

    inserted = await store.write_ingestion_error(error)

    assert inserted is True
    assert error.id == error_id
    query, args = connection.fetches[0]
    assert "INSERT INTO ingestion_errors" in query
    assert args[1] == "openfda_drug_ndc"
    assert args[2] == source_run_id
    assert args[3] == raw_document_id
    assert args[4] == "extractor"
    assert json.loads(args[7])["document_chunk_id"]


async def test_postgres_store_writes_human_feedback_audit_record() -> None:
    feedback_id = uuid4()
    target_id = uuid4()
    connection = FakePostgresConnection([{"id": feedback_id, "inserted": True}])
    store = PostgresEvidenceStore(connection)
    feedback = HumanFeedback(
        target_table="canonical_entities",
        target_id=target_id,
        feedback_type="review_requested",
        decision="pending",
        comment="Low-confidence manufacturer match.",
        after_value={"status": "open", "priority": "P1"},
        metadata={"evidence_span_ids": [str(uuid4())]},
    )

    inserted = await store.write_human_feedback(feedback)

    assert inserted is True
    assert feedback.id == feedback_id
    query, args = connection.fetches[0]
    assert "INSERT INTO human_feedback" in query
    assert args[1] == "canonical_entities"
    assert args[2] == target_id
    assert args[3] == "review_requested"
    assert args[4] == "pending"
    assert json.loads(args[8])["priority"] == "P1"
    assert json.loads(args[9])["evidence_span_ids"]


async def test_postgres_store_upserts_human_review_task() -> None:
    task_id = uuid4()
    target_id = uuid4()
    evidence_span_id = uuid4()
    connection = FakePostgresConnection([{"id": task_id, "inserted": True}])
    store = PostgresEvidenceStore(connection)
    task = HumanReviewTask(
        target_table="canonical_entities",
        target_id=target_id,
        review_type="low_confidence",
        reason="Review low-confidence manufacturer.",
        priority="P1",
        evidence_span_ids=[evidence_span_id],
    )

    inserted = await store.write_human_review_task(task)

    assert inserted is True
    assert task.id == task_id
    query, args = connection.fetches[0]
    assert "INSERT INTO human_review_queue" in query
    assert "ON CONFLICT (target_table, target_id) DO UPDATE" in query
    assert args[1] == "canonical_entities"
    assert args[2] == target_id
    assert args[3] == "low_confidence"
    assert args[5] == "open"
    assert args[7] == [evidence_span_id]


async def test_postgres_store_reads_and_resolves_human_review_task() -> None:
    task = HumanReviewTask(
        target_table="canonical_entities",
        target_id=uuid4(),
        review_type="conflict",
        reason="Conflicting deterministic source assertions.",
        priority="P0",
        evidence_span_ids=[uuid4()],
    )
    resolved = task.model_copy(update={"status": "resolved"})
    connection = FakePostgresConnection(
        [
            [task.model_dump(mode="python")],
            resolved.model_dump(mode="python"),
        ]
    )
    store = PostgresEvidenceStore(connection)

    tasks = await store.read_human_review_tasks(status="open")
    resolved_task = await store.resolve_human_review_task(task.id)

    assert tasks == [task]
    assert resolved_task == resolved
    assert "FROM human_review_queue" in connection.fetches[0][0]
    assert connection.fetches[0][1] == ("open",)
    assert "UPDATE human_review_queue" in connection.fetches[1][0]


async def test_postgres_store_upserts_agent_finding() -> None:
    finding_id = uuid4()
    risk_case_id = uuid4()
    evidence_span_id = uuid4()
    connection = FakePostgresConnection([{"id": finding_id, "inserted": True}])
    store = PostgresEvidenceStore(connection)
    finding = AgentFinding(
        id=finding_id,
        risk_case_id=risk_case_id,
        agent_name="evidence_verifier",
        agent_version="1.0",
        finding_type="evidence_check",
        finding={"status": "supported"},
        evidence_span_ids=[evidence_span_id],
        confidence=0.93,
        critic_status="approved",
    )

    inserted = await store.write_agent_finding(finding)

    assert inserted is True
    query, args = connection.fetches[0]
    assert "INSERT INTO agent_findings" in query
    assert "ON CONFLICT (id) DO UPDATE" in query
    assert args[0] == finding_id
    assert args[1] == risk_case_id
    assert args[2] == "evidence_verifier"
    assert args[4] == "deterministic-local"
    assert args[5] == "deterministic_agent_finding_v1"
    assert args[7] == "AgentFinding"
    assert json.loads(args[9]) == {}
    assert args[10] == "evidence_check"
    assert json.loads(args[11]) == {"status": "supported"}
    assert args[12] == [evidence_span_id]
    assert args[14] == "approved"
    assert args[16] is None


async def test_postgres_store_upserts_risk_feature_snapshot() -> None:
    snapshot_id = uuid4()
    risk_case_id = uuid4()
    evidence_span_id = uuid4()
    connection = FakePostgresConnection([{"id": snapshot_id, "inserted": False}])
    store = PostgresEvidenceStore(connection)
    snapshot = RiskFeatureSnapshot(
        id=snapshot_id,
        risk_case_id=risk_case_id,
        case_key="risk:recall_quality:Recall:openfda:123",
        scope_type="Recall",
        graph_node_key="Recall:openfda:123",
        feature_name="evidence_confidence",
        value=RISK_FEATURE_VALUE,
        evidence_span_ids=[evidence_span_id],
        computed_at=datetime.now(UTC),
    )

    inserted = await store.write_risk_feature_snapshot(snapshot)

    assert inserted is False
    query, args = connection.fetches[0]
    assert "INSERT INTO risk_feature_snapshots" in query
    assert 'ON CONFLICT (risk_case_id, feature_name, feature_version, "window")' in query
    assert args[1] == risk_case_id
    assert args[2] == "risk:recall_quality:Recall:openfda:123"
    assert args[6] == "evidence_confidence"
    assert args[7] == RISK_FEATURE_VALUE
    assert args[9] == [evidence_span_id]
    assert args[11] == "risk_features.v1"


async def test_postgres_store_upserts_canonical_entity_with_review_state() -> None:
    entity_id = uuid4()
    connection = FakePostgresConnection([{"id": entity_id, "inserted": True}])
    store = PostgresEvidenceStore(connection)
    entity = CanonicalEntity(
        id=entity_id,
        entity_type="Manufacturer",
        canonical_key="Manufacturer:labeler:acme",
        display_name="Acme",
        normalized_name="acme",
        external_ids={"fei": "123"},
        attributes={"country": "US"},
        confidence=0.82,
        needs_review=True,
        review_reason="Low-confidence manufacturer match.",
    )

    inserted = await store.write_canonical_entity(entity)

    assert inserted is True
    query, args = connection.fetches[0]
    assert "INSERT INTO canonical_entities" in query
    assert "ON CONFLICT (entity_type, canonical_key) DO UPDATE" in query
    assert args[1] == "Manufacturer"
    assert args[2] == "Manufacturer:labeler:acme"
    assert json.loads(args[5]) == {"fei": "123"}
    assert json.loads(args[6]) == {"country": "US"}
    assert args[9] is True
    assert args[10] == "Low-confidence manufacturer match."


async def test_postgres_store_upserts_entity_alias_with_evidence() -> None:
    alias_id = uuid4()
    canonical_entity_id = uuid4()
    evidence_span_id = uuid4()
    connection = FakePostgresConnection([{"id": alias_id, "inserted": True}])
    store = PostgresEvidenceStore(connection)
    alias = EntityAlias(
        id=alias_id,
        canonical_entity_id=canonical_entity_id,
        alias="Acme Inc.",
        normalized_alias="acme inc",
        alias_type="extracted_name",
        source_id="openfda_drug_ndc",
        evidence_span_id=evidence_span_id,
        confidence=0.91,
    )

    inserted = await store.write_entity_alias(alias)

    assert inserted is True
    query, args = connection.fetches[0]
    assert "INSERT INTO entity_aliases" in query
    assert "ON CONFLICT (canonical_entity_id, normalized_alias, alias_type) DO UPDATE" in query
    assert args[1] == canonical_entity_id
    assert args[3] == "acme inc"
    assert args[5] == "openfda_drug_ndc"
    assert args[6] == evidence_span_id


async def test_postgres_store_writes_entity_mention_idempotently() -> None:
    mention_id = uuid4()
    raw_document_id = uuid4()
    chunk_id = uuid4()
    extraction_run_id = uuid4()
    evidence_span_id = uuid4()
    canonical_entity_id = uuid4()
    connection = FakePostgresConnection([{"id": mention_id, "inserted": False}])
    store = PostgresEvidenceStore(connection)
    mention = EntityMention(
        id=mention_id,
        raw_document_id=raw_document_id,
        document_chunk_id=chunk_id,
        extraction_run_id=extraction_run_id,
        evidence_span_id=evidence_span_id,
        entity_type="Manufacturer",
        mention_text="Acme Inc.",
        normalized_mention="acme inc",
        candidate_external_ids={"fei": "123"},
        canonical_entity_id=canonical_entity_id,
        resolution_status="needs_human_review",
        resolution_confidence=0.82,
        resolution_method="deterministic_key",
        needs_review=True,
    )

    inserted = await store.write_entity_mention(mention)

    assert inserted is False
    query, args = connection.fetches[0]
    assert "INSERT INTO entity_mentions" in query
    assert "WHERE raw_document_id = $2" in query
    assert args[1] == raw_document_id
    assert args[2] == chunk_id
    assert args[4] == evidence_span_id
    assert args[5] == "Manufacturer"
    assert json.loads(args[8]) == {"fei": "123"}
    assert args[10] == "needs_human_review"


def test_baseline_migration_contains_risk_verdict_persistence() -> None:
    migration = Path("migrations/0001_extensions_and_evidence_schema.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS risk_verdicts" in migration
    assert "evidence_span_ids uuid[]" in migration
