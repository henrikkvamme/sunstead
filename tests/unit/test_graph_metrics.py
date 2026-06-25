from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.models.graph import (
    GraphNodeUpsert,
    GraphRelationshipUpsert,
    RelationshipProvenance,
)
from supply_intel.observability.graph_metrics import (
    GRAPH_NODES_TOTAL,
    GRAPH_RELATIONSHIPS_TOTAL,
    collect_file_graph_metrics,
    collect_neo4j_graph_metrics,
)

EXPECTED_GRAPH_NODE_COUNT = 7
EXPECTED_GRAPH_RELATIONSHIP_COUNT = 11
EXPECTED_GRAPH_METRIC_COUNT = 2
EXPECTED_FILE_GRAPH_NODE_COUNT = 2
EXPECTED_FILE_GRAPH_RELATIONSHIP_COUNT = 1


class FakeGraphMetricReader:
    async def run_read_query(
        self,
        cypher: str,
        parameters: dict[str, object],
    ) -> list[dict[str, object]]:
        assert parameters == {}
        if "MATCH (n)" in cypher:
            return [{"value": EXPECTED_GRAPH_NODE_COUNT}]
        return [{"value": EXPECTED_GRAPH_RELATIONSHIP_COUNT}]


async def test_collect_neo4j_graph_metrics_builds_provenance_backed_metrics() -> None:
    observed_at = datetime(2026, 6, 25, 9, 0, tzinfo=UTC)

    metrics = await collect_neo4j_graph_metrics(
        FakeGraphMetricReader(),
        observed_at=observed_at,
    )

    by_name = {metric.metric_name: metric for metric in metrics}
    assert set(by_name) == {GRAPH_NODES_TOTAL, GRAPH_RELATIONSHIPS_TOTAL}
    assert by_name[GRAPH_NODES_TOTAL].metric_value == EXPECTED_GRAPH_NODE_COUNT
    assert by_name[GRAPH_RELATIONSHIPS_TOTAL].metric_value == EXPECTED_GRAPH_RELATIONSHIP_COUNT
    assert by_name[GRAPH_NODES_TOTAL].service == "neo4j"
    assert by_name[GRAPH_NODES_TOTAL].unit == "count"
    assert by_name[GRAPH_NODES_TOTAL].observed_at == observed_at
    assert by_name[GRAPH_NODES_TOTAL].tags["metric_scope"] == "graph_growth"
    assert by_name[GRAPH_NODES_TOTAL].metadata["provenance"] == "neo4j_read_query"
    assert by_name[GRAPH_NODES_TOTAL].idempotency_key.endswith(observed_at.isoformat())


def test_collect_file_graph_metrics_counts_unique_local_graph_upserts(tmp_path: Path) -> None:
    observed_at = datetime(2026, 6, 25, 9, 0, tzinfo=UTC)
    _write_local_graph_upserts(tmp_path)

    metrics = collect_file_graph_metrics(tmp_path, observed_at=observed_at)

    by_name = {metric.metric_name: metric for metric in metrics}
    assert set(by_name) == {GRAPH_NODES_TOTAL, GRAPH_RELATIONSHIPS_TOTAL}
    assert by_name[GRAPH_NODES_TOTAL].metric_value == EXPECTED_FILE_GRAPH_NODE_COUNT
    assert by_name[GRAPH_RELATIONSHIPS_TOTAL].metric_value == EXPECTED_FILE_GRAPH_RELATIONSHIP_COUNT
    assert by_name[GRAPH_NODES_TOTAL].service == "file-graph"
    assert by_name[GRAPH_NODES_TOTAL].unit == "count"
    assert by_name[GRAPH_NODES_TOTAL].observed_at == observed_at
    assert by_name[GRAPH_NODES_TOTAL].tags["datasource"] == "file_graph"
    assert by_name[GRAPH_NODES_TOTAL].metadata["data_dir"] == str(tmp_path)
    assert by_name[GRAPH_NODES_TOTAL].metadata["provenance"] == "local_graph_upsert_jsonl"
    assert by_name[GRAPH_NODES_TOTAL].idempotency_key.endswith(observed_at.isoformat())


def test_record_graph_metrics_cli_passes_backend_and_data_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    observed_at = datetime(2026, 6, 25, 9, 0, tzinfo=UTC)
    calls: list[dict[str, object]] = []

    async def fake_record_graph_metrics(settings, **kwargs):
        del settings
        calls.append(kwargs)
        return {
            "backend": kwargs["backend"],
            "metrics_seen": EXPECTED_GRAPH_METRIC_COUNT,
            "metrics_created": EXPECTED_GRAPH_METRIC_COUNT,
            "metrics": [],
        }

    monkeypatch.setattr("supply_intel.cli._record_graph_metrics", fake_record_graph_metrics)

    result = CliRunner().invoke(
        app,
        [
            "record-graph-metrics",
            "--backend",
            "file",
            "--source",
            "file",
            "--data-dir",
            str(tmp_path),
            "--observed-at",
            observed_at.isoformat(),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["metrics_created"] == EXPECTED_GRAPH_METRIC_COUNT
    assert calls[0]["backend"] == "file"
    assert calls[0]["source"] == "file"
    assert calls[0]["data_dir"] == tmp_path
    assert calls[0]["observed_at"] == observed_at


def test_record_graph_metrics_cli_writes_file_backed_graph_metrics(tmp_path: Path) -> None:
    observed_at = datetime(2026, 6, 25, 9, 0, tzinfo=UTC)
    _write_local_graph_upserts(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "record-graph-metrics",
            "--backend",
            "file",
            "--source",
            "file",
            "--data-dir",
            str(tmp_path),
            "--observed-at",
            observed_at.isoformat(),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["backend"] == "file"
    assert payload["source"] == "file"
    assert payload["metrics_created"] == EXPECTED_GRAPH_METRIC_COUNT
    assert payload["metrics_seen"] == EXPECTED_GRAPH_METRIC_COUNT
    by_name = {metric["metric_name"]: metric for metric in payload["metrics"]}
    assert by_name[GRAPH_NODES_TOTAL]["metric_value"] == EXPECTED_FILE_GRAPH_NODE_COUNT
    assert (
        by_name[GRAPH_RELATIONSHIPS_TOTAL]["metric_value"] == EXPECTED_FILE_GRAPH_RELATIONSHIP_COUNT
    )

    ops_metrics = [
        json.loads(line) for line in (tmp_path / "ops_metrics.jsonl").read_text().splitlines()
    ]
    assert len(ops_metrics) == EXPECTED_GRAPH_METRIC_COUNT
    assert {row["service"] for row in ops_metrics} == {"file-graph"}


def _write_local_graph_upserts(data_dir: Path) -> None:
    store = FileEvidenceStore(data_dir)
    source_document_id = uuid4()
    evidence_span_id = uuid4()
    extraction_run_id = uuid4()
    store.write_graph_node(
        GraphNodeUpsert(
            graph_node_key="drug:carboplatin",
            labels=["Drug"],
            properties={"name": "Carboplatin"},
            source_document_id=source_document_id,
            evidence_span_id=evidence_span_id,
            extraction_run_id=extraction_run_id,
            confidence=0.96,
        )
    )
    store.write_graph_node(
        GraphNodeUpsert(
            graph_node_key="manufacturer:example-pharma",
            labels=["Manufacturer"],
            properties={"name": "Example Pharma"},
            source_document_id=source_document_id,
            evidence_span_id=evidence_span_id,
            extraction_run_id=extraction_run_id,
            confidence=0.91,
        )
    )
    store.write_graph_node(
        GraphNodeUpsert(
            graph_node_key="drug:carboplatin",
            labels=["Drug"],
            properties={"name": "Carboplatin"},
            source_document_id=uuid4(),
            evidence_span_id=evidence_span_id,
            extraction_run_id=extraction_run_id,
            confidence=0.89,
        )
    )
    store.write_graph_relationship(
        GraphRelationshipUpsert(
            relationship_key="drug:carboplatin|MANUFACTURED_BY|manufacturer:example-pharma",
            from_key="drug:carboplatin",
            to_key="manufacturer:example-pharma",
            relationship_type="MANUFACTURED_BY",
            properties=RelationshipProvenance(
                confidence=0.9,
                source_document_id=source_document_id,
                evidence_span_id=evidence_span_id,
                extraction_run_id=extraction_run_id,
                source_name="unit-test",
                source_url="https://example.test/source",
                method="fixture",
            ),
        )
    )
