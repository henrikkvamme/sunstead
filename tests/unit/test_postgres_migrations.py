from pathlib import Path
from typing import Any

import pytest

from supply_intel.db import postgres
from supply_intel.db.postgres import apply_migrations_with_connection, migration_checksum


class FakeMigrationConnection:
    def __init__(self, applied: dict[str, str] | None = None) -> None:
        self.applied = applied or {}
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append((query, args))
        if query.startswith("INSERT INTO schema_migrations"):
            self.applied[str(args[0])] = str(args[1])
        return "OK"

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        if "FROM schema_migrations" not in query:
            return None
        checksum = self.applied.get(str(args[0]))
        if checksum is None:
            return None
        return {"checksum": checksum}

    async def close(self) -> None:
        return None


async def test_apply_migrations_tracks_applied_versions(tmp_path: Path) -> None:
    migration = tmp_path / "0001_test.sql"
    migration.write_text("CREATE TABLE example (id int);\n", encoding="utf-8")
    connection = FakeMigrationConnection()

    results = await apply_migrations_with_connection(connection, tmp_path)

    assert [result.status for result in results] == ["applied"]
    assert connection.applied["0001_test"] == migration_checksum(migration.read_text())
    assert any(
        "CREATE TABLE IF NOT EXISTS schema_migrations" in query for query, _ in connection.executed
    )
    assert any("CREATE TABLE example" in query for query, _ in connection.executed)


async def test_apply_migrations_skips_matching_checksum(tmp_path: Path) -> None:
    migration = tmp_path / "0001_test.sql"
    sql = "CREATE TABLE example (id int);\n"
    migration.write_text(sql, encoding="utf-8")
    connection = FakeMigrationConnection(applied={"0001_test": migration_checksum(sql)})

    results = await apply_migrations_with_connection(connection, tmp_path)

    assert [result.status for result in results] == ["skipped"]
    assert not any("CREATE TABLE example" in query for query, _ in connection.executed)


async def test_apply_migrations_rejects_changed_checksum(tmp_path: Path) -> None:
    migration = tmp_path / "0001_test.sql"
    migration.write_text("CREATE TABLE changed (id int);\n", encoding="utf-8")
    connection = FakeMigrationConnection(applied={"0001_test": "old-checksum"})

    with pytest.raises(ValueError, match="checksum changed"):
        await apply_migrations_with_connection(connection, tmp_path)


async def test_apply_migrations_passes_ca_cert_path_to_connector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = tmp_path / "0001_test.sql"
    migration.write_text("CREATE TABLE example (id int);\n", encoding="utf-8")
    connection = FakeMigrationConnection()
    ca_path = tmp_path / "ca.pem"
    ca_path.write_text("placeholder", encoding="utf-8")
    captured: dict[str, object] = {}

    async def fake_connect_database(database_url: str, *, ca_cert_path: Path | None = None):
        captured["database_url"] = database_url
        captured["ca_cert_path"] = ca_cert_path
        return connection

    monkeypatch.setattr(postgres, "connect_database", fake_connect_database)

    results = await postgres.apply_migrations(
        "postgresql://example.test/defaultdb",
        root=tmp_path,
        ca_cert_path=ca_path,
    )

    assert [result.status for result in results] == ["applied"]
    assert captured == {
        "database_url": "postgresql://example.test/defaultdb",
        "ca_cert_path": ca_path,
    }


def test_initial_migration_indexes_mcp_audit_log() -> None:
    sql = Path("migrations/0001_extensions_and_evidence_schema.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS mcp_audit_log" in sql
    assert "mcp_audit_log_action_started_idx" in sql
    assert "mcp_audit_log_project_service_started_idx" in sql
    assert "mcp_audit_log_destructive_status_idx" in sql
    assert "mcp_audit_log_request_gin_idx" in sql


def test_initial_migration_indexes_ops_metrics() -> None:
    sql = Path("migrations/0001_extensions_and_evidence_schema.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS ops_metrics" in sql
    assert "idempotency_key text NOT NULL UNIQUE" in sql
    assert "ops_metrics_name_observed_idx" in sql
    assert "ops_metrics_service_observed_idx" in sql
    assert "ops_metrics_topic_observed_idx" in sql
    assert "ops_metrics_tags_gin_idx" in sql


def test_initial_migration_indexes_source_cursors() -> None:
    sql = Path("migrations/0001_extensions_and_evidence_schema.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS source_cursors" in sql
    assert "source_cursors_watermark_idx" in sql


def test_initial_migration_includes_risk_feature_snapshots() -> None:
    sql = Path("migrations/0001_extensions_and_evidence_schema.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS risk_feature_snapshots" in sql
    assert 'UNIQUE (risk_case_id, feature_name, feature_version, "window")' in sql
    assert "risk_feature_snapshots_case_feature_idx" in sql


def test_initial_migration_includes_risk_candidates() -> None:
    sql = Path("migrations/0001_extensions_and_evidence_schema.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS risk_candidates" in sql
    assert "candidate_key text NOT NULL UNIQUE" in sql
    assert "risk_candidates_type_score_idx" in sql
    assert "risk_candidates_scope_gin_idx" in sql
    assert "risk_candidates_signals_gin_idx" in sql


def test_human_review_queue_migration_adds_cloud_review_queue() -> None:
    sql = Path("migrations/0002_human_review_queue.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS human_review_queue" in sql
    assert "UNIQUE (target_table, target_id)" in sql
    assert "human_review_queue_status_priority_idx" in sql
    assert "human_review_queue_evidence_span_ids_gin_idx" in sql


def test_agent_finding_runtime_metadata_migration_adds_agent_audit_fields() -> None:
    sql = Path("migrations/0003_agent_finding_runtime_metadata.sql").read_text(encoding="utf-8")

    assert "ALTER TABLE agent_findings" in sql
    assert "ADD COLUMN IF NOT EXISTS model_name text" in sql
    assert "ADD COLUMN IF NOT EXISTS prompt_hash text" in sql
    assert "ADD COLUMN IF NOT EXISTS input_hash text" in sql
    assert "ADD COLUMN IF NOT EXISTS output_schema text" in sql
    assert "ADD COLUMN IF NOT EXISTS usage jsonb" in sql
    assert "agent_findings_runtime_idx" in sql
    assert "agent_findings_prompt_input_idx" in sql
