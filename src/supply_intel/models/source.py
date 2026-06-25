import base64
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, field_serializer, field_validator, model_validator

from supply_intel.models.base import StrictBaseModel, TimestampedModel, VersionedModel


def parse_duration_seconds(value: str | int | None) -> int | None:
    if value is None or isinstance(value, int):
        return value
    raw = value.strip().lower()
    units = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }
    if raw.isdigit():
        return int(raw)
    unit = raw[-1]
    if unit not in units or not raw[:-1].isdigit():
        raise ValueError(f"Unsupported duration: {value}")
    return int(raw[:-1]) * units[unit]


class AuthConfig(StrictBaseModel):
    type: Literal["none", "query_param", "header", "bearer_env"] = "none"
    env: str | None = None
    param: str | None = None
    header: str | None = None
    required: bool = True

    @model_validator(mode="after")
    def validate_secret_reference(self) -> "AuthConfig":
        if self.type != "none" and not self.env:
            raise ValueError("Authenticated sources must reference an environment variable")
        return self


class BackoffConfig(StrictBaseModel):
    min_seconds: int = Field(default=1, ge=0)
    max_seconds: int = Field(default=60, ge=1)


class RateLimitConfig(StrictBaseModel):
    requests_per_minute: int | None = Field(default=None, ge=1)
    burst: int | None = Field(default=None, ge=1)
    backoff: BackoffConfig = Field(default_factory=BackoffConfig)


class PaginationConfig(StrictBaseModel):
    type: Literal[
        "none",
        "skip_limit",
        "page_number",
        "cursor_token",
        "link_header",
        "next_url",
        "date_window",
    ] = "none"
    limit_param: str = "limit"
    offset_param: str = "skip"
    page_size: int = Field(default=1000, ge=1, le=5000)
    max_offset: int | None = Field(default=None, ge=0)
    results_path: str | None = None


class CursorConfig(StrictBaseModel):
    strategy: Literal[
        "none",
        "etag",
        "last_modified",
        "date_watermark",
        "date_window",
        "cursor_token",
        "offset_checkpoint",
        "content_hash",
        "full_refresh_plus_watermark",
    ] = "none"
    field: str | None = None
    lag_seconds: int = Field(default=0, ge=0)


class DedupeConfig(StrictBaseModel):
    key_fields: list[str] = Field(default_factory=list)
    content_hash: Literal["sha256"] = "sha256"
    canonical_url: bool = True

    @model_validator(mode="after")
    def validate_key(self) -> "DedupeConfig":
        if not self.key_fields:
            raise ValueError("dedupe.key_fields must contain at least one stable field")
        return self


class ParserConfig(StrictBaseModel):
    profile: str
    chunking: str = "json_record"
    max_chunks: int | None = Field(default=None, ge=1)


class ComplianceConfig(StrictBaseModel):
    robots: str
    license_notes: str = Field(min_length=1)
    pii_expected: bool = False
    data_minimization: str | None = None
    retention_notes: str | None = None


class ScheduleConfig(StrictBaseModel):
    cadence: str | int
    jitter_seconds: int = Field(default=0, ge=0)

    @property
    def cadence_seconds(self) -> int:
        parsed = parse_duration_seconds(self.cadence)
        if parsed is None or parsed <= 0:
            raise ValueError("schedule.cadence must be positive")
        return parsed


class FixtureConfig(StrictBaseModel):
    success: Path | None = None
    empty: Path | None = None


class SourceConfig(VersionedModel):
    source_id: str
    name: str
    source_type: str
    adapter: str
    enabled: bool = True
    priority: Literal["P0", "P1", "P2", "P3"] = "P2"
    base_url: str
    method: Literal["GET", "POST"] = "GET"
    auth: AuthConfig = Field(default_factory=AuthConfig)
    headers: dict[str, str] = Field(default_factory=dict)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    cursor: CursorConfig = Field(default_factory=CursorConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    dedupe: DedupeConfig
    parser: ParserConfig
    compliance: ComplianceConfig
    schedule: ScheduleConfig
    fixtures: FixtureConfig = Field(default_factory=FixtureConfig)

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        if not value.replace("_", "").isalnum() or value.lower() != value:
            raise ValueError("source_id must be lowercase snake case")
        return value

    @model_validator(mode="after")
    def validate_compliance(self) -> "SourceConfig":
        if self.adapter in {"html_scraper", "js_rendered_scraper"} and not self.compliance.robots:
            raise ValueError("scraping sources require robots policy notes")
        return self

    @property
    def cadence_seconds(self) -> int:
        return self.schedule.cadence_seconds


class SourceRun(TimestampedModel):
    source_id: str
    run_type: Literal["scheduled", "manual", "backfill", "replay", "test"]
    status: Literal["pending", "running", "succeeded", "failed"]
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    cursor_before: dict[str, Any] | None = None
    cursor_after: dict[str, Any] | None = None
    documents_seen: int = 0
    documents_created: int = 0
    documents_unchanged: int = 0
    error_count: int = 0
    correlation_id: UUID = Field(default_factory=uuid4)
    idempotency_key: str


class SourceCursor(TimestampedModel):
    source_id: str
    cursor_name: str = "default"
    cursor_state: dict[str, Any] = Field(default_factory=dict)
    watermark: datetime | None = None
    etag: str | None = None
    last_content_hash: str | None = None
    updated_by_run_id: UUID | None = None


class IngestionError(TimestampedModel):
    source_id: str
    source_run_id: UUID | None = None
    raw_document_id: UUID | None = None
    stage: Literal[
        "scheduler",
        "adapter",
        "storage",
        "parser",
        "extractor",
        "entity_resolution",
        "graph",
        "risk",
        "agent",
    ]
    error_type: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SourceHealth(TimestampedModel):
    source_id: str
    status: Literal["healthy", "degraded", "failing", "unknown"]
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    consecutive_failures: int = Field(default=0, ge=0)
    freshness_lag_seconds: int | None = Field(default=None, ge=0)
    last_error_id: UUID | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class SourceRegistryAudit(TimestampedModel):
    source_id: str
    action: Literal["register_source"]
    backend: Literal["file", "postgres"]
    result: Literal["created", "updated", "unchanged", "upserted"]
    config_hash: str
    config_path: str | None = None
    actor: str | None = None


class RawDocument(TimestampedModel):
    source_id: str
    source_run_id: UUID
    source_url: str | None = None
    canonical_url: str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    response_headers: dict[str, Any] = Field(default_factory=dict)
    http_status: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    content_hash: str
    payload_storage: Literal["inline", "filesystem", "object_store"] = "inline"
    payload_bytes: bytes | None = None
    payload_text: str | None = None
    payload_uri: str | None = None
    source_published_at: datetime | None = None
    source_updated_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    dedupe_key: str
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload_bytes", mode="before")
    @classmethod
    def decode_payload_bytes(cls, value: object) -> object:
        if isinstance(value, str):
            return base64.b64decode(value.encode("ascii"))
        return value

    @field_serializer("payload_bytes", when_used="json")
    def serialize_payload_bytes(self, value: bytes | None) -> str | None:
        if value is None:
            return None
        return base64.b64encode(value).decode("ascii")
