import json
from pathlib import Path
from uuid import uuid4

from supply_intel.models.source import RawDocument
from supply_intel.pipeline import ingest_sec_edgar_supplier_filings_fixture
from supply_intel.settings import Settings
from supply_intel.sources.parsers.sec_edgar import parse_sec_edgar_supplier_filings_document
from supply_intel.sources.registry import load_source_config

EXPECTED_FILINGS = 3
EXPECTED_MAX_RECORD_CHUNKS = 2
EXPECTED_UNIQUE_GRAPH_NODE_EVENTS = 5


def test_sec_edgar_parser_respects_max_records() -> None:
    payload = Path("tests/fixtures/sources/sec_edgar_supplier_filings/success.json").read_text(
        encoding="utf-8"
    )
    document = RawDocument(
        source_id="sec_edgar_supplier_filings",
        source_run_id=uuid4(),
        source_url="https://data.sec.gov/submissions/CIK0000078003.json",
        content_hash="fixture",
        payload_text=payload,
        dedupe_key="fixture",
    )

    chunks = parse_sec_edgar_supplier_filings_document(
        document,
        max_records=EXPECTED_MAX_RECORD_CHUNKS,
    )

    assert len(chunks) == EXPECTED_MAX_RECORD_CHUNKS
    assert [chunk.structured_data["accession_number"] for chunk in chunks] == [
        "0000078003-26-000045",
        "0000078003-26-000032",
    ]


def test_sec_edgar_supplier_filings_fixture_creates_regulatory_graph(
    tmp_path: Path,
) -> None:
    config = load_source_config(Path("sources/sec_edgar_supplier_filings.yaml"))
    settings = Settings(data_dir=tmp_path)

    stats = ingest_sec_edgar_supplier_filings_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/sec_edgar_supplier_filings/success.json"),
        settings=settings,
        max_documents=1,
    )

    assert stats["raw_documents_created"] == 1
    assert stats["chunks_created"] == EXPECTED_FILINGS
    assert stats["regulatory_events"] == EXPECTED_FILINGS
    assert stats["graph_nodes"] == EXPECTED_FILINGS * 3
    assert stats["graph_relationships"] == EXPECTED_FILINGS * 2

    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    nodes = _read_jsonl(tmp_path / "graph_node_upserts.jsonl")
    relationships = _read_jsonl(tmp_path / "graph_relationship_upserts.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")

    assert len(extraction_runs) == EXPECTED_FILINGS
    regulatory_events = [
        event for run in extraction_runs for event in run["validated_output"]["regulatory_events"]
    ]
    assert {event["attributes"]["form"] for event in regulatory_events} == {
        "10-K",
        "10-Q",
        "8-K",
    }
    assert {event["agency"] for event in regulatory_events} == {"SEC"}
    assert all(event["evidence"][0]["extraction_run_id"] for event in regulatory_events)
    assert all(
        str(event["evidence"][0]["source_url"]).startswith(
            "https://www.sec.gov/Archives/edgar/data/78003/"
        )
        for event in regulatory_events
    )

    entities = [entity for run in extraction_runs for entity in run["validated_output"]["entities"]]
    supplier_entities = [entity for entity in entities if entity["entity_type"] == "Supplier"]
    assert len(supplier_entities) == EXPECTED_FILINGS
    assert {entity["name"] for entity in supplier_entities} == {"PFIZER INC"}
    assert {entity["external_ids"]["sec_cik"] for entity in supplier_entities} == {
        "0000078003",
    }
    assert all(entity["needs_review"] for entity in supplier_entities)

    label_counts = _label_counts(nodes)
    assert label_counts[("RegulatoryNotice",)] == EXPECTED_FILINGS
    assert label_counts[("Supplier",)] == EXPECTED_FILINGS
    assert label_counts[("RegulatoryAgency",)] == EXPECTED_FILINGS
    assert all(row["evidence_span_id"] for row in nodes)
    assert all(row["extraction_run_id"] for row in nodes)

    relationship_types = [relationship["relationship_type"] for relationship in relationships]
    assert relationship_types.count("FILED_BY") == EXPECTED_FILINGS
    assert relationship_types.count("FILED_WITH") == EXPECTED_FILINGS

    event_type_names = [event["event_type"] for event in events]
    assert event_type_names.count("ingest.raw_document_created") == 1
    assert event_type_names.count("ingest.document_parsed") == 1
    assert event_type_names.count("ingest.extraction_completed") == EXPECTED_FILINGS
    assert event_type_names.count("graph.node_upsert") == EXPECTED_UNIQUE_GRAPH_NODE_EVENTS
    assert event_type_names.count("graph.relationship_upsert") == EXPECTED_FILINGS * 2


def _label_counts(rows: list[dict[str, object]]) -> dict[tuple[str, ...], int]:
    counts: dict[tuple[str, ...], int] = {}
    for row in rows:
        labels = tuple(str(label) for label in row["labels"])
        counts[labels] = counts.get(labels, 0) + 1
    return counts


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
