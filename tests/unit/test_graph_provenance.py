import json
from pathlib import Path

from supply_intel.pipeline import ingest_openfda_ndc_fixture
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config


def test_graph_relationships_include_required_provenance(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    settings = Settings(data_dir=tmp_path)

    ingest_openfda_ndc_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_ndc/success.json"),
        settings=settings,
        max_documents=1,
    )

    rows = [
        json.loads(line)
        for line in (tmp_path / "graph_relationship_upserts.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert rows
    properties = rows[0]["properties"]
    assert properties["confidence"] > 0
    assert properties["source_document_id"]
    assert properties["observed_at"]
    assert properties["source_name"] == "openfda_drug_ndc"
    assert properties["method"] == "deterministic_openfda_ndc_v1"
