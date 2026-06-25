from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.infra.demo_refresh import refresh_demo_data
from supply_intel.settings import Settings

SELECTED_DEMO_SOURCE_COUNT = 2
EXPECTED_RAW_DOCUMENTS = 2
MIN_EXPECTED_CHUNKS = 2
MIN_EXPECTED_GRAPH_NODES = 7
MIN_EXPECTED_GRAPH_RELATIONSHIPS = 6
EXPECTED_RISK_CASES = 1
EXPECTED_RISK_ALERTS = 1


def test_refresh_demo_data_runs_selected_fixture_sources_into_meaningful_store(
    tmp_path: Path,
) -> None:
    summary = refresh_demo_data(
        settings=Settings(data_dir=tmp_path),
        source_ids={"openfda_drug_ndc", "fda_drug_shortages"},
        max_documents_per_source=1,
    )

    assert summary.selected_sources == SELECTED_DEMO_SOURCE_COUNT
    assert summary.succeeded_sources == SELECTED_DEMO_SOURCE_COUNT
    assert summary.failed_sources == 0
    assert summary.totals["raw_documents_created"] == EXPECTED_RAW_DOCUMENTS
    assert summary.totals["chunks_created"] >= MIN_EXPECTED_CHUNKS
    assert summary.totals["graph_nodes"] >= MIN_EXPECTED_GRAPH_NODES
    assert summary.totals["graph_relationships"] >= MIN_EXPECTED_GRAPH_RELATIONSHIPS
    assert summary.store_counts["raw_documents"] == EXPECTED_RAW_DOCUMENTS
    assert summary.store_counts["graph_node_upserts"] >= MIN_EXPECTED_GRAPH_NODES
    assert summary.store_counts["graph_relationship_upserts"] >= MIN_EXPECTED_GRAPH_RELATIONSHIPS
    assert summary.store_counts["risk_cases"] == EXPECTED_RISK_CASES
    assert summary.store_counts["risk_alerts"] == EXPECTED_RISK_ALERTS
    assert summary.event_topics["ingest.raw_document_created"] == EXPECTED_RAW_DOCUMENTS
    assert summary.event_topics["ingest.extraction_completed"] >= MIN_EXPECTED_CHUNKS
    assert summary.event_topics["graph.node_upsert"] >= MIN_EXPECTED_GRAPH_NODES
    assert "run-graph-writer" in " ".join(summary.recommended_commands)


def test_refresh_demo_data_is_idempotent_for_raw_documents_but_reports_store_counts(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path)
    first = refresh_demo_data(
        settings=settings,
        source_ids={"openfda_drug_ndc"},
        max_documents_per_source=1,
    )
    second = refresh_demo_data(
        settings=settings,
        source_ids={"openfda_drug_ndc"},
        max_documents_per_source=1,
    )

    assert first.totals["raw_documents_created"] == 1
    assert second.totals["raw_documents_unchanged"] == 1
    assert second.store_counts["raw_documents"] == 1


def test_refresh_demo_data_cli_filters_sources_and_writes_summary(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "refresh-demo-data",
            "--data-dir",
            str(tmp_path),
            "--source-id",
            "openfda_drug_ndc",
            "--source-id",
            "fda_drug_shortages",
            "--max-documents-per-source",
            "1",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["data_dir"] == str(tmp_path)
    assert payload["selected_sources"] == SELECTED_DEMO_SOURCE_COUNT
    assert payload["succeeded_sources"] == SELECTED_DEMO_SOURCE_COUNT
    assert payload["store_counts"]["risk_cases"] == EXPECTED_RISK_CASES
    assert (tmp_path / "graph_node_upserts.jsonl").exists()


def test_refresh_demo_data_rejects_unknown_priority(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "refresh-demo-data",
            "--data-dir",
            str(tmp_path),
            "--priority",
            "P9",
        ],
    )

    assert result.exit_code != 0
    assert "Unsupported source priority" in result.output
