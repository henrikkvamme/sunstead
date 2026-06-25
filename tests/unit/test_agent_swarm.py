import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.events.envelope import deserialize_event, serialize_event
from supply_intel.models.kafka import EventEnvelope
from supply_intel.pipeline import ingest_openfda_drug_enforcement_fixture
from supply_intel.risk.swarm import run_agent_swarm_consumer, run_local_agent_swarm
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config

EXPECTED_AGENT_FINDINGS = 3
EXPECTED_SWARM_EVENTS = 5
EXPECTED_TOTAL_RISK_VERDICTS = 2
SWARM_CONSUMER_MESSAGES = 1


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


def test_local_agent_swarm_creates_evidence_graph_and_critic_findings(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/openfda_drug_enforcement.yaml"))
    settings = Settings(data_dir=tmp_path)
    ingest_openfda_drug_enforcement_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_enforcement/success.json"),
        settings=settings,
        max_documents=1,
    )
    case = _read_jsonl(tmp_path / "risk_cases.jsonl")[0]

    summary = run_local_agent_swarm(tmp_path, str(case["case_key"]))

    assert summary.status == "completed"
    assert summary.findings_created == EXPECTED_AGENT_FINDINGS
    assert summary.verdicts_created == 1
    assert len(summary.event_ids) == EXPECTED_SWARM_EVENTS
    assert summary.agent_names == [
        "EvidenceVerifierAgent",
        "GraphBlastRadiusAgent",
        "CriticAgent",
        "VerdictAgent",
    ]

    findings = _read_jsonl(tmp_path / "agent_findings.jsonl")
    assert [row["agent_name"] for row in findings] == [
        "EvidenceVerifierAgent",
        "GraphBlastRadiusAgent",
        "CriticAgent",
    ]
    verifier = findings[0]["finding"]
    critic = findings[2]["finding"]
    assert verifier["status"] == "supported"
    assert verifier["supported_spans"]
    assert critic["decision"] == "approve"
    assert {row["model_name"] for row in findings} == {"deterministic-local"}
    assert {row["input_hash"] for row in findings}
    assert [row["output_schema"] for row in findings] == [
        "EvidenceVerificationOutput",
        "BlastRadiusOutput",
        "CriticOutput",
    ]

    events = _read_jsonl(tmp_path / "events.jsonl")
    event_types = [event["event_type"] for event in events]
    assert event_types.count("risk.agent_findings") == EXPECTED_AGENT_FINDINGS
    assert event_types.count("risk.verdicts") == EXPECTED_TOTAL_RISK_VERDICTS
    assert event_types.count("agents.audit_log") == 1
    finding_events = [event for event in events if event["event_type"] == "risk.agent_findings"]
    assert {event["payload"]["model_name"] for event in finding_events} == {"deterministic-local"}
    assert all(event["payload"]["prompt_hash"] for event in finding_events)
    assert all(event["payload"]["input_hash"] for event in finding_events)
    audit = next(event for event in events if event["event_type"] == "agents.audit_log")
    assert audit["payload"]["agent_names"] == summary.agent_names

    verdicts = _read_jsonl(tmp_path / "risk_verdicts.jsonl")
    agent_verdicts = [
        row
        for row in verdicts
        if row["metadata"].get("verdict_key") == f"verdict-agent:{case['case_key']}"
    ]
    assert len(agent_verdicts) == 1
    assert agent_verdicts[0]["metadata"]["agent_name"] == "VerdictAgent"


async def test_agent_swarm_consumer_processes_risk_case_created_event(
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
    event = _risk_case_created_event_from_store(tmp_path)
    consumer = FakeConsumerClient([_fake_message(event)])
    producer = FakeProducerClient()

    summary = await run_agent_swarm_consumer(
        settings=settings,
        max_messages=SWARM_CONSUMER_MESSAGES,
        consumer_client=consumer,
        producer_client=producer,
    )

    assert summary.processed_messages == SWARM_CONSUMER_MESSAGES
    assert summary.deadlettered_messages == 0
    assert summary.committed_messages == SWARM_CONSUMER_MESSAGES
    assert consumer.commits == SWARM_CONSUMER_MESSAGES
    assert [topic for topic, _, _, _ in producer.sent] == [
        "risk.agent_findings",
        "risk.agent_findings",
        "risk.agent_findings",
        "risk.verdicts",
        "agents.audit_log",
    ]
    findings = _read_jsonl(tmp_path / "agent_findings.jsonl")
    assert [row["agent_name"] for row in findings] == [
        "EvidenceVerifierAgent",
        "GraphBlastRadiusAgent",
        "CriticAgent",
    ]
    audit = deserialize_event(producer.sent[-1][1])
    assert audit.payload["agent_names"] == [
        "EvidenceVerifierAgent",
        "GraphBlastRadiusAgent",
        "CriticAgent",
        "VerdictAgent",
    ]


def test_local_agent_swarm_is_idempotent_for_findings_verdict_and_events(
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
    case = _read_jsonl(tmp_path / "risk_cases.jsonl")[0]

    first = run_local_agent_swarm(tmp_path, str(case["case_key"]))
    second = run_local_agent_swarm(tmp_path, str(case["case_key"]))

    assert first.findings_created == EXPECTED_AGENT_FINDINGS
    assert first.verdicts_created == 1
    assert len(first.event_ids) == EXPECTED_SWARM_EVENTS
    assert second.findings_created == 0
    assert second.verdicts_created == 0
    assert second.event_ids == []

    findings = _read_jsonl(tmp_path / "agent_findings.jsonl")
    assert len(findings) == EXPECTED_AGENT_FINDINGS
    verdicts = _read_jsonl(tmp_path / "risk_verdicts.jsonl")
    verdict_keys = [
        row["metadata"].get("verdict_key")
        for row in verdicts
        if row["metadata"].get("agent_name") == "VerdictAgent"
    ]
    assert verdict_keys == [f"verdict-agent:{case['case_key']}"]


async def test_agent_swarm_consumer_deadletters_missing_risk_case(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/openfda_drug_enforcement.yaml"))
    settings = Settings(data_dir=tmp_path)
    ingest_openfda_drug_enforcement_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_enforcement/success.json"),
        settings=settings,
        max_documents=1,
    )
    event = _risk_case_created_event_from_store(tmp_path)
    event.payload["risk_case_id"] = str(uuid4())
    event.payload["case_key"] = "risk:missing"
    consumer = FakeConsumerClient([_fake_message(event)])
    producer = FakeProducerClient()

    summary = await run_agent_swarm_consumer(
        settings=settings,
        max_messages=SWARM_CONSUMER_MESSAGES,
        consumer_client=consumer,
        producer_client=producer,
    )

    assert summary.processed_messages == 0
    assert summary.deadlettered_messages == SWARM_CONSUMER_MESSAGES
    assert summary.committed_messages == SWARM_CONSUMER_MESSAGES
    assert consumer.commits == SWARM_CONSUMER_MESSAGES
    topic, value, key, headers = producer.sent[0]
    assert topic == "ops.errors"
    assert key == b"risk-case"
    deadletter = deserialize_event(value)
    assert deadletter.payload["error_type"] == "risk_case_missing"
    assert deadletter.payload["original_topic"] == "risk.case_created"
    assert headers is not None


def test_run_agent_swarm_cli_requires_consume_for_kafka_options() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["run-agent-swarm", "--max-messages", "1"])

    assert result.exit_code != 0
    assert "--consume-kafka" in result.output


def test_local_agent_swarm_reports_missing_case(tmp_path: Path) -> None:
    summary = run_local_agent_swarm(tmp_path, "risk:missing")

    assert summary.status == "case_not_found"
    assert summary.findings_created == 0
    assert not (tmp_path / "agent_findings.jsonl").exists()


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _risk_case_created_event_from_store(data_dir: Path) -> EventEnvelope:
    for row in _read_jsonl(data_dir / "events.jsonl"):
        if row["event_type"] == "risk.case_created":
            return EventEnvelope.model_validate(row)
    raise AssertionError("expected risk.case_created event")


def _fake_message(event: EventEnvelope) -> FakeMessage:
    return FakeMessage(
        topic="risk.case_created",
        key=b"risk-case",
        value=serialize_event(event),
    )
