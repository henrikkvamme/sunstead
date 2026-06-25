import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.infra.secrets import (
    validate_aiven_grafana_secret_bundle,
    validate_aiven_mvp_secret_bundle,
    validate_aiven_worker_secret_bundle,
)
from supply_intel.settings import Settings

EXPECTED_AIVEN_MVP_SECRET_CHECKS = 8


def write_secret(tmp_path: Path, name: str, value: str) -> Path:
    path = tmp_path / name
    path.write_text(value + "\n", encoding="utf-8")
    return path


def test_settings_loads_credential_values_from_files(tmp_path: Path) -> None:
    settings = Settings(
        database_url="postgresql://local/local",
        database_url_file=write_secret(tmp_path, "database-url", "postgresql://aiven/defaultdb"),
        kafka_sasl_password="inline-password",
        kafka_sasl_password_file=write_secret(tmp_path, "kafka-password", "kafka-secret"),
        grafana_token_file=write_secret(tmp_path, "grafana-token", "grafana-secret"),
        grafana_postgres_password_file=write_secret(
            tmp_path,
            "grafana-pg-password",
            "grafana-pg-secret",
        ),
        llm_api_key_file=write_secret(tmp_path, "llm-key", "llm-secret"),
        embedding_api_key_file=write_secret(tmp_path, "embedding-key", "embedding-secret"),
        openfda_api_key_file=write_secret(tmp_path, "openfda-key", "openfda-secret"),
        eia_api_key_file=write_secret(tmp_path, "eia-key", "eia-secret"),
        un_comtrade_api_key_file=write_secret(tmp_path, "comtrade-key", "comtrade-secret"),
        reliefweb_appname_file=write_secret(tmp_path, "reliefweb-appname", "demo-app"),
        aiven_api_token_file=write_secret(tmp_path, "aiven-token", "aiven-secret"),
        neo4j_password_file=write_secret(tmp_path, "neo4j-password", "neo4j-secret"),
    )

    assert settings.database_url == "postgresql://aiven/defaultdb"
    assert settings.kafka_sasl_password == "kafka-secret"
    assert settings.grafana_token == "grafana-secret"
    assert settings.grafana_postgres_password == "grafana-pg-secret"
    assert settings.llm_api_key == "llm-secret"
    assert settings.embedding_api_key == "embedding-secret"
    assert settings.openfda_api_key == "openfda-secret"
    assert settings.eia_api_key == "eia-secret"
    assert settings.un_comtrade_api_key == "comtrade-secret"
    assert settings.reliefweb_appname == "demo-app"
    assert settings.aiven_api_token == "aiven-secret"
    assert settings.neo4j_password == "neo4j-secret"


def test_settings_rejects_empty_secret_file(tmp_path: Path) -> None:
    empty = tmp_path / "database-url"
    empty.write_text("\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="database_url_file is empty"):
        Settings(database_url_file=empty)


def test_settings_available_secret_loading_leaves_missing_files_for_validation(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing-grafana-token"

    settings = Settings(secret_file_loading="available", grafana_token_file=missing)

    assert settings.grafana_token is None
    assert settings.grafana_token_file == missing


def test_aiven_worker_secret_bundle_validation_accepts_certificate_auth(
    tmp_path: Path,
) -> None:
    ca = write_secret(tmp_path, "project-ca.pem", "ca-cert")
    settings = Settings(
        database_url_file=write_secret(tmp_path, "postgres-url", "postgresql://aiven/defaultdb"),
        database_ca_cert_path=ca,
        kafka_bootstrap_servers="kafka.example.test:9092",
        kafka_security_protocol="SSL",
        kafka_ca_cert_path=ca,
        kafka_client_cert_path=write_secret(tmp_path, "kafka-service.cert", "client-cert"),
        kafka_client_key_path=write_secret(tmp_path, "kafka-service.key", "client-key"),
    )

    summary = validate_aiven_worker_secret_bundle(settings)

    assert summary.ready is True
    assert summary.issues == []
    assert {check.env_var: check.status for check in summary.checks} == {
        "DATABASE_URL_FILE": "ok",
        "DATABASE_CA_CERT_PATH": "ok",
        "KAFKA_CA_CERT_PATH": "ok",
        "KAFKA_CLIENT_CERT_PATH": "ok",
        "KAFKA_CLIENT_KEY_PATH": "ok",
    }


def test_validate_cloud_secrets_cli_reports_paths_without_secret_values(tmp_path: Path) -> None:
    ca = write_secret(tmp_path, "project-ca.pem", "ca-secret-value")
    env = {
        "DATABASE_URL_FILE": str(write_secret(tmp_path, "postgres-url", "postgres-secret-value")),
        "DATABASE_CA_CERT_PATH": str(ca),
        "KAFKA_BOOTSTRAP_SERVERS": "kafka.example.test:9092",
        "KAFKA_SECURITY_PROTOCOL": "SSL",
        "KAFKA_CA_CERT_PATH": str(ca),
        "KAFKA_CLIENT_CERT_PATH": str(
            write_secret(tmp_path, "kafka-service.cert", "client-cert-secret-value")
        ),
        "KAFKA_CLIENT_KEY_PATH": str(
            write_secret(tmp_path, "kafka-service.key", "client-key-secret-value")
        ),
    }

    result = CliRunner().invoke(app, ["validate-cloud-secrets"], env=env)

    assert result.exit_code == 0
    assert "secret-value" not in result.output
    payload = json.loads(result.output)
    assert payload["ready"] is True
    assert {check["status"] for check in payload["checks"]} == {"ok"}


def test_validate_cloud_secrets_cli_can_fail_when_required(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["validate-cloud-secrets", "--require-ready"],
        env={"DATA_DIR": str(tmp_path)},
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ready"] is False
    assert "DATABASE_URL_FILE is not configured" in payload["issues"]


def test_validate_cloud_secrets_cli_reports_configured_missing_secret_file(
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(
        app,
        ["validate-cloud-secrets", "--profile", "aiven-grafana", "--require-ready"],
        env={
            "DATA_DIR": str(tmp_path),
            "GRAFANA_URL": "https://grafana.example.test",
            "GRAFANA_TOKEN_FILE": str(tmp_path / "missing-grafana-token"),
            "GRAFANA_POSTGRES_HOST": "pg.example.test",
            "GRAFANA_POSTGRES_PASSWORD_FILE": str(tmp_path / "missing-postgres-password"),
            "GRAFANA_POSTGRES_SSLMODE": "disable",
        },
    )

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    payload = json.loads(result.output)
    assert payload["ready"] is False
    assert "GRAFANA_TOKEN_FILE is missing" in payload["issues"]
    assert "GRAFANA_POSTGRES_PASSWORD_FILE is missing" in payload["issues"]


def test_aiven_grafana_secret_bundle_validation_accepts_tls_datasource(
    tmp_path: Path,
) -> None:
    settings = Settings(
        grafana_url="https://grafana.example.test",
        grafana_token_file=write_secret(tmp_path, "grafana-token", "grafana-secret"),
        grafana_postgres_host="pg.example.test",
        grafana_postgres_password_file=write_secret(
            tmp_path,
            "grafana-pg-password",
            "grafana-pg-secret",
        ),
        grafana_postgres_sslmode="verify-full",
        grafana_postgres_tls_ca_cert_path=write_secret(tmp_path, "postgres-ca.pem", "ca-cert"),
    )

    summary = validate_aiven_grafana_secret_bundle(settings)

    assert summary.ready is True
    assert summary.profile == "aiven-grafana"
    assert summary.issues == []
    assert {check.env_var: check.status for check in summary.checks} == {
        "GRAFANA_TOKEN_FILE": "ok",
        "GRAFANA_POSTGRES_PASSWORD_FILE": "ok",
        "GRAFANA_POSTGRES_TLS_CA_CERT_PATH": "ok",
    }


def test_aiven_mvp_secret_bundle_combines_worker_and_grafana_checks(tmp_path: Path) -> None:
    ca = write_secret(tmp_path, "project-ca.pem", "ca-cert")
    settings = Settings(
        database_url_file=write_secret(tmp_path, "postgres-url", "postgresql://aiven/defaultdb"),
        database_ca_cert_path=ca,
        kafka_bootstrap_servers="kafka.example.test:9092",
        kafka_security_protocol="SSL",
        kafka_ca_cert_path=ca,
        kafka_client_cert_path=write_secret(tmp_path, "kafka-service.cert", "client-cert"),
        kafka_client_key_path=write_secret(tmp_path, "kafka-service.key", "client-key"),
        grafana_url="https://grafana.example.test",
        grafana_token_file=write_secret(tmp_path, "grafana-token", "grafana-secret"),
        grafana_postgres_host="pg.example.test",
        grafana_postgres_password_file=write_secret(
            tmp_path,
            "grafana-pg-password",
            "grafana-pg-secret",
        ),
        grafana_postgres_sslmode="verify-full",
        grafana_postgres_tls_ca_cert_path=ca,
    )

    summary = validate_aiven_mvp_secret_bundle(settings)

    assert summary.ready is True
    assert summary.profile == "aiven-mvp"
    assert len(summary.checks) == EXPECTED_AIVEN_MVP_SECRET_CHECKS
