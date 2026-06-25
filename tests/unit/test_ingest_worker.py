import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.events.consumer import PermanentEventError
from supply_intel.events.envelope import deserialize_event, serialize_event
from supply_intel.models.kafka import EventEnvelope
from supply_intel.models.source import SourceCursor
from supply_intel.settings import Settings
from supply_intel.sources.adapters.base import FetchedPayload, FetchPlan, FetchRequest
from supply_intel.sources.scheduler import run_local_scheduler
from supply_intel.sources.worker import (
    execute_ingest_job_event,
    run_ingest_worker,
    run_ingest_worker_once,
)

EXPECTED_NDC_ENTITY_COUNT = 4
EXPECTED_NDC_RELATIONSHIP_COUNT = 3
WORKER_BATCH_MESSAGE_COUNT = 2


@dataclass
class FakeMessage:
    topic: str
    key: bytes | None
    value: bytes | None


class FakeConsumerClient:
    def __init__(self, messages: list[FakeMessage]) -> None:
        self.messages = messages
        self.commits = 0

    async def getone(self) -> FakeMessage:
        return self.messages.pop(0)

    async def commit(self) -> None:
        self.commits += 1


class WaitingConsumerClient:
    def __init__(self) -> None:
        self.commits = 0

    async def getone(self) -> FakeMessage:
        await asyncio.sleep(60)
        raise AssertionError("idle timeout should stop before a message is returned")

    async def commit(self) -> None:
        self.commits += 1


class FakeProducerClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, bytes | None, list[tuple[str, bytes]] | None]] = []

    async def send_and_wait(
        self,
        topic: str,
        value: bytes,
        *,
        key: bytes | None = None,
        headers: list[tuple[str, bytes]] | None = None,
    ) -> object:
        self.sent.append((topic, value, key, headers))
        return {"topic": topic}


class SmartPostgresConnection:
    def __init__(self, *, fail_on_raw_document: bool = False) -> None:
        self.fail_on_raw_document = fail_on_raw_document
        self.fetches: list[tuple[str, tuple[object, ...]]] = []
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append((query, args))
        return "OK"

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        self.fetches.append((query, args))
        if self.fail_on_raw_document and "INSERT INTO raw_documents" in query:
            raise RuntimeError("postgres sync unavailable")
        returned_id = args[0] if args and isinstance(args[0], UUID) else uuid4()
        return {"id": returned_id, "inserted": True, "previous_status": None}


class FakeAdapter:
    adapter_type = "paginated_rest"

    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records
        self.planned_cursor: object | None = None

    async def plan_fetch(
        self,
        config: object,
        cursor: object,
        run: object,
        *,
        max_documents: int | None = None,
    ) -> FetchPlan:
        del config, run
        self.planned_cursor = cursor
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
                    "etag": '"worker-v1"',
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


def scheduled_ingest_job(settings: Settings) -> EventEnvelope:
    summary = run_local_scheduler(settings=settings, source_ids={"openfda_drug_ndc"})
    assert summary.scheduled == 1
    store = FileEvidenceStore(settings.data_dir)
    events = store.read_collection("events")
    return EventEnvelope.model_validate(events[-1])


def fake_ingest_message(event: EventEnvelope) -> FakeMessage:
    return FakeMessage(
        "ingest.jobs",
        str(event.payload["source_run_id"]).encode(),
        serialize_event(event),
    )


async def test_execute_ingest_job_event_preserves_scheduled_source_run_id(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path)
    store = FileEvidenceStore(tmp_path)
    store.write_source_cursor(
        SourceCursor(
            source_id="openfda_drug_ndc",
            cursor_state={"skip": 1000},
            watermark=datetime(2026, 6, 24, tzinfo=UTC),
            etag='"scheduled-v0"',
        )
    )
    event = scheduled_ingest_job(settings)
    adapter = FakeAdapter([fixture_ndc_record()])

    summary = await execute_ingest_job_event(
        settings=settings,
        event=event,
        max_documents=1,
        adapter=adapter,
    )

    source_run_id = str(event.payload["source_run_id"])
    assert summary.status == "succeeded"
    assert summary.source_run_id == source_run_id
    assert summary.stats["entities_resolved"] == EXPECTED_NDC_ENTITY_COUNT
    assert isinstance(adapter.planned_cursor, SourceCursor)
    assert adapter.planned_cursor.etag == '"scheduled-v0"'

    raw_documents = store.read_collection("raw_documents")
    assert raw_documents[0]["source_run_id"] == source_run_id

    matching_runs = [
        row for row in store.read_collection("source_runs") if row["id"] == source_run_id
    ]
    assert matching_runs[-1]["status"] == "succeeded"
    assert matching_runs[-1]["run_type"] == "scheduled"
    assert matching_runs[-1]["cursor_before"]["etag"] == '"scheduled-v0"'

    health = store.current_source_health("openfda_drug_ndc")
    assert health is not None
    assert health.metrics["source_run_id"] == source_run_id


async def test_execute_ingest_job_event_rejects_stale_config_hash(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    event = scheduled_ingest_job(settings)
    event.payload["config_hash"] = "stale"

    with pytest.raises(PermanentEventError, match="config hash"):
        await execute_ingest_job_event(
            settings=settings,
            event=event,
            adapter=FakeAdapter([fixture_ndc_record()]),
        )


async def test_run_ingest_worker_once_processes_and_commits(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    event = scheduled_ingest_job(settings)
    consumer = FakeConsumerClient([fake_ingest_message(event)])
    producer = FakeProducerClient()

    result = await run_ingest_worker_once(
        settings=settings,
        max_documents=1,
        consumer_client=consumer,
        producer_client=producer,
        adapter=FakeAdapter([fixture_ndc_record()]),
    )

    assert result.status == "processed"
    assert result.committed is True
    assert consumer.commits == 1
    assert _sent_topics(producer) == _expected_ndc_worker_topics()


async def test_run_ingest_worker_processes_bounded_batch(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    event_one = scheduled_ingest_job(settings)
    event_two = scheduled_ingest_job(settings)
    consumer = FakeConsumerClient([fake_ingest_message(event_one), fake_ingest_message(event_two)])
    producer = FakeProducerClient()

    summary = await run_ingest_worker(
        settings=settings,
        max_messages=WORKER_BATCH_MESSAGE_COUNT,
        max_documents=1,
        consumer_client=consumer,
        producer_client=producer,
        adapter=FakeAdapter([fixture_ndc_record()]),
    )

    assert summary.requested_messages == WORKER_BATCH_MESSAGE_COUNT
    assert summary.processed_messages == WORKER_BATCH_MESSAGE_COUNT
    assert summary.deadlettered_messages == 0
    assert summary.committed_messages == WORKER_BATCH_MESSAGE_COUNT
    assert summary.timed_out is False
    assert [execution.source_id for execution in summary.executions] == [
        "openfda_drug_ndc",
        "openfda_drug_ndc",
    ]
    assert [execution.status for execution in summary.executions] == ["succeeded", "succeeded"]
    assert summary.executions[0].stats["entities_resolved"] == EXPECTED_NDC_ENTITY_COUNT
    assert summary.executions[0].events_published == len(_expected_ndc_worker_topics())
    assert summary.executions[1].stats["raw_documents_unchanged"] == 1
    assert summary.executions[1].events_published == 0
    assert consumer.commits == WORKER_BATCH_MESSAGE_COUNT
    assert _sent_topics(producer) == _expected_ndc_worker_topics()


async def test_run_ingest_worker_exits_on_idle_timeout(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    consumer = WaitingConsumerClient()
    producer = FakeProducerClient()

    summary = await run_ingest_worker(
        settings=settings,
        max_messages=1,
        idle_timeout_seconds=0.01,
        consumer_client=consumer,
        producer_client=producer,
        adapter=FakeAdapter([fixture_ndc_record()]),
    )

    assert summary.timed_out is True
    assert summary.processed_messages == 0
    assert summary.deadlettered_messages == 0
    assert summary.committed_messages == 0
    assert summary.executions == []
    assert consumer.commits == 0
    assert producer.sent == []


def test_run_ingest_worker_cli_rejects_loop_options_in_once_mode() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["run-ingest-worker", "--max-messages", "2"])

    assert result.exit_code != 0
    assert "--max-messages and --idle-timeout-seconds require --no-once" in result.output


def test_run_ingest_worker_cli_exposes_loop_mode() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["run-ingest-worker", "--help"])

    assert result.exit_code == 0
    assert "--no-once" in result.output
    assert "--max-messages" in result.output


async def test_run_ingest_worker_once_syncs_postgres_before_commit(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    event = scheduled_ingest_job(settings)
    consumer = FakeConsumerClient([fake_ingest_message(event)])
    producer = FakeProducerClient()
    postgres = SmartPostgresConnection()

    result = await run_ingest_worker_once(
        settings=settings,
        max_documents=1,
        consumer_client=consumer,
        producer_client=producer,
        adapter=FakeAdapter([fixture_ndc_record()]),
        evidence_backend="postgres",
        postgres_connection=postgres,
    )

    assert result.status == "processed"
    assert consumer.commits == 1
    assert any("INSERT INTO raw_documents" in query for query, _ in postgres.fetches)


async def test_run_ingest_worker_once_does_not_commit_when_postgres_sync_fails(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path)
    event = scheduled_ingest_job(settings)
    consumer = FakeConsumerClient([fake_ingest_message(event)])
    producer = FakeProducerClient()
    postgres = SmartPostgresConnection(fail_on_raw_document=True)

    with pytest.raises(RuntimeError, match="postgres sync unavailable"):
        await run_ingest_worker_once(
            settings=settings,
            max_documents=1,
            consumer_client=consumer,
            producer_client=producer,
            adapter=FakeAdapter([fixture_ndc_record()]),
            evidence_backend="postgres",
            postgres_connection=postgres,
        )

    assert consumer.commits == 0
    assert producer.sent == []


async def test_run_ingest_worker_once_deadletters_permanent_job_failure(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path)
    event = scheduled_ingest_job(settings)
    event.payload["config_hash"] = "stale"
    consumer = FakeConsumerClient([fake_ingest_message(event)])
    producer = FakeProducerClient()

    result = await run_ingest_worker_once(
        settings=settings,
        max_documents=1,
        consumer_client=consumer,
        producer_client=producer,
        adapter=FakeAdapter([fixture_ndc_record()]),
    )

    assert result.status == "deadlettered"
    assert result.committed is True
    assert result.deadletter_topic == "ingest.deadletter"
    assert consumer.commits == 1
    topic, value, key, headers = producer.sent[0]
    assert topic == "ingest.deadletter"
    assert key == str(event.payload["source_run_id"]).encode()
    deadletter = deserialize_event(value)
    assert deadletter.event_type == "ops.deadletter"
    assert deadletter.payload["error_type"] == "source_config_hash_mismatch"
    assert headers is not None


async def test_run_ingest_worker_summary_excludes_deadlettered_jobs_from_executions(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path)
    event = scheduled_ingest_job(settings)
    event.payload["config_hash"] = "stale"
    consumer = FakeConsumerClient([fake_ingest_message(event)])
    producer = FakeProducerClient()

    summary = await run_ingest_worker(
        settings=settings,
        max_messages=1,
        max_documents=1,
        consumer_client=consumer,
        producer_client=producer,
        adapter=FakeAdapter([fixture_ndc_record()]),
    )

    assert summary.processed_messages == 0
    assert summary.deadlettered_messages == 1
    assert summary.executions == []


def _sent_topics(producer: FakeProducerClient) -> list[str]:
    return [topic for topic, _, _, _ in producer.sent]


def _expected_ndc_worker_topics() -> list[str]:
    return [
        "ingest.raw_document_created",
        "ingest.document_parsed",
        "ingest.extraction_completed",
        *["graph.node_upsert"] * EXPECTED_NDC_ENTITY_COUNT,
        *["graph.relationship_upsert"] * EXPECTED_NDC_RELATIONSHIP_COUNT,
    ]
