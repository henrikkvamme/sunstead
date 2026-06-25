from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import yaml

from supply_intel.models.source import SourceConfig

KNOWN_ADAPTERS = {
    "rest",
    "paginated_rest",
    "rss",
    "html_scraper",
    "js_rendered_scraper",
    "file_download",
    "pdf_document",
    "manual_seed",
    "webhook",
}

KNOWN_PARSER_PROFILES = {
    "openfda.drug_ndc.v1",
    "openfda.drug_enforcement.v1",
    "fda.drug_shortages_html.v1",
    "fda.warning_letters_xlsx.v1",
    "fda.inspections_dashboard.v1",
    "gdelt.doc_search.v1",
    "gdacs.events_rss.v1",
    "reliefweb.reports.v1",
    "worldbank.commodity_prices_monthly.v1",
    "eia.energy_prices.v1",
    "sec.edgar_supplier_filings.v1",
    "uncomtrade.trade_flows.v1",
    "nyfed.gscpi.v1",
    "gdelt.search_trends.v1",
    "openfda.device_registrationlisting.v1",
    "openfda.device_enforcement.v1",
}
NETWORK_ADAPTERS = {
    "rest",
    "paginated_rest",
    "rss",
    "html_scraper",
    "js_rendered_scraper",
    "file_download",
    "pdf_document",
}
SCRAPING_ADAPTERS = {"html_scraper", "js_rendered_scraper"}
SECRET_PARAM_NAMES = {
    "api_key",
    "apikey",
    "access_token",
    "token",
    "secret",
    "password",
    "authorization",
}
REQUIRED_HTTP_HEADER = "user-agent"
MIN_ENV_REF_LENGTH = 4


def load_source_config(path: Path) -> SourceConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    config = SourceConfig.model_validate(data)
    validate_source_config(config)
    return config


def validate_source_config(config: SourceConfig) -> None:
    if config.adapter not in KNOWN_ADAPTERS:
        raise ValueError(f"Unknown adapter: {config.adapter}")
    if config.parser.profile not in KNOWN_PARSER_PROFILES:
        raise ValueError(f"Unknown parser profile: {config.parser.profile}")
    _validate_auth_ref(config)
    _validate_no_literal_secrets(config)
    _validate_compliance_metadata(config)
    _validate_http_operational_metadata(config)


def find_source_config(source_id: str, source_dir: Path = Path("sources")) -> Path:
    path = source_dir / f"{source_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Source config not found: {path}")
    return path


def load_all_source_configs(source_dir: Path = Path("sources")) -> list[SourceConfig]:
    return [load_source_config(path) for path in sorted(source_dir.glob("*.yaml"))]


def _validate_auth_ref(config: SourceConfig) -> None:
    if config.auth.type == "none":
        return
    if config.auth.env is None or not config.auth.env.replace("_", "").isalnum():
        raise ValueError("Authenticated sources must use an environment variable reference")
    if config.auth.env.upper() != config.auth.env:
        raise ValueError("Authenticated source env refs must use uppercase variable names")


def _validate_no_literal_secrets(config: SourceConfig) -> None:
    for name, value in config.headers.items():
        normalized_name = _normalized_secret_name(name)
        if normalized_name in SECRET_PARAM_NAMES and not _is_env_ref(value):
            raise ValueError("Headers must not contain literal secrets")
        if _looks_like_literal_secret(value):
            raise ValueError("Headers must not contain literal secrets")
    parsed = urlparse(config.base_url)
    for name, value in parse_qsl(parsed.query, keep_blank_values=True):
        normalized_name = _normalized_secret_name(name)
        if normalized_name in SECRET_PARAM_NAMES and value and not _is_env_ref(value):
            raise ValueError("Base URL must not contain literal secrets")


def _validate_compliance_metadata(config: SourceConfig) -> None:
    if config.compliance.robots.lower() in {"", "unknown", "todo", "tbd"}:
        raise ValueError("Source config must include robots or API terms notes")
    if config.compliance.pii_expected:
        raise ValueError("Default source configs must not expect patient-identifiable data")
    if not config.compliance.data_minimization:
        raise ValueError("Source config must include data minimization notes")
    if not config.compliance.retention_notes:
        raise ValueError("Source config must include retention notes")
    if config.adapter in SCRAPING_ADAPTERS and config.compliance.robots == "not_applicable_api":
        raise ValueError("Scraping sources require a robots validation policy")


def _validate_http_operational_metadata(config: SourceConfig) -> None:
    parsed = urlparse(config.base_url)
    if parsed.scheme not in {"http", "https"}:
        return
    header_names = {name.casefold() for name in config.headers}
    if REQUIRED_HTTP_HEADER not in header_names:
        raise ValueError("HTTP sources must declare a User-Agent header")
    if config.adapter in NETWORK_ADAPTERS and (
        config.rate_limit.requests_per_minute is None or config.rate_limit.burst is None
    ):
        raise ValueError("Network sources must declare rate limit requests_per_minute and burst")


def _is_env_ref(value: str) -> bool:
    stripped = value.strip()
    return (
        stripped.startswith("${") and stripped.endswith("}") and len(stripped) >= MIN_ENV_REF_LENGTH
    )


def _looks_like_literal_secret(value: str) -> bool:
    lowered = value.lower()
    if _is_env_ref(value):
        return False
    return any(name in lowered for name in SECRET_PARAM_NAMES)


def _normalized_secret_name(value: str) -> str:
    return value.strip().lower().replace("-", "_")
