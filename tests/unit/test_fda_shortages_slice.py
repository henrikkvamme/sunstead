import json
from pathlib import Path
from uuid import uuid4

from supply_intel.models.source import RawDocument
from supply_intel.pipeline import ingest_fda_drug_shortages_fixture
from supply_intel.risk.engine import run_local_risk_engine
from supply_intel.settings import Settings
from supply_intel.sources.parsers.fda_shortages import parse_fda_drug_shortages_document
from supply_intel.sources.registry import load_source_config

EXPECTED_ENTITY_COUNT = 2
EXPECTED_GRAPH_NODE_COUNT = 3
EXPECTED_GRAPH_RELATIONSHIP_COUNT = 3
EXPECTED_RISK_EVENTS = 4
EXPECTED_RISK_FEATURE_SNAPSHOTS = 3


def test_fda_shortages_fixture_creates_shortage_risk_case(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/fda_drug_shortages.yaml"))
    settings = Settings(data_dir=tmp_path)

    stats = ingest_fda_drug_shortages_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/fda_drug_shortages/success.html"),
        settings=settings,
        max_documents=1,
    )

    assert stats["raw_documents_created"] == 1
    assert stats["chunks_created"] == 1
    assert stats["shortage_events"] == 1
    assert stats["entities_resolved"] == EXPECTED_ENTITY_COUNT
    assert stats["graph_nodes"] == EXPECTED_GRAPH_NODE_COUNT
    assert stats["graph_relationships"] == EXPECTED_GRAPH_RELATIONSHIP_COUNT
    assert stats["risk_cases"] == 1
    assert stats["risk_candidates"] == 1
    assert stats["risk_alerts"] == 1
    assert stats["risk_feature_snapshots"] == EXPECTED_RISK_FEATURE_SNAPSHOTS
    assert stats["human_review_tasks"] == 1

    candidates = _read_jsonl(tmp_path / "risk_candidates.jsonl")
    cases = _read_jsonl(tmp_path / "risk_cases.jsonl")
    verdicts = _read_jsonl(tmp_path / "risk_verdicts.jsonl")
    feature_snapshots = _read_jsonl(tmp_path / "risk_feature_snapshots.jsonl")
    nodes = _read_jsonl(tmp_path / "graph_node_upserts.jsonl")
    relationships = _read_jsonl(tmp_path / "graph_relationship_upserts.jsonl")
    feedback = _read_jsonl(tmp_path / "human_feedback.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")
    assert candidates[0]["risk_type"] == "shortage"
    assert candidates[0]["candidate_key"].startswith("risk_candidate:shortage:")
    assert candidates[0]["evidence_span_ids"] == verdicts[0]["evidence_span_ids"]
    assert cases[0]["risk_type"] == "shortage"
    assert cases[0]["case_key"].startswith("risk:shortage:Shortage:fda:")
    assert verdicts[0]["evidence_span_ids"]
    assert {row["feature_name"] for row in feature_snapshots} == {
        "affected_relationships",
        "evidence_confidence",
        "shortage_status",
    }
    assert {tuple(row["labels"]) for row in nodes} >= {("Shortage",), ("Drug",), ("Manufacturer",)}
    assert {row["relationship_type"] for row in relationships} == {
        "AFFECTS",
        "INVOLVES",
        "MARKETS",
    }
    assert all(row["properties"]["evidence_span_id"] for row in relationships)
    assert feedback[0]["feedback_type"] == "review_requested"
    assert feedback[0]["decision"] == "pending"
    assert [event["event_type"] for event in events if event["event_type"].startswith("risk.")] == [
        "risk.candidates",
        "risk.case_created",
        "risk.verdicts",
        "risk.alerts",
    ]


def test_fda_shortages_parser_handles_live_generic_name_header() -> None:
    document = RawDocument(
        source_id="fda_drug_shortages",
        source_run_id=uuid4(),
        source_url="https://www.accessdata.fda.gov/scripts/drugshortages/default.cfm",
        content_hash="shortages-live-header",
        dedupe_key="shortages-live-header",
        payload_text="""
        <table>
          <tr>
            <th>Generic Name or Active Ingredient</th>
            <th>Status</th>
          </tr>
          <tr>
            <td>Acetaminophen; Oxycodone Hydrochloride Tablet</td>
            <td>Currently in Shortage</td>
          </tr>
          <tr>
            <td></td>
            <td></td>
          </tr>
        </table>
        """,
    )

    chunks = parse_fda_drug_shortages_document(document)

    assert len(chunks) == 1
    assert chunks[0].structured_data["generic_name"] == (
        "Acetaminophen; Oxycodone Hydrochloride Tablet"
    )
    assert "Generic name: Acetaminophen" in chunks[0].text
    assert chunks[0].text.strip()


def test_local_risk_engine_replays_shortage_extractions_idempotently(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/fda_drug_shortages.yaml"))
    settings = Settings(data_dir=tmp_path)
    ingest_fda_drug_shortages_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/fda_drug_shortages/success.html"),
        settings=settings,
        max_documents=1,
    )
    _remove_inline_risk_outputs(tmp_path)

    first = run_local_risk_engine(tmp_path)
    second = run_local_risk_engine(tmp_path)

    assert first.extraction_runs_scanned == 1
    assert first.shortage_events_seen == 1
    assert first.risk_candidates_created == 1
    assert first.risk_cases_created == 1
    assert first.risk_verdicts_created == 1
    assert first.risk_alerts_created == 1
    assert first.risk_feature_snapshots_created == EXPECTED_RISK_FEATURE_SNAPSHOTS
    assert first.events_emitted == EXPECTED_RISK_EVENTS
    assert second.risk_candidates_created == 0
    assert second.risk_candidates_existing == 1
    assert second.risk_cases_created == 0
    assert second.risk_cases_existing == 1
    assert second.risk_verdicts_created == 0
    assert second.risk_alerts_created == 0
    assert second.risk_feature_snapshots_created == 0
    assert second.events_emitted == 0


def _remove_inline_risk_outputs(data_dir: Path) -> None:
    for name in [
        "risk_cases.jsonl",
        "risk_candidates.jsonl",
        "risk_verdicts.jsonl",
        "risk_alerts.jsonl",
        "risk_feature_snapshots.jsonl",
    ]:
        path = data_dir / name
        if path.exists():
            path.unlink()
    events_path = data_dir / "events.jsonl"
    events = [
        line
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if not json.loads(line)["event_type"].startswith("risk.")
    ]
    events_path.write_text("\n".join(events) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
