CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS data_sources (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  source_id text NOT NULL UNIQUE,
  name text NOT NULL,
  source_type text NOT NULL,
  adapter_type text NOT NULL,
  base_url text,
  config jsonb NOT NULL,
  parser_profile text NOT NULL,
  priority text NOT NULL,
  cadence_seconds int,
  enabled boolean NOT NULL DEFAULT true,
  auth_ref text,
  rate_limit jsonb NOT NULL DEFAULT '{}'::jsonb,
  robots_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
  license_notes text,
  compliance_notes text,
  owner text,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_runs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  source_id text NOT NULL REFERENCES data_sources(source_id),
  run_type text NOT NULL,
  status text NOT NULL,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  cursor_before jsonb,
  cursor_after jsonb,
  documents_seen int NOT NULL DEFAULT 0,
  documents_created int NOT NULL DEFAULT 0,
  documents_unchanged int NOT NULL DEFAULT 0,
  error_count int NOT NULL DEFAULT 0,
  correlation_id uuid NOT NULL,
  idempotency_key text NOT NULL,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS source_cursors (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  source_id text NOT NULL REFERENCES data_sources(source_id),
  cursor_name text NOT NULL DEFAULT 'default',
  cursor_state jsonb NOT NULL,
  watermark timestamptz,
  etag text,
  last_content_hash text,
  updated_by_run_id uuid REFERENCES source_runs(id),
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, cursor_name)
);

CREATE TABLE IF NOT EXISTS raw_documents (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  source_id text NOT NULL REFERENCES data_sources(source_id),
  source_run_id uuid NOT NULL REFERENCES source_runs(id),
  source_url text,
  canonical_url text,
  request jsonb NOT NULL DEFAULT '{}'::jsonb,
  response_headers jsonb NOT NULL DEFAULT '{}'::jsonb,
  http_status int,
  content_type text,
  content_length bigint,
  content_hash text NOT NULL,
  payload_storage text NOT NULL,
  payload_bytes bytea,
  payload_text text,
  payload_uri text,
  source_published_at timestamptz,
  source_updated_at timestamptz,
  fetched_at timestamptz NOT NULL,
  dedupe_key text NOT NULL,
  raw_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, dedupe_key, content_hash)
);

CREATE TABLE IF NOT EXISTS document_chunks (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  raw_document_id uuid NOT NULL REFERENCES raw_documents(id),
  chunk_index int NOT NULL,
  chunk_type text NOT NULL,
  title text,
  text text NOT NULL,
  structured_data jsonb NOT NULL DEFAULT '{}'::jsonb,
  char_start int,
  char_end int,
  page_number int,
  section_path text[],
  embedding vector,
  embedding_model text,
  content_hash text NOT NULL,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (raw_document_id, chunk_index, content_hash)
);

CREATE TABLE IF NOT EXISTS extraction_runs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  raw_document_id uuid REFERENCES raw_documents(id),
  document_chunk_id uuid REFERENCES document_chunks(id),
  agent_name text NOT NULL,
  agent_version text NOT NULL,
  model_name text NOT NULL,
  prompt_hash text NOT NULL,
  input_hash text NOT NULL,
  output_schema text NOT NULL,
  output_schema_version int NOT NULL,
  status text NOT NULL,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  usage jsonb NOT NULL DEFAULT '{}'::jsonb,
  raw_output jsonb,
  validated_output jsonb,
  error text,
  correlation_id uuid NOT NULL,
  idempotency_key text NOT NULL,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (agent_name, agent_version, input_hash, prompt_hash, output_schema_version)
);

CREATE TABLE IF NOT EXISTS evidence_spans (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  raw_document_id uuid NOT NULL REFERENCES raw_documents(id),
  document_chunk_id uuid REFERENCES document_chunks(id),
  extraction_run_id uuid REFERENCES extraction_runs(id),
  source_id text NOT NULL,
  source_url text,
  quote text NOT NULL,
  normalized_text text,
  char_start int,
  char_end int,
  page_number int,
  table_ref jsonb,
  confidence numeric(5,4) NOT NULL,
  evidence_type text NOT NULL,
  hash text NOT NULL,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (raw_document_id, hash)
);

CREATE TABLE IF NOT EXISTS canonical_entities (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  entity_type text NOT NULL,
  canonical_key text NOT NULL,
  display_name text NOT NULL,
  normalized_name text NOT NULL,
  external_ids jsonb NOT NULL DEFAULT '{}'::jsonb,
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  embedding vector,
  embedding_model text,
  confidence numeric(5,4) NOT NULL DEFAULT 1.0,
  status text NOT NULL DEFAULT 'active',
  needs_review boolean NOT NULL DEFAULT false,
  review_reason text,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (entity_type, canonical_key)
);

CREATE TABLE IF NOT EXISTS entity_aliases (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  canonical_entity_id uuid NOT NULL REFERENCES canonical_entities(id),
  alias text NOT NULL,
  normalized_alias text NOT NULL,
  alias_type text NOT NULL,
  source_id text,
  evidence_span_id uuid REFERENCES evidence_spans(id),
  confidence numeric(5,4) NOT NULL,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (canonical_entity_id, normalized_alias, alias_type)
);

CREATE TABLE IF NOT EXISTS entity_mentions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  raw_document_id uuid NOT NULL REFERENCES raw_documents(id),
  document_chunk_id uuid REFERENCES document_chunks(id),
  extraction_run_id uuid REFERENCES extraction_runs(id),
  evidence_span_id uuid REFERENCES evidence_spans(id),
  entity_type text NOT NULL,
  mention_text text NOT NULL,
  normalized_mention text NOT NULL,
  candidate_external_ids jsonb NOT NULL DEFAULT '{}'::jsonb,
  canonical_entity_id uuid REFERENCES canonical_entities(id),
  resolution_status text NOT NULL,
  resolution_confidence numeric(5,4),
  resolution_method text,
  needs_review boolean NOT NULL DEFAULT false,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS graph_upsert_audit (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  event_id uuid,
  upsert_type text NOT NULL,
  graph_key text NOT NULL,
  neo4j_label_or_type text NOT NULL,
  payload jsonb NOT NULL,
  cypher_template text NOT NULL,
  status text NOT NULL,
  attempt int NOT NULL DEFAULT 1,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  neo4j_summary jsonb,
  error text,
  correlation_id uuid,
  idempotency_key text NOT NULL UNIQUE,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS risk_candidates (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  candidate_key text NOT NULL UNIQUE,
  risk_type text NOT NULL,
  scope jsonb NOT NULL,
  signals jsonb NOT NULL DEFAULT '[]'::jsonb,
  initial_score numeric(6,3) NOT NULL,
  confidence numeric(5,4) NOT NULL,
  evidence_span_ids uuid[] NOT NULL DEFAULT '{}',
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS risk_cases (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  case_key text NOT NULL UNIQUE,
  title text NOT NULL,
  risk_type text NOT NULL,
  scope_type text NOT NULL,
  scope_entity_id uuid REFERENCES canonical_entities(id),
  graph_node_key text,
  status text NOT NULL,
  severity text NOT NULL,
  risk_score numeric(6,3) NOT NULL,
  confidence numeric(5,4) NOT NULL,
  component_scores jsonb NOT NULL,
  opened_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  closed_at timestamptz,
  latest_verdict_id uuid,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS risk_feature_snapshots (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  risk_case_id uuid NOT NULL REFERENCES risk_cases(id),
  case_key text NOT NULL,
  scope_type text NOT NULL,
  scope_entity_id uuid REFERENCES canonical_entities(id),
  graph_node_key text,
  feature_name text NOT NULL,
  value numeric(12,4) NOT NULL,
  "window" text NOT NULL,
  evidence_span_ids uuid[] NOT NULL DEFAULT '{}',
  computed_at timestamptz NOT NULL,
  feature_version text NOT NULL,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (risk_case_id, feature_name, feature_version, "window")
);

CREATE TABLE IF NOT EXISTS risk_verdicts (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  risk_case_id uuid NOT NULL REFERENCES risk_cases(id),
  verdict_type text NOT NULL,
  severity text NOT NULL,
  risk_score numeric(6,3) NOT NULL,
  confidence numeric(5,4) NOT NULL,
  summary text NOT NULL,
  key_drivers jsonb NOT NULL DEFAULT '[]'::jsonb,
  affected_entities jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_span_ids uuid[] NOT NULL DEFAULT '{}',
  limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
  recommended_actions jsonb NOT NULL DEFAULT '[]'::jsonb,
  next_review_at timestamptz,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_findings (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  risk_case_id uuid REFERENCES risk_cases(id),
  agent_name text NOT NULL,
  agent_version text NOT NULL,
  finding_type text NOT NULL,
  finding jsonb NOT NULL,
  evidence_span_ids uuid[] NOT NULL DEFAULT '{}',
  confidence numeric(5,4) NOT NULL,
  critic_status text,
  status text NOT NULL,
  correlation_id uuid NOT NULL,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS risk_alerts (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  alert_key text NOT NULL UNIQUE,
  risk_case_id uuid REFERENCES risk_cases(id),
  alert_type text NOT NULL,
  severity text NOT NULL,
  status text NOT NULL,
  title text NOT NULL,
  body text NOT NULL,
  channels jsonb NOT NULL,
  payload jsonb NOT NULL,
  first_emitted_at timestamptz NOT NULL,
  last_emitted_at timestamptz NOT NULL,
  acknowledged_at timestamptz,
  resolved_at timestamptz,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS human_feedback (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  target_table text NOT NULL,
  target_id uuid NOT NULL,
  feedback_type text NOT NULL,
  decision text NOT NULL,
  comment text,
  reviewer text,
  before_value jsonb,
  after_value jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mcp_audit_log (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  controller text NOT NULL,
  action text NOT NULL,
  project text,
  service_name text,
  request jsonb NOT NULL,
  response_summary jsonb,
  status text NOT NULL,
  destructive boolean NOT NULL DEFAULT false,
  approval_id uuid,
  actor text,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  error text,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops_metrics (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  metric_name text NOT NULL,
  metric_value double precision NOT NULL,
  unit text,
  service text NOT NULL,
  source_id text,
  topic text,
  consumer_group text,
  correlation_id uuid,
  causation_id uuid,
  observed_at timestamptz NOT NULL,
  tags jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text NOT NULL UNIQUE,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingestion_errors (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  source_id text NOT NULL,
  source_run_id uuid REFERENCES source_runs(id),
  raw_document_id uuid REFERENCES raw_documents(id),
  stage text NOT NULL,
  error_type text NOT NULL,
  message text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  retryable boolean NOT NULL,
  occurred_at timestamptz NOT NULL,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS source_health (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  source_id text NOT NULL UNIQUE,
  status text NOT NULL,
  last_success_at timestamptz,
  last_failure_at timestamptz,
  consecutive_failures int NOT NULL DEFAULT 0,
  freshness_lag_seconds int,
  last_error_id uuid REFERENCES ingestion_errors(id),
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_memory (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  memory_type text NOT NULL,
  scope_type text NOT NULL,
  scope_key text NOT NULL,
  content text NOT NULL,
  structured_content jsonb NOT NULL DEFAULT '{}'::jsonb,
  embedding vector,
  embedding_model text,
  source_ref jsonb NOT NULL DEFAULT '{}'::jsonb,
  valid_from timestamptz,
  valid_to timestamptz,
  confidence numeric(5,4) NOT NULL,
  schema_version int NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS data_sources_enabled_priority_idx ON data_sources(enabled, priority);
CREATE INDEX IF NOT EXISTS data_sources_config_gin_idx ON data_sources USING gin(config);
CREATE INDEX IF NOT EXISTS source_runs_source_started_idx ON source_runs(source_id, started_at DESC);
CREATE INDEX IF NOT EXISTS source_cursors_watermark_idx ON source_cursors(watermark);
CREATE INDEX IF NOT EXISTS raw_documents_source_fetched_idx ON raw_documents(source_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS raw_documents_content_hash_idx ON raw_documents(content_hash);
CREATE INDEX IF NOT EXISTS document_chunks_text_trgm_idx ON document_chunks USING gin(text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS canonical_entities_name_trgm_idx ON canonical_entities USING gin(normalized_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS entity_aliases_alias_trgm_idx ON entity_aliases USING gin(normalized_alias gin_trgm_ops);
CREATE INDEX IF NOT EXISTS entity_mentions_mention_trgm_idx ON entity_mentions USING gin(normalized_mention gin_trgm_ops);
CREATE INDEX IF NOT EXISTS risk_candidates_type_score_idx ON risk_candidates(risk_type, initial_score DESC);
CREATE INDEX IF NOT EXISTS risk_candidates_scope_gin_idx ON risk_candidates USING gin(scope);
CREATE INDEX IF NOT EXISTS risk_candidates_signals_gin_idx ON risk_candidates USING gin(signals);
CREATE INDEX IF NOT EXISTS risk_cases_status_score_idx ON risk_cases(risk_type, status, risk_score DESC);
CREATE INDEX IF NOT EXISTS risk_feature_snapshots_case_feature_idx ON risk_feature_snapshots(risk_case_id, feature_name);
CREATE INDEX IF NOT EXISTS risk_feature_snapshots_case_key_idx ON risk_feature_snapshots(case_key);
CREATE INDEX IF NOT EXISTS risk_verdicts_case_created_idx ON risk_verdicts(risk_case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS mcp_audit_log_action_started_idx ON mcp_audit_log(action, started_at DESC);
CREATE INDEX IF NOT EXISTS mcp_audit_log_project_service_started_idx ON mcp_audit_log(project, service_name, started_at DESC);
CREATE INDEX IF NOT EXISTS mcp_audit_log_destructive_status_idx ON mcp_audit_log(destructive, status);
CREATE INDEX IF NOT EXISTS mcp_audit_log_request_gin_idx ON mcp_audit_log USING gin(request);
CREATE INDEX IF NOT EXISTS ops_metrics_name_observed_idx ON ops_metrics(metric_name, observed_at DESC);
CREATE INDEX IF NOT EXISTS ops_metrics_service_observed_idx ON ops_metrics(service, observed_at DESC);
CREATE INDEX IF NOT EXISTS ops_metrics_topic_observed_idx ON ops_metrics(topic, observed_at DESC);
CREATE INDEX IF NOT EXISTS ops_metrics_tags_gin_idx ON ops_metrics USING gin(tags);
