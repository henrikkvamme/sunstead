from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine, Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

import typer

from supply_intel import __version__
from supply_intel.agents.factory import ModelFactory
from supply_intel.agents.smoke import (
    DEFAULT_LLM_SMOKE_PROMPT,
    failed_llm_smoke_report,
    run_llm_smoke,
)
from supply_intel.dashboard.graph_chat_events import (
    default_dashboard_graph_chat_audit_path,
    import_dashboard_graph_chat_audit_events,
)
from supply_intel.db.postgres import (
    apply_migrations,
    connect_postgres,
    migration_files,
)
from supply_intel.db.repositories.evidence import FileEvidenceStore, PostgresEvidenceStore
from supply_intel.db.sync import plan_local_evidence_to_postgres, sync_local_evidence_to_postgres
from supply_intel.entity_resolution.service import HumanFeedback, HumanReviewTask
from supply_intel.events.outbox import (
    publish_outbox_events_to_kafka,
    select_outbox_events,
    summarize_outbox_selection,
)
from supply_intel.events.schemas import export_event_schema_bundle
from supply_intel.events.topics import ensure_topics_direct, load_topic_specs, plan_topic_bootstrap
from supply_intel.extraction.replay import run_extractor_consumer, run_local_extractor
from supply_intel.graph.explorer_snapshot import (
    write_explorer_snapshot_from_file_store,
    write_explorer_snapshot_from_neo4j,
)
from supply_intel.graph.insights import summarize_file_graph
from supply_intel.graph.mapper_worker import run_graph_mapper_consumer
from supply_intel.graph.neo4j_client import AsyncNeo4jClient, apply_cypher_migrations
from supply_intel.graph.queries import GraphQueryPlan, load_graph_query_plan
from supply_intel.graph.writer import (
    Neo4jGraphWriter,
    summarize_graph_replay,
    summarize_graph_replay_from_postgres,
)
from supply_intel.graph.writer import run_graph_writer_consumer as run_graph_writer_consumer_loop
from supply_intel.infra.aiven_mcp import NoopAivenMCPController
from supply_intel.infra.bootstrap import (
    apply_local_bootstrap,
    cloud_bootstrap_plan,
    local_bootstrap_summary,
)
from supply_intel.infra.cloud_readiness import inspect_cloud_readiness
from supply_intel.infra.demo_prepare import prepare_demo
from supply_intel.infra.demo_readiness import (
    AIVEN_DEFAULT_SECRETS_DIR,
    inspect_demo_readiness,
    settings_with_aiven_demo_defaults,
)
from supply_intel.infra.demo_refresh import normalize_priorities, refresh_demo_data
from supply_intel.infra.graph_backfill import GraphBackfillMode, backfill_graph
from supply_intel.infra.secrets import SecretBundleProfile, validate_cloud_secret_bundle
from supply_intel.models.infra import MCPAuditAction, OperationalMetric
from supply_intel.models.source import SourceConfig, SourceRegistryAudit, SourceRun
from supply_intel.observability.grafana import (
    GrafanaClient,
    build_postgres_datasource_payload,
    generate_dashboard,
    load_dashboard_payload,
)
from supply_intel.observability.graph_metrics import (
    GRAPH_NODES_TOTAL,
    GRAPH_RELATIONSHIPS_TOTAL,
    collect_file_graph_metrics,
    collect_neo4j_graph_metrics,
)
from supply_intel.pipeline import (
    fetch_source_sample,
    ingest_eia_energy_prices_fixture,
    ingest_eia_energy_prices_live,
    ingest_fda_drug_shortages_fixture,
    ingest_fda_drug_shortages_live,
    ingest_fda_inspections_dashboard_fixture,
    ingest_fda_inspections_dashboard_live,
    ingest_fda_warning_letters_fixture,
    ingest_fda_warning_letters_live,
    ingest_freight_proxy_prices_fixture,
    ingest_freight_proxy_prices_live,
    ingest_gdacs_events_fixture,
    ingest_gdacs_events_live,
    ingest_gdelt_doc_search_fixture,
    ingest_gdelt_doc_search_live,
    ingest_openfda_device_enforcement_fixture,
    ingest_openfda_device_enforcement_live,
    ingest_openfda_device_registrationlisting_fixture,
    ingest_openfda_device_registrationlisting_live,
    ingest_openfda_drug_enforcement_fixture,
    ingest_openfda_drug_enforcement_live,
    ingest_openfda_ndc_fixture,
    ingest_openfda_ndc_live,
    ingest_reliefweb_reports_fixture,
    ingest_reliefweb_reports_live,
    ingest_search_trend_signals_fixture,
    ingest_search_trend_signals_live,
    ingest_sec_edgar_supplier_filings_fixture,
    ingest_sec_edgar_supplier_filings_live,
    ingest_un_comtrade_trade_flows_fixture,
    ingest_un_comtrade_trade_flows_live,
    ingest_worldbank_commodity_prices_fixture,
    ingest_worldbank_commodity_prices_live,
)
from supply_intel.risk.engine import run_local_risk_engine, run_risk_engine_consumer
from supply_intel.risk.explain import explain_case_from_store
from supply_intel.risk.swarm import run_agent_swarm_consumer, run_local_agent_swarm
from supply_intel.settings import (
    Settings,
    get_settings,
    materialize_source_runtime_env,
    source_runtime_env_value,
)
from supply_intel.sources.credentials import build_source_credential_report
from supply_intel.sources.registry import (
    find_source_config,
    load_all_source_configs,
    load_source_config,
)
from supply_intel.sources.scheduler import (
    publish_scheduled_events_to_kafka,
    run_local_scheduler,
    source_config_hash,
)
from supply_intel.sources.worker import run_ingest_worker as run_ingest_worker_loop
from supply_intel.sources.worker import run_ingest_worker_once

SourceEndpointAccess = Literal["public", "public_limited", "configured", "requires_env"]
HumanReviewDecision = Literal[
    "approve_match",
    "reject_match",
    "create_new_entity",
    "merge_entities",
    "split_entity",
    "add_alias",
    "mark_source_assertion_incorrect",
    "dismiss_review",
]

app = typer.Typer(help="CLI for the unnamed intelligence platform.")

LiveIngest = Callable[..., Coroutine[Any, Any, dict[str, int]]]
FixtureIngest = Callable[..., dict[str, int]]

LIVE_INGEST_BY_PROFILE: dict[str, LiveIngest] = {
    "openfda.drug_ndc.v1": ingest_openfda_ndc_live,
    "openfda.drug_enforcement.v1": ingest_openfda_drug_enforcement_live,
    "openfda.device_registrationlisting.v1": ingest_openfda_device_registrationlisting_live,
    "openfda.device_enforcement.v1": ingest_openfda_device_enforcement_live,
    "fda.drug_shortages_html.v1": ingest_fda_drug_shortages_live,
    "fda.warning_letters_xlsx.v1": ingest_fda_warning_letters_live,
    "fda.inspections_dashboard.v1": ingest_fda_inspections_dashboard_live,
    "gdelt.doc_search.v1": ingest_gdelt_doc_search_live,
    "gdacs.events_rss.v1": ingest_gdacs_events_live,
    "reliefweb.reports.v1": ingest_reliefweb_reports_live,
    "worldbank.commodity_prices_monthly.v1": ingest_worldbank_commodity_prices_live,
    "eia.energy_prices.v1": ingest_eia_energy_prices_live,
    "sec.edgar_supplier_filings.v1": ingest_sec_edgar_supplier_filings_live,
    "uncomtrade.trade_flows.v1": ingest_un_comtrade_trade_flows_live,
    "nyfed.gscpi.v1": ingest_freight_proxy_prices_live,
    "gdelt.search_trends.v1": ingest_search_trend_signals_live,
}

FIXTURE_INGEST_BY_PROFILE: dict[str, FixtureIngest] = {
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


async def _register_source_postgres(config: SourceConfig, settings: Settings) -> bool:
    connection = await connect_postgres(settings)
    try:
        store = PostgresEvidenceStore(connection)
        return await store.register_source(config)
    finally:
        await connection.close()


def _write_source_registry_audit(
    *,
    settings: Settings,
    config: SourceConfig,
    backend: Literal["file", "postgres"],
    result: Literal["created", "updated", "unchanged", "upserted"],
    config_path: Path,
    actor: str | None,
) -> None:
    store = FileEvidenceStore(settings.data_dir)
    store.write_source_registry_audit(
        SourceRegistryAudit(
            source_id=config.source_id,
            action="register_source",
            backend=backend,
            result=result,
            config_hash=source_config_hash(config),
            config_path=str(config_path),
            actor=actor,
        )
    )


async def _apply_neo4j_migrations(settings: Settings) -> list[dict[str, object]]:
    client = AsyncNeo4jClient(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)
    try:
        results = await apply_cypher_migrations(client)
        return [
            {
                "path": result.path,
                "statements": result.statements,
                "results": result.results,
            }
            for result in results
        ]
    finally:
        await client.close()


async def _record_graph_metrics(
    settings: Settings,
    *,
    backend: Literal["file", "postgres"],
    source: Literal["file", "neo4j"] = "neo4j",
    data_dir: Path | None = None,
    observed_at: datetime | None = None,
) -> dict[str, object]:
    metric_data_dir = data_dir or settings.data_dir
    if source == "neo4j":
        client = AsyncNeo4jClient(
            settings.neo4j_uri,
            settings.neo4j_username,
            settings.neo4j_password,
        )
        try:
            metrics = await collect_neo4j_graph_metrics(client, observed_at=observed_at)
        finally:
            await client.close()
    else:
        metrics = collect_file_graph_metrics(metric_data_dir, observed_at=observed_at)

    if backend == "postgres":
        created = await _write_graph_metrics_to_postgres(settings, metrics)
    else:
        store = FileEvidenceStore(metric_data_dir)
        created = sum(1 for metric in metrics if store.write_operational_metric(metric))
    return _graph_metrics_cli_payload(
        backend=backend,
        source=source,
        metrics=metrics,
        metrics_created=created,
    )


async def _read_neo4j_graph_counts(settings: Settings) -> dict[str, int]:
    client = AsyncNeo4jClient(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)
    try:
        metrics = await collect_neo4j_graph_metrics(client)
    finally:
        await client.close()
    return {metric.metric_name: int(metric.metric_value) for metric in metrics}


def _read_file_graph_counts(data_dir: Path) -> dict[str, int]:
    store = FileEvidenceStore(data_dir)
    node_keys = {
        str(row.get("graph_node_key"))
        for row in store.read_collection("graph_node_upserts")
        if row.get("graph_node_key")
    }
    relationship_keys = {
        str(row.get("relationship_key"))
        for row in store.read_collection("graph_relationship_upserts")
        if row.get("relationship_key")
    }
    return {
        GRAPH_NODES_TOTAL: len(node_keys),
        GRAPH_RELATIONSHIPS_TOTAL: len(relationship_keys),
    }


async def _write_graph_metrics_to_postgres(
    settings: Settings,
    metrics: list[OperationalMetric],
) -> int:
    connection = await connect_postgres(settings)
    try:
        store = PostgresEvidenceStore(connection)
        created = 0
        for metric in metrics:
            if await store.write_operational_metric(metric):
                created += 1
        return created
    finally:
        await connection.close()


def _graph_metrics_cli_payload(
    *,
    backend: Literal["file", "postgres"],
    source: Literal["file", "neo4j"],
    metrics: list[OperationalMetric],
    metrics_created: int,
) -> dict[str, object]:
    return {
        "backend": backend,
        "source": source,
        "metrics_seen": len(metrics),
        "metrics_created": metrics_created,
        "metrics": [metric.model_dump(mode="json") for metric in metrics],
    }


def _parse_observed_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    try:
        observed_at = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise typer.BadParameter("Use ISO 8601 format, for example 2026-06-25T09:00:00Z") from exc
    if observed_at.tzinfo is None:
        return observed_at.replace(tzinfo=UTC)
    return observed_at


async def _apply_graph_replay(settings: Settings, data_dir: Path) -> dict[str, object]:
    client = AsyncNeo4jClient(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)
    try:
        writer = Neo4jGraphWriter(client)
        summary = await writer.replay_from_jsonl(data_dir)
        return summary.model_dump(mode="json")
    finally:
        await client.close()


def _graph_replay_cli_payload(
    payload: dict[str, object],
    *,
    summary_only: bool = False,
) -> dict[str, object]:
    if not summary_only:
        return payload
    summarized = dict(payload)
    results = summarized.pop("results", [])
    if not isinstance(results, list):
        results = []
    summarized["result_count"] = len(results)
    summarized["nodes_created"] = _sum_graph_result_counter(results, "nodes_created")
    summarized["nodes_deleted"] = _sum_graph_result_counter(results, "nodes_deleted")
    summarized["relationships_created"] = _sum_graph_result_counter(
        results,
        "relationships_created",
    )
    summarized["relationships_deleted"] = _sum_graph_result_counter(
        results,
        "relationships_deleted",
    )
    summarized["properties_set"] = _sum_graph_result_counter(results, "properties_set")
    summarized["records_returned"] = _sum_graph_result_counter(results, "record_count")
    return summarized


def _sum_graph_result_counter(results: list[object], key: str) -> int:
    total = 0
    for result in results:
        if isinstance(result, dict):
            total += int(result.get(key, 0) or 0)
    return total


async def _summarize_graph_replay_from_postgres(
    settings: Settings,
    *,
    limit: int | None,
) -> dict[str, object]:
    connection = await connect_postgres(settings)
    try:
        summary = await summarize_graph_replay_from_postgres(connection, limit=limit)
        return summary.model_dump(mode="json")
    finally:
        await connection.close()


async def _apply_graph_replay_from_postgres(
    settings: Settings,
    *,
    limit: int | None,
) -> dict[str, object]:
    connection = await connect_postgres(settings)
    client = AsyncNeo4jClient(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)
    try:
        writer = Neo4jGraphWriter(client)
        summary = await writer.replay_from_postgres_audit(connection, limit=limit)
        return summary.model_dump(mode="json")
    finally:
        await client.close()
        await connection.close()


async def _run_graph_query(settings: Settings, plan: GraphQueryPlan) -> dict[str, object]:
    client = AsyncNeo4jClient(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)
    try:
        records = await client.run_read_query(plan.cypher, dict(plan.parameters))
        return {
            "query_name": plan.query_name,
            "parameters": plan.parameters,
            "records": records,
            "record_count": len(records),
        }
    finally:
        await client.close()


async def _export_graph_snapshot(
    settings: Settings,
    output_path: Path,
    *,
    limit: int,
) -> dict[str, object]:
    client = AsyncNeo4jClient(settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password)
    try:
        snapshot = await write_explorer_snapshot_from_neo4j(client, output_path, limit=limit)
        return {
            "output_path": str(output_path),
            "generated_at": snapshot.generatedAt,
            "nodes": len(snapshot.nodes),
            "edges": len(snapshot.edges),
            "graph_nodes": snapshot.summary.graphNodes,
            "graph_relationships": snapshot.summary.graphRelationships,
            "data_mode": snapshot.dataStatus.mode,
        }
    finally:
        await client.close()


def _export_file_graph_snapshot(
    data_dir: Path,
    output_path: Path,
    *,
    limit: int,
) -> dict[str, object]:
    snapshot = write_explorer_snapshot_from_file_store(data_dir, output_path, limit=limit)
    return {
        "output_path": str(output_path),
        "generated_at": snapshot.generatedAt,
        "nodes": len(snapshot.nodes),
        "edges": len(snapshot.edges),
        "graph_nodes": snapshot.summary.graphNodes,
        "graph_relationships": snapshot.summary.graphRelationships,
        "data_mode": snapshot.dataStatus.mode,
    }


async def _provision_grafana_dashboards(
    settings: Settings,
    paths: list[Path],
    *,
    folder_uid: str | None = None,
    message: str | None = None,
) -> list[dict[str, object]]:
    async with GrafanaClient.from_settings(settings) as client:
        results = []
        for path in paths:
            result = await client.upsert_dashboard(
                load_dashboard_payload(path),
                folder_uid=folder_uid,
                message=message,
                path=path,
            )
            results.append(result.model_dump(mode="json"))
        return results


async def _provision_grafana_datasource(
    settings: Settings,
    *,
    name: str,
    uid: str,
) -> dict[str, object]:
    async with GrafanaClient.from_settings(settings) as client:
        result = await client.upsert_postgres_datasource(
            build_postgres_datasource_payload(settings, name=name, uid=uid)
        )
        return result.model_dump(mode="json")


async def _record_mcp_audit_plan(settings: Settings, actions: list[MCPAuditAction]) -> int:
    store = FileEvidenceStore(settings.data_dir)
    controller = NoopAivenMCPController(audit_sink=store)
    for action in actions:
        await controller.audit_action(action)
    return len(actions)


def _case_key_from_id_or_key(data_dir: Path, value: str) -> str:
    if value.startswith("risk:"):
        return value
    path = data_dir / "risk_cases.jsonl"
    if not path.exists():
        raise typer.BadParameter(f"No risk case store found in {data_dir}")
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("id")) == value:
            return str(row["case_key"])
    raise typer.BadParameter(f"Risk case id not found: {value}")


def _read_source_health_rows(data_dir: Path) -> list[dict[str, Any]]:
    path = data_dir / "source_health.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _read_source_run_rows(data_dir: Path) -> list[dict[str, Any]]:
    path = data_dir / "source_runs.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


async def _read_postgres_source_health_rows(settings: Settings) -> list[dict[str, Any]]:
    connection = await connect_postgres(settings)
    try:
        rows = await connection.fetch(
            """
            WITH raw_counts AS (
              SELECT
                source_id,
                count(*) AS raw_documents,
                max(fetched_at) AS last_raw_document_at
              FROM raw_documents
              GROUP BY source_id
            ),
            chunk_counts AS (
              SELECT
                rd.source_id,
                count(*) AS document_chunks
              FROM document_chunks dc
              JOIN raw_documents rd ON rd.id = dc.raw_document_id
              GROUP BY rd.source_id
            )
            SELECT
              ds.source_id,
              sh.status,
              sh.last_success_at,
              sh.last_failure_at,
              sh.consecutive_failures,
              sh.freshness_lag_seconds,
              sh.metrics,
              COALESCE(raw_counts.raw_documents, 0) AS raw_documents,
              COALESCE(chunk_counts.document_chunks, 0) AS document_chunks,
              raw_counts.last_raw_document_at
            FROM data_sources ds
            LEFT JOIN source_health sh ON sh.source_id = ds.source_id
            LEFT JOIN raw_counts ON raw_counts.source_id = ds.source_id
            LEFT JOIN chunk_counts ON chunk_counts.source_id = ds.source_id
            ORDER BY ds.source_id
            """
        )
        return [dict(row) for row in rows]
    finally:
        await connection.close()


async def _read_postgres_source_run_rows(
    settings: Settings,
    *,
    source_id: str | None,
    status: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    connection = await connect_postgres(settings)
    try:
        rows = await connection.fetch(
            """
            SELECT
              id::text,
              source_id,
              run_type,
              status,
              started_at,
              finished_at,
              cursor_before,
              cursor_after,
              documents_seen,
              documents_created,
              documents_unchanged,
              error_count,
              correlation_id::text,
              idempotency_key,
              metadata,
              created_at,
              updated_at
            FROM source_runs
            WHERE ($1::text IS NULL OR source_id = $1)
              AND ($2::text IS NULL OR status = $2)
            ORDER BY created_at DESC
            LIMIT $3
            """,
            source_id,
            status,
            limit,
        )
        return [_normalize_postgres_source_run_row(dict(row)) for row in rows]
    finally:
        await connection.close()


def _decode_postgres_json_object(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = json.loads(value)
    if value is None:
        return None
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"Expected JSON object, got {type(value).__name__}")


def _normalize_postgres_source_run_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["metadata"] = _decode_postgres_json_object(row.get("metadata")) or {}
    normalized["cursor_before"] = _decode_postgres_json_object(row.get("cursor_before"))
    normalized["cursor_after"] = _decode_postgres_json_object(row.get("cursor_after"))
    return normalized


def _source_run_query_rows(
    *,
    run_rows: list[dict[str, Any]],
    source_id: str | None,
    status: str | None,
    limit: int,
    include_cursors: bool = False,
    latest_state_only: bool = False,
) -> list[dict[str, object]]:
    parsed_runs: list[SourceRun] = []
    for row in run_rows:
        run = SourceRun.model_validate(row)
        if source_id is not None and run.source_id != source_id:
            continue
        parsed_runs.append(run)
    parsed_runs.sort(key=lambda run: (run.updated_at, run.created_at), reverse=True)
    if latest_state_only:
        seen_run_ids: set[str] = set()
        latest_runs: list[SourceRun] = []
        for run in parsed_runs:
            run_id = str(run.id)
            if run_id in seen_run_ids:
                continue
            seen_run_ids.add(run_id)
            latest_runs.append(run)
        parsed_runs = latest_runs
    if status is not None:
        parsed_runs = [run for run in parsed_runs if run.status == status]
    return [
        _source_run_query_row(run, include_cursors=include_cursors) for run in parsed_runs[:limit]
    ]


def _source_run_query_row(run: SourceRun, *, include_cursors: bool) -> dict[str, object]:
    row: dict[str, object] = {
        "source_run_id": str(run.id),
        "source_id": run.source_id,
        "run_type": run.run_type,
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "documents_seen": run.documents_seen,
        "documents_created": run.documents_created,
        "documents_unchanged": run.documents_unchanged,
        "error_count": run.error_count,
        "correlation_id": str(run.correlation_id),
        "idempotency_key": run.idempotency_key,
        "error": run.metadata.get("error"),
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }
    if include_cursors:
        row["cursor_before"] = run.cursor_before
        row["cursor_after"] = run.cursor_after
    return row


def _source_status_matches(actual: str, requested: str) -> bool:
    actual_normalized = actual.casefold()
    requested_normalized = requested.casefold()
    if requested_normalized in {"failed", "failing", "unhealthy"}:
        return actual_normalized in {"failed", "failing", "unhealthy"}
    return actual_normalized == requested_normalized


def _source_query_rows(
    *,
    configs: list[SourceConfig],
    health_rows: list[dict[str, Any]],
    status: str | None,
    priority: str | None,
    endpoint_access: SourceEndpointAccess | None = None,
    settings: Settings | None = None,
) -> list[dict[str, object]]:
    health_by_source = {str(row["source_id"]): row for row in health_rows if row.get("source_id")}
    rows: list[dict[str, object]] = []
    for config in configs:
        health = health_by_source.get(config.source_id, {})
        source_status = str(health.get("status") or "unknown")
        auth_metadata = _source_query_auth_metadata(config, settings=settings)
        if status is not None and not _source_status_matches(source_status, status):
            continue
        if priority is not None and config.priority.casefold() != priority.casefold():
            continue
        if endpoint_access is not None and auth_metadata["endpoint_access"] != endpoint_access:
            continue
        rows.append(
            {
                "source_id": config.source_id,
                "name": config.name,
                "enabled": config.enabled,
                "priority": config.priority,
                "adapter": config.adapter,
                "parser_profile": config.parser.profile,
                "cadence_seconds": config.cadence_seconds,
                **auth_metadata,
                "robots_policy": config.compliance.robots,
                "rate_limit_requests_per_minute": config.rate_limit.requests_per_minute,
                "rate_limit_burst": config.rate_limit.burst,
                "status": source_status,
                "last_success_at": _source_query_json_value(health.get("last_success_at")),
                "last_failure_at": _source_query_json_value(health.get("last_failure_at")),
                "consecutive_failures": health.get("consecutive_failures") or 0,
                "freshness_lag_seconds": health.get("freshness_lag_seconds"),
                **_source_query_optional_counts(health),
            }
        )
    return rows


def _source_query_auth_metadata(
    config: SourceConfig,
    *,
    settings: Settings | None = None,
) -> dict[str, object]:
    auth_required = config.auth.type != "none" and config.auth.required
    auth_env_configured = bool(
        config.auth.env and source_runtime_env_value(config.auth.env, settings)
    )
    return {
        "auth_type": config.auth.type,
        "auth_env": config.auth.env,
        "auth_required": auth_required,
        "auth_env_configured": auth_env_configured if config.auth.type != "none" else None,
        "endpoint_access": _source_endpoint_access(config, auth_env_configured),
    }


def _source_endpoint_access(
    config: SourceConfig,
    auth_env_configured: bool,
) -> SourceEndpointAccess:
    if config.auth.type == "none":
        return "public"
    if auth_env_configured:
        return "configured"
    if config.auth.required:
        return "requires_env"
    return "public_limited"


def _source_query_optional_counts(health: dict[str, Any]) -> dict[str, object]:
    optional_fields = ("raw_documents", "document_chunks", "last_raw_document_at")
    return {
        field: _source_query_json_value(health[field])
        for field in optional_fields
        if field in health
    }


def _source_query_json_value(value: object) -> object:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _human_review_rows_from_tasks(tasks: list[HumanReviewTask]) -> list[dict[str, object]]:
    return [_human_review_row(task) for task in tasks]


def _local_human_review_tasks(
    store: FileEvidenceStore,
    *,
    status: Literal["open", "resolved"] | None,
) -> list[HumanReviewTask]:
    tasks = [
        HumanReviewTask.model_validate(row) for row in store.read_collection("human_review_queue")
    ]
    if status is None:
        return tasks
    return [task for task in tasks if task.status == status]


def _human_review_row(task: HumanReviewTask) -> dict[str, object]:
    return {
        "id": str(task.id),
        "target_table": task.target_table,
        "target_id": str(task.target_id),
        "review_type": task.review_type,
        "reason": task.reason,
        "status": task.status,
        "priority": task.priority,
        "evidence_span_ids": [str(value) for value in task.evidence_span_ids],
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _human_feedback_for_task(
    *,
    task: HumanReviewTask,
    decision: HumanReviewDecision,
    reviewer: str | None,
    comment: str | None,
) -> HumanFeedback:
    before_value = task.model_dump(mode="json")
    return HumanFeedback(
        target_table=task.target_table,
        target_id=task.target_id,
        feedback_type="review_decision",
        decision=decision,
        comment=comment,
        reviewer=reviewer,
        before_value=before_value,
        after_value={
            "status": "resolved",
            "decision": decision,
            "reviewer": reviewer,
        },
        metadata={
            "human_review_task_id": str(task.id),
            "review_type": task.review_type,
            "evidence_span_ids": [str(value) for value in task.evidence_span_ids],
        },
    )


def _human_feedback_result(
    *,
    task: HumanReviewTask,
    feedback: HumanFeedback,
    inserted: bool,
    resolved: HumanReviewTask,
) -> dict[str, object]:
    return {
        "review_task_id": str(task.id),
        "target_table": task.target_table,
        "target_id": str(task.target_id),
        "decision": feedback.decision,
        "reviewer": feedback.reviewer,
        "feedback_id": str(feedback.id),
        "feedback_inserted": inserted,
        "status": resolved.status,
    }


def _record_local_human_feedback(
    *,
    store: FileEvidenceStore,
    review_task_id: UUID,
    decision: HumanReviewDecision,
    reviewer: str | None,
    comment: str | None,
) -> dict[str, object]:
    tasks = [
        HumanReviewTask.model_validate(row) for row in store.read_collection("human_review_queue")
    ]
    task = next((candidate for candidate in tasks if candidate.id == review_task_id), None)
    if task is None:
        raise typer.BadParameter(f"Human review task not found: {review_task_id}")
    if task.status == "resolved":
        raise typer.BadParameter(f"Human review task is already resolved: {review_task_id}")
    feedback = _human_feedback_for_task(
        task=task,
        decision=decision,
        reviewer=reviewer,
        comment=comment,
    )
    inserted = store.write_human_feedback(feedback)
    resolved = store.resolve_human_review_task(task.id)
    if resolved is None:
        raise typer.BadParameter(f"Human review task not found: {review_task_id}")
    return _human_feedback_result(
        task=task,
        feedback=feedback,
        inserted=inserted,
        resolved=resolved,
    )


async def _postgres_human_review_rows(
    settings: Settings,
    *,
    status: Literal["open", "resolved"] | None,
) -> list[dict[str, object]]:
    connection = await connect_postgres(settings)
    try:
        store = PostgresEvidenceStore(connection)
        return _human_review_rows_from_tasks(await store.read_human_review_tasks(status=status))
    finally:
        await connection.close()


async def _record_postgres_human_feedback(
    *,
    settings: Settings,
    review_task_id: UUID,
    decision: HumanReviewDecision,
    reviewer: str | None,
    comment: str | None,
) -> dict[str, object]:
    connection = await connect_postgres(settings)
    try:
        store = PostgresEvidenceStore(connection)
        task = await store.read_human_review_task(review_task_id)
        if task is None:
            raise typer.BadParameter(f"Human review task not found: {review_task_id}")
        if task.status == "resolved":
            raise typer.BadParameter(f"Human review task is already resolved: {review_task_id}")
        feedback = _human_feedback_for_task(
            task=task,
            decision=decision,
            reviewer=reviewer,
            comment=comment,
        )
        inserted = await store.write_human_feedback(feedback)
        resolved = await store.resolve_human_review_task(task.id)
        if resolved is None:
            raise typer.BadParameter(f"Human review task not found: {review_task_id}")
        return _human_feedback_result(
            task=task,
            feedback=feedback,
            inserted=inserted,
            resolved=resolved,
        )
    finally:
        await connection.close()


@app.callback()
def main(
    version: Annotated[bool, typer.Option("--version", help="Show version and exit.")] = False,
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command("bootstrap-infra")
def bootstrap_infra(
    mode: Annotated[
        Literal["local", "aiven", "hybrid"],
        typer.Option(help="local, aiven, or hybrid."),
    ] = "local",
    project: Annotated[str | None, typer.Option("--project")] = None,
    postgres_service: Annotated[str | None, typer.Option("--postgres-service")] = None,
    kafka_service: Annotated[str | None, typer.Option("--kafka-service")] = None,
    grafana_service: Annotated[str | None, typer.Option("--grafana-service")] = None,
    allow_service_create: Annotated[
        bool,
        typer.Option(
            "--allow-service-create",
            help="Plan Aiven service creation when service names are absent.",
        ),
    ] = False,
    cloud: Annotated[str | None, typer.Option("--cloud")] = None,
    postgres_plan: Annotated[str | None, typer.Option("--postgres-plan")] = None,
    kafka_plan: Annotated[str | None, typer.Option("--kafka-plan")] = None,
    grafana_plan: Annotated[str | None, typer.Option("--grafana-plan")] = None,
    approval_id: Annotated[UUID | None, typer.Option("--approval-id")] = None,
    actor: Annotated[str | None, typer.Option("--actor")] = None,
    record_audit: Annotated[
        bool,
        typer.Option(
            "--record-audit",
            help="Persist the dry-run MCP action plan to DATA_DIR/mcp_audit_log.jsonl.",
        ),
    ] = False,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="For --mode local, start Docker Compose services."),
    ] = False,
    timeout_seconds: Annotated[
        float,
        typer.Option("--timeout-seconds", min=1, help="Local compose startup timeout."),
    ] = 300,
) -> None:
    settings = get_settings()
    if mode == "local":
        if apply:
            typer.echo(
                json.dumps(
                    apply_local_bootstrap(timeout_seconds=timeout_seconds).model_dump(mode="json"),
                    indent=2,
                )
            )
            return
        typer.echo(json.dumps(local_bootstrap_summary().model_dump(mode="json"), indent=2))
        return
    if apply:
        raise typer.BadParameter("--apply is only supported for --mode local.")
    plan = cloud_bootstrap_plan(
        settings=settings,
        mode=mode,
        project=project,
        postgres_service=postgres_service,
        kafka_service=kafka_service,
        grafana_service=grafana_service,
        allow_service_create=allow_service_create,
        cloud=cloud,
        postgres_plan=postgres_plan,
        kafka_plan=kafka_plan,
        grafana_plan=grafana_plan,
        approval_id=approval_id,
        actor=actor,
    )
    payload = plan.model_dump(mode="json")
    if record_audit:
        payload["audit_records_written"] = asyncio.run(
            _record_mcp_audit_plan(settings, plan.mcp_actions)
        )
    typer.echo(json.dumps(payload, indent=2))


@app.command("validate-cloud-secrets")
def validate_cloud_secrets(
    profile: Annotated[
        SecretBundleProfile,
        typer.Option("--profile", help="Secret bundle profile to validate."),
    ] = "aiven-worker",
    require_ready: Annotated[
        bool,
        typer.Option("--require-ready", help="Exit non-zero when required files are missing."),
    ] = False,
) -> None:
    settings = get_settings(secret_file_loading="available")
    summary = validate_cloud_secret_bundle(settings, profile)
    typer.echo(json.dumps(summary.model_dump(mode="json"), indent=2))
    if require_ready and not summary.ready:
        raise typer.Exit(1)


@app.command("cloud-readiness")
def cloud_readiness(
    profile: Annotated[
        SecretBundleProfile,
        typer.Option("--profile", help="Secret bundle profile to validate."),
    ] = "aiven-mvp",
    live_aiven: Annotated[
        bool,
        typer.Option(
            "--live-aiven",
            help="Use the direct Aiven API fallback to verify configured service names.",
        ),
    ] = False,
    require_ready: Annotated[
        bool,
        typer.Option("--require-ready", help="Exit non-zero when the cloud path is not ready."),
    ] = False,
) -> None:
    settings = get_settings(secret_file_loading="available")
    report = asyncio.run(inspect_cloud_readiness(settings, profile=profile, live_aiven=live_aiven))
    typer.echo(json.dumps(report.model_dump(mode="json"), indent=2))
    if require_ready and not report.ready:
        raise typer.Exit(1)


@app.command("demo-readiness")
def demo_readiness(
    live_neo4j: Annotated[
        bool,
        typer.Option("--live-neo4j", help="Connect to NEO4J_URI and include current graph counts."),
    ] = False,
    local_graph: Annotated[
        bool,
        typer.Option("--local-graph", help="Read graph counts from local JSONL graph upserts."),
    ] = False,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Local evidence directory for --local-graph."),
    ] = None,
    aiven_defaults: Annotated[
        bool,
        typer.Option(
            "--aiven-defaults",
            help="Use conventional .platform-secrets/aiven paths when env vars are unset.",
        ),
    ] = False,
    aiven_secrets_dir: Annotated[
        Path,
        typer.Option("--aiven-secrets-dir", help="Directory used by --aiven-defaults."),
    ] = AIVEN_DEFAULT_SECRETS_DIR,
    require_ready: Annotated[
        bool,
        typer.Option(
            "--require-ready", help="Exit non-zero when the minimal demo path is blocked."
        ),
    ] = False,
) -> None:
    if live_neo4j and local_graph:
        raise typer.BadParameter("--live-neo4j and --local-graph are mutually exclusive.")
    settings = get_settings(secret_file_loading="available")
    materialize_source_runtime_env(settings)
    if aiven_defaults:
        settings = settings_with_aiven_demo_defaults(settings, secrets_dir=aiven_secrets_dir)
    graph_counts: dict[str, int] | None = None
    graph_count_source: Literal["neo4j", "file", "not_checked"] = "not_checked"
    if live_neo4j:
        graph_counts = asyncio.run(_read_neo4j_graph_counts(settings))
        graph_count_source = "neo4j"
    if local_graph:
        graph_counts = _read_file_graph_counts(data_dir or settings.data_dir)
        graph_count_source = "file"
    report = inspect_demo_readiness(
        settings=settings,
        source_configs=load_all_source_configs(settings.source_dir),
        graph_counts=graph_counts,
        graph_count_source=graph_count_source,
    )
    typer.echo(json.dumps(report.model_dump(mode="json"), indent=2))
    if require_ready and not report.demo_ready_now:
        raise typer.Exit(1)


@app.command("refresh-demo-data")
def refresh_demo_data_command(
    source_id: Annotated[
        list[str] | None,
        typer.Option("--source-id", help="Refresh only specific source ids; repeatable."),
    ] = None,
    priority: Annotated[
        list[str] | None,
        typer.Option("--priority", help="Refresh only selected priorities: P0, P1, P2, P3."),
    ] = None,
    max_documents_per_source: Annotated[
        int,
        typer.Option(
            "--max-documents-per-source",
            min=1,
            help="Bound fixture records processed per source where the parser supports it.",
        ),
    ] = 1,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Local evidence directory to refresh."),
    ] = None,
    fail_fast: Annotated[
        bool,
        typer.Option("--fail-fast", help="Stop after the first source refresh failure."),
    ] = False,
) -> None:
    settings = get_settings(secret_file_loading="available")
    refresh_settings = settings.model_copy(update={"data_dir": data_dir or settings.data_dir})
    try:
        priorities = normalize_priorities(priority)
        summary = refresh_demo_data(
            settings=refresh_settings,
            source_ids=set(source_id) if source_id else None,
            priorities=priorities,
            max_documents_per_source=max_documents_per_source,
            fail_fast=fail_fast,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(summary.model_dump(mode="json"), indent=2))


@app.command("backfill-graph")
def backfill_graph_command(
    source_id: Annotated[
        list[str] | None,
        typer.Option("--source-id", help="Backfill only specific source ids; repeatable."),
    ] = None,
    priority: Annotated[
        list[str] | None,
        typer.Option("--priority", help="Backfill only selected priorities: P0, P1, P2, P3."),
    ] = None,
    mode: Annotated[
        GraphBackfillMode,
        typer.Option("--mode", help="Use checked-in fixtures or live source endpoints."),
    ] = "fixture",
    target_graph_nodes: Annotated[
        int,
        typer.Option(
            "--target-graph-nodes",
            min=1,
            help="Stop after the local graph store reaches this many unique graph nodes.",
        ),
    ] = 10_000,
    max_documents_per_source: Annotated[
        int,
        typer.Option(
            "--max-documents-per-source",
            min=1,
            help="Bound documents fetched or processed per source per round.",
        ),
    ] = 1_000,
    max_rounds: Annotated[
        int,
        typer.Option("--max-rounds", min=1, help="Maximum passes across selected sources."),
    ] = 10,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Local evidence directory to grow."),
    ] = None,
    snapshot_limit: Annotated[
        int,
        typer.Option(
            "--snapshot-limit",
            min=1,
            help="Node/edge limit included in the recommended graph snapshot command.",
        ),
    ] = 5_000,
    fail_fast: Annotated[
        bool,
        typer.Option("--fail-fast", help="Stop after the first source backfill failure."),
    ] = False,
) -> None:
    settings = get_settings(secret_file_loading="available")
    if mode == "live":
        materialize_source_runtime_env(settings)
    backfill_settings = settings.model_copy(update={"data_dir": data_dir or settings.data_dir})
    try:
        priorities = normalize_priorities(priority)
        summary = backfill_graph(
            settings=backfill_settings,
            mode=mode,
            source_ids=set(source_id) if source_id else None,
            priorities=priorities,
            target_graph_nodes=target_graph_nodes,
            max_documents_per_source=max_documents_per_source,
            max_rounds=max_rounds,
            fail_fast=fail_fast,
            snapshot_limit=snapshot_limit,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(summary.model_dump(mode="json"), indent=2))


@app.command("prepare-demo")
def prepare_demo_command(
    source_id: Annotated[
        list[str] | None,
        typer.Option(
            "--source-id",
            help="Prepare demo using only specific source ids; repeatable.",
        ),
    ] = None,
    priority: Annotated[
        list[str] | None,
        typer.Option("--priority", help="Prepare demo using only selected priorities: P0-P3."),
    ] = None,
    max_documents_per_source: Annotated[
        int,
        typer.Option(
            "--max-documents-per-source",
            min=1,
            help="Bound fixture records processed per source where the parser supports it.",
        ),
    ] = 1,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Local evidence directory to refresh."),
    ] = None,
    snapshot_output: Annotated[
        Path,
        typer.Option(
            "--snapshot-output",
            help="Frontend graph snapshot path to write.",
        ),
    ] = Path("public/platform-demo/supply-chain-graph.json"),
    snapshot_limit: Annotated[
        int,
        typer.Option("--snapshot-limit", min=1, help="Maximum graph nodes and edges to export."),
    ] = 500,
    observed_at: Annotated[
        str | None,
        typer.Option(
            "--observed-at", help="ISO metric observation timestamp for idempotent replay."
        ),
    ] = None,
    fail_fast: Annotated[
        bool,
        typer.Option("--fail-fast", help="Stop after the first source refresh failure."),
    ] = False,
    require_ready: Annotated[
        bool,
        typer.Option(
            "--require-ready",
            help="Exit non-zero when the minimal demo path is blocked.",
        ),
    ] = False,
) -> None:
    settings = get_settings(secret_file_loading="available")
    demo_settings = settings.model_copy(update={"data_dir": data_dir or settings.data_dir})
    try:
        priorities = normalize_priorities(priority)
        summary = prepare_demo(
            settings=demo_settings,
            source_ids=set(source_id) if source_id else None,
            priorities=priorities,
            max_documents_per_source=max_documents_per_source,
            fail_fast=fail_fast,
            snapshot_output_path=snapshot_output,
            snapshot_limit=snapshot_limit,
            observed_at=_parse_observed_at(observed_at),
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(summary.model_dump(mode="json"), indent=2))
    if require_ready and not summary.readiness.demo_ready_now:
        raise typer.Exit(1)


@app.command("source-credentials")
def source_credentials(
    only_missing: Annotated[
        bool,
        typer.Option("--only-missing", help="Hide configured source credentials."),
    ] = False,
) -> None:
    settings = get_settings(secret_file_loading="available")
    report = build_source_credential_report(
        source_configs=load_all_source_configs(settings.source_dir),
        settings=settings,
        only_missing=only_missing,
    )
    typer.echo(json.dumps(report.model_dump(mode="json"), indent=2))


@app.command("llm-smoke")
def llm_smoke(
    prompt: Annotated[
        str | None,
        typer.Option("--prompt", help="Optional prompt to use for the structured LLM smoke test."),
    ] = None,
) -> None:
    settings = get_settings(secret_file_loading="available")
    factory = ModelFactory(settings)
    try:
        report = asyncio.run(run_llm_smoke(factory, prompt=prompt or DEFAULT_LLM_SMOKE_PROMPT))
    except Exception as exc:  # pragma: no cover - exercised through CLI behavior.
        report = failed_llm_smoke_report(
            factory,
            error_type=type(exc).__name__,
            error="Structured LLM smoke failed before validated output was returned.",
        )
        typer.echo(json.dumps(report.model_dump(mode="json"), indent=2))
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(report.model_dump(mode="json"), indent=2))


@app.command("init-db")
def init_db(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Apply migrations to DATABASE_URL. Without this, only list migration files.",
        ),
    ] = False,
) -> None:
    settings = get_settings()
    if apply:
        results = asyncio.run(
            apply_migrations(
                settings.database_url,
                ca_cert_path=settings.database_ca_cert_path,
            )
        )
        typer.echo(json.dumps([result.model_dump(mode="json") for result in results], indent=2))
        return
    files = migration_files()
    typer.echo(
        json.dumps(
            {"migrations": [str(path) for path in files], "count": len(files)},
            indent=2,
        )
    )


@app.command("init-kafka")
def init_kafka(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Create/ensure topics. Without this, only print the bootstrap plan.",
        ),
    ] = False,
    backend: Annotated[
        Literal["direct", "aiven-mcp"],
        typer.Option(help="Topic bootstrap backend used with --apply."),
    ] = "direct",
) -> None:
    specs = load_topic_specs()
    settings = get_settings()
    if not apply:
        typer.echo(
            json.dumps(
                {
                    "topics": [
                        result.model_dump(mode="json") for result in plan_topic_bootstrap(specs)
                    ],
                    "apply": False,
                },
                indent=2,
            )
        )
        return
    if backend == "aiven-mcp":
        raise typer.BadParameter(
            "Aiven MCP topic bootstrap requires an injected controller; use --backend direct here."
        )
    results = asyncio.run(ensure_topics_direct(specs, settings))
    typer.echo(
        json.dumps(
            {"topics": [result.model_dump(mode="json") for result in results], "apply": True},
            indent=2,
        )
    )


@app.command("export-event-schemas")
def export_event_schemas(
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Optional path for the JSON Schema bundle."),
    ] = None,
) -> None:
    payload = export_event_schema_bundle()
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if out is None:
        typer.echo(rendered)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered + "\n", encoding="utf-8")
    typer.echo(str(out))


@app.command("init-neo4j")
def init_neo4j(
    apply: Annotated[
        bool,
        typer.Option(
            "--apply",
            help="Apply Cypher constraints/indexes to NEO4J_URI. Without this, only list files.",
        ),
    ] = False,
) -> None:
    if apply:
        settings = get_settings()
        typer.echo(json.dumps(asyncio.run(_apply_neo4j_migrations(settings)), indent=2))
        return
    paths = sorted(Path("cypher/migrations").glob("*.cypher"))
    typer.echo(json.dumps({"cypher_migrations": [str(path) for path in paths]}, indent=2))


@app.command("record-graph-metrics")
def record_graph_metrics(
    backend: Annotated[
        Literal["file", "postgres"],
        typer.Option("--backend", help="Write graph metrics to local JSONL or PostgreSQL."),
    ] = "file",
    source: Annotated[
        Literal["neo4j", "file"],
        typer.Option("--source", help="Read graph totals from Neo4j or local graph upsert JSONL."),
    ] = "neo4j",
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Directory for local graph upserts and ops_metrics.jsonl."),
    ] = None,
    observed_at: Annotated[
        str | None,
        typer.Option(
            "--observed-at", help="ISO metric observation timestamp for idempotent replay."
        ),
    ] = None,
) -> None:
    settings = get_settings()
    payload = asyncio.run(
        _record_graph_metrics(
            settings,
            backend=backend,
            source=source,
            data_dir=data_dir,
            observed_at=_parse_observed_at(observed_at),
        )
    )
    typer.echo(json.dumps(payload, indent=2))


@app.command("validate-source")
def validate_source(path: Path) -> None:
    config = load_source_config(path)
    typer.echo(json.dumps({"source_id": config.source_id, "valid": True}, indent=2))


@app.command("register-source")
def register_source(
    path: Path,
    backend: Annotated[
        Literal["file", "postgres"],
        typer.Option(help="Where to register the source definition."),
    ] = "file",
    actor: Annotated[
        str | None,
        typer.Option("--actor", help="Optional operator or automation identity for audit."),
    ] = None,
) -> None:
    config = load_source_config(path)
    settings = get_settings()
    if backend == "postgres":
        inserted = asyncio.run(_register_source_postgres(config, settings))
        pg_result: Literal["created", "upserted"] = "created" if inserted else "upserted"
        _write_source_registry_audit(
            settings=settings,
            config=config,
            backend=backend,
            result=pg_result,
            config_path=path,
            actor=actor,
        )
        typer.echo(
            json.dumps(
                {
                    "source_id": config.source_id,
                    "registered": True,
                    "backend": backend,
                    "inserted": inserted,
                    "result": pg_result,
                    "audit_collection": "source_registry_audit",
                },
                indent=2,
            )
        )
        return

    store = FileEvidenceStore(settings.data_dir)
    file_result = store.upsert_registered_source(config)
    _write_source_registry_audit(
        settings=settings,
        config=config,
        backend=backend,
        result=file_result,
        config_path=path,
        actor=actor,
    )
    typer.echo(
        json.dumps(
            {
                "source_id": config.source_id,
                "registered": True,
                "backend": backend,
                "result": file_result,
                "audit_collection": "source_registry_audit",
            },
            indent=2,
        )
    )


@app.command("test-fetch")
def test_fetch(
    source_id: str,
    limit: Annotated[int, typer.Option("--limit", min=1)] = 2,
    live: Annotated[
        bool,
        typer.Option("--live", help="Fetch a bounded live sample from the source."),
    ] = False,
) -> None:
    settings = get_settings(secret_file_loading="available")
    path = find_source_config(source_id)
    config = load_source_config(path)
    if live:
        materialize_source_runtime_env(settings)
        typer.echo(
            json.dumps(
                asyncio.run(fetch_source_sample(config=config, max_documents=limit)),
                indent=2,
            )
        )
        return
    typer.echo(
        json.dumps(
            {
                "source_id": config.source_id,
                "adapter": config.adapter,
                "base_url": config.base_url,
                "limit": limit,
                "dry_run": True,
                "live": False,
            },
            indent=2,
        )
    )


@app.command("ingest-once")
def ingest_once(
    source_id: str,
    max_documents: Annotated[int, typer.Option("--max-documents", min=1)] = 100,
    fixture: Annotated[Path | None, typer.Option("--fixture")] = None,
    live: Annotated[
        bool,
        typer.Option("--live", help="Fetch from the source instead of using configured fixtures."),
    ] = False,
) -> None:
    settings = get_settings(secret_file_loading="available")
    config = load_source_config(find_source_config(source_id))
    if live:
        materialize_source_runtime_env(settings)
        live_ingest = LIVE_INGEST_BY_PROFILE.get(config.parser.profile)
        if live_ingest is None:
            raise typer.BadParameter(f"Live ingestion not implemented for {config.parser.profile}")
        stats: dict[str, int] = asyncio.run(
            live_ingest(
                config=config,
                settings=settings,
                max_documents=max_documents,
            )
        )
        typer.echo(json.dumps(stats, indent=2))
        return

    fixture_path = fixture or config.fixtures.success
    if fixture_path is None:
        raise typer.BadParameter("Provide --fixture or configure fixtures.success")
    fixture_ingest = FIXTURE_INGEST_BY_PROFILE.get(config.parser.profile)
    if fixture_ingest is None:
        raise typer.BadParameter(f"Fixture ingestion not implemented for {config.parser.profile}")
    stats = fixture_ingest(
        config=config,
        fixture_path=fixture_path,
        settings=settings,
        max_documents=max_documents,
    )
    typer.echo(json.dumps(stats, indent=2))


@app.command("sync-postgres-evidence")
def sync_postgres_evidence(
    source_id: Annotated[
        str | None,
        typer.Option("--source-id", help="Sync only one source; defaults to all source configs."),
    ] = None,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Local evidence directory to replay into Postgres."),
    ] = None,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Write the selected local evidence rows to DATABASE_URL."),
    ] = False,
    aiven_defaults: Annotated[
        bool,
        typer.Option(
            "--aiven-defaults",
            help="Use conventional .platform-secrets/aiven paths when env vars are unset.",
        ),
    ] = False,
    aiven_secrets_dir: Annotated[
        Path,
        typer.Option("--aiven-secrets-dir", help="Directory used by --aiven-defaults."),
    ] = AIVEN_DEFAULT_SECRETS_DIR,
) -> None:
    settings = get_settings(secret_file_loading="available")
    if aiven_defaults:
        settings = settings_with_aiven_demo_defaults(settings, secrets_dir=aiven_secrets_dir)
    sync_settings = settings.model_copy(update={"data_dir": data_dir or settings.data_dir})
    configs = (
        [load_source_config(find_source_config(source_id, sync_settings.source_dir))]
        if source_id is not None
        else load_all_source_configs(sync_settings.source_dir)
    )
    if not configs:
        raise typer.BadParameter(f"No source configs found under {sync_settings.source_dir}")

    if apply:
        summary = asyncio.run(
            sync_local_evidence_to_postgres(settings=sync_settings, configs=configs)
        )
    else:
        summary = plan_local_evidence_to_postgres(settings=sync_settings, configs=configs)

    typer.echo(
        json.dumps(
            {
                **summary.model_dump(mode="json"),
                "apply": apply,
                "data_dir": str(sync_settings.data_dir),
            },
            indent=2,
        )
    )


@app.command("run-scheduler")
def run_scheduler(
    source_id: Annotated[
        str | None,
        typer.Option("--source-id", help="Schedule only one source."),
    ] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Plan scheduler output without writing DATA_DIR artifacts."),
    ] = False,
    publish_kafka: Annotated[
        bool,
        typer.Option(
            "--publish-kafka",
            help="Publish generated ingest.jobs envelopes to KAFKA_BOOTSTRAP_SERVERS.",
        ),
    ] = False,
) -> None:
    if dry_run and publish_kafka:
        raise typer.BadParameter(
            "--publish-kafka requires persisted scheduler events; omit --dry-run."
        )
    settings = get_settings()
    summary = run_local_scheduler(
        settings=settings,
        source_ids={source_id} if source_id else None,
        limit=limit,
        dry_run=dry_run,
    )
    payload: dict[str, object] = {"scheduler": summary.model_dump(mode="json")}
    if publish_kafka:
        payload["kafka"] = asyncio.run(
            publish_scheduled_events_to_kafka(settings=settings, event_ids=summary.event_ids)
        ).model_dump(mode="json")
    typer.echo(json.dumps(payload, indent=2))


@app.command("publish-events")
def publish_events(
    event_id: Annotated[
        list[str] | None,
        typer.Option("--event-id", help="Publish one or more exact event IDs from events.jsonl."),
    ] = None,
    event_type: Annotated[
        str | None,
        typer.Option("--event-type", help="Filter events.jsonl by event_type/topic."),
    ] = None,
    idempotency_key: Annotated[
        str | None,
        typer.Option("--idempotency-key", help="Filter events.jsonl by idempotency key."),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Maximum selected events after filtering."),
    ] = None,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Directory containing local events.jsonl output."),
    ] = None,
    all_events: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Allow selecting all events when no exact selector is provided.",
        ),
    ] = False,
    publish_kafka: Annotated[
        bool,
        typer.Option(
            "--publish-kafka",
            help="Publish selected envelopes to KAFKA_BOOTSTRAP_SERVERS.",
        ),
    ] = False,
) -> None:
    if not all_events and not event_id and event_type is None and idempotency_key is None:
        raise typer.BadParameter(
            "Provide --event-id, --event-type, --idempotency-key, or explicit --all."
        )
    settings = get_settings()
    resolved_data_dir = data_dir or settings.data_dir
    store = FileEvidenceStore(resolved_data_dir)
    try:
        events = select_outbox_events(
            store=store,
            event_ids=event_id,
            event_type=event_type,
            idempotency_key=idempotency_key,
            limit=limit,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not publish_kafka:
        summary = summarize_outbox_selection(
            data_dir=str(resolved_data_dir),
            events=events,
            publish_kafka=False,
        )
        typer.echo(json.dumps(summary.model_dump(mode="json"), indent=2))
        return
    summary = asyncio.run(
        publish_outbox_events_to_kafka(
            settings=settings,
            store=store,
            events=events,
        )
    )
    typer.echo(json.dumps(summary.model_dump(mode="json"), indent=2))


@app.command("run-ingest-worker")
def run_ingest_worker(
    max_documents: Annotated[int | None, typer.Option("--max-documents", min=1)] = None,
    max_messages: Annotated[
        int | None,
        typer.Option(
            "--max-messages",
            min=1,
            help="In --no-once mode, stop after this many Kafka messages.",
        ),
    ] = None,
    idle_timeout_seconds: Annotated[
        float | None,
        typer.Option(
            "--idle-timeout-seconds",
            min=0.1,
            help="In --no-once mode, exit when no Kafka message arrives before this timeout.",
        ),
    ] = None,
    evidence_backend: Annotated[
        Literal["file", "postgres"],
        typer.Option(
            "--evidence-backend",
            help="Persist worker evidence locally only or sync it to DATABASE_URL before commit.",
        ),
    ] = "file",
    once: Annotated[
        bool,
        typer.Option("--once/--no-once", help="Process one ingest.jobs message and exit."),
    ] = True,
) -> None:
    settings = get_settings()
    if once:
        if max_messages is not None or idle_timeout_seconds is not None:
            raise typer.BadParameter("--max-messages and --idle-timeout-seconds require --no-once.")
        one_result = asyncio.run(
            run_ingest_worker_once(
                settings=settings,
                max_documents=max_documents,
                evidence_backend=evidence_backend,
            )
        )
        typer.echo(json.dumps(one_result.model_dump(mode="json"), indent=2))
        return
    loop_result = asyncio.run(
        run_ingest_worker_loop(
            settings=settings,
            max_messages=max_messages,
            max_documents=max_documents,
            idle_timeout_seconds=idle_timeout_seconds,
            evidence_backend=evidence_backend,
        )
    )
    typer.echo(json.dumps(loop_result.model_dump(mode="json"), indent=2))


@app.command("run-extractor")
def run_extractor(
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Directory containing raw document and chunk JSONL files."),
    ] = None,
    source_id: Annotated[
        str | None,
        typer.Option("--source-id", help="Extract only chunks for one source."),
    ] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1)] = None,
    consume_kafka: Annotated[
        bool,
        typer.Option("--consume-kafka", help="Consume ingest.document_parsed events from Kafka."),
    ] = False,
    max_messages: Annotated[
        int | None,
        typer.Option(
            "--max-messages",
            min=1,
            help="With --consume-kafka, stop after this many extraction events.",
        ),
    ] = None,
    idle_timeout_seconds: Annotated[
        float | None,
        typer.Option(
            "--idle-timeout-seconds",
            min=0.1,
            help="With --consume-kafka, exit when no extraction event arrives before this timeout.",
        ),
    ] = None,
) -> None:
    settings = get_settings()
    if consume_kafka:
        if data_dir is not None or source_id is not None or limit is not None:
            raise typer.BadParameter(
                "--consume-kafka cannot be combined with --data-dir, --source-id, or --limit."
            )
        worker_summary = asyncio.run(
            run_extractor_consumer(
                settings=settings,
                max_messages=max_messages,
                idle_timeout_seconds=idle_timeout_seconds,
            )
        )
        typer.echo(json.dumps(worker_summary.model_dump(mode="json"), indent=2))
        return
    if max_messages is not None or idle_timeout_seconds is not None:
        raise typer.BadParameter(
            "--max-messages and --idle-timeout-seconds require --consume-kafka."
        )
    replay_summary = run_local_extractor(
        settings=settings,
        data_dir=data_dir or settings.data_dir,
        source_id=source_id,
        limit=limit,
    )
    typer.echo(json.dumps(replay_summary.model_dump(mode="json"), indent=2))


@app.command("run-graph-mapper")
def run_graph_mapper(
    consume_kafka: Annotated[
        bool,
        typer.Option("--consume-kafka", help="Consume ingest.extraction_completed events."),
    ] = False,
    max_messages: Annotated[
        int | None,
        typer.Option(
            "--max-messages",
            min=1,
            help="With --consume-kafka, stop after this many extraction events.",
        ),
    ] = None,
    idle_timeout_seconds: Annotated[
        float | None,
        typer.Option(
            "--idle-timeout-seconds",
            min=0.1,
            help="With --consume-kafka, exit when no extraction event arrives before this timeout.",
        ),
    ] = None,
) -> None:
    if not consume_kafka:
        raise typer.BadParameter("run-graph-mapper currently requires --consume-kafka.")
    settings = get_settings()
    worker_summary = asyncio.run(
        run_graph_mapper_consumer(
            settings=settings,
            max_messages=max_messages,
            idle_timeout_seconds=idle_timeout_seconds,
        )
    )
    typer.echo(json.dumps(worker_summary.model_dump(mode="json"), indent=2))


@app.command("run-graph-writer")
def run_graph_writer(
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Directory containing graph upsert JSONL files."),
    ] = None,
    source: Annotated[
        Literal["file", "postgres"],
        typer.Option("--source", help="Read graph upserts from local JSONL or PostgreSQL audit."),
    ] = "file",
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Apply graph upserts to NEO4J_URI."),
    ] = False,
    consume_kafka: Annotated[
        bool,
        typer.Option("--consume-kafka", help="Consume graph upsert events from Kafka."),
    ] = False,
    max_messages: Annotated[
        int | None,
        typer.Option(
            "--max-messages",
            min=1,
            help="With --consume-kafka, stop after this many graph events.",
        ),
    ] = None,
    idle_timeout_seconds: Annotated[
        float | None,
        typer.Option(
            "--idle-timeout-seconds",
            min=0.1,
            help="With --consume-kafka, exit when no graph event arrives before this timeout.",
        ),
    ] = None,
    limit: Annotated[
        int | None,
        typer.Option("--limit", min=1, help="Limit graph upserts read from PostgreSQL audit."),
    ] = None,
    summary_only: Annotated[
        bool,
        typer.Option(
            "--summary-only",
            help="When applying replay, omit per-statement Neo4j results and print aggregates.",
        ),
    ] = False,
) -> None:
    settings = get_settings()
    if consume_kafka:
        if apply or data_dir is not None or source != "file" or limit is not None or summary_only:
            raise typer.BadParameter(
                "--consume-kafka cannot be combined with --apply, --data-dir, --source, "
                "--limit, or --summary-only."
            )
        summary = asyncio.run(
            run_graph_writer_consumer_loop(
                settings=settings,
                max_messages=max_messages,
                idle_timeout_seconds=idle_timeout_seconds,
            )
        )
        typer.echo(json.dumps(summary.model_dump(mode="json"), indent=2))
        return
    if max_messages is not None or idle_timeout_seconds is not None:
        raise typer.BadParameter(
            "--max-messages and --idle-timeout-seconds require --consume-kafka."
        )
    if source == "postgres":
        if data_dir is not None:
            raise typer.BadParameter("--data-dir is only valid with --source file.")
        if apply:
            typer.echo(
                json.dumps(
                    _graph_replay_cli_payload(
                        asyncio.run(_apply_graph_replay_from_postgres(settings, limit=limit)),
                        summary_only=summary_only,
                    ),
                    indent=2,
                )
            )
            return
        typer.echo(
            json.dumps(
                asyncio.run(_summarize_graph_replay_from_postgres(settings, limit=limit)),
                indent=2,
            )
        )
        return
    if limit is not None:
        raise typer.BadParameter("--limit is only valid with --source postgres.")
    replay_dir = data_dir or settings.data_dir
    if apply:
        typer.echo(
            json.dumps(
                _graph_replay_cli_payload(
                    asyncio.run(_apply_graph_replay(settings, replay_dir)),
                    summary_only=summary_only,
                ),
                indent=2,
            )
        )
        return
    typer.echo(
        json.dumps(
            _graph_replay_cli_payload(
                summarize_graph_replay(replay_dir).model_dump(mode="json"),
                summary_only=summary_only,
            ),
            indent=2,
        )
    )


@app.command("sync-graph-view")
def sync_graph_view(
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Directory containing local graph upsert JSONL files."),
    ] = None,
    apply_neo4j: Annotated[
        bool,
        typer.Option(
            "--apply-neo4j",
            help="Replay local graph upserts into NEO4J_URI before recording metrics/snapshot.",
        ),
    ] = False,
    snapshot_source: Annotated[
        Literal["file", "neo4j"],
        typer.Option("--snapshot-source", help="Export the dashboard snapshot from file or Neo4j."),
    ] = "file",
    output: Annotated[
        Path,
        typer.Option("--output", help="Snapshot path consumed by the frontend dashboard."),
    ] = Path("public/platform-demo/supply-chain-graph.json"),
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, help="Maximum nodes and relationships to export."),
    ] = 5_000,
    record_metrics: Annotated[
        bool,
        typer.Option("--record-metrics/--no-record-metrics", help="Write graph count metrics."),
    ] = True,
) -> None:
    settings = get_settings()
    graph_dir = data_dir or settings.data_dir
    replay_payload: dict[str, object] | None = None
    if apply_neo4j:
        replay_payload = _graph_replay_cli_payload(
            asyncio.run(_apply_graph_replay(settings, graph_dir)),
            summary_only=True,
        )

    metric_payload: dict[str, object] | None = None
    if record_metrics:
        metric_payload = asyncio.run(
            _record_graph_metrics(
                settings,
                backend="file",
                source=snapshot_source,
                data_dir=graph_dir,
            )
        )

    if snapshot_source == "neo4j":
        snapshot_payload = asyncio.run(_export_graph_snapshot(settings, output, limit=limit))
    else:
        snapshot_payload = _export_file_graph_snapshot(graph_dir, output, limit=limit)

    typer.echo(
        json.dumps(
            {
                "data_dir": str(graph_dir),
                "apply_neo4j": apply_neo4j,
                "snapshot_source": snapshot_source,
                "neo4j_replay": replay_payload,
                "graph_metrics": metric_payload,
                "graph_snapshot": snapshot_payload,
            },
            indent=2,
        )
    )


@app.command("run-risk-engine")
def run_risk_engine(
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Directory containing extraction run JSONL files."),
    ] = None,
    consume_kafka: Annotated[
        bool,
        typer.Option("--consume-kafka", help="Consume ingest.extraction_completed events."),
    ] = False,
    max_messages: Annotated[
        int | None,
        typer.Option(
            "--max-messages",
            min=1,
            help="With --consume-kafka, stop after this many extraction events.",
        ),
    ] = None,
    idle_timeout_seconds: Annotated[
        float | None,
        typer.Option(
            "--idle-timeout-seconds",
            min=0.1,
            help="With --consume-kafka, exit when no extraction event arrives before this timeout.",
        ),
    ] = None,
) -> None:
    settings = get_settings()
    if consume_kafka:
        if data_dir is not None:
            raise typer.BadParameter("--consume-kafka cannot be combined with --data-dir.")
        worker_summary = asyncio.run(
            run_risk_engine_consumer(
                settings=settings,
                max_messages=max_messages,
                idle_timeout_seconds=idle_timeout_seconds,
            )
        )
        typer.echo(json.dumps(worker_summary.model_dump(mode="json"), indent=2))
        return
    if max_messages is not None or idle_timeout_seconds is not None:
        raise typer.BadParameter(
            "--max-messages and --idle-timeout-seconds require --consume-kafka."
        )
    replay_summary = run_local_risk_engine(data_dir or settings.data_dir)
    typer.echo(json.dumps(replay_summary.model_dump(mode="json"), indent=2))


@app.command("run-agent-swarm")
def run_agent_swarm(
    case_id: Annotated[str | None, typer.Option("--case-id")] = None,
    case_key: Annotated[str | None, typer.Option("--case-key")] = None,
    consume_kafka: Annotated[
        bool,
        typer.Option("--consume-kafka", help="Consume risk.case_created events."),
    ] = False,
    max_messages: Annotated[
        int | None,
        typer.Option(
            "--max-messages",
            min=1,
            help="With --consume-kafka, stop after this many risk cases.",
        ),
    ] = None,
    idle_timeout_seconds: Annotated[
        float | None,
        typer.Option(
            "--idle-timeout-seconds",
            min=0.1,
            help="With --consume-kafka, exit when no risk case arrives before this timeout.",
        ),
    ] = None,
) -> None:
    settings = get_settings()
    if consume_kafka:
        if case_key is not None or case_id is not None:
            raise typer.BadParameter("--consume-kafka cannot be combined with case selectors.")
        worker_summary = asyncio.run(
            run_agent_swarm_consumer(
                settings=settings,
                max_messages=max_messages,
                idle_timeout_seconds=idle_timeout_seconds,
            )
        )
        typer.echo(json.dumps(worker_summary.model_dump(mode="json"), indent=2))
        return
    if max_messages is not None or idle_timeout_seconds is not None:
        raise typer.BadParameter(
            "--max-messages and --idle-timeout-seconds require --consume-kafka."
        )
    if case_key is None and case_id is None:
        raise typer.BadParameter("Provide --case-key or --case-id")
    selected_case_key = case_key or _case_key_from_id_or_key(settings.data_dir, str(case_id))
    summary = run_local_agent_swarm(settings.data_dir, selected_case_key)
    typer.echo(json.dumps(summary.model_dump(mode="json"), indent=2))


@app.command("create-dashboard")
def create_dashboard(
    name: str,
    out: Annotated[Path | None, typer.Option("--out")] = None,
    provision: Annotated[
        bool,
        typer.Option("--provision", help="Upload generated dashboard JSON to GRAFANA_URL."),
    ] = False,
    provision_datasource: Annotated[
        bool,
        typer.Option(
            "--provision-datasource",
            help="Create or update the Grafana PostgreSQL datasource before dashboard upload.",
        ),
    ] = False,
    datasource_name: Annotated[str, typer.Option("--datasource-name")] = "Platform PostgreSQL",
    datasource_uid: Annotated[str, typer.Option("--datasource-uid")] = "platform-postgres",
    folder_uid: Annotated[str | None, typer.Option("--folder-uid")] = None,
    message: Annotated[str | None, typer.Option("--message")] = None,
) -> None:
    definition = Path("dashboards/definitions") / f"{name}.yaml"
    settings = get_settings()
    if not definition.exists() and name == "all":
        generated_paths = []
        for path in sorted(Path("dashboards/definitions").glob("*.yaml")):
            output_path = Path("dashboards/generated") / f"{path.stem}.json"
            generated_paths.append(generate_dashboard(path, output_path))
        payload: dict[str, object] = {"generated": [str(path) for path in generated_paths]}
        if provision_datasource:
            payload["datasource"] = asyncio.run(
                _provision_grafana_datasource(
                    settings,
                    name=datasource_name,
                    uid=datasource_uid,
                )
            )
        if provision:
            payload["provisioned"] = asyncio.run(
                _provision_grafana_dashboards(
                    settings,
                    generated_paths,
                    folder_uid=folder_uid,
                    message=message,
                )
            )
        typer.echo(json.dumps(payload, indent=2))
        return
    output = out or Path("dashboards/generated") / f"{name}.json"
    generated = generate_dashboard(definition, output)
    payload = {"generated": [str(generated)]}
    if provision_datasource:
        payload["datasource"] = asyncio.run(
            _provision_grafana_datasource(
                settings,
                name=datasource_name,
                uid=datasource_uid,
            )
        )
    if not provision:
        if provision_datasource:
            typer.echo(json.dumps(payload, indent=2))
            return
        typer.echo(str(generated))
        return
    provisioned = asyncio.run(
        _provision_grafana_dashboards(
            settings,
            [generated],
            folder_uid=folder_uid,
            message=message,
        )
    )
    typer.echo(
        json.dumps(
            {**payload, "provisioned": provisioned},
            indent=2,
        )
    )


@app.command("query-sources")
def query_sources(
    status: Annotated[
        str | None,
        typer.Option("--status", help="Filter by source health status, such as failed."),
    ] = None,
    priority: Annotated[
        str | None,
        typer.Option("--priority", help="Filter by checked-in source priority."),
    ] = None,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Directory containing source_health.jsonl."),
    ] = None,
    backend: Annotated[
        Literal["file", "postgres"],
        typer.Option("--backend", help="Read source health from local JSONL or PostgreSQL."),
    ] = "file",
    endpoint_access: Annotated[
        SourceEndpointAccess | None,
        typer.Option(
            "--endpoint-access",
            help="Filter by endpoint access: public, public_limited, configured, requires_env.",
        ),
    ] = None,
) -> None:
    settings = get_settings(secret_file_loading="available")
    materialize_source_runtime_env(settings)
    health_rows = (
        asyncio.run(_read_postgres_source_health_rows(settings))
        if backend == "postgres"
        else _read_source_health_rows(data_dir or settings.data_dir)
    )
    rows = _source_query_rows(
        configs=load_all_source_configs(settings.source_dir),
        health_rows=health_rows,
        status=status,
        priority=priority,
        endpoint_access=endpoint_access,
        settings=settings,
    )
    typer.echo(json.dumps(rows, indent=2))


@app.command("query-source-runs")
def query_source_runs(
    source_id: Annotated[
        str | None,
        typer.Option("--source-id", help="Filter by source id."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Filter by source run status."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", min=1)] = 20,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Directory containing source_runs.jsonl."),
    ] = None,
    backend: Annotated[
        Literal["file", "postgres"],
        typer.Option("--backend", help="Read source runs from local JSONL or PostgreSQL."),
    ] = "file",
    include_cursors: Annotated[
        bool,
        typer.Option("--include-cursors", help="Include cursor_before and cursor_after snapshots."),
    ] = False,
    latest_state_only: Annotated[
        bool,
        typer.Option(
            "--latest-state-only",
            help="Collapse local source-run history to the latest row per source_run_id.",
        ),
    ] = False,
) -> None:
    settings = get_settings()
    run_rows = (
        asyncio.run(
            _read_postgres_source_run_rows(
                settings,
                source_id=source_id,
                status=status,
                limit=limit,
            )
        )
        if backend == "postgres"
        else _read_source_run_rows(data_dir or settings.data_dir)
    )
    rows = _source_run_query_rows(
        run_rows=run_rows,
        source_id=source_id,
        status=status,
        limit=limit,
        include_cursors=include_cursors,
        latest_state_only=latest_state_only,
    )
    typer.echo(json.dumps(rows, indent=2))


@app.command("query-human-reviews")
def query_human_reviews(
    status: Annotated[
        Literal["open", "resolved"] | None,
        typer.Option("--status", help="Filter human-review tasks by status."),
    ] = None,
    backend: Annotated[
        Literal["file", "postgres"],
        typer.Option("--backend", help="Read review tasks from local JSONL or PostgreSQL."),
    ] = "file",
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Directory containing human_review_queue.jsonl."),
    ] = None,
) -> None:
    settings = get_settings()
    rows = (
        asyncio.run(_postgres_human_review_rows(settings, status=status))
        if backend == "postgres"
        else _human_review_rows_from_tasks(
            _local_human_review_tasks(
                FileEvidenceStore(data_dir or settings.data_dir),
                status=status,
            )
        )
    )
    typer.echo(json.dumps(rows, indent=2))


@app.command("record-human-feedback")
def record_human_feedback(
    review_task_id: UUID,
    decision: Annotated[
        HumanReviewDecision,
        typer.Option(
            "--decision",
            help="Reviewer decision for the human-review task.",
        ),
    ],
    reviewer: Annotated[str | None, typer.Option("--reviewer")] = None,
    comment: Annotated[str | None, typer.Option("--comment")] = None,
    backend: Annotated[
        Literal["file", "postgres"],
        typer.Option("--backend", help="Record feedback in local JSONL or PostgreSQL."),
    ] = "file",
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Directory containing human_review_queue.jsonl."),
    ] = None,
) -> None:
    settings = get_settings()
    payload = (
        asyncio.run(
            _record_postgres_human_feedback(
                settings=settings,
                review_task_id=review_task_id,
                decision=decision,
                reviewer=reviewer,
                comment=comment,
            )
        )
        if backend == "postgres"
        else _record_local_human_feedback(
            store=FileEvidenceStore(data_dir or settings.data_dir),
            review_task_id=review_task_id,
            decision=decision,
            reviewer=reviewer,
            comment=comment,
        )
    )
    typer.echo(json.dumps(payload, indent=2))


@app.command("query-graph")
def query_graph(
    query_name: str,
    commodity_key: Annotated[str | None, typer.Option("--commodity-key")] = None,
    disaster_key: Annotated[str | None, typer.Option("--disaster-key")] = None,
    drug_key: Annotated[str | None, typer.Option("--drug-key")] = None,
    facility_key: Annotated[str | None, typer.Option("--facility-key")] = None,
    ingredient_key: Annotated[str | None, typer.Option("--ingredient-key")] = None,
    port_key: Annotated[str | None, typer.Option("--port-key")] = None,
    recall_key: Annotated[str | None, typer.Option("--recall-key")] = None,
    risk_case_key: Annotated[str | None, typer.Option("--risk-case-key")] = None,
    shortage_key: Annotated[str | None, typer.Option("--shortage-key")] = None,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Run the query against NEO4J_URI."),
    ] = False,
) -> None:
    try:
        plan = load_graph_query_plan(
            query_name,
            parameters={
                "commodity_key": commodity_key,
                "disaster_key": disaster_key,
                "drug_key": drug_key,
                "facility_key": facility_key,
                "ingredient_key": ingredient_key,
                "port_key": port_key,
                "recall_key": recall_key,
                "risk_case_key": risk_case_key,
                "shortage_key": shortage_key,
            },
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if apply:
        settings = get_settings()
        typer.echo(json.dumps(asyncio.run(_run_graph_query(settings, plan)), indent=2))
        return
    typer.echo(json.dumps(plan.model_dump(mode="json"), indent=2))


@app.command("graph-insights")
def graph_insights(
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Local evidence directory containing graph upsert JSONL."),
    ] = None,
    top: Annotated[
        int,
        typer.Option("--top", min=1, help="Number of top labels, relationships, and hubs."),
    ] = 10,
) -> None:
    settings = get_settings()
    try:
        summary = summarize_file_graph(data_dir or settings.data_dir, top=top)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(json.dumps(summary.model_dump(mode="json"), indent=2))


@app.command("export-graph-snapshot")
def export_graph_snapshot(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            help="Snapshot path consumed by the frontend dashboard.",
        ),
    ] = Path("public/platform-demo/supply-chain-graph.json"),
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, help="Maximum nodes and relationships to export."),
    ] = 500,
    source: Annotated[
        Literal["neo4j", "file"],
        typer.Option("--source", help="Read graph snapshot from Neo4j or local JSONL files."),
    ] = "neo4j",
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Local evidence directory for --source file."),
    ] = None,
) -> None:
    settings = get_settings()
    if source == "file":
        typer.echo(
            json.dumps(
                _export_file_graph_snapshot(
                    data_dir or settings.data_dir,
                    output,
                    limit=limit,
                ),
                indent=2,
            )
        )
        return
    typer.echo(
        json.dumps(
            asyncio.run(_export_graph_snapshot(settings, output, limit=limit)),
            indent=2,
        )
    )


@app.command("import-dashboard-graph-chat-audit")
def import_dashboard_graph_chat_audit(
    audit_path: Annotated[
        Path | None,
        typer.Option(
            "--audit-path",
            help="Path to dashboard_graph_chat_audit.jsonl. Defaults to DATA_DIR.",
        ),
    ] = None,
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Directory containing local events.jsonl output."),
    ] = None,
) -> None:
    settings = get_settings()
    resolved_data_dir = data_dir or settings.data_dir
    resolved_audit_path = audit_path or default_dashboard_graph_chat_audit_path(resolved_data_dir)
    summary = import_dashboard_graph_chat_audit_events(
        audit_path=resolved_audit_path,
        store=FileEvidenceStore(resolved_data_dir),
    )
    typer.echo(json.dumps(summary.model_dump(mode="json"), indent=2))


@app.command("explain-case")
def explain_case(case_key: str) -> None:
    settings: Settings = get_settings()
    explanation = explain_case_from_store(settings.data_dir, case_key)
    typer.echo(json.dumps(explanation.model_dump(mode="json"), indent=2))
