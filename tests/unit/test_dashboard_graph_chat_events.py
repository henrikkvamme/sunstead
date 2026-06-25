from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.dashboard.graph_chat_events import (
    dashboard_graph_chat_event_from_audit,
    dashboard_graph_chat_payload_from_audit,
    import_dashboard_graph_chat_audit_events,
)
from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.events.outbox import event_key

EXPECTED_SOURCE_GRAPH_NODES = 546
EXPECTED_SOURCE_GRAPH_RELATIONSHIPS = 324


def test_dashboard_graph_chat_audit_maps_to_typed_payload_and_event_envelope() -> None:
    audit = _graph_chat_audit_row()

    payload = dashboard_graph_chat_payload_from_audit(audit)
    event = dashboard_graph_chat_event_from_audit(audit)

    assert payload.audit_id == UUID(audit["auditId"])
    assert payload.graph_stats == {
        "curated_nodes": 42,
        "edges": 334,
        "live_sources": 8,
        "nodes": 542,
        "platform_edges": 276,
        "platform_nodes": 500,
        "source_graph_nodes": EXPECTED_SOURCE_GRAPH_NODES,
        "source_graph_relationships": EXPECTED_SOURCE_GRAPH_RELATIONSHIPS,
        "watch_signals": 17,
    }
    assert payload.metadata["snapshot_mode"] == "neo4j_snapshot"
    assert payload.metadata["snapshot_generated_at"] == "2026-06-25T10:50:00Z"
    assert payload.metadata["source_graph_nodes"] == EXPECTED_SOURCE_GRAPH_NODES
    assert payload.metadata["source_graph_relationships"] == EXPECTED_SOURCE_GRAPH_RELATIONSHIPS
    assert payload.safety == {
        "advice_scope": "supply_chain_intelligence_only",
        "clinical_advice": False,
        "patient_identifiable_data": False,
    }
    assert event.event_type == "dashboard.graph_chat_answered"
    assert event.idempotency_key == f"dashboard.graph_chat_answered:{audit['auditId']}"
    assert event.source.service == "dashboard-graph-chat"
    assert event.payload["audit_id"] == audit["auditId"]
    assert event_key(event) == audit["auditId"]
    assert event.emitted_at.isoformat() == "2026-06-25T10:54:23+00:00"


def test_dashboard_graph_chat_audit_import_writes_idempotent_events(tmp_path: Path) -> None:
    audit_path = tmp_path / "dashboard_graph_chat_audit.jsonl"
    audit_path.write_text(json.dumps(_graph_chat_audit_row()) + "\n", encoding="utf-8")
    store = FileEvidenceStore(tmp_path)

    first = import_dashboard_graph_chat_audit_events(audit_path=audit_path, store=store)
    second = import_dashboard_graph_chat_audit_events(audit_path=audit_path, store=store)

    assert first.audit_rows_seen == 1
    assert first.events_created == 1
    assert first.events_skipped == 0
    assert second.audit_rows_seen == 1
    assert second.events_created == 0
    assert second.events_skipped == 1
    events = _read_jsonl(tmp_path / "events.jsonl")
    assert len(events) == 1
    assert events[0]["event_type"] == "dashboard.graph_chat_answered"
    assert events[0]["payload"]["audit_id"] == _graph_chat_audit_row()["auditId"]


def test_import_dashboard_graph_chat_audit_cli_uses_data_dir_default(tmp_path: Path) -> None:
    audit_path = tmp_path / "dashboard_graph_chat_audit.jsonl"
    audit_path.write_text(json.dumps(_graph_chat_audit_row()) + "\n", encoding="utf-8")
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["import-dashboard-graph-chat-audit", "--data-dir", str(tmp_path)],
    )

    assert result.exit_code == 0
    summary = json.loads(result.output)
    assert summary["audit_rows_seen"] == 1
    assert summary["events_created"] == 1
    assert summary["events_skipped"] == 0
    assert (tmp_path / "events.jsonl").exists()


def _graph_chat_audit_row() -> dict[str, object]:
    return {
        "auditId": "11223344-5566-7788-99aa-bbccddeeff00",
        "auditType": "dashboard.graph_chat_answer",
        "correlationId": "00000000-1111-2222-3333-444444444444",
        "createdAt": "2026-06-25T10:54:23.000Z",
        "eventType": "dashboard.graph_chat_answered",
        "graphStats": {
            "curatedNodes": 42,
            "edges": 334,
            "liveSources": 8,
            "nodes": 542,
            "platformEdges": 276,
            "platformNodes": 500,
            "sourceGraphNodes": EXPECTED_SOURCE_GRAPH_NODES,
            "sourceGraphRelationships": EXPECTED_SOURCE_GRAPH_RELATIONSHIPS,
            "watchSignals": 17,
        },
        "idempotencyKey": "dashboard.graph_chat_answer:input:output",
        "inputHash": "a" * 64,
        "inputLength": 24,
        "metadata": {
            "graphDataMode": "platform_snapshot",
            "liveSources": 8,
            "outputMode": "deterministic_graph_summary",
            "platformEdges": 276,
            "platformNodes": 500,
            "snapshotGeneratedAt": "2026-06-25T10:50:00Z",
            "snapshotMode": "neo4j_snapshot",
            "sourceGraphNodes": EXPECTED_SOURCE_GRAPH_NODES,
            "sourceGraphRelationships": EXPECTED_SOURCE_GRAPH_RELATIONSHIPS,
            "watchSignals": 17,
        },
        "neighborNodeIds": ["platform:NDC:product:0002-8215"],
        "nodeId": "platform:Drug:ndc_product:0002-8215",
        "outputHash": "b" * 64,
        "outputSchema": "SupplyGraphQuestionResponse",
        "outputSchemaVersion": 1,
        "relatedNodeIds": ["platform:Ingredient:insulin-lispro"],
        "safety": {
            "adviceScope": "supply_chain_intelligence_only",
            "clinicalAdvice": False,
            "patientIdentifiableData": False,
        },
        "selectedNodeId": "platform:Drug:ndc_product:0002-8215",
        "service": "dashboard-graph-chat",
        "sourceRefs": [
            {
                "meta": "source-run-1, 2026-06-25T10:54:23Z",
                "title": "HUMALOG platform graph evidence",
                "url": "/platform-demo/supply-chain-graph.json",
            }
        ],
        "status": "succeeded",
        "topic": "dashboard.graph_chat_answered",
    }


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
