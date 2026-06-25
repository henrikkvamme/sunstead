import json
from datetime import UTC, datetime
from pathlib import Path

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.events.envelope import deserialize_event
from supply_intel.models.source import SourceCursor
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config
from supply_intel.sources.scheduler import (
    publish_scheduled_events_to_kafka,
    run_local_scheduler,
    source_config_hash,
)

SHA256_HEX_LENGTH = 64
EXPECTED_PUBLISHED_JOB_COUNT = 1


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


def test_source_config_hash_is_stable() -> None:
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))

    first = source_config_hash(config)
    second = source_config_hash(config)

    assert first == second
    assert len(first) == SHA256_HEX_LENGTH


def test_run_local_scheduler_writes_ingest_job_event(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)

    summary = run_local_scheduler(
        settings=settings,
        source_ids={"openfda_drug_ndc"},
    )

    assert summary.scheduled == 1
    assert summary.source_run_ids
    assert summary.event_ids

    source_runs = [
        json.loads(line)
        for line in (tmp_path / "source_runs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert source_runs[0]["source_id"] == "openfda_drug_ndc"
    assert source_runs[0]["run_type"] == "scheduled"
    assert source_runs[0]["status"] == "pending"
    assert events[0]["event_type"] == "ingest.jobs"
    assert events[0]["source"]["service"] == "scheduler"
    assert events[0]["source"]["source_id"] == "openfda_drug_ndc"
    assert events[0]["trace"]["source_run_id"] == source_runs[0]["id"]
    assert events[0]["correlation_id"] == source_runs[0]["correlation_id"]
    assert events[0]["payload"]["source_run_id"] == source_runs[0]["id"]
    assert events[0]["payload"]["run_type"] == "scheduled"
    assert events[0]["payload"]["config_hash"] == source_config_hash(
        load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    )


def test_run_local_scheduler_includes_current_source_cursor(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    store = FileEvidenceStore(tmp_path)
    cursor = SourceCursor(
        source_id="openfda_drug_ndc",
        cursor_state={"skip": 1000},
        watermark=datetime(2026, 6, 24, tzinfo=UTC),
        etag='"v1"',
    )
    store.write_source_cursor(cursor)

    run_local_scheduler(
        settings=settings,
        source_ids={"openfda_drug_ndc"},
    )

    source_runs = [
        json.loads(line)
        for line in (tmp_path / "source_runs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert source_runs[0]["cursor_before"]["cursor_state"] == {"skip": 1000}
    assert source_runs[0]["cursor_before"]["etag"] == '"v1"'
    assert events[0]["payload"]["cursor"] == source_runs[0]["cursor_before"]


def test_run_local_scheduler_dry_run_does_not_write(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)

    summary = run_local_scheduler(
        settings=settings,
        source_ids={"openfda_drug_ndc"},
        dry_run=True,
    )

    assert summary.dry_run is True
    assert summary.scheduled == 1
    assert not (tmp_path / "events.jsonl").exists()
    assert not (tmp_path / "source_runs.jsonl").exists()


async def test_publish_scheduled_events_to_kafka_uses_stored_ingest_job_envelope(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path)
    scheduler_summary = run_local_scheduler(
        settings=settings,
        source_ids={"openfda_drug_ndc"},
    )
    producer = FakeProducerClient()

    publish_summary = await publish_scheduled_events_to_kafka(
        settings=settings,
        event_ids=scheduler_summary.event_ids,
        producer_client=producer,
    )

    assert publish_summary.topic == "ingest.jobs"
    assert publish_summary.published == EXPECTED_PUBLISHED_JOB_COUNT
    assert publish_summary.event_ids == scheduler_summary.event_ids
    assert publish_summary.metrics_recorded == EXPECTED_PUBLISHED_JOB_COUNT
    topic, value, key, headers = producer.sent[0]
    event = deserialize_event(value)
    assert topic == "ingest.jobs"
    assert event.event_type == "ingest.jobs"
    assert str(event.event_id) == scheduler_summary.event_ids[0]
    assert key == str(event.payload["source_run_id"]).encode("utf-8")
    assert headers is not None
    assert ("event_type", b"ingest.jobs") in headers
    metric_topic, metric_value, metric_key, metric_headers = producer.sent[1]
    metric_event = deserialize_event(metric_value)
    assert metric_topic == "ops.metrics"
    assert metric_key == b"events_produced_total"
    assert metric_event.event_type == "ops.metrics"
    assert metric_event.causation_id == event.event_id
    assert metric_event.payload["metric_name"] == "events_produced_total"
    assert metric_event.payload["topic"] == "ingest.jobs"
    assert metric_event.payload["tags"] == {"event_type": "ingest.jobs"}
    assert metric_headers is not None
    assert ("event_type", b"ops.metrics") in metric_headers
    metric_rows = FileEvidenceStore(tmp_path).read_collection("ops_metrics")
    assert len(metric_rows) == EXPECTED_PUBLISHED_JOB_COUNT
    assert metric_rows[0]["metric_name"] == "events_produced_total"
    assert metric_rows[0]["topic"] == "ingest.jobs"
    assert metric_rows[0]["source_id"] == "openfda_drug_ndc"


async def test_publish_scheduled_events_to_kafka_requires_existing_audit_event(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path)

    try:
        await publish_scheduled_events_to_kafka(
            settings=settings,
            event_ids=["missing-event-id"],
            producer_client=FakeProducerClient(),
        )
    except ValueError as exc:
        assert "Scheduled events not found" in str(exc)
    else:
        raise AssertionError("missing scheduled events must fail before Kafka publish")
