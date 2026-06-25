from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Literal

import httpx
import yaml

from supply_intel.models.infra import (
    GrafanaDashboardProvisionResult,
    GrafanaDatasourceProvisionResult,
)
from supply_intel.settings import Settings


class GrafanaApiError(RuntimeError):
    """Raised when Grafana dashboard provisioning cannot complete safely."""


def generate_dashboard(definition_path: Path, output_path: Path) -> Path:
    definition = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    panels = []
    for index, panel in enumerate(definition.get("panels", []), start=1):
        panels.append(
            {
                "id": index,
                "title": panel["title"],
                "type": panel.get("type", "table"),
                "targets": [{"refId": "A", "rawSql": panel["query"], "format": "table"}],
                "gridPos": {"h": 8, "w": 12, "x": 0 if index % 2 else 12, "y": (index - 1) * 4},
            }
        )
    dashboard = {
        "uid": definition["uid"],
        "title": definition["title"],
        "schemaVersion": 39,
        "version": 1,
        "refresh": "5m",
        "panels": panels,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"dashboard": dashboard, "overwrite": True}, indent=2),
        encoding="utf-8",
    )
    return output_path


def load_dashboard_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("dashboard"), dict):
        raise GrafanaApiError(f"Dashboard payload must contain a dashboard object: {path}")
    return payload


def build_postgres_datasource_payload(
    settings: Settings,
    *,
    name: str = "Platform PostgreSQL",
    uid: str = "platform-postgres",
) -> dict[str, Any]:
    if not settings.grafana_postgres_password:
        raise GrafanaApiError("GRAFANA_POSTGRES_PASSWORD is required for datasource provisioning.")
    secure_json_data = {"password": settings.grafana_postgres_password}
    json_data: dict[str, object] = {
        "database": settings.grafana_postgres_db,
        "sslmode": settings.grafana_postgres_sslmode,
        "postgresVersion": 1700,
        "timescaledb": False,
    }
    if settings.grafana_postgres_tls_ca_cert_path is not None:
        secure_json_data["tlsCACert"] = settings.grafana_postgres_tls_ca_cert_path.read_text(
            encoding="utf-8"
        )
        json_data["tlsAuthWithCACert"] = True
    return {
        "name": name,
        "uid": uid,
        "type": "postgres",
        "access": "proxy",
        "url": f"{settings.grafana_postgres_host}:{settings.grafana_postgres_port}",
        "user": settings.grafana_postgres_user,
        "secureJsonData": secure_json_data,
        "jsonData": json_data,
    }


class GrafanaClient:
    def __init__(
        self,
        *,
        url: str,
        token: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not token:
            raise GrafanaApiError("GRAFANA_TOKEN is required for dashboard provisioning.")
        self.url = url.rstrip("/")
        self.token = token
        self._client = client
        self._owns_client = client is None

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> GrafanaClient:
        if settings.grafana_token is None:
            raise GrafanaApiError("GRAFANA_TOKEN is required for dashboard provisioning.")
        return cls(url=settings.grafana_url, token=settings.grafana_token, client=client)

    async def __aenter__(self) -> GrafanaClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    async def upsert_dashboard(
        self,
        payload: dict[str, Any],
        *,
        folder_uid: str | None = None,
        message: str | None = None,
        path: Path | None = None,
    ) -> GrafanaDashboardProvisionResult:
        if not isinstance(payload.get("dashboard"), dict):
            raise GrafanaApiError("Dashboard payload must contain a dashboard object.")
        request_payload = copy.deepcopy(payload)
        if folder_uid:
            request_payload["folderUid"] = folder_uid
        if message:
            request_payload["message"] = message

        client = self._client or httpx.AsyncClient(timeout=30.0)
        if self._client is None:
            self._client = client
        response = await client.post(
            f"{self.url}/api/dashboards/db",
            json=request_payload,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GrafanaApiError(
                f"Grafana dashboard provisioning failed with status {exc.response.status_code}"
            ) from exc

        data = response.json()
        if not isinstance(data, dict):
            raise GrafanaApiError("Grafana dashboard provisioning response was not an object.")
        dashboard = request_payload["dashboard"]
        return GrafanaDashboardProvisionResult(
            uid=str(data.get("uid") or dashboard.get("uid") or ""),
            title=str(dashboard["title"]) if dashboard.get("title") is not None else None,
            status=str(data.get("status", "unknown")),
            url=str(data["url"]) if data.get("url") is not None else None,
            version=int(data["version"]) if data.get("version") is not None else None,
            path=str(path) if path is not None else None,
        )

    async def upsert_postgres_datasource(
        self,
        payload: dict[str, Any],
    ) -> GrafanaDatasourceProvisionResult:
        uid = _required_text(payload, "uid")
        name = _required_text(payload, "name")
        client = self._client or httpx.AsyncClient(timeout=30.0)
        if self._client is None:
            self._client = client

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        lookup = await client.get(f"{self.url}/api/datasources/uid/{uid}", headers=headers)
        if lookup.status_code == httpx.codes.NOT_FOUND:
            response = await client.post(
                f"{self.url}/api/datasources",
                json=payload,
                headers=headers,
            )
            status: Literal["created", "updated"] = "created"
        else:
            try:
                lookup.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise GrafanaApiError(
                    f"Grafana datasource lookup failed with status {exc.response.status_code}"
                ) from exc
            response = await client.put(
                f"{self.url}/api/datasources/uid/{uid}",
                json=payload,
                headers=headers,
            )
            status = "updated"
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise GrafanaApiError(
                f"Grafana datasource provisioning failed with status {exc.response.status_code}"
            ) from exc
        datasource = _datasource_response(response.json())
        return GrafanaDatasourceProvisionResult(
            uid=str(datasource.get("uid") or uid),
            name=str(datasource.get("name") or name),
            status=status,
            datasource_id=_int_or_none(datasource.get("id")),
        )


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise GrafanaApiError(f"Grafana datasource payload requires {key}.")
    return value


def _datasource_response(data: object) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise GrafanaApiError("Grafana datasource provisioning response was not an object.")
    datasource = data.get("datasource")
    if isinstance(datasource, dict):
        return datasource
    return data


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except ValueError:
        return None
