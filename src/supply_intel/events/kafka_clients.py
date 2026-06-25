from __future__ import annotations

import ssl
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer  # type: ignore[import-untyped]

from supply_intel.settings import Settings


def kafka_client_config(settings: Settings) -> dict[str, object]:
    config: dict[str, object] = {
        "bootstrap_servers": settings.kafka_bootstrap_servers,
        "security_protocol": settings.kafka_security_protocol,
    }
    ssl_context = kafka_ssl_context(settings)
    if ssl_context is not None:
        config["ssl_context"] = ssl_context
    if settings.kafka_sasl_username is not None:
        config["sasl_plain_username"] = settings.kafka_sasl_username
    if settings.kafka_sasl_password is not None:
        config["sasl_plain_password"] = settings.kafka_sasl_password
    return config


def kafka_ssl_context(settings: Settings) -> ssl.SSLContext | None:
    if (
        settings.kafka_ca_cert_path is None
        and settings.kafka_client_cert_path is None
        and settings.kafka_client_key_path is None
    ):
        return None
    if (settings.kafka_client_cert_path is None) != (settings.kafka_client_key_path is None):
        raise ValueError("KAFKA_CLIENT_CERT_PATH and KAFKA_CLIENT_KEY_PATH must be set together")

    context = ssl.create_default_context(
        cafile=str(settings.kafka_ca_cert_path) if settings.kafka_ca_cert_path is not None else None
    )
    if settings.kafka_client_cert_path is not None and settings.kafka_client_key_path is not None:
        context.load_cert_chain(
            certfile=str(settings.kafka_client_cert_path),
            keyfile=str(settings.kafka_client_key_path),
        )
    return context


class DirectKafkaProducerClient:
    """aiokafka-backed runtime producer used when MCP Kafka REST is unavailable."""

    def __init__(
        self,
        settings: Settings,
        *,
        producer: Any | None = None,
    ) -> None:
        self.producer = producer or AIOKafkaProducer(**kafka_client_config(settings))

    async def start(self) -> None:
        await self.producer.start()

    async def stop(self) -> None:
        await self.producer.stop()

    async def send_and_wait(
        self,
        topic: str,
        value: bytes,
        *,
        key: bytes | None = None,
        headers: list[tuple[str, bytes]] | None = None,
    ) -> object:
        return await self.producer.send_and_wait(
            topic,
            value=value,
            key=key,
            headers=headers,
        )


class DirectKafkaConsumerClient:
    """aiokafka-backed runtime consumer with explicit commit control."""

    def __init__(
        self,
        settings: Settings,
        *,
        topics: list[str],
        group_id: str,
        auto_offset_reset: str = "earliest",
        consumer: Any | None = None,
    ) -> None:
        self.consumer = consumer or AIOKafkaConsumer(
            *topics,
            group_id=group_id,
            enable_auto_commit=False,
            auto_offset_reset=auto_offset_reset,
            **kafka_client_config(settings),
        )

    async def start(self) -> None:
        await self.consumer.start()

    async def stop(self) -> None:
        await self.consumer.stop()

    async def getone(self) -> Any:
        return await self.consumer.getone()

    async def commit(self) -> None:
        await self.consumer.commit()
