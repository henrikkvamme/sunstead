import json
from pathlib import Path

from supply_intel.pipeline import ingest_eia_energy_prices_fixture
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config

EXPECTED_PRICE_OBSERVATIONS = 3


def test_eia_energy_prices_fixture_creates_price_observation_graph(
    tmp_path: Path,
) -> None:
    config = load_source_config(Path("sources/eia_energy_prices.yaml"))
    settings = Settings(data_dir=tmp_path)

    stats = ingest_eia_energy_prices_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/eia_energy_prices/success.json"),
        settings=settings,
        max_documents=1,
    )

    assert stats["raw_documents_created"] == 1
    assert stats["chunks_created"] == EXPECTED_PRICE_OBSERVATIONS
    assert stats["price_observations"] == EXPECTED_PRICE_OBSERVATIONS
    assert stats["graph_nodes"] == EXPECTED_PRICE_OBSERVATIONS
    assert stats["graph_relationships"] == 0

    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    nodes = _read_jsonl(tmp_path / "graph_node_upserts.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")

    assert len(extraction_runs) == EXPECTED_PRICE_OBSERVATIONS
    observations = [run["validated_output"]["price_observations"][0] for run in extraction_runs]
    assert {observation["commodity_name"] for observation in observations} == {
        "No 2 Diesel, U.S.",
    }
    assert {observation["currency"] for observation in observations} == {"USD"}
    assert {observation["unit"] for observation in observations} == {"USD/gal"}
    assert all(observation["observed_at"].startswith("2026-06-") for observation in observations)
    assert all(observation["evidence"][0]["extraction_run_id"] for observation in observations)
    assert {observation["attributes"]["product_code"] for observation in observations} == {"EPD2D"}
    assert {observation["attributes"]["area_code"] for observation in observations} == {"NUS"}
    assert {observation["attributes"]["series_description"] for observation in observations} == {
        "U.S. No 2 Diesel Retail Prices",
    }

    assert {tuple(row["labels"]) for row in nodes} == {("PriceObservation",)}
    assert all(row["evidence_span_id"] for row in nodes)
    assert all(row["extraction_run_id"] for row in nodes)
    assert {row["properties"]["currency"] for row in nodes} == {"USD"}
    assert {row["properties"]["attributes"]["raw_unit"] for row in nodes} == {"$/GAL"}

    event_type_names = [event["event_type"] for event in events]
    assert event_type_names.count("ingest.raw_document_created") == 1
    assert event_type_names.count("ingest.document_parsed") == 1
    assert event_type_names.count("ingest.extraction_completed") == EXPECTED_PRICE_OBSERVATIONS
    assert event_type_names.count("graph.node_upsert") == EXPECTED_PRICE_OBSERVATIONS
    assert event_type_names.count("graph.relationship_upsert") == 0


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
