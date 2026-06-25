from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.graph.explorer_snapshot import write_explorer_snapshot_from_file_store
from supply_intel.infra.demo_readiness import DemoReadinessReport, inspect_demo_readiness
from supply_intel.infra.demo_refresh import (
    DemoDataRefreshSummary,
    SourcePriority,
    refresh_demo_data,
)
from supply_intel.models.base import StrictBaseModel
from supply_intel.observability.graph_metrics import (
    GRAPH_NODES_TOTAL,
    GRAPH_RELATIONSHIPS_TOTAL,
    collect_file_graph_metrics,
)
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_all_source_configs


class DemoGraphSnapshotSummary(StrictBaseModel):
    output_path: str
    generated_at: str
    data_mode: str
    exported_nodes: int
    exported_edges: int
    graph_nodes: int
    graph_relationships: int


class DemoGraphMetricSummary(StrictBaseModel):
    backend: str = "file"
    source: str = "file"
    observed_at: datetime
    metrics_seen: int
    metrics_created: int
    metric_values: dict[str, float] = Field(default_factory=dict)


class DemoPreparationSummary(StrictBaseModel):
    data_dir: str
    snapshot_output_path: str
    refresh: DemoDataRefreshSummary
    graph_snapshot: DemoGraphSnapshotSummary
    graph_metrics: DemoGraphMetricSummary
    readiness: DemoReadinessReport
    recommended_commands: list[str]


def prepare_demo(
    *,
    settings: Settings,
    source_ids: set[str] | None = None,
    priorities: set[SourcePriority] | None = None,
    max_documents_per_source: int = 1,
    fail_fast: bool = False,
    snapshot_output_path: Path = Path("public/platform-demo/supply-chain-graph.json"),
    snapshot_limit: int = 500,
    observed_at: datetime | None = None,
    source_dir: Path | None = None,
) -> DemoPreparationSummary:
    if snapshot_limit < 1:
        raise ValueError("snapshot_limit must be greater than zero.")
    observed = observed_at or datetime.now(UTC)
    refresh = refresh_demo_data(
        settings=settings,
        source_ids=source_ids,
        priorities=priorities,
        max_documents_per_source=max_documents_per_source,
        fail_fast=fail_fast,
        source_dir=source_dir,
    )
    snapshot = write_explorer_snapshot_from_file_store(
        settings.data_dir,
        snapshot_output_path,
        limit=snapshot_limit,
    )
    metrics = collect_file_graph_metrics(settings.data_dir, observed_at=observed)
    store = FileEvidenceStore(settings.data_dir)
    metrics_created = sum(1 for metric in metrics if store.write_operational_metric(metric))
    graph_counts = {
        GRAPH_NODES_TOTAL: int(snapshot.summary.graphNodes),
        GRAPH_RELATIONSHIPS_TOTAL: int(snapshot.summary.graphRelationships),
    }
    readiness = inspect_demo_readiness(
        settings=settings,
        source_configs=load_all_source_configs(source_dir or settings.source_dir),
        graph_counts=graph_counts,
        graph_count_source="file",
    )
    return DemoPreparationSummary(
        data_dir=str(settings.data_dir),
        snapshot_output_path=str(snapshot_output_path),
        refresh=refresh,
        graph_snapshot=DemoGraphSnapshotSummary(
            output_path=str(snapshot_output_path),
            generated_at=snapshot.generatedAt,
            data_mode=snapshot.dataStatus.mode,
            exported_nodes=len(snapshot.nodes),
            exported_edges=len(snapshot.edges),
            graph_nodes=snapshot.summary.graphNodes,
            graph_relationships=snapshot.summary.graphRelationships,
        ),
        graph_metrics=DemoGraphMetricSummary(
            observed_at=observed,
            metrics_seen=len(metrics),
            metrics_created=metrics_created,
            metric_values={metric.metric_name: metric.metric_value for metric in metrics},
        ),
        readiness=readiness,
        recommended_commands=_recommended_commands(settings.data_dir, snapshot_output_path),
    )


def _recommended_commands(data_dir: Path, snapshot_output_path: Path) -> list[str]:
    return [
        f"uv run platform demo-readiness --local-graph --data-dir {data_dir}",
        "devme up -d",
        "devme url web",
        (
            "uv run platform export-graph-snapshot "
            f"--source file --data-dir {data_dir} "
            f"--output {snapshot_output_path} --limit 500"
        ),
        f"uv run platform import-dashboard-graph-chat-audit --data-dir {data_dir}",
        (
            "uv run platform publish-events "
            f"--data-dir {data_dir} --event-type dashboard.graph_chat_answered"
        ),
    ]
