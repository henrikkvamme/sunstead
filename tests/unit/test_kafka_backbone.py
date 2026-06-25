from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from supply_intel.events.consumer import EventConsumer, PermanentEventError
from supply_intel.events.envelope import build_event, deserialize_event, serialize_event
from supply_intel.events.kafka_clients import (
    DirectKafkaConsumerClient,
    DirectKafkaProducerClient,
    kafka_client_config,
    kafka_ssl_context,
)
from supply_intel.events.outbox import event_key
from supply_intel.events.producer import EventProducer
from supply_intel.events.schemas import export_event_schema_bundle
from supply_intel.models.kafka import (
    DashboardGraphChatAnsweredPayload,
    EventEnvelope,
    OpsMetricPayload,
    RawDocumentCreatedPayload,
    RiskCandidatePayload,
)
from supply_intel.models.risk import RiskScope
from supply_intel.settings import Settings


@dataclass
class FakeMessage:
    topic: str
    key: bytes | None
    value: bytes | None


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
        return object()


class FakeConsumerClient:
    def __init__(self, messages: list[FakeMessage]) -> None:
        self.messages = messages
        self.commits = 0

    async def getone(self) -> FakeMessage:
        return self.messages.pop(0)

    async def commit(self) -> None:
        self.commits += 1


class FakeRuntimeProducer:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.sent: list[tuple[str, bytes, bytes | None, list[tuple[str, bytes]] | None]] = []

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def send_and_wait(
        self,
        topic: str,
        *,
        value: bytes,
        key: bytes | None = None,
        headers: list[tuple[str, bytes]] | None = None,
    ) -> object:
        self.sent.append((topic, value, key, headers))
        return {"topic": topic}


class FakeRuntimeConsumer:
    def __init__(self, message: FakeMessage) -> None:
        self.message = message
        self.started = False
        self.stopped = False
        self.commits = 0

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def getone(self) -> FakeMessage:
        return self.message

    async def commit(self) -> None:
        self.commits += 1


class FakeSSLContext:
    def __init__(self) -> None:
        self.loaded_cert_chain: tuple[str, str] | None = None

    def load_cert_chain(self, *, certfile: str, keyfile: str) -> None:
        self.loaded_cert_chain = (certfile, keyfile)


def sample_event() -> EventEnvelope:
    source_run_id = uuid4()
    raw_document_id = uuid4()
    payload = RawDocumentCreatedPayload(
        source_id="openfda_drug_ndc",
        source_run_id=source_run_id,
        raw_document_id=raw_document_id,
        source_url="https://api.fda.gov/drug/ndc.json",
        content_hash="hash-1",
        content_type="application/json",
        fetched_at=datetime.now(UTC),
    )
    return build_event(
        event_type="ingest.raw_document_created",
        service="ingester",
        source_id="openfda_drug_ndc",
        idempotency_key="openfda_drug_ndc:0002-8215:hash-1",
        payload=payload.model_dump(mode="json"),
    )


async def test_event_producer_validates_and_serializes_envelope() -> None:
    client = FakeProducerClient()
    producer = EventProducer(client, allowed_topics={"ingest.raw_document_created"})
    event = sample_event()

    produced = await producer.produce("ingest.raw_document_created", event, key="doc-1")

    assert produced.event_id == event.event_id
    topic, value, key, headers = client.sent[0]
    assert topic == "ingest.raw_document_created"
    assert key == b"doc-1"
    assert deserialize_event(value).event_id == event.event_id
    assert headers is not None
    assert ("event_type", b"ingest.raw_document_created") in headers


async def test_event_producer_can_emit_ops_metric_for_produced_events() -> None:
    client = FakeProducerClient()
    producer = EventProducer(
        client,
        allowed_topics={"ingest.raw_document_created", "ops.metrics"},
        emit_metrics=True,
    )
    event = sample_event()

    await producer.produce("ingest.raw_document_created", event, key="doc-1")

    assert [topic for topic, _, _, _ in client.sent] == [
        "ingest.raw_document_created",
        "ops.metrics",
    ]
    metric_event = deserialize_event(client.sent[1][1])
    assert metric_event.event_type == "ops.metrics"
    assert metric_event.causation_id == event.event_id
    assert metric_event.payload["metric_name"] == "events_produced_total"
    assert metric_event.payload["metric_value"] == 1
    assert metric_event.payload["service"] == "ingester"
    assert metric_event.payload["topic"] == "ingest.raw_document_created"


async def test_event_producer_rejects_invalid_known_payload_before_send() -> None:
    client = FakeProducerClient()
    producer = EventProducer(client, allowed_topics={"ingest.raw_document_created"})
    invalid = EventEnvelope(
        event_type="ingest.raw_document_created",
        source={"service": "ingester", "source_id": "openfda_drug_ndc"},
        idempotency_key="bad-payload",
        payload={"raw_document_id": "not-a-uuid"},
    )

    with pytest.raises(ValidationError):
        await producer.produce("ingest.raw_document_created", invalid, key="doc-1")

    assert client.sent == []


def test_event_schema_bundle_exports_envelope_and_payload_models() -> None:
    schemas = export_event_schema_bundle()

    assert schemas["schema_version"] == 1
    assert "properties" in schemas["envelope"]
    assert "ingest.raw_document_created" in schemas["payloads"]
    assert "dashboard.graph_chat_answered" in schemas["payloads"]
    assert "ops.metrics" in schemas["payloads"]
    assert "risk.candidates" in schemas["payloads"]
    assert "risk.verdicts" in schemas["payloads"]
    raw_document_schema = schemas["payloads"]["ingest.raw_document_created"]
    assert "raw_document_id" in raw_document_schema["properties"]


def test_ops_metric_event_key_uses_metric_name() -> None:
    payload = OpsMetricPayload(
        metric_name="events_produced_total",
        metric_value=1,
        service="scheduler",
        topic="ingest.jobs",
        idempotency_key="metric-1",
    )
    event = build_event(
        event_type="ops.metrics",
        service="scheduler",
        payload=payload.model_dump(mode="json"),
        idempotency_key="metric-1",
    )

    assert event_key(event) == "events_produced_total"


def test_risk_candidate_event_key_uses_candidate_key() -> None:
    payload = RiskCandidatePayload(
        candidate_key="risk_candidate:shortage:Shortage:fda:abc",
        risk_type="shortage",
        scope=RiskScope(type="Shortage", graph_key="Shortage:fda:abc"),
        initial_score=80.0,
        confidence=0.92,
    )
    event = build_event(
        event_type="risk.candidates",
        service="risk-engine",
        payload=payload.model_dump(mode="json"),
        idempotency_key="risk.candidates:risk_candidate:shortage:Shortage:fda:abc",
    )

    assert event_key(event) == "risk_candidate:shortage:Shortage:fda:abc"


def test_dashboard_graph_chat_answer_event_key_uses_audit_id() -> None:
    audit_id = uuid4()
    payload = DashboardGraphChatAnsweredPayload(
        audit_id=audit_id,
        selected_node_id="platform:Drug:ndc_product:0002-8215",
        requested_node_id="platform:Drug:ndc_product:0002-8215",
        input_hash="a" * 64,
        input_length=24,
        output_hash="b" * 64,
        output_schema="SupplyGraphQuestionResponse",
        output_schema_version=1,
        graph_stats={"nodes": 538, "edges": 311, "platform_nodes": 500},
        neighbor_node_ids=["platform:NDC:product:0002-8215"],
        related_node_ids=[],
        source_refs=[
            {
                "meta": "source-run-1, 2026-06-25T10:54:23Z",
                "title": "HUMALOG platform graph evidence",
                "url": "/platform-demo/supply-chain-graph.json",
            }
        ],
        safety={
            "advice_scope": "supply_chain_intelligence_only",
            "clinical_advice": False,
            "patient_identifiable_data": False,
        },
        status="succeeded",
    )
    event = build_event(
        event_type="dashboard.graph_chat_answered",
        service="dashboard-graph-chat",
        payload=payload.model_dump(mode="json"),
        idempotency_key=f"dashboard.graph_chat_answered:{audit_id}",
    )

    assert event_key(event) == str(audit_id)


def test_kafka_client_config_uses_direct_runtime_settings() -> None:
    settings = Settings(
        kafka_bootstrap_servers="kafka.example.test:9092",
        kafka_security_protocol="SASL_SSL",
        kafka_sasl_username="platform",
        kafka_sasl_password="secret-value",
    )

    config = kafka_client_config(settings)

    assert config["bootstrap_servers"] == "kafka.example.test:9092"
    assert config["security_protocol"] == "SASL_SSL"
    assert config["sasl_plain_username"] == "platform"
    assert config["sasl_plain_password"] == "secret-value"
    assert "ssl_context" not in config


def test_kafka_client_config_loads_mtls_context(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[tuple[str | None, FakeSSLContext]] = []

    def fake_default_context(*, cafile: str | None = None) -> FakeSSLContext:
        context = FakeSSLContext()
        created.append((cafile, context))
        return context

    monkeypatch.setattr(
        "supply_intel.events.kafka_clients.ssl.create_default_context",
        fake_default_context,
    )
    settings = Settings(
        kafka_bootstrap_servers="kafka.example.test:9092",
        kafka_security_protocol="SSL",
        kafka_ca_cert_path="/secrets/aiven/kafka-ca.pem",
        kafka_client_cert_path="/secrets/aiven/service.cert",
        kafka_client_key_path="/secrets/aiven/service.key",
    )

    config = kafka_client_config(settings)

    assert config["security_protocol"] == "SSL"
    assert created[0][0] == "/secrets/aiven/kafka-ca.pem"
    context = created[0][1]
    assert config["ssl_context"] is context
    assert context.loaded_cert_chain == (
        "/secrets/aiven/service.cert",
        "/secrets/aiven/service.key",
    )


def test_kafka_ssl_context_requires_cert_and_key_pair() -> None:
    settings = Settings(kafka_client_cert_path="/secrets/aiven/service.cert")

    with pytest.raises(ValueError, match="must be set together"):
        kafka_ssl_context(settings)


async def test_direct_kafka_producer_client_delegates_lifecycle_and_send() -> None:
    runtime = FakeRuntimeProducer()
    client = DirectKafkaProducerClient(Settings(), producer=runtime)

    await client.start()
    result = await client.send_and_wait(
        "ingest.raw_document_created",
        b"{}",
        key=b"doc-1",
        headers=[("event_type", b"ingest.raw_document_created")],
    )
    await client.stop()

    assert runtime.started is True
    assert runtime.stopped is True
    assert result == {"topic": "ingest.raw_document_created"}
    assert runtime.sent == [
        (
            "ingest.raw_document_created",
            b"{}",
            b"doc-1",
            [("event_type", b"ingest.raw_document_created")],
        )
    ]


async def test_direct_kafka_consumer_client_delegates_lifecycle_get_and_commit() -> None:
    message = FakeMessage("ingest.raw_document_created", b"doc-1", b"{}")
    runtime = FakeRuntimeConsumer(message)
    client = DirectKafkaConsumerClient(
        Settings(),
        topics=["ingest.raw_document_created"],
        group_id="parser",
        consumer=runtime,
    )

    await client.start()
    received = await client.getone()
    await client.commit()
    await client.stop()

    assert runtime.started is True
    assert runtime.stopped is True
    assert runtime.commits == 1
    assert received is message


async def test_event_consumer_commits_after_successful_handler() -> None:
    event = sample_event()
    consumer_client = FakeConsumerClient(
        [FakeMessage("ingest.raw_document_created", b"doc-1", serialize_event(event))]
    )
    producer = EventProducer(FakeProducerClient())
    consumer = EventConsumer(
        consumer_client,
        producer,
        consumer_group="parser",
        stage="parse",
    )
    handled: list[EventEnvelope] = []

    async def handler(received: EventEnvelope) -> None:
        handled.append(received)

    result = await consumer.process_one(handler)

    assert result.status == "processed"
    assert result.event_id == event.event_id
    assert consumer_client.commits == 1
    assert handled[0].event_id == event.event_id


async def test_event_consumer_deadletters_invalid_envelope_and_commits() -> None:
    producer_client = FakeProducerClient()
    consumer_client = FakeConsumerClient(
        [FakeMessage("ingest.raw_document_created", b"doc-1", b'{"not":"an envelope"}')]
    )
    consumer = EventConsumer(
        consumer_client,
        EventProducer(producer_client),
        consumer_group="parser",
        stage="parse",
    )

    async def handler(_: EventEnvelope) -> None:
        raise AssertionError("invalid messages must not reach the handler")

    result = await consumer.process_one(handler)

    assert result.status == "deadlettered"
    assert result.deadletter_topic == "ingest.deadletter"
    assert consumer_client.commits == 1
    topic, value, key, _ = producer_client.sent[0]
    assert topic == "ingest.deadletter"
    assert key == b"doc-1"
    deadletter = deserialize_event(value)
    assert deadletter.payload["original_topic"] == "ingest.raw_document_created"
    assert deadletter.payload["retryable"] is False
    assert deadletter.payload["original_value"] == '{"not":"an envelope"}'


async def test_event_consumer_deadletters_permanent_handler_failure_and_commits() -> None:
    event = sample_event()
    producer_client = FakeProducerClient()
    consumer_client = FakeConsumerClient(
        [FakeMessage("graph.node_upsert", b"Drug:1", serialize_event(event))]
    )
    consumer = EventConsumer(
        consumer_client,
        EventProducer(producer_client),
        consumer_group="graph-writer",
        stage="write-graph",
    )

    async def handler(_: EventEnvelope) -> None:
        raise PermanentEventError("bad graph command", error_type="invalid_graph_command")

    result = await consumer.process_one(handler)

    assert result.status == "deadlettered"
    assert result.deadletter_topic == "graph.deadletter"
    assert consumer_client.commits == 1
    topic, value, _, _ = producer_client.sent[0]
    assert topic == "graph.deadletter"
    deadletter = deserialize_event(value)
    assert deadletter.causation_id == event.event_id
    assert deadletter.correlation_id == event.correlation_id
    assert deadletter.payload["error_type"] == "invalid_graph_command"
    assert deadletter.payload["original_event"]["event_id"] == str(event.event_id)


async def test_event_consumer_does_not_commit_transient_handler_failure() -> None:
    event = sample_event()
    producer_client = FakeProducerClient()
    consumer_client = FakeConsumerClient(
        [FakeMessage("ingest.raw_document_created", b"doc-1", serialize_event(event))]
    )
    consumer = EventConsumer(
        consumer_client,
        EventProducer(producer_client),
        consumer_group="parser",
        stage="parse",
    )

    async def handler(_: EventEnvelope) -> None:
        raise RuntimeError("transient database outage")

    with pytest.raises(RuntimeError, match="transient database outage"):
        await consumer.process_one(handler)

    assert consumer_client.commits == 0
    assert producer_client.sent == []
