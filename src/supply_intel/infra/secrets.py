from __future__ import annotations

from pathlib import Path
from typing import Literal

from supply_intel.models.base import StrictBaseModel
from supply_intel.settings import Settings

SecretFileStatus = Literal["ok", "not_configured", "missing", "not_file", "empty"]
SecretBundleProfile = Literal["aiven-worker", "aiven-grafana", "aiven-mvp"]


class SecretFileCheck(StrictBaseModel):
    name: str
    env_var: str
    path: str | None = None
    required: bool
    status: SecretFileStatus


class CloudSecretBundleSummary(StrictBaseModel):
    profile: SecretBundleProfile
    ready: bool
    checks: list[SecretFileCheck]
    issues: list[str]


def validate_aiven_worker_secret_bundle(settings: Settings) -> CloudSecretBundleSummary:
    checks = [
        _file_check("postgres_url", "DATABASE_URL_FILE", settings.database_url_file, required=True),
        _file_check(
            "postgres_ca",
            "DATABASE_CA_CERT_PATH",
            settings.database_ca_cert_path,
            required=True,
        ),
    ]
    issues: list[str] = []

    protocol = settings.kafka_security_protocol.upper()
    if settings.kafka_bootstrap_servers == "localhost:19092":
        issues.append("KAFKA_BOOTSTRAP_SERVERS still points at local Redpanda.")
    if protocol not in {"SSL", "SASL_SSL"}:
        issues.append("KAFKA_SECURITY_PROTOCOL must be SSL or SASL_SSL for Aiven Kafka.")

    if protocol in {"SSL", "SASL_SSL"}:
        checks.append(
            _file_check(
                "kafka_ca",
                "KAFKA_CA_CERT_PATH",
                settings.kafka_ca_cert_path,
                required=True,
            )
        )
    if protocol == "SSL":
        checks.extend(
            [
                _file_check(
                    "kafka_client_cert",
                    "KAFKA_CLIENT_CERT_PATH",
                    settings.kafka_client_cert_path,
                    required=True,
                ),
                _file_check(
                    "kafka_client_key",
                    "KAFKA_CLIENT_KEY_PATH",
                    settings.kafka_client_key_path,
                    required=True,
                ),
            ]
        )
    if protocol == "SASL_SSL":
        checks.append(
            _file_check(
                "kafka_sasl_password",
                "KAFKA_SASL_PASSWORD_FILE",
                settings.kafka_sasl_password_file,
                required=True,
            )
        )
        if settings.kafka_sasl_username is None:
            issues.append("KAFKA_SASL_USERNAME is required when KAFKA_SECURITY_PROTOCOL=SASL_SSL.")

    failing_checks = [
        check
        for check in checks
        if check.required and check.status in {"not_configured", "missing", "not_file", "empty"}
    ]
    return CloudSecretBundleSummary(
        profile="aiven-worker",
        ready=not failing_checks and not issues,
        checks=checks,
        issues=[
            *issues,
            *[f"{check.env_var} is {check.status.replace('_', ' ')}" for check in failing_checks],
        ],
    )


def validate_aiven_grafana_secret_bundle(settings: Settings) -> CloudSecretBundleSummary:
    checks = [
        _file_check(
            "grafana_token",
            "GRAFANA_TOKEN_FILE",
            settings.grafana_token_file,
            required=True,
        ),
        _file_check(
            "grafana_postgres_password",
            "GRAFANA_POSTGRES_PASSWORD_FILE",
            settings.grafana_postgres_password_file,
            required=True,
        ),
    ]
    issues: list[str] = []
    if settings.grafana_url == "http://localhost:13000":
        issues.append("GRAFANA_URL still points at local Grafana.")
    if settings.grafana_postgres_host == "postgres":
        issues.append("GRAFANA_POSTGRES_HOST still points at the local Docker service.")
    if settings.grafana_postgres_sslmode in {"verify-ca", "verify-full"}:
        checks.append(
            _file_check(
                "grafana_postgres_tls_ca",
                "GRAFANA_POSTGRES_TLS_CA_CERT_PATH",
                settings.grafana_postgres_tls_ca_cert_path,
                required=True,
            )
        )

    failing_checks = [
        check
        for check in checks
        if check.required and check.status in {"not_configured", "missing", "not_file", "empty"}
    ]
    return CloudSecretBundleSummary(
        profile="aiven-grafana",
        ready=not failing_checks and not issues,
        checks=checks,
        issues=[
            *issues,
            *[f"{check.env_var} is {check.status.replace('_', ' ')}" for check in failing_checks],
        ],
    )


def validate_aiven_mvp_secret_bundle(settings: Settings) -> CloudSecretBundleSummary:
    worker = validate_aiven_worker_secret_bundle(settings)
    grafana = validate_aiven_grafana_secret_bundle(settings)
    return CloudSecretBundleSummary(
        profile="aiven-mvp",
        ready=worker.ready and grafana.ready,
        checks=[*worker.checks, *grafana.checks],
        issues=[*worker.issues, *grafana.issues],
    )


def validate_cloud_secret_bundle(
    settings: Settings,
    profile: SecretBundleProfile,
) -> CloudSecretBundleSummary:
    if profile == "aiven-worker":
        return validate_aiven_worker_secret_bundle(settings)
    if profile == "aiven-grafana":
        return validate_aiven_grafana_secret_bundle(settings)
    return validate_aiven_mvp_secret_bundle(settings)


def _file_check(
    name: str,
    env_var: str,
    path: Path | None,
    *,
    required: bool,
) -> SecretFileCheck:
    if path is None:
        return SecretFileCheck(
            name=name,
            env_var=env_var,
            path=None,
            required=required,
            status="not_configured",
        )
    if not path.exists():
        status: SecretFileStatus = "missing"
    elif not path.is_file():
        status = "not_file"
    elif path.stat().st_size == 0:
        status = "empty"
    else:
        status = "ok"
    return SecretFileCheck(
        name=name,
        env_var=env_var,
        path=str(path),
        required=required,
        status=status,
    )
