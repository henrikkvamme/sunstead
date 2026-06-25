from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field

from supply_intel.models.base import TimestampedModel, VersionedModel


class EvidenceVerificationOutput(VersionedModel):
    claim_id: str
    status: Literal["supported", "partially_supported", "unsupported", "contradicted"]
    supported_spans: list[UUID] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    contradictions: list[UUID] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class AffectedGraphNode(VersionedModel):
    graph_key: str
    relationship_type: str
    distance: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)


class RiskPath(VersionedModel):
    from_key: str
    to_key: str
    relationship_type: str
    evidence_span_id: UUID | None = None
    confidence: float = Field(ge=0, le=1)


class BlastRadiusOutput(VersionedModel):
    root_graph_key: str
    affected_nodes: list[AffectedGraphNode] = Field(default_factory=list)
    paths: list[RiskPath] = Field(default_factory=list)
    path_query_name: str
    max_depth: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)


class CriticIssue(VersionedModel):
    issue_type: str
    detail: str
    severity: Literal["critical", "high", "medium", "low", "info"]


class CriticOutput(VersionedModel):
    target_id: UUID
    target_type: str
    decision: Literal["approve", "revise", "reject", "needs_human_review"]
    issues: list[CriticIssue] = Field(default_factory=list)
    required_changes: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class AgentFinding(TimestampedModel):
    risk_case_id: UUID
    agent_name: str
    agent_version: str
    model_name: str = "deterministic-local"
    prompt_hash: str = "deterministic_agent_finding_v1"
    input_hash: str = "not_recorded"
    output_schema: str = "AgentFinding"
    output_schema_version: int = 1
    usage: dict[str, object] = Field(default_factory=dict)
    finding_type: str
    finding: dict[str, object]
    evidence_span_ids: list[UUID] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    critic_status: str | None = None
    status: Literal["created", "revised", "rejected"] = "created"
    error: str | None = None
    correlation_id: UUID = Field(default_factory=uuid4)
