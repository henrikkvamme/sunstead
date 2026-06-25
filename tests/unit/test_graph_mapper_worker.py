import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.events.envelope import deserialize_event, serialize_event
from supply_intel.graph.mapper_worker import execute_graph_mapping_event, run_graph_mapper_consumer
from supply_intel.models.kafka import EventEnvelope
from supply_intel.pipeline import ingest_openfda_ndc_fixture
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config

EXPECTED_NDC_GRAPH_NODES = 4
EXPECTED_NDC_GRAPH_RELATIONSHIPS = 3
GRAPH_MAPPER_CONSUMER_MESSAGES = 1


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


async def test_graph_mapper_consumer_maps_extraction_and_publishes_graph_events(
    tmp_path: Path,
) -> None:
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    settings = Settings(data_dir=tmp_path)
    ingest_openfda_ndc_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_ndc/success.json"),
        settings=settings,
        max_documents=1,
    )
    _remove_graph_outputs(tmp_path)
    event = _extraction_completed_event_from_store(tmp_path)
    consumer = FakeConsumerClient([_fake_message(event)])
    producer = FakeProducerClient()

    summary = await run_graph_mapper_consumer(
        settings=settings,
        max_messages=GRAPH_MAPPER_CONSUMER_MESSAGES,
        consumer_client=consumer,
        producer_client=producer,
    )

    assert summary.processed_messages == GRAPH_MAPPER_CONSUMER_MESSAGES
    assert summary.deadlettered_messages == 0
    assert summary.committed_messages == GRAPH_MAPPER_CONSUMER_MESSAGES
    assert consumer.commits == GRAPH_MAPPER_CONSUMER_MESSAGES

    nodes = _read_jsonl(tmp_path / "graph_node_upserts.jsonl")
    relationships = _read_jsonl(tmp_path / "graph_relationship_upserts.jsonl")
    assert len(nodes) == EXPECTED_NDC_GRAPH_NODES
    assert len(relationships) == EXPECTED_NDC_GRAPH_RELATIONSHIPS

    topics = [topic for topic, _, _, _ in producer.sent]
    assert topics.count("graph.node_upsert") == EXPECTED_NDC_GRAPH_NODES
    assert topics.count("graph.relationship_upsert") == EXPECTED_NDC_GRAPH_RELATIONSHIPS
    first_graph_event = deserialize_event(producer.sent[0][1])
    assert first_graph_event.correlation_id == event.correlation_id
    assert first_graph_event.causation_id == event.event_id
    assert first_graph_event.trace.raw_document_id == event.trace.raw_document_id

    graph_events = [
        row["event_type"]
        for row in _read_jsonl(tmp_path / "events.jsonl")
        if row["event_type"].startswith("graph.")
    ]
    assert graph_events.count("graph.node_upsert") == EXPECTED_NDC_GRAPH_NODES
    assert graph_events.count("graph.relationship_upsert") == EXPECTED_NDC_GRAPH_RELATIONSHIPS


async def test_graph_mapper_consumer_deadletters_missing_extraction_run(
    tmp_path: Path,
) -> None:
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    settings = Settings(data_dir=tmp_path)
    ingest_openfda_ndc_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_ndc/success.json"),
        settings=settings,
        max_documents=1,
    )
    _remove_graph_outputs(tmp_path)
    event = _extraction_completed_event_from_store(tmp_path)
    event.payload["extraction_run_id"] = str(uuid4())
    consumer = FakeConsumerClient([_fake_message(event)])
    producer = FakeProducerClient()

    summary = await run_graph_mapper_consumer(
        settings=settings,
        max_messages=GRAPH_MAPPER_CONSUMER_MESSAGES,
        consumer_client=consumer,
        producer_client=producer,
    )

    assert summary.processed_messages == 0
    assert summary.deadlettered_messages == GRAPH_MAPPER_CONSUMER_MESSAGES
    assert summary.committed_messages == GRAPH_MAPPER_CONSUMER_MESSAGES
    assert consumer.commits == GRAPH_MAPPER_CONSUMER_MESSAGES
    topic, value, key, headers = producer.sent[0]
    assert topic == "ingest.deadletter"
    assert key == b"extraction-run"
    deadletter = deserialize_event(value)
    assert deadletter.payload["error_type"] == "extraction_run_missing"
    assert deadletter.payload["original_topic"] == "ingest.extraction_completed"
    assert headers is not None


async def test_graph_mapper_event_processing_is_idempotent_locally(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    settings = Settings(data_dir=tmp_path)
    ingest_openfda_ndc_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_ndc/success.json"),
        settings=settings,
        max_documents=1,
    )
    _remove_graph_outputs(tmp_path)
    event = _extraction_completed_event_from_store(tmp_path)

    first = await execute_graph_mapping_event(settings=settings, event=event)
    second = await execute_graph_mapping_event(settings=settings, event=event)

    assert first.node_upserts_created == EXPECTED_NDC_GRAPH_NODES
    assert first.relationship_upserts_created == EXPECTED_NDC_GRAPH_RELATIONSHIPS
    assert first.events_emitted == EXPECTED_NDC_GRAPH_NODES + EXPECTED_NDC_GRAPH_RELATIONSHIPS
    assert second.node_upserts_existing == EXPECTED_NDC_GRAPH_NODES
    assert second.relationship_upserts_existing == EXPECTED_NDC_GRAPH_RELATIONSHIPS
    assert second.events_emitted == 0
    assert len(_read_jsonl(tmp_path / "graph_node_upserts.jsonl")) == EXPECTED_NDC_GRAPH_NODES
    assert (
        len(_read_jsonl(tmp_path / "graph_relationship_upserts.jsonl"))
        == EXPECTED_NDC_GRAPH_RELATIONSHIPS
    )


def test_run_graph_mapper_cli_requires_consume_kafka() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["run-graph-mapper"])

    assert result.exit_code != 0
    assert "--consume-kafka" in result.output


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


def _remove_graph_outputs(data_dir: Path) -> None:
    for filename in ["graph_node_upserts.jsonl", "graph_relationship_upserts.jsonl"]:
        path = data_dir / filename
        if path.exists():
            path.unlink()
    events_path = data_dir / "events.jsonl"
    events = [
        line
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if not json.loads(line)["event_type"].startswith("graph.")
    ]
    events_path.write_text("\n".join(events) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
