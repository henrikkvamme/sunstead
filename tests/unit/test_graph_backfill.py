from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.infra.graph_backfill import backfill_graph
from supply_intel.settings import Settings

SELECTED_BACKFILL_SOURCE_COUNT = 2
EXPECTED_GRAPH_NODES = 7
EXPECTED_GRAPH_RELATIONSHIPS = 6


def test_backfill_graph_fixture_reaches_target_and_returns_next_steps(
    tmp_path: Path,
) -> None:
    summary = backfill_graph(
        settings=Settings(data_dir=tmp_path),
        mode="fixture",
        source_ids={"openfda_drug_ndc", "fda_drug_shortages"},
        target_graph_nodes=EXPECTED_GRAPH_NODES,
        max_documents_per_source=1,
        max_rounds=2,
    )

    assert summary.mode == "fixture"
    assert summary.selected_sources == SELECTED_BACKFILL_SOURCE_COUNT
    assert summary.rounds_completed == 1
    assert summary.target_met is True
    assert summary.initial_graph_nodes == 0
    assert summary.final_graph_nodes == EXPECTED_GRAPH_NODES
    assert summary.final_graph_relationships == EXPECTED_GRAPH_RELATIONSHIPS
    assert summary.graph_nodes_added == EXPECTED_GRAPH_NODES
    assert summary.succeeded_source_runs == SELECTED_BACKFILL_SOURCE_COUNT
    assert summary.failed_source_runs == 0
    assert summary.totals["raw_documents_created"] == SELECTED_BACKFILL_SOURCE_COUNT
    assert summary.store_counts["raw_documents"] == SELECTED_BACKFILL_SOURCE_COUNT
    assert summary.event_topics["graph.node_upsert"] >= EXPECTED_GRAPH_NODES
    rendered_commands = " ".join(summary.recommended_commands)
    assert "sync-graph-view" in rendered_commands
    assert "run-risk-engine" in rendered_commands
    assert "export-graph-snapshot" in rendered_commands
    assert "sync-postgres-evidence" in rendered_commands


def test_backfill_graph_stops_after_target_is_met(tmp_path: Path) -> None:
    summary = backfill_graph(
        settings=Settings(data_dir=tmp_path),
        mode="fixture",
        source_ids={"openfda_drug_ndc", "fda_drug_shortages"},
        target_graph_nodes=1,
        max_documents_per_source=1,
        max_rounds=3,
    )

    assert summary.target_met is True
    assert summary.selected_sources == SELECTED_BACKFILL_SOURCE_COUNT
    assert len(summary.source_results) == 1
    assert summary.rounds_completed == 1
    assert summary.final_graph_nodes >= 1


def test_backfill_graph_cli_runs_fixture_mode(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "backfill-graph",
            "--data-dir",
            str(tmp_path),
            "--mode",
            "fixture",
            "--source-id",
            "openfda_drug_ndc",
            "--source-id",
            "fda_drug_shortages",
            "--target-graph-nodes",
            str(EXPECTED_GRAPH_NODES),
            "--max-documents-per-source",
            "1",
            "--max-rounds",
            "2",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["data_dir"] == str(tmp_path)
    assert payload["target_met"] is True
    assert payload["final_graph_nodes"] == EXPECTED_GRAPH_NODES
    assert payload["selected_sources"] == SELECTED_BACKFILL_SOURCE_COUNT
    assert (tmp_path / "graph_node_upserts.jsonl").exists()


def test_backfill_graph_cli_rejects_unknown_priority(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "backfill-graph",
            "--data-dir",
            str(tmp_path),
            "--priority",
            "P9",
        ],
    )

    assert result.exit_code != 0
    assert "Unsupported source priority" in result.output


def test_sync_graph_view_cli_records_file_metrics_and_exports_snapshot(
    tmp_path: Path,
) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    backfill_graph(
        settings=Settings(data_dir=tmp_path),
        mode="fixture",
        source_ids={"openfda_drug_ndc", "fda_drug_shortages"},
        target_graph_nodes=EXPECTED_GRAPH_NODES,
        max_documents_per_source=1,
        max_rounds=1,
    )

    result = CliRunner().invoke(
        app,
        [
            "sync-graph-view",
            "--data-dir",
            str(tmp_path),
            "--snapshot-source",
            "file",
            "--output",
            str(snapshot_path),
            "--limit",
            "50",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["data_dir"] == str(tmp_path)
    assert payload["apply_neo4j"] is False
    assert payload["snapshot_source"] == "file"
    assert payload["neo4j_replay"] is None
    assert payload["graph_metrics"]["source"] == "file"
    assert payload["graph_snapshot"]["output_path"] == str(snapshot_path)
    assert payload["graph_snapshot"]["graph_nodes"] == EXPECTED_GRAPH_NODES
    assert payload["graph_snapshot"]["graph_relationships"] == EXPECTED_GRAPH_RELATIONSHIPS
    assert snapshot_path.exists()
    assert (tmp_path / "ops_metrics.jsonl").exists()
