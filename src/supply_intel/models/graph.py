from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from supply_intel.models.base import VersionedModel

GraphLabel = Literal[
    "Drug",
    "NDC",
    "ActiveIngredient",
    "Excipient",
    "RawMaterial",
    "ChemicalInput",
    "Manufacturer",
    "Supplier",
    "Facility",
    "MedicalDevice",
    "DeviceCategory",
    "RegulatoryAgency",
    "Country",
    "Region",
    "City",
    "Port",
    "TransportRoute",
    "Commodity",
    "Shortage",
    "Recall",
    "RegulatoryNotice",
    "NewsEvent",
    "DisasterEvent",
    "StrikeEvent",
    "PriceObservation",
    "TradeFlowObservation",
    "LogisticsPressureObservation",
    "TrendSignalObservation",
    "RiskCase",
    "EvidenceDocument",
    "Source",
]

RelationshipType = Literal[
    "HAS_NDC",
    "CONTAINS_ACTIVE_INGREDIENT",
    "CONTAINS_EXCIPIENT",
    "USES_INPUT",
    "LINKED_TO_COMMODITY",
    "LABELS",
    "MARKETS",
    "PRODUCES",
    "OPERATES",
    "SUPPLIES",
    "SUPPLIES_INPUT",
    "LOCATED_IN",
    "NEAR_PORT",
    "CONNECTS",
    "MANUFACTURED_BY",
    "MANUFACTURED_AT",
    "BELONGS_TO_CATEGORY",
    "INVOLVES",
    "MENTIONS",
    "AFFECTS",
    "OBSERVED_FOR",
    "ABOUT",
    "ISSUED_BY",
    "ISSUED_TO",
    "FILED_BY",
    "FILED_WITH",
    "SUPPORTED_BY",
    "HAS_EVIDENCE",
]


class RelationshipProvenance(VersionedModel):
    confidence: float = Field(ge=0, le=1)
    source_document_id: UUID
    evidence_span_id: UUID | None = None
    extraction_run_id: UUID | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    source_name: str
    source_url: str | None = None
    method: str
    status: str = "active"


class GraphNodeUpsert(VersionedModel):
    graph_node_key: str
    labels: list[GraphLabel]
    properties: dict[str, object] = Field(default_factory=dict)
    source_document_id: UUID | None = None
    evidence_span_id: UUID | None = None
    extraction_run_id: UUID | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)

    @field_validator("labels")
    @classmethod
    def labels_not_empty(cls, value: list[GraphLabel]) -> list[GraphLabel]:
        if not value:
            raise ValueError("Graph nodes require at least one label")
        return value


class GraphRelationshipUpsert(VersionedModel):
    relationship_key: str
    from_key: str
    to_key: str
    relationship_type: RelationshipType
    properties: RelationshipProvenance


class GraphMappingOutput(VersionedModel):
    node_upserts: list[GraphNodeUpsert] = Field(default_factory=list)
    relationship_upserts: list[GraphRelationshipUpsert] = Field(default_factory=list)
    skipped_items: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
