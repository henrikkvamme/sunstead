import json
from typing import Any
from uuid import uuid4

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.entity_resolution.service import HumanReviewTask


class FakePostgresConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.closed = False

    async def fetch(self, query: str, *args: object) -> list[dict[str, Any]]:
        assert "FROM human_review_queue" in query
        assert args == ("open",)
        return self.rows

    async def fetchrow(self, query: str, *args: object) -> dict[str, Any] | None:
        del query, args
        return None

    async def execute(self, query: str, *args: object) -> str:
        del query, args
        return "OK"

    async def close(self) -> None:
        self.closed = True


def test_query_human_reviews_lists_local_open_tasks(tmp_path) -> None:
    task = HumanReviewTask(
        target_table="canonical_entities",
        target_id=uuid4(),
        review_type="low_confidence",
        reason="High-impact Manufacturer entity confidence 0.75 is below 0.88.",
        priority="P1",
        evidence_span_ids=[uuid4()],
    )
    store = FileEvidenceStore(tmp_path)
    store.write_human_review_task(task)

    result = CliRunner().invoke(
        app,
        ["query-human-reviews", "--data-dir", str(tmp_path), "--status", "open"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload == [
        {
            "id": str(task.id),
            "target_table": "canonical_entities",
            "target_id": str(task.target_id),
            "review_type": "low_confidence",
            "reason": "High-impact Manufacturer entity confidence 0.75 is below 0.88.",
            "status": "open",
            "priority": "P1",
            "evidence_span_ids": [str(task.evidence_span_ids[0])],
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        }
    ]


def test_query_human_reviews_reads_postgres_backend(monkeypatch) -> None:
    task = HumanReviewTask(
        target_table="canonical_entities",
        target_id=uuid4(),
        review_type="low_confidence",
        reason="Review cloud task.",
        priority="P1",
        evidence_span_ids=[uuid4()],
    )
    connection = FakePostgresConnection([task.model_dump(mode="python")])

    async def fake_connect_postgres(settings):
        del settings
        return connection

    monkeypatch.setattr("supply_intel.cli.connect_postgres", fake_connect_postgres)

    result = CliRunner().invoke(
        app,
        ["query-human-reviews", "--backend", "postgres", "--status", "open"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert [row["id"] for row in payload] == [str(task.id)]
    assert payload[0]["status"] == "open"
    assert connection.closed is True


def test_record_human_feedback_resolves_task_and_writes_audit(tmp_path) -> None:
    task = HumanReviewTask(
        target_table="canonical_entities",
        target_id=uuid4(),
        review_type="low_confidence",
        reason="High-impact Supplier entity confidence 0.70 is below 0.88.",
        priority="P1",
        evidence_span_ids=[uuid4()],
    )
    store = FileEvidenceStore(tmp_path)
    store.write_human_review_task(task)

    result = CliRunner().invoke(
        app,
        [
            "record-human-feedback",
            str(task.id),
            "--decision",
            "approve_match",
            "--reviewer",
            "unit-test",
            "--comment",
            "Official identifier confirms the match.",
            "--data-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["review_task_id"] == str(task.id)
    assert payload["decision"] == "approve_match"
    assert payload["reviewer"] == "unit-test"
    assert payload["feedback_inserted"] is True
    assert payload["status"] == "resolved"

    review_rows = _read_jsonl(tmp_path / "human_review_queue.jsonl")
    feedback_rows = _read_jsonl(tmp_path / "human_feedback.jsonl")
    assert review_rows[0]["status"] == "resolved"
    assert [row["feedback_type"] for row in feedback_rows] == [
        "review_requested",
        "review_decision",
    ]
    decision = feedback_rows[1]
    assert decision["decision"] == "approve_match"
    assert decision["reviewer"] == "unit-test"
    assert decision["comment"] == "Official identifier confirms the match."
    assert decision["before_value"]["status"] == "open"
    assert decision["after_value"]["status"] == "resolved"
    assert decision["metadata"]["human_review_task_id"] == str(task.id)
    assert decision["metadata"]["evidence_span_ids"] == [str(task.evidence_span_ids[0])]


def _read_jsonl(path):
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
