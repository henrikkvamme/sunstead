from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.graph import GraphNodeUpsert, GraphRelationshipUpsert
from supply_intel.models.risk import RiskCase


class CountBucket(StrictBaseModel):
    key: str
    count: int = Field(ge=0)


class GraphProvenanceCoverage(StrictBaseModel):
    nodes_with_source_document: int = Field(ge=0)
    nodes_with_evidence_span: int = Field(ge=0)
    relationships_with_source_document: int = Field(ge=0)
    relationships_with_evidence_span: int = Field(ge=0)


class GraphHub(StrictBaseModel):
    graph_node_key: str
    label: str
    labels: list[str]
    degree: int = Field(ge=0)
    in_degree: int = Field(ge=0)
    out_degree: int = Field(ge=0)
    relationship_types: list[CountBucket]
    risk_cases: int = Field(ge=0)
    source_documents: int = Field(ge=0)


class GraphRiskCoverage(StrictBaseModel):
    risk_cases: int = Field(ge=0)
    risk_alerts: int = Field(ge=0)
    by_type: list[CountBucket]
    by_status: list[CountBucket]
    by_severity: list[CountBucket]
    high_or_critical_cases: int = Field(ge=0)


class GraphSourceCoverage(StrictBaseModel):
    raw_documents: int = Field(ge=0)
    document_chunks: int = Field(ge=0)
    source_runs: int = Field(ge=0)
    by_source: list[CountBucket]
    run_statuses: list[CountBucket]


class GraphDemoQuery(StrictBaseModel):
    title: str
    purpose: str
    cypher: str


class GraphIntelligenceSummary(StrictBaseModel):
    data_dir: str
    generated_at: datetime
    graph_nodes: int = Field(ge=0)
    graph_relationships: int = Field(ge=0)
    label_counts: list[CountBucket]
    relationship_type_counts: list[CountBucket]
    provenance: GraphProvenanceCoverage
    source_coverage: GraphSourceCoverage
    risk_coverage: GraphRiskCoverage
    top_hubs: list[GraphHub]
    demo_queries: list[GraphDemoQuery]


def summarize_file_graph(data_dir: Path, *, top: int = 10) -> GraphIntelligenceSummary:
    if top < 1:
        raise ValueError("top must be greater than zero.")
    store = FileEvidenceStore(data_dir)
    nodes = _current_nodes(store)
    relationships = _current_relationships(store)
    risks = [RiskCase.model_validate(row) for row in store.read_collection("risk_cases")]
    risk_cases_by_node = Counter(
        risk.graph_node_key for risk in risks if risk.graph_node_key is not None
    )
    source_documents_by_node = _source_document_counts_by_node(nodes, relationships)

    return GraphIntelligenceSummary(
        data_dir=str(data_dir),
        generated_at=datetime.now(UTC),
        graph_nodes=len(nodes),
        graph_relationships=len(relationships),
        label_counts=_count_buckets(_label_counts(nodes), limit=top),
        relationship_type_counts=_count_buckets(_relationship_type_counts(relationships), limit=top),
        provenance=_provenance_coverage(nodes, relationships),
        source_coverage=_source_coverage(store, top=top),
        risk_coverage=_risk_coverage(store, risks=risks, top=top),
        top_hubs=_top_hubs(
            nodes=nodes,
            relationships=relationships,
            risk_cases_by_node=risk_cases_by_node,
            source_documents_by_node=source_documents_by_node,
            top=top,
        ),
        demo_queries=_demo_queries(),
    )


def _current_nodes(store: FileEvidenceStore) -> dict[str, GraphNodeUpsert]:
    nodes: dict[str, GraphNodeUpsert] = {}
    for row in store.read_collection("graph_node_upserts"):
        node = GraphNodeUpsert.model_validate(row)
        nodes[node.graph_node_key] = node
    return nodes


def _current_relationships(store: FileEvidenceStore) -> dict[str, GraphRelationshipUpsert]:
    relationships: dict[str, GraphRelationshipUpsert] = {}
    for row in store.read_collection("graph_relationship_upserts"):
        relationship = GraphRelationshipUpsert.model_validate(row)
        relationships[relationship.relationship_key] = relationship
    return relationships


def _label_counts(nodes: dict[str, GraphNodeUpsert]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for node in nodes.values():
        counts.update(str(label) for label in node.labels)
    return counts


def _relationship_type_counts(
    relationships: dict[str, GraphRelationshipUpsert],
) -> Counter[str]:
    return Counter(str(relationship.relationship_type) for relationship in relationships.values())


def _provenance_coverage(
    nodes: dict[str, GraphNodeUpsert],
    relationships: dict[str, GraphRelationshipUpsert],
) -> GraphProvenanceCoverage:
    return GraphProvenanceCoverage(
        nodes_with_source_document=sum(1 for node in nodes.values() if node.source_document_id),
        nodes_with_evidence_span=sum(1 for node in nodes.values() if node.evidence_span_id),
        relationships_with_source_document=sum(
            1 for relationship in relationships.values() if relationship.properties.source_document_id
        ),
        relationships_with_evidence_span=sum(
            1 for relationship in relationships.values() if relationship.properties.evidence_span_id
        ),
    )


def _source_coverage(store: FileEvidenceStore, *, top: int) -> GraphSourceCoverage:
    raw_documents = store.read_collection("raw_documents")
    source_runs = store.read_collection("source_runs")
    return GraphSourceCoverage(
        raw_documents=len(raw_documents),
        document_chunks=len(store.read_collection("document_chunks")),
        source_runs=len(source_runs),
        by_source=_count_buckets(
            Counter(str(row.get("source_id", "unknown")) for row in raw_documents),
            limit=top,
        ),
        run_statuses=_count_buckets(
            Counter(str(row.get("status", "unknown")) for row in source_runs),
            limit=top,
        ),
    )


def _risk_coverage(
    store: FileEvidenceStore,
    *,
    risks: list[RiskCase],
    top: int,
) -> GraphRiskCoverage:
    return GraphRiskCoverage(
        risk_cases=len(risks),
        risk_alerts=len(store.read_collection("risk_alerts")),
        by_type=_count_buckets(Counter(risk.risk_type for risk in risks), limit=top),
        by_status=_count_buckets(Counter(risk.status for risk in risks), limit=top),
        by_severity=_count_buckets(Counter(risk.severity for risk in risks), limit=top),
        high_or_critical_cases=sum(1 for risk in risks if risk.severity in {"high", "critical"}),
    )


def _source_document_counts_by_node(
    nodes: dict[str, GraphNodeUpsert],
    relationships: dict[str, GraphRelationshipUpsert],
) -> Counter[str]:
    documents_by_node: dict[str, set[str]] = defaultdict(set)
    for node in nodes.values():
        if node.source_document_id is not None:
            documents_by_node[node.graph_node_key].add(str(node.source_document_id))
    for relationship in relationships.values():
        source_document_id = str(relationship.properties.source_document_id)
        documents_by_node[relationship.from_key].add(source_document_id)
        documents_by_node[relationship.to_key].add(source_document_id)
    return Counter({key: len(values) for key, values in documents_by_node.items()})


def _top_hubs(
    *,
    nodes: dict[str, GraphNodeUpsert],
    relationships: dict[str, GraphRelationshipUpsert],
    risk_cases_by_node: Counter[str],
    source_documents_by_node: Counter[str],
    top: int,
) -> list[GraphHub]:
    degree: Counter[str] = Counter()
    in_degree: Counter[str] = Counter()
    out_degree: Counter[str] = Counter()
    relationship_types_by_node: dict[str, Counter[str]] = defaultdict(Counter)
    for relationship in relationships.values():
        relationship_type = str(relationship.relationship_type)
        degree.update([relationship.from_key, relationship.to_key])
        out_degree.update([relationship.from_key])
        in_degree.update([relationship.to_key])
        relationship_types_by_node[relationship.from_key].update([relationship_type])
        relationship_types_by_node[relationship.to_key].update([relationship_type])

    ranked_keys = sorted(degree, key=lambda key: (-degree[key], key))[:top]
    return [
        GraphHub(
            graph_node_key=key,
            label=_node_label(nodes.get(key), fallback=key),
            labels=[str(label) for label in nodes[key].labels] if key in nodes else [],
            degree=degree[key],
            in_degree=in_degree[key],
            out_degree=out_degree[key],
            relationship_types=_count_buckets(relationship_types_by_node[key], limit=5),
            risk_cases=risk_cases_by_node[key],
            source_documents=source_documents_by_node[key],
        )
        for key in ranked_keys
    ]


def _node_label(node: GraphNodeUpsert | None, *, fallback: str) -> str:
    if node is None:
        return fallback
    for key in (
        "name",
        "label",
        "brand_name",
        "generic_name",
        "proprietary_name",
        "device_name",
        "recalling_firm",
        "firm_name",
        "facility_name",
        "product_description",
        "event_type",
    ):
        value = node.properties.get(key)
        if isinstance(value, str) and value.strip():
            return _truncate(value.strip(), limit=160)
    return fallback


def _count_buckets(counter: Counter[str], *, limit: int | None = None) -> list[CountBucket]:
    items = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    if limit is not None:
        items = items[:limit]
    return [CountBucket(key=key, count=count) for key, count in items]


def _truncate(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def _demo_queries() -> list[GraphDemoQuery]:
    return [
        GraphDemoQuery(
            title="Label coverage",
            purpose="Show graph breadth by node type.",
            cypher=(
                "MATCH (n) UNWIND labels(n) AS label "
                "RETURN label, count(*) AS nodes ORDER BY nodes DESC"
            ),
        ),
        GraphDemoQuery(
            title="Relationship coverage",
            purpose="Show which supply-chain edges dominate the graph.",
            cypher=(
                "MATCH ()-[r]->() RETURN type(r) AS relationship, count(*) AS edges "
                "ORDER BY edges DESC"
            ),
        ),
        GraphDemoQuery(
            title="Top connected manufacturers and facilities",
            purpose="Find the entities with the largest immediate blast radius.",
            cypher=(
                "MATCH (n)-[r]-() WHERE n:Manufacturer OR n:Facility "
                "RETURN labels(n) AS labels, coalesce(n.name, n.key) AS entity, count(r) AS degree "
                "ORDER BY degree DESC LIMIT 25"
            ),
        ),
        GraphDemoQuery(
            title="Recall blast radius",
            purpose="Inspect affected devices, manufacturers, facilities, and evidence.",
            cypher=(
                "MATCH p=(recall:Recall)-[*1..2]-(n) "
                "RETURN recall, relationships(p), n LIMIT 100"
            ),
        ),
        GraphDemoQuery(
            title="Evidence-backed risk cases",
            purpose="Show risk cases tied back to graph nodes and source evidence.",
            cypher=(
                "MATCH (risk:RiskCase)-[r]-(n) "
                "RETURN risk, type(r) AS relationship, n LIMIT 100"
            ),
        ),
    ]
