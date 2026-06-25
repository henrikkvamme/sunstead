from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.events.kafka_clients import DirectKafkaProducerClient
from supply_intel.events.producer import EventProducer, KafkaProducerClient
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.infra import OperationalMetric
from supply_intel.models.kafka import EventEnvelope
from supply_intel.settings import Settings

EVENT_KEY_FIELD_BY_TYPE = {
    "agents.audit_log": "risk_case_id",
    "dashboard.graph_chat_answered": "audit_id",
    "graph.node_upsert": "graph_node_key",
    "graph.relationship_upsert": "relationship_key",
    "ingest.document_parsed": "raw_document_id",
    "ingest.extraction_completed": "extraction_run_id",
    "ingest.raw_document_created": "raw_document_id",
    "ops.metrics": "metric_name",
    "risk.agent_findings": "risk_case_id",
    "risk.alerts": "alert_key",
    "risk.candidates": "candidate_key",
    "risk.case_created": "risk_case_id",
    "risk.verdicts": "risk_case_id",
}


class OutboxPublishSummary(StrictBaseModel):
    data_dir: str
    publish_kafka: bool
    selected: int
    published: int
    event_ids: list[str]
    topics: dict[str, int]
    metrics_recorded: int = 0


async def publish_events_by_ids(
    *,
    store: FileEvidenceStore,
    producer: EventProducer,
    event_ids: list[str],
) -> int:
    events = _events_by_id(store)
    published = 0
    for event_id in event_ids:
        event = events.get(event_id)
        if event is None:
            continue
        await producer.produce(event.event_type, event, key=event_key(event))
        published += 1
    return published


def select_outbox_events(
    *,
    store: FileEvidenceStore,
    event_ids: list[str] | None = None,
    event_type: str | None = None,
    idempotency_key: str | None = None,
    limit: int | None = None,
) -> list[EventEnvelope]:
    requested_ids = set(event_ids or [])
    found_ids: set[str] = set()
    events: list[EventEnvelope] = []

    for row in store.read_collection("events"):
        event = EventEnvelope.model_validate(row)
        event_id = str(event.event_id)
        if requested_ids and event_id not in requested_ids:
            continue
        found_ids.add(event_id)
        if event_type is not None and event.event_type != event_type:
            continue
        if idempotency_key is not None and event.idempotency_key != idempotency_key:
            continue
        events.append(event)
        if limit is not None and len(events) >= limit:
            break

    missing = sorted(requested_ids - found_ids)
    if missing:
        raise ValueError(f"Outbox events not found in local audit store: {missing}")
    return events


def summarize_outbox_selection(
    *,
    data_dir: str,
    events: list[EventEnvelope],
    publish_kafka: bool = False,
) -> OutboxPublishSummary:
    topics = Counter(event.event_type for event in events)
    return OutboxPublishSummary(
        data_dir=data_dir,
        publish_kafka=publish_kafka,
        selected=len(events),
        published=0,
        event_ids=[str(event.event_id) for event in events],
        topics=dict(sorted(topics.items())),
    )


async def publish_outbox_events_to_kafka(
    *,
    settings: Settings,
    store: FileEvidenceStore,
    events: list[EventEnvelope],
    producer_client: KafkaProducerClient | None = None,
) -> OutboxPublishSummary:
    if producer_client is not None:
        return await _publish_outbox_events(
            store=store,
            events=events,
            producer_client=producer_client,
            data_dir=str(store.root),
        )

    direct_client = DirectKafkaProducerClient(settings)
    await direct_client.start()
    try:
        return await _publish_outbox_events(
            store=store,
            events=events,
            producer_client=direct_client,
            data_dir=str(store.root),
        )
    finally:
        await direct_client.stop()


async def _publish_outbox_events(
    *,
    store: FileEvidenceStore,
    events: list[EventEnvelope],
    producer_client: KafkaProducerClient,
    data_dir: str,
) -> OutboxPublishSummary:
    allowed_topics = {event.event_type for event in events} | {"ops.metrics"}
    producer = EventProducer(
        producer_client,
        allowed_topics=allowed_topics,
        emit_metrics=True,
    )
    published: list[str] = []
    metrics_recorded = 0
    topics: Counter[str] = Counter()

    for event in events:
        await producer.produce(event.event_type, event, key=event_key(event))
        published.append(str(event.event_id))
        topics[event.event_type] += 1
        if store.write_operational_metric(_event_produced_metric(event, topic=event.event_type)):
            metrics_recorded += 1

    return OutboxPublishSummary(
        data_dir=data_dir,
        publish_kafka=True,
        selected=len(events),
        published=len(published),
        event_ids=published,
        topics=dict(sorted(topics.items())),
        metrics_recorded=metrics_recorded,
    )


def event_key(event: EventEnvelope) -> str | UUID:
    field = EVENT_KEY_FIELD_BY_TYPE.get(event.event_type)
    if field is None:
        return event.idempotency_key
    value = event.payload.get(field)
    if isinstance(value, UUID):
        return value
    if value is None:
        return event.idempotency_key
    return str(value)


def _events_by_id(store: FileEvidenceStore) -> dict[str, EventEnvelope]:
    return {
        str(event.event_id): event
        for event in (EventEnvelope.model_validate(row) for row in store.read_collection("events"))
    }


def _event_produced_metric(event: EventEnvelope, *, topic: str) -> OperationalMetric:
    idempotency_key = f"ops.metrics:events_produced_total:{topic}:{event.event_id}"
    return OperationalMetric(
        metric_name="events_produced_total",
        metric_value=1,
        service=event.source.service,
        source_id=event.source.source_id,
        topic=topic,
        unit="count",
        idempotency_key=idempotency_key,
        correlation_id=event.correlation_id,
        causation_id=event.event_id,
        observed_at=datetime.now(UTC),
        tags={"event_type": event.event_type},
    )
