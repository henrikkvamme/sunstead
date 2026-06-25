from aiokafka.admin import NewTopic
from aiokafka.errors import TopicAlreadyExistsError

from supply_intel.events.topics import (
    ensure_topics_with_admin,
    ensure_topics_with_mcp,
    load_topic_specs,
    new_topic_from_spec,
    plan_topic_bootstrap,
    topic_config,
)
from supply_intel.models.infra import AivenProject, AivenServiceRef, KafkaTopicSpec, MCPAuditAction


class FakeKafkaAdmin:
    def __init__(self, *, existing_topic: str | None = None) -> None:
        self.existing_topic = existing_topic
        self.started = False
        self.closed = False
        self.created: list[NewTopic] = []

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    async def create_topics(self, new_topics: list[NewTopic]) -> object:
        topic = new_topics[0]
        if topic.name == self.existing_topic:
            raise TopicAlreadyExistsError()
        self.created.extend(new_topics)
        return object()


class FakeAivenMCPController:
    def __init__(self) -> None:
        self.topics: list[KafkaTopicSpec] = []
        self.audits: list[MCPAuditAction] = []

    async def discover_projects(self) -> list[AivenProject]:
        return []

    async def discover_services(self, project: str | None = None) -> list[AivenServiceRef]:
        del project
        return []

    async def ensure_kafka_topic(self, spec: KafkaTopicSpec) -> None:
        self.topics.append(spec)

    async def audit_action(self, action: MCPAuditAction) -> None:
        self.audits.append(action)


def test_topic_config_sets_cleanup_policy_and_retention_ms() -> None:
    spec = KafkaTopicSpec(
        topic_name="ingest.raw_document_created",
        partitions=3,
        replication=2,
        cleanup_policy="delete",
        retention_hours=24,
        config={"compression.type": "zstd"},
    )

    config = topic_config(spec)

    assert config["cleanup.policy"] == "delete"
    assert config["retention.ms"] == str(24 * 60 * 60 * 1000)
    assert config["compression.type"] == "zstd"


def test_new_topic_from_spec_uses_explicit_partitions_replication_and_config() -> None:
    spec = KafkaTopicSpec(
        topic_name="agents.status",
        partitions=1,
        replication=1,
        cleanup_policy="compact,delete",
        retention_hours=168,
    )

    topic = new_topic_from_spec(spec)

    assert topic.name == "agents.status"
    assert topic.num_partitions == 1
    assert topic.replication_factor == 1
    assert topic.topic_configs["cleanup.policy"] == "compact,delete"


def test_plan_topic_bootstrap_returns_all_configured_topics() -> None:
    specs = load_topic_specs()

    plan = plan_topic_bootstrap(specs)

    assert len(plan) == len(specs)
    assert {result.topic_name for result in plan} >= {"dashboard.graph_chat_answered"}
    assert plan[0].backend == "dry_run"
    assert plan[0].status == "planned"
    assert plan[0].config["cleanup.policy"] == specs[0].cleanup_policy


async def test_ensure_topics_with_admin_creates_and_closes_client() -> None:
    specs = [
        KafkaTopicSpec(topic_name="ingest.jobs", partitions=1, replication=1),
        KafkaTopicSpec(topic_name="ingest.raw_document_created", partitions=1, replication=1),
    ]
    admin = FakeKafkaAdmin(existing_topic="ingest.raw_document_created")

    results = await ensure_topics_with_admin(specs, admin)

    assert admin.started is True
    assert admin.closed is True
    assert [topic.name for topic in admin.created] == ["ingest.jobs"]
    assert [result.status for result in results] == ["created", "already_exists"]
    assert all(result.backend == "direct_admin" for result in results)


async def test_ensure_topics_with_mcp_delegates_each_spec() -> None:
    specs = [
        KafkaTopicSpec(topic_name="risk.alerts", partitions=1, replication=1),
        KafkaTopicSpec(topic_name="ops.errors", partitions=1, replication=1),
    ]
    controller = FakeAivenMCPController()

    results = await ensure_topics_with_mcp(specs, controller)

    assert [topic.topic_name for topic in controller.topics] == ["risk.alerts", "ops.errors"]
    assert [audit.action for audit in controller.audits] == [
        "ensure_kafka_topic",
        "ensure_kafka_topic",
    ]
    assert [audit.status for audit in controller.audits] == ["succeeded", "succeeded"]
    assert controller.audits[0].request["topic_name"] == "risk.alerts"
    assert [result.backend for result in results] == ["aiven_mcp", "aiven_mcp"]
    assert [result.status for result in results] == ["ensured", "ensured"]
