# Pydantic AI Agents

Pydantic AI is the structured agent framework. Agents may reason internally, but every persisted output must be a Pydantic model with a schema version. No loose JSON crosses Kafka, PostgreSQL, or Neo4j boundaries.

## Provider Configuration

Support Featherless or any OpenAI-compatible provider through:

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_TIMEOUT_SECONDS`
- `LLM_MAX_RETRIES`
- `LLM_MAX_OUTPUT_TOKENS`

Embedding provider:

- `EMBEDDING_BASE_URL`
- `EMBEDDING_API_KEY`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIMENSIONS`

Chunk embeddings are optional and fail closed: when all embedding settings are present,
the parser pipeline calls an OpenAI-compatible `/embeddings` endpoint and stores the
validated vector plus `embedding_model` on `document_chunks`; when settings are absent,
deterministic ingestion and extraction run without embedding network calls.

Implementation pattern:

- central `ModelFactory` that owns deterministic fallback metadata and
  OpenAI-compatible provider/model construction
- no provider hardcoding in agents
- pass usage limits to every run
- store model name, prompt hash, schema version, usage, validated output, and errors in `extraction_runs` or `agent_findings`
- `risk.agent_findings` events include the same non-secret runtime metadata so agent
  conclusions can be audited from Kafka and PostgreSQL.

## Core Model Conventions

All output models inherit:

```python
class VersionedModel(BaseModel):
    schema_version: Literal[1] = 1
```

All extracted facts include:

```python
class ProvenanceRef(BaseModel):
    raw_document_id: UUID
    document_chunk_id: UUID | None
    evidence_span_id: UUID | None
    source_id: str
    source_url: AnyUrl | None
    extraction_run_id: UUID | None
    observed_at: datetime
    confidence: confloat(ge=0, le=1)
    method: str
```

All evidence-using models include:

- `evidence: list[EvidenceRef]`
- `confidence`
- `needs_review`
- `review_reason`

## SourceOnboardingAgent

Purpose:

- inspect a new source URL or file sample
- propose source config
- identify parser profile needs
- identify compliance/rate-limit concerns
- propose fixtures/tests

Input:

- source URL
- sample payload
- user-provided notes
- source documentation excerpts

Output model:

```python
class SourceOnboardingOutput(VersionedModel):
    proposed_source_config: SourceConfig
    parser_profile_name: str
    adapter_required: str
    custom_adapter_needed: bool
    compliance_notes: list[str]
    rate_limit_notes: list[str]
    fixture_plan: list[str]
    open_questions: list[str]
    confidence: float
```

Rules:

- Never invent API limits; mark unknowns as unknown.
- Must recommend raw-first storage.
- Must fail closed when scraping compliance is unclear.

## FetchPlannerAgent

Purpose:

- plan backfills and incremental runs for complex sources
- choose date windows, pagination, and dedupe strategy

Output:

```python
class FetchPlannerOutput(VersionedModel):
    source_id: str
    run_type: Literal["scheduled", "manual", "backfill", "replay", "test"]
    fetch_windows: list[FetchWindow]
    cursor_strategy: str
    dedupe_strategy: str
    expected_volume: int | None
    risk_notes: list[str]
```

Use sparingly. Most sources should use deterministic scheduler logic.

## MedicalExtractionAgent

Purpose:

- extract domain facts from parsed chunks
- produce typed medical, regulatory, shortage, recall, device, disaster, labor, price, and logistics outputs

Output:

```python
class MedicalExtractionOutput(VersionedModel):
    entities: list[MedicalEntity]
    regulatory_events: list[RegulatoryEvent]
    recall_events: list[RecallEvent]
    shortage_events: list[ShortageEvent]
    news_events: list[NewsEvent]
    disaster_events: list[DisasterEvent]
    strike_events: list[StrikeEvent]
    price_observations: list[PriceObservation]
    relationships: list[ExtractedRelationship]
    evidence_spans: list[EvidenceSpanCandidate]
    warnings: list[str]
```

Key entity models:

- `DrugEntity`
- `NDCEntity`
- `ActiveIngredientEntity`
- `ExcipientEntity`
- `RawMaterialEntity`
- `ChemicalInputEntity`
- `ManufacturerEntity`
- `SupplierEntity`
- `FacilityEntity`
- `MedicalDeviceEntity`
- `DeviceCategoryEntity`
- `RegulatoryAgencyEntity`
- `LocationEntity`
- `PortEntity`
- `CommodityEntity`

Rules:

- Extract only claims supported by source text.
- Use exact evidence spans.
- Separate mentions from canonical identity.
- Mark inferred relationships as inferred and lower confidence.

## EntityResolutionAgent

Purpose:

- adjudicate uncertain entity matches after deterministic matchers run
- explain why candidates match or do not match

Input:

- mention
- deterministic candidates
- alias candidates
- vector candidates
- graph context
- source evidence

Output:

```python
class EntityResolutionOutput(VersionedModel):
    mention_id: UUID
    decision: Literal["match", "new_entity", "conflict", "needs_human_review"]
    canonical_entity_id: UUID | None
    proposed_canonical_key: str | None
    confidence: float
    rationale: str
    supporting_evidence_ids: list[UUID]
    conflicting_evidence_ids: list[UUID]
```

Rules:

- Do not merge below threshold.
- Do not merge companies based on similar names alone.
- Preserve subsidiaries and labelers distinctly unless official evidence supports equivalence.

## GraphMappingAgent

Purpose:

- map validated extraction/entity outputs into graph node and relationship upserts

Output:

```python
class GraphMappingOutput(VersionedModel):
    node_upserts: list[GraphNodeUpsert]
    relationship_upserts: list[GraphRelationshipUpsert]
    skipped_items: list[SkippedGraphItem]
    warnings: list[str]
```

Rules:

- Every relationship must include provenance fields required by `09_NEO4J_GRAPH_SCHEMA.md`.
- Do not create graph relationships without evidence unless the relationship is explicitly curated and audited.
- Use stable graph keys.

## RiskSignalAgent

Purpose:

- identify candidate risks from new source events, graph changes, and risk feature changes

Output:

```python
class RiskSignalOutput(VersionedModel):
    candidates: list[RiskCandidate]
    ignored_signals: list[IgnoredSignal]
    confidence: float
```

Rules:

- Risk candidates are not verdicts.
- Must include evidence and affected scope.

## EvidenceVerifierAgent

Purpose:

- verify whether claims in findings and verdicts are supported by source evidence
- reject unsupported or overbroad claims

Output:

```python
class EvidenceVerificationOutput(VersionedModel):
    claim_id: str
    status: Literal["supported", "partially_supported", "unsupported", "contradicted"]
    supported_spans: list[UUID]
    missing_evidence: list[str]
    contradictions: list[UUID]
    confidence: float
```

## GraphBlastRadiusAgent

Purpose:

- query Neo4j to find downstream and upstream entities affected by a risk signal

Output:

```python
class BlastRadiusOutput(VersionedModel):
    root_graph_key: str
    affected_nodes: list[AffectedGraphNode]
    paths: list[RiskPath]
    path_query_name: str
    max_depth: int
    confidence: float
```

Rules:

- Must return path evidence and relationship confidence.
- Must distinguish direct, inferred, and weak paths.

## CriticAgent

Purpose:

- challenge extraction, risk, and verdict outputs
- identify unsupported causality, stale data, source bias, and overclaiming

Output:

```python
class CriticOutput(VersionedModel):
    target_id: UUID
    target_type: str
    decision: Literal["approve", "revise", "reject", "needs_human_review"]
    issues: list[CriticIssue]
    required_changes: list[str]
    confidence: float
```

## VerdictAgent

Purpose:

- synthesize risk signals, blast radius, evidence verification, critic feedback, and scoring into final risk verdicts

Output:

```python
class RiskVerdict(VersionedModel):
    risk_case_id: UUID
    verdict_type: Literal["confirmed_risk", "possible_risk", "watch", "dismissed", "resolved"]
    severity: Literal["critical", "high", "medium", "low", "info"]
    risk_score: float
    confidence: float
    summary: str
    key_drivers: list[str]
    affected_entities: list[AffectedEntity]
    evidence_span_ids: list[UUID]
    limitations: list[str]
    recommended_actions: list[str]
    next_review_at: datetime | None
```

Rules:

- Include limitations.
- No medical advice.
- No clinical decision guidance.

## InfraOpsAgent

Purpose:

- assist operators with Aiven MCP, local services, logs, metrics, failed topics, failed migrations, and dashboard provisioning

Output:

```python
class InfraOpsPlan(VersionedModel):
    requested_action: str
    environment: str
    safety_level: Literal["safe_read", "safe_write_dev", "migration_write", "production_change", "credential_access"]
    mcp_actions: list[MCPActionProposal]
    fallback_actions: list[FallbackAction]
    requires_approval: bool
    audit_reason: str
```

Rules:

- Never perform destructive action without approval.
- Prefer read-only MCP by default.
- Use fallbacks when MCP lacks capability.

## Typed Domain Models To Implement

Required model files:

- `models/source.py`: source configs, source runs, raw documents.
- `models/documents.py`: parsed documents, chunks, evidence spans.
- `models/extraction.py`: extraction outputs and entity mentions.
- `models/medical.py`: drugs, NDCs, ingredients, manufacturers, suppliers, facilities, devices.
- `models/events.py`: regulatory, recall, shortage, news, disaster, strike, price observations.
- `models/graph.py`: node and relationship upserts.
- `models/risk.py`: risk signals, candidates, findings, verdicts, alerts.
- `models/kafka.py`: event envelope.
- `models/infra.py`: Aiven MCP and infrastructure specs.

## Validation and Persistence

- Agent output validation failure marks run failed.
- Validated model dumps are stored in JSONB.
- Raw model output can be stored only for debugging and redacted where needed.
- Every agent run stores prompt hash, model, usage, start/end timestamps, status, and errors.
- Agent retries must use same idempotency key unless input changes.
