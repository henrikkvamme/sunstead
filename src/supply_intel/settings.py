from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SecretFileLoadingMode = Literal["strict", "available", "disabled"]
LLMOutputMode = Literal["tool", "prompted", "native"]


class Settings(BaseSettings):
    secret_file_loading: SecretFileLoadingMode = Field(default="strict", exclude=True)

    platform_env: str = "local"
    platform_user_agent: str = "unnamed-platform-dev/0.1"
    data_dir: Path = Path(".platform-data")

    database_url: str = "postgresql://platform:platform@localhost:55432/platform"
    database_url_file: Path | None = None
    database_ca_cert_path: Path | None = None
    kafka_bootstrap_servers: str = "localhost:19092"
    kafka_security_protocol: str = "PLAINTEXT"
    kafka_sasl_username: str | None = None
    kafka_sasl_password: str | None = None
    kafka_sasl_password_file: Path | None = None
    kafka_ca_cert_path: Path | None = None
    kafka_client_cert_path: Path | None = None
    kafka_client_key_path: Path | None = None

    neo4j_uri: str = "neo4j://localhost:17687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "platform"
    neo4j_password_file: Path | None = None

    grafana_url: str = "http://localhost:13000"
    grafana_token: str | None = None
    grafana_token_file: Path | None = None
    grafana_postgres_host: str = "postgres"
    grafana_postgres_port: int = 5432
    grafana_postgres_user: str = "platform"
    grafana_postgres_password: str | None = "platform"
    grafana_postgres_password_file: Path | None = None
    grafana_postgres_db: str = "platform"
    grafana_postgres_sslmode: str = "disable"
    grafana_postgres_tls_ca_cert_path: Path | None = None

    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_api_key_file: Path | None = None
    llm_model: str | None = None
    llm_output_mode: LLMOutputMode = "tool"
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 2
    llm_max_output_tokens: int = 4096

    embedding_base_url: str | None = None
    embedding_api_key: str | None = None
    embedding_api_key_file: Path | None = None
    embedding_model: str | None = None
    embedding_dimensions: int = 1536

    openfda_api_key: str | None = None
    openfda_api_key_file: Path | None = None
    eia_api_key: str | None = None
    eia_api_key_file: Path | None = None
    un_comtrade_api_key: str | None = None
    un_comtrade_api_key_file: Path | None = None
    reliefweb_appname: str | None = None
    reliefweb_appname_file: Path | None = None

    aiven_project: str | None = None
    aiven_postgres_service: str | None = None
    aiven_kafka_service: str | None = None
    aiven_grafana_service: str | None = None
    aiven_api_token: str | None = None
    aiven_api_token_file: Path | None = None
    aiven_api_base_url: str = "https://api.aiven.io/v1"
    aiven_api_auth_scheme: str = "Bearer"

    source_dir: Path = Field(default=Path("sources"))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def load_secret_files(self) -> Settings:
        _set_from_file(
            self,
            "database_url",
            self.database_url_file,
            mode=self.secret_file_loading,
        )
        _set_from_file(
            self,
            "kafka_sasl_password",
            self.kafka_sasl_password_file,
            mode=self.secret_file_loading,
        )
        _set_from_file(
            self,
            "neo4j_password",
            self.neo4j_password_file,
            mode=self.secret_file_loading,
        )
        _set_from_file(
            self,
            "grafana_token",
            self.grafana_token_file,
            mode=self.secret_file_loading,
        )
        _set_from_file(
            self,
            "grafana_postgres_password",
            self.grafana_postgres_password_file,
            mode=self.secret_file_loading,
        )
        _set_from_file(self, "llm_api_key", self.llm_api_key_file, mode=self.secret_file_loading)
        _set_from_file(
            self,
            "embedding_api_key",
            self.embedding_api_key_file,
            mode=self.secret_file_loading,
        )
        _set_from_file(
            self,
            "openfda_api_key",
            self.openfda_api_key_file,
            mode=self.secret_file_loading,
        )
        _set_from_file(self, "eia_api_key", self.eia_api_key_file, mode=self.secret_file_loading)
        _set_from_file(
            self,
            "un_comtrade_api_key",
            self.un_comtrade_api_key_file,
            mode=self.secret_file_loading,
        )
        _set_from_file(
            self,
            "reliefweb_appname",
            self.reliefweb_appname_file,
            mode=self.secret_file_loading,
        )
        _set_from_file(
            self,
            "aiven_api_token",
            self.aiven_api_token_file,
            mode=self.secret_file_loading,
        )
        return self

    def source_runtime_env_values(self) -> dict[str, str]:
        values = {
            "PLATFORM_USER_AGENT": self.platform_user_agent,
            "OPENFDA_API_KEY": self.openfda_api_key,
            "EIA_API_KEY": self.eia_api_key,
            "UN_COMTRADE_API_KEY": self.un_comtrade_api_key,
            "RELIEFWEB_APPNAME": self.reliefweb_appname,
        }
        return {key: value for key, value in values.items() if value}


def _set_from_file(
    settings: Settings,
    field_name: str,
    path: Path | None,
    *,
    mode: SecretFileLoadingMode,
) -> None:
    if mode == "disabled":
        return
    if path is None:
        return
    if mode == "available" and (
        not path.exists() or not path.is_file() or path.stat().st_size == 0
    ):
        return
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"{field_name}_file is empty: {path}")
    setattr(settings, field_name, value)


def get_settings(secret_file_loading: SecretFileLoadingMode = "strict") -> Settings:
    return Settings(secret_file_loading=secret_file_loading)


def source_runtime_env_value(env_name: str, settings: Settings | None = None) -> str | None:
    if settings is not None and (value := settings.source_runtime_env_values().get(env_name)):
        return value
    return os.getenv(env_name)


def materialize_source_runtime_env(settings: Settings, *, overwrite: bool = False) -> list[str]:
    configured: list[str] = []
    for env_name, value in settings.source_runtime_env_values().items():
        if overwrite or not os.getenv(env_name):
            os.environ[env_name] = value
        configured.append(env_name)
    return configured
