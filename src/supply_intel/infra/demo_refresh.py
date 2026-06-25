from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Literal, cast

from pydantic import Field

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.source import SourceConfig
from supply_intel.pipeline import (
    ingest_eia_energy_prices_fixture,
    ingest_fda_drug_shortages_fixture,
    ingest_fda_inspections_dashboard_fixture,
    ingest_fda_warning_letters_fixture,
    ingest_freight_proxy_prices_fixture,
    ingest_gdacs_events_fixture,
    ingest_gdelt_doc_search_fixture,
    ingest_openfda_device_enforcement_fixture,
    ingest_openfda_device_registrationlisting_fixture,
    ingest_openfda_drug_enforcement_fixture,
    ingest_openfda_ndc_fixture,
    ingest_reliefweb_reports_fixture,
    ingest_search_trend_signals_fixture,
    ingest_sec_edgar_supplier_filings_fixture,
    ingest_un_comtrade_trade_flows_fixture,
    ingest_worldbank_commodity_prices_fixture,
)
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_all_source_configs

SourcePriority = Literal["P0", "P1", "P2", "P3"]
DemoRefreshStatus = Literal["succeeded", "skipped", "failed"]
FixtureIngest = Callable[..., dict[str, int]]

DEMO_FIXTURE_INGEST_BY_PROFILE: dict[str, FixtureIngest] = {
    "openfda.drug_ndc.v1": ingest_openfda_ndc_fixture,
    "openfda.drug_enforcement.v1": ingest_openfda_drug_enforcement_fixture,
    "openfda.device_registrationlisting.v1": ingest_openfda_device_registrationlisting_fixture,
    "openfda.device_enforcement.v1": ingest_openfda_device_enforcement_fixture,
    "fda.drug_shortages_html.v1": ingest_fda_drug_shortages_fixture,
    "fda.warning_letters_xlsx.v1": ingest_fda_warning_letters_fixture,
    "fda.inspections_dashboard.v1": ingest_fda_inspections_dashboard_fixture,
    "gdelt.doc_search.v1": ingest_gdelt_doc_search_fixture,
    "gdacs.events_rss.v1": ingest_gdacs_events_fixture,
    "reliefweb.reports.v1": ingest_reliefweb_reports_fixture,
    "worldbank.commodity_prices_monthly.v1": ingest_worldbank_commodity_prices_fixture,
    "eia.energy_prices.v1": ingest_eia_energy_prices_fixture,
    "sec.edgar_supplier_filings.v1": ingest_sec_edgar_supplier_filings_fixture,
    "uncomtrade.trade_flows.v1": ingest_un_comtrade_trade_flows_fixture,
    "nyfed.gscpi.v1": ingest_freight_proxy_prices_fixture,
    "gdelt.search_trends.v1": ingest_search_trend_signals_fixture,
}

DEMO_REFRESH_COLLECTIONS = [
    "raw_documents",
    "document_chunks",
    "evidence_spans",
    "extraction_runs",
    "canonical_entities",
    "entity_aliases",
    "graph_node_upserts",
    "graph_relationship_upserts",
    "risk_candidates",
    "risk_cases",
    "risk_verdicts",
    "risk_alerts",
    "risk_feature_snapshots",
    "human_review_queue",
    "events",
]


class DemoSourceRefreshResult(StrictBaseModel):
    source_id: str
    priority: SourcePriority
    parser_profile: str
    fixture_path: str | None = None
    status: DemoRefreshStatus
    stats: dict[str, int] = Field(default_factory=dict)
    reason: str | None = None


class DemoDataRefreshSummary(StrictBaseModel):
    data_dir: str
    requested_source_ids: list[str] = Field(default_factory=list)
    priorities: list[SourcePriority] = Field(default_factory=list)
    max_documents_per_source: int
    selected_sources: int
    succeeded_sources: int
    skipped_sources: int
    failed_sources: int
    totals: dict[str, int]
    store_counts: dict[str, int]
    event_topics: dict[str, int]
    source_results: list[DemoSourceRefreshResult]
    recommended_commands: list[str]


def refresh_demo_data(
    *,
    settings: Settings,
    source_ids: set[str] | None = None,
    priorities: set[SourcePriority] | None = None,
    max_documents_per_source: int = 1,
    fail_fast: bool = False,
    source_dir: Path | None = None,
) -> DemoDataRefreshSummary:
    if max_documents_per_source < 1:
        raise ValueError("max_documents_per_source must be greater than zero.")
    configs = _selected_source_configs(
        source_dir or settings.source_dir,
        source_ids=source_ids,
        priorities=priorities,
    )
    results: list[DemoSourceRefreshResult] = []
    totals: Counter[str] = Counter()

    for config in configs:
        result = _refresh_source(
            config=config,
            settings=settings,
            max_documents_per_source=max_documents_per_source,
        )
        results.append(result)
        totals.update(result.stats)
        if result.status == "failed" and fail_fast:
            break

    store = FileEvidenceStore(settings.data_dir)
    store_counts = _store_counts(store)
    event_topics = _event_topics(store)
    return DemoDataRefreshSummary(
        data_dir=str(settings.data_dir),
        requested_source_ids=sorted(source_ids or []),
        priorities=sorted(priorities or []),
        max_documents_per_source=max_documents_per_source,
        selected_sources=len(configs),
        succeeded_sources=sum(1 for result in results if result.status == "succeeded"),
        skipped_sources=sum(1 for result in results if result.status == "skipped"),
        failed_sources=sum(1 for result in results if result.status == "failed"),
        totals=dict(sorted(totals.items())),
        store_counts=store_counts,
        event_topics=event_topics,
        source_results=results,
        recommended_commands=_recommended_commands(settings.data_dir),
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


def _refresh_source(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents_per_source: int,
) -> DemoSourceRefreshResult:
    fixture_path = config.fixtures.success
    if fixture_path is None or not fixture_path.exists():
        return _source_result(
            config,
            status="skipped",
            reason="fixture_success_missing",
        )
    fixture_ingest = DEMO_FIXTURE_INGEST_BY_PROFILE.get(config.parser.profile)
    if fixture_ingest is None:
        return _source_result(
            config,
            fixture_path=fixture_path,
            status="skipped",
            reason="fixture_ingest_not_implemented",
        )
    try:
        stats = fixture_ingest(
            config=config,
            fixture_path=fixture_path,
            settings=settings,
            max_documents=max_documents_per_source,
        )
    except Exception as exc:  # pragma: no cover - exercised through fail-fast behavior in CLI use.
        return _source_result(
            config,
            fixture_path=fixture_path,
            status="failed",
            reason=f"{exc.__class__.__name__}: {exc}",
        )
    return _source_result(
        config,
        fixture_path=fixture_path,
        status="succeeded",
        stats=stats,
    )


def _source_result(
    config: SourceConfig,
    *,
    status: DemoRefreshStatus,
    fixture_path: Path | None = None,
    stats: dict[str, int] | None = None,
    reason: str | None = None,
) -> DemoSourceRefreshResult:
    return DemoSourceRefreshResult(
        source_id=config.source_id,
        priority=config.priority,
        parser_profile=config.parser.profile,
        fixture_path=str(fixture_path) if fixture_path is not None else None,
        status=status,
        stats=stats or {},
        reason=reason,
    )


def _store_counts(store: FileEvidenceStore) -> dict[str, int]:
    return {
        collection: len(store.read_collection(collection))
        for collection in DEMO_REFRESH_COLLECTIONS
    }


def _event_topics(store: FileEvidenceStore) -> dict[str, int]:
    topics = Counter(
        str(row.get("event_type", "unknown")) for row in store.read_collection("events")
    )
    return dict(sorted(topics.items()))


def _recommended_commands(data_dir: Path) -> list[str]:
    return [
        f"uv run platform run-graph-writer --data-dir {data_dir} --apply --summary-only",
        (
            "uv run platform export-graph-snapshot "
            f"--source file --data-dir {data_dir} "
            "--output public/platform-demo/supply-chain-graph.json --limit 500"
        ),
        f"uv run platform sync-postgres-evidence --data-dir {data_dir}",
        f"uv run platform publish-events --data-dir {data_dir} --event-type graph.node_upsert",
    ]


def normalize_priorities(values: Iterable[str] | None) -> set[SourcePriority] | None:
    if values is None:
        return None
    normalized: set[SourcePriority] = set()
    for value in values:
        upper = value.upper()
        if upper not in {"P0", "P1", "P2", "P3"}:
            raise ValueError(f"Unsupported source priority: {value}")
        normalized.add(cast(SourcePriority, upper))
    return normalized
