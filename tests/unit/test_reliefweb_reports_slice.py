import json
from pathlib import Path

from supply_intel.pipeline import ingest_reliefweb_reports_fixture
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config

EXPECTED_RELIEFWEB_REPORTS = 2


def test_reliefweb_reports_fixture_creates_unverified_news_event_graph(
    tmp_path: Path,
) -> None:
    config = load_source_config(Path("sources/reliefweb_reports.yaml"))
    settings = Settings(data_dir=tmp_path)

    stats = ingest_reliefweb_reports_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/reliefweb_reports/success.json"),
        settings=settings,
        max_documents=1,
    )

    assert stats["raw_documents_created"] == 1
    assert stats["chunks_created"] == EXPECTED_RELIEFWEB_REPORTS
    assert stats["news_events"] == EXPECTED_RELIEFWEB_REPORTS
    assert stats["graph_nodes"] == EXPECTED_RELIEFWEB_REPORTS
    assert stats["graph_relationships"] == 0

    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    nodes = _read_jsonl(tmp_path / "graph_node_upserts.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")

    assert len(extraction_runs) == EXPECTED_RELIEFWEB_REPORTS
    news_events = [run["validated_output"]["news_events"][0] for run in extraction_runs]
    assert {event["event_status"] for event in news_events} == {"unverified"}
    assert all(event["observed_at"] for event in news_events)
    assert {event["attributes"]["reliefweb_id"] for event in news_events} == {
        "4110001",
        "4110002",
    }
    assert {event["attributes"]["source_shortnames"][0] for event in news_events} == {
        "EHLC",
        "EHEO",
    }
    assert all("Health" in event["attributes"]["themes"] for event in news_events)
    assert all(event["evidence"][0]["extraction_run_id"] for event in news_events)

    assert {tuple(row["labels"]) for row in nodes} == {("NewsEvent",)}
    assert all(row["evidence_span_id"] for row in nodes)
    assert all(row["extraction_run_id"] for row in nodes)
    assert {row["properties"]["event_status"] for row in nodes} == {"unverified"}
    assert {row["properties"]["attributes"]["reliefweb_id"] for row in nodes} == {
        "4110001",
        "4110002",
    }

    event_type_names = [event["event_type"] for event in events]
    assert event_type_names.count("ingest.raw_document_created") == 1
    assert event_type_names.count("ingest.document_parsed") == 1
    assert event_type_names.count("ingest.extraction_completed") == EXPECTED_RELIEFWEB_REPORTS
    assert event_type_names.count("graph.node_upsert") == EXPECTED_RELIEFWEB_REPORTS
    assert event_type_names.count("graph.relationship_upsert") == 0


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
