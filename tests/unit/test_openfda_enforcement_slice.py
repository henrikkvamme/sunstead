import json
from pathlib import Path

from supply_intel.pipeline import ingest_openfda_drug_enforcement_fixture
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config

EXPECTED_RECALL_EVENTS = 1
EXPECTED_RISK_CASES = 1
EXPECTED_RISK_ALERTS = 1
EXPECTED_GRAPH_NODES = 3
EXPECTED_GRAPH_RELATIONSHIPS = 2
EXPECTED_RISK_FEATURE_SNAPSHOTS = 3


def test_openfda_enforcement_fixture_creates_recall_risk_case(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/openfda_drug_enforcement.yaml"))
    settings = Settings(data_dir=tmp_path)

    stats = ingest_openfda_drug_enforcement_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_enforcement/success.json"),
        settings=settings,
        max_documents=1,
    )

    assert stats["raw_documents_created"] == 1
    assert stats["recall_events"] == EXPECTED_RECALL_EVENTS
    assert stats["risk_candidates"] == EXPECTED_RISK_CASES
    assert stats["risk_cases"] == EXPECTED_RISK_CASES
    assert stats["risk_alerts"] == EXPECTED_RISK_ALERTS
    assert stats["risk_feature_snapshots"] == EXPECTED_RISK_FEATURE_SNAPSHOTS
    assert stats["graph_relationships"] >= 1

    candidates = [
        json.loads(line)
        for line in (tmp_path / "risk_candidates.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    cases = [
        json.loads(line)
        for line in (tmp_path / "risk_cases.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    verdicts = [
        json.loads(line)
        for line in (tmp_path / "risk_verdicts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    feature_snapshots = [
        json.loads(line)
        for line in (tmp_path / "risk_feature_snapshots.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert candidates[0]["risk_type"] == "recall_quality"
    assert candidates[0]["candidate_key"].startswith("risk_candidate:recall_quality:")
    assert candidates[0]["evidence_span_ids"] == verdicts[0]["evidence_span_ids"]
    assert cases[0]["risk_type"] == "recall_quality"
    assert cases[0]["component_scores"]["evidence_confidence"] > 0
    assert verdicts[0]["evidence_span_ids"]
    assert {row["feature_name"] for row in feature_snapshots} == {
        "affected_relationships",
        "evidence_confidence",
        "recall_classification",
    }
    assert all(
        row["evidence_span_ids"] == verdicts[0]["evidence_span_ids"] for row in feature_snapshots
    )
    assert "not medical advice" in " ".join(verdicts[0]["limitations"])

    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    event_types = [event["event_type"] for event in events]
    assert event_types.count("graph.node_upsert") == EXPECTED_GRAPH_NODES
    assert event_types.count("graph.relationship_upsert") == EXPECTED_GRAPH_RELATIONSHIPS
    assert event_types.count("risk.candidates") == EXPECTED_RISK_CASES
    assert event_types.count("risk.case_created") == EXPECTED_RISK_CASES
    assert event_types.count("risk.verdicts") == EXPECTED_RISK_CASES
    assert event_types.count("risk.alerts") == EXPECTED_RISK_ALERTS
    risk_case_event = next(event for event in events if event["event_type"] == "risk.case_created")
    assert risk_case_event["payload"]["evidence_span_ids"] == verdicts[0]["evidence_span_ids"]
    assert risk_case_event["payload"]["case_key"] == cases[0]["case_key"]


def test_openfda_enforcement_graph_edges_carry_evidence_span(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/openfda_drug_enforcement.yaml"))
    settings = Settings(data_dir=tmp_path)

    ingest_openfda_drug_enforcement_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_enforcement/success.json"),
        settings=settings,
        max_documents=1,
    )

    relationships = [
        json.loads(line)
        for line in (tmp_path / "graph_relationship_upserts.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert relationships
    assert all(row["properties"]["evidence_span_id"] for row in relationships)
    assert {row["relationship_type"] for row in relationships} >= {"AFFECTS", "INVOLVES"}
