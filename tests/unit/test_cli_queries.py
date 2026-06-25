import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from supply_intel.cli import (
    _normalize_postgres_source_run_row,
    _source_query_rows,
    _source_run_query_rows,
    app,
)
from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.graph.queries import GRAPH_QUERY_PARAMETERS, load_graph_query_plan
from supply_intel.models.source import SourceHealth, SourceRun
from supply_intel.sources.registry import load_source_config
from supply_intel.sources.scheduler import source_config_hash

CONSECUTIVE_FAILURES = 2
EXPORTED_GRAPH_NODE_COUNT = 546
EXPORTED_GRAPH_RELATIONSHIP_COUNT = 324
SOURCE_RUN_LIMIT = 2
REQUIRED_GRAPH_QUERIES = {
    "commodity_input_exposure": "commodity_key",
    "disaster_facility_exposure": "disaster_key",
    "drug_supply_chain": "drug_key",
    "facility_downstream_products": "facility_key",
    "ingredient_dependency": "ingredient_key",
    "port_exposure": "port_key",
    "recall_blast_radius": "recall_key",
    "risk_case_context": "risk_case_key",
    "shortage_blast_radius": "shortage_key",
}


def test_query_sources_filters_failed_sources_from_local_health(tmp_path: Path) -> None:
    health = SourceHealth(
        source_id="openfda_drug_ndc",
        status="failing",
        consecutive_failures=CONSECUTIVE_FAILURES,
        metrics={"error_count": CONSECUTIVE_FAILURES},
    )
    (tmp_path / "source_health.jsonl").write_text(
        health.model_dump_json() + "\n",
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["query-sources", "--status", "failed", "--data-dir", str(tmp_path)],
    )

    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert [row["source_id"] for row in rows] == ["openfda_drug_ndc"]
    assert rows[0]["status"] == "failing"
    assert rows[0]["consecutive_failures"] == CONSECUTIVE_FAILURES
    assert rows[0]["parser_profile"] == "openfda.drug_ndc.v1"


def test_source_query_rows_include_postgres_counts_and_serialized_timestamps(monkeypatch) -> None:
    monkeypatch.delenv("OPENFDA_API_KEY", raising=False)
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    last_success_at = datetime(2026, 6, 25, 8, 30, tzinfo=UTC)

    rows = _source_query_rows(
        configs=[config],
        health_rows=[
            {
                "source_id": config.source_id,
                "status": "healthy",
                "last_success_at": last_success_at,
                "consecutive_failures": 0,
                "raw_documents": 2,
                "document_chunks": 2,
                "last_raw_document_at": last_success_at,
            }
        ],
        status=None,
        priority=None,
    )

    assert rows == [
        {
            "source_id": "openfda_drug_ndc",
            "name": "openFDA Drug NDC",
            "enabled": True,
            "priority": "P0",
            "adapter": "paginated_rest",
            "parser_profile": "openfda.drug_ndc.v1",
            "cadence_seconds": 86400,
            "auth_type": "query_param",
            "auth_env": "OPENFDA_API_KEY",
            "auth_required": False,
            "auth_env_configured": False,
            "endpoint_access": "public_limited",
            "robots_policy": "not_applicable_api",
            "rate_limit_requests_per_minute": 220,
            "rate_limit_burst": 10,
            "status": "healthy",
            "last_success_at": "2026-06-25T08:30:00+00:00",
            "last_failure_at": None,
            "consecutive_failures": 0,
            "freshness_lag_seconds": None,
            "raw_documents": 2,
            "document_chunks": 2,
            "last_raw_document_at": "2026-06-25T08:30:00+00:00",
        }
    ]


def test_source_query_rows_filter_endpoint_access_without_secret_values(monkeypatch) -> None:
    monkeypatch.delenv("OPENFDA_API_KEY", raising=False)
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    openfda = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    eia = load_source_config(Path("sources/eia_energy_prices.yaml"))

    requires_env = _source_query_rows(
        configs=[openfda, eia],
        health_rows=[],
        status=None,
        priority=None,
        endpoint_access="requires_env",
    )
    public_limited = _source_query_rows(
        configs=[openfda, eia],
        health_rows=[],
        status=None,
        priority=None,
        endpoint_access="public_limited",
    )

    assert [row["source_id"] for row in requires_env] == ["eia_energy_prices"]
    assert requires_env[0]["auth_env"] == "EIA_API_KEY"
    assert requires_env[0]["auth_env_configured"] is False
    assert "secret" not in json.dumps(requires_env).lower()
    assert [row["source_id"] for row in public_limited] == ["openfda_drug_ndc"]

    monkeypatch.setenv("EIA_API_KEY", "configured-secret")
    configured = _source_query_rows(
        configs=[openfda, eia],
        health_rows=[],
        status=None,
        priority=None,
        endpoint_access="configured",
    )

    assert [row["source_id"] for row in configured] == ["eia_energy_prices"]
    assert "configured-secret" not in json.dumps(configured)


def test_export_event_schemas_writes_schema_bundle(tmp_path: Path) -> None:
    output = tmp_path / "event-schemas.json"
    runner = CliRunner()

    result = runner.invoke(app, ["export-event-schemas", "--out", str(output)])

    assert result.exit_code == 0
    assert result.output.strip() == str(output)
    bundle = json.loads(output.read_text(encoding="utf-8"))
    assert "envelope" in bundle
    assert "ingest.raw_document_created" in bundle["payloads"]


def test_register_source_file_backend_is_idempotent_and_audited(tmp_path: Path) -> None:
    source_path = Path("sources/openfda_drug_ndc.yaml")
    config = load_source_config(source_path)
    runner = CliRunner()

    first = runner.invoke(
        app,
        ["register-source", str(source_path), "--actor", "unit-test"],
        env={"DATA_DIR": str(tmp_path)},
    )
    second = runner.invoke(
        app,
        ["register-source", str(source_path), "--actor", "unit-test"],
        env={"DATA_DIR": str(tmp_path)},
    )

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert json.loads(first.output)["result"] == "created"
    assert json.loads(second.output)["result"] == "unchanged"
    store = FileEvidenceStore(tmp_path)
    registered = store.read_collection("registered_sources")
    audits = store.read_collection("source_registry_audit")
    assert [row["source_id"] for row in registered] == ["openfda_drug_ndc"]
    assert [row["result"] for row in audits] == ["created", "unchanged"]
    assert {row["config_hash"] for row in audits} == {source_config_hash(config)}
    assert {row["actor"] for row in audits} == {"unit-test"}


def test_query_source_runs_filters_local_runs_and_hides_cursors_by_default(
    tmp_path: Path,
) -> None:
    store = FileEvidenceStore(tmp_path)
    matching_run = SourceRun(
        source_id="openfda_drug_ndc",
        run_type="scheduled",
        status="succeeded",
        finished_at=datetime(2026, 6, 25, 8, 30, tzinfo=UTC),
        cursor_before={"skip": 0},
        cursor_after={"skip": 1},
        documents_seen=1,
        documents_created=1,
        idempotency_key="scheduled-openfda",
    )
    store.write_source_run(matching_run)
    store.write_source_run(
        SourceRun(
            source_id="eia_energy_prices",
            run_type="scheduled",
            status="failed",
            error_count=1,
            metadata={"error": "missing EIA_API_KEY"},
            idempotency_key="scheduled-eia",
        )
    )
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "query-source-runs",
            "--data-dir",
            str(tmp_path),
            "--source-id",
            "openfda_drug_ndc",
            "--status",
            "succeeded",
        ],
    )

    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert [row["source_run_id"] for row in rows] == [str(matching_run.id)]
    assert rows[0]["source_id"] == "openfda_drug_ndc"
    assert rows[0]["documents_seen"] == 1
    assert rows[0]["documents_created"] == 1
    assert "cursor_before" not in rows[0]
    assert "cursor_after" not in rows[0]


def test_query_source_runs_can_include_cursor_snapshots(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    run = SourceRun(
        source_id="openfda_drug_ndc",
        run_type="scheduled",
        status="succeeded",
        cursor_before={"skip": 0},
        cursor_after={"skip": 1},
        documents_seen=1,
        idempotency_key="scheduled-openfda",
    )
    store.write_source_run(run)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "query-source-runs",
            "--data-dir",
            str(tmp_path),
            "--include-cursors",
        ],
    )

    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert rows[0]["cursor_before"] == {"skip": 0}
    assert rows[0]["cursor_after"] == {"skip": 1}


def test_source_run_query_rows_serializes_postgres_timestamps_and_applies_limit() -> None:
    older = SourceRun(
        source_id="openfda_drug_ndc",
        run_type="scheduled",
        status="succeeded",
        documents_seen=1,
        idempotency_key="older",
    )
    newer = SourceRun(
        source_id="openfda_drug_ndc",
        run_type="scheduled",
        status="failed",
        error_count=1,
        metadata={"error": "rate limited"},
        idempotency_key="newer",
    )
    newer.created_at = datetime(2026, 6, 25, 9, 0, tzinfo=UTC)
    newer.updated_at = datetime(2026, 6, 25, 9, 30, tzinfo=UTC)
    older.created_at = datetime(2026, 6, 25, 8, 0, tzinfo=UTC)
    older.updated_at = datetime(2026, 6, 25, 8, 30, tzinfo=UTC)

    rows = _source_run_query_rows(
        run_rows=[older.model_dump(mode="python"), newer.model_dump(mode="python")],
        source_id="openfda_drug_ndc",
        status=None,
        limit=SOURCE_RUN_LIMIT,
    )

    assert [row["idempotency_key"] for row in rows] == ["newer", "older"]
    assert rows[0]["error"] == "rate limited"
    assert rows[0]["created_at"] == "2026-06-25T09:00:00+00:00"


def test_source_run_query_rows_can_return_latest_state_per_run_before_status_filter() -> None:
    completed = SourceRun(
        source_id="openfda_drug_ndc",
        run_type="scheduled",
        status="succeeded",
        documents_seen=1,
        idempotency_key="completed",
    )
    completed.created_at = datetime(2026, 6, 25, 8, 0, tzinfo=UTC)
    completed.updated_at = datetime(2026, 6, 25, 8, 30, tzinfo=UTC)

    historical_success = SourceRun(
        source_id="openfda_drug_ndc",
        run_type="scheduled",
        status="succeeded",
        documents_seen=1,
        idempotency_key="failed-later",
    )
    historical_success.created_at = datetime(2026, 6, 25, 9, 0, tzinfo=UTC)
    historical_success.updated_at = datetime(2026, 6, 25, 9, 10, tzinfo=UTC)

    latest_failure = SourceRun(
        source_id="openfda_drug_ndc",
        run_type="scheduled",
        status="failed",
        error_count=1,
        idempotency_key="failed-later",
    )
    latest_failure.id = historical_success.id
    latest_failure.created_at = historical_success.created_at
    latest_failure.updated_at = datetime(2026, 6, 25, 9, 30, tzinfo=UTC)

    rows = _source_run_query_rows(
        run_rows=[
            completed.model_dump(mode="python"),
            historical_success.model_dump(mode="python"),
            latest_failure.model_dump(mode="python"),
        ],
        source_id="openfda_drug_ndc",
        status="succeeded",
        limit=SOURCE_RUN_LIMIT,
        latest_state_only=True,
    )

    assert [row["source_run_id"] for row in rows] == [str(completed.id)]
    assert rows[0]["status"] == "succeeded"


def test_query_source_runs_latest_state_only_cli(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    pending = SourceRun(
        source_id="openfda_drug_ndc",
        run_type="scheduled",
        status="pending",
        idempotency_key="scheduled-openfda",
    )
    pending.updated_at = datetime(2026, 6, 25, 8, 0, tzinfo=UTC)
    succeeded = SourceRun(
        source_id="openfda_drug_ndc",
        run_type="scheduled",
        status="succeeded",
        documents_seen=1,
        idempotency_key="scheduled-openfda",
    )
    succeeded.id = pending.id
    succeeded.created_at = pending.created_at
    succeeded.updated_at = datetime(2026, 6, 25, 8, 30, tzinfo=UTC)
    store.write_source_run(pending)
    store.write_source_run(succeeded)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "query-source-runs",
            "--data-dir",
            str(tmp_path),
            "--latest-state-only",
        ],
    )

    assert result.exit_code == 0
    rows = json.loads(result.output)
    assert [row["status"] for row in rows] == ["succeeded"]


def test_postgres_source_run_rows_decode_json_object_strings() -> None:
    run = SourceRun(
        source_id="openfda_drug_ndc",
        run_type="scheduled",
        status="succeeded",
        documents_seen=1,
        idempotency_key="scheduled-openfda",
    )
    row = run.model_dump(mode="python")
    row["cursor_before"] = "{}"
    row["cursor_after"] = '{"etag": "live-v1"}'
    row["metadata"] = '{"error": "rate limited"}'

    normalized = _normalize_postgres_source_run_row(row)
    rows = _source_run_query_rows(
        run_rows=[normalized],
        source_id="openfda_drug_ndc",
        status=None,
        limit=SOURCE_RUN_LIMIT,
        include_cursors=True,
    )

    assert rows[0]["cursor_before"] == {}
    assert rows[0]["cursor_after"] == {"etag": "live-v1"}
    assert rows[0]["error"] == "rate limited"

    row["cursor_after"] = "null"
    assert _normalize_postgres_source_run_row(row)["cursor_after"] is None


def test_query_graph_plans_named_query_with_cli_parameters() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["query-graph", "drug-supply-chain", "--drug-key", "Drug:ndc_product:0002-8215"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["query_name"] == "drug_supply_chain"
    assert payload["parameters"] == {"drug_key": "Drug:ndc_product:0002-8215"}
    assert "MATCH path = (d:Drug {key: $drug_key})" in payload["cypher"]


def test_required_graph_query_catalog_is_parameterized() -> None:
    assert set(GRAPH_QUERY_PARAMETERS) >= set(REQUIRED_GRAPH_QUERIES)
    for query_name, parameter_name in REQUIRED_GRAPH_QUERIES.items():
        plan = load_graph_query_plan(
            query_name,
            parameters={parameter_name: f"{parameter_name}:example"},
        )

        assert plan.query_name == query_name
        assert plan.parameters == {parameter_name: f"{parameter_name}:example"}
        assert f"${parameter_name}" in plan.cypher


def test_query_graph_plans_recall_blast_radius_with_cli_parameter() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["query-graph", "recall-blast-radius", "--recall-key", "openfda_recall:123"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["query_name"] == "recall_blast_radius"
    assert payload["parameters"] == {"recall_key": "openfda_recall:123"}
    assert "MATCH path = (r:Recall {key: $recall_key})" in payload["cypher"]


def test_query_graph_requires_named_query_parameters() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["query-graph", "drug-supply-chain"])

    assert result.exit_code != 0
    assert "requires --drug-key" in result.output


def test_export_graph_snapshot_cli_passes_output_and_limit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_export_graph_snapshot(settings, output_path: Path, *, limit: int):
        del settings
        calls.append({"output_path": output_path, "limit": limit})
        return {
            "output_path": str(output_path),
            "generated_at": "2026-06-25T10:54:23Z",
            "nodes": 2,
            "edges": 1,
            "graph_nodes": EXPORTED_GRAPH_NODE_COUNT,
            "graph_relationships": EXPORTED_GRAPH_RELATIONSHIP_COUNT,
            "data_mode": "neo4j_snapshot",
        }

    monkeypatch.setattr("supply_intel.cli._export_graph_snapshot", fake_export_graph_snapshot)
    output_path = tmp_path / "graph.json"

    result = CliRunner().invoke(
        app,
        [
            "export-graph-snapshot",
            "--output",
            str(output_path),
            "--limit",
            "25",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["output_path"] == str(output_path)
    assert payload["data_mode"] == "neo4j_snapshot"
    assert calls == [{"output_path": output_path, "limit": 25}]


def test_export_graph_snapshot_cli_can_use_file_store_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_export_file_graph_snapshot(data_dir: Path, output_path: Path, *, limit: int):
        calls.append({"data_dir": data_dir, "output_path": output_path, "limit": limit})
        return {
            "output_path": str(output_path),
            "generated_at": "2026-06-25T10:54:23Z",
            "nodes": 4,
            "edges": 3,
            "graph_nodes": 4,
            "graph_relationships": 3,
            "data_mode": "file_snapshot",
        }

    monkeypatch.setattr(
        "supply_intel.cli._export_file_graph_snapshot",
        fake_export_file_graph_snapshot,
    )
    output_path = tmp_path / "graph.json"
    data_dir = tmp_path / "data"

    result = CliRunner().invoke(
        app,
        [
            "export-graph-snapshot",
            "--source",
            "file",
            "--data-dir",
            str(data_dir),
            "--output",
            str(output_path),
            "--limit",
            "25",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["output_path"] == str(output_path)
    assert payload["data_mode"] == "file_snapshot"
    assert calls == [{"data_dir": data_dir, "output_path": output_path, "limit": 25}]
