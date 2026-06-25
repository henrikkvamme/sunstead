from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.infra.demo_prepare import prepare_demo
from supply_intel.observability.graph_metrics import GRAPH_NODES_TOTAL, GRAPH_RELATIONSHIPS_TOTAL
from supply_intel.settings import Settings

EXPECTED_SELECTED_SOURCES = 2
EXPECTED_GRAPH_NODES = 7
EXPECTED_GRAPH_RELATIONSHIPS = 6
EXPECTED_GRAPH_METRICS = 2
EXPECTED_RISK_CASES = 1


def test_prepare_demo_refreshes_sources_exports_snapshot_and_records_metrics(
    tmp_path: Path,
) -> None:
    observed_at = datetime(2026, 6, 25, 9, 0, tzinfo=UTC)
    snapshot_output = tmp_path / "public" / "platform-demo" / "supply-chain-graph.json"

    summary = prepare_demo(
        settings=Settings(data_dir=tmp_path),
        source_ids={"openfda_drug_ndc", "fda_drug_shortages"},
        max_documents_per_source=1,
        snapshot_output_path=snapshot_output,
        observed_at=observed_at,
    )

    assert summary.refresh.selected_sources == EXPECTED_SELECTED_SOURCES
    assert summary.refresh.succeeded_sources == EXPECTED_SELECTED_SOURCES
    assert summary.refresh.store_counts["risk_cases"] == EXPECTED_RISK_CASES
    assert summary.graph_snapshot.output_path == str(snapshot_output)
    assert summary.graph_snapshot.data_mode == "file_snapshot"
    assert summary.graph_snapshot.graph_nodes == EXPECTED_GRAPH_NODES
    assert summary.graph_snapshot.graph_relationships == EXPECTED_GRAPH_RELATIONSHIPS
    assert summary.graph_metrics.metrics_seen == EXPECTED_GRAPH_METRICS
    assert summary.graph_metrics.metrics_created == EXPECTED_GRAPH_METRICS
    assert summary.graph_metrics.metric_values[GRAPH_NODES_TOTAL] == EXPECTED_GRAPH_NODES
    assert (
        summary.graph_metrics.metric_values[GRAPH_RELATIONSHIPS_TOTAL]
        == EXPECTED_GRAPH_RELATIONSHIPS
    )
    assert summary.readiness.demo_ready_now is True
    graph_check = next(check for check in summary.readiness.checks if check.area == "graph_data")
    assert graph_check.status == "ready"
    assert graph_check.details["source"] == "file"
    assert snapshot_output.exists()
    snapshot = json.loads(snapshot_output.read_text(encoding="utf-8"))
    assert snapshot["summary"]["graphNodes"] == EXPECTED_GRAPH_NODES
    ops_metrics = [
        json.loads(line) for line in (tmp_path / "ops_metrics.jsonl").read_text().splitlines()
    ]
    assert len(ops_metrics) == EXPECTED_GRAPH_METRICS
    assert "devme up -d" in summary.recommended_commands


def test_prepare_demo_cli_writes_repeatable_demo_artifacts(tmp_path: Path) -> None:
    observed_at = datetime(2026, 6, 25, 9, 0, tzinfo=UTC)
    snapshot_output = tmp_path / "snapshot.json"

    result = CliRunner().invoke(
        app,
        [
            "prepare-demo",
            "--data-dir",
            str(tmp_path),
            "--snapshot-output",
            str(snapshot_output),
            "--source-id",
            "openfda_drug_ndc",
            "--source-id",
            "fda_drug_shortages",
            "--max-documents-per-source",
            "1",
            "--observed-at",
            observed_at.isoformat(),
            "--require-ready",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["data_dir"] == str(tmp_path)
    assert payload["snapshot_output_path"] == str(snapshot_output)
    assert payload["refresh"]["selected_sources"] == EXPECTED_SELECTED_SOURCES
    assert payload["graph_snapshot"]["graph_nodes"] == EXPECTED_GRAPH_NODES
    assert payload["graph_metrics"]["metrics_created"] == EXPECTED_GRAPH_METRICS
    assert payload["readiness"]["demo_ready_now"] is True
    assert snapshot_output.exists()


def test_prepare_demo_cli_rejects_unknown_priority(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "prepare-demo",
            "--data-dir",
            str(tmp_path),
            "--priority",
            "P9",
        ],
    )

    assert result.exit_code != 0
    assert "Unsupported source priority" in result.output
