from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.events.envelope import build_event, deserialize_event
from supply_intel.events.outbox import (
    publish_outbox_events_to_kafka,
    select_outbox_events,
    summarize_outbox_selection,
)
from supply_intel.models.kafka import (
    DashboardGraphChatAnsweredPayload,
    RawDocumentCreatedPayload,
)
from supply_intel.settings import Settings


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
        return {"topic": topic}


def test_select_outbox_events_filters_by_type_and_limit(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    raw_event = _raw_document_event()
    graph_chat_event = _dashboard_graph_chat_event()
    store.write_event(raw_event)
    store.write_event(graph_chat_event)

    selected = select_outbox_events(
        store=store,
        event_type="dashboard.graph_chat_answered",
        limit=1,
    )
    summary = summarize_outbox_selection(
        data_dir=str(tmp_path),
        events=selected,
    )

    assert [event.event_id for event in selected] == [graph_chat_event.event_id]
    assert summary.selected == 1
    assert summary.published == 0
    assert summary.topics == {"dashboard.graph_chat_answered": 1}


def test_publish_events_cli_requires_selector_unless_all() -> None:
    result = CliRunner().invoke(app, ["publish-events"])

    assert result.exit_code != 0
    assert "--event-id" in result.output
    assert "--all" in result.output


def test_publish_events_cli_dry_run_lists_selected_events(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    event = _dashboard_graph_chat_event()
    store.write_event(event)

    result = CliRunner().invoke(
        app,
        [
            "publish-events",
            "--data-dir",
            str(tmp_path),
            "--event-type",
            "dashboard.graph_chat_answered",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["publish_kafka"] is False
    assert payload["selected"] == 1
    assert payload["published"] == 0
    assert payload["event_ids"] == [str(event.event_id)]
    assert payload["topics"] == {"dashboard.graph_chat_answered": 1}


async def test_publish_outbox_events_to_kafka_uses_event_key_and_records_metric(
    tmp_path: Path,
) -> None:
    store = FileEvidenceStore(tmp_path)
    event = _dashboard_graph_chat_event()
    store.write_event(event)
    selected = select_outbox_events(store=store, event_ids=[str(event.event_id)])
    producer = FakeProducerClient()

    summary = await publish_outbox_events_to_kafka(
        settings=Settings(data_dir=tmp_path),
        store=store,
        events=selected,
        producer_client=producer,
    )

    assert summary.publish_kafka is True
    assert summary.selected == 1
    assert summary.published == 1
    assert summary.metrics_recorded == 1
    assert summary.event_ids == [str(event.event_id)]
    topic, value, key, headers = producer.sent[0]
    assert topic == "dashboard.graph_chat_answered"
    assert key == str(event.payload["audit_id"]).encode("utf-8")
    assert deserialize_event(value).event_id == event.event_id
    assert headers is not None
    assert ("event_type", b"dashboard.graph_chat_answered") in headers
    metric_topic, metric_value, metric_key, _ = producer.sent[1]
    metric = deserialize_event(metric_value)
    assert metric_topic == "ops.metrics"
    assert metric_key == b"events_produced_total"
    assert metric.payload["topic"] == "dashboard.graph_chat_answered"
    metric_rows = store.read_collection("ops_metrics")
    assert len(metric_rows) == 1
    assert metric_rows[0]["topic"] == "dashboard.graph_chat_answered"


def test_select_outbox_events_reports_missing_exact_ids(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)

    try:
        select_outbox_events(store=store, event_ids=[str(uuid4())])
    except ValueError as exc:
        assert "Outbox events not found" in str(exc)
    else:
        raise AssertionError("missing exact event ids should fail")


def _raw_document_event():
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
        idempotency_key=f"openfda_drug_ndc:{raw_document_id}:hash-1",
        payload=payload.model_dump(mode="json"),
    )


def _dashboard_graph_chat_event():
    audit_id = UUID("11223344-5566-7788-99aa-bbccddeeff00")
    payload = DashboardGraphChatAnsweredPayload(
        audit_id=audit_id,
        selected_node_id="platform:Drug:ndc_product:0002-8215",
        requested_node_id="platform:Drug:ndc_product:0002-8215",
        input_hash="a" * 64,
        input_length=24,
        output_hash="b" * 64,
        output_schema="SupplyGraphQuestionResponse",
        output_schema_version=1,
        graph_stats={"nodes": 542, "edges": 334, "platform_nodes": 500},
        neighbor_node_ids=["platform:NDC:product:0002-8215"],
        source_refs=[
            {
                "meta": "source-run-1",
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
    return build_event(
        event_type="dashboard.graph_chat_answered",
        service="dashboard-graph-chat",
        source_id="dashboard_graph_chat_audit_jsonl",
        idempotency_key=f"dashboard.graph_chat_answered:{audit_id}",
        payload=payload.model_dump(mode="json"),
    )
