from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.models.infra import OperationalMetric

GRAPH_NODES_TOTAL = "graph_nodes_total"
GRAPH_RELATIONSHIPS_TOTAL = "graph_relationships_total"

GRAPH_METRIC_QUERIES: dict[str, str] = {
    GRAPH_NODES_TOTAL: "MATCH (n) RETURN count(n) AS value",
    GRAPH_RELATIONSHIPS_TOTAL: "MATCH ()-[r]->() RETURN count(r) AS value",
}


class GraphMetricReader(Protocol):
    async def run_read_query(
        self,
        cypher: str,
        parameters: dict[str, object],
    ) -> list[dict[str, object]]: ...


async def collect_neo4j_graph_metrics(
    reader: GraphMetricReader,
    *,
    observed_at: datetime | None = None,
) -> list[OperationalMetric]:
    observed = observed_at or datetime.now(UTC)
    metrics: list[OperationalMetric] = []
    for metric_name, cypher in GRAPH_METRIC_QUERIES.items():
        rows = await reader.run_read_query(cypher, {})
        metrics.append(
            neo4j_count_metric(
                metric_name=metric_name,
                metric_value=_count_value(rows, metric_name=metric_name),
                observed_at=observed,
                cypher=cypher,
            )
        )
    return metrics


def collect_file_graph_metrics(
    data_dir: Path,
    *,
    observed_at: datetime | None = None,
) -> list[OperationalMetric]:
    observed = observed_at or datetime.now(UTC)
    store = FileEvidenceStore(data_dir)
    node_count = len(
        {
            str(row.get("graph_node_key"))
            for row in store.read_collection("graph_node_upserts")
            if row.get("graph_node_key")
        }
    )
    relationship_count = len(
        {
            str(row.get("relationship_key"))
            for row in store.read_collection("graph_relationship_upserts")
            if row.get("relationship_key")
        }
    )
    return [
        file_graph_count_metric(
            metric_name=GRAPH_NODES_TOTAL,
            metric_value=node_count,
            observed_at=observed,
            data_dir=data_dir,
        ),
        file_graph_count_metric(
            metric_name=GRAPH_RELATIONSHIPS_TOTAL,
            metric_value=relationship_count,
            observed_at=observed,
            data_dir=data_dir,
        ),
    ]


def neo4j_count_metric(
    *,
    metric_name: str,
    metric_value: float,
    observed_at: datetime,
    cypher: str,
) -> OperationalMetric:
    return OperationalMetric(
        metric_name=metric_name,
        metric_value=metric_value,
        unit="count",
        service="neo4j",
        observed_at=observed_at,
        idempotency_key=f"ops.metrics:neo4j:{metric_name}:{observed_at.isoformat()}",
        tags={"metric_scope": "graph_growth", "datasource": "neo4j"},
        metadata={"cypher": cypher, "provenance": "neo4j_read_query"},
    )


def file_graph_count_metric(
    *,
    metric_name: str,
    metric_value: float,
    observed_at: datetime,
    data_dir: Path,
) -> OperationalMetric:
    return OperationalMetric(
        metric_name=metric_name,
        metric_value=metric_value,
        unit="count",
        service="file-graph",
        observed_at=observed_at,
        idempotency_key=f"ops.metrics:file_graph:{metric_name}:{observed_at.isoformat()}",
        tags={"metric_scope": "graph_growth", "datasource": "file_graph"},
        metadata={
            "data_dir": str(data_dir),
            "provenance": "local_graph_upsert_jsonl",
        },
    )


def _count_value(rows: list[dict[str, object]], *, metric_name: str) -> float:
    if not rows:
        raise ValueError(f"Neo4j graph metric query returned no rows for {metric_name}")
    row = rows[0]
    value = _mapping_value(row, "value")
    if value is None:
        value = _mapping_value(row, "count")
    if value is None:
        raise ValueError(f"Neo4j graph metric query returned no count for {metric_name}")
    return float(str(value))


def _mapping_value(row: Mapping[str, object], key: str) -> object | None:
    return row.get(key)
