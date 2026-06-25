from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, Protocol
from uuid import UUID

from supply_intel.events.topics import load_topic_specs
from supply_intel.models.infra import (
    CloudBootstrapFallbackAction,
    CloudBootstrapPlan,
    CloudBootstrapServicePlan,
    LocalBootstrapResult,
    LocalBootstrapSummary,
    MCPAuditAction,
    SafetyLevel,
)
from supply_intel.settings import Settings

POSTGRES_EXTENSIONS = ["vector", "pg_trgm", "uuid-ossp"]
PRODUCTION_ENVIRONMENTS = {"production", "prod", "staging", "shared"}
LOCAL_COMPOSE_FILE = Path("infra/docker-compose.yml")
LOCAL_SERVICES = ["postgres", "redpanda", "neo4j", "grafana"]


class BootstrapRunner(Protocol):
    def __call__(
        self,
        args: Sequence[str],
        *,
        cwd: Path,
        text: bool,
        capture_output: bool,
        check: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]: ...


def local_bootstrap_summary() -> LocalBootstrapSummary:
    cypher_paths = sorted(Path("cypher/migrations").glob("*.cypher"))
    dashboard_paths = sorted(Path("dashboards/definitions").glob("*.yaml"))
    return LocalBootstrapSummary(
        compose_file=str(LOCAL_COMPOSE_FILE),
        services=LOCAL_SERVICES,
        topic_count=len(load_topic_specs()),
        cypher_migrations=[str(path) for path in cypher_paths],
        dashboard_definitions=[str(path) for path in dashboard_paths],
        command=local_bootstrap_command(),
    )


def local_bootstrap_command() -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(LOCAL_COMPOSE_FILE),
        "up",
        "-d",
        *LOCAL_SERVICES,
    ]


def apply_local_bootstrap(
    *,
    timeout_seconds: float = 300,
    runner: BootstrapRunner = subprocess.run,
) -> LocalBootstrapResult:
    command = local_bootstrap_command()
    completed = runner(
        command,
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )
    summary = local_bootstrap_summary()
    summary.apply = True
    return LocalBootstrapResult(
        summary=summary,
        status="started" if completed.returncode == 0 else "failed",
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def approval_required(
    *,
    safety_level: SafetyLevel,
    environment: str,
    destructive: bool = False,
) -> bool:
    normalized_env = environment.casefold()
    if destructive or safety_level in {"credential_access", "production_change"}:
        return True
    if normalized_env in PRODUCTION_ENVIRONMENTS:
        return safety_level in {"safe_write_dev", "migration_write"}
    return False


def cloud_bootstrap_plan(
    *,
    settings: Settings,
    mode: Literal["aiven", "hybrid"],
    project: str | None = None,
    postgres_service: str | None = None,
    kafka_service: str | None = None,
    grafana_service: str | None = None,
    allow_service_create: bool = False,
    cloud: str | None = None,
    postgres_plan: str | None = None,
    kafka_plan: str | None = None,
    grafana_plan: str | None = None,
    approval_id: UUID | None = None,
    actor: str | None = None,
) -> CloudBootstrapPlan:
    resolved_project = project or settings.aiven_project
    resolved_postgres = postgres_service or settings.aiven_postgres_service
    resolved_kafka = kafka_service or settings.aiven_kafka_service
    resolved_grafana = grafana_service or settings.aiven_grafana_service
    topic_count = len(load_topic_specs())
    required_decisions: list[str] = []
    services = [
        _managed_service_plan(
            service_role="postgres",
            service_name=resolved_postgres,
            allow_service_create=allow_service_create,
            plan=postgres_plan,
            cloud=cloud,
            required_decisions=required_decisions,
        ),
        _managed_service_plan(
            service_role="kafka",
            service_name=resolved_kafka,
            allow_service_create=allow_service_create,
            plan=kafka_plan,
            cloud=cloud,
            required_decisions=required_decisions,
        ),
        _managed_service_plan(
            service_role="grafana",
            service_name=resolved_grafana,
            allow_service_create=allow_service_create,
            plan=grafana_plan,
            cloud=cloud,
            required_decisions=required_decisions,
        ),
        CloudBootstrapServicePlan(
            service_role="neo4j",
            target="local",
            service_name=None,
            status="deferred" if mode == "aiven" else "configured",
            notes=["Neo4j remains local-first; Aura migration is replayed from graph audit later."],
        ),
    ]
    if resolved_project is None:
        required_decisions.append("Set AIVEN_PROJECT or pass --project before cloud discovery.")

    actions = _cloud_mcp_actions(
        environment=settings.platform_env,
        project=resolved_project,
        postgres_service=resolved_postgres,
        kafka_service=resolved_kafka,
        grafana_service=resolved_grafana,
        allow_service_create=allow_service_create,
        cloud=cloud,
        postgres_plan=postgres_plan,
        kafka_plan=kafka_plan,
        grafana_plan=grafana_plan,
        topic_count=topic_count,
        approval_id=approval_id,
        actor=actor,
    )
    fallback_actions = _cloud_fallback_actions()
    ready_to_apply = (
        not required_decisions
        and all(action.status != "requires_approval" for action in actions)
        and all(action.status != "blocked" for action in actions)
    )
    return CloudBootstrapPlan(
        mode=mode,
        environment=settings.platform_env,
        project=resolved_project,
        topic_count=topic_count,
        required_postgres_extensions=POSTGRES_EXTENSIONS,
        services=services,
        mcp_actions=actions,
        fallback_actions=fallback_actions,
        required_decisions=required_decisions,
        ready_to_apply=ready_to_apply,
    )


def _managed_service_plan(
    *,
    service_role: Literal["postgres", "kafka", "grafana"],
    service_name: str | None,
    allow_service_create: bool,
    plan: str | None,
    cloud: str | None,
    required_decisions: list[str],
) -> CloudBootstrapServicePlan:
    if service_name is not None:
        return CloudBootstrapServicePlan(
            service_role=service_role,
            target="aiven",
            service_name=service_name,
            status="configured",
        )
    notes = [
        "Existing service name is not configured.",
        "Service creation needs explicit service name, plan, and cloud choices.",
    ]
    if not allow_service_create:
        required_decisions.append(
            f"Set AIVEN_{service_role.upper()}_SERVICE or pass --{service_role}-service."
        )
        return CloudBootstrapServicePlan(
            service_role=service_role,
            target="aiven",
            status="missing_decision",
            notes=notes,
        )
    if plan is None or cloud is None:
        required_decisions.append(
            f"Pass --{service_role}-plan and --cloud to plan {service_role} service creation."
        )
        return CloudBootstrapServicePlan(
            service_role=service_role,
            target="aiven",
            status="missing_decision",
            notes=notes,
        )
    return CloudBootstrapServicePlan(
        service_role=service_role,
        target="aiven",
        status="planned",
        notes=[f"{service_role} service creation is planned but not executed by dry-run."],
    )


def _cloud_mcp_actions(
    *,
    environment: str,
    project: str | None,
    postgres_service: str | None,
    kafka_service: str | None,
    grafana_service: str | None,
    allow_service_create: bool,
    cloud: str | None,
    postgres_plan: str | None,
    kafka_plan: str | None,
    grafana_plan: str | None,
    topic_count: int,
    approval_id: UUID | None,
    actor: str | None,
) -> list[MCPAuditAction]:
    actions = [
        _action(
            action="discover_projects",
            safety_level="safe_read",
            project=project,
            request={},
            environment=environment,
            approval_id=approval_id,
            actor=actor,
        ),
        _action(
            action="discover_services",
            safety_level="safe_read",
            project=project,
            request={"project": project},
            environment=environment,
            approval_id=approval_id,
            actor=actor,
            blocked=project is None,
            error="Aiven project is required for service discovery." if project is None else None,
        ),
    ]
    service_specs = [
        ("postgres", postgres_service, postgres_plan),
        ("kafka", kafka_service, kafka_plan),
        ("grafana", grafana_service, grafana_plan),
    ]
    for service_role, service_name, plan in service_specs:
        if service_name is not None:
            actions.append(
                _action(
                    action=f"get_{service_role}_service",
                    safety_level="safe_read",
                    project=project,
                    service_name=service_name,
                    request={"project": project, "service_name": service_name},
                    environment=environment,
                    approval_id=approval_id,
                    actor=actor,
                    blocked=project is None,
                    error=(
                        "Aiven project is required for service inspection."
                        if project is None
                        else None
                    ),
                )
            )
        elif allow_service_create:
            actions.append(
                _action(
                    action=f"ensure_{service_role}_service",
                    safety_level=(
                        "production_change"
                        if environment.casefold() in PRODUCTION_ENVIRONMENTS
                        else "safe_write_dev"
                    ),
                    project=project,
                    request={
                        "project": project,
                        "service_role": service_role,
                        "plan": plan,
                        "cloud": cloud,
                    },
                    environment=environment,
                    approval_id=approval_id,
                    actor=actor,
                    blocked=project is None or plan is None or cloud is None,
                    error=(
                        "Service creation requires project, service plan, and cloud."
                        if project is None or plan is None or cloud is None
                        else None
                    ),
                )
            )
    actions.extend(
        [
            _action(
                action="verify_postgres_extensions",
                safety_level="safe_read",
                project=project,
                service_name=postgres_service,
                request={
                    "required_extensions": POSTGRES_EXTENSIONS,
                    "service_name": postgres_service,
                },
                environment=environment,
                approval_id=approval_id,
                actor=actor,
                blocked=project is None or postgres_service is None,
                error=(
                    "PostgreSQL service is required before extension verification."
                    if project is None or postgres_service is None
                    else None
                ),
            ),
            _action(
                action="apply_postgres_migrations",
                safety_level="migration_write",
                project=project,
                service_name=postgres_service,
                request={"migration_path": "migrations", "service_name": postgres_service},
                environment=environment,
                approval_id=approval_id,
                actor=actor,
                blocked=project is None or postgres_service is None,
                error=(
                    "PostgreSQL service is required before migration bootstrap."
                    if project is None or postgres_service is None
                    else None
                ),
            ),
            _action(
                action="ensure_kafka_topics",
                safety_level="migration_write",
                project=project,
                service_name=kafka_service,
                request={"topic_count": topic_count, "service_name": kafka_service},
                environment=environment,
                approval_id=approval_id,
                actor=actor,
                blocked=project is None or kafka_service is None,
                error=(
                    "Kafka service is required before topic bootstrap."
                    if project is None or kafka_service is None
                    else None
                ),
            ),
            _action(
                action="provision_grafana_dashboards",
                safety_level="migration_write",
                project=project,
                service_name=grafana_service,
                request={
                    "dashboard_definitions": "dashboards/definitions",
                    "service_name": grafana_service,
                },
                environment=environment,
                approval_id=approval_id,
                actor=actor,
                blocked=project is None or grafana_service is None,
                error=(
                    "Grafana service is required before dashboard provisioning."
                    if project is None or grafana_service is None
                    else None
                ),
            ),
        ]
    )
    return actions


def _action(
    *,
    action: str,
    safety_level: SafetyLevel,
    request: dict[str, object],
    environment: str,
    project: str | None,
    service_name: str | None = None,
    approval_id: UUID | None,
    actor: str | None,
    blocked: bool = False,
    error: str | None = None,
) -> MCPAuditAction:
    needs_approval = approval_required(safety_level=safety_level, environment=environment)
    status: Literal["planned", "blocked", "requires_approval"]
    if blocked:
        status = "blocked"
    elif needs_approval and approval_id is None:
        status = "requires_approval"
    else:
        status = "planned"
    return MCPAuditAction(
        controller="aiven_mcp",
        action=action,
        safety_level=safety_level,
        project=project,
        service_name=service_name,
        request=request,
        response_summary=None,
        status=status,
        destructive=safety_level == "production_change",
        requires_approval=needs_approval,
        approval_id=approval_id if needs_approval else None,
        actor=actor,
        error=error,
    )


def _cloud_fallback_actions() -> list[CloudBootstrapFallbackAction]:
    return [
        CloudBootstrapFallbackAction(
            capability="project_service_discovery",
            preferred_mcp_action="discover_projects/discover_services",
            fallback="Aiven REST API or explicit AIVEN_* environment configuration.",
        ),
        CloudBootstrapFallbackAction(
            capability="postgres_migrations",
            preferred_mcp_action="verify_postgres_extensions/apply_postgres_migrations",
            fallback="Direct DATABASE_URL connection using the migration runner.",
            command="uv run platform init-db --apply",
            requires_credentials=True,
        ),
        CloudBootstrapFallbackAction(
            capability="kafka_topic_bootstrap",
            preferred_mcp_action="ensure_kafka_topics",
            fallback="Direct Kafka AdminClient using KAFKA_* settings.",
            command="uv run platform init-kafka --apply --backend direct",
            requires_credentials=True,
        ),
        CloudBootstrapFallbackAction(
            capability="grafana_dashboards",
            preferred_mcp_action="provision_grafana_dashboards",
            fallback=(
                "Generate JSON locally, then provision through Grafana HTTP API or manual import."
            ),
            command="uv run platform create-dashboard all",
            requires_credentials=True,
        ),
        CloudBootstrapFallbackAction(
            capability="neo4j_graph",
            preferred_mcp_action="not_applicable",
            fallback=(
                "Keep Neo4j local first; later switch NEO4J_URI to Aura and replay graph audit."
            ),
            command="uv run platform init-neo4j --apply",
            requires_credentials=True,
        ),
    ]
