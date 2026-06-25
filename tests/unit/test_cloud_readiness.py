import json
from pathlib import Path

import httpx
from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.infra.aiven_api import AivenApiController
from supply_intel.infra.cloud_readiness import inspect_cloud_readiness
from supply_intel.settings import Settings


def _secret_file(tmp_path: Path, name: str, value: str = "secret-value") -> Path:
    path = tmp_path / name
    path.write_text(value + "\n", encoding="utf-8")
    return path


def _ready_mvp_settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        database_url_file=_secret_file(
            tmp_path,
            "database-url",
            "postgresql://avnadmin:secret-value@pg.example.test:26410/platform",
        ),
        database_ca_cert_path=_secret_file(tmp_path, "database-ca.pem", "ca-cert"),
        kafka_bootstrap_servers="kafka.example.test:26411",
        kafka_security_protocol="SSL",
        kafka_ca_cert_path=_secret_file(tmp_path, "kafka-ca.pem", "kafka-ca"),
        kafka_client_cert_path=_secret_file(tmp_path, "service.cert", "client-cert"),
        kafka_client_key_path=_secret_file(tmp_path, "service.key", "client-key"),
        grafana_url="https://grafana.example.test",
        grafana_token_file=_secret_file(tmp_path, "grafana-token", "grafana-token-value"),
        grafana_postgres_host="pg.example.test",
        grafana_postgres_port=26410,
        grafana_postgres_user="avnadmin",
        grafana_postgres_password_file=_secret_file(
            tmp_path,
            "grafana-postgres-password",
            "grafana-postgres-secret",
        ),
        grafana_postgres_sslmode="verify-full",
        grafana_postgres_tls_ca_cert_path=_secret_file(
            tmp_path,
            "grafana-postgres-ca.pem",
            "grafana-postgres-ca",
        ),
        aiven_project="demo-project",
        aiven_postgres_service="platform-pg",
        aiven_kafka_service="platform-kafka",
        aiven_grafana_service="platform-grafana",
    )


async def test_cloud_readiness_reports_missing_local_configuration(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)

    report = await inspect_cloud_readiness(settings)

    assert report.ready is False
    assert report.secret_summary.ready is False
    assert {check.role: check.status for check in report.service_checks} == {
        "postgres": "not_configured",
        "kafka": "not_configured",
        "grafana": "not_configured",
        "neo4j": "local",
    }
    rendered = report.model_dump_json()
    assert "secret-value" not in rendered
    assert "postgresql://platform:platform" not in rendered


async def test_cloud_readiness_configured_mvp_is_ready_without_live_probe(
    tmp_path: Path,
) -> None:
    settings = _ready_mvp_settings(tmp_path)

    report = await inspect_cloud_readiness(settings)

    assert report.ready is True
    assert report.live_aiven is False
    assert {check.role: check.status for check in report.service_checks} == {
        "postgres": "configured",
        "kafka": "configured",
        "grafana": "configured",
        "neo4j": "local",
    }
    assert any(
        step.command == "uv run platform init-db --apply" and step.status == "ready"
        for step in report.next_steps
    )
    assert "grafana-token-value" not in report.model_dump_json()


async def test_cloud_readiness_live_aiven_probe_marks_running_services_ready(
    tmp_path: Path,
) -> None:
    settings = _ready_mvp_settings(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/project/demo-project/service"
        return httpx.Response(
            200,
            json={
                "services": [
                    {
                        "service_name": "platform-pg",
                        "service_type": "pg",
                        "state": "RUNNING",
                    },
                    {
                        "service_name": "platform-kafka",
                        "service_type": "kafka",
                        "state": "RUNNING",
                    },
                    {
                        "service_name": "platform-grafana",
                        "service_type": "grafana",
                        "state": "RUNNING",
                    },
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        controller = AivenApiController(
            api_token="test-token",
            default_project="demo-project",
            client=client,
        )
        report = await inspect_cloud_readiness(
            settings,
            live_aiven=True,
            controller=controller,
        )

    assert report.ready is True
    assert {check.role: check.status for check in report.service_checks} == {
        "postgres": "running",
        "kafka": "running",
        "grafana": "running",
        "neo4j": "local",
    }


async def test_cloud_readiness_live_aiven_probe_detects_missing_service(
    tmp_path: Path,
) -> None:
    settings = _ready_mvp_settings(tmp_path)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "services": [
                        {
                            "service_name": "platform-pg",
                            "service_type": "pg",
                            "state": "RUNNING",
                        }
                    ]
                },
            )
        )
    ) as client:
        controller = AivenApiController(
            api_token="test-token",
            default_project="demo-project",
            client=client,
        )
        report = await inspect_cloud_readiness(
            settings,
            live_aiven=True,
            controller=controller,
        )

    assert report.ready is False
    assert {check.role: check.status for check in report.service_checks}["kafka"] == "not_found"
    assert any("platform-kafka" in issue for issue in report.issues)


def test_cloud_readiness_cli_scopes_checks_to_selected_profile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["cloud-readiness", "--profile", "aiven-grafana"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["profile"] == "aiven-grafana"
    assert [check["role"] for check in payload["service_checks"]] == ["grafana", "neo4j"]
