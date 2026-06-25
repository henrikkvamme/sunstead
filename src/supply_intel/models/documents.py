from uuid import UUID

from pydantic import Field, FiniteFloat, model_validator

from supply_intel.models.base import TimestampedModel


class DocumentChunk(TimestampedModel):
    raw_document_id: UUID
    chunk_index: int = Field(ge=0)
    chunk_type: str
    title: str | None = None
    text: str
    structured_data: dict[str, object] = Field(default_factory=dict)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    page_number: int | None = Field(default=None, ge=1)
    section_path: list[str] = Field(default_factory=list)
    embedding: list[FiniteFloat] | None = None
    embedding_model: str | None = None
    content_hash: str

    @model_validator(mode="after")
    def require_embedding_model_for_vector(self) -> "DocumentChunk":
        if self.embedding is not None and not self.embedding_model:
            raise ValueError("embedding_model is required when embedding is set")
        return self


class EvidenceSpan(TimestampedModel):
    raw_document_id: UUID
    document_chunk_id: UUID | None = None
    extraction_run_id: UUID | None = None
    source_id: str
    source_url: str | None = None
    quote: str
    normalized_text: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    page_number: int | None = Field(default=None, ge=1)
    table_ref: dict[str, object] | None = None
    confidence: float = Field(ge=0, le=1)
    evidence_type: str
    hash: str
