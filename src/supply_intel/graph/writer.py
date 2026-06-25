from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import Field

from supply_intel.db.postgres import PostgresConnection
from supply_intel.events.consumer import (
    EventConsumer,
    EventHandler,
    KafkaConsumerClient,
    PermanentEventError,
)
from supply_intel.events.kafka_clients import DirectKafkaConsumerClient, DirectKafkaProducerClient
from supply_intel.events.producer import EventProducer, KafkaProducerClient
from supply_intel.events.schemas import validate_event_payload
from supply_intel.graph.neo4j_client import (
    AsyncNeo4jClient,
    Neo4jStatementRunner,
    Neo4jWriteStatement,
    node_statement,
    relationship_statement,
)
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.graph import GraphNodeUpsert, GraphRelationshipUpsert
from supply_intel.models.kafka import (
    EventEnvelope,
    EventProcessingResult,
    GraphNodeUpsertPayload,
    GraphRelationshipUpsertPayload,
)
from supply_intel.settings import Settings

GRAPH_WRITER_GROUP = "platform-graph-writer"
GRAPH_WRITER_STAGE = "write-graph"
GRAPH_NODE_TOPIC = "graph.node_upsert"
GRAPH_RELATIONSHIP_TOPIC = "graph.relationship_upsert"
POSTGRES_GRAPH_REPLAY_SOURCE = "postgres:graph_upsert_audit"


class GraphReplayBatch(StrictBaseModel):
    node_upserts: list[GraphNodeUpsert]
    relationship_upserts: list[GraphRelationshipUpsert]


class GraphReplaySummary(StrictBaseModel):
    data_dir: str
    node_upserts: int
    relationship_upserts: int
    statements: int
    applied: bool
    results: list[dict[str, object]]


class GraphWriterRunSummary(StrictBaseModel):
    requested_messages: int | None = None
    processed_messages: int = Field(default=0, ge=0)
    deadlettered_messages: int = Field(default=0, ge=0)
    committed_messages: int = Field(default=0, ge=0)
    timed_out: bool = False
    results: list[EventProcessingResult] = Field(default_factory=list)

    @property
    def handled_messages(self) -> int:
        return self.processed_messages + self.deadlettered_messages


class GraphWriteError(RuntimeError):
    """Raised when Neo4j accepts a statement but does not upsert the requested graph item."""


class GraphUpsertWriter(Protocol):
    async def write_node(self, upsert: GraphNodeUpsert) -> dict[str, object]: ...

    async def write_relationship(self, upsert: GraphRelationshipUpsert) -> dict[str, object]: ...


@dataclass
class GraphWriterRuntime:
    consumer_client: KafkaConsumerClient
    producer_client: KafkaProducerClient
    writer: GraphUpsertWriter
    direct_consumer: DirectKafkaConsumerClient | None = None
    direct_producer: DirectKafkaProducerClient | None = None
    neo4j_client: AsyncNeo4jClient | None = None

    async def close(self) -> None:
        if self.neo4j_client is not None:
            await self.neo4j_client.close()
        if self.direct_consumer is not None:
            await self.direct_consumer.stop()
        if self.direct_producer is not None:
            await self.direct_producer.stop()


class Neo4jGraphWriter:
    def __init__(self, runner: Neo4jStatementRunner) -> None:
        self.runner = runner

    async def write_node(self, upsert: GraphNodeUpsert) -> dict[str, object]:
        result = await self.runner.run_statement(node_statement(upsert))
        _ensure_records_returned(result, item_key=upsert.graph_node_key, item_type="node")
        return result

    async def write_relationship(self, upsert: GraphRelationshipUpsert) -> dict[str, object]:
        result = await self.runner.run_statement(relationship_statement(upsert))
        _ensure_records_returned(
            result,
            item_key=upsert.relationship_key,
            item_type="relationship",
        )
        return result

    async def write_batch(self, batch: GraphReplayBatch) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for node in batch.node_upserts:
            results.append(await self.write_node(node))
        for relationship in batch.relationship_upserts:
            results.append(await self.write_relationship(relationship))
        return results

    async def replay_from_jsonl(self, data_dir: Path) -> GraphReplaySummary:
        batch = load_graph_replay_batch(data_dir)
        results = await self.write_batch(batch)
        return GraphReplaySummary(
            data_dir=str(data_dir),
            node_upserts=len(batch.node_upserts),
            relationship_upserts=len(batch.relationship_upserts),
            statements=len(results),
            applied=True,
            results=results,
        )

    async def replay_from_postgres_audit(
        self,
        connection: PostgresConnection,
        *,
        limit: int | None = None,
    ) -> GraphReplaySummary:
        batch = await load_graph_replay_batch_from_postgres(connection, limit=limit)
        results = await self.write_batch(batch)
        return GraphReplaySummary(
            data_dir=POSTGRES_GRAPH_REPLAY_SOURCE,
            node_upserts=len(batch.node_upserts),
            relationship_upserts=len(batch.relationship_upserts),
            statements=len(results),
            applied=True,
            results=results,
        )


async def execute_graph_upsert_event(
    *,
    writer: GraphUpsertWriter,
    event: EventEnvelope,
) -> dict[str, object]:
    event = validate_event_payload(event)
    if event.event_type == GRAPH_NODE_TOPIC:
        node_payload = GraphNodeUpsertPayload.model_validate(event.payload)
        node_upsert = GraphNodeUpsert.model_validate(node_payload.model_dump(mode="json"))
        result = await writer.write_node(node_upsert)
        return {"event_type": event.event_type, "graph_key": node_upsert.graph_node_key, **result}
    if event.event_type == GRAPH_RELATIONSHIP_TOPIC:
        relationship_payload = GraphRelationshipUpsertPayload.model_validate(event.payload)
        relationship_upsert = GraphRelationshipUpsert.model_validate(
            relationship_payload.model_dump(mode="json")
        )
        result = await writer.write_relationship(relationship_upsert)
        return {
            "event_type": event.event_type,
            "graph_key": relationship_upsert.relationship_key,
            **result,
        }
    raise PermanentEventError(
        f"Unsupported graph writer event type: {event.event_type}",
        error_type="unsupported_graph_event",
    )


async def run_graph_writer_once(
    *,
    settings: Settings,
    consumer_client: KafkaConsumerClient | None = None,
    producer_client: KafkaProducerClient | None = None,
    writer: GraphUpsertWriter | None = None,
) -> EventProcessingResult:
    summary = await run_graph_writer_consumer(
        settings=settings,
        max_messages=1,
        consumer_client=consumer_client,
        producer_client=producer_client,
        writer=writer,
    )
    if not summary.results:
        raise RuntimeError("Graph writer exited before processing a message.")
    return summary.results[0]


async def run_graph_writer_consumer(
    *,
    settings: Settings,
    max_messages: int | None = None,
    idle_timeout_seconds: float | None = None,
    consumer_client: KafkaConsumerClient | None = None,
    producer_client: KafkaProducerClient | None = None,
    writer: GraphUpsertWriter | None = None,
) -> GraphWriterRunSummary:
    if max_messages is not None and max_messages < 1:
        raise ValueError("max_messages must be greater than zero when provided.")

    runtime = await _start_graph_writer_runtime(
        settings=settings,
        consumer_client=consumer_client,
        producer_client=producer_client,
        writer=writer,
    )

    producer = EventProducer(runtime.producer_client)
    consumer = EventConsumer(
        runtime.consumer_client,
        producer,
        consumer_group=GRAPH_WRITER_GROUP,
        stage=GRAPH_WRITER_STAGE,
    )

    async def handler(received: EventEnvelope) -> None:
        try:
            await execute_graph_upsert_event(writer=runtime.writer, event=received)
        except GraphWriteError as exc:
            raise PermanentEventError(str(exc), error_type="graph_write_failed") from exc

    summary = GraphWriterRunSummary(requested_messages=max_messages)
    try:
        while max_messages is None or summary.handled_messages < max_messages:
            try:
                result = await _process_one_with_optional_timeout(
                    consumer,
                    handler,
                    idle_timeout_seconds=idle_timeout_seconds,
                )
            except TimeoutError:
                summary.timed_out = True
                break
            summary.results.append(result)
            if result.status == "processed":
                summary.processed_messages += 1
            if result.status == "deadlettered":
                summary.deadlettered_messages += 1
            if result.committed:
                summary.committed_messages += 1
        return summary
    finally:
        await runtime.close()


async def _start_graph_writer_runtime(
    *,
    settings: Settings,
    consumer_client: KafkaConsumerClient | None,
    producer_client: KafkaProducerClient | None,
    writer: GraphUpsertWriter | None,
) -> GraphWriterRuntime:
    direct_consumer: DirectKafkaConsumerClient | None = None
    direct_producer: DirectKafkaProducerClient | None = None
    neo4j_client: AsyncNeo4jClient | None = None
    selected_consumer = consumer_client
    selected_producer = producer_client
    selected_writer = writer
    if selected_consumer is None:
        direct_consumer = DirectKafkaConsumerClient(
            settings,
            topics=[GRAPH_NODE_TOPIC, GRAPH_RELATIONSHIP_TOPIC],
            group_id=GRAPH_WRITER_GROUP,
        )
        selected_consumer = direct_consumer
        await direct_consumer.start()
    if selected_producer is None:
        direct_producer = DirectKafkaProducerClient(settings)
        selected_producer = direct_producer
        await direct_producer.start()
    if selected_writer is None:
        neo4j_client = AsyncNeo4jClient(
            settings.neo4j_uri,
            settings.neo4j_username,
            settings.neo4j_password,
        )
        selected_writer = Neo4jGraphWriter(neo4j_client)
    return GraphWriterRuntime(
        consumer_client=selected_consumer,
        producer_client=selected_producer,
        writer=selected_writer,
        direct_consumer=direct_consumer,
        direct_producer=direct_producer,
        neo4j_client=neo4j_client,
    )


async def _process_one_with_optional_timeout(
    consumer: EventConsumer,
    handler: EventHandler,
    *,
    idle_timeout_seconds: float | None,
) -> EventProcessingResult:
    if idle_timeout_seconds is None:
        return await consumer.process_one(handler)
    return await asyncio.wait_for(consumer.process_one(handler), timeout=idle_timeout_seconds)


def load_graph_replay_batch(data_dir: Path) -> GraphReplayBatch:
    return GraphReplayBatch(
        node_upserts=[
            GraphNodeUpsert.model_validate(row)
            for row in _read_jsonl(data_dir / "graph_node_upserts.jsonl")
        ],
        relationship_upserts=[
            GraphRelationshipUpsert.model_validate(row)
            for row in _read_jsonl(data_dir / "graph_relationship_upserts.jsonl")
        ],
    )


async def load_graph_replay_batch_from_postgres(
    connection: PostgresConnection,
    *,
    limit: int | None = None,
) -> GraphReplayBatch:
    rows = await connection.fetch(
        """
        WITH ordered AS (
          SELECT
            upsert_type,
            payload,
            row_number() OVER (
              ORDER BY
                CASE WHEN upsert_type = 'node' THEN 0 ELSE 1 END,
                created_at ASC,
                graph_key ASC
            ) AS replay_order
          FROM graph_upsert_audit
          WHERE upsert_type IN ('node', 'relationship')
        )
        SELECT upsert_type, payload
        FROM ordered
        WHERE $1::int IS NULL OR replay_order <= $1
        ORDER BY replay_order ASC
        """,
        limit,
    )
    node_upserts: list[GraphNodeUpsert] = []
    relationship_upserts: list[GraphRelationshipUpsert] = []
    for row in sorted(rows, key=_postgres_graph_replay_sort_key):
        payload = _payload_dict(row["payload"])
        if row["upsert_type"] == "node":
            node_upserts.append(GraphNodeUpsert.model_validate(payload))
        elif row["upsert_type"] == "relationship":
            relationship_upserts.append(GraphRelationshipUpsert.model_validate(payload))
    return GraphReplayBatch(
        node_upserts=node_upserts,
        relationship_upserts=relationship_upserts,
    )


async def summarize_graph_replay_from_postgres(
    connection: PostgresConnection,
    *,
    limit: int | None = None,
) -> GraphReplaySummary:
    batch = await load_graph_replay_batch_from_postgres(connection, limit=limit)
    return GraphReplaySummary(
        data_dir=POSTGRES_GRAPH_REPLAY_SOURCE,
        node_upserts=len(batch.node_upserts),
        relationship_upserts=len(batch.relationship_upserts),
        statements=len(batch.node_upserts) + len(batch.relationship_upserts),
        applied=False,
        results=[],
    )


def build_graph_replay_statements(data_dir: Path) -> list[Neo4jWriteStatement]:
    batch = load_graph_replay_batch(data_dir)
    return [
        *(node_statement(upsert) for upsert in batch.node_upserts),
        *(relationship_statement(upsert) for upsert in batch.relationship_upserts),
    ]


def summarize_graph_replay(data_dir: Path, *, applied: bool = False) -> GraphReplaySummary:
    batch = load_graph_replay_batch(data_dir)
    return GraphReplaySummary(
        data_dir=str(data_dir),
        node_upserts=len(batch.node_upserts),
        relationship_upserts=len(batch.relationship_upserts),
        statements=len(batch.node_upserts) + len(batch.relationship_upserts),
        applied=applied,
        results=[],
    )


def _ensure_records_returned(
    result: dict[str, object],
    *,
    item_key: str,
    item_type: str,
) -> None:
    record_count = result.get("record_count")
    if record_count == 0:
        raise GraphWriteError(
            f"Neo4j {item_type} upsert returned no rows for {item_key}; "
            "a relationship endpoint or node key is missing."
        )


def _postgres_graph_replay_sort_key(row: dict[str, object]) -> tuple[int, str]:
    upsert_type = str(row.get("upsert_type", ""))
    payload = _payload_dict(row.get("payload"))
    if upsert_type == "node":
        return (0, str(payload.get("graph_node_key", "")))
    return (1, str(payload.get("relationship_key", "")))


def _payload_dict(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str):
        decoded = json.loads(value)
        if isinstance(decoded, dict):
            return {str(key): item for key, item in decoded.items()}
    raise ValueError("PostgreSQL graph_upsert_audit payload must be a JSON object")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
