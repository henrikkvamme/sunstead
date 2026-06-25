from __future__ import annotations

from typing import Protocol
from uuid import UUID

from supply_intel.events.envelope import build_event, serialize_event
from supply_intel.events.schemas import validate_event_payload
from supply_intel.models.kafka import DeadLetterPayload, EventEnvelope, OpsMetricPayload


class KafkaProducerClient(Protocol):
    async def send_and_wait(
        self,
        topic: str,
        value: bytes,
        *,
        key: bytes | None = None,
        headers: list[tuple[str, bytes]] | None = None,
    ) -> object: ...


def encode_key(key: str | UUID | None) -> bytes | None:
    if key is None:
        return None
    return str(key).encode("utf-8")


def deadletter_topic_for(topic: str) -> str:
    if topic.startswith("graph."):
        return "graph.deadletter"
    if topic.startswith("ingest."):
        return "ingest.deadletter"
    return "ops.errors"


class EventProducer:
    def __init__(
        self,
        client: KafkaProducerClient,
        *,
        allowed_topics: set[str] | None = None,
        emit_metrics: bool = False,
    ) -> None:
        self.client = client
        self.allowed_topics = allowed_topics
        self.emit_metrics = emit_metrics

    async def produce(
        self,
        topic: str,
        event: EventEnvelope,
        *,
        key: str | UUID | None = None,
    ) -> EventEnvelope:
        self._ensure_topic_allowed(topic)
        validated_event = validate_event_payload(
            EventEnvelope.model_validate(event.model_dump(mode="json"))
        )
        await self.client.send_and_wait(
            topic,
            serialize_event(validated_event),
            key=encode_key(key),
            headers=[
                ("event_type", validated_event.event_type.encode("utf-8")),
                ("schema_version", str(validated_event.schema_version).encode("utf-8")),
                ("correlation_id", str(validated_event.correlation_id).encode("utf-8")),
            ],
        )
        if self.emit_metrics and topic != "ops.metrics":
            await self._produce_event_produced_metric(topic, validated_event)
        return validated_event

    async def deadletter(
        self,
        *,
        original_topic: str,
        original_key: str | None,
        consumer_group: str | None,
        stage: str,
        error_type: str,
        error_message: str,
        retryable: bool,
        original_event: EventEnvelope | None = None,
        original_value: str | None = None,
    ) -> EventEnvelope:
        payload = DeadLetterPayload(
            original_topic=original_topic,
            original_key=original_key,
            consumer_group=consumer_group,
            stage=stage,
            error_type=error_type,
            error_message=error_message,
            retryable=retryable,
            original_event=(
                original_event.model_dump(mode="json") if original_event is not None else None
            ),
            original_value=original_value,
        )
        event = build_event(
            event_type="ops.deadletter",
            service="event-consumer",
            source_id=original_event.source.source_id if original_event is not None else None,
            payload=payload.model_dump(mode="json"),
            idempotency_key=(
                f"deadletter:{original_topic}:{original_key}:{stage}:{error_type}:"
                f"{original_event.event_id if original_event is not None else ''}"
            ),
            correlation_id=original_event.correlation_id if original_event is not None else None,
            causation_id=original_event.event_id if original_event is not None else None,
            trace=original_event.trace if original_event is not None else None,
        )
        await self.produce(deadletter_topic_for(original_topic), event, key=original_key)
        return event

    def _ensure_topic_allowed(self, topic: str) -> None:
        if self.allowed_topics is None or topic in self.allowed_topics:
            return
        raise ValueError(f"Topic {topic} is not configured")

    async def _produce_event_produced_metric(
        self,
        topic: str,
        event: EventEnvelope,
    ) -> None:
        self._ensure_topic_allowed("ops.metrics")
        idempotency_key = f"ops.metrics:events_produced_total:{topic}:{event.event_id}"
        payload = OpsMetricPayload(
            metric_name="events_produced_total",
            metric_value=1,
            service=event.source.service,
            source_id=event.source.source_id,
            topic=topic,
            idempotency_key=idempotency_key,
            unit="count",
            tags={"event_type": event.event_type},
        )
        metric_event = build_event(
            event_type="ops.metrics",
            service=event.source.service,
            source_id=event.source.source_id,
            payload=payload.model_dump(mode="json"),
            idempotency_key=idempotency_key,
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
            trace=event.trace,
        )
        validated_metric = validate_event_payload(metric_event)
        await self.client.send_and_wait(
            "ops.metrics",
            serialize_event(validated_metric),
            key=encode_key(payload.metric_name),
            headers=[
                ("event_type", b"ops.metrics"),
                ("schema_version", str(validated_metric.schema_version).encode("utf-8")),
                ("correlation_id", str(validated_metric.correlation_id).encode("utf-8")),
            ],
        )
