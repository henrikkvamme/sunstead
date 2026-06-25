import json
from datetime import UTC, datetime
from pathlib import Path

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.models.source import SourceCursor
from supply_intel.sources.scheduler import source_cursor_snapshot


def test_file_store_upserts_source_cursor(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    first = SourceCursor(
        source_id="openfda_drug_ndc",
        cursor_state={"skip": 0},
        watermark=datetime(2026, 6, 24, tzinfo=UTC),
        etag='"v1"',
    )
    second = SourceCursor(
        source_id="openfda_drug_ndc",
        cursor_state={"skip": 1000},
        watermark=datetime(2026, 6, 25, tzinfo=UTC),
        etag='"v2"',
    )

    assert store.write_source_cursor(first) is True
    assert store.write_source_cursor(second) is False

    current = store.current_source_cursor("openfda_drug_ndc")
    assert current is not None
    assert current.cursor_state == {"skip": 1000}
    assert current.etag == '"v2"'
    rows = _read_jsonl(tmp_path / "source_cursors.jsonl")
    assert len(rows) == 1
    assert rows[0]["cursor_state"] == {"skip": 1000}


def test_source_cursor_snapshot_is_job_payload_safe() -> None:
    cursor = SourceCursor(
        source_id="openfda_drug_ndc",
        cursor_state={"skip": 1000},
        watermark=datetime(2026, 6, 24, tzinfo=UTC),
        etag='"v1"',
        last_content_hash="hash-1",
    )

    snapshot = source_cursor_snapshot(cursor)

    assert snapshot == {
        "source_id": "openfda_drug_ndc",
        "cursor_name": "default",
        "cursor_state": {"skip": 1000},
        "watermark": "2026-06-24T00:00:00Z",
        "etag": '"v1"',
        "last_content_hash": "hash-1",
        "updated_by_run_id": None,
    }


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
