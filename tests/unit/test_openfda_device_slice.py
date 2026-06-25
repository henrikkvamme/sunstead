import json
from pathlib import Path
from uuid import uuid4

from supply_intel.models.source import RawDocument
from supply_intel.pipeline import (
    ingest_openfda_device_enforcement_fixture,
    ingest_openfda_device_registrationlisting_fixture,
)
from supply_intel.settings import Settings
from supply_intel.sources.parsers.openfda_device import (
    parse_openfda_device_registrationlisting_document,
)
from supply_intel.sources.registry import load_source_config

EXPECTED_REGISTRATION_ENTITIES = 4
EXPECTED_REGISTRATION_RELATIONSHIPS = 4
EXPECTED_LIVE_NESTED_PRODUCT_CHUNKS = 2
EXPECTED_ENFORCEMENT_RISK_EVENTS = 4
EXPECTED_ENFORCEMENT_GRAPH_NODES = 3
EXPECTED_ENFORCEMENT_GRAPH_RELATIONSHIPS = 2


def test_openfda_device_registration_parser_normalizes_live_nested_products() -> None:
    document = RawDocument(
        source_id="openfda_device_registrationlisting",
        source_run_id=uuid4(),
        source_url="https://api.fda.gov/device/registrationlisting.json?limit=1&skip=0",
        content_hash="fixture",
        payload_text=json.dumps(
            {
                "establishment_type": ["Contract Manufacturer"],
                "products": [
                    {
                        "created_date": "2024-11-05",
                        "openfda": {
                            "device_class": "1",
                            "device_name": "Accessories, Arthroscopic",
                            "medical_specialty_description": "Orthopedic",
                            "regulation_number": "888.1100",
                        },
                        "owner_operator_number": "9011072",
                        "product_code": "NBH",
                    },
                    {
                        "created_date": "2024-11-05",
                        "openfda": {
                            "device_class": "1",
                            "device_name": "Reamer",
                            "medical_specialty_description": "Orthopedic",
                            "regulation_number": "888.4540",
                        },
                        "owner_operator_number": "9011072",
                        "product_code": "HTO",
                    },
                ],
                "registration": {
                    "address_line_1": "125 W 1000 S",
                    "city": "Smithfield",
                    "fei_number": "1000517406",
                    "iso_country_code": "US",
                    "name": "Paragon Medical Inc.",
                    "owner_operator": {
                        "firm_name": "Paragon Medical",
                        "official_correspondent": {"phone_number": "001-435-5355456-x"},
                        "owner_operator_number": "9011072",
                    },
                    "registration_number": "1000517406",
                    "state_code": "UT",
                },
            },
            sort_keys=True,
        ),
        dedupe_key="fixture",
    )

    chunks = parse_openfda_device_registrationlisting_document(document)

    assert len(chunks) == EXPECTED_LIVE_NESTED_PRODUCT_CHUNKS
    assert [chunk.structured_data["product_code"] for chunk in chunks] == ["NBH", "HTO"]
    assert {chunk.structured_data["registration_number"] for chunk in chunks} == {"1000517406"}
    assert {chunk.structured_data["firm_name"] for chunk in chunks} == {"Paragon Medical Inc."}
    assert all("official_correspondent" not in chunk.structured_data for chunk in chunks)


def test_openfda_device_registrationlisting_fixture_maps_device_supply_graph(
    tmp_path: Path,
) -> None:
    config = load_source_config(Path("sources/openfda_device_registrationlisting.yaml"))
    settings = Settings(data_dir=tmp_path)

    stats = ingest_openfda_device_registrationlisting_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_device_registrationlisting/success.json"),
        settings=settings,
        max_documents=1,
    )

    assert stats["raw_documents_created"] == 1
    assert stats["chunks_created"] == 1
    assert stats["entities_resolved"] == EXPECTED_REGISTRATION_ENTITIES
    assert stats["graph_nodes"] == EXPECTED_REGISTRATION_ENTITIES
    assert stats["graph_relationships"] == EXPECTED_REGISTRATION_RELATIONSHIPS

    nodes = _read_jsonl(tmp_path / "graph_node_upserts.jsonl")
    relationships = _read_jsonl(tmp_path / "graph_relationship_upserts.jsonl")
    labels = {tuple(row["labels"]) for row in nodes}
    relationship_types = {row["relationship_type"] for row in relationships}
    assert labels >= {
        ("MedicalDevice",),
        ("DeviceCategory",),
        ("Manufacturer",),
        ("Facility",),
    }
    assert relationship_types == {
        "BELONGS_TO_CATEGORY",
        "MANUFACTURED_BY",
        "MANUFACTURED_AT",
        "OPERATES",
    }
    assert all(row["evidence_span_id"] for row in nodes)
    assert all(row["extraction_run_id"] for row in nodes)
    assert all(row["properties"]["extraction_run_id"] for row in relationships)


def test_openfda_device_enforcement_fixture_creates_device_recall_risk_case(
    tmp_path: Path,
) -> None:
    config = load_source_config(Path("sources/openfda_device_enforcement.yaml"))
    settings = Settings(data_dir=tmp_path)

    stats = ingest_openfda_device_enforcement_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_device_enforcement/success.json"),
        settings=settings,
        max_documents=1,
    )

    assert stats["raw_documents_created"] == 1
    assert stats["recall_events"] == 1
    assert stats["risk_candidates"] == 1
    assert stats["risk_cases"] == 1
    assert stats["risk_alerts"] == 1
    assert stats["graph_nodes"] == EXPECTED_ENFORCEMENT_GRAPH_NODES
    assert stats["graph_relationships"] == EXPECTED_ENFORCEMENT_GRAPH_RELATIONSHIPS

    candidates = _read_jsonl(tmp_path / "risk_candidates.jsonl")
    cases = _read_jsonl(tmp_path / "risk_cases.jsonl")
    verdicts = _read_jsonl(tmp_path / "risk_verdicts.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")
    event_types = [event["event_type"] for event in events]
    assert candidates[0]["risk_type"] == "recall_quality"
    assert candidates[0]["candidate_key"].startswith("risk_candidate:recall_quality:")
    assert candidates[0]["evidence_span_ids"] == verdicts[0]["evidence_span_ids"]
    assert cases[0]["risk_type"] == "recall_quality"
    assert cases[0]["case_key"].startswith("risk:recall_quality:Recall:openfda_device:")
    assert verdicts[0]["evidence_span_ids"]
    assert event_types.count("risk.candidates") == 1
    assert event_types.count("risk.case_created") == 1
    assert event_types.count("risk.verdicts") == 1
    assert event_types.count("risk.alerts") == 1
    assert sum(event_type.startswith("risk.") for event_type in event_types) == (
        EXPECTED_ENFORCEMENT_RISK_EVENTS
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
