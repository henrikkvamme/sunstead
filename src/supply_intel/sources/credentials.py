from __future__ import annotations

from typing import Literal

from pydantic import Field

from supply_intel.models.base import StrictBaseModel
from supply_intel.models.source import SourceConfig
from supply_intel.settings import Settings, source_runtime_env_value

CredentialStatus = Literal["configured", "missing_required", "missing_optional"]
SameDayLikelihood = Literal["likely_today", "possible_today", "not_needed"]


class SourceCredentialGuide(StrictBaseModel):
    env: str
    label: str
    acquisition_url: str
    same_day_likelihood: SameDayLikelihood
    demo_priority: Literal["high", "medium", "low"]
    notes: str


class SourceCredentialReportRow(StrictBaseModel):
    env: str
    label: str
    status: CredentialStatus
    configured: bool
    required_by: list[str] = Field(default_factory=list)
    optional_for: list[str] = Field(default_factory=list)
    source_count: int
    acquisition_url: str | None = None
    same_day_likelihood: SameDayLikelihood | None = None
    demo_priority: Literal["high", "medium", "low"] | None = None
    notes: str | None = None


class SourceCredentialReport(StrictBaseModel):
    rows: list[SourceCredentialReportRow]
    missing_required: list[str]
    missing_optional: list[str]
    configured: list[str]


SOURCE_CREDENTIAL_GUIDES: dict[str, SourceCredentialGuide] = {
    "EIA_API_KEY": SourceCredentialGuide(
        env="EIA_API_KEY",
        label="EIA Open Data API key",
        acquisition_url="https://www.eia.gov/opendata/register.php",
        same_day_likelihood="likely_today",
        demo_priority="high",
        notes="Email registration key for energy-price input-cost signals.",
    ),
    "UN_COMTRADE_API_KEY": SourceCredentialGuide(
        env="UN_COMTRADE_API_KEY",
        label="UN Comtrade API subscription key",
        acquisition_url="https://uncomtrade.org/docs/api-subscription-keys/",
        same_day_likelihood="likely_today",
        demo_priority="high",
        notes="Free API subscription key from the UN Comtrade developer portal.",
    ),
    "RELIEFWEB_APPNAME": SourceCredentialGuide(
        env="RELIEFWEB_APPNAME",
        label="ReliefWeb pre-approved app name",
        acquisition_url="https://apidoc.rwlabs.org/",
        same_day_likelihood="possible_today",
        demo_priority="medium",
        notes=(
            "App name/domain string for humanitarian report signals; ReliefWeb states "
            "appnames must be pre-approved from 2025-11-01."
        ),
    ),
    "OPENFDA_API_KEY": SourceCredentialGuide(
        env="OPENFDA_API_KEY",
        label="openFDA API key",
        acquisition_url="https://open.fda.gov/apis/authentication/",
        same_day_likelihood="likely_today",
        demo_priority="medium",
        notes="Optional key that increases openFDA daily quota for drug and device sources.",
    ),
}


def build_source_credential_report(
    *,
    source_configs: list[SourceConfig],
    settings: Settings,
    only_missing: bool = False,
) -> SourceCredentialReport:
    by_env: dict[str, dict[str, list[str]]] = {}
    for config in source_configs:
        if config.auth.type == "none" or config.auth.env is None:
            continue
        bucket = by_env.setdefault(config.auth.env, {"required": [], "optional": []})
        target = "required" if config.auth.required else "optional"
        bucket[target].append(config.source_id)

    all_rows: list[SourceCredentialReportRow] = []
    for env_name, grouped_sources in sorted(by_env.items()):
        configured = bool(source_runtime_env_value(env_name, settings))
        required_by = sorted(grouped_sources["required"])
        optional_for = sorted(grouped_sources["optional"])
        if configured:
            status: CredentialStatus = "configured"
        elif required_by:
            status = "missing_required"
        else:
            status = "missing_optional"
        guide = SOURCE_CREDENTIAL_GUIDES.get(env_name)
        all_rows.append(
            SourceCredentialReportRow(
                env=env_name,
                label=guide.label if guide is not None else env_name,
                status=status,
                configured=configured,
                required_by=required_by,
                optional_for=optional_for,
                source_count=len(required_by) + len(optional_for),
                acquisition_url=guide.acquisition_url if guide is not None else None,
                same_day_likelihood=guide.same_day_likelihood if guide is not None else None,
                demo_priority=guide.demo_priority if guide is not None else None,
                notes=guide.notes if guide is not None else None,
            )
        )
    rows = [row for row in all_rows if not only_missing or row.status != "configured"]
    return SourceCredentialReport(
        rows=rows,
        missing_required=[row.env for row in all_rows if row.status == "missing_required"],
        missing_optional=[row.env for row in all_rows if row.status == "missing_optional"],
        configured=[row.env for row in all_rows if row.status == "configured"],
    )
