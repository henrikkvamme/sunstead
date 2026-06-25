from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, use_enum_values=True)


class VersionedModel(StrictBaseModel):
    schema_version: Literal[1] = 1


class TimestampedModel(VersionedModel):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, object] = Field(default_factory=dict)


class EvidenceRef(VersionedModel):
    raw_document_id: UUID
    document_chunk_id: UUID | None = None
    evidence_span_id: UUID | None = None
    source_id: str
    source_url: str | None = None
    extraction_run_id: UUID | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    confidence: float = Field(ge=0, le=1)
    method: str


class EvidenceSpanCandidate(VersionedModel):
    quote: str = Field(min_length=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    evidence_type: str = "source_text"
    confidence: float = Field(default=1.0, ge=0, le=1)
