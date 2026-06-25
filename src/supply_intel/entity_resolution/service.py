from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from supply_intel.entity_resolution.normalize import normalize_name
from supply_intel.models.base import StrictBaseModel, TimestampedModel
from supply_intel.models.medical import MedicalEntity

HIGH_IMPACT_ENTITY_TYPES = {
    "ActiveIngredient",
    "Facility",
    "Manufacturer",
    "MedicalDevice",
    "Supplier",
}
HIGH_IMPACT_REVIEW_THRESHOLD = 0.88


class CanonicalEntity(TimestampedModel):
    entity_type: str
    canonical_key: str
    display_name: str
    normalized_name: str
    external_ids: dict[str, str] = Field(default_factory=dict)
    attributes: dict[str, object] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0, le=1)
    status: str = "active"
    needs_review: bool = False
    review_reason: str | None = None


class EntityAlias(TimestampedModel):
    canonical_entity_id: UUID
    alias: str
    normalized_alias: str
    alias_type: Literal["extracted_name", "external_id", "manual"] = "extracted_name"
    source_id: str | None = None
    evidence_span_id: UUID | None = None
    confidence: float = Field(ge=0, le=1)


class HumanReviewTask(TimestampedModel):
    target_table: str
    target_id: UUID
    review_type: Literal["low_confidence", "conflict", "high_impact_sparse_evidence"]
    reason: str
    status: Literal["open", "resolved"] = "open"
    priority: Literal["P0", "P1", "P2", "P3"] = "P2"
    evidence_span_ids: list[UUID] = Field(default_factory=list)


class HumanFeedback(StrictBaseModel):
    id: UUID = Field(default_factory=uuid4)
    target_table: str
    target_id: UUID
    feedback_type: str
    decision: str
    comment: str | None = None
    reviewer: str | None = None
    before_value: dict[str, object] | None = None
    after_value: dict[str, object] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, object] = Field(default_factory=dict)


@dataclass
class EntityResolutionService:
    entities_by_key: dict[tuple[str, str], CanonicalEntity] = field(default_factory=dict)

    def resolve(self, entity: MedicalEntity) -> CanonicalEntity:
        key = (entity.entity_type, entity.canonical_key)
        normalized_name = normalize_name(entity.name)
        existing = self.entities_by_key.get(key)
        if existing is not None:
            if existing.normalized_name != normalized_name:
                existing.needs_review = True
                existing.review_reason = (
                    "Conflicting normalized names for the same deterministic canonical key."
                )
            return existing
        needs_review, review_reason = review_decision(entity)
        canonical = CanonicalEntity(
            id=uuid4(),
            entity_type=entity.entity_type,
            canonical_key=entity.canonical_key,
            display_name=entity.name,
            normalized_name=normalized_name,
            external_ids=entity.external_ids,
            attributes=entity.attributes,
            confidence=entity.confidence,
            needs_review=needs_review,
            review_reason=review_reason,
        )
        self.entities_by_key[key] = canonical
        return canonical

    def by_id(self, entity_id: UUID) -> CanonicalEntity | None:
        return next(
            (entity for entity in self.entities_by_key.values() if entity.id == entity_id),
            None,
        )


def review_decision(entity: MedicalEntity) -> tuple[bool, str | None]:
    if entity.needs_review:
        return True, entity.review_reason or "Extractor marked this entity for review."
    if (
        entity.entity_type in HIGH_IMPACT_ENTITY_TYPES
        and entity.confidence < HIGH_IMPACT_REVIEW_THRESHOLD
    ):
        return (
            True,
            (
                f"High-impact {entity.entity_type} entity confidence "
                f"{entity.confidence:.2f} is below {HIGH_IMPACT_REVIEW_THRESHOLD:.2f}."
            ),
        )
    return False, None


def human_feedback_from_review_task(task: HumanReviewTask) -> HumanFeedback:
    return HumanFeedback(
        target_table=task.target_table,
        target_id=task.target_id,
        feedback_type="review_requested",
        decision="pending",
        comment=task.reason,
        before_value=None,
        after_value={"status": task.status, "priority": task.priority},
        metadata={
            "human_review_task_id": str(task.id),
            "review_type": task.review_type,
            "evidence_span_ids": [str(value) for value in task.evidence_span_ids],
        },
    )
