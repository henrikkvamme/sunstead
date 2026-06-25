from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Protocol

from pydantic import ValidationError

from supply_intel.events.envelope import deserialize_event
from supply_intel.events.producer import EventProducer, deadletter_topic_for
from supply_intel.events.schemas import validate_event_payload
from supply_intel.models.kafka import EventEnvelope, EventProcessingResult

EventHandler = Callable[[EventEnvelope], Awaitable[None]]


class KafkaConsumerMessage(Protocol):
    topic: str
    key: bytes | None
    value: bytes | None


class KafkaConsumerClient(Protocol):
    async def getone(self) -> KafkaConsumerMessage: ...

    async def commit(self) -> None: ...


class PermanentEventError(Exception):
    def __init__(self, message: str, *, error_type: str = "permanent_event_failure") -> None:
        super().__init__(message)
        self.error_type = error_type


class EventConsumer:
    def __init__(
        self,
        client: KafkaConsumerClient,
        producer: EventProducer,
        *,
        consumer_group: str,
        stage: str,
    ) -> None:
        self.client = client
        self.producer = producer
        self.consumer_group = consumer_group
        self.stage = stage

    async def process_one(self, handler: EventHandler) -> EventProcessingResult:
        message = await self.client.getone()
        event: EventEnvelope | None = None
        try:
            event = decode_message_event(message)
            await handler(event)
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            deadletter = await self._deadletter_invalid_message(message, exc)
            await self.client.commit()
            return EventProcessingResult(
                status="deadlettered",
                topic=message.topic,
                event_id=deadletter.event_id,
                committed=True,
                deadletter_topic=deadletter_topic_for(message.topic),
            )
        except PermanentEventError as exc:
            deadletter = await self._deadletter_permanent_failure(message, event, exc)
            await self.client.commit()
            return EventProcessingResult(
                status="deadlettered",
                topic=message.topic,
                event_id=deadletter.event_id,
                committed=True,
                deadletter_topic=deadletter_topic_for(message.topic),
            )

        await self.client.commit()
        return EventProcessingResult(
            status="processed",
            topic=message.topic,
            event_id=event.event_id if event is not None else None,
            committed=True,
        )

    async def _deadletter_invalid_message(
        self,
        message: KafkaConsumerMessage,
        exc: Exception,
    ) -> EventEnvelope:
        return await self.producer.deadletter(
            original_topic=message.topic,
            original_key=decode_key(message.key),
            consumer_group=self.consumer_group,
            stage=self.stage,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            retryable=False,
            original_value=decode_value(message.value),
        )

    async def _deadletter_permanent_failure(
        self,
        message: KafkaConsumerMessage,
        event: EventEnvelope | None,
        exc: PermanentEventError,
    ) -> EventEnvelope:
        return await self.producer.deadletter(
            original_topic=message.topic,
            original_key=decode_key(message.key),
            consumer_group=self.consumer_group,
            stage=self.stage,
            error_type=exc.error_type,
            error_message=str(exc),
            retryable=False,
            original_event=event,
            original_value=decode_value(message.value),
        )


def decode_message_event(message: KafkaConsumerMessage) -> EventEnvelope:
    if message.value is None:
        raise ValueError("Kafka message value is empty")
    return validate_event_payload(deserialize_event(message.value))


def decode_key(value: bytes | None) -> str | None:
    if value is None:
        return None
    return value.decode("utf-8", errors="replace")


def decode_value(value: bytes | None) -> str | None:
    if value is None:
        return None
    return value.decode("utf-8", errors="replace")
