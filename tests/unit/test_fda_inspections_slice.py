import json
from pathlib import Path

from supply_intel.pipeline import ingest_fda_inspections_dashboard_fixture
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config

EXPECTED_INSPECTION_ROWS = 3
EXPECTED_INSPECTION_ENTITIES = 9
EXPECTED_INSPECTION_GRAPH_NODES = 12
EXPECTED_INSPECTION_GRAPH_NODE_EVENTS = 6
EXPECTED_INSPECTION_GRAPH_RELATIONSHIPS = 6


def test_fda_inspections_fixture_creates_regulatory_notice_graph(
    tmp_path: Path,
) -> None:
    config = load_source_config(Path("sources/fda_inspections_dashboard.yaml"))
    settings = Settings(data_dir=tmp_path)

    stats = ingest_fda_inspections_dashboard_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/fda_inspections_dashboard/success.csv"),
        settings=settings,
        max_documents=1,
    )

    assert stats["raw_documents_created"] == 1
    assert stats["chunks_created"] == EXPECTED_INSPECTION_ROWS
    assert stats["regulatory_events"] == EXPECTED_INSPECTION_ROWS
    assert stats["entities_resolved"] == EXPECTED_INSPECTION_ENTITIES
    assert stats["graph_nodes"] == EXPECTED_INSPECTION_GRAPH_NODES
    assert stats["graph_relationships"] == EXPECTED_INSPECTION_GRAPH_RELATIONSHIPS
    assert stats["human_review_tasks"] == 1

    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    nodes = _read_jsonl(tmp_path / "graph_node_upserts.jsonl")
    relationships = _read_jsonl(tmp_path / "graph_relationship_upserts.jsonl")
    feedback = _read_jsonl(tmp_path / "human_feedback.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")

    assert len(extraction_runs) == EXPECTED_INSPECTION_ROWS
    event_types = {
        run["validated_output"]["regulatory_events"][0]["event_type"] for run in extraction_runs
    }
    assert event_types == {
        "fda_inspection_classification",
        "fda_inspection_citation",
        "fda_published_483",
    }
    assert {tuple(row["labels"]) for row in nodes} >= {
        ("RegulatoryNotice",),
        ("Manufacturer",),
        ("Facility",),
        ("RegulatoryAgency",),
    }
    facility_nodes = [row for row in nodes if row["labels"] == ["Facility"]]
    assert facility_nodes
    assert {row["properties"]["external_ids"].get("fei_number") for row in facility_nodes} == {
        "3012345678"
    }
    assert {row["relationship_type"] for row in relationships} == {"ISSUED_BY", "ISSUED_TO"}
    assert all(row["properties"]["evidence_span_id"] for row in relationships)
    assert all(row["properties"]["extraction_run_id"] for row in relationships)
    assert len(feedback) == 1
    assert feedback[0]["feedback_type"] == "review_requested"
    assert feedback[0]["decision"] == "pending"

    event_type_names = [event["event_type"] for event in events]
    assert event_type_names.count("ingest.raw_document_created") == 1
    assert event_type_names.count("ingest.document_parsed") == 1
    assert event_type_names.count("ingest.extraction_completed") == EXPECTED_INSPECTION_ROWS
    assert event_type_names.count("graph.node_upsert") == EXPECTED_INSPECTION_GRAPH_NODE_EVENTS
    assert (
        event_type_names.count("graph.relationship_upsert")
        == EXPECTED_INSPECTION_GRAPH_RELATIONSHIPS
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
