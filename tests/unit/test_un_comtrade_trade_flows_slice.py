import json
from pathlib import Path

from supply_intel.pipeline import ingest_un_comtrade_trade_flows_fixture
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config

EXPECTED_TRADE_FLOWS = 2
EXPECTED_GRAPH_NODE_UPSERTS = EXPECTED_TRADE_FLOWS * 4
EXPECTED_UNIQUE_GRAPH_NODE_EVENTS = 6
EXPECTED_GRAPH_RELATIONSHIPS = EXPECTED_TRADE_FLOWS * 3


def test_un_comtrade_trade_flows_fixture_creates_trade_flow_graph(
    tmp_path: Path,
) -> None:
    config = load_source_config(Path("sources/un_comtrade_trade_flows.yaml"))
    settings = Settings(data_dir=tmp_path)

    stats = ingest_un_comtrade_trade_flows_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/un_comtrade_trade_flows/success.json"),
        settings=settings,
        max_documents=1,
    )

    assert stats["raw_documents_created"] == 1
    assert stats["chunks_created"] == EXPECTED_TRADE_FLOWS
    assert stats["trade_flow_observations"] == EXPECTED_TRADE_FLOWS
    assert stats["graph_nodes"] == EXPECTED_GRAPH_NODE_UPSERTS
    assert stats["graph_relationships"] == EXPECTED_GRAPH_RELATIONSHIPS

    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    nodes = _read_jsonl(tmp_path / "graph_node_upserts.jsonl")
    relationships = _read_jsonl(tmp_path / "graph_relationship_upserts.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")

    assert len(extraction_runs) == EXPECTED_TRADE_FLOWS
    observations = [
        observation
        for run in extraction_runs
        for observation in run["validated_output"]["trade_flow_observations"]
    ]
    assert {observation["commodity_code"] for observation in observations} == {"3004"}
    assert {observation["reporter_name"] for observation in observations} == {"USA"}
    assert {observation["flow"] for observation in observations} == {"Import"}
    assert {observation["primary_value_usd"] for observation in observations} == {
        18400000000.0,
        92500000000.0,
    }
    assert all(observation["evidence"][0]["extraction_run_id"] for observation in observations)
    assert all(observation["attributes"]["source_caveat"] for observation in observations)

    label_counts = _label_counts(nodes)
    assert label_counts[("TradeFlowObservation",)] == EXPECTED_TRADE_FLOWS
    assert label_counts[("Commodity",)] == EXPECTED_TRADE_FLOWS
    assert label_counts[("Country",)] == EXPECTED_TRADE_FLOWS * 2
    assert all(row["evidence_span_id"] for row in nodes)
    assert all(row["extraction_run_id"] for row in nodes)

    relationship_types = [relationship["relationship_type"] for relationship in relationships]
    assert relationship_types.count("OBSERVED_FOR") == EXPECTED_TRADE_FLOWS
    assert relationship_types.count("ABOUT") == EXPECTED_TRADE_FLOWS * 2
    assert all(relationship["properties"]["evidence_span_id"] for relationship in relationships)
    assert all(relationship["properties"]["extraction_run_id"] for relationship in relationships)

    event_type_names = [event["event_type"] for event in events]
    assert event_type_names.count("ingest.raw_document_created") == 1
    assert event_type_names.count("ingest.document_parsed") == 1
    assert event_type_names.count("ingest.extraction_completed") == EXPECTED_TRADE_FLOWS
    assert event_type_names.count("graph.node_upsert") == EXPECTED_UNIQUE_GRAPH_NODE_EVENTS
    assert event_type_names.count("graph.relationship_upsert") == EXPECTED_GRAPH_RELATIONSHIPS


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
