import json
from pathlib import Path

from supply_intel.pipeline import ingest_openfda_drug_enforcement_fixture
from supply_intel.risk.explain import explain_case_from_store
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config


def test_explain_case_reconstructs_risk_from_local_evidence_store(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/openfda_drug_enforcement.yaml"))
    settings = Settings(data_dir=tmp_path)
    ingest_openfda_drug_enforcement_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_enforcement/success.json"),
        settings=settings,
        max_documents=1,
    )
    case = json.loads((tmp_path / "risk_cases.jsonl").read_text(encoding="utf-8").splitlines()[0])

    explanation = explain_case_from_store(tmp_path, str(case["case_key"]))

    assert explanation.found is True
    assert explanation.risk_case is not None
    assert explanation.risk_case["case_key"] == case["case_key"]
    assert explanation.latest_verdict is not None
    assert explanation.component_values["evidence_confidence"] > 0
    assert explanation.confidence["risk_case_confidence"] == case["confidence"]
    assert explanation.evidence_spans
    assert explanation.source_documents
    assert explanation.graph_paths
    assert "not medical advice" in " ".join(explanation.limitations)


def test_explain_case_reports_missing_case(tmp_path: Path) -> None:
    explanation = explain_case_from_store(tmp_path, "risk:missing")

    assert explanation.found is False
    assert explanation.risk_case is None
    assert explanation.unresolved_conflicts == [
        "No stored risk case matched the requested case_key."
    ]
