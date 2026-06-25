# PostgreSQL Data Model

PostgreSQL is the durable source/evidence, metadata, memory, vector search, risk, alert, and audit database. It must be queryable by Grafana and safe for replay/reprocessing.

## Extensions

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

If Aiven does not expose an extension on a selected plan or version, `bootstrap-infra` must fail clearly and record the missing capability. Do not silently disable vector or trigram functionality.

## Common Columns

Most tables should include:

- `id uuid primary key`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`
- `schema_version int not null`
- `metadata jsonb not null default '{}'::jsonb`

Prefer application-generated UUIDv7 or ULID for sortable IDs. If not available, use UUIDv4.

## Tables

### `data_sources`

Purpose: registry of all source definitions and compliance metadata.

Columns:

- `id uuid primary key`
- `source_id text not null unique`
- `name text not null`
- `source_type text not null`
- `adapter_type text not null`
- `base_url text`
- `config jsonb not null`
- `parser_profile text not null`
- `priority text not null`
- `cadence_seconds int`
- `enabled boolean not null default true`
- `auth_ref text`
- `rate_limit jsonb not null default '{}'::jsonb`
- `robots_policy jsonb not null default '{}'::jsonb`
- `license_notes text`
- `compliance_notes text`
- `owner text`
- common columns

Indexes:

- unique btree `(source_id)`
- btree `(enabled, priority)`
- GIN `(config)`

Idempotency:

- `source_id` is stable and human-readable.

### `source_runs`

Purpose: each scheduler or manual ingestion attempt.

Columns:

- `id uuid primary key`
- `source_id text not null references data_sources(source_id)`
- `run_type text not null` (`scheduled`, `manual`, `backfill`, `replay`, `test`)
- `status text not null`
- `started_at timestamptz not null`
- `finished_at timestamptz`
- `cursor_before jsonb`
- `cursor_after jsonb`
- `documents_seen int not null default 0`
- `documents_created int not null default 0`
- `documents_unchanged int not null default 0`
- `error_count int not null default 0`
- `correlation_id uuid not null`
- `idempotency_key text not null`
- common columns

Indexes:

- unique `(source_id, idempotency_key)`
- btree `(source_id, started_at desc)`
- btree `(status, started_at desc)`

### `source_cursors`

Purpose: current checkpoint per source and partition.

Columns:

- `id uuid primary key`
- `source_id text not null references data_sources(source_id)`
- `cursor_name text not null default 'default'`
- `cursor_state jsonb not null`
- `watermark timestamptz`
- `etag text`
- `last_content_hash text`
- `updated_by_run_id uuid references source_runs(id)`
- common columns

Indexes:

- unique `(source_id, cursor_name)`
- btree `(watermark)`

### `raw_documents`

Purpose: immutable raw payload storage metadata and optionally inline payloads.

Columns:

- `id uuid primary key`
- `source_id text not null references data_sources(source_id)`
- `source_run_id uuid not null references source_runs(id)`
- `source_url text`
- `canonical_url text`
- `request jsonb not null default '{}'::jsonb`
- `response_headers jsonb not null default '{}'::jsonb`
- `http_status int`
- `content_type text`
- `content_length bigint`
- `content_hash text not null`
- `payload_storage text not null` (`inline`, `filesystem`, `object_store`)
- `payload_bytes bytea`
- `payload_text text`
- `payload_uri text`
- `source_published_at timestamptz`
- `source_updated_at timestamptz`
- `fetched_at timestamptz not null`
- `dedupe_key text not null`
- `raw_metadata jsonb not null default '{}'::jsonb`
- common columns

Indexes:

- unique `(source_id, dedupe_key, content_hash)`
- btree `(source_id, fetched_at desc)`
- btree `(source_updated_at desc)`
- btree `(content_hash)`
- GIN `(raw_metadata)`

Idempotency:

- `dedupe_key` is source-specific stable identity.
- `content_hash` detects corrected-in-place documents.

### `document_chunks`

Purpose: parsed chunks suitable for evidence spans, retrieval, and extraction.

Columns:

- `id uuid primary key`
- `raw_document_id uuid not null references raw_documents(id)`
- `chunk_index int not null`
- `chunk_type text not null` (`text`, `table`, `json_fragment`, `html_section`, `pdf_page`, `rss_item`)
- `title text`
- `text text not null`
- `structured_data jsonb not null default '{}'::jsonb`
- `char_start int`
- `char_end int`
- `page_number int`
- `section_path text[]`
- `embedding vector`
- `embedding_model text`
- `content_hash text not null`
- common columns

Indexes:

- unique `(raw_document_id, chunk_index, content_hash)`
- btree `(raw_document_id, chunk_index)`
- GIN `(structured_data)`
- GIN `(text gin_trgm_ops)`
- HNSW or IVFFlat on `embedding` after dimensions are fixed.

### `extraction_runs`

Purpose: agent/model extraction execution records.

Columns:

- `id uuid primary key`
- `raw_document_id uuid references raw_documents(id)`
- `document_chunk_id uuid references document_chunks(id)`
- `agent_name text not null`
- `agent_version text not null`
- `model_name text not null`
- `prompt_hash text not null`
- `input_hash text not null`
- `output_schema text not null`
- `output_schema_version int not null`
- `status text not null`
- `started_at timestamptz not null`
- `finished_at timestamptz`
- `usage jsonb not null default '{}'::jsonb`
- `raw_output jsonb`
- `validated_output jsonb`
- `error text`
- `correlation_id uuid not null`
- `idempotency_key text not null`
- common columns

Indexes:

- unique `(agent_name, agent_version, input_hash, prompt_hash, output_schema_version)`
- btree `(status, started_at desc)`
- btree `(raw_document_id)`
- GIN `(validated_output)`

### `evidence_spans`

Purpose: exact evidence references in raw or parsed source content.

Columns:

- `id uuid primary key`
- `raw_document_id uuid not null references raw_documents(id)`
- `document_chunk_id uuid references document_chunks(id)`
- `extraction_run_id uuid references extraction_runs(id)`
- `source_id text not null`
- `source_url text`
- `quote text not null`
- `normalized_text text`
- `char_start int`
- `char_end int`
- `page_number int`
- `table_ref jsonb`
- `confidence numeric(5,4) not null`
- `evidence_type text not null`
- `hash text not null`
- common columns

Indexes:

- unique `(raw_document_id, hash)`
- btree `(extraction_run_id)`
- btree `(source_id, created_at desc)`
- GIN `(quote gin_trgm_ops)`

### `canonical_entities`

Purpose: canonical entity registry.

Columns:

- `id uuid primary key`
- `entity_type text not null`
- `canonical_key text not null`
- `display_name text not null`
- `normalized_name text not null`
- `external_ids jsonb not null default '{}'::jsonb`
- `attributes jsonb not null default '{}'::jsonb`
- `embedding vector`
- `embedding_model text`
- `confidence numeric(5,4) not null default 1.0`
- `status text not null default 'active'`
- `needs_review boolean not null default false`
- `review_reason text`
- common columns

Indexes:

- unique `(entity_type, canonical_key)`
- btree `(entity_type, normalized_name)`
- GIN `(external_ids)`
- GIN `(attributes)`
- GIN `(normalized_name gin_trgm_ops)`
- vector index on `embedding`

### `entity_aliases`

Purpose: aliases and normalized names for canonical entities.

Columns:

- `id uuid primary key`
- `canonical_entity_id uuid not null references canonical_entities(id)`
- `alias text not null`
- `normalized_alias text not null`
- `alias_type text not null`
- `source_id text`
- `evidence_span_id uuid references evidence_spans(id)`
- `confidence numeric(5,4) not null`
- common columns

Indexes:

- unique `(canonical_entity_id, normalized_alias, alias_type)`
- btree `(normalized_alias)`
- GIN `(normalized_alias gin_trgm_ops)`

### `entity_mentions`

Purpose: extracted mention instances before and after resolution.

Columns:

- `id uuid primary key`
- `raw_document_id uuid not null references raw_documents(id)`
- `document_chunk_id uuid references document_chunks(id)`
- `extraction_run_id uuid references extraction_runs(id)`
- `evidence_span_id uuid references evidence_spans(id)`
- `entity_type text not null`
- `mention_text text not null`
- `normalized_mention text not null`
- `candidate_external_ids jsonb not null default '{}'::jsonb`
- `canonical_entity_id uuid references canonical_entities(id)`
- `resolution_status text not null`
- `resolution_confidence numeric(5,4)`
- `resolution_method text`
- `needs_review boolean not null default false`
- common columns

Indexes:

- btree `(entity_type, normalized_mention)`
- btree `(canonical_entity_id)`
- GIN `(candidate_external_ids)`
- GIN `(normalized_mention gin_trgm_ops)`

### `graph_upsert_audit`

Purpose: exact audit of Neo4j writes.

Columns:

- `id uuid primary key`
- `event_id uuid`
- `upsert_type text not null` (`node`, `relationship`, `batch`)
- `graph_key text not null`
- `neo4j_label_or_type text not null`
- `payload jsonb not null`
- `cypher_template text not null`
- `status text not null`
- `attempt int not null default 1`
- `started_at timestamptz not null`
- `finished_at timestamptz`
- `neo4j_summary jsonb`
- `error text`
- `correlation_id uuid`
- `idempotency_key text not null`
- common columns

Indexes:

- unique `(idempotency_key)`
- btree `(graph_key)`
- btree `(status, started_at desc)`
- GIN `(payload)`

### `risk_cases`

Purpose: tracked risk investigations.

Columns:

- `id uuid primary key`
- `case_key text not null unique`
- `title text not null`
- `risk_type text not null`
- `scope_type text not null`
- `scope_entity_id uuid references canonical_entities(id)`
- `graph_node_key text`
- `status text not null`
- `severity text not null`
- `risk_score numeric(6,3) not null`
- `confidence numeric(5,4) not null`
- `component_scores jsonb not null`
- `opened_at timestamptz not null`
- `updated_at timestamptz not null`
- `closed_at timestamptz`
- `latest_verdict_id uuid`
- common columns

Indexes:

- unique `(case_key)`
- btree `(risk_type, status, risk_score desc)`
- btree `(scope_entity_id)`
- GIN `(component_scores)`

### `risk_candidates`

Purpose: initial scored risk signals produced before durable case lifecycle records.

Columns:

- `id uuid primary key`
- `candidate_key text not null unique`
- `risk_type text not null`
- `scope jsonb not null`
- `signals jsonb not null default '[]'::jsonb`
- `initial_score numeric(6,3) not null`
- `confidence numeric(5,4) not null`
- `evidence_span_ids uuid[] not null default '{}'`
- common columns

Indexes:

- unique `(candidate_key)`
- btree `(risk_type, initial_score desc)`
- GIN `(scope)`
- GIN `(signals)`

### `agent_findings`

Purpose: typed findings produced by agents.

Columns:

- `id uuid primary key`
- `risk_case_id uuid references risk_cases(id)`
- `agent_name text not null`
- `agent_version text not null`
- `finding_type text not null`
- `finding jsonb not null`
- `evidence_span_ids uuid[] not null default '{}'`
- `confidence numeric(5,4) not null`
- `critic_status text`
- `status text not null`
- `correlation_id uuid not null`
- common columns

Indexes:

- btree `(risk_case_id, created_at desc)`
- btree `(agent_name, finding_type)`
- GIN `(finding)`

### `risk_alerts`

Purpose: emitted alert records.

Columns:

- `id uuid primary key`
- `alert_key text not null unique`
- `risk_case_id uuid references risk_cases(id)`
- `alert_type text not null`
- `severity text not null`
- `status text not null`
- `title text not null`
- `body text not null`
- `channels jsonb not null`
- `payload jsonb not null`
- `first_emitted_at timestamptz not null`
- `last_emitted_at timestamptz not null`
- `acknowledged_at timestamptz`
- `resolved_at timestamptz`
- common columns

Indexes:

- unique `(alert_key)`
- btree `(status, severity, last_emitted_at desc)`
- btree `(risk_case_id)`

### `human_review_queue`

Purpose: pending and resolved human-review tasks for low-confidence, conflicting, or high-impact sparse evidence.

Columns:

- `id uuid primary key`
- `target_table text not null`
- `target_id uuid not null`
- `review_type text not null`
- `reason text not null`
- `status text not null`
- `priority text not null`
- `evidence_span_ids uuid[] not null default '{}'`
- common columns

Indexes:

- unique `(target_table, target_id)`
- btree `(status, priority, created_at desc)`
- btree `(target_table, target_id)`
- gin `(evidence_span_ids)`

### `human_feedback`

Purpose: review and correction loop.

Columns:

- `id uuid primary key`
- `target_table text not null`
- `target_id uuid not null`
- `feedback_type text not null`
- `decision text not null`
- `comment text`
- `reviewer text`
- `before_value jsonb`
- `after_value jsonb`
- `created_at timestamptz not null default now()`
- `metadata jsonb not null default '{}'::jsonb`

Indexes:

- btree `(target_table, target_id)`
- btree `(feedback_type, created_at desc)`

### `mcp_audit_log`

Purpose: full MCP action audit.

Columns:

- `id uuid primary key`
- `controller text not null`
- `action text not null`
- `project text`
- `service_name text`
- `request jsonb not null`
- `response_summary jsonb`
- `status text not null`
- `destructive boolean not null default false`
- `approval_id uuid`
- `actor text`
- `started_at timestamptz not null`
- `finished_at timestamptz`
- `error text`
- common columns

Indexes:

- btree `(action, started_at desc)`
- btree `(project, service_name, started_at desc)`
- btree `(destructive, status)`
- GIN `(request)`

### `ops_metrics`

Purpose: lightweight service and event telemetry for Grafana and replay-safe operational analysis.

Columns:

- `id uuid primary key`
- `metric_name text not null`
- `metric_value double precision not null`
- `unit text`
- `service text not null`
- `source_id text`
- `topic text`
- `consumer_group text`
- `correlation_id uuid`
- `causation_id uuid`
- `observed_at timestamptz not null`
- `tags jsonb not null default '{}'::jsonb`
- `idempotency_key text not null unique`
- common columns

Indexes:

- unique `(idempotency_key)`
- btree `(metric_name, observed_at desc)`
- btree `(service, observed_at desc)`
- btree `(topic, observed_at desc)`
- GIN `(tags)`

### `ingestion_errors`

Purpose: source, adapter, parser, and storage errors.

Columns:

- `id uuid primary key`
- `source_id text not null`
- `source_run_id uuid references source_runs(id)`
- `raw_document_id uuid references raw_documents(id)`
- `stage text not null`
- `error_type text not null`
- `message text not null`
- `details jsonb not null default '{}'::jsonb`
- `retryable boolean not null`
- `occurred_at timestamptz not null`
- common columns

Indexes:

- btree `(source_id, occurred_at desc)`
- btree `(stage, retryable, occurred_at desc)`

### `source_health`

Purpose: current source health for dashboards.

Columns:

- `id uuid primary key`
- `source_id text not null unique`
- `status text not null`
- `last_success_at timestamptz`
- `last_failure_at timestamptz`
- `consecutive_failures int not null default 0`
- `freshness_lag_seconds int`
- `last_error_id uuid references ingestion_errors(id)`
- `metrics jsonb not null default '{}'::jsonb`
- common columns

Indexes:

- unique `(source_id)`
- btree `(status, last_success_at desc)`

### `agent_memory`

Purpose: durable agent memory and reusable observations.

Columns:

- `id uuid primary key`
- `memory_type text not null`
- `scope_type text not null`
- `scope_key text not null`
- `content text not null`
- `structured_content jsonb not null default '{}'::jsonb`
- `embedding vector`
- `embedding_model text`
- `source_ref jsonb not null default '{}'::jsonb`
- `valid_from timestamptz`
- `valid_to timestamptz`
- `confidence numeric(5,4) not null`
- common columns

Indexes:

- btree `(memory_type, scope_type, scope_key)`
- GIN `(structured_content)`
- vector index on `embedding`

## JSONB Usage

Use JSONB for:

- source-specific raw metadata
- config blobs
- request/response headers
- extraction validated outputs
- agent findings
- risk component scores
- source health metrics

Do not use JSONB as an excuse to skip typed Pydantic models. JSONB stores validated model dumps with schema versions.

## pgvector Usage

Use vectors for:

- document chunk semantic retrieval
- entity name/context embeddings
- agent memory retrieval

Initial index choice:

- HNSW for interactive similarity search once dimensions are fixed.
- Exact scan before data is large or while validating recall.

## pg_trgm Usage

Use `pg_trgm` for:

- normalized entity mention matching
- alias search
- source title/name search
- evidence quote search

Apply trigram indexes on normalized text fields used in entity resolution.

## Idempotency Rules

- Every Kafka event has `idempotency_key`.
- `raw_documents` uniqueness is `(source_id, dedupe_key, content_hash)`.
- `extraction_runs` uniqueness is `(agent_name, agent_version, input_hash, prompt_hash, output_schema_version)`.
- `canonical_entities` uniqueness is `(entity_type, canonical_key)`.
- `graph_upsert_audit` uniqueness is `idempotency_key`.
- `risk_cases` uniqueness is `case_key`.
- `risk_alerts` uniqueness is `alert_key`.

## Migration Strategy

- Use Alembic or equivalent SQL migrations.
- Each migration has an irreversible-risk note.
- Extensions are migration 0001.
- Tables are grouped by source/evidence, extraction/entity, graph/risk, audit/ops.
- Indexes that require long builds are separate migrations with concurrent build support where PostgreSQL permits it.
