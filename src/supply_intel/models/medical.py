from typing import Literal

from pydantic import Field

from supply_intel.models.base import EvidenceRef, VersionedModel

MedicalEntityType = Literal[
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
]


class MedicalEntity(VersionedModel):
    entity_type: MedicalEntityType
    name: str = Field(min_length=1)
    canonical_key: str
    external_ids: dict[str, str] = Field(default_factory=dict)
    attributes: dict[str, object] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)
    needs_review: bool = False
    review_reason: str | None = None


class ExtractedRelationship(VersionedModel):
    relationship_type: str
    from_entity_key: str
    to_entity_key: str
    evidence: list[EvidenceRef]
    attributes: dict[str, object] = Field(default_factory=dict)
    confidence: float = Field(ge=0, le=1)
    inferred: bool = False
