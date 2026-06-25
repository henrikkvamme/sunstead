from __future__ import annotations

from typing import Literal

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.infra.aiven_api import AivenApiController, AivenApiError
from supply_intel.infra.secrets import (
    CloudSecretBundleSummary,
    SecretBundleProfile,
    validate_cloud_secret_bundle,
)
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.infra import AivenServiceRef
from supply_intel.settings import Settings

CloudReadinessServiceRole = Literal["postgres", "kafka", "grafana", "neo4j"]
CloudReadinessServiceStatus = Literal[
    "configured",
    "local",
    "not_configured",
    "not_checked",
    "not_found",
    "running",
    "not_running",
    "type_mismatch",
    "error",
]
CloudReadinessNextStepStatus = Literal["ready", "blocked", "manual"]


class CloudReadinessServiceCheck(StrictBaseModel):
    role: CloudReadinessServiceRole
    target: Literal["aiven", "local"]
    service_name: str | None = None
    expected_service_type: str | None = None
    discovered_service_type: str | None = None
    state: str | None = None
    status: CloudReadinessServiceStatus
    issues: list[str] = []


class CloudReadinessNextStep(StrictBaseModel):
    command: str | None = None
    reason: str
    status: CloudReadinessNextStepStatus


class CloudReadinessReport(StrictBaseModel):
    profile: SecretBundleProfile
    live_aiven: bool
    ready: bool
    secret_summary: CloudSecretBundleSummary
    service_checks: list[CloudReadinessServiceCheck]
    issues: list[str]
    next_steps: list[CloudReadinessNextStep]


async def inspect_cloud_readiness(
    settings: Settings,
    *,
    profile: SecretBundleProfile = "aiven-mvp",
    live_aiven: bool = False,
    controller: AivenApiController | None = None,
) -> CloudReadinessReport:
    secret_summary = validate_cloud_secret_bundle(settings, profile)
    services: list[AivenServiceRef] | None = None
    service_discovery_issue: str | None = None
    owns_controller = False

    if live_aiven:
        if settings.aiven_project is None:
            service_discovery_issue = "AIVEN_PROJECT is required for live Aiven service inspection."
        elif controller is None and settings.aiven_api_token is None:
            service_discovery_issue = (
                "AIVEN_API_TOKEN_FILE or AIVEN_API_TOKEN is required for live Aiven service "
                "inspection."
            )
        else:
            try:
                if controller is None:
                    controller = AivenApiController.from_settings(
                        settings,
                        audit_sink=FileEvidenceStore(settings.data_dir),
                    )
                    owns_controller = True
                services = await controller.discover_services(settings.aiven_project)
            except AivenApiError as exc:
                service_discovery_issue = str(exc)
            finally:
                if controller is not None and owns_controller:
                    await controller.close()

    service_checks = _service_checks(
        settings,
        profile=profile,
        live_aiven=live_aiven,
        discovered_services=services,
    )
    issues = [
        *secret_summary.issues,
        *[issue for check in service_checks for issue in check.issues],
    ]
    if service_discovery_issue is not None:
        issues.append(service_discovery_issue)
        service_checks = [
            _mark_not_checked(check, service_discovery_issue) if check.target == "aiven" else check
            for check in service_checks
        ]

    ready = (
        secret_summary.ready
        and not issues
        and _service_checks_ready(
            service_checks,
            live_aiven=live_aiven,
        )
    )
    return CloudReadinessReport(
        profile=profile,
        live_aiven=live_aiven,
        ready=ready,
        secret_summary=secret_summary,
        service_checks=service_checks,
        issues=issues,
        next_steps=_next_steps(profile=profile, ready=ready, live_aiven=live_aiven, issues=issues),
    )


def _service_checks(
    settings: Settings,
    *,
    profile: SecretBundleProfile,
    live_aiven: bool,
    discovered_services: list[AivenServiceRef] | None,
) -> list[CloudReadinessServiceCheck]:
    services_by_name = {
        service.service_name: service
        for service in discovered_services or []
        if service.service_name is not None
    }
    checks: list[CloudReadinessServiceCheck] = []
    if profile in {"aiven-worker", "aiven-mvp"}:
        checks.extend(
            [
                _aiven_service_check(
                    role="postgres",
                    service_name=settings.aiven_postgres_service,
                    expected_service_type="pg",
                    live_aiven=live_aiven,
                    services_by_name=services_by_name,
                ),
                _aiven_service_check(
                    role="kafka",
                    service_name=settings.aiven_kafka_service,
                    expected_service_type="kafka",
                    live_aiven=live_aiven,
                    services_by_name=services_by_name,
                ),
            ]
        )
    if profile in {"aiven-grafana", "aiven-mvp"}:
        checks.append(
            _aiven_service_check(
                role="grafana",
                service_name=settings.aiven_grafana_service,
                expected_service_type="grafana",
                live_aiven=live_aiven,
                services_by_name=services_by_name,
            )
        )
    checks.append(
        CloudReadinessServiceCheck(
            role="neo4j",
            target="local",
            service_name=None,
            expected_service_type=None,
            status="local",
            issues=[],
        )
    )
    return checks


def _aiven_service_check(
    *,
    role: Literal["postgres", "kafka", "grafana"],
    service_name: str | None,
    expected_service_type: str,
    live_aiven: bool,
    services_by_name: dict[str, AivenServiceRef],
) -> CloudReadinessServiceCheck:
    if service_name is None:
        return CloudReadinessServiceCheck(
            role=role,
            target="aiven",
            expected_service_type=expected_service_type,
            status="not_configured",
            issues=[f"AIVEN_{role.upper()}_SERVICE is not configured."],
        )
    if not live_aiven:
        return CloudReadinessServiceCheck(
            role=role,
            target="aiven",
            service_name=service_name,
            expected_service_type=expected_service_type,
            status="configured",
            issues=[],
        )
    discovered = services_by_name.get(service_name)
    if discovered is None:
        return CloudReadinessServiceCheck(
            role=role,
            target="aiven",
            service_name=service_name,
            expected_service_type=expected_service_type,
            status="not_found",
            issues=[f"Aiven {role} service was not found: {service_name}."],
        )
    if discovered.service_type != expected_service_type:
        return CloudReadinessServiceCheck(
            role=role,
            target="aiven",
            service_name=service_name,
            expected_service_type=expected_service_type,
            discovered_service_type=discovered.service_type,
            state=discovered.state,
            status="type_mismatch",
            issues=[
                (
                    f"Aiven {role} service {service_name} has type "
                    f"{discovered.service_type}, expected {expected_service_type}."
                )
            ],
        )
    if (discovered.state or "").casefold() != "running":
        return CloudReadinessServiceCheck(
            role=role,
            target="aiven",
            service_name=service_name,
            expected_service_type=expected_service_type,
            discovered_service_type=discovered.service_type,
            state=discovered.state,
            status="not_running",
            issues=[f"Aiven {role} service {service_name} is not RUNNING."],
        )
    return CloudReadinessServiceCheck(
        role=role,
        target="aiven",
        service_name=service_name,
        expected_service_type=expected_service_type,
        discovered_service_type=discovered.service_type,
        state=discovered.state,
        status="running",
        issues=[],
    )


def _mark_not_checked(
    check: CloudReadinessServiceCheck,
    issue: str,
) -> CloudReadinessServiceCheck:
    if check.status in {"not_configured", "local"}:
        return check
    return check.model_copy(update={"status": "not_checked", "issues": [issue]})


def _service_checks_ready(
    checks: list[CloudReadinessServiceCheck],
    *,
    live_aiven: bool,
) -> bool:
    ready_statuses = {"local", "running"} if live_aiven else {"local", "configured"}
    return all(check.status in ready_statuses for check in checks)


def _next_steps(
    *,
    profile: SecretBundleProfile,
    ready: bool,
    live_aiven: bool,
    issues: list[str],
) -> list[CloudReadinessNextStep]:
    steps: list[CloudReadinessNextStep] = []
    if issues:
        steps.append(
            CloudReadinessNextStep(
                command=(
                    f"uv run platform validate-cloud-secrets --profile {profile} --require-ready"
                ),
                reason="Fix required secret files and non-local endpoint settings first.",
                status="blocked",
            )
        )
    if not live_aiven:
        steps.append(
            CloudReadinessNextStep(
                command=f"uv run platform cloud-readiness --profile {profile} --live-aiven",
                reason="Confirm configured Aiven service names exist and are RUNNING.",
                status="manual",
            )
        )
    worker_profile = profile in {"aiven-worker", "aiven-mvp"}
    grafana_profile = profile in {"aiven-grafana", "aiven-mvp"}
    if worker_profile:
        steps.extend(
            [
                CloudReadinessNextStep(
                    command="uv run platform init-db --apply",
                    reason="Apply PostgreSQL migrations through the direct DATABASE_URL fallback.",
                    status="ready" if ready else "blocked",
                ),
                CloudReadinessNextStep(
                    command="uv run platform init-kafka --apply --backend direct",
                    reason="Ensure Kafka topics through the direct Kafka admin fallback.",
                    status="ready" if ready else "blocked",
                ),
                CloudReadinessNextStep(
                    command="uv run platform run-scheduler --limit 1 --publish-kafka",
                    reason="Publish the first bounded cloud ingest job.",
                    status="ready" if ready else "blocked",
                ),
                CloudReadinessNextStep(
                    command="uv run platform run-ingest-worker --evidence-backend postgres",
                    reason="Process one Kafka ingest job into Aiven PostgreSQL.",
                    status="ready" if ready else "blocked",
                ),
            ]
        )
    if grafana_profile:
        steps.append(
            CloudReadinessNextStep(
                command="uv run platform create-dashboard all --provision-datasource --provision",
                reason="Provision the Aiven Grafana datasource and dashboards.",
                status="ready" if ready else "blocked",
            )
        )
    return steps
