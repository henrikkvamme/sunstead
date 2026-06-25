import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.events.envelope import deserialize_event, serialize_event
from supply_intel.models.kafka import EventEnvelope
from supply_intel.models.risk import RiskAlert
from supply_intel.pipeline import ingest_openfda_drug_enforcement_fixture
from supply_intel.risk.engine import run_local_risk_engine, run_risk_engine_consumer
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config

EXPECTED_RISK_EVENTS = 4
EXPECTED_RISK_FEATURE_SNAPSHOTS = 3
RISK_CONSUMER_MESSAGES = 1


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


def test_file_store_updates_existing_risk_alert_without_duplicate(
    tmp_path: Path,
) -> None:
    store = FileEvidenceStore(tmp_path)
    risk_case_id = uuid4()
    first_seen = datetime(2026, 6, 24, 10, 0, tzinfo=UTC)
    second_seen = datetime(2026, 6, 25, 10, 0, tzinfo=UTC)
    first = RiskAlert(
        alert_key="alert:risk:recall_quality:abc",
        risk_case_id=risk_case_id,
        alert_type="risk_case_created",
        severity="medium",
        status="open",
        title="Initial recall risk",
        body="Initial body",
        channels=["dashboard"],
        payload={"case_key": "risk:recall_quality:abc", "run": "first"},
        first_emitted_at=first_seen,
        last_emitted_at=first_seen,
    )
    second = RiskAlert(
        alert_key=first.alert_key,
        risk_case_id=risk_case_id,
        alert_type="risk_case_created",
        severity="high",
        status="acknowledged",
        title="Updated recall risk",
        body="Updated body",
        channels=["dashboard", "email"],
        payload={"case_key": "risk:recall_quality:abc", "run": "second"},
        first_emitted_at=second_seen,
        last_emitted_at=second_seen,
    )

    first_inserted = store.write_risk_alert(first)
    second_inserted = store.write_risk_alert(second)

    alerts = _read_jsonl(tmp_path / "risk_alerts.jsonl")
    assert first_inserted is True
    assert second_inserted is False
    assert len(alerts) == 1
    assert alerts[0]["id"] == str(first.id)
    assert second.id == first.id
    assert alerts[0]["severity"] == "high"
    assert alerts[0]["status"] == "acknowledged"
    assert alerts[0]["title"] == "Updated recall risk"
    assert alerts[0]["body"] == "Updated body"
    assert alerts[0]["channels"] == ["dashboard", "email"]
    assert alerts[0]["payload"]["run"] == "second"
    assert alerts[0]["first_emitted_at"] == first_seen.isoformat().replace("+00:00", "Z")
    assert alerts[0]["last_emitted_at"] == second_seen.isoformat().replace("+00:00", "Z")


def test_local_risk_engine_replays_recall_extractions_idempotently(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/openfda_drug_enforcement.yaml"))
    settings = Settings(data_dir=tmp_path)
    ingest_openfda_drug_enforcement_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_enforcement/success.json"),
        settings=settings,
        max_documents=1,
    )
    _remove_inline_risk_outputs(tmp_path)

    first = run_local_risk_engine(tmp_path)
    second = run_local_risk_engine(tmp_path)

    assert first.extraction_runs_scanned == 1
    assert first.recall_events_seen == 1
    assert first.risk_candidates_created == 1
    assert first.risk_cases_created == 1
    assert first.risk_verdicts_created == 1
    assert first.risk_alerts_created == 1
    assert first.risk_feature_snapshots_created == EXPECTED_RISK_FEATURE_SNAPSHOTS
    assert first.events_emitted == EXPECTED_RISK_EVENTS
    assert second.risk_candidates_created == 0
    assert second.risk_candidates_existing == 1
    assert second.risk_cases_created == 0
    assert second.risk_cases_existing == 1
    assert second.risk_verdicts_created == 0
    assert second.risk_alerts_created == 0
    assert second.risk_feature_snapshots_created == 0
    assert second.events_emitted == 0

    candidates = _read_jsonl(tmp_path / "risk_candidates.jsonl")
    cases = _read_jsonl(tmp_path / "risk_cases.jsonl")
    verdicts = _read_jsonl(tmp_path / "risk_verdicts.jsonl")
    alerts = _read_jsonl(tmp_path / "risk_alerts.jsonl")
    feature_snapshots = _read_jsonl(tmp_path / "risk_feature_snapshots.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")
    assert len(candidates) == 1
    assert len(cases) == 1
    assert len(verdicts) == 1
    assert len(alerts) == 1
    assert len(feature_snapshots) == EXPECTED_RISK_FEATURE_SNAPSHOTS
    assert verdicts[0]["risk_case_id"] == cases[0]["id"]
    assert alerts[0]["risk_case_id"] == cases[0]["id"]
    assert [event["event_type"] for event in events if event["event_type"].startswith("risk.")] == [
        "risk.candidates",
        "risk.case_created",
        "risk.verdicts",
        "risk.alerts",
    ]
    assert candidates[0]["candidate_key"].startswith("risk_candidate:recall_quality:")
    assert candidates[0]["evidence_span_ids"] == verdicts[0]["evidence_span_ids"]


async def test_risk_engine_consumer_processes_extraction_completed_event(
    tmp_path: Path,
) -> None:
    config = load_source_config(Path("sources/openfda_drug_enforcement.yaml"))
    settings = Settings(data_dir=tmp_path)
    ingest_openfda_drug_enforcement_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_enforcement/success.json"),
        settings=settings,
        max_documents=1,
    )
    _remove_inline_risk_outputs(tmp_path)
    event = _extraction_completed_event_from_store(tmp_path)
    consumer = FakeConsumerClient([_fake_message(event)])
    producer = FakeProducerClient()

    summary = await run_risk_engine_consumer(
        settings=settings,
        max_messages=RISK_CONSUMER_MESSAGES,
        consumer_client=consumer,
        producer_client=producer,
    )

    assert summary.processed_messages == RISK_CONSUMER_MESSAGES
    assert summary.deadlettered_messages == 0
    assert summary.committed_messages == RISK_CONSUMER_MESSAGES
    assert consumer.commits == RISK_CONSUMER_MESSAGES
    assert [topic for topic, _, _, _ in producer.sent] == [
        "risk.candidates",
        "risk.case_created",
        "risk.verdicts",
        "risk.alerts",
    ]
    cases = _read_jsonl(tmp_path / "risk_cases.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")
    assert len(cases) == 1
    assert [event["event_type"] for event in events if event["event_type"].startswith("risk.")] == [
        "risk.candidates",
        "risk.case_created",
        "risk.verdicts",
        "risk.alerts",
    ]


async def test_risk_engine_consumer_deadletters_missing_extraction_run(
    tmp_path: Path,
) -> None:
    config = load_source_config(Path("sources/openfda_drug_enforcement.yaml"))
    settings = Settings(data_dir=tmp_path)
    ingest_openfda_drug_enforcement_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_enforcement/success.json"),
        settings=settings,
        max_documents=1,
    )
    _remove_inline_risk_outputs(tmp_path)
    event = _extraction_completed_event_from_store(tmp_path)
    event.payload["extraction_run_id"] = str(uuid4())
    consumer = FakeConsumerClient([_fake_message(event)])
    producer = FakeProducerClient()

    summary = await run_risk_engine_consumer(
        settings=settings,
        max_messages=RISK_CONSUMER_MESSAGES,
        consumer_client=consumer,
        producer_client=producer,
    )

    assert summary.processed_messages == 0
    assert summary.deadlettered_messages == RISK_CONSUMER_MESSAGES
    assert summary.committed_messages == RISK_CONSUMER_MESSAGES
    assert consumer.commits == RISK_CONSUMER_MESSAGES
    topic, value, key, headers = producer.sent[0]
    assert topic == "ingest.deadletter"
    assert key == b"extraction-run"
    deadletter = deserialize_event(value)
    assert deadletter.payload["error_type"] == "extraction_run_missing"
    assert deadletter.payload["original_topic"] == "ingest.extraction_completed"
    assert headers is not None


def test_run_risk_engine_cli_requires_consume_for_kafka_options() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["run-risk-engine", "--max-messages", "1"])

    assert result.exit_code != 0
    assert "--consume-kafka" in result.output


def test_local_risk_engine_handles_no_extractions(tmp_path: Path) -> None:
    summary = run_local_risk_engine(tmp_path)

    assert summary.extraction_runs_scanned == 0
    assert summary.risk_cases_created == 0
    assert summary.events_emitted == 0


def _remove_inline_risk_outputs(data_dir: Path) -> None:
    for name in [
        "risk_cases.jsonl",
        "risk_candidates.jsonl",
        "risk_verdicts.jsonl",
        "risk_alerts.jsonl",
        "risk_feature_snapshots.jsonl",
    ]:
        path = data_dir / name
        if path.exists():
            path.unlink()
    events_path = data_dir / "events.jsonl"
    events = [
        line
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if not json.loads(line)["event_type"].startswith("risk.")
    ]
    events_path.write_text("\n".join(events) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _extraction_completed_event_from_store(data_dir: Path) -> EventEnvelope:
    for row in _read_jsonl(data_dir / "events.jsonl"):
        if row["event_type"] == "ingest.extraction_completed":
            return EventEnvelope.model_validate(row)
    raise AssertionError("expected ingest.extraction_completed event")


def _fake_message(event: EventEnvelope) -> FakeMessage:
    return FakeMessage(
        topic="ingest.extraction_completed",
        key=b"extraction-run",
        value=serialize_event(event),
    )
