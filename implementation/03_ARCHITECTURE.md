# Architecture

## End-to-End Flow

```text
External sources
  -> source registry
  -> ingestion scheduler
  -> generic source adapters
  -> raw source/evidence database in PostgreSQL
  -> Kafka event backbone
  -> parsing and chunking
  -> Pydantic AI extraction agents
  -> entity resolution agents
  -> graph mapping agents
  -> Neo4j graph writer
  -> risk detection
  -> investigation swarm
  -> risk verdicts
  -> PostgreSQL/Kafka alerts
  -> Grafana dashboards
```

## Architectural Tenets

- Raw-first: no derived state exists without an immutable raw source record.
- Typed boundaries: API payloads, Kafka events, extraction outputs, graph upserts, and risk verdicts are Pydantic models.
- Idempotent writes: every source run, raw document, extraction run, graph upsert, risk case, and alert uses deterministic keys.
- Provenance everywhere: source URL, raw document, evidence span, extraction run, observed time, confidence, and method survive across PostgreSQL, Kafka, Neo4j, and Grafana.
- Local-first, cloud-ready: local compose runs everything except Aiven MCP; cloud mode swaps PostgreSQL/Kafka/Grafana to Aiven and later swaps Neo4j to Aura.
- MCP optional: Aiven MCP assists operations but the deployed application uses normal service clients.
- Human review by design: low-confidence matches, conflicts, unsupported conclusions, and destructive actions become review tasks.

## Service Boundaries

### Source Registry

Owns:

- `data_sources`
- source config validation
- source compliance notes
- parser profile registration
- schedule metadata

Primary APIs:

- `register_source(config)`
- `validate_source(config)`
- `list_sources(status, priority)`
- `get_source(source_id)`

### Ingestion Scheduler

Owns:

- schedule selection
- run creation
- cursor loading
- job event emission
- retry/backoff policy

It emits `ingest.jobs` and records `source_runs`.

### Source Adapters

Adapter categories:

- REST
- paginated REST
- RSS/Atom
- HTML scraping
- JavaScript-rendered scraping
- file download
- PDF/document
- manual seed
- webhook

Adapters fetch raw payloads, compute content hashes, store `raw_documents`, update cursors, and emit `ingest.raw_document_created`.

### Parser and Chunker

Converts raw payloads into normalized parsed documents and evidence-ready chunks:

- HTML -> readable text, tables, links, metadata
- JSON/XML/CSV -> structured records plus raw JSON fragments
- PDF/document -> pages, blocks, tables, OCR where needed
- RSS -> feed item records

It emits `ingest.document_parsed` and creates `document_chunks`.

### Extraction Agents

Pydantic AI agents convert parsed chunks into typed domain events and entities:

- medical entities
- regulatory events
- recalls
- shortages
- news events
- disaster events
- strike events
- price observations
- facility and supplier facts

Extraction creates `extraction_runs`, `evidence_spans`, `entity_mentions`, and emits `ingest.extraction_completed`.

### Entity Resolution

Resolves mentions into canonical entities using:

- deterministic identifiers
- normalized aliases
- `pg_trgm`
- pgvector
- graph context
- agent-assisted adjudication
- human review thresholds

It writes `canonical_entities`, `entity_aliases`, and review feedback requests.

### Graph Mapper and Writer

Maps canonical entities and events into Neo4j node/relationship upserts. The writer:

- validates graph upsert models
- uses idempotent `MERGE`
- applies constraints and indexes
- stores every relationship provenance property
- records `graph_upsert_audit`
- emits graph deadletter events for failed writes

### Risk Engine

Consumes graph, source, and event signals. Produces:

- risk candidates
- risk cases
- risk signals
- agent findings
- verdicts
- alerts

Risk scores are explainable weighted component scores with confidence adjustment and evidence.

### Investigation Swarm

Coordinates agents for deeper cases:

- RiskSignalAgent proposes candidate risk.
- GraphBlastRadiusAgent finds affected dependencies.
- EvidenceVerifierAgent checks source support.
- CriticAgent challenges weak claims.
- VerdictAgent emits final typed verdict.

All findings are stored in PostgreSQL and emitted through Kafka.

### Grafana Observability

Queries PostgreSQL first. Later can add Kafka lag, Neo4j metrics, Prometheus, and Aiven service metrics.

## Data Stores

### PostgreSQL

Primary durable system of record for:

- source registry
- raw source payloads
- parsed chunks
- evidence spans
- extraction runs
- entity metadata
- agent memory
- risk cases
- alerts
- audit logs
- pgvector search

Required extensions:

- `vector`
- `pg_trgm`
- `uuid-ossp` or application-generated UUIDv7

### Kafka

Backbone for:

- ingestion work
- raw document notifications
- extraction requests and completions
- graph upsert work
- risk cases and investigation tasks
- agent findings
- verdicts and alerts
- ops metrics/errors/audits

Kafka is not the system of record. It transports typed events with idempotency keys.

### Neo4j

Graph database for dependency, blast radius, and relationship queries:

- drugs to ingredients
- ingredients to inputs and commodities
- manufacturers to facilities
- facilities to locations and ports
- suppliers to downstream products
- events to affected entities
- risk cases to evidence and affected nodes

### Grafana

Initial dashboards use PostgreSQL as datasource. Aiven Grafana is preferred cloud target, local Grafana is fallback.

## Provider Configuration

LLM:

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_TIMEOUT_SECONDS`
- `LLM_MAX_RETRIES`
- `LLM_MAX_OUTPUT_TOKENS`

Embedding:

- `EMBEDDING_BASE_URL`
- `EMBEDDING_API_KEY`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIMENSIONS`

Infrastructure:

- `DATABASE_URL`
- `KAFKA_BOOTSTRAP_SERVERS`
- `KAFKA_SECURITY_PROTOCOL`
- `KAFKA_SASL_USERNAME`
- `KAFKA_SASL_PASSWORD`
- `KAFKA_CA_CERT_PATH`
- `NEO4J_URI`
- `NEO4J_USERNAME`
- `NEO4J_PASSWORD`
- `GRAFANA_URL`
- `GRAFANA_TOKEN`
- `AIVEN_PROJECT`
- `AIVEN_POSTGRES_SERVICE`
- `AIVEN_KAFKA_SERVICE`
- `AIVEN_GRAFANA_SERVICE`

## Runtime Processes

- `platform-cli`: operational CLI.
- `scheduler`: schedules source jobs.
- `ingester`: fetches raw documents.
- `parser`: parses and chunks raw documents.
- `extractor`: runs Pydantic AI extraction.
- `entity-resolver`: resolves mentions and entities.
- `graph-writer`: writes Neo4j upserts.
- `risk-engine`: creates risk candidates and risk cases.
- `agent-swarm`: runs multi-agent investigations.
- `alert-worker`: emits and stores alerts.
- `dashboard-provisioner`: generates/provisions Grafana JSON.

## Failure Model

- Source fetch failure: store `ingestion_errors`, update `source_health`, retry with backoff, emit `ops.errors`.
- Parse failure: keep raw document, store parser error, do not lose source.
- Extraction failure: create failed `extraction_runs`, retry only idempotently.
- Entity conflict: do not overwrite canonical record; create conflict and human review flag.
- Graph write failure: write `graph.deadletter`, preserve upsert payload and error.
- Risk failure: risk candidate remains pending or failed with reason.
- MCP failure: fall back to direct client or surface operator action.

## Deployment Shape

Local:

- Docker Compose: PostgreSQL, Redpanda/Kafka, Neo4j, Grafana.
- Python processes run from `uv`.

Cloud phase 1:

- Aiven PostgreSQL.
- Aiven Kafka.
- Aiven Grafana.
- Local or VM-hosted Neo4j.

Cloud phase 2:

- Aiven data services.
- Neo4j Aura.
- Application workers on container platform or Aiven application services if selected.

Cloud phase 3:

- Neo4j Aura Graph Analytics or GDS.
- Managed observability and alert routing.
- Private enterprise data connectors.
