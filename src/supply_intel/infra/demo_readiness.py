from __future__ import annotations

from pathlib import Path
from typing import Literal

from supply_intel.infra.secrets import validate_cloud_secret_bundle
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.source import SourceConfig
from supply_intel.observability.graph_metrics import GRAPH_NODES_TOTAL, GRAPH_RELATIONSHIPS_TOTAL
from supply_intel.settings import Settings, source_runtime_env_value

DemoReadinessStatus = Literal["ready", "warning", "blocked", "manual"]
AIVEN_DEFAULT_SECRETS_DIR = Path(".platform-secrets/aiven")


class DemoReadinessCheck(StrictBaseModel):
    area: str
    status: DemoReadinessStatus
    summary: str
    details: dict[str, object] = {}


class DemoReadinessReport(StrictBaseModel):
    demo_ready_now: bool
    polished_cloud_demo_ready: bool
    checks: list[DemoReadinessCheck]
    missing_live_source_credentials: list[str]
    recommended_commands: list[str]


def inspect_demo_readiness(
    *,
    settings: Settings,
    source_configs: list[SourceConfig],
    dashboard_definition_dir: Path = Path("dashboards/definitions"),
    dashboard_generated_dir: Path = Path("dashboards/generated"),
    graph_counts: dict[str, int] | None = None,
    graph_count_source: Literal["neo4j", "file", "not_checked"] = "not_checked",
) -> DemoReadinessReport:
    checks = [
        _agent_runtime_check(settings),
        _source_credential_check(settings, source_configs),
        _dashboard_check(dashboard_definition_dir, dashboard_generated_dir),
        _grafana_provisioning_check(settings),
        _cloud_worker_check(settings),
        _graph_data_check(graph_counts, graph_count_source=graph_count_source),
    ]
    blocking_areas = {"agent_runtime", "source_fixtures", "dashboard_assets"}
    demo_ready_now = not any(
        check.status == "blocked" and check.area in blocking_areas for check in checks
    )
    polished_cloud_demo_ready = all(
        check.status == "ready"
        for check in checks
        if check.area in {"grafana_provisioning", "cloud_worker"}
    )
    return DemoReadinessReport(
        demo_ready_now=demo_ready_now,
        polished_cloud_demo_ready=polished_cloud_demo_ready,
        checks=checks,
        missing_live_source_credentials=_missing_live_source_credentials(settings, source_configs),
        recommended_commands=_recommended_commands(checks),
    )


def settings_with_aiven_demo_defaults(
    settings: Settings,
    *,
    secrets_dir: Path = AIVEN_DEFAULT_SECRETS_DIR,
) -> Settings:
    values = settings.model_dump()
    _fill_path(values, "database_url_file", secrets_dir / "postgres-url")
    _fill_path(values, "database_ca_cert_path", secrets_dir / "project-ca.pem")
    _fill_path(values, "kafka_ca_cert_path", secrets_dir / "project-ca.pem")
    _fill_path(values, "kafka_client_cert_path", secrets_dir / "kafka-service.cert")
    _fill_path(values, "kafka_client_key_path", secrets_dir / "kafka-service.key")
    _fill_path(values, "grafana_token_file", secrets_dir / "grafana-token")
    _fill_path(values, "grafana_postgres_password_file", secrets_dir / "postgres-password")
    _fill_path(values, "grafana_postgres_tls_ca_cert_path", secrets_dir / "project-ca.pem")
    if values.get("kafka_security_protocol") == "PLAINTEXT":
        values["kafka_security_protocol"] = "SSL"
    _fill_text_from_file(values, "kafka_bootstrap_servers", secrets_dir / "kafka-bootstrap")
    _fill_text_from_file(values, "grafana_url", secrets_dir / "grafana-url")
    _fill_text_from_file(values, "grafana_postgres_host", secrets_dir / "postgres-host")
    _fill_text(values, "aiven_postgres_service", "platform-pg")
    _fill_text(values, "aiven_kafka_service", "platform-kafka")
    _fill_text(values, "aiven_grafana_service", "platform-grafana")
    return Settings(secret_file_loading="available", **values)


def _agent_runtime_check(settings: Settings) -> DemoReadinessCheck:
    configured = {
        "LLM_BASE_URL": bool(settings.llm_base_url),
        "LLM_API_KEY": bool(settings.llm_api_key),
        "LLM_MODEL": bool(settings.llm_model),
    }
    configured_count = sum(configured.values())
    if configured_count == len(configured):
        return DemoReadinessCheck(
            area="agent_runtime",
            status="ready",
            summary="Live OpenAI-compatible Pydantic AI runtime is configured.",
            details={
                "mode": "live",
                "configured": configured,
                "output_mode": settings.llm_output_mode,
            },
        )
    if configured_count == 0:
        return DemoReadinessCheck(
            area="agent_runtime",
            status="ready",
            summary="Deterministic typed extraction is available for the demo.",
            details={
                "mode": "deterministic",
                "configured": configured,
                "output_mode": settings.llm_output_mode,
            },
        )
    return DemoReadinessCheck(
        area="agent_runtime",
        status="warning",
        summary="Partial LLM config is present; live agents will fail closed.",
        details={
            "mode": "partial",
            "configured": configured,
            "output_mode": settings.llm_output_mode,
        },
    )


def _source_credential_check(
    settings: Settings,
    source_configs: list[SourceConfig],
) -> DemoReadinessCheck:
    fixture_sources = [
        config.source_id
        for config in source_configs
        if config.fixtures.success is not None and config.fixtures.success.exists()
    ]
    missing = _missing_live_source_credentials(settings, source_configs)
    optional_missing = sorted(
        {
            config.auth.env
            for config in source_configs
            if config.auth.env is not None
            and not config.auth.required
            and not _env_configured(config.auth.env, settings)
        }
    )
    if not fixture_sources:
        return DemoReadinessCheck(
            area="source_fixtures",
            status="blocked",
            summary="No checked-in fixture-backed sources are available for deterministic demo.",
            details={"fixture_sources": []},
        )
    status: DemoReadinessStatus = "warning" if missing or optional_missing else "ready"
    summary = (
        "Fixture-backed sources are ready; some live source credentials are missing."
        if status == "warning"
        else "Fixture and configured live source credentials are ready."
    )
    return DemoReadinessCheck(
        area="source_fixtures",
        status=status,
        summary=summary,
        details={
            "fixture_source_count": len(fixture_sources),
            "missing_required_env": missing,
            "missing_optional_env": optional_missing,
        },
    )


def _dashboard_check(definition_dir: Path, generated_dir: Path) -> DemoReadinessCheck:
    definitions = sorted(path.stem for path in definition_dir.glob("*.yaml"))
    generated = sorted(path.stem for path in generated_dir.glob("*.json"))
    missing_generated = sorted(set(definitions) - set(generated))
    if not definitions:
        return DemoReadinessCheck(
            area="dashboard_assets",
            status="blocked",
            summary="Dashboard definitions are missing.",
            details={"definition_count": 0, "generated_count": len(generated)},
        )
    status: DemoReadinessStatus = "warning" if missing_generated else "ready"
    return DemoReadinessCheck(
        area="dashboard_assets",
        status=status,
        summary=(
            "Generated dashboard JSON is ready."
            if status == "ready"
            else "Some dashboard JSON files need regeneration."
        ),
        details={
            "definition_count": len(definitions),
            "generated_count": len(generated),
            "missing_generated": missing_generated,
        },
    )


def _grafana_provisioning_check(settings: Settings) -> DemoReadinessCheck:
    summary = validate_cloud_secret_bundle(settings, "aiven-grafana")
    if summary.ready:
        return DemoReadinessCheck(
            area="grafana_provisioning",
            status="ready",
            summary="Grafana datasource and dashboard provisioning secrets are ready.",
            details={
                "grafana_url": settings.grafana_url,
                "token_configured": bool(settings.grafana_token),
                "issues": [],
            },
        )
    return DemoReadinessCheck(
        area="grafana_provisioning",
        status="warning",
        summary=(
            "Grafana dashboards can be generated locally, but cloud provisioning is incomplete."
        ),
        details={
            "grafana_url": settings.grafana_url,
            "token_configured": bool(settings.grafana_token),
            "issues": summary.issues,
        },
    )


def _cloud_worker_check(settings: Settings) -> DemoReadinessCheck:
    summary = validate_cloud_secret_bundle(settings, "aiven-worker")
    return DemoReadinessCheck(
        area="cloud_worker",
        status="ready" if summary.ready else "warning",
        summary=(
            "Aiven PostgreSQL/Kafka worker secret bundle is ready."
            if summary.ready
            else "Aiven PostgreSQL/Kafka worker secrets are incomplete."
        ),
        details={
            "profile": summary.profile,
            "ready": summary.ready,
            "issues": summary.issues,
        },
    )


def _graph_data_check(
    graph_counts: dict[str, int] | None,
    *,
    graph_count_source: Literal["neo4j", "file", "not_checked"],
) -> DemoReadinessCheck:
    if graph_counts is None:
        return DemoReadinessCheck(
            area="graph_data",
            status="manual",
            summary=(
                "Graph counts were not checked; run with --local-graph or --live-neo4j to verify."
            ),
            details={"source": graph_count_source},
        )
    nodes = graph_counts.get(GRAPH_NODES_TOTAL, 0)
    relationships = graph_counts.get(GRAPH_RELATIONSHIPS_TOTAL, 0)
    status: DemoReadinessStatus = "ready" if nodes > 0 and relationships > 0 else "warning"
    source_label = "Neo4j" if graph_count_source == "neo4j" else "local graph files"
    return DemoReadinessCheck(
        area="graph_data",
        status=status,
        summary=(
            f"{source_label} have queryable graph data."
            if status == "ready"
            else f"{source_label} are empty or incomplete."
        ),
        details={"source": graph_count_source, "nodes": nodes, "relationships": relationships},
    )


def _missing_live_source_credentials(
    settings: Settings,
    source_configs: list[SourceConfig],
) -> list[str]:
    return sorted(
        {
            config.auth.env
            for config in source_configs
            if config.auth.env is not None
            and config.auth.required
            and not _env_configured(config.auth.env, settings)
        }
    )


def _env_configured(env_name: str, settings: Settings) -> bool:
    return bool(source_runtime_env_value(env_name, settings))


def _recommended_commands(checks: list[DemoReadinessCheck]) -> list[str]:
    commands = [
        "uv run platform create-dashboard all",
        (
            "uv run platform refresh-demo-data "
            "--priority P0 --priority P1 --max-documents-per-source 1"
        ),
        (
            "uv run platform export-graph-snapshot --source file "
            "--output public/platform-demo/supply-chain-graph.json --limit 500"
        ),
        "uv run platform run-graph-writer --apply --summary-only",
        "uv run platform record-graph-metrics --backend postgres",
    ]
    statuses = {check.area: check.status for check in checks}
    if statuses.get("grafana_provisioning") != "ready":
        commands.append("uv run platform validate-cloud-secrets --profile aiven-grafana")
    else:
        commands.append("uv run platform create-dashboard all --provision-datasource --provision")
    return commands


def _fill_path(values: dict[str, object], field_name: str, path: Path) -> None:
    if values.get(field_name) is None:
        values[field_name] = path


def _fill_text_from_file(values: dict[str, object], field_name: str, path: Path) -> None:
    current = values.get(field_name)
    if current not in {None, "", "localhost:19092", "http://localhost:13000", "postgres"}:
        return
    if not path.exists() or not path.is_file() or path.stat().st_size == 0:
        return
    values[field_name] = path.read_text(encoding="utf-8").strip()


def _fill_text(values: dict[str, object], field_name: str, value: str) -> None:
    if values.get(field_name) in {None, ""}:
        values[field_name] = value
