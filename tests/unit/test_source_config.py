from pathlib import Path

import pytest

from supply_intel.sources.registry import load_all_source_configs, load_source_config

ONE_DAY_SECONDS = 86400


def test_openfda_ndc_source_config_is_valid() -> None:
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))

    assert config.source_id == "openfda_drug_ndc"
    assert config.adapter == "paginated_rest"
    assert config.cadence_seconds == ONE_DAY_SECONDS
    assert config.auth.env == "OPENFDA_API_KEY"
    assert config.auth.required is False


def test_all_checked_in_source_configs_include_governance_metadata() -> None:
    configs = load_all_source_configs(Path("sources"))

    assert configs
    assert all(config.compliance.data_minimization for config in configs)
    assert all(config.compliance.retention_notes for config in configs)
    assert all(config.rate_limit.requests_per_minute for config in configs)
    assert all(config.rate_limit.burst for config in configs)


def test_source_config_rejects_literal_secret_in_base_url(tmp_path: Path) -> None:
    path = _write_source_config(
        tmp_path,
        base_url="https://example.test/feed.json?api_key=literal-secret",
    )

    with pytest.raises(ValueError, match="Base URL must not contain literal secrets"):
        load_source_config(path)


def test_source_config_rejects_http_source_without_user_agent(tmp_path: Path) -> None:
    path = _write_source_config(tmp_path, headers="")

    with pytest.raises(ValueError, match="HTTP sources must declare a User-Agent"):
        load_source_config(path)


def _write_source_config(
    tmp_path: Path,
    *,
    base_url: str = "https://example.test/feed.json",
    headers: str = 'headers:\n  User-Agent: "${PLATFORM_USER_AGENT}"',
) -> Path:
    path = tmp_path / "source.yaml"
    path.write_text(
        f"""
source_id: test_source
name: Test Source
source_type: government_api
adapter: rest
enabled: true
priority: P3
base_url: {base_url}
method: GET
auth:
  type: none
{headers}
pagination:
  type: none
cursor:
  strategy: none
rate_limit:
  requests_per_minute: 60
  burst: 2
dedupe:
  key_fields:
    - canonical_url
  content_hash: sha256
  canonical_url: true
parser:
  profile: openfda.drug_ndc.v1
  chunking: json_record
compliance:
  robots: not_applicable_api
  license_notes: Public test source.
  pii_expected: false
  data_minimization: Store only fields needed for provenance tests.
  retention_notes: Test records retained only for test duration.
schedule:
  cadence: 1d
""".lstrip(),
        encoding="utf-8",
    )
    return path
