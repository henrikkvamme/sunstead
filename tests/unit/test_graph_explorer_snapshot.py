import json
from pathlib import Path

from supply_intel.graph.explorer_snapshot import (
    export_explorer_snapshot_from_file_store,
    export_explorer_snapshot_from_neo4j,
    write_explorer_snapshot_from_file_store,
    write_explorer_snapshot_from_neo4j,
)
from supply_intel.pipeline import ingest_openfda_ndc_fixture
from supply_intel.settings import Settings
from supply_intel.sources.registry import load_source_config

EXPECTED_EXPORTED_EDGE_COUNT = 1
EXPECTED_EXPORTED_NODE_COUNT = 2
EXPECTED_FILE_EDGE_COUNT = 3
EXPECTED_FILE_NODE_COUNT = 4
EXPECTED_GRAPH_NODE_COUNT = 546
EXPECTED_GRAPH_RELATIONSHIP_COUNT = 324
EXPECTED_QUERY_COUNT = 3


class FakeExplorerSnapshotClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def run_read_query(
        self,
        cypher: str,
        parameters: dict[str, object],
    ) -> list[dict[str, object]]:
        self.calls.append((cypher, parameters))
        if "RETURN coalesce(n.key" in cypher:
            return [
                {
                    "id": "Drug:ndc_product:79481-0860",
                    "labels": ["Drug"],
                    "properties": {
                        "name": "Sennosides",
                        "confidence": 1.0,
                        "status": "active",
                        "source_document_id": "raw-doc-1",
                        "evidence_span_id": "evidence-1",
                        "attributes": json.dumps(
                            {
                                "brand_name": "Sennosides",
                                "dosage_form": "TABLET, CHEWABLE",
                            }
                        ),
                    },
                },
                {
                    "id": "ActiveIngredient:name:sennosides",
                    "labels": ["ActiveIngredient"],
                    "properties": {
                        "name": "SENNOSIDES",
                        "confidence": 0.98,
                        "status": "active",
                        "source_document_id": "raw-doc-1",
                        "evidence_span_id": "evidence-1",
                        "attributes": json.dumps({"strength": "15 mg/1"}),
                    },
                },
            ]
        if "RETURN coalesce(r.relationship_key" in cypher:
            return [
                {
                    "id": (
                        "Drug:ndc_product:79481-0860|CONTAINS_ACTIVE_INGREDIENT|"
                        "ActiveIngredient:name:sennosides"
                    ),
                    "type": "CONTAINS_ACTIVE_INGREDIENT",
                    "from": "Drug:ndc_product:79481-0860",
                    "to": "ActiveIngredient:name:sennosides",
                    "properties": {
                        "confidence": 0.98,
                        "evidence_span_id": "evidence-1",
                        "source_name": "openfda_drug_ndc",
                    },
                }
            ]
        return [
            {
                "nodes": EXPECTED_GRAPH_NODE_COUNT,
                "relationships": EXPECTED_GRAPH_RELATIONSHIP_COUNT,
            }
        ]


async def test_export_explorer_snapshot_from_neo4j_preserves_provenance() -> None:
    client = FakeExplorerSnapshotClient()

    snapshot = await export_explorer_snapshot_from_neo4j(client, limit=25)

    assert len(client.calls) == EXPECTED_QUERY_COUNT
    assert client.calls[0][1] == {"limit": 25}
    assert snapshot.dataStatus.mode == "neo4j_snapshot"
    assert snapshot.summary.graphNodes == EXPECTED_GRAPH_NODE_COUNT
    assert snapshot.summary.graphRelationships == EXPECTED_GRAPH_RELATIONSHIP_COUNT
    assert len(snapshot.nodes) == EXPECTED_EXPORTED_NODE_COUNT
    assert len(snapshot.edges) == EXPECTED_EXPORTED_EDGE_COUNT
    drug = snapshot.nodes[0]
    assert drug.id == "Drug:ndc_product:79481-0860"
    assert drug.label == "Sennosides"
    assert drug.kind == "Drug"
    assert drug.attributes["Brand name"] == "Sennosides"
    assert drug.attributes["Evidence span id"] == "evidence-1"
    edge = snapshot.edges[0]
    assert edge.from_ == "Drug:ndc_product:79481-0860"
    assert edge.to == "ActiveIngredient:name:sennosides"
    assert edge.evidenceCount == 1


async def test_write_explorer_snapshot_from_neo4j_writes_frontend_contract(
    tmp_path: Path,
) -> None:
    client = FakeExplorerSnapshotClient()
    output_path = tmp_path / "supply-chain-graph.json"

    snapshot = await write_explorer_snapshot_from_neo4j(client, output_path, limit=10)

    rendered = output_path.read_text(encoding="utf-8")
    payload = json.loads(rendered)
    assert payload["dataStatus"]["mode"] == "neo4j_snapshot"
    assert payload["summary"]["graphNodes"] == EXPECTED_GRAPH_NODE_COUNT
    assert payload["nodes"][0]["id"] == snapshot.nodes[0].id
    assert payload["edges"][0]["from"] == "Drug:ndc_product:79481-0860"
    assert '"chainIds": ["neo4j-live"]' in rendered


def test_export_explorer_snapshot_from_file_store_preserves_local_graph_provenance(
    tmp_path: Path,
) -> None:
    _seed_openfda_ndc_graph(tmp_path)

    snapshot = export_explorer_snapshot_from_file_store(tmp_path)

    assert snapshot.dataStatus.mode == "file_snapshot"
    assert snapshot.summary.graphNodes == EXPECTED_FILE_NODE_COUNT
    assert snapshot.summary.graphRelationships == EXPECTED_FILE_EDGE_COUNT
    assert len(snapshot.nodes) == EXPECTED_FILE_NODE_COUNT
    assert len(snapshot.edges) == EXPECTED_FILE_EDGE_COUNT
    drug = next(node for node in snapshot.nodes if node.kind == "Drug")
    assert drug.id.startswith("Drug:ndc_product:")
    assert drug.label
    assert drug.chainIds == ["file-store"]
    assert drug.attributes["Source document id"]
    assert drug.attributes["Evidence span id"]
    edge = snapshot.edges[0]
    assert edge.evidenceCount == 1
    assert edge.from_
    assert edge.to


def test_write_explorer_snapshot_from_file_store_writes_frontend_contract(
    tmp_path: Path,
) -> None:
    _seed_openfda_ndc_graph(tmp_path)
    output_path = tmp_path / "supply-chain-graph.json"

    snapshot = write_explorer_snapshot_from_file_store(tmp_path, output_path, limit=10)

    rendered = output_path.read_text(encoding="utf-8")
    payload = json.loads(rendered)
    assert payload["dataStatus"]["mode"] == "file_snapshot"
    assert payload["summary"]["graphNodes"] == EXPECTED_FILE_NODE_COUNT
    assert payload["nodes"][0]["id"] == snapshot.nodes[0].id
    assert payload["edges"][0]["from"]
    assert '"chainIds": ["file-store"]' in rendered


def _seed_openfda_ndc_graph(data_dir: Path) -> None:
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    ingest_openfda_ndc_fixture(
        config=config,
        fixture_path=Path("tests/fixtures/sources/openfda_drug_ndc/success.json"),
        settings=Settings(data_dir=data_dir),
        max_documents=1,
    )
