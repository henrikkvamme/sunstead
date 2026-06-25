from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.graph.neo4j_client import AsyncNeo4jClient
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.graph import GraphNodeUpsert, GraphRelationshipUpsert

LOW_CONFIDENCE_THRESHOLD = 0.7
SCALAR_ARRAY_START_RE = re.compile(r"^(?P<indent>\s+)(?P<prefix>.*): \[$")
SCALAR_ARRAY_ITEM_RE = re.compile(
    r'^\s+(?P<value>(?:"(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|true|false|null)),?$'
)


class ExplorerDataStatus(StrictBaseModel):
    mode: Literal["neo4j_snapshot", "file_snapshot"]
    evidence: str
    limits: str


class ExplorerChain(StrictBaseModel):
    id: str
    name: str
    owner: str
    status: Literal["live", "ready", "planned"]
    description: str


class ExplorerNode(StrictBaseModel):
    id: str
    label: str
    kind: str
    chainIds: list[str]
    confidence: float = Field(ge=0, le=1)
    source: str
    status: str
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    subtitle: str | None = None
    risk: Literal["low", "medium", "high", "watch"] = "low"
    attributes: dict[str, str] = Field(default_factory=dict)


class ExplorerEdge(StrictBaseModel):
    id: str
    from_: str = Field(alias="from")
    to: str
    label: str
    confidence: float = Field(ge=0, le=1)
    evidenceCount: int = Field(ge=0)


class ExplorerSignal(StrictBaseModel):
    id: str
    title: str
    source: str
    severity: Literal["low", "medium", "high", "watch"]
    observedAt: str
    summary: str


class ExplorerSource(StrictBaseModel):
    id: str
    name: str
    status: Literal["live", "ready", "planned"]
    coverage: str
    records: str


class ExplorerSummary(StrictBaseModel):
    graphNodes: int
    graphRelationships: int
    liveSources: int
    watchSignals: int


class ExplorerSnapshot(StrictBaseModel):
    generatedAt: str
    dataStatus: ExplorerDataStatus
    summary: ExplorerSummary
    chains: list[ExplorerChain]
    nodes: list[ExplorerNode]
    edges: list[ExplorerEdge]
    signals: list[ExplorerSignal]
    sources: list[ExplorerSource]


async def export_explorer_snapshot_from_neo4j(
    client: AsyncNeo4jClient,
    *,
    limit: int = 500,
) -> ExplorerSnapshot:
    if limit < 1:
        raise ValueError("limit must be greater than zero.")

    node_rows = await client.run_read_query(
        """
        MATCH (n)
        WITH n
        ORDER BY coalesce(n.updated_at, n.created_at, datetime()) DESC
        LIMIT $limit
        RETURN coalesce(n.key, n.graph_node_key, elementId(n)) AS id,
               labels(n) AS labels,
               properties(n) AS properties
        """,
        {"limit": limit},
    )
    relationship_rows = await client.run_read_query(
        """
        MATCH (a)-[r]->(b)
        WITH a, r, b
        ORDER BY coalesce(r.updated_at, r.created_at, datetime()) DESC
        LIMIT $limit
        RETURN coalesce(r.relationship_key, elementId(r)) AS id,
               type(r) AS type,
               coalesce(a.key, a.graph_node_key, elementId(a)) AS from,
               coalesce(b.key, b.graph_node_key, elementId(b)) AS to,
               properties(r) AS properties
        """,
        {"limit": limit},
    )
    count_rows = await client.run_read_query(
        """
        MATCH (n)
        WITH count(n) AS nodes
        MATCH ()-[r]->()
        RETURN nodes, count(r) AS relationships
        """,
        {},
    )
    count_row = count_rows[0] if count_rows else {}
    nodes_total = _as_int(count_row.get("nodes"), fallback=len(node_rows))
    relationships_total = _as_int(count_row.get("relationships"), fallback=len(relationship_rows))
    now = datetime.now(UTC).replace(microsecond=0)
    nodes = [
        _explorer_node_from_neo4j_row(row, index=index, total=max(len(node_rows), 1))
        for index, row in enumerate(node_rows)
    ]
    node_ids = {node.id for node in nodes}
    edges = [
        _explorer_edge_from_neo4j_row(row)
        for row in relationship_rows
        if str(row.get("from", "")) in node_ids and str(row.get("to", "")) in node_ids
    ]
    sources = _sources_from_nodes(nodes)
    signals = _signals_from_nodes(nodes, now)

    return ExplorerSnapshot(
        generatedAt=now.isoformat().replace("+00:00", "Z"),
        dataStatus=ExplorerDataStatus(
            mode="neo4j_snapshot",
            evidence=(
                "Exported from the local Neo4j graph. Nodes and relationships preserve source, "
                "confidence, and evidence identifiers from the platform graph upsert pipeline."
            ),
            limits=(
                "This is a snapshot for the frontend; refresh it after new graph-writer runs or "
                "replace it with a live graph API for continuous updates."
            ),
        ),
        summary=ExplorerSummary(
            graphNodes=nodes_total,
            graphRelationships=relationships_total,
            liveSources=len(sources),
            watchSignals=len(signals),
        ),
        chains=[
            ExplorerChain(
                id="neo4j-live",
                name="Neo4j platform graph",
                owner="graph-writer",
                status="live",
                description=(
                    "Current exported Neo4j nodes and relationships from platform evidence."
                ),
            )
        ],
        nodes=nodes,
        edges=edges,
        signals=signals,
        sources=sources,
    )


async def write_explorer_snapshot_from_neo4j(
    client: AsyncNeo4jClient,
    output_path: Path,
    *,
    limit: int = 500,
) -> ExplorerSnapshot:
    snapshot = await export_explorer_snapshot_from_neo4j(client, limit=limit)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_snapshot_json(snapshot, output_path)
    return snapshot


def export_explorer_snapshot_from_file_store(
    data_dir: Path,
    *,
    limit: int = 500,
) -> ExplorerSnapshot:
    if limit < 1:
        raise ValueError("limit must be greater than zero.")

    store = FileEvidenceStore(data_dir)
    node_upserts = _current_node_upserts(store)
    relationship_upserts = _current_relationship_upserts(store)
    limited_nodes = list(node_upserts.values())[-limit:]
    node_ids = {node.graph_node_key for node in limited_nodes}
    limited_relationships = [
        relationship
        for relationship in list(relationship_upserts.values())[-limit:]
        if relationship.from_key in node_ids and relationship.to_key in node_ids
    ]
    now = datetime.now(UTC).replace(microsecond=0)
    nodes = [
        _explorer_node_from_upsert(upsert, index=index, total=max(len(limited_nodes), 1))
        for index, upsert in enumerate(limited_nodes)
    ]
    edges = [
        _explorer_edge_from_upsert(upsert, evidence_counts=_relationship_evidence_counts(store))
        for upsert in limited_relationships
    ]
    sources = _sources_from_nodes(nodes)
    signals = _signals_from_nodes(nodes, now)

    return ExplorerSnapshot(
        generatedAt=now.isoformat().replace("+00:00", "Z"),
        dataStatus=ExplorerDataStatus(
            mode="file_snapshot",
            evidence=(
                "Exported from local graph upsert evidence. Nodes and relationships preserve "
                "source document, extraction run, confidence, and evidence span identifiers."
            ),
            limits=(
                "This file-backed snapshot is deterministic for demos. Replay graph upserts into "
                "Neo4j and export with --source neo4j when live graph queries are required."
            ),
        ),
        summary=ExplorerSummary(
            graphNodes=len(node_upserts),
            graphRelationships=len(relationship_upserts),
            liveSources=len(sources),
            watchSignals=len(signals),
        ),
        chains=[
            ExplorerChain(
                id="file-store",
                name="Local evidence graph",
                owner="refresh-demo-data",
                status="ready",
                description=(
                    "Current graph nodes and relationships from local platform evidence files."
                ),
            )
        ],
        nodes=nodes,
        edges=edges,
        signals=signals,
        sources=sources,
    )


def write_explorer_snapshot_from_file_store(
    data_dir: Path,
    output_path: Path,
    *,
    limit: int = 500,
) -> ExplorerSnapshot:
    snapshot = export_explorer_snapshot_from_file_store(data_dir, limit=limit)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_snapshot_json(snapshot, output_path)
    return snapshot


def _write_snapshot_json(snapshot: ExplorerSnapshot, output_path: Path) -> None:
    rendered = json.dumps(snapshot.model_dump(mode="json", by_alias=True), indent=2)
    output_path.write_text(_compact_scalar_json_arrays(rendered) + "\n", encoding="utf-8")


def _compact_scalar_json_arrays(rendered: str) -> str:
    lines = rendered.splitlines()
    compacted: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = SCALAR_ARRAY_START_RE.match(line)
        if match is None:
            compacted.append(line)
            index += 1
            continue
        closing_index = _scalar_array_closing_index(lines, index, match.group("indent"))
        if closing_index is None:
            compacted.append(line)
            index += 1
            continue
        values = [
            SCALAR_ARRAY_ITEM_RE.match(lines[item_index]).group("value")  # type: ignore[union-attr]
            for item_index in range(index + 1, closing_index)
        ]
        suffix = "," if lines[closing_index].strip().endswith(",") else ""
        compacted.append(
            f"{match.group('indent')}{match.group('prefix')}: [{', '.join(values)}]{suffix}"
        )
        index = closing_index + 1
    return "\n".join(compacted)


def _scalar_array_closing_index(
    lines: list[str],
    start_index: int,
    indent: str,
) -> int | None:
    closing_prefix = f"{indent}]"
    item_index = start_index + 1
    if item_index >= len(lines) or lines[item_index].startswith(closing_prefix):
        return None
    while item_index < len(lines):
        line = lines[item_index]
        if line.startswith(closing_prefix):
            return item_index
        if SCALAR_ARRAY_ITEM_RE.match(line) is None:
            return None
        item_index += 1
    return None


def _explorer_node_from_neo4j_row(
    row: dict[str, object],
    *,
    index: int,
    total: int,
) -> ExplorerNode:
    labels = _string_list(row.get("labels"))
    properties = _properties(row.get("properties"))
    node_id = str(row.get("id") or properties.get("key") or f"neo4j-node-{index}")
    kind = _node_kind(labels)
    x, y = _layout_point(index, total)
    confidence = _as_float(properties.get("confidence"), fallback=0.75)
    attributes = _attributes(properties)
    source = str(
        properties.get("source_name")
        or properties.get("source")
        or properties.get("source_document_id")
        or "neo4j"
    )

    return ExplorerNode(
        id=node_id,
        label=str(properties.get("name") or properties.get("label") or node_id),
        kind=kind,
        chainIds=["neo4j-live"],
        confidence=confidence,
        source=source,
        status=str(properties.get("status") or "active"),
        x=x,
        y=y,
        subtitle=_subtitle(kind, properties, labels),
        risk=_risk_for_node(kind, confidence),
        attributes=attributes,
    )


def _explorer_node_from_upsert(
    upsert: GraphNodeUpsert,
    *,
    index: int,
    total: int,
) -> ExplorerNode:
    labels = [str(label) for label in upsert.labels]
    properties = {
        **upsert.properties,
        "key": upsert.graph_node_key,
        "graph_node_key": upsert.graph_node_key,
        "source_document_id": str(upsert.source_document_id) if upsert.source_document_id else None,
        "evidence_span_id": str(upsert.evidence_span_id) if upsert.evidence_span_id else None,
        "extraction_run_id": str(upsert.extraction_run_id) if upsert.extraction_run_id else None,
        "confidence": upsert.confidence,
    }
    kind = _node_kind(labels)
    x, y = _layout_point(index, total)
    source = str(
        properties.get("source_name")
        or properties.get("source")
        or properties.get("source_document_id")
        or "local-evidence"
    )
    return ExplorerNode(
        id=upsert.graph_node_key,
        label=str(properties.get("name") or properties.get("label") or upsert.graph_node_key),
        kind=kind,
        chainIds=["file-store"],
        confidence=upsert.confidence,
        source=source,
        status=str(properties.get("status") or "active"),
        x=x,
        y=y,
        subtitle=_subtitle(kind, properties, labels),
        risk=_risk_for_node(kind, upsert.confidence),
        attributes=_attributes(properties),
    )


def _explorer_edge_from_neo4j_row(row: dict[str, object]) -> ExplorerEdge:
    properties = _properties(row.get("properties"))
    confidence = _as_float(properties.get("confidence"), fallback=0.75)
    relationship_key = str(row.get("id") or properties.get("relationship_key") or "")
    return ExplorerEdge(
        id=relationship_key or f"{row.get('from')}|{row.get('type')}|{row.get('to')}",
        from_=str(row.get("from")),
        to=str(row.get("to")),
        label=str(row.get("type") or "RELATED_TO"),
        confidence=confidence,
        evidenceCount=1 if properties.get("evidence_span_id") else 0,
    )


def _explorer_edge_from_upsert(
    upsert: GraphRelationshipUpsert,
    *,
    evidence_counts: dict[str, int],
) -> ExplorerEdge:
    properties = upsert.properties
    return ExplorerEdge(
        id=upsert.relationship_key,
        from_=upsert.from_key,
        to=upsert.to_key,
        label=upsert.relationship_type,
        confidence=properties.confidence,
        evidenceCount=evidence_counts.get(upsert.relationship_key, 0),
    )


def _current_node_upserts(store: FileEvidenceStore) -> dict[str, GraphNodeUpsert]:
    nodes: dict[str, GraphNodeUpsert] = {}
    for row in store.read_collection("graph_node_upserts"):
        upsert = GraphNodeUpsert.model_validate(row)
        current = nodes.get(upsert.graph_node_key)
        if current is None or upsert.confidence >= current.confidence:
            nodes[upsert.graph_node_key] = upsert
    return nodes


def _current_relationship_upserts(store: FileEvidenceStore) -> dict[str, GraphRelationshipUpsert]:
    relationships: dict[str, GraphRelationshipUpsert] = {}
    for row in store.read_collection("graph_relationship_upserts"):
        upsert = GraphRelationshipUpsert.model_validate(row)
        current = relationships.get(upsert.relationship_key)
        if current is None or upsert.properties.confidence >= current.properties.confidence:
            relationships[upsert.relationship_key] = upsert
    return relationships


def _relationship_evidence_counts(store: FileEvidenceStore) -> dict[str, int]:
    evidence_ids_by_relationship: dict[str, set[str]] = {}
    for row in store.read_collection("graph_relationship_upserts"):
        upsert = GraphRelationshipUpsert.model_validate(row)
        evidence_span_id = upsert.properties.evidence_span_id
        evidence_ids_by_relationship.setdefault(upsert.relationship_key, set())
        if evidence_span_id is not None:
            evidence_ids_by_relationship[upsert.relationship_key].add(str(evidence_span_id))
    return {
        relationship_key: len(evidence_ids)
        for relationship_key, evidence_ids in evidence_ids_by_relationship.items()
    }


def _sources_from_nodes(nodes: list[ExplorerNode]) -> list[ExplorerSource]:
    names = sorted({node.source for node in nodes if node.source and node.source != "neo4j"})
    if not names:
        names = ["neo4j"]
    return [
        ExplorerSource(
            id=_safe_id(name),
            name=name,
            status="live",
            coverage="Neo4j graph export source observed in node provenance.",
            records=f"{sum(1 for node in nodes if node.source == name)} graph nodes",
        )
        for name in names
    ]


def _signals_from_nodes(nodes: list[ExplorerNode], observed_at: datetime) -> list[ExplorerSignal]:
    watched = [node for node in nodes if node.risk in {"medium", "high", "watch"}]
    if not watched:
        return []
    return [
        ExplorerSignal(
            id=f"neo4j-signal-{index}",
            title=f"{node.label} graph signal",
            source=node.source,
            severity=node.risk,
            observedAt=observed_at.isoformat().replace("+00:00", "Z"),
            summary=f"{node.kind} node exported from Neo4j with {node.confidence:.0%} confidence.",
        )
        for index, node in enumerate(watched[:8])
    ]


def _properties(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _attributes(properties: dict[str, object]) -> dict[str, str]:
    attributes: dict[str, str] = {}
    nested = _json_object(properties.get("attributes"))
    for key, value in nested.items():
        attributes[_humanize_key(str(key))] = _display_value(value)
    for key in [
        "key",
        "graph_node_key",
        "source_document_id",
        "evidence_span_id",
        "extraction_run_id",
        "observed_at",
        "value",
        "unit",
        "currency",
        "commodity_name",
    ]:
        if key in properties and properties[key] is not None:
            attributes[_humanize_key(key)] = _display_value(properties[key])
    return attributes


def _json_object(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): item for key, item in parsed.items()}


def _node_kind(labels: list[str]) -> str:
    for label in [
        "Drug",
        "NDC",
        "ActiveIngredient",
        "Manufacturer",
        "PriceObservation",
        "NewsSignal",
        "Location",
        "Source",
    ]:
        if label in labels:
            return label
    return labels[0] if labels else "Source"


def _subtitle(kind: str, properties: dict[str, object], labels: list[str]) -> str:
    if kind == "PriceObservation":
        value = properties.get("value")
        unit = properties.get("unit")
        observed_at = properties.get("observed_at")
        return " ".join(str(item) for item in [value, unit, observed_at] if item)
    if kind == "Drug":
        attributes = _json_object(properties.get("attributes"))
        return _display_value(attributes.get("dosage_form") or attributes.get("route") or "Drug")
    return ", ".join(labels) if labels else kind


def _risk_for_node(kind: str, confidence: float) -> Literal["low", "medium", "high", "watch"]:
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        return "watch"
    if kind in {"PriceObservation", "NewsSignal"}:
        return "medium"
    return "low"


def _layout_point(index: int, total: int) -> tuple[float, float]:
    angle = index * (math.pi * (3 - math.sqrt(5)))
    radius = 8 + 36 * math.sqrt((index + 0.5) / max(total, 1))
    x = 50 + math.cos(angle) * radius
    y = 50 + math.sin(angle) * radius
    return _clamp(x, 8, 92), _clamp(y, 10, 90)


def _safe_id(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_") or "source"


def _humanize_key(value: str) -> str:
    return value.replace("_", " ").capitalize()


def _display_value(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str, sort_keys=True)


def _as_float(value: object, *, fallback: float) -> float:
    if isinstance(value, int | float):
        return _clamp(float(value), 0, 1)
    if isinstance(value, str):
        try:
            return _clamp(float(value), 0, 1)
        except ValueError:
            return fallback
    return fallback


def _as_int(value: object, *, fallback: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return fallback
    return fallback


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))
