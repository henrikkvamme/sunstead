import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.db.sync import sync_local_evidence_to_postgres
from supply_intel.entity_resolution.service import CanonicalEntity, EntityAlias, HumanReviewTask
from supply_intel.events.envelope import serialize_event
from supply_intel.models.graph import GraphNodeUpsert
from supply_intel.models.infra import OperationalMetric
from supply_intel.models.kafka import EventEnvelope
from supply_intel.models.source import SourceCursor
from supply_intel.settings import Settings
from supply_intel.sources.adapters.base import FetchedPayload, FetchPlan, FetchRequest
from supply_intel.sources.registry import load_source_config
from supply_intel.sources.scheduler import run_local_scheduler
from supply_intel.sources.worker import execute_ingest_job_event

EXPECTED_NDC_ENTITY_COUNT = 4
EXPECTED_NDC_ALIAS_COUNT = 6
EXPECTED_NDC_RELATIONSHIP_COUNT = 3


class SmartPostgresConnection:
    def __init__(self) -> None:
        self.fetches: list[tuple[str, tuple[object, ...]]] = []
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append((query, args))
        return "OK"

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        self.fetches.append((query, args))
        returned_id = args[0] if args and isinstance(args[0], UUID) else uuid4()
        return {"id": returned_id, "inserted": True, "previous_status": None}


class CanonicalEntityRemapConnection(SmartPostgresConnection):
    def __init__(self, *, local_entity_id: UUID, postgres_entity_id: UUID) -> None:
        super().__init__()
        self.local_entity_id = local_entity_id
        self.postgres_entity_id = postgres_entity_id

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        self.fetches.append((query, args))
        if "INSERT INTO canonical_entities" in query and args[0] == self.local_entity_id:
            return {"id": self.postgres_entity_id, "inserted": False, "previous_status": None}
        returned_id = args[0] if args and isinstance(args[0], UUID) else uuid4()
        return {"id": returned_id, "inserted": True, "previous_status": None}


class FakeAdapter:
    adapter_type = "paginated_rest"

    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records

    async def plan_fetch(
        self,
        config: object,
        cursor: object,
        run: object,
        *,
        max_documents: int | None = None,
    ) -> FetchPlan:
        del config, cursor, run
        return FetchPlan(
            requests=[FetchRequest(url="https://example.test/openfda")],
            max_documents=max_documents,
        )

    async def fetch(
        self,
        config: object,
        plan: FetchPlan,
    ) -> AsyncIterator[FetchedPayload]:
        del config
        for record in self.records[: plan.max_documents]:
            yield FetchedPayload(
                source_url="https://example.test/openfda?limit=1&skip=0",
                status_code=200,
                headers={
                    "content-type": "application/json",
                    "etag": '"sync-v1"',
                    "last-modified": "Wed, 24 Jun 2026 10:00:00 GMT",
                },
                content_type="application/json",
                text=json.dumps(record, sort_keys=True),
                record=record,
            )


def fixture_ndc_record() -> dict[str, object]:
    data = json.loads(
        Path("tests/fixtures/sources/openfda_drug_ndc/success.json").read_text(encoding="utf-8")
    )
    record = data["results"][0]
    assert isinstance(record, dict)
    return record


async def create_local_ingestion(settings: Settings) -> EventEnvelope:
    run_local_scheduler(settings=settings, source_ids={"openfda_drug_ndc"})
    event = EventEnvelope.model_validate(
        json.loads((settings.data_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    )
    await execute_ingest_job_event(
        settings=settings,
        event=event,
        max_documents=1,
        adapter=FakeAdapter([fixture_ndc_record()]),
    )
    return event


async def test_sync_local_evidence_to_postgres_replays_worker_artifacts(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path)
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    event = await create_local_ingestion(settings)
    FileEvidenceStore(tmp_path).write_operational_metric(
        OperationalMetric(
            metric_name="events_produced_total",
            metric_value=1,
            service="scheduler",
            source_id="openfda_drug_ndc",
            topic="ingest.jobs",
            unit="count",
            idempotency_key=f"ops.metrics:events_produced_total:ingest.jobs:{event.event_id}",
            causation_id=event.event_id,
            correlation_id=event.correlation_id,
            tags={"event_type": "ingest.jobs"},
        )
    )
    write_unrelated_local_artifacts(tmp_path)
    connection = SmartPostgresConnection()

    summary = await sync_local_evidence_to_postgres(
        settings=settings,
        configs=[config],
        connection=connection,
    )

    assert summary.rows_by_collection["data_sources"] == 1
    assert summary.rows_by_collection["raw_documents"] == 1
    assert summary.rows_by_collection["document_chunks"] == 1
    assert summary.rows_by_collection["extraction_runs"] == 1
    assert summary.rows_by_collection["evidence_spans"] == 1
    assert summary.rows_by_collection["canonical_entities"] == EXPECTED_NDC_ENTITY_COUNT
    assert summary.rows_by_collection["entity_aliases"] == EXPECTED_NDC_ALIAS_COUNT
    assert summary.rows_by_collection["graph_node_upserts"] == EXPECTED_NDC_ENTITY_COUNT
    assert (
        summary.rows_by_collection["graph_relationship_upserts"] == EXPECTED_NDC_RELATIONSHIP_COUNT
    )
    assert summary.rows_by_collection["ops_metrics"] == 1
    assert summary.rows_by_collection["source_health"] == 1
    queries = [query for query, _ in connection.fetches]
    assert "INSERT INTO data_sources" in queries[0]
    assert any("INSERT INTO raw_documents" in query for query in queries)
    assert any("INSERT INTO ops_metrics" in query for query in queries)
    assert not any("INSERT INTO events" in query for query in queries)


async def test_sync_local_evidence_to_postgres_preserves_scheduled_cursor_snapshot(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path)
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))

    FileEvidenceStore(tmp_path).write_source_cursor(
        SourceCursor(
            source_id="openfda_drug_ndc",
            cursor_state={"skip": 500},
            watermark=datetime(2026, 6, 24, tzinfo=UTC),
            etag='"sync-v0"',
        )
    )
    await create_local_ingestion(settings)
    connection = SmartPostgresConnection()

    await sync_local_evidence_to_postgres(
        settings=settings,
        configs=[config],
        connection=connection,
    )

    source_run_fetches = [
        args for query, args in connection.fetches if "INSERT INTO source_runs" in query
    ]
    assert source_run_fetches
    final_run_args = source_run_fetches[-1]
    cursor_before = json.loads(final_run_args[6])
    assert cursor_before["etag"] == '"sync-v0"'
    assert cursor_before["cursor_state"] == {"skip": 500}


async def test_sync_local_evidence_to_postgres_remaps_existing_canonical_entity_ids(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path)
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    await create_local_ingestion(settings)
    canonical_entity = _read_jsonl(tmp_path / "canonical_entities.jsonl")[0]
    local_entity_id = UUID(str(canonical_entity["id"]))
    postgres_entity_id = uuid4()
    local_alias = next(
        row
        for row in _read_jsonl(tmp_path / "entity_aliases.jsonl")
        if UUID(str(row["canonical_entity_id"])) == local_entity_id
    )
    connection = CanonicalEntityRemapConnection(
        local_entity_id=local_entity_id,
        postgres_entity_id=postgres_entity_id,
    )

    await sync_local_evidence_to_postgres(
        settings=settings,
        configs=[config],
        connection=connection,
    )

    alias_args = [
        args for query, args in connection.fetches if "INSERT INTO entity_aliases" in query
    ]
    assert any(
        args[1] == postgres_entity_id and args[3] == local_alias["normalized_alias"]
        for args in alias_args
    )


async def test_sync_local_evidence_to_postgres_syncs_human_review_queue_with_remaps(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path)
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    await create_local_ingestion(settings)
    canonical_entity = _read_jsonl(tmp_path / "canonical_entities.jsonl")[0]
    evidence_span = _read_jsonl(tmp_path / "evidence_spans.jsonl")[0]
    local_entity_id = UUID(str(canonical_entity["id"]))
    postgres_entity_id = uuid4()
    review_task = HumanReviewTask(
        target_table="canonical_entities",
        target_id=local_entity_id,
        review_type="low_confidence",
        reason="Review remapped entity id.",
        priority="P1",
        evidence_span_ids=[UUID(str(evidence_span["id"]))],
    )
    FileEvidenceStore(tmp_path).write_human_review_task(review_task)
    connection = CanonicalEntityRemapConnection(
        local_entity_id=local_entity_id,
        postgres_entity_id=postgres_entity_id,
    )

    summary = await sync_local_evidence_to_postgres(
        settings=settings,
        configs=[config],
        connection=connection,
    )

    review_args = [
        args for query, args in connection.fetches if "INSERT INTO human_review_queue" in query
    ]
    feedback_args = [
        args for query, args in connection.fetches if "INSERT INTO human_feedback" in query
    ]
    assert summary.rows_by_collection["human_review_queue"] == 1
    assert review_args
    assert review_args[0][2] == postgres_entity_id
    assert review_args[0][7] == [UUID(str(evidence_span["id"]))]
    assert feedback_args
    assert feedback_args[0][2] == postgres_entity_id


def test_sync_event_fixture_uses_serializable_envelope(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    event = run_local_scheduler(settings=settings, source_ids={"openfda_drug_ndc"})
    stored = EventEnvelope.model_validate(
        json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    )

    assert event.event_ids == [str(stored.event_id)]
    assert serialize_event(stored)


async def test_sync_postgres_evidence_cli_plans_source_scoped_rows(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    await create_local_ingestion(settings)
    write_unrelated_local_artifacts(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "sync-postgres-evidence",
            "--source-id",
            "openfda_drug_ndc",
            "--data-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["apply"] is False
    assert payload["source_ids"] == ["openfda_drug_ndc"]
    assert payload["rows_by_collection"]["data_sources"] == 1
    assert payload["rows_by_collection"]["canonical_entities"] == EXPECTED_NDC_ENTITY_COUNT
    assert payload["rows_by_collection"]["graph_node_upserts"] == EXPECTED_NDC_ENTITY_COUNT
    assert payload["inserted_by_collection"]["canonical_entities"] == 0


async def test_sync_postgres_evidence_cli_accepts_aiven_default_secret_paths(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    secrets_dir = tmp_path / "aiven"
    secrets_dir.mkdir()
    (secrets_dir / "postgres-url").write_text(
        "postgresql://aiven.example.test/defaultdb\n",
        encoding="utf-8",
    )
    (secrets_dir / "project-ca.pem").write_text("ca-cert\n", encoding="utf-8")
    settings = Settings(data_dir=data_dir, _env_file=None)
    await create_local_ingestion(settings)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "sync-postgres-evidence",
            "--source-id",
            "openfda_drug_ndc",
            "--data-dir",
            str(data_dir),
            "--aiven-defaults",
            "--aiven-secrets-dir",
            str(secrets_dir),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["apply"] is False
    assert payload["data_dir"] == str(data_dir)
    assert payload["source_ids"] == ["openfda_drug_ndc"]
    assert "postgresql://aiven.example.test" not in result.output


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def write_unrelated_local_artifacts(data_dir: Path) -> None:
    store = FileEvidenceStore(data_dir)
    entity = CanonicalEntity(
        entity_type="Supplier",
        canonical_key="Supplier:unrelated",
        display_name="Unrelated Supplier",
        normalized_name="unrelated supplier",
        confidence=0.99,
    )
    store.write_canonical_entity(entity)
    store.write_entity_alias(
        EntityAlias(
            canonical_entity_id=entity.id,
            alias="Unrelated Supplier",
            normalized_alias="unrelated supplier",
            source_id="unrelated_source",
            confidence=0.99,
        )
    )
    store.write_graph_node(
        GraphNodeUpsert(
            graph_node_key="Supplier:unrelated",
            labels=["Supplier"],
            properties={"key": "Supplier:unrelated", "name": "Unrelated Supplier"},
            source_document_id=uuid4(),
            evidence_span_id=uuid4(),
            extraction_run_id=uuid4(),
            confidence=0.99,
        )
    )
