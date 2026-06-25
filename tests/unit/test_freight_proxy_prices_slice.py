import json
from pathlib import Path

from supply_intel.pipeline import ingest_freight_proxy_prices_fixture
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config

EXPECTED_GSCPI_VALUE = 0.452


def test_freight_proxy_prices_fixture_creates_logistics_pressure_graph(
    tmp_path: Path,
) -> None:
    config = load_source_config(Path("sources/freight_proxy_prices.yaml"))
    settings = Settings(data_dir=tmp_path)

    stats = ingest_freight_proxy_prices_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/freight_proxy_prices/success.csv"),
        settings=settings,
        max_documents=1,
    )

    assert stats["raw_documents_created"] == 1
    assert stats["chunks_created"] == 1
    assert stats["logistics_pressure_observations"] == 1
    assert stats["graph_nodes"] == 1
    assert stats["graph_relationships"] == 0

    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    nodes = _read_jsonl(tmp_path / "graph_node_upserts.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")

    assert len(extraction_runs) == 1
    observation = extraction_runs[0]["validated_output"]["logistics_pressure_observations"][0]
    assert observation["index_name"] == "New York Fed Global Supply Chain Pressure Index"
    assert observation["observed_at"].startswith("2026-05-31")
    assert observation["value"] == EXPECTED_GSCPI_VALUE
    assert observation["unit"] == "standard_deviations_from_average"
    assert observation["attributes"]["latest_vintage_serial"] == "46174"
    assert observation["attributes"]["latest_vintage_date"] == "2026-06-01"
    assert observation["evidence"][0]["extraction_run_id"]

    assert {tuple(row["labels"]) for row in nodes} == {("LogisticsPressureObservation",)}
    assert all(row["evidence_span_id"] for row in nodes)
    assert all(row["extraction_run_id"] for row in nodes)
    assert {row["properties"]["value"] for row in nodes} == {EXPECTED_GSCPI_VALUE}
    assert {row["properties"]["attributes"]["source_series"] for row in nodes} == {"GSCPI"}

    event_type_names = [event["event_type"] for event in events]
    assert event_type_names.count("ingest.raw_document_created") == 1
    assert event_type_names.count("ingest.document_parsed") == 1
    assert event_type_names.count("ingest.extraction_completed") == 1
    assert event_type_names.count("graph.node_upsert") == 1
    assert event_type_names.count("graph.relationship_upsert") == 0


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
