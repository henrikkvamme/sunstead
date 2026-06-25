import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from supply_intel.cli import _graph_replay_cli_payload, app
from supply_intel.events.envelope import build_event, deserialize_event, serialize_event
from supply_intel.graph.neo4j_client import (
    Neo4jWriteStatement,
    apply_cypher_migrations,
    node_statement,
    relationship_statement,
)
from supply_intel.graph.writer import (
    GraphWriteError,
    Neo4jGraphWriter,
    load_graph_replay_batch,
    load_graph_replay_batch_from_postgres,
    run_graph_writer_consumer,
    summarize_graph_replay,
    summarize_graph_replay_from_postgres,
)
from supply_intel.models.graph import (
    GraphNodeUpsert,
    GraphRelationshipUpsert,
    RelationshipProvenance,
)
from supply_intel.models.kafka import GraphNodeUpsertPayload, GraphRelationshipUpsertPayload
from supply_intel.settings import Settings

EXPECTED_CYPHER_STATEMENTS = 2
EXPECTED_REPLAY_PROPERTIES_SET = 10
EXPECTED_REPLAY_RECORDS_RETURNED = 2
EXPECTED_REPLAY_RESULT_COUNT = 2
GRAPH_CLI_MAX_MESSAGES = 2


class FakeGraphAuditConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.fetches: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.fetches.append((query, args))
        return self.rows


class FakeStatementRunner:
    def __init__(self) -> None:
        self.statements: list[Neo4jWriteStatement] = []

    async def run_statement(self, statement: Neo4jWriteStatement) -> dict[str, object]:
        self.statements.append(statement)
        return {"ok": True, "cypher": statement.cypher}


class MissingRelationshipEndpointRunner:
    async def run_statement(self, statement: Neo4jWriteStatement) -> dict[str, object]:
        del statement
        return {"record_count": 0, "records": []}


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


class FakeGraphWriter:
    def __init__(self, *, fail_relationship: bool = False) -> None:
        self.fail_relationship = fail_relationship
        self.nodes: list[GraphNodeUpsert] = []
        self.relationships: list[GraphRelationshipUpsert] = []

    async def write_node(self, upsert: GraphNodeUpsert) -> dict[str, object]:
        self.nodes.append(upsert)
        return {"record_count": 1, "records": [{"key": upsert.graph_node_key}]}

    async def write_relationship(self, upsert: GraphRelationshipUpsert) -> dict[str, object]:
        if self.fail_relationship:
            raise GraphWriteError("missing endpoint")
        self.relationships.append(upsert)
        return {"record_count": 1, "records": [{"key": upsert.relationship_key}]}


class FakeCypherRunner:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def run_cypher(self, cypher: str) -> dict[str, object]:
        self.statements.append(cypher)
        return {"ok": True}


def test_node_statement_preserves_queryable_provenance_and_json_metadata() -> None:
    source_document_id = uuid4()
    evidence_span_id = uuid4()
    upsert = GraphNodeUpsert(
        graph_node_key="Drug:ndc_product:0002-8215",
        labels=["Drug"],
        properties={
            "name": "Example drug",
            "external_ids": {"ndc_product": "0002-8215"},
            "confidence": 0.94,
        },
        source_document_id=source_document_id,
        evidence_span_id=evidence_span_id,
        confidence=0.94,
    )

    statement = node_statement(upsert)

    assert "MERGE (n:Drug {key: $key})" in statement.cypher
    properties = statement.parameters["properties"]
    assert isinstance(properties, dict)
    assert properties["source_document_id"] == str(source_document_id)
    assert properties["evidence_span_id"] == str(evidence_span_id)
    assert properties["labels"] == ["Drug"]
    assert json.loads(str(properties["external_ids"])) == {"ndc_product": "0002-8215"}


def test_relationship_statement_keeps_provenance_properties() -> None:
    source_document_id = uuid4()
    evidence_span_id = uuid4()
    extraction_run_id = uuid4()
    upsert = GraphRelationshipUpsert(
        relationship_key="Drug:1|HAS_NDC|NDC:1",
        from_key="Drug:1",
        to_key="NDC:1",
        relationship_type="HAS_NDC",
        properties=RelationshipProvenance(
            confidence=0.91,
            source_document_id=source_document_id,
            evidence_span_id=evidence_span_id,
            extraction_run_id=extraction_run_id,
            source_name="openfda_drug_ndc",
            source_url="https://api.fda.gov/drug/ndc.json",
            method="deterministic_openfda_ndc_v1",
        ),
    )

    statement = relationship_statement(upsert)

    assert "MERGE (a)-[r:HAS_NDC {relationship_key: $relationship_key}]->(b)" in statement.cypher
    properties = statement.parameters["properties"]
    assert isinstance(properties, dict)
    assert properties["relationship_key"] == "Drug:1|HAS_NDC|NDC:1"
    assert properties["source_document_id"] == str(source_document_id)
    assert properties["evidence_span_id"] == str(evidence_span_id)
    assert properties["extraction_run_id"] == str(extraction_run_id)


async def test_graph_writer_replays_nodes_before_relationships(tmp_path: Path) -> None:
    node = GraphNodeUpsert(
        graph_node_key="Drug:1",
        labels=["Drug"],
        properties={"name": "Example drug"},
    )
    relationship = GraphRelationshipUpsert(
        relationship_key="Drug:1|HAS_NDC|NDC:1",
        from_key="Drug:1",
        to_key="NDC:1",
        relationship_type="HAS_NDC",
        properties=RelationshipProvenance(
            confidence=0.8,
            source_document_id=uuid4(),
            source_name="fixture",
            method="test",
        ),
    )
    (tmp_path / "graph_node_upserts.jsonl").write_text(
        node.model_dump_json() + "\n",
        encoding="utf-8",
    )
    (tmp_path / "graph_relationship_upserts.jsonl").write_text(
        relationship.model_dump_json() + "\n",
        encoding="utf-8",
    )
    runner = FakeStatementRunner()
    writer = Neo4jGraphWriter(runner)

    summary = await writer.replay_from_jsonl(tmp_path)

    assert summary.applied is True
    assert summary.node_upserts == 1
    assert summary.relationship_upserts == 1
    assert runner.statements[0].cypher.startswith("MERGE (n:Drug")
    assert "MERGE (a)-[r:HAS_NDC" in runner.statements[1].cypher


async def test_graph_writer_rejects_relationship_write_with_missing_endpoints() -> None:
    relationship = GraphRelationshipUpsert(
        relationship_key="Drug:missing|HAS_NDC|NDC:missing",
        from_key="Drug:missing",
        to_key="NDC:missing",
        relationship_type="HAS_NDC",
        properties=RelationshipProvenance(
            confidence=0.8,
            source_document_id=uuid4(),
            source_name="fixture",
            method="test",
        ),
    )
    writer = Neo4jGraphWriter(MissingRelationshipEndpointRunner())

    with pytest.raises(GraphWriteError, match="returned no rows"):
        await writer.write_relationship(relationship)


async def test_graph_writer_consumer_writes_node_event_and_commits(tmp_path: Path) -> None:
    payload = GraphNodeUpsertPayload(
        graph_node_key="Drug:1",
        labels=["Drug"],
        properties={"name": "Example drug"},
        confidence=0.95,
    )
    event = build_event(
        event_type="graph.node_upsert",
        service="graph-mapper",
        payload=payload.model_dump(mode="json"),
        idempotency_key="graph.node_upsert:Drug:1",
    )
    consumer = FakeConsumerClient(
        [FakeMessage("graph.node_upsert", b"Drug:1", serialize_event(event))]
    )
    producer = FakeProducerClient()
    writer = FakeGraphWriter()

    summary = await run_graph_writer_consumer(
        settings=Settings(data_dir=tmp_path),
        max_messages=1,
        consumer_client=consumer,
        producer_client=producer,
        writer=writer,
    )

    assert summary.processed_messages == 1
    assert summary.deadlettered_messages == 0
    assert summary.committed_messages == 1
    assert consumer.commits == 1
    assert writer.nodes[0].graph_node_key == "Drug:1"
    assert producer.sent == []


async def test_graph_writer_consumer_deadletters_permanent_graph_write_failure(
    tmp_path: Path,
) -> None:
    payload = GraphRelationshipUpsertPayload(
        relationship_key="Drug:missing|HAS_NDC|NDC:missing",
        from_key="Drug:missing",
        to_key="NDC:missing",
        relationship_type="HAS_NDC",
        properties=RelationshipProvenance(
            confidence=0.8,
            source_document_id=uuid4(),
            source_name="fixture",
            method="test",
        ).model_dump(mode="json"),
    )
    event = build_event(
        event_type="graph.relationship_upsert",
        service="graph-mapper",
        payload=payload.model_dump(mode="json"),
        idempotency_key="graph.relationship_upsert:missing",
    )
    consumer = FakeConsumerClient(
        [FakeMessage("graph.relationship_upsert", b"missing", serialize_event(event))]
    )
    producer = FakeProducerClient()

    summary = await run_graph_writer_consumer(
        settings=Settings(data_dir=tmp_path),
        max_messages=1,
        consumer_client=consumer,
        producer_client=producer,
        writer=FakeGraphWriter(fail_relationship=True),
    )

    assert summary.processed_messages == 0
    assert summary.deadlettered_messages == 1
    assert summary.committed_messages == 1
    assert consumer.commits == 1
    topic, value, key, headers = producer.sent[0]
    assert topic == "graph.deadletter"
    assert key == b"missing"
    deadletter = deserialize_event(value)
    assert deadletter.payload["error_type"] == "graph_write_failed"
    assert deadletter.payload["original_topic"] == "graph.relationship_upsert"
    assert headers is not None


async def test_postgres_graph_replay_loader_validates_audit_payloads() -> None:
    source_document_id = uuid4()
    node = GraphNodeUpsert(
        graph_node_key="Drug:1",
        labels=["Drug"],
        properties={"name": "Example drug"},
    )
    relationship = GraphRelationshipUpsert(
        relationship_key="Drug:1|HAS_NDC|NDC:1",
        from_key="Drug:1",
        to_key="NDC:1",
        relationship_type="HAS_NDC",
        properties=RelationshipProvenance(
            confidence=0.9,
            source_document_id=source_document_id,
            source_name="postgres-audit",
            method="test",
        ),
    )
    connection = FakeGraphAuditConnection(
        [
            {
                "upsert_type": "relationship",
                "payload": relationship.model_dump(mode="json"),
            },
            {
                "upsert_type": "node",
                "payload": node.model_dump_json(),
            },
        ]
    )

    batch = await load_graph_replay_batch_from_postgres(connection, limit=GRAPH_CLI_MAX_MESSAGES)
    summary = await summarize_graph_replay_from_postgres(
        connection,
        limit=GRAPH_CLI_MAX_MESSAGES,
    )

    assert batch.node_upserts == [node]
    assert batch.relationship_upserts == [relationship]
    assert summary.data_dir == "postgres:graph_upsert_audit"
    assert summary.node_upserts == 1
    assert summary.relationship_upserts == 1
    assert summary.applied is False
    assert "FROM graph_upsert_audit" in connection.fetches[0][0]
    assert connection.fetches[0][1] == (GRAPH_CLI_MAX_MESSAGES,)


async def test_graph_writer_replays_from_postgres_audit() -> None:
    node = GraphNodeUpsert(
        graph_node_key="Drug:1",
        labels=["Drug"],
        properties={"name": "Example drug"},
    )
    connection = FakeGraphAuditConnection(
        [{"upsert_type": "node", "payload": node.model_dump(mode="json")}]
    )
    runner = FakeStatementRunner()
    writer = Neo4jGraphWriter(runner)

    summary = await writer.replay_from_postgres_audit(connection)

    assert summary.applied is True
    assert summary.data_dir == "postgres:graph_upsert_audit"
    assert summary.node_upserts == 1
    assert summary.relationship_upserts == 0
    assert runner.statements[0].parameters["key"] == "Drug:1"


def test_run_graph_writer_cli_requires_consume_for_kafka_options() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["run-graph-writer", "--max-messages", str(GRAPH_CLI_MAX_MESSAGES)],
    )

    assert result.exit_code != 0
    assert "--consume-kafka" in result.output


def test_run_graph_writer_cli_rejects_file_data_dir_with_postgres_source() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["run-graph-writer", "--source", "postgres", "--data-dir", "/tmp/graph"],
    )

    assert result.exit_code != 0
    assert "--data-dir is only valid with --source file" in result.output


def test_run_graph_writer_cli_rejects_summary_only_with_kafka_consumer() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["run-graph-writer", "--consume-kafka", "--summary-only"],
    )

    assert result.exit_code != 0
    assert "--summary-only" in result.output


def test_graph_replay_cli_payload_can_omit_statement_results() -> None:
    payload = {
        "data_dir": "postgres:graph_upsert_audit",
        "node_upserts": 2,
        "relationship_upserts": 1,
        "statements": 3,
        "applied": True,
        "results": [
            {
                "nodes_created": 1,
                "relationships_created": 0,
                "properties_set": 4,
                "record_count": 1,
            },
            {
                "nodes_created": 0,
                "relationships_created": 1,
                "properties_set": 6,
                "record_count": 1,
            },
        ],
    }

    summarized = _graph_replay_cli_payload(payload, summary_only=True)

    assert "results" not in summarized
    assert summarized["result_count"] == EXPECTED_REPLAY_RESULT_COUNT
    assert summarized["nodes_created"] == 1
    assert summarized["relationships_created"] == 1
    assert summarized["properties_set"] == EXPECTED_REPLAY_PROPERTIES_SET
    assert summarized["records_returned"] == EXPECTED_REPLAY_RECORDS_RETURNED


def test_graph_replay_summary_loads_missing_files_as_empty(tmp_path: Path) -> None:
    batch = load_graph_replay_batch(tmp_path)
    summary = summarize_graph_replay(tmp_path)

    assert batch.node_upserts == []
    assert batch.relationship_upserts == []
    assert summary.statements == 0
    assert summary.applied is False


async def test_apply_cypher_migrations_runs_each_statement(tmp_path: Path) -> None:
    (tmp_path / "0001_test.cypher").write_text(
        "CREATE CONSTRAINT example IF NOT EXISTS FOR (n:Drug) REQUIRE n.key IS UNIQUE;\n"
        "CREATE INDEX example_name IF NOT EXISTS FOR (n:Drug) ON (n.name);\n",
        encoding="utf-8",
    )
    runner = FakeCypherRunner()

    results = await apply_cypher_migrations(runner, tmp_path)

    assert len(results) == 1
    assert results[0].statements == EXPECTED_CYPHER_STATEMENTS
    assert runner.statements == [
        "CREATE CONSTRAINT example IF NOT EXISTS FOR (n:Drug) REQUIRE n.key IS UNIQUE",
        "CREATE INDEX example_name IF NOT EXISTS FOR (n:Drug) ON (n.name)",
    ]
