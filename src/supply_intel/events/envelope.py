from typing import Any
from uuid import UUID

from supply_intel.events.schemas import validate_event_payload
from supply_intel.models.kafka import EventEnvelope, EventSource, TraceMetadata


def build_event(
    *,
    event_type: str,
    service: str,
    payload: dict[str, Any],
    idempotency_key: str,
    source_id: str | None = None,
    correlation_id: UUID | None = None,
    causation_id: UUID | None = None,
    trace: TraceMetadata | None = None,
) -> EventEnvelope:
    event = EventEnvelope(
        event_type=event_type,
        source=EventSource(service=service, source_id=source_id),
        payload=payload,
        idempotency_key=idempotency_key,
        causation_id=causation_id,
        trace=trace or TraceMetadata(),
    )
    if correlation_id is not None:
        event.correlation_id = correlation_id
    return validate_event_payload(event)


def serialize_event(event: EventEnvelope) -> bytes:
    return event.model_dump_json().encode("utf-8")


def deserialize_event(value: bytes | str) -> EventEnvelope:
    return EventEnvelope.model_validate_json(value)
