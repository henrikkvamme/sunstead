from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.infra.graph_backfill import backfill_graph
from supply_intel.graph.insights import summarize_file_graph
from supply_intel.settings import Settings

EXPECTED_GRAPH_NODES = 7
EXPECTED_GRAPH_RELATIONSHIPS = 6
EXPECTED_RAW_DOCUMENTS = 2
EXPECTED_RISK_CASES = 1
EXPECTED_RISK_ALERTS = 1


def test_summarize_file_graph_reports_demo_ready_coverage(tmp_path: Path) -> None:
    _seed_graph(tmp_path)

    summary = summarize_file_graph(tmp_path, top=5)

    assert summary.graph_nodes == EXPECTED_GRAPH_NODES
    assert summary.graph_relationships == EXPECTED_GRAPH_RELATIONSHIPS
    assert summary.source_coverage.raw_documents == EXPECTED_RAW_DOCUMENTS
    assert summary.risk_coverage.risk_cases == EXPECTED_RISK_CASES
    assert summary.risk_coverage.risk_alerts == EXPECTED_RISK_ALERTS
    assert summary.provenance.nodes_with_source_document > 0
    assert summary.provenance.relationships_with_source_document > 0
    assert {bucket.key for bucket in summary.label_counts} >= {"Drug", "Manufacturer"}
    assert {bucket.key for bucket in summary.relationship_type_counts} >= {
        "HAS_NDC",
        "MANUFACTURED_BY",
    }
    assert summary.top_hubs
    assert summary.demo_queries
    assert all("MATCH" in query.cypher for query in summary.demo_queries)


def test_graph_insights_cli_prints_summary(tmp_path: Path) -> None:
    _seed_graph(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "graph-insights",
            "--data-dir",
            str(tmp_path),
            "--top",
            "3",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["data_dir"] == str(tmp_path)
    assert payload["graph_nodes"] == EXPECTED_GRAPH_NODES
    assert payload["graph_relationships"] == EXPECTED_GRAPH_RELATIONSHIPS
    assert len(payload["label_counts"]) <= 3
    assert payload["risk_coverage"]["risk_cases"] == EXPECTED_RISK_CASES
    assert payload["demo_queries"][0]["title"] == "Label coverage"


def _seed_graph(data_dir: Path) -> None:
    backfill_graph(
        settings=Settings(data_dir=data_dir),
        mode="fixture",
        source_ids={"openfda_drug_ndc", "fda_drug_shortages"},
        target_graph_nodes=EXPECTED_GRAPH_NODES,
        max_documents_per_source=1,
        max_rounds=1,
    )
