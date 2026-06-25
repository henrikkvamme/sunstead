from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from pydantic import Field

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.events.consumer import (
    EventConsumer,
    EventHandler,
    KafkaConsumerClient,
    PermanentEventError,
)
from supply_intel.events.envelope import build_event
from supply_intel.events.kafka_clients import DirectKafkaConsumerClient, DirectKafkaProducerClient
from supply_intel.events.producer import EventProducer, KafkaProducerClient
from supply_intel.events.schemas import validate_event_payload
from supply_intel.graph.mapper import map_extraction_to_graph
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.extraction import MedicalExtractionOutput
from supply_intel.models.graph import GraphMappingOutput, GraphNodeUpsert, GraphRelationshipUpsert
from supply_intel.models.kafka import (
    EventEnvelope,
    EventProcessingResult,
    ExtractionCompletedPayload,
    GraphNodeUpsertPayload,
    GraphRelationshipUpsertPayload,
)
from supply_intel.models.source import RawDocument
from supply_intel.settings import Settings

GRAPH_MAPPER_GROUP = "platform-graph-mapper"
GRAPH_MAPPER_STAGE = "map-graph"
EXTRACTION_COMPLETED_TOPIC = "ingest.extraction_completed"
GRAPH_NODE_TOPIC = "graph.node_upsert"
GRAPH_RELATIONSHIP_TOPIC = "graph.relationship_upsert"
SUPPORTED_EXTRACTION_SCHEMA = "MedicalExtractionOutput"


class GraphMapperSummary(StrictBaseModel):
    data_dir: str
    extraction_runs_scanned: int = Field(default=0, ge=0)
    node_upserts_created: int = Field(default=0, ge=0)
    node_upserts_existing: int = Field(default=0, ge=0)
    relationship_upserts_created: int = Field(default=0, ge=0)
    relationship_upserts_existing: int = Field(default=0, ge=0)
    events_emitted: int = Field(default=0, ge=0)
    kafka_events_published: int = Field(default=0, ge=0)
    skipped_items: list[str] = Field(default_factory=list)
    graph_node_keys: list[str] = Field(default_factory=list)
    graph_relationship_keys: list[str] = Field(default_factory=list)


class GraphMapperWorkerRunSummary(StrictBaseModel):
    requested_messages: int | None = None
    processed_messages: int = Field(default=0, ge=0)
    deadlettered_messages: int = Field(default=0, ge=0)
    committed_messages: int = Field(default=0, ge=0)
    timed_out: bool = False
    results: list[EventProcessingResult] = Field(default_factory=list)

    @property
    def handled_messages(self) -> int:
        return self.processed_messages + self.deadlettered_messages


@dataclass
class GraphMapperRuntime:
    consumer_client: KafkaConsumerClient
    producer_client: KafkaProducerClient
    direct_consumer: DirectKafkaConsumerClient | None = None
    direct_producer: DirectKafkaProducerClient | None = None

    async def close(self) -> None:
        if self.direct_consumer is not None:
            await self.direct_consumer.stop()
        if self.direct_producer is not None:
            await self.direct_producer.stop()


async def execute_graph_mapping_event(
    *,
    settings: Settings,
    event: EventEnvelope,
    producer: EventProducer | None = None,
) -> GraphMapperSummary:
    event = validate_event_payload(event)
    if event.event_type != EXTRACTION_COMPLETED_TOPIC:
        raise PermanentEventError(
            f"Unsupported graph mapper event type: {event.event_type}",
            error_type="unsupported_graph_mapper_event",
        )

    payload = ExtractionCompletedPayload.model_validate(event.payload)
    summary = _new_summary(settings.data_dir)
    if payload.status != "succeeded" or payload.output_schema != SUPPORTED_EXTRACTION_SCHEMA:
        return summary

    store = FileEvidenceStore(settings.data_dir)
    row = _extraction_run_row_by_id(store, payload.extraction_run_id)
    if row is None:
        raise PermanentEventError(
            f"Extraction run for graph mapping is missing: {payload.extraction_run_id}",
            error_type="extraction_run_missing",
        )
    if row.get("status") != "succeeded":
        raise PermanentEventError(
            f"Extraction run status does not match succeeded event: {payload.extraction_run_id}",
            error_type="extraction_run_status_mismatch",
        )
    if row.get("output_schema") != SUPPORTED_EXTRACTION_SCHEMA:
        return summary
    if not row.get("validated_output"):
        raise PermanentEventError(
            f"Extraction run has no validated output: {payload.extraction_run_id}",
            error_type="extraction_output_missing",
        )

    document = _raw_document_by_id(store, payload.raw_document_id)
    if document is None:
        raise PermanentEventError(
            f"Raw document for graph mapping is missing: {payload.raw_document_id}",
            error_type="raw_document_missing",
        )
    if str(row.get("raw_document_id")) != str(document.id):
        raise PermanentEventError(
            "Graph mapping event raw document does not match extraction run raw document",
            error_type="graph_mapping_document_mismatch",
        )

    output = MedicalExtractionOutput.model_validate(row["validated_output"])
    graph = map_extraction_to_graph(document, output)
    summary.extraction_runs_scanned = 1
    summary.skipped_items = graph.skipped_items
    await _write_and_publish_graph(
        store=store,
        summary=summary,
        event=event,
        document=document,
        graph=graph,
        producer=producer,
    )
    return summary


async def run_graph_mapper_once(
    *,
    settings: Settings,
    consumer_client: KafkaConsumerClient | None = None,
    producer_client: KafkaProducerClient | None = None,
) -> EventProcessingResult:
    summary = await run_graph_mapper_consumer(
        settings=settings,
        max_messages=1,
        consumer_client=consumer_client,
        producer_client=producer_client,
    )
    if not summary.results:
        raise RuntimeError("Graph mapper exited before processing a message.")
    return summary.results[0]


async def run_graph_mapper_consumer(
    *,
    settings: Settings,
    max_messages: int | None = None,
    idle_timeout_seconds: float | None = None,
    consumer_client: KafkaConsumerClient | None = None,
    producer_client: KafkaProducerClient | None = None,
) -> GraphMapperWorkerRunSummary:
    if max_messages is not None and max_messages < 1:
        raise ValueError("max_messages must be greater than zero when provided.")

    runtime = await _start_graph_mapper_runtime(
        settings=settings,
        consumer_client=consumer_client,
        producer_client=producer_client,
    )
    producer = EventProducer(runtime.producer_client)
    consumer = EventConsumer(
        runtime.consumer_client,
        producer,
        consumer_group=GRAPH_MAPPER_GROUP,
        stage=GRAPH_MAPPER_STAGE,
    )

    async def handler(received: EventEnvelope) -> None:
        await execute_graph_mapping_event(
            settings=settings,
            event=received,
            producer=producer,
        )

    summary = GraphMapperWorkerRunSummary(requested_messages=max_messages)
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


async def _start_graph_mapper_runtime(
    *,
    settings: Settings,
    consumer_client: KafkaConsumerClient | None,
    producer_client: KafkaProducerClient | None,
) -> GraphMapperRuntime:
    direct_consumer: DirectKafkaConsumerClient | None = None
    direct_producer: DirectKafkaProducerClient | None = None
    selected_consumer = consumer_client
    selected_producer = producer_client
    if selected_consumer is None:
        direct_consumer = DirectKafkaConsumerClient(
            settings,
            topics=[EXTRACTION_COMPLETED_TOPIC],
            group_id=GRAPH_MAPPER_GROUP,
        )
        selected_consumer = direct_consumer
        await direct_consumer.start()
    if selected_producer is None:
        direct_producer = DirectKafkaProducerClient(settings)
        selected_producer = direct_producer
        await direct_producer.start()
    return GraphMapperRuntime(
        consumer_client=selected_consumer,
        producer_client=selected_producer,
        direct_consumer=direct_consumer,
        direct_producer=direct_producer,
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


async def _write_and_publish_graph(
    *,
    store: FileEvidenceStore,
    summary: GraphMapperSummary,
    event: EventEnvelope,
    document: RawDocument,
    graph: GraphMappingOutput,
    producer: EventProducer | None,
) -> None:
    for node_upsert in graph.node_upserts:
        if store.write_graph_node(node_upsert):
            summary.node_upserts_created += 1
        else:
            summary.node_upserts_existing += 1
        graph_event = _graph_node_event(event=event, document=document, upsert=node_upsert)
        summary.events_emitted += int(store.write_event(graph_event))
        if producer is not None:
            await producer.produce(GRAPH_NODE_TOPIC, graph_event, key=node_upsert.graph_node_key)
            summary.kafka_events_published += 1
        summary.graph_node_keys.append(node_upsert.graph_node_key)

    for relationship_upsert in graph.relationship_upserts:
        if store.write_graph_relationship(relationship_upsert):
            summary.relationship_upserts_created += 1
        else:
            summary.relationship_upserts_existing += 1
        graph_event = _graph_relationship_event(
            event=event,
            document=document,
            upsert=relationship_upsert,
        )
        summary.events_emitted += int(store.write_event(graph_event))
        if producer is not None:
            await producer.produce(
                GRAPH_RELATIONSHIP_TOPIC,
                graph_event,
                key=relationship_upsert.relationship_key,
            )
            summary.kafka_events_published += 1
        summary.graph_relationship_keys.append(relationship_upsert.relationship_key)


def _graph_node_event(
    *,
    event: EventEnvelope,
    document: RawDocument,
    upsert: GraphNodeUpsert,
) -> EventEnvelope:
    payload = GraphNodeUpsertPayload(
        graph_node_key=upsert.graph_node_key,
        labels=list(upsert.labels),
        properties=upsert.properties,
        source_document_id=upsert.source_document_id,
        evidence_span_id=upsert.evidence_span_id,
        extraction_run_id=upsert.extraction_run_id,
        confidence=upsert.confidence,
    )
    return build_event(
        event_type=GRAPH_NODE_TOPIC,
        service="graph-mapper",
        source_id=document.source_id,
        payload=payload.model_dump(mode="json"),
        idempotency_key=f"graph.node_upsert:{upsert.graph_node_key}:{document.id}",
        correlation_id=event.correlation_id,
        causation_id=event.event_id,
        trace=event.trace,
    )


def _graph_relationship_event(
    *,
    event: EventEnvelope,
    document: RawDocument,
    upsert: GraphRelationshipUpsert,
) -> EventEnvelope:
    payload = GraphRelationshipUpsertPayload(
        relationship_key=upsert.relationship_key,
        from_key=upsert.from_key,
        to_key=upsert.to_key,
        relationship_type=upsert.relationship_type,
        properties=upsert.properties.model_dump(mode="json"),
    )
    return build_event(
        event_type=GRAPH_RELATIONSHIP_TOPIC,
        service="graph-mapper",
        source_id=document.source_id,
        payload=payload.model_dump(mode="json"),
        idempotency_key=f"graph.relationship_upsert:{upsert.relationship_key}",
        correlation_id=event.correlation_id,
        causation_id=event.event_id,
        trace=event.trace,
    )


def _new_summary(data_dir: Path) -> GraphMapperSummary:
    return GraphMapperSummary(data_dir=str(data_dir))


def _extraction_run_row_by_id(
    store: FileEvidenceStore,
    extraction_run_id: UUID,
) -> dict[str, object] | None:
    for row in store.read_collection("extraction_runs"):
        if row.get("id") == str(extraction_run_id):
            return row
    return None


def _raw_document_by_id(
    store: FileEvidenceStore,
    raw_document_id: UUID,
) -> RawDocument | None:
    for row in store.read_collection("raw_documents"):
        if row.get("id") == str(raw_document_id):
            return RawDocument.model_validate(row)
    return None
