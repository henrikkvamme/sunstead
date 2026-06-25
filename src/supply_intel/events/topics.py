from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import yaml
from aiokafka.admin import AIOKafkaAdminClient, NewTopic  # type: ignore[import-untyped]
from aiokafka.errors import TopicAlreadyExistsError  # type: ignore[import-untyped]

from supply_intel.events.kafka_clients import kafka_ssl_context
from supply_intel.infra.aiven_mcp import AivenMCPController
from supply_intel.models.infra import KafkaTopicBootstrapResult, KafkaTopicSpec, MCPAuditAction
from supply_intel.settings import Settings


def load_topic_specs(path: Path = Path("infra/kafka/topics.yaml")) -> list[KafkaTopicSpec]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    topics = data.get("topics", []) if isinstance(data, dict) else []
    return [KafkaTopicSpec.model_validate(topic) for topic in topics]


class KafkaAdminClient(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...

    async def create_topics(self, new_topics: list[NewTopic]) -> object: ...


def topic_config(spec: KafkaTopicSpec) -> dict[str, str]:
    config = {str(key): str(value) for key, value in spec.config.items()}
    config["cleanup.policy"] = spec.cleanup_policy
    if spec.retention_hours is not None:
        config["retention.ms"] = str(spec.retention_hours * 60 * 60 * 1000)
    return config


def new_topic_from_spec(spec: KafkaTopicSpec) -> NewTopic:
    return NewTopic(
        spec.topic_name,
        num_partitions=spec.partitions,
        replication_factor=spec.replication,
        topic_configs=topic_config(spec),
    )


def plan_topic_bootstrap(specs: list[KafkaTopicSpec]) -> list[KafkaTopicBootstrapResult]:
    return [
        KafkaTopicBootstrapResult(
            topic_name=spec.topic_name,
            backend="dry_run",
            status="planned",
            partitions=spec.partitions,
            replication=spec.replication,
            config=topic_config(spec),
        )
        for spec in specs
    ]


async def ensure_topics_with_mcp(
    specs: list[KafkaTopicSpec],
    controller: AivenMCPController,
) -> list[KafkaTopicBootstrapResult]:
    results: list[KafkaTopicBootstrapResult] = []
    for spec in specs:
        started_at = datetime.now(UTC)
        request = {
            "topic_name": spec.topic_name,
            "partitions": spec.partitions,
            "replication": spec.replication,
            "config": topic_config(spec),
        }
        try:
            await controller.ensure_kafka_topic(spec)
        except Exception as exc:
            await controller.audit_action(
                MCPAuditAction(
                    controller="aiven_mcp",
                    action="ensure_kafka_topic",
                    safety_level="migration_write",
                    request=request,
                    response_summary=None,
                    status="failed",
                    destructive=False,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    error=str(exc),
                )
            )
            raise
        await controller.audit_action(
            MCPAuditAction(
                controller="aiven_mcp",
                action="ensure_kafka_topic",
                safety_level="migration_write",
                request=request,
                response_summary={"topic_name": spec.topic_name, "status": "ensured"},
                status="succeeded",
                destructive=False,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        )
        results.append(
            KafkaTopicBootstrapResult(
                topic_name=spec.topic_name,
                backend="aiven_mcp",
                status="ensured",
                partitions=spec.partitions,
                replication=spec.replication,
                config=topic_config(spec),
            )
        )
    return results


async def ensure_topics_with_admin(
    specs: list[KafkaTopicSpec],
    admin: KafkaAdminClient,
) -> list[KafkaTopicBootstrapResult]:
    results: list[KafkaTopicBootstrapResult] = []
    await admin.start()
    try:
        for spec in specs:
            try:
                await admin.create_topics([new_topic_from_spec(spec)])
                status = "created"
            except TopicAlreadyExistsError:
                status = "already_exists"
            results.append(
                KafkaTopicBootstrapResult(
                    topic_name=spec.topic_name,
                    backend="direct_admin",
                    status=status,
                    partitions=spec.partitions,
                    replication=spec.replication,
                    config=topic_config(spec),
                )
            )
    finally:
        await admin.close()
    return results


async def ensure_topics_direct(
    specs: list[KafkaTopicSpec],
    settings: Settings,
) -> list[KafkaTopicBootstrapResult]:
    admin = AIOKafkaAdminClient(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        security_protocol=settings.kafka_security_protocol,
        ssl_context=kafka_ssl_context(settings),
        sasl_plain_username=settings.kafka_sasl_username,
        sasl_plain_password=settings.kafka_sasl_password,
    )
    return await ensure_topics_with_admin(specs, admin)
