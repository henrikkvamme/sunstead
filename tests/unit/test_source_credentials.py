import json
from pathlib import Path

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.settings import Settings
from supply_intel.sources.credentials import build_source_credential_report
from supply_intel.sources.registry import load_all_source_configs


def test_source_credential_report_uses_settings_secret_files(tmp_path: Path) -> None:
    secret = tmp_path / "eia-key"
    secret.write_text("configured-secret\n", encoding="utf-8")
    settings = Settings(_env_file=None, eia_api_key_file=secret)

    report = build_source_credential_report(
        source_configs=load_all_source_configs(Path("sources")),
        settings=settings,
        only_missing=True,
    )

    assert "EIA_API_KEY" in report.configured
    assert "EIA_API_KEY" not in report.missing_required
    assert "EIA_API_KEY" not in [row.env for row in report.rows]
    assert "configured-secret" not in report.model_dump_json()


def test_source_credentials_cli_does_not_print_secret(monkeypatch, tmp_path: Path) -> None:
    secret = tmp_path / "eia-key"
    secret.write_text("configured-secret\n", encoding="utf-8")
    monkeypatch.setattr(
        "supply_intel.cli.get_settings",
        lambda secret_file_loading="strict": Settings(_env_file=None, eia_api_key_file=secret),
    )

    result = CliRunner().invoke(app, ["source-credentials", "--only-missing"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "EIA_API_KEY" in payload["configured"]
    assert "configured-secret" not in result.output
