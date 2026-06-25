import json
from datetime import UTC, datetime
from pathlib import Path

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.models.source import SourceRun
from supply_intel.pipeline import ingest_openfda_ndc_fixture
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config


def test_successful_ingestion_updates_local_source_health(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    settings = Settings(data_dir=tmp_path)

    ingest_openfda_ndc_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_ndc/success.json"),
        settings=settings,
        max_documents=1,
    )

    health = _read_jsonl(tmp_path / "source_health.jsonl")
    assert len(health) == 1
    assert health[0]["source_id"] == "openfda_drug_ndc"
    assert health[0]["status"] == "healthy"
    assert health[0]["consecutive_failures"] == 0
    assert health[0]["last_success_at"]
    assert health[0]["freshness_lag_seconds"] == 0
    assert health[0]["metrics"]["documents_seen"] == 1
    assert health[0]["metrics"]["documents_created"] == 1


def test_failed_source_run_updates_local_source_health_without_losing_success(
    tmp_path: Path,
) -> None:
    store = FileEvidenceStore(tmp_path)
    success = SourceRun(
        source_id="openfda_drug_ndc",
        run_type="manual",
        status="succeeded",
        finished_at=datetime.now(UTC),
        documents_seen=1,
        documents_created=1,
        idempotency_key="success",
    )
    failure = SourceRun(
        source_id="openfda_drug_ndc",
        run_type="manual",
        status="failed",
        finished_at=datetime.now(UTC),
        error_count=1,
        idempotency_key="failure",
    )

    store.write_source_run(success)
    store.write_source_run(failure)

    health = _read_jsonl(tmp_path / "source_health.jsonl")
    assert len(health) == 1
    assert health[0]["status"] == "failing"
    assert health[0]["last_success_at"] == success.finished_at.isoformat().replace("+00:00", "Z")
    assert health[0]["last_failure_at"]
    assert health[0]["consecutive_failures"] == 1
    assert health[0]["metrics"]["error_count"] == 1


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
