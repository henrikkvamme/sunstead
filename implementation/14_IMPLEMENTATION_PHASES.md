# Implementation Phases

These phases are practical execution slices. Do not re-plan the product unless blocked by a verified external constraint.

## Phase 0: Repository and Tooling

Deliverables:

- `pyproject.toml`
- Python package skeleton
- settings and logging
- CLI shell
- `.env.example`
- local test config
- ruff, mypy/pyright, pytest

Done when:

- `uv run platform --help` works.
- `uv run ruff check .` works.
- `uv run pytest` runs empty or basic tests.

## Phase 1: Local Infrastructure

Deliverables:

- Docker Compose for PostgreSQL, Redpanda/Kafka, Neo4j, Grafana.
- `bootstrap-infra --mode local`
- `init-db`
- `init-kafka`
- `init-neo4j`
- Grafana datasource local provisioning.

Done when:

- local stack starts.
- PostgreSQL extensions are installed.
- all Kafka topics exist.
- Neo4j constraints exist.
- Grafana can query PostgreSQL.

## Phase 2: PostgreSQL Evidence Schema

Deliverables:

- migrations for tables in `04_DATA_MODEL_POSTGRES.md`.
- repository layer.
- idempotency helpers.
- audit helpers.

Done when:

- migrations run cleanly up/down where safe.
- tables and indexes exist.
- tests cover idempotent raw document and source run writes.

## Phase 3: Kafka Event Backbone

Deliverables:

- event envelope models.
- topic spec file.
- producer/consumer abstractions.
- deadletter support.
- JSON schema export from Pydantic models.

Done when:

- events validate on produce/consume.
- consumer commits after durable side effects.
- deadletter path is tested.

## Phase 4: Source Registry and Ingestion

Deliverables:

- source config models.
- registry commands.
- scheduler.
- REST, paginated REST, RSS, HTML, file download, PDF/document, manual seed adapters.
- cursor and dedupe logic.
- initial configs for openFDA NDC, openFDA enforcement, FDA shortages, device registration/listing, and device enforcement.

Done when:

- `validate-source` passes for initial sources.
- `test-fetch` works.
- `ingest-once` stores raw documents.
- `ingest.raw_document_created` events are emitted.

## Phase 5: Parsing, Chunking, and Evidence

Deliverables:

- parser profiles.
- chunk creation.
- evidence span locator helpers.
- embeddings for chunks where configured.

Done when:

- raw documents parse into chunks.
- chunks link back to raw documents.
- fixtures validate expected chunks.

## Phase 6: Pydantic AI Extraction

Deliverables:

- model factory.
- `MedicalExtractionAgent`.
- extraction run storage.
- typed extraction output models.
- retry and validation handling.

Done when:

- sample source chunks produce validated outputs.
- extraction failures are persisted.
- evidence spans are created.

## Phase 7: Entity Resolution

Deliverables:

- deterministic matcher.
- alias matcher.
- trigram matcher.
- vector matcher.
- graph-context hook.
- agent-assisted review for uncertain cases.
- human review queue records.

Done when:

- canonical entities and aliases are created.
- ambiguous cases are not auto-merged.
- test fixtures cover false positives and conflicts.

## Phase 8: Graph Mapping and Neo4j Writer

Deliverables:

- graph upsert models.
- graph mapping agent.
- Neo4j client.
- graph writer consumer.
- query library.
- graph upsert audit.

Done when:

- graph nodes and relationships are idempotently written.
- relationship provenance fields are present.
- replay from PostgreSQL audit is possible.

## Phase 9: Transparent Risk Engine

Deliverables:

- scoring components.
- risk candidate creation.
- risk case lifecycle.
- risk alerts.
- `explain-case`.

Done when:

- shortage/recall/regulatory/disaster examples create explainable cases.
- component scores and evidence are visible.
- alerts are idempotent.

## Phase 10: Investigation Swarm

Deliverables:

- RiskSignalAgent.
- EvidenceVerifierAgent.
- GraphBlastRadiusAgent.
- CriticAgent.
- VerdictAgent.
- swarm coordinator.

Done when:

- a risk case can be investigated end to end.
- critic/evidence verification can revise or reject weak findings.
- verdicts are persisted and emitted.

## Phase 11: Grafana Dashboards

Deliverables:

- dashboard definitions.
- generated JSON.
- local provisioning.
- Aiven Grafana provisioning path.
- SQL queries for required dashboards.

Done when:

- local Grafana displays dashboards from PostgreSQL.
- dashboard generation is repeatable.

## Phase 12: Aiven Cloud Path

Deliverables:

- AivenMCPController.
- direct Aiven/API/client fallbacks.
- cloud bootstrap.
- Aiven PostgreSQL/Kafka/Grafana docs.
- secret/TLS handling.

Done when:

- cloud bootstrap can discover services.
- topic and migration bootstrap works where permissions allow.
- missing MCP capabilities fall back cleanly.

## Phase 13: Hardening

Deliverables:

- governance gates.
- source compliance validation.
- load/backfill tests.
- retry/backoff tuning.
- docs/runbooks.
- deployment notes.

Done when:

- tests pass.
- docs explain local and cloud operation.
- risky operations require approval.

## Dependency Graph

```text
tooling
  -> local infra
  -> postgres schema
  -> kafka backbone
  -> source registry
  -> ingestion
  -> parsing/evidence
  -> extraction
  -> entity resolution
  -> graph writer
  -> risk engine
  -> investigation swarm
  -> grafana dashboards
  -> aiven cloud path
  -> hardening
```

## First End-to-End Slice

Use this as the first vertical product slice:

1. openFDA Drug NDC ingestion.
2. raw JSON storage.
3. parser chunks per NDC record.
4. extraction of drug, NDC, active ingredient, labeler/manufacturer.
5. entity resolution.
6. Neo4j graph: `Drug` - `HAS_NDC` -> `NDC`, `Drug` - `CONTAINS_ACTIVE_INGREDIENT` -> `ActiveIngredient`, `Manufacturer` - `LABELS` -> `Drug`.
7. Grafana source freshness and graph growth.

Then add drug enforcement recalls and create the first recall/quality risk case.
