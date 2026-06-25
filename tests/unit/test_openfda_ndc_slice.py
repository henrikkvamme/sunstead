import json
from pathlib import Path

from supply_intel.pipeline import ingest_openfda_ndc_fixture
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config

EXPECTED_ENTITY_COUNT = 4
EXPECTED_RELATIONSHIP_COUNT = 3
EXPECTED_BASE_EVENT_COUNT = 3


def test_openfda_ndc_fixture_runs_raw_first_slice(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    settings = Settings(data_dir=tmp_path)

    stats = ingest_openfda_ndc_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_ndc/success.json"),
        settings=settings,
        max_documents=1,
    )

    assert stats["raw_documents_created"] == 1
    assert stats["chunks_created"] == 1
    assert stats["entities_resolved"] == EXPECTED_ENTITY_COUNT
    assert stats["graph_nodes"] == EXPECTED_ENTITY_COUNT
    assert stats["graph_relationships"] == EXPECTED_RELATIONSHIP_COUNT
    assert (tmp_path / "raw_documents.jsonl").exists()
    assert (tmp_path / "graph_relationship_upserts.jsonl").exists()

    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    event_types = [event["event_type"] for event in events]
    assert event_types[:EXPECTED_BASE_EVENT_COUNT] == [
        "ingest.raw_document_created",
        "ingest.document_parsed",
        "ingest.extraction_completed",
    ]
    assert event_types.count("graph.node_upsert") == EXPECTED_ENTITY_COUNT
    assert event_types.count("graph.relationship_upsert") == EXPECTED_RELATIONSHIP_COUNT
    assert events[0]["trace"]["source_run_id"] == events[1]["trace"]["source_run_id"]
    assert events[0]["trace"]["raw_document_id"] == events[2]["trace"]["raw_document_id"]
    assert all(event["correlation_id"] == events[0]["correlation_id"] for event in events)
