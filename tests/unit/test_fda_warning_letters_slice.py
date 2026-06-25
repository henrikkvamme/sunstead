import json
from pathlib import Path

from supply_intel.pipeline import ingest_fda_warning_letters_fixture
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config

EXPECTED_WARNING_LETTER_ROWS = 2
EXPECTED_WARNING_LETTER_ENTITIES = 4
EXPECTED_WARNING_LETTER_GRAPH_NODES = 6
EXPECTED_WARNING_LETTER_GRAPH_NODE_EVENTS = 5
EXPECTED_WARNING_LETTER_GRAPH_RELATIONSHIPS = 4


def test_fda_warning_letters_fixture_creates_regulatory_notice_graph(
    tmp_path: Path,
) -> None:
    config = load_source_config(Path("sources/fda_warning_letters.yaml"))
    settings = Settings(data_dir=tmp_path)

    stats = ingest_fda_warning_letters_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/fda_warning_letters/success.csv"),
        settings=settings,
        max_documents=1,
    )

    assert stats["raw_documents_created"] == 1
    assert stats["chunks_created"] == EXPECTED_WARNING_LETTER_ROWS
    assert stats["regulatory_events"] == EXPECTED_WARNING_LETTER_ROWS
    assert stats["entities_resolved"] == EXPECTED_WARNING_LETTER_ENTITIES
    assert stats["graph_nodes"] == EXPECTED_WARNING_LETTER_GRAPH_NODES
    assert stats["graph_relationships"] == EXPECTED_WARNING_LETTER_GRAPH_RELATIONSHIPS
    assert stats["human_review_tasks"] == EXPECTED_WARNING_LETTER_ROWS

    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    nodes = _read_jsonl(tmp_path / "graph_node_upserts.jsonl")
    relationships = _read_jsonl(tmp_path / "graph_relationship_upserts.jsonl")
    feedback = _read_jsonl(tmp_path / "human_feedback.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")

    assert len(extraction_runs) == EXPECTED_WARNING_LETTER_ROWS
    assert all(run["validated_output"]["regulatory_events"] for run in extraction_runs)
    assert {
        run["validated_output"]["regulatory_events"][0]["event_type"] for run in extraction_runs
    } == {"fda_warning_letter"}
    assert {tuple(row["labels"]) for row in nodes} >= {
        ("RegulatoryNotice",),
        ("Manufacturer",),
        ("RegulatoryAgency",),
    }
    assert {row["relationship_type"] for row in relationships} == {"ISSUED_BY", "ISSUED_TO"}
    assert all(row["properties"]["evidence_span_id"] for row in relationships)
    assert all(row["properties"]["extraction_run_id"] for row in relationships)
    assert len(feedback) == EXPECTED_WARNING_LETTER_ROWS
    assert {row["feedback_type"] for row in feedback} == {"review_requested"}
    assert {row["decision"] for row in feedback} == {"pending"}

    event_types = [event["event_type"] for event in events]
    assert event_types.count("ingest.raw_document_created") == 1
    assert event_types.count("ingest.document_parsed") == 1
    assert event_types.count("ingest.extraction_completed") == EXPECTED_WARNING_LETTER_ROWS
    assert event_types.count("graph.node_upsert") == EXPECTED_WARNING_LETTER_GRAPH_NODE_EVENTS
    assert (
        event_types.count("graph.relationship_upsert")
        == EXPECTED_WARNING_LETTER_GRAPH_RELATIONSHIPS
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
