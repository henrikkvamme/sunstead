import json
from pathlib import Path

from supply_intel.pipeline import ingest_search_trend_signals_fixture
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config

EXPECTED_TREND_VALUES = {0.72, 1.31}
EXPECTED_TREND_OBSERVATIONS = 2


def test_search_trend_signals_fixture_creates_trend_signal_graph(
    tmp_path: Path,
) -> None:
    config = load_source_config(Path("sources/search_trend_signals.yaml"))
    settings = Settings(data_dir=tmp_path)

    stats = ingest_search_trend_signals_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/search_trend_signals/success.json"),
        settings=settings,
        max_documents=1,
    )

    assert stats["raw_documents_created"] == 1
    assert stats["chunks_created"] == EXPECTED_TREND_OBSERVATIONS
    assert stats["trend_signal_observations"] == EXPECTED_TREND_OBSERVATIONS
    assert stats["graph_nodes"] == EXPECTED_TREND_OBSERVATIONS
    assert stats["graph_relationships"] == 0

    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    nodes = _read_jsonl(tmp_path / "graph_node_upserts.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")

    assert len(extraction_runs) == EXPECTED_TREND_OBSERVATIONS
    observations = [
        observation
        for run in extraction_runs
        for observation in run["validated_output"]["trend_signal_observations"]
    ]
    assert {observation["signal_name"] for observation in observations} == {
        "GDELT DOC news volume trend"
    }
    assert {observation["value"] for observation in observations} == EXPECTED_TREND_VALUES
    assert {observation["unit"] for observation in observations} == {"normalized_news_volume"}
    assert {observation["window"] for observation in observations} == {"1d"}
    assert all(observation["query"] for observation in observations)
    assert all(observation["evidence"][0]["extraction_run_id"] for observation in observations)

    assert {tuple(row["labels"]) for row in nodes} == {("TrendSignalObservation",)}
    assert all(row["evidence_span_id"] for row in nodes)
    assert all(row["extraction_run_id"] for row in nodes)
    assert {row["properties"]["value"] for row in nodes} == EXPECTED_TREND_VALUES
    assert {row["properties"]["unit"] for row in nodes} == {"normalized_news_volume"}

    event_type_names = [event["event_type"] for event in events]
    assert event_type_names.count("ingest.raw_document_created") == 1
    assert event_type_names.count("ingest.document_parsed") == 1
    assert event_type_names.count("ingest.extraction_completed") == EXPECTED_TREND_OBSERVATIONS
    assert event_type_names.count("graph.node_upsert") == EXPECTED_TREND_OBSERVATIONS
    assert event_type_names.count("graph.relationship_upsert") == 0


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
