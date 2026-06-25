import json
from pathlib import Path

import httpx
import pytest
import yaml

from supply_intel.observability.grafana import (
    GrafanaApiError,
    GrafanaClient,
    build_postgres_datasource_payload,
    generate_dashboard,
    load_dashboard_payload,
)
from supply_intel.settings import Settings

EXPECTED_DASHBOARD_VERSION = 2
EXPECTED_DATASOURCE_ID = 42
REQUIRED_DASHBOARDS = {
    "agent-activity",
    "evidence-coverage",
    "executive-risk-overview",
    "graph-growth",
    "ingestion-throughput",
    "low-confidence-review",
    "mcp-audit-activity",
    "medicine-drug-manufacturing-risk",
    "operational-metrics",
    "risk-cases",
    "source-failures",
    "source-freshness",
}


def test_generate_dashboard_payload_can_be_loaded_for_provisioning(tmp_path: Path) -> None:
    definition = tmp_path / "source-freshness.yaml"
    output = tmp_path / "source-freshness.json"
    definition.write_text(
        "\n".join(
            [
                "uid: source-freshness",
                "title: Source Freshness",
                "panels:",
                "  - title: Source status",
                "    query: SELECT 1",
            ]
        ),
        encoding="utf-8",
    )

    generated = generate_dashboard(definition, output)
    payload = load_dashboard_payload(generated)

    assert payload["overwrite"] is True
    assert payload["dashboard"]["uid"] == "source-freshness"
    assert payload["dashboard"]["title"] == "Source Freshness"


def test_required_dashboard_definitions_are_checked_in() -> None:
    definitions = {path.stem for path in Path("dashboards/definitions").glob("*.yaml")}

    assert definitions >= REQUIRED_DASHBOARDS


def test_local_grafana_provisioning_points_at_generated_dashboards() -> None:
    provider = yaml.safe_load(
        Path("infra/grafana/provisioning/dashboards/platform.yaml").read_text(encoding="utf-8")
    )
    datasource = yaml.safe_load(
        Path("infra/grafana/provisioning/datasources/postgres.yaml").read_text(encoding="utf-8")
    )
    provider_config = provider["providers"][0]
    datasource_config = datasource["datasources"][0]

    assert provider_config["options"]["path"] == "/var/lib/grafana/dashboards/platform"
    assert provider_config["allowUiUpdates"] is False
    assert datasource_config["url"] == "${GRAFANA_POSTGRES_HOST}:${GRAFANA_POSTGRES_PORT}"
    assert datasource_config["user"] == "${GRAFANA_POSTGRES_USER}"
    assert datasource_config["secureJsonData"]["password"] == "${GRAFANA_POSTGRES_PASSWORD}"
    assert datasource_config["jsonData"]["database"] == "${GRAFANA_POSTGRES_DB}"
    assert datasource_config["jsonData"]["sslmode"] == "${GRAFANA_POSTGRES_SSLMODE}"


def test_compose_mounts_grafana_provisioning_and_generated_dashboards() -> None:
    compose = yaml.safe_load(Path("infra/docker-compose.yml").read_text(encoding="utf-8"))
    grafana = compose["services"]["grafana"]

    assert "./grafana/provisioning:/etc/grafana/provisioning:ro" in grafana["volumes"]
    assert "../dashboards/generated:/var/lib/grafana/dashboards/platform:ro" in grafana["volumes"]
    assert grafana["environment"]["GRAFANA_POSTGRES_HOST"] == "postgres"
    assert grafana["environment"]["GRAFANA_POSTGRES_SSLMODE"] == "disable"


def test_checked_in_dashboard_definitions_generate_valid_payloads(tmp_path: Path) -> None:
    for definition in sorted(Path("dashboards/definitions").glob("*.yaml")):
        generated = generate_dashboard(definition, tmp_path / f"{definition.stem}.json")
        payload = load_dashboard_payload(generated)
        dashboard = payload["dashboard"]

        assert payload["overwrite"] is True
        assert dashboard["uid"] == definition.stem
        assert dashboard["title"]
        assert dashboard["panels"]
        assert all(panel["targets"][0]["rawSql"].strip() for panel in dashboard["panels"])


def test_source_freshness_dashboard_surfaces_postgres_source_coverage() -> None:
    definition = yaml.safe_load(
        Path("dashboards/definitions/source-freshness.yaml").read_text(encoding="utf-8")
    )
    queries = {panel["title"]: panel["query"] for panel in definition["panels"]}

    coverage_query = queries["Source evidence coverage"]

    assert "data_sources ds" in coverage_query
    assert "raw_documents rd" in coverage_query
    assert "document_chunks dc" in coverage_query
    assert "raw_documents" in coverage_query
    assert "document_chunks" in coverage_query
    assert "latest_fetch_at" in coverage_query


def test_low_confidence_dashboard_surfaces_open_human_review_queue() -> None:
    definition = yaml.safe_load(
        Path("dashboards/definitions/low-confidence-review.yaml").read_text(encoding="utf-8")
    )
    queries = {panel["title"]: panel["query"] for panel in definition["panels"]}

    review_query = queries["Open human-review tasks"]

    assert "human_review_queue" in review_query
    assert "status = 'open'" in review_query
    assert "ORDER BY priority" in review_query


def test_graph_growth_dashboard_surfaces_neo4j_metric_snapshots() -> None:
    definition = yaml.safe_load(
        Path("dashboards/definitions/graph-growth.yaml").read_text(encoding="utf-8")
    )
    queries = {panel["title"]: panel["query"] for panel in definition["panels"]}

    totals_query = queries["Neo4j graph totals"]

    assert "ops_metrics" in totals_query
    assert "service = 'neo4j'" in totals_query
    assert "graph_nodes_total" in totals_query
    assert "graph_relationships_total" in totals_query


def test_build_postgres_datasource_payload_uses_grafana_postgres_settings(
    tmp_path: Path,
) -> None:
    ca_cert = "-----BEGIN CERTIFICATE-----\nexample\n-----END CERTIFICATE-----\n"
    ca_path = tmp_path / "grafana-ca.pem"
    ca_path.write_text(ca_cert, encoding="utf-8")
    settings = Settings(
        grafana_postgres_host="pg.example.test",
        grafana_postgres_port=26410,
        grafana_postgres_user="avnadmin",
        grafana_postgres_password="secret-password",
        grafana_postgres_db="platform",
        grafana_postgres_sslmode="verify-full",
        grafana_postgres_tls_ca_cert_path=ca_path,
    )

    payload = build_postgres_datasource_payload(
        settings,
        name="Aiven PostgreSQL",
        uid="aiven-platform-postgres",
    )

    assert payload["name"] == "Aiven PostgreSQL"
    assert payload["uid"] == "aiven-platform-postgres"
    assert payload["url"] == "pg.example.test:26410"
    assert payload["user"] == "avnadmin"
    assert payload["secureJsonData"]["password"] == "secret-password"
    assert payload["secureJsonData"]["tlsCACert"] == ca_cert
    assert payload["jsonData"]["database"] == "platform"
    assert payload["jsonData"]["sslmode"] == "verify-full"
    assert payload["jsonData"]["tlsAuthWithCACert"] is True


def test_build_postgres_datasource_payload_requires_password() -> None:
    settings = Settings(grafana_postgres_password=None)

    with pytest.raises(GrafanaApiError, match="GRAFANA_POSTGRES_PASSWORD"):
        build_postgres_datasource_payload(settings)


async def test_grafana_client_creates_postgres_datasource() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer grafana-token"
        if request.method == "GET":
            assert request.url.path == "/api/datasources/uid/platform-postgres"
            return httpx.Response(404, json={"message": "not found"})
        assert request.method == "POST"
        assert request.url.path == "/api/datasources"
        payload = json.loads(request.content)
        assert payload["uid"] == "platform-postgres"
        assert payload["secureJsonData"]["password"] == "secret-password"
        return httpx.Response(
            200,
            json={
                "message": "Datasource added",
                "datasource": {
                    "id": EXPECTED_DATASOURCE_ID,
                    "uid": "platform-postgres",
                    "name": "Platform PostgreSQL",
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GrafanaClient(
            url="https://grafana.example.test/",
            token="grafana-token",
            client=http_client,
        )
        result = await client.upsert_postgres_datasource(
            {
                "name": "Platform PostgreSQL",
                "uid": "platform-postgres",
                "type": "postgres",
                "secureJsonData": {"password": "secret-password"},
            }
        )

    assert [request.method for request in requests] == ["GET", "POST"]
    assert result.uid == "platform-postgres"
    assert result.name == "Platform PostgreSQL"
    assert result.status == "created"
    assert result.datasource_id == EXPECTED_DATASOURCE_ID
    assert "secret" not in result.model_dump_json()


async def test_grafana_client_updates_existing_postgres_datasource() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": EXPECTED_DATASOURCE_ID,
                    "uid": "platform-postgres",
                    "name": "Platform PostgreSQL",
                },
            )
        assert request.method == "PUT"
        assert request.url.path == "/api/datasources/uid/platform-postgres"
        return httpx.Response(
            200,
            json={
                "message": "Datasource updated",
                "datasource": {
                    "id": EXPECTED_DATASOURCE_ID,
                    "uid": "platform-postgres",
                    "name": "Platform PostgreSQL",
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GrafanaClient(
            url="https://grafana.example.test/",
            token="grafana-token",
            client=http_client,
        )
        result = await client.upsert_postgres_datasource(
            {"name": "Platform PostgreSQL", "uid": "platform-postgres", "type": "postgres"}
        )

    assert [request.method for request in requests] == ["GET", "PUT"]
    assert result.status == "updated"
    assert result.datasource_id == EXPECTED_DATASOURCE_ID


async def test_grafana_client_upserts_dashboard_with_bearer_token_and_folder(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer grafana-token"
        assert request.url.path == "/api/dashboards/db"
        payload = json.loads(request.content)
        assert payload["folderUid"] == "platform-folder"
        assert payload["message"] == "provision from tests"
        assert payload["dashboard"]["uid"] == "graph-growth"
        return httpx.Response(
            200,
            json={
                "uid": "graph-growth",
                "status": "success",
                "url": "/d/graph-growth/graph-growth",
                "version": 2,
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = GrafanaClient(
            url="https://grafana.example.test/",
            token="grafana-token",
            client=http_client,
        )
        result = await client.upsert_dashboard(
            {
                "dashboard": {
                    "uid": "graph-growth",
                    "title": "Graph Growth",
                    "schemaVersion": 39,
                },
                "overwrite": True,
            },
            folder_uid="platform-folder",
            message="provision from tests",
            path=tmp_path / "graph-growth.json",
        )

    assert len(requests) == 1
    assert result.uid == "graph-growth"
    assert result.title == "Graph Growth"
    assert result.status == "success"
    assert result.url == "/d/graph-growth/graph-growth"
    assert result.version == EXPECTED_DASHBOARD_VERSION
    assert result.path == str(tmp_path / "graph-growth.json")


def test_grafana_client_from_settings_requires_token() -> None:
    settings = Settings(grafana_token=None)

    with pytest.raises(GrafanaApiError, match="GRAFANA_TOKEN"):
        GrafanaClient.from_settings(settings)
