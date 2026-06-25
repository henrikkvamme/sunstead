import json
from pathlib import Path

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.infra.demo_readiness import (
    inspect_demo_readiness,
    settings_with_aiven_demo_defaults,
)
from supply_intel.infra.demo_refresh import refresh_demo_data
from supply_intel.infra.secrets import validate_cloud_secret_bundle
from supply_intel.observability.graph_metrics import GRAPH_NODES_TOTAL, GRAPH_RELATIONSHIPS_TOTAL
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_all_source_configs

EXPECTED_DEMO_GRAPH_NODES = 541
EXPECTED_DEMO_GRAPH_RELATIONSHIPS = 321
EXPECTED_LOCAL_GRAPH_NODES = 7
EXPECTED_LOCAL_GRAPH_RELATIONSHIPS = 6


def _secret_file(root: Path, name: str, value: str = "secret-value") -> Path:
    path = root / name
    path.write_text(value + "\n", encoding="utf-8")
    return path


def test_demo_readiness_reports_demo_ready_without_live_llm_or_source_keys(
    monkeypatch,
) -> None:
    for env_name in [
        "EIA_API_KEY",
        "OPENFDA_API_KEY",
        "RELIEFWEB_APPNAME",
        "UN_COMTRADE_API_KEY",
    ]:
        monkeypatch.delenv(env_name, raising=False)

    report = inspect_demo_readiness(
        settings=Settings(
            _env_file=None,
            llm_base_url=None,
            llm_api_key=None,
            llm_api_key_file=None,
            llm_model=None,
        ),
        source_configs=load_all_source_configs(Path("sources")),
        graph_counts={
            GRAPH_NODES_TOTAL: EXPECTED_DEMO_GRAPH_NODES,
            GRAPH_RELATIONSHIPS_TOTAL: EXPECTED_DEMO_GRAPH_RELATIONSHIPS,
        },
        graph_count_source="file",
    )

    checks = {check.area: check for check in report.checks}
    assert report.demo_ready_now is True
    assert report.polished_cloud_demo_ready is False
    assert checks["agent_runtime"].status == "ready"
    assert checks["agent_runtime"].details["mode"] == "deterministic"
    assert checks["graph_data"].status == "ready"
    assert checks["graph_data"].details == {
        "source": "file",
        "nodes": EXPECTED_DEMO_GRAPH_NODES,
        "relationships": EXPECTED_DEMO_GRAPH_RELATIONSHIPS,
    }
    assert set(report.missing_live_source_credentials) == {
        "EIA_API_KEY",
        "RELIEFWEB_APPNAME",
        "UN_COMTRADE_API_KEY",
    }
    rendered = report.model_dump_json()
    assert "postgresql://platform:platform" not in rendered


def test_demo_readiness_detects_configured_live_llm_without_printing_key() -> None:
    report = inspect_demo_readiness(
        settings=Settings(
            _env_file=None,
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="secret-value",
            llm_model="demo-model",
        ),
        source_configs=load_all_source_configs(Path("sources")),
    )

    agent_check = {check.area: check for check in report.checks}["agent_runtime"]

    assert agent_check.status == "ready"
    assert agent_check.details["mode"] == "live"
    assert "secret-value" not in report.model_dump_json()


def test_aiven_demo_defaults_fill_conventional_worker_secret_paths(tmp_path: Path) -> None:
    _secret_file(tmp_path, "postgres-url", "postgresql://avnadmin:secret@pg.example.test/db")
    _secret_file(tmp_path, "project-ca.pem", "ca-cert")
    _secret_file(tmp_path, "kafka-service.cert", "client-cert")
    _secret_file(tmp_path, "kafka-service.key", "client-key")
    _secret_file(tmp_path, "kafka-bootstrap", "kafka.example.test:26841")

    settings = settings_with_aiven_demo_defaults(
        Settings(_env_file=None, secret_file_loading="available"),
        secrets_dir=tmp_path,
    )
    summary = validate_cloud_secret_bundle(settings, "aiven-worker")

    assert summary.ready is True
    assert settings.kafka_security_protocol == "SSL"
    assert settings.kafka_bootstrap_servers == "kafka.example.test:26841"
    rendered = summary.model_dump_json()
    assert "postgresql://avnadmin:secret" not in rendered
    assert "client-key" not in rendered


def test_demo_readiness_cli_outputs_report(monkeypatch) -> None:
    async def fake_graph_counts(settings):
        del settings
        return {
            GRAPH_NODES_TOTAL: EXPECTED_DEMO_GRAPH_NODES,
            GRAPH_RELATIONSHIPS_TOTAL: EXPECTED_DEMO_GRAPH_RELATIONSHIPS,
        }

    monkeypatch.setattr("supply_intel.cli._read_neo4j_graph_counts", fake_graph_counts)

    result = CliRunner().invoke(app, ["demo-readiness", "--live-neo4j"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["demo_ready_now"] is True
    graph_check = next(check for check in payload["checks"] if check["area"] == "graph_data")
    assert graph_check["status"] == "ready"
    assert graph_check["details"]["source"] == "neo4j"
    assert graph_check["details"]["relationships"] == EXPECTED_DEMO_GRAPH_RELATIONSHIPS


def test_demo_readiness_cli_can_use_local_graph_counts(tmp_path: Path) -> None:
    refresh_demo_data(
        settings=Settings(data_dir=tmp_path),
        source_ids={"openfda_drug_ndc", "fda_drug_shortages"},
        max_documents_per_source=1,
    )

    result = CliRunner().invoke(
        app,
        ["demo-readiness", "--local-graph", "--data-dir", str(tmp_path)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    graph_check = next(check for check in payload["checks"] if check["area"] == "graph_data")
    assert graph_check["status"] == "ready"
    assert graph_check["details"]["source"] == "file"
    assert graph_check["details"]["nodes"] == EXPECTED_LOCAL_GRAPH_NODES
    assert graph_check["details"]["relationships"] == EXPECTED_LOCAL_GRAPH_RELATIONSHIPS


def test_demo_readiness_cli_rejects_both_graph_count_sources() -> None:
    result = CliRunner().invoke(app, ["demo-readiness", "--local-graph", "--live-neo4j"])

    assert result.exit_code != 0
    assert "mutually exclusive" in result.output


def test_demo_readiness_cli_accepts_aiven_defaults(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _secret_file(tmp_path, "postgres-url", "postgresql://avnadmin:secret@pg.example.test/db")
    _secret_file(tmp_path, "project-ca.pem", "ca-cert")
    _secret_file(tmp_path, "kafka-service.cert", "client-cert")
    _secret_file(tmp_path, "kafka-service.key", "client-key")
    _secret_file(tmp_path, "kafka-bootstrap", "kafka.example.test:26841")

    async def fake_graph_counts(settings):
        del settings
        return {
            GRAPH_NODES_TOTAL: EXPECTED_DEMO_GRAPH_NODES,
            GRAPH_RELATIONSHIPS_TOTAL: EXPECTED_DEMO_GRAPH_RELATIONSHIPS,
        }

    monkeypatch.setattr("supply_intel.cli._read_neo4j_graph_counts", fake_graph_counts)

    result = CliRunner().invoke(
        app,
        [
            "demo-readiness",
            "--aiven-defaults",
            "--aiven-secrets-dir",
            str(tmp_path),
            "--live-neo4j",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    checks = {check["area"]: check for check in payload["checks"]}
    assert checks["cloud_worker"]["status"] == "ready"
    assert "postgresql://avnadmin:secret" not in result.output
