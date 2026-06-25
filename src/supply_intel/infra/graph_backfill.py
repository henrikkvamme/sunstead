from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.infra.demo_refresh import (
    DEMO_FIXTURE_INGEST_BY_PROFILE,
    DEMO_REFRESH_COLLECTIONS,
    SourcePriority,
)
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.source import SourceConfig, SourceRun
from supply_intel.observability.graph_metrics import GRAPH_NODES_TOTAL, GRAPH_RELATIONSHIPS_TOTAL
from supply_intel.pipeline import process_live_source_run
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_all_source_configs

GraphBackfillMode = Literal["fixture", "live"]
GraphBackfillStatus = Literal["succeeded", "skipped", "failed"]


class GraphBackfillCounts(StrictBaseModel):
    graph_nodes: int
    graph_relationships: int


class GraphBackfillSourceResult(StrictBaseModel):
    round_index: int = Field(ge=1)
    source_id: str
    priority: SourcePriority
    parser_profile: str
    mode: GraphBackfillMode
    status: GraphBackfillStatus
    fixture_path: str | None = None
    stats: dict[str, int] = Field(default_factory=dict)
    reason: str | None = None
    graph_nodes_before: int
    graph_nodes_after: int
    graph_nodes_added: int
    graph_relationships_before: int
    graph_relationships_after: int
    graph_relationships_added: int


class GraphBackfillSummary(StrictBaseModel):
    mode: GraphBackfillMode
    data_dir: str
    requested_source_ids: list[str] = Field(default_factory=list)
    priorities: list[SourcePriority] = Field(default_factory=list)
    target_graph_nodes: int
    max_documents_per_source: int
    max_rounds: int
    selected_sources: int
    rounds_completed: int
    target_met: bool
    initial_graph_nodes: int
    initial_graph_relationships: int
    final_graph_nodes: int
    final_graph_relationships: int
    graph_nodes_added: int
    graph_relationships_added: int
    succeeded_source_runs: int
    skipped_source_runs: int
    failed_source_runs: int
    totals: dict[str, int]
    store_counts: dict[str, int]
    event_topics: dict[str, int]
    source_results: list[GraphBackfillSourceResult]
    recommended_commands: list[str]


def backfill_graph(
    *,
    settings: Settings,
    mode: GraphBackfillMode = "fixture",
    source_ids: set[str] | None = None,
    priorities: set[SourcePriority] | None = None,
    target_graph_nodes: int = 10_000,
    max_documents_per_source: int = 1_000,
    max_rounds: int = 10,
    fail_fast: bool = False,
    source_dir: Path | None = None,
    snapshot_limit: int = 5_000,
) -> GraphBackfillSummary:
    if target_graph_nodes < 1:
        raise ValueError("target_graph_nodes must be greater than zero.")
    if max_documents_per_source < 1:
        raise ValueError("max_documents_per_source must be greater than zero.")
    if max_rounds < 1:
        raise ValueError("max_rounds must be greater than zero.")
    if snapshot_limit < 1:
        raise ValueError("snapshot_limit must be greater than zero.")

    configs = _selected_source_configs(
        source_dir or settings.source_dir,
        source_ids=source_ids,
        priorities=priorities,
    )
    initial_counts = _graph_counts(settings.data_dir)
    current_counts = initial_counts
    totals: Counter[str] = Counter()
    results: list[GraphBackfillSourceResult] = []
    rounds_completed = 0
    stop_after_failure = False

    for round_index in range(1, max_rounds + 1):
        if current_counts.graph_nodes >= target_graph_nodes:
            break
        rounds_completed = round_index
        for config in configs:
            if current_counts.graph_nodes >= target_graph_nodes:
                break
            result = _run_backfill_source(
                config=config,
                settings=settings,
                mode=mode,
                round_index=round_index,
                max_documents_per_source=max_documents_per_source,
            )
            results.append(result)
            totals.update(result.stats)
            current_counts = GraphBackfillCounts(
                graph_nodes=result.graph_nodes_after,
                graph_relationships=result.graph_relationships_after,
            )
            if result.status == "failed" and fail_fast:
                stop_after_failure = True
                break
        if stop_after_failure:
            break

    final_counts = _graph_counts(settings.data_dir)
    return GraphBackfillSummary(
        mode=mode,
        data_dir=str(settings.data_dir),
        requested_source_ids=sorted(source_ids or []),
        priorities=sorted(priorities or []),
        target_graph_nodes=target_graph_nodes,
        max_documents_per_source=max_documents_per_source,
        max_rounds=max_rounds,
        selected_sources=len(configs),
        rounds_completed=rounds_completed,
        target_met=final_counts.graph_nodes >= target_graph_nodes,
        initial_graph_nodes=initial_counts.graph_nodes,
        initial_graph_relationships=initial_counts.graph_relationships,
        final_graph_nodes=final_counts.graph_nodes,
        final_graph_relationships=final_counts.graph_relationships,
        graph_nodes_added=final_counts.graph_nodes - initial_counts.graph_nodes,
        graph_relationships_added=(
            final_counts.graph_relationships - initial_counts.graph_relationships
        ),
        succeeded_source_runs=sum(1 for result in results if result.status == "succeeded"),
        skipped_source_runs=sum(1 for result in results if result.status == "skipped"),
        failed_source_runs=sum(1 for result in results if result.status == "failed"),
        totals=dict(sorted(totals.items())),
        store_counts=_store_counts(settings.data_dir),
        event_topics=_event_topics(settings.data_dir),
        source_results=results,
        recommended_commands=_recommended_commands(
            data_dir=settings.data_dir,
            snapshot_limit=snapshot_limit,
        ),
    )


def _selected_source_configs(
    source_dir: Path,
    *,
    source_ids: set[str] | None,
    priorities: set[SourcePriority] | None,
) -> list[SourceConfig]:
    configs = [config for config in load_all_source_configs(source_dir) if config.enabled]
    available_ids = {config.source_id for config in configs}
    missing_ids = sorted((source_ids or set()) - available_ids)
    if missing_ids:
        raise ValueError(f"Unknown source ids: {missing_ids}")
    if source_ids is not None:
        configs = [config for config in configs if config.source_id in source_ids]
    if priorities is not None:
        configs = [config for config in configs if config.priority in priorities]
    return sorted(configs, key=lambda config: (config.priority, config.source_id))


def _run_backfill_source(
    *,
    config: SourceConfig,
    settings: Settings,
    mode: GraphBackfillMode,
    round_index: int,
    max_documents_per_source: int,
) -> GraphBackfillSourceResult:
    before = _graph_counts(settings.data_dir)
    fixture_path: Path | None = None
    stats: dict[str, int] = {}
    status: GraphBackfillStatus = "succeeded"
    reason: str | None = None

    try:
        if mode == "fixture":
            fixture_path = config.fixtures.success
            if fixture_path is None or not fixture_path.exists():
                status = "skipped"
                reason = "fixture_success_missing"
            else:
                fixture_ingest = DEMO_FIXTURE_INGEST_BY_PROFILE.get(config.parser.profile)
                if fixture_ingest is None:
                    status = "skipped"
                    reason = "fixture_ingest_not_implemented"
                else:
                    stats = fixture_ingest(
                        config=config,
                        fixture_path=fixture_path,
                        settings=settings,
                        max_documents=max_documents_per_source,
                    )
        else:
            run = SourceRun(
                source_id=config.source_id,
                run_type="backfill",
                status="running",
                idempotency_key=(
                    f"{config.source_id}:graph-backfill:{round_index}:"
                    f"{datetime.now(UTC).isoformat()}"
                ),
                metadata={
                    "backfill_round": round_index,
                    "backfill_mode": mode,
                    "target": "large_graph_ingestion",
                },
            )
            stats = asyncio.run(
                process_live_source_run(
                    config=config,
                    settings=settings,
                    run=run,
                    max_documents=max_documents_per_source,
                )
            )
    except Exception as exc:  # pragma: no cover - fail-fast path is exercised by operators.
        status = "failed"
        reason = f"{exc.__class__.__name__}: {exc}"

    after = _graph_counts(settings.data_dir)
    return GraphBackfillSourceResult(
        round_index=round_index,
        source_id=config.source_id,
        priority=config.priority,
        parser_profile=config.parser.profile,
        mode=mode,
        status=status,
        fixture_path=str(fixture_path) if fixture_path is not None else None,
        stats=stats,
        reason=reason,
        graph_nodes_before=before.graph_nodes,
        graph_nodes_after=after.graph_nodes,
        graph_nodes_added=after.graph_nodes - before.graph_nodes,
        graph_relationships_before=before.graph_relationships,
        graph_relationships_after=after.graph_relationships,
        graph_relationships_added=after.graph_relationships - before.graph_relationships,
    )


def _graph_counts(data_dir: Path) -> GraphBackfillCounts:
    store = FileEvidenceStore(data_dir)
    counts = {
        GRAPH_NODES_TOTAL: len(
            {
                str(row.get("graph_node_key"))
                for row in store.read_collection("graph_node_upserts")
                if row.get("graph_node_key")
            }
        ),
        GRAPH_RELATIONSHIPS_TOTAL: len(
            {
                str(row.get("relationship_key"))
                for row in store.read_collection("graph_relationship_upserts")
                if row.get("relationship_key")
            }
        ),
    }
    return GraphBackfillCounts(
        graph_nodes=counts.get(GRAPH_NODES_TOTAL, 0),
        graph_relationships=counts.get(GRAPH_RELATIONSHIPS_TOTAL, 0),
    )


def _store_counts(data_dir: Path) -> dict[str, int]:
    store = FileEvidenceStore(data_dir)
    return {
        collection: len(store.read_collection(collection))
        for collection in DEMO_REFRESH_COLLECTIONS
    }


def _event_topics(data_dir: Path) -> dict[str, int]:
    store = FileEvidenceStore(data_dir)
    topics = Counter(
        str(row.get("event_type", "unknown")) for row in store.read_collection("events")
    )
    return dict(sorted(topics.items()))


def _recommended_commands(*, data_dir: Path, snapshot_limit: int) -> list[str]:
    return [
        (
            "uv run platform sync-graph-view "
            f"--data-dir {data_dir} --apply-neo4j --snapshot-source neo4j "
            "--output public/platform-demo/supply-chain-graph.json "
            f"--limit {snapshot_limit}"
        ),
        (
            "uv run platform sync-graph-view "
            f"--data-dir {data_dir} --snapshot-source file "
            "--output public/platform-demo/supply-chain-graph.json "
            f"--limit {snapshot_limit}"
        ),
        f"uv run platform run-graph-writer --data-dir {data_dir} --apply --summary-only",
        f"uv run platform record-graph-metrics --source file --data-dir {data_dir}",
        f"uv run platform run-risk-engine --data-dir {data_dir}",
        (
            "uv run platform export-graph-snapshot "
            f"--source file --data-dir {data_dir} "
            "--output public/platform-demo/supply-chain-graph.json "
            f"--limit {snapshot_limit}"
        ),
        f"uv run platform sync-postgres-evidence --data-dir {data_dir} --apply --aiven-defaults",
        (
            f"uv run platform publish-events --data-dir {data_dir} "
            "--event-type graph.node_upsert --publish-kafka"
        ),
        (
            f"uv run platform publish-events --data-dir {data_dir} "
            "--event-type graph.relationship_upsert --publish-kafka"
        ),
    ]
