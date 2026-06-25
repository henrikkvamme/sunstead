from pathlib import Path

from pydantic import Field

from supply_intel.models.base import StrictBaseModel

DEFAULT_QUERY_DIR = Path("cypher/queries")
GRAPH_QUERY_PARAMETERS = {
    "commodity_input_exposure": {"commodity_key"},
    "disaster_facility_exposure": {"disaster_key"},
    "drug_supply_chain": {"drug_key"},
    "facility_downstream_products": {"facility_key"},
    "ingredient_dependency": {"ingredient_key"},
    "port_exposure": {"port_key"},
    "recall_blast_radius": {"recall_key"},
    "risk_case_context": {"risk_case_key"},
    "shortage_blast_radius": {"shortage_key"},
}


class GraphQueryPlan(StrictBaseModel):
    query_name: str
    path: str
    cypher: str
    parameters: dict[str, str] = Field(default_factory=dict)


def load_graph_query_plan(
    query_name: str,
    *,
    parameters: dict[str, str | None],
    query_dir: Path = DEFAULT_QUERY_DIR,
) -> GraphQueryPlan:
    normalized_name = normalize_graph_query_name(query_name)
    path = query_dir / f"{normalized_name}.cypher"
    if not path.exists():
        raise ValueError(f"Unknown graph query: {query_name}")

    required = GRAPH_QUERY_PARAMETERS.get(normalized_name, set())
    missing = sorted(name for name in required if not parameters.get(name))
    if missing:
        formatted = ", ".join(f"--{name.replace('_', '-')}" for name in missing)
        raise ValueError(f"Graph query {query_name} requires {formatted}")

    bound_parameters = {name: str(parameters[name]) for name in sorted(required)}
    return GraphQueryPlan(
        query_name=normalized_name,
        path=str(path),
        cypher=path.read_text(encoding="utf-8"),
        parameters=bound_parameters,
    )


def normalize_graph_query_name(value: str) -> str:
    normalized = value.strip().replace("-", "_")
    if not normalized or not normalized.replace("_", "").isalnum():
        raise ValueError(f"Unsafe graph query name: {value}")
    return normalized
