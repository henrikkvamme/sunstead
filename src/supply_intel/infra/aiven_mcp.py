from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

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

MCPToolInvoker = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class AivenMCPController(Protocol):
    async def discover_projects(self) -> list[AivenProject]: ...

    async def discover_services(self, project: str | None = None) -> list[AivenServiceRef]: ...

    async def ensure_postgres_service(self, spec: PostgresServiceSpec) -> AivenServiceRef: ...

    async def ensure_kafka_service(self, spec: KafkaServiceSpec) -> AivenServiceRef: ...

    async def ensure_grafana_service(self, spec: GrafanaServiceSpec) -> AivenServiceRef: ...

    async def ensure_kafka_topic(self, spec: KafkaTopicSpec) -> None: ...

    async def pg_read(self, query: str, *, database: str | None = None) -> QueryResult: ...

    async def pg_write(self, statement: str, *, database: str | None = None) -> QueryResult: ...

    async def kafka_produce(self, topic: str, records: list[KafkaRecord]) -> ProduceResult: ...

    async def kafka_read(
        self,
        topic: str,
        partition_offsets: dict[int, int],
    ) -> ConsumeResult: ...

    async def get_service_metrics(
        self,
        service_name: str,
        period: str = "day",
    ) -> MetricsSnapshot: ...

    async def get_service_logs(
        self,
        service_name: str,
        since: str | None = None,
    ) -> LogBatch: ...

    async def audit_action(self, action: MCPAuditAction) -> None: ...


class MCPAuditSink(Protocol):
    def write_mcp_audit_log(self, record: MCPAuditLog) -> bool: ...


class NoopAivenMCPController:
    def __init__(self, audit_sink: MCPAuditSink | None = None) -> None:
        self.audit_sink = audit_sink
        self.audit_log: list[MCPAuditLog] = []

    async def discover_projects(self) -> list[AivenProject]:
        return []

    async def discover_services(self, project: str | None = None) -> list[AivenServiceRef]:
        del project
        return []

    async def ensure_postgres_service(self, spec: PostgresServiceSpec) -> AivenServiceRef:
        return AivenServiceRef(
            project=spec.project,
            service_name=spec.service_name,
            service_type=spec.service_type,
            state="planned",
        )

    async def ensure_kafka_service(self, spec: KafkaServiceSpec) -> AivenServiceRef:
        return AivenServiceRef(
            project=spec.project,
            service_name=spec.service_name,
            service_type=spec.service_type,
            state="planned",
        )

    async def ensure_grafana_service(self, spec: GrafanaServiceSpec) -> AivenServiceRef:
        return AivenServiceRef(
            project=spec.project,
            service_name=spec.service_name,
            service_type=spec.service_type,
            state="planned",
        )

    async def ensure_kafka_topic(self, spec: KafkaTopicSpec) -> None:
        del spec

    async def pg_read(self, query: str, *, database: str | None = None) -> QueryResult:
        del query, database
        return QueryResult(columns=[], rows=[], row_count=0)

    async def pg_write(self, statement: str, *, database: str | None = None) -> QueryResult:
        del statement, database
        return QueryResult(columns=[], rows=[], row_count=0)

    async def kafka_produce(self, topic: str, records: list[KafkaRecord]) -> ProduceResult:
        return ProduceResult(topic=topic, produced=len(records))

    async def kafka_read(
        self,
        topic: str,
        partition_offsets: dict[int, int],
    ) -> ConsumeResult:
        del partition_offsets
        return ConsumeResult(topic=topic, records=[])

    async def get_service_metrics(
        self,
        service_name: str,
        period: str = "day",
    ) -> MetricsSnapshot:
        return MetricsSnapshot(service_name=service_name, period=period)

    async def get_service_logs(
        self,
        service_name: str,
        since: str | None = None,
    ) -> LogBatch:
        del since
        return LogBatch(service_name=service_name)

    async def audit_action(self, action: MCPAuditAction) -> None:
        record = mcp_audit_log_from_action(action)
        self.audit_log.append(record)
        if self.audit_sink is not None:
            self.audit_sink.write_mcp_audit_log(record)


class InjectedAivenMCPController:
    """Aiven MCP adapter for hosts that inject callable MCP tools.

    Application runtime stays independent of MCP. This adapter is only used when
    a host process supplies an invoker for Aiven MCP tools; direct database,
    Kafka, and HTTP API fallbacks remain separate.
    """

    def __init__(
        self,
        *,
        invoke_tool: MCPToolInvoker,
        project: str | None = None,
        postgres_service: str | None = None,
        kafka_service: str | None = None,
        grafana_service: str | None = None,
        audit_sink: MCPAuditSink | None = None,
    ) -> None:
        self.invoke_tool = invoke_tool
        self.project = project
        self.postgres_service = postgres_service
        self.kafka_service = kafka_service
        self.grafana_service = grafana_service
        self.audit_sink = audit_sink
        self.audit_log: list[MCPAuditLog] = []

    async def discover_projects(self) -> list[AivenProject]:
        started_at = datetime.now(UTC)
        request: dict[str, object] = {}
        try:
            response = await self.invoke_tool("aiven_project_list", request)
            projects = [
                AivenProject(
                    project_name=str(row["project_name"]),
                    default_cloud=(
                        str(row["default_cloud"]) if row.get("default_cloud") is not None else None
                    ),
                )
                for row in _rows(response, "projects")
                if row.get("project_name") is not None
            ]
        except Exception as exc:
            await self._audit(
                action="discover_projects",
                safety_level="safe_read",
                request=request,
                status="failed",
                started_at=started_at,
                error=str(exc),
            )
            raise
        await self._audit(
            action="discover_projects",
            safety_level="safe_read",
            request=request,
            response_summary={"project_count": len(projects)},
            status="succeeded",
            started_at=started_at,
        )
        return projects

    async def discover_services(self, project: str | None = None) -> list[AivenServiceRef]:
        started_at = datetime.now(UTC)
        selected_project = self._project(project)
        request: dict[str, object] = {"project": selected_project}
        try:
            response = await self.invoke_tool("aiven_service_list", request)
            services = [
                _service_ref(selected_project, row)
                for row in _rows(response, "services")
                if row.get("service_name") is not None
            ]
        except Exception as exc:
            await self._audit(
                action="discover_services",
                safety_level="safe_read",
                request=request,
                project=selected_project,
                status="failed",
                started_at=started_at,
                error=str(exc),
            )
            raise
        await self._audit(
            action="discover_services",
            safety_level="safe_read",
            request=request,
            project=selected_project,
            response_summary={"service_count": len(services)},
            status="succeeded",
            started_at=started_at,
        )
        return services

    async def ensure_postgres_service(self, spec: PostgresServiceSpec) -> AivenServiceRef:
        return await self._get_existing_service(
            spec.project,
            spec.service_name,
            action="ensure_postgres_service",
        )

    async def ensure_kafka_service(self, spec: KafkaServiceSpec) -> AivenServiceRef:
        return await self._get_existing_service(
            spec.project,
            spec.service_name,
            action="ensure_kafka_service",
        )

    async def ensure_grafana_service(self, spec: GrafanaServiceSpec) -> AivenServiceRef:
        return await self._get_existing_service(
            spec.project,
            spec.service_name,
            action="ensure_grafana_service",
        )

    async def ensure_kafka_topic(self, spec: KafkaTopicSpec) -> None:
        started_at = datetime.now(UTC)
        selected_project = self._project()
        request: dict[str, object] = {
            "project": selected_project,
            "service_name": self._kafka_service(),
            "topic_name": spec.topic_name,
            "partitions": spec.partitions,
            "replication": spec.replication,
            "cleanup_policy": spec.cleanup_policy,
            "retention_hours": spec.retention_hours,
            "config": spec.config,
        }
        try:
            await self.invoke_tool("aiven_kafka_topic_create", request)
        except Exception as exc:
            await self._audit(
                action="ensure_kafka_topic",
                safety_level="safe_write_dev",
                request=request,
                project=selected_project,
                service_name=self._kafka_service(),
                status="failed",
                started_at=started_at,
                error=str(exc),
            )
            raise
        await self._audit(
            action="ensure_kafka_topic",
            safety_level="safe_write_dev",
            request=request,
            project=selected_project,
            service_name=self._kafka_service(),
            response_summary={"topic_name": spec.topic_name},
            status="succeeded",
            started_at=started_at,
        )

    async def pg_read(self, query: str, *, database: str | None = None) -> QueryResult:
        return await self._pg_query(
            tool_name="aiven_pg_read",
            action="pg_read",
            query_key="query",
            sql=query,
            database=database,
            safety_level="safe_read",
        )

    async def pg_write(self, statement: str, *, database: str | None = None) -> QueryResult:
        return await self._pg_query(
            tool_name="aiven_pg_write",
            action="pg_write",
            query_key="query",
            sql=statement,
            database=database,
            safety_level="safe_write_dev",
        )

    async def kafka_produce(self, topic: str, records: list[KafkaRecord]) -> ProduceResult:
        started_at = datetime.now(UTC)
        request: dict[str, object] = {
            "project": self._project(),
            "service_name": self._kafka_service(),
            "topic_name": topic,
            "format": "json",
            "records": [_kafka_record_payload(record) for record in records],
        }
        try:
            response = await self.invoke_tool("aiven_kafka_topic_message_produce", request)
            offsets = response.get("offsets", [])
            produced = len(offsets) if isinstance(offsets, list) else len(records)
        except Exception as exc:
            await self._audit(
                action="kafka_produce",
                safety_level="safe_write_dev",
                request=request,
                project=self._project(),
                service_name=self._kafka_service(),
                status="failed",
                started_at=started_at,
                error=str(exc),
            )
            raise
        await self._audit(
            action="kafka_produce",
            safety_level="safe_write_dev",
            request=request,
            project=self._project(),
            service_name=self._kafka_service(),
            response_summary={"topic": topic, "produced": produced},
            status="succeeded",
            started_at=started_at,
        )
        return ProduceResult(topic=topic, produced=produced)

    async def kafka_read(
        self,
        topic: str,
        partition_offsets: dict[int, int],
    ) -> ConsumeResult:
        started_at = datetime.now(UTC)
        request: dict[str, object] = {
            "project": self._project(),
            "service_name": self._kafka_service(),
            "topic_name": topic,
            "format": "json",
            "partitions": {
                str(partition): {"offset": offset}
                for partition, offset in partition_offsets.items()
            },
        }
        try:
            response = await self.invoke_tool("aiven_kafka_topic_message_list", request)
            records = [_kafka_record_from_message(row) for row in _rows(response, "messages")]
        except Exception as exc:
            await self._audit(
                action="kafka_read",
                safety_level="safe_read",
                request=request,
                project=self._project(),
                service_name=self._kafka_service(),
                status="failed",
                started_at=started_at,
                error=str(exc),
            )
            raise
        await self._audit(
            action="kafka_read",
            safety_level="safe_read",
            request=request,
            project=self._project(),
            service_name=self._kafka_service(),
            response_summary={"topic": topic, "record_count": len(records)},
            status="succeeded",
            started_at=started_at,
        )
        return ConsumeResult(topic=topic, records=records)

    async def get_service_metrics(
        self,
        service_name: str,
        period: str = "day",
    ) -> MetricsSnapshot:
        started_at = datetime.now(UTC)
        request: dict[str, object] = {
            "project": self._project(),
            "service_name": service_name,
            "period": period,
        }
        try:
            response = await self.invoke_tool("aiven_service_metrics_fetch", request)
        except Exception as exc:
            await self._audit(
                action="get_service_metrics",
                safety_level="safe_read",
                request=request,
                project=self._project(),
                service_name=service_name,
                status="failed",
                started_at=started_at,
                error=str(exc),
            )
            raise
        await self._audit(
            action="get_service_metrics",
            safety_level="safe_read",
            request=request,
            project=self._project(),
            service_name=service_name,
            response_summary={"period": period},
            status="succeeded",
            started_at=started_at,
        )
        return MetricsSnapshot(service_name=service_name, period=period, metrics=response)

    async def get_service_logs(
        self,
        service_name: str,
        since: str | None = None,
    ) -> LogBatch:
        started_at = datetime.now(UTC)
        request: dict[str, object] = {
            "project": self._project(),
            "service_name": service_name,
            "since": since,
        }
        try:
            response = await self.invoke_tool("aiven_project_get_service_logs", request)
            entries = [
                {
                    "timestamp": row.get("time") or row.get("timestamp"),
                    "level": row.get("severity") or row.get("level"),
                    "message": str(row.get("msg") or row.get("message") or ""),
                    "metadata": {key: value for key, value in row.items() if key not in {"msg"}},
                }
                for row in _rows(response, "logs")
            ]
        except Exception as exc:
            await self._audit(
                action="get_service_logs",
                safety_level="safe_read",
                request=request,
                project=self._project(),
                service_name=service_name,
                status="failed",
                started_at=started_at,
                error=str(exc),
            )
            raise
        await self._audit(
            action="get_service_logs",
            safety_level="safe_read",
            request=request,
            project=self._project(),
            service_name=service_name,
            response_summary={"line_count": len(entries)},
            status="succeeded",
            started_at=started_at,
        )
        return LogBatch(service_name=service_name, entries=entries)

    async def audit_action(self, action: MCPAuditAction) -> None:
        record = mcp_audit_log_from_action(action)
        self.audit_log.append(record)
        if self.audit_sink is not None:
            self.audit_sink.write_mcp_audit_log(record)

    async def _get_existing_service(
        self,
        project: str,
        service_name: str,
        *,
        action: str,
    ) -> AivenServiceRef:
        started_at = datetime.now(UTC)
        request: dict[str, object] = {"project": project, "service_name": service_name}
        try:
            response = await self.invoke_tool("aiven_service_get", request)
            service = response.get("service", response)
            if not isinstance(service, dict):
                raise ValueError("aiven_service_get response did not include a service object")
            ref = _service_ref(project, service)
        except Exception as exc:
            await self._audit(
                action=action,
                safety_level="safe_read",
                request=request,
                project=project,
                service_name=service_name,
                status="failed",
                started_at=started_at,
                error=str(exc),
            )
            raise
        await self._audit(
            action=action,
            safety_level="safe_read",
            request=request,
            project=project,
            service_name=service_name,
            response_summary={"service_type": ref.service_type, "state": ref.state},
            status="succeeded",
            started_at=started_at,
        )
        return ref

    async def _pg_query(
        self,
        *,
        tool_name: str,
        action: str,
        query_key: str,
        sql: str,
        database: str | None,
        safety_level: Literal["safe_read", "safe_write_dev"],
    ) -> QueryResult:
        started_at = datetime.now(UTC)
        request: dict[str, object] = {
            "project": self._project(),
            "service_name": self._postgres_service(),
            query_key: sql,
            "reasoning": f"{action} through injected Aiven MCP controller",
        }
        if database is not None:
            request["database"] = database
        try:
            response = await self.invoke_tool(tool_name, request)
            result = _query_result(response)
        except Exception as exc:
            await self._audit(
                action=action,
                safety_level=safety_level,
                request=request,
                project=self._project(),
                service_name=self._postgres_service(),
                status="failed",
                started_at=started_at,
                error=str(exc),
            )
            raise
        await self._audit(
            action=action,
            safety_level=safety_level,
            request=request,
            project=self._project(),
            service_name=self._postgres_service(),
            response_summary={"row_count": result.row_count},
            status="succeeded",
            started_at=started_at,
        )
        return result

    async def _audit(
        self,
        *,
        action: str,
        safety_level: Literal[
            "safe_read",
            "safe_write_dev",
            "migration_write",
            "production_change",
            "credential_access",
        ],
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
                controller="aiven_mcp",
                action=action,
                safety_level=safety_level,
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

    def _project(self, project: str | None = None) -> str:
        selected = project or self.project
        if selected is None:
            raise ValueError("Aiven project is required for MCP operation")
        return selected

    def _postgres_service(self) -> str:
        if self.postgres_service is None:
            raise ValueError("Aiven PostgreSQL service is required for MCP operation")
        return self.postgres_service

    def _kafka_service(self) -> str:
        if self.kafka_service is None:
            raise ValueError("Aiven Kafka service is required for MCP operation")
        return self.kafka_service


def _rows(response: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = response.get(key)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _service_ref(project: str, payload: dict[str, Any]) -> AivenServiceRef:
    return AivenServiceRef(
        project=project,
        service_name=str(payload["service_name"]),
        service_type=str(payload.get("service_type", "unknown")),
        state=str(payload["state"]) if payload.get("state") is not None else None,
    )


def _query_result(response: dict[str, Any]) -> QueryResult:
    rows = _rows(response, "rows")
    meta = response.get("meta", {})
    columns: list[str] = []
    if isinstance(meta, dict):
        fields = meta.get("fields", [])
        columns = [str(field) for field in fields] if isinstance(fields, list) else []
    if not columns and rows:
        columns = list(rows[0])
    return QueryResult(columns=columns, rows=rows, row_count=len(rows))


def _kafka_record_payload(record: KafkaRecord) -> dict[str, object]:
    payload: dict[str, object] = {"value": record.value}
    if record.key is not None:
        payload["key"] = {"key": record.key}
    return payload


def _kafka_record_from_message(message: dict[str, Any]) -> KafkaRecord:
    key = message.get("key")
    value = message.get("value", {})
    return KafkaRecord(
        key=_string_key(key),
        value=value if isinstance(value, dict) else {"value": value},
        headers={},
    )


def _string_key(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
