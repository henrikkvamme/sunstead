from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

import httpx

from supply_intel.infra.aiven_mcp import MCPAuditSink
from supply_intel.models.infra import (
    AivenProject,
    AivenServiceRef,
    ConsumeResult,
    GrafanaServiceSpec,
    KafkaRecord,
    KafkaServiceSpec,
    KafkaTopicSpec,
    LogBatch,
    MCPAuditAction,
    MCPAuditLog,
    MetricsSnapshot,
    PostgresServiceSpec,
    ProduceResult,
    QueryResult,
    mcp_audit_log_from_action,
)
from supply_intel.settings import Settings


class AivenApiError(RuntimeError):
    """Raised when a direct Aiven API fallback cannot complete safely."""


class AivenApiUnsupportedOperation(AivenApiError):
    """Raised for Aiven capabilities delegated to safer direct clients or approval flows."""


class AivenApiController:
    """Direct Aiven REST API fallback for safe project and service discovery."""

    def __init__(
        self,
        *,
        api_token: str,
        base_url: str = "https://api.aiven.io/v1",
        auth_scheme: str = "Bearer",
        default_project: str | None = None,
        audit_sink: MCPAuditSink | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_token:
            raise AivenApiError("Aiven API token is required for direct API fallback.")
        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self.auth_scheme = auth_scheme
        self.default_project = default_project
        self.audit_sink = audit_sink
        self.audit_log: list[MCPAuditLog] = []
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> AivenApiController:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        audit_sink: MCPAuditSink | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> AivenApiController:
        if settings.aiven_api_token is None:
            raise AivenApiError("AIVEN_API_TOKEN is required for Aiven API fallback.")
        return cls(
            api_token=settings.aiven_api_token,
            base_url=settings.aiven_api_base_url,
            auth_scheme=settings.aiven_api_auth_scheme,
            default_project=settings.aiven_project,
            audit_sink=audit_sink,
            client=client,
        )

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    async def discover_projects(self) -> list[AivenProject]:
        started_at = datetime.now(UTC)
        try:
            data = await self._get("/project")
            projects = data.get("projects", [])
            if not isinstance(projects, list):
                raise AivenApiError("Aiven projects response did not include a projects list.")
            result = [
                AivenProject(
                    project_name=str(project["project_name"]),
                    default_cloud=(
                        str(project["default_cloud"])
                        if project.get("default_cloud") is not None
                        else None
                    ),
                )
                for project in projects
                if isinstance(project, dict) and project.get("project_name")
            ]
        except Exception as exc:
            await self._audit_safe_read(
                action="discover_projects",
                request={},
                status="failed",
                started_at=started_at,
                error=str(exc),
            )
            raise
        await self._audit_safe_read(
            action="discover_projects",
            request={},
            response_summary={"project_count": len(result)},
            status="succeeded",
            started_at=started_at,
        )
        return result

    async def discover_services(self, project: str | None = None) -> list[AivenServiceRef]:
        started_at = datetime.now(UTC)
        selected_project = project or self.default_project
        request: dict[str, object] = {"project": selected_project}
        try:
            if selected_project is None:
                raise AivenApiError("Aiven project is required to list services.")
            data = await self._get(f"/project/{selected_project}/service")
            services = data.get("services", [])
            if not isinstance(services, list):
                raise AivenApiError("Aiven services response did not include a services list.")
            result = [
                _service_ref_from_payload(selected_project, service)
                for service in services
                if isinstance(service, dict) and service.get("service_name")
            ]
        except Exception as exc:
            await self._audit_safe_read(
                action="discover_services",
                request=request,
                project=selected_project,
                status="failed",
                started_at=started_at,
                error=str(exc),
            )
            raise
        await self._audit_safe_read(
            action="discover_services",
            request=request,
            project=selected_project,
            response_summary={"service_count": len(result)},
            status="succeeded",
            started_at=started_at,
        )
        return result

    async def get_service(self, project: str, service_name: str) -> AivenServiceRef:
        started_at = datetime.now(UTC)
        request: dict[str, object] = {"project": project, "service_name": service_name}
        try:
            data = await self._get(f"/project/{project}/service/{service_name}")
            service_payload = data.get("service", data)
            if not isinstance(service_payload, dict):
                raise AivenApiError("Aiven service response was not an object.")
            result = _service_ref_from_payload(project, service_payload)
        except Exception as exc:
            await self._audit_safe_read(
                action="get_service",
                request=request,
                project=project,
                service_name=service_name,
                status="failed",
                started_at=started_at,
                error=str(exc),
            )
            raise
        await self._audit_safe_read(
            action="get_service",
            request=request,
            project=project,
            service_name=service_name,
            response_summary={"service_type": result.service_type, "state": result.state},
            status="succeeded",
            started_at=started_at,
        )
        return result

    async def ensure_postgres_service(self, spec: PostgresServiceSpec) -> AivenServiceRef:
        raise AivenApiUnsupportedOperation(
            "Direct Aiven service creation is approval-gated and not performed by "
            "AivenApiController; use the cloud bootstrap plan, Terraform, or an approved MCP flow."
        )

    async def ensure_kafka_service(self, spec: KafkaServiceSpec) -> AivenServiceRef:
        raise AivenApiUnsupportedOperation(
            "Direct Aiven service creation is approval-gated and not performed by "
            "AivenApiController; use the cloud bootstrap plan, Terraform, or an approved MCP flow."
        )

    async def ensure_grafana_service(self, spec: GrafanaServiceSpec) -> AivenServiceRef:
        raise AivenApiUnsupportedOperation(
            "Direct Aiven service creation is approval-gated and not performed by "
            "AivenApiController; use the cloud bootstrap plan, Terraform, or an approved MCP flow."
        )

    async def ensure_kafka_topic(self, spec: KafkaTopicSpec) -> None:
        raise AivenApiUnsupportedOperation(
            "Use the direct Kafka AdminClient fallback for topic bootstrap: "
            "uv run platform init-kafka --apply --backend direct."
        )

    async def pg_read(self, query: str, *, database: str | None = None) -> QueryResult:
        raise AivenApiUnsupportedOperation(
            "Use a direct read-only PostgreSQL connection for pg_read fallback."
        )

    async def pg_write(self, statement: str, *, database: str | None = None) -> QueryResult:
        raise AivenApiUnsupportedOperation(
            "Use reviewed migrations over DATABASE_URL for pg_write fallback."
        )

    async def kafka_produce(self, topic: str, records: list[KafkaRecord]) -> ProduceResult:
        raise AivenApiUnsupportedOperation(
            "Use the direct Kafka producer client for kafka_produce fallback."
        )

    async def kafka_read(
        self,
        topic: str,
        partition_offsets: dict[int, int],
    ) -> ConsumeResult:
        raise AivenApiUnsupportedOperation(
            "Use the direct Kafka consumer client for kafka_read fallback."
        )

    async def get_service_metrics(
        self,
        service_name: str,
        period: str = "day",
    ) -> MetricsSnapshot:
        raise AivenApiUnsupportedOperation(
            "Use Aiven metrics integrations or Grafana datasource queries for metrics fallback."
        )

    async def get_service_logs(
        self,
        service_name: str,
        since: str | None = None,
    ) -> LogBatch:
        raise AivenApiUnsupportedOperation(
            "Use configured log integrations for service log fallback; logs are untrusted input."
        )

    async def audit_action(self, action: MCPAuditAction) -> None:
        record = mcp_audit_log_from_action(action)
        self.audit_log.append(record)
        if self.audit_sink is not None:
            self.audit_sink.write_mcp_audit_log(record)

    async def _audit_safe_read(
        self,
        *,
        action: str,
        request: dict[str, object],
        status: Literal["succeeded", "failed"],
        started_at: datetime,
        project: str | None = None,
        service_name: str | None = None,
        response_summary: dict[str, object] | None = None,
        error: str | None = None,
    ) -> None:
        await self.audit_action(
            MCPAuditAction(
                controller="aiven_api",
                action=action,
                safety_level="safe_read",
                project=project,
                service_name=service_name,
                request=request,
                response_summary=response_summary,
                status=status,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                error=error,
            )
        )

    async def _get(self, path: str) -> dict[str, Any]:
        client = self._client or httpx.AsyncClient(timeout=30.0)
        if self._client is None:
            self._client = client
        response = await client.get(
            f"{self.base_url}{path}",
            headers={"Authorization": f"{self.auth_scheme} {self.api_token}"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AivenApiError(
                f"Aiven API request failed with status {exc.response.status_code}: {path}"
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise AivenApiError(f"Aiven API response was not an object: {path}")
        return data


def _service_ref_from_payload(project: str, payload: dict[str, Any]) -> AivenServiceRef:
    return AivenServiceRef(
        project=project,
        service_name=str(payload["service_name"]),
        service_type=str(payload.get("service_type", "unknown")),
        state=str(payload["state"]) if payload.get("state") is not None else None,
    )
