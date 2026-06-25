# Platform Runbook

This runbook covers the current local-first implementation of the unnamed platform.

## Local Verification

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/supply_intel
uv run pytest
vp check
vp test
```

Run `vp build` only when frontend or build behavior changes.

## Demo Readiness

Before a demo, run the typed readiness report:

```bash
uv run platform demo-readiness
uv run platform demo-readiness --local-graph --data-dir /tmp/platform-ndc
uv run platform demo-readiness --live-neo4j
uv run platform demo-readiness --aiven-defaults --live-neo4j
```

The report separates the minimum demo path from the polished cloud path. The
minimum path can use deterministic typed extraction and checked-in source
fixtures. The polished cloud path needs Aiven PostgreSQL/Kafka secrets, a
Grafana token, and the source credentials listed in
`missing_live_source_credentials`. The report only prints whether credentials are
configured; it does not print secret values. `--aiven-defaults` fills conventional
local paths such as `.platform-secrets/aiven/postgres-url`,
`.platform-secrets/aiven/project-ca.pem`, `.platform-secrets/aiven/kafka-service.cert`,
and `.platform-secrets/aiven/kafka-service.key` when the matching env vars are
not exported. If `.platform-secrets/aiven/kafka-bootstrap`,
`.platform-secrets/aiven/grafana-url`, or `.platform-secrets/aiven/postgres-host`
exist, those non-secret endpoint values are used too.

Use `--local-graph` after `refresh-demo-data` to verify the file-backed graph
path without starting Neo4j. Use `--live-neo4j` after graph replay to verify
the live graph database.

For the repeatable local demo path, run the one-command preparation flow. It
refreshes fixture-backed source evidence, exports the frontend graph snapshot,
records file-backed graph growth metrics, and returns a readiness report:

```bash
uv run platform prepare-demo \
  --data-dir /tmp/platform-ndc \
  --source-id openfda_drug_ndc \
  --source-id fda_drug_shortages \
  --snapshot-output public/platform-demo/supply-chain-graph.json \
  --max-documents-per-source 1 \
  --require-ready
```

The command is deterministic and does not require Neo4j to be running. After a
Neo4j replay, refresh `public/platform-demo/supply-chain-graph.json` with
`export-graph-snapshot --source neo4j` when the frontend should show live graph
database counts.

For a fast deterministic demo refresh, build a multi-source local evidence set
from checked-in fixtures. This runs raw-first ingestion, parsing, evidence spans,
typed extraction, entity resolution, graph upserts, and risk case generation for
the selected sources:

```bash
uv run platform refresh-demo-data \
  --data-dir /tmp/platform-ndc \
  --source-id openfda_drug_ndc \
  --source-id openfda_drug_enforcement \
  --source-id fda_drug_shortages \
  --source-id gdelt_doc_search \
  --max-documents-per-source 1
```

Use `--priority P0 --priority P1` instead of explicit `--source-id` to refresh a
broader fixture-backed set. The command prints cumulative evidence-store counts,
Kafka event-topic counts, and the next graph writer/snapshot commands.

## Large Graph Backfill

Use `backfill-graph` when the graph needs to grow past the fixture demo into a
larger local evidence set. Fixture mode is deterministic and useful for smoke
tests; live mode fetches public/configured source endpoints, checkpoints source
cursors, and stops when the local graph store reaches the requested unique node
count.

Fast local smoke:

```bash
uv run platform backfill-graph \
  --mode fixture \
  --data-dir /tmp/platform-large-graph \
  --source-id openfda_drug_ndc \
  --source-id fda_drug_shortages \
  --target-graph-nodes 7 \
  --max-documents-per-source 1 \
  --max-rounds 2
```

Large live backfill for the supply-chain dashboard:

```bash
uv run platform backfill-graph \
  --mode live \
  --data-dir /tmp/platform-large-graph \
  --source-id openfda_drug_ndc \
  --source-id openfda_drug_enforcement \
  --source-id openfda_device_registrationlisting \
  --source-id openfda_device_enforcement \
  --source-id fda_drug_shortages \
  --source-id gdelt_doc_search \
  --target-graph-nodes 10000 \
  --max-documents-per-source 1000 \
  --max-rounds 10 \
  --snapshot-limit 5000
```

The command returns cumulative graph counts, per-source run deltas, event-topic
counts, and next-step commands. The important follow-ups are:

```bash
uv run platform sync-graph-view \
  --data-dir /tmp/platform-large-graph \
  --apply-neo4j \
  --snapshot-source neo4j \
  --output public/platform-demo/supply-chain-graph.json \
  --limit 5000

uv run platform sync-postgres-evidence --data-dir /tmp/platform-large-graph --apply --aiven-defaults
```

`sync-graph-view` is the operator shortcut that makes the local graph visible:
it can replay graph upserts into Neo4j, record graph growth metrics, and export
the dashboard snapshot in one command. Without this step, Neo4j Browser still
shows the previous graph even if the local backfill has written many
`graph_node_upserts` and `graph_relationship_upserts`.

Use a fresh `--data-dir` for a clean large run. Reusing a previous data
directory resumes source cursors and preserves existing graph nodes, which is
useful for continuing an interrupted backfill but can make growth look smaller
than the document count.

For interactive demo prep, prefer smaller live batches that can be materialized
between runs:

```bash
uv run platform backfill-graph \
  --mode live \
  --data-dir /tmp/platform-large-graph \
  --priority P0 \
  --target-graph-nodes 10000 \
  --max-documents-per-source 200 \
  --max-rounds 1

uv run platform sync-graph-view \
  --data-dir /tmp/platform-large-graph \
  --apply-neo4j \
  --snapshot-source neo4j \
  --output public/platform-demo/supply-chain-graph.json \
  --limit 5000

uv run platform graph-insights \
  --data-dir /tmp/platform-large-graph \
  --top 10
```

Repeat those two commands until the Neo4j metrics report the target graph size.
Use `graph-insights` before a demo to pick entry points: it reports label and
relationship coverage, high-degree graph hubs, source/risk coverage, provenance
coverage, and ready-to-run Cypher queries for Neo4j Browser.

## Agent Runtime Configuration

The platform runs in deterministic mode when `LLM_BASE_URL`, `LLM_API_KEY` or
`LLM_API_KEY_FILE`, and `LLM_MODEL` are unset. In that mode
`ModelFactory.runtime_metadata()` reports `provider=deterministic`, deterministic
extractors and replay paths keep working, and no placeholder model client is
constructed.

Live typed agents require all three LLM settings. `ModelFactory` builds an
OpenAI-compatible `OpenAIProvider`, `OpenAIChatModel`, and `Agent` with the
requested Pydantic output model, then applies `LLM_OUTPUT_MODE`,
`LLM_MAX_RETRIES`, and `LLM_MAX_OUTPUT_TOKENS` through Pydantic AI usage
limits. `LLM_OUTPUT_MODE=tool` uses tool-call structured output,
`LLM_OUTPUT_MODE=prompted` embeds the schema in the prompt for broader
OpenAI-compatible model support, and `LLM_OUTPUT_MODE=native` asks the provider
for native structured output. Missing live-agent settings fail closed with the
missing env names only; runtime metadata records whether base URLs and API keys
are configured without printing secret values.

Use a single structured provider smoke before relying on a new model:

```bash
uv run platform llm-smoke
```

Embedding configuration is tracked separately through `EMBEDDING_BASE_URL`,
`EMBEDDING_API_KEY` or `EMBEDDING_API_KEY_FILE`, `EMBEDDING_MODEL`, and
`EMBEDDING_DIMENSIONS`. The current runtime metadata exposes readiness for
embedding-backed features without requiring embeddings for deterministic
ingestion, extraction, graph mapping, or risk scoring. When all embedding
settings are configured, chunk parsing calls the OpenAI-compatible
`/embeddings` endpoint, stores the returned vector and `embedding_model` on
`document_chunks`, and syncs that value into PostgreSQL's pgvector column.
Provider errors or dimension mismatches fail the source run instead of silently
writing partially embedded chunks.

## Local Infrastructure

Local infrastructure specs are checked in and can be inspected without starting services.

Files:

- `infra/docker-compose.yml`: PostgreSQL with pgvector, Redpanda, Neo4j, Grafana.
- `migrations/0001_extensions_and_evidence_schema.sql`: PostgreSQL source/evidence schema.
- `cypher/migrations/0001_constraints.cypher`: Neo4j constraints and indexes.
- `infra/kafka/topics.yaml`: required Kafka topics.
- `infra/grafana/provisioning/`: local Grafana PostgreSQL datasource and dashboard provider.
- `dashboards/generated/`: Grafana dashboard JSON mounted into local Grafana.

Inspect bootstrap assets:

```bash
uv run platform bootstrap-infra --mode local
uv run platform init-db
uv run platform init-kafka
uv run platform init-neo4j
```

Start the local Docker Compose infrastructure explicitly when Docker is available:

```bash
uv run platform bootstrap-infra --mode local --apply
```

The apply form runs `docker compose -f infra/docker-compose.yml up -d postgres redpanda neo4j grafana` and returns the command, exit status, stdout, and stderr. If image pulls fail or hang, start the unavailable services manually with the same compose file and rerun the relevant `init-*` commands.

Plan cloud or hybrid Aiven bootstrap without touching cloud resources:

```bash
uv run platform bootstrap-infra --mode hybrid --project <aiven-project> \
  --postgres-service <pg-service> \
  --kafka-service <kafka-service> \
  --grafana-service <grafana-service>
```

The cloud plan lists read-only discovery actions, PostgreSQL extension verification, migration/topic/dashboard bootstrap actions, required decisions, approval status, and direct-client fallback commands. Use `--record-audit` to persist the dry-run MCP action plan to `DATA_DIR/mcp_audit_log.jsonl`. Production and shared-environment migration writes remain `requires_approval` until an `--approval-id` is supplied.

When MCP is unavailable, the direct `AivenApiController` can perform safe project and service discovery with `AIVEN_API_TOKEN`, `AIVEN_API_BASE_URL`, and `AIVEN_API_AUTH_SCHEME`. Discovery calls automatically write `aiven_api` audit records when an audit sink is configured. The controller intentionally fails closed for service creation, topic creation, credential-adjacent operations, metrics, and logs; those paths stay behind the cloud bootstrap approval plan, direct PostgreSQL/Kafka/Grafana clients, or explicit log/metrics integrations.

`init-kafka` is a dry-run by default and prints the exact topic plan, including cleanup policy and retention:

```bash
uv run platform init-kafka
```

Create or ensure topics through the direct Kafka AdminClient when a broker is available:

```bash
uv run platform init-kafka --apply --backend direct
```

Apply PostgreSQL migrations to `DATABASE_URL` when the local or cloud database is available:

```bash
uv run platform init-db --apply
```

The migration runner records checksums in `schema_migrations` and fails if an already-applied migration changes.

Apply Neo4j constraints and indexes to `NEO4J_URI` when Neo4j is available:

```bash
uv run platform init-neo4j --apply
```

## Source Validation

Validate source configs before registration or ingestion:

```bash
uv run platform validate-source sources/openfda_drug_ndc.yaml
uv run platform validate-source sources/openfda_drug_enforcement.yaml
uv run platform validate-source sources/fda_warning_letters.yaml
uv run platform validate-source sources/fda_inspections_dashboard.yaml
uv run platform validate-source sources/gdelt_doc_search.yaml
uv run platform validate-source sources/gdacs_events.yaml
uv run platform validate-source sources/reliefweb_reports.yaml
uv run platform validate-source sources/worldbank_commodity_prices.yaml
uv run platform validate-source sources/eia_energy_prices.yaml
uv run platform validate-source sources/sec_edgar_supplier_filings.yaml
uv run platform validate-source sources/un_comtrade_trade_flows.yaml
uv run platform validate-source sources/freight_proxy_prices.yaml
uv run platform validate-source sources/search_trend_signals.yaml
```

Source configs must not include literal secrets. API keys are referenced by env vars such as `OPENFDA_API_KEY`, `EIA_API_KEY`, and `UN_COMTRADE_API_KEY`. HTTP source configs must declare a `User-Agent`, rate limit and burst settings, robots or API terms notes, data minimization notes, and retention notes before registration or ingestion.

Runtime adapters currently cover paginated REST, single-request REST, RSS/Atom feeds, HTML scraping, file downloads, PDF documents, and manual seed files. RSS/Atom fetching uses conditional request headers when cursor ETag or Last-Modified state is available, and emits one raw payload per feed entry for stable dedupe/provenance. File downloads preserve raw bytes in `payload_bytes` while still hashing the original body for dedupe. PDF document sources additionally extract page text into `payload_text` while retaining the original PDF bytes. Manual seed sources read checked-in JSON or JSONL files and emit one raw payload per seed record.

Use the source credential report before a live demo:

```bash
uv run platform source-credentials
uv run platform source-credentials --only-missing
```

The report groups checked-in source configs by auth env var, shows whether each value is configured, and includes acquisition URLs and demo priority without printing secret values. Source credentials can be configured either directly through env vars or through file-backed settings:

```bash
OPENFDA_API_KEY_FILE=.platform-secrets/sources/openfda-api-key
EIA_API_KEY_FILE=.platform-secrets/sources/eia-api-key
UN_COMTRADE_API_KEY_FILE=.platform-secrets/sources/un-comtrade-api-key
RELIEFWEB_APPNAME_FILE=.platform-secrets/sources/reliefweb-appname
```

Live REST fetches redact query-param auth values in diagnostic `source_url` values before printing or storing raw-document provenance.

Inspect planned fetch metadata without network access:

```bash
uv run platform test-fetch openfda_drug_ndc --limit 2
```

Fetch a bounded live source sample without storing it:

```bash
uv run platform test-fetch openfda_drug_ndc --limit 2 --live
```

Register source definitions locally for fixture work, or into PostgreSQL after migrations have been applied:

```bash
uv run platform register-source sources/openfda_drug_ndc.yaml
uv run platform register-source sources/openfda_drug_ndc.yaml --backend postgres
```

## Fixture Ingestion

The first deterministic, raw-first slices can run without network or service credentials:

```bash
DATA_DIR=/tmp/platform-ndc uv run platform ingest-once openfda_drug_ndc --max-documents 1
DATA_DIR=/tmp/platform-enforcement uv run platform ingest-once openfda_drug_enforcement --max-documents 1
DATA_DIR=/tmp/platform-shortages uv run platform ingest-once fda_drug_shortages --max-documents 1
DATA_DIR=/tmp/platform-device-registration uv run platform ingest-once openfda_device_registrationlisting --max-documents 1
DATA_DIR=/tmp/platform-device-enforcement uv run platform ingest-once openfda_device_enforcement --max-documents 1
DATA_DIR=/tmp/platform-warning-letters uv run platform ingest-once fda_warning_letters --max-documents 1
DATA_DIR=/tmp/platform-inspections uv run platform ingest-once fda_inspections_dashboard --max-documents 1
DATA_DIR=/tmp/platform-gdelt uv run platform ingest-once gdelt_doc_search --max-documents 1
DATA_DIR=/tmp/platform-gdacs uv run platform ingest-once gdacs_events --max-documents 1
DATA_DIR=/tmp/platform-reliefweb uv run platform ingest-once reliefweb_reports --max-documents 1
DATA_DIR=/tmp/platform-worldbank uv run platform ingest-once worldbank_commodity_prices --max-documents 1
DATA_DIR=/tmp/platform-eia uv run platform ingest-once eia_energy_prices --max-documents 1
DATA_DIR=/tmp/platform-sec uv run platform ingest-once sec_edgar_supplier_filings --max-documents 1
DATA_DIR=/tmp/platform-comtrade uv run platform ingest-once un_comtrade_trade_flows --max-documents 1
DATA_DIR=/tmp/platform-freight-proxy uv run platform ingest-once freight_proxy_prices --max-documents 1
DATA_DIR=/tmp/platform-search-trends uv run platform ingest-once search_trend_signals --max-documents 1
```

Outputs are JSONL collections under `DATA_DIR`, including raw documents, chunks, evidence spans, extraction runs, graph upserts, risk candidates, risk cases, risk feature snapshots, verdicts, alerts, and validated Kafka-style event envelopes.

Completed source runs also refresh `source_health.jsonl` locally, or the `source_health` table when using PostgreSQL, so the source freshness dashboard has current status, success/failure timestamps, freshness lag, and failure streaks.

Run bounded live ingestion explicitly:

```bash
DATA_DIR=/tmp/platform-ndc-live uv run platform ingest-once openfda_drug_ndc --max-documents 5 --live
DATA_DIR=/tmp/platform-device-registration-live uv run platform ingest-once openfda_device_registrationlisting --max-documents 1 --live
PLATFORM_USER_AGENT='unnamed-platform-dev/0.1 ops@example.com' DATA_DIR=/tmp/platform-sec-live uv run platform ingest-once sec_edgar_supplier_filings --max-documents 1 --live
EIA_API_KEY=... DATA_DIR=/tmp/platform-eia-live uv run platform ingest-once eia_energy_prices --max-documents 5 --live
UN_COMTRADE_API_KEY=... DATA_DIR=/tmp/platform-comtrade-live uv run platform ingest-once un_comtrade_trade_flows --max-documents 5 --live
```

Live ingestion reads the current `source_cursors` entry before fetching, stores that snapshot in `source_runs.cursor_before`, and writes `source_runs.cursor_after` plus the updated `source_cursors` row after a successful fetch.
The FDA drug shortages parser handles both fixture-style `Generic Name` tables and the
live FDA `Generic Name or Active Ingredient` header, and skips empty table rows so no
empty evidence spans are generated.
The openFDA device registration parser handles both flat fixture records and live nested
`registration` plus `products` records, emitting one product-level chunk per listed product
while carrying registration, facility, and owner-operator provenance into each chunk.

Expected base event sequence per created raw document:

- `ingest.raw_document_created`
- `ingest.document_parsed`
- `ingest.extraction_completed`
- `graph.node_upsert`
- `graph.relationship_upsert`

Recall enforcement ingestion also emits:

- `risk.candidates`
- `risk.case_created`
- `risk.verdicts`
- `risk.alerts`

FDA shortage ingestion stores the raw HTML page, parses shortage table rows into evidence chunks, extracts shortage events, and creates evidence-backed shortage risk cases. The HTML adapter supports bounded one-page live fetches, but default tests and CI use checked-in fixtures.

Device registration/listing ingestion extracts medical devices, device categories, manufacturers, and facilities, then maps evidence-backed `MANUFACTURED_BY`, `MANUFACTURED_AT`, `OPERATES`, and `BELONGS_TO_CATEGORY` graph relationships. Device enforcement ingestion creates recall/quality risk cases for recalled devices.

FDA warning letter ingestion downloads the public XLSX source for live runs, uses a checked-in CSV fixture for deterministic tests, parses one chunk per warning-letter row, extracts typed regulatory notice events, and maps `RegulatoryNotice`, `Manufacturer`, and `RegulatoryAgency` nodes with evidence-backed `ISSUED_TO` and `ISSUED_BY` relationships. Warning-letter company entities are routed to human review before treating them as canonical manufacturers or suppliers.

FDA inspections dashboard ingestion stores the official dashboard page for live raw-source provenance and parses exported inspection, citation, and published-483 CSV/XLSX datasets when supplied as fixtures or downloaded exports. The extractor creates `RegulatoryNotice`, `Manufacturer`, `Facility`, and `RegulatoryAgency` nodes with evidence-backed `ISSUED_TO` and `ISSUED_BY` relationships. FDA inspection legal names are routed to human review before treating them as canonical manufacturers or suppliers, and dashboard caveats are preserved on regulatory notice attributes.

GDELT DOC search ingestion stores the raw ArticleList JSON response, parses one chunk per article metadata record, and creates unverified `NewsEvent` nodes. This source stores article URL/title/domain/language/country metadata only; publisher article claims remain unverified signals until evidence-verification agents process them. GDELT requires OR clauses to be wrapped in parentheses and currently rate-limits these endpoints to roughly one request every five seconds; use `requests_per_minute: 12` and `burst: 1` for GDELT sources.

GDACS event ingestion stores the public disaster-alert RSS payload, parses one chunk per event item, and creates `DisasterEvent` nodes with event type, alert level, country, coordinates, severity, population exposure, CAP URL, and report URL attributes. These records are near-real-time exposure signals for supply-chain risk screening and retain GDACS attribution and caveats in extracted attributes.

ReliefWeb report ingestion stores the raw API v2 reports response, parses one chunk per report metadata record, and creates unverified `NewsEvent` nodes with ReliefWeb report ID, URL, source, country, theme, disaster, format, language, and date metadata. Live runs require `RELIEFWEB_APPNAME`; ReliefWeb requires appnames for API calls, and from November 1, 2025 appnames must be pre-approved. Partner report claims remain unverified until evidence-verification agents process them.

World Bank commodity price ingestion stores the raw Commodity Markets Pink Sheet monthly XLSX, parses the latest `Monthly Prices` row into one chunk per numeric commodity, and creates `PriceObservation` nodes with commodity, period, nominal USD value, unit, update date, and source table metadata. These observations are input-cost signals for risk scoring; they are not product-specific costs. Use under the World Bank dataset terms linked from the Commodity Markets page.

EIA energy price ingestion stores raw Open Data API v2 records, currently scoped to weekly U.S. No. 2 diesel retail prices in `sources/eia_energy_prices.yaml`, parses one chunk per price row, and creates `PriceObservation` nodes with period, product, process, area, unit, value, and series metadata. Live runs require `EIA_API_KEY`; EIA returns an API-key error when no key is supplied. These observations are manufacturing and transport input-cost signals, not product-specific costs.

SEC EDGAR supplier filing ingestion stores raw company submissions JSON from `data.sec.gov/submissions/CIK##########.json`, currently seeded with Pfizer as a pharma issuer in `sources/sec_edgar_supplier_filings.yaml`, parses one chunk per recent filing, and creates `RegulatoryNotice`, reviewed `Supplier`, and `RegulatoryAgency` graph nodes with evidence-backed `FILED_BY` and `FILED_WITH` relationships. Live runs require a declared `User-Agent` and must stay at or below SEC fair-access request rates. The source stores the full raw submissions response, then uses `parser.max_chunks: 25` to bound extraction fan-out for each run; increase that config deliberately for backfills. This slice stores filing metadata and SEC archive links; risk-factor, supplier, manufacturing, shortage, recall, and regulatory-proceeding claims require later filing-document text ingestion.

UN Comtrade trade-flow ingestion stores raw aggregate trade statistics from `comtradeapi.un.org/data/v1/get/...`, currently scoped to annual U.S. imports of HS 3004 medicaments in `sources/un_comtrade_trade_flows.yaml`, parses one chunk per trade-flow row, and creates `TradeFlowObservation`, `Commodity`, and `Country` graph nodes with evidence-backed `OBSERVED_FOR` and `ABOUT` relationships. Live runs require `UN_COMTRADE_API_KEY` in the `Ocp-Apim-Subscription-Key` header; the API returns a missing subscription key error without it. These records are aggregate exposure signals, not company-specific shipment evidence.

Freight proxy ingestion stores the New York Fed Global Supply Chain Pressure Index CSV from `newyorkfed.org`, parses the latest available vintage into one `LogisticsPressureObservation`, and creates a provenance-backed graph node. This is a public aggregate logistics-pressure proxy for risk scoring, not a commercial freight-rate feed or route-specific transport price.

Search trend signal ingestion stores GDELT DOC 2.0 timeline-volume JSON for monitored supply-chain and shortage terms, parses one chunk per timeline bucket, and creates `TrendSignalObservation` graph nodes. This is a public aggregate news-volume proxy, not verified search intent, product demand, or proof that publisher article claims are true. Empty GDELT windows can return no chunks and are retained through raw-response hashing and cursor state.

Each event carries an idempotency key, correlation ID, source run ID, and raw document trace metadata.

## Extractor Replay

The local extractor can replay parsed raw documents and chunks without fetching source data again:

```bash
DATA_DIR=/tmp/platform-ndc uv run platform run-extractor --source-id openfda_drug_ndc
uv run platform run-extractor --data-dir /tmp/platform-ndc --limit 10
```

It reads `raw_documents.jsonl`, `document_chunks.jsonl`, and `source_runs.jsonl`, writes missing `evidence_spans.jsonl` and `extraction_runs.jsonl`, and emits idempotent `ingest.extraction_completed` events. Current deterministic replay supports `openfda.drug_ndc.v1`, `openfda.drug_enforcement.v1`, `fda.drug_shortages_html.v1`, `openfda.device_registrationlisting.v1`, `openfda.device_enforcement.v1`, `fda.warning_letters_xlsx.v1`, `fda.inspections_dashboard.v1`, `gdelt.doc_search.v1`, `gdacs.events_rss.v1`, `reliefweb.reports.v1`, `worldbank.commodity_prices_monthly.v1`, `eia.energy_prices.v1`, `sec.edgar_supplier_filings.v1`, `uncomtrade.trade_flows.v1`, `nyfed.gscpi.v1`, and `gdelt.search_trends.v1`.

If extraction fails, the replay stores a failed `extraction_runs.jsonl` row with the same prompt/input/schema idempotency identity, records an `ingestion_errors.jsonl` row at stage `extractor`, and emits one failed `ingest.extraction_completed` event. A retry does not rerun the extractor unless the input, prompt, agent version, or schema changes.

The extractor can also run as a bounded Kafka worker against local Redpanda or Aiven Kafka:

```bash
DATA_DIR=/tmp/platform-scheduler \
KAFKA_BOOTSTRAP_SERVERS='...' \
KAFKA_SECURITY_PROTOCOL=SSL \
KAFKA_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
KAFKA_CLIENT_CERT_PATH=.platform-secrets/aiven/kafka-service.cert \
KAFKA_CLIENT_KEY_PATH=.platform-secrets/aiven/kafka-service.key \
uv run platform run-extractor --consume-kafka --max-messages 25 --idle-timeout-seconds 30
```

Kafka mode consumes `ingest.document_parsed`, validates the event payload, loads the referenced raw document and document chunks from `DATA_DIR`, writes evidence spans and extraction runs, emits idempotent `ingest.extraction_completed` events locally, publishes newly-created `ingest.extraction_completed` envelopes to Kafka for graph mapper and risk engine workers, and commits the message after durable local writes and downstream publication finish. Permanent state/config mismatches such as missing raw documents, missing chunks, unsupported parser profiles, or chunk/document mismatches are published to `ingest.deadletter` before commit.

## Graph Mapper Worker

The graph mapper can run as a bounded Kafka worker between the extractor and graph writer:

```bash
DATA_DIR=/tmp/platform-scheduler \
KAFKA_BOOTSTRAP_SERVERS='...' \
KAFKA_SECURITY_PROTOCOL=SSL \
KAFKA_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
KAFKA_CLIENT_CERT_PATH=.platform-secrets/aiven/kafka-service.cert \
KAFKA_CLIENT_KEY_PATH=.platform-secrets/aiven/kafka-service.key \
uv run platform run-graph-mapper --consume-kafka --max-messages 25 --idle-timeout-seconds 30
```

Kafka mode consumes `ingest.extraction_completed`, ignores failed or unsupported extraction schemas, loads the referenced `MedicalExtractionOutput` from `DATA_DIR`, writes idempotent `graph_node_upserts.jsonl` and `graph_relationship_upserts.jsonl` rows, persists matching graph event envelopes locally, publishes `graph.node_upsert` and `graph.relationship_upsert` commands to Kafka, and commits after those side effects finish. Missing extraction runs, raw documents, validated outputs, or document mismatches are permanent state errors and are published to `ingest.deadletter`.

## Entity Resolution

Ingestion writes local entity resolution artifacts under `DATA_DIR`:

- `canonical_entities.jsonl`
- `entity_aliases.jsonl`
- `entity_mentions.jsonl`
- `human_review_queue.jsonl` when review rules trigger
- `human_feedback.jsonl` audit records for requested reviews

Resolution uses deterministic canonical keys first, stores extracted-name and external-ID aliases, links mentions to evidence spans and extraction runs, and marks high-impact low-confidence entities for human review. Each local review task also writes a typed `review_requested` feedback record aligned with the PostgreSQL `human_feedback` table so dashboard and audit paths can track pending human-review actions.

Inspect local human-review tasks and record reviewer decisions:

```bash
uv run platform query-human-reviews --status open
DATABASE_URL_FILE=.platform-secrets/aiven/postgres-url \
DATABASE_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
uv run platform query-human-reviews --backend postgres --status open
uv run platform record-human-feedback <review-task-id> \
  --decision approve_match \
  --reviewer '<operator-or-reviewer>' \
  --comment '<why this decision is supported>'
```

Use `--backend postgres` on `record-human-feedback` after local review tasks have been synced into PostgreSQL/Aiven. The command appends a `review_decision` row to `human_feedback` with before/after values, reviewer, comment, decision, review task id, review type, and evidence span ids, then marks the matching `human_review_queue` task as resolved. The command does not mutate source evidence or canonical facts directly; follow-up merge/split/alias mechanics remain explicit future actions.

The PostgreSQL evidence repository has idempotent writers for the same canonical entity, alias, mention, and human-feedback artifacts. Canonical entities upsert by `(entity_type, canonical_key)`, aliases by `(canonical_entity_id, normalized_alias, alias_type)`, and mentions by raw document, chunk, evidence span, entity type, and normalized mention.

## Scheduler

The local scheduler reads enabled source configs and emits `ingest.jobs` envelopes plus pending `source_runs` under `DATA_DIR`:

```bash
DATA_DIR=/tmp/platform-scheduler uv run platform run-scheduler --source-id openfda_drug_ndc
```

Inspect source-run history locally or in PostgreSQL/Aiven. Use `--latest-state-only`
when JSONL history contains pending/running/succeeded transitions and the operator
needs one current row per source run:

```bash
DATA_DIR=/tmp/platform-scheduler \
uv run platform query-source-runs --source-id openfda_drug_ndc --latest-state-only --include-cursors

DATABASE_URL_FILE=.platform-secrets/aiven/postgres-url \
DATABASE_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
uv run platform query-source-runs --backend postgres \
  --source-id openfda_drug_ndc \
  --latest-state-only \
  --include-cursors
```

Publish those same stored envelopes to local Redpanda or Aiven Kafka through the direct Kafka client:

```bash
DATA_DIR=/tmp/platform-scheduler \
KAFKA_BOOTSTRAP_SERVERS=localhost:19092 \
uv run platform run-scheduler --source-id openfda_drug_ndc --publish-kafka
```

Process one queued ingest job with the live ingestion worker:

```bash
DATA_DIR=/tmp/platform-scheduler \
KAFKA_BOOTSTRAP_SERVERS=localhost:19092 \
uv run platform run-ingest-worker --once --max-documents 1
```

Replay an already completed local fixture or live run into PostgreSQL/Aiven without Kafka. The
command is dry-run by default and reports exactly which source-scoped rows would be written:

```bash
DATA_DIR=/tmp/platform-scheduler \
uv run platform sync-postgres-evidence --source-id openfda_drug_ndc
```

Apply the same replay after `DATABASE_URL_FILE` and, for Aiven, `DATABASE_CA_CERT_PATH` are configured. Keep local credential files under `.platform-secrets/`, which is ignored by Git:

```bash
DATA_DIR=/tmp/platform-scheduler \
DATABASE_URL_FILE=.platform-secrets/aiven/postgres-url \
DATABASE_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
uv run platform sync-postgres-evidence --source-id openfda_drug_ndc --apply
```

For Aiven/PostgreSQL-backed execution, write the PostgreSQL URL, project CA certificate, Kafka client certificate, and Kafka client key to local secret files. The worker reads those paths, syncs evidence to PostgreSQL, and commits the Kafka message only after durable writes complete:

```bash
DATABASE_URL_FILE=.platform-secrets/aiven/postgres-url \
DATABASE_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
KAFKA_BOOTSTRAP_SERVERS='...' \
KAFKA_SECURITY_PROTOCOL=SSL \
KAFKA_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
KAFKA_CLIENT_CERT_PATH=.platform-secrets/aiven/kafka-service.cert \
KAFKA_CLIENT_KEY_PATH=.platform-secrets/aiven/kafka-service.key \
uv run platform validate-cloud-secrets --require-ready
```

Before provisioning Aiven Grafana, validate the Grafana token, PostgreSQL password, and optional PostgreSQL CA file:

```bash
GRAFANA_URL='https://...' \
GRAFANA_TOKEN_FILE=.platform-secrets/aiven/grafana-token \
GRAFANA_POSTGRES_HOST='...' \
GRAFANA_POSTGRES_PORT=26839 \
GRAFANA_POSTGRES_USER=avnadmin \
GRAFANA_POSTGRES_PASSWORD_FILE=.platform-secrets/aiven/postgres-password \
GRAFANA_POSTGRES_DB=defaultdb \
GRAFANA_POSTGRES_SSLMODE=verify-full \
GRAFANA_POSTGRES_TLS_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
uv run platform validate-cloud-secrets --profile aiven-grafana --require-ready
```

If `GRAFANA_TOKEN_FILE` points at a missing file, the command exits non-zero with a structured `missing` check instead of attempting to load the absent secret. Create `.platform-secrets/aiven/grafana-token` with a Grafana service account/API token before running `create-dashboard ... --provision`.

Use `--profile aiven-mvp` to validate both worker and Grafana secret bundles in one check.
After the file checks pass, run the combined cloud readiness inspection. Without
`--live-aiven`, this validates local configuration and service names only. With
`--live-aiven`, the command uses the direct Aiven API fallback to verify the configured
services exist and are `RUNNING`; the request is audited without printing secret values:

```bash
AIVEN_PROJECT='<project>' \
AIVEN_POSTGRES_SERVICE=platform-pg \
AIVEN_KAFKA_SERVICE=platform-kafka \
AIVEN_GRAFANA_SERVICE=platform-grafana \
AIVEN_API_TOKEN_FILE=.platform-secrets/aiven/api-token \
uv run platform cloud-readiness --profile aiven-mvp --live-aiven --require-ready
```

The readiness output includes scoped service checks and the next direct-client commands:
`init-db --apply`, `init-kafka --apply --backend direct`, `run-scheduler --publish-kafka`,
`run-ingest-worker --evidence-backend postgres`, and Grafana datasource/dashboard provisioning.

```bash
DATA_DIR=/tmp/platform-scheduler \
DATABASE_URL_FILE=.platform-secrets/aiven/postgres-url \
DATABASE_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
KAFKA_BOOTSTRAP_SERVERS='...' \
KAFKA_SECURITY_PROTOCOL=SSL \
KAFKA_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
KAFKA_CLIENT_CERT_PATH=.platform-secrets/aiven/kafka-service.cert \
KAFKA_CLIENT_KEY_PATH=.platform-secrets/aiven/kafka-service.key \
uv run platform run-ingest-worker --once --max-documents 1 --evidence-backend postgres
```

To drain a bounded batch of Aiven Kafka ingest jobs with one worker lifecycle, use loop mode:

```bash
DATA_DIR=/tmp/platform-aiven-smoke \
DATABASE_URL_FILE=.platform-secrets/aiven/postgres-url \
DATABASE_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
KAFKA_BOOTSTRAP_SERVERS='...' \
KAFKA_SECURITY_PROTOCOL=SSL \
KAFKA_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
KAFKA_CLIENT_CERT_PATH=.platform-secrets/aiven/kafka-service.cert \
KAFKA_CLIENT_KEY_PATH=.platform-secrets/aiven/kafka-service.key \
uv run platform run-ingest-worker \
  --no-once \
  --max-messages 3 \
  --max-documents 1 \
  --evidence-backend postgres
```

A representative cloud smoke should schedule and publish a small batch from
`openfda_drug_ndc`, `openfda_drug_enforcement`, and `fda_drug_shortages`, then require
`processed_messages == committed_messages`, `deadlettered_messages == 0`, and matching
Aiven PostgreSQL row growth for raw documents, evidence spans, risk candidates, cases,
verdicts, alerts, and graph audit rows.

Additional bounded live runs have been verified and synced to Aiven/PostgreSQL for
`gdacs_events`, `sec_edgar_supplier_filings`, `openfda_device_registrationlisting`,
`openfda_device_enforcement`, and `freight_proxy_prices`. After those syncs, the Aiven
database contained 8 data sources, 10 raw documents, 287 document chunks/evidence spans,
928 graph audit rows, 256 risk cases, and 256 risk alerts.

```bash
DATA_DIR=/tmp/platform-scheduler \
DATABASE_URL_FILE=.platform-secrets/aiven/postgres-url \
DATABASE_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
KAFKA_BOOTSTRAP_SERVERS='...' \
KAFKA_SECURITY_PROTOCOL=SSL \
KAFKA_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
KAFKA_CLIENT_CERT_PATH=.platform-secrets/aiven/kafka-service.cert \
KAFKA_CLIENT_KEY_PATH=.platform-secrets/aiven/kafka-service.key \
uv run platform run-ingest-worker --no-once --max-messages 25 \
  --idle-timeout-seconds 30 --evidence-backend postgres
```

If the Kafka service is configured for SASL instead of certificate authentication, use
`KAFKA_SECURITY_PROTOCOL=SASL_SSL` with `KAFKA_SASL_USERNAME` and
`KAFKA_SASL_PASSWORD_FILE`.

Preview scheduler output without writing artifacts:

```bash
uv run platform run-scheduler --source-id openfda_drug_ndc --dry-run
```

Each job includes `source_id`, `source_run_id`, `run_type`, source config hash, and request timestamp. If a `source_cursors` entry exists for the source, the scheduler snapshots it into both the job payload cursor and the pending `source_runs.cursor_before` field. The worker preserves that scheduled `source_run_id` across raw documents, chunks, graph facts, risk artifacts, source health, and cursor checkpoints. It commits Kafka offsets only after durable ingestion writes and downstream event publication complete. With `--evidence-backend postgres`, the worker first writes local raw-first artifacts, syncs supported evidence collections to `DATABASE_URL`, then publishes newly-created local event envelopes such as `ingest.raw_document_created`, `ingest.document_parsed`, `ingest.extraction_completed`, graph upsert commands, and risk events. A PostgreSQL/Aiven sync failure prevents downstream publication and Kafka commit so the job can retry. Permanent validation failures, such as a stale source config hash, go to `ingest.deadletter`; transient adapter, endpoint, or database failures remain uncommitted for retry. In `--no-once` mode, `--max-messages` gives a bounded batch size and `--idle-timeout-seconds` exits cleanly when the topic is drained. `--publish-kafka` is disabled for `--dry-run` because Kafka publishing must use the exact envelopes already written to the local audit store.
The ingest worker summary includes an `executions` list for successfully processed
jobs, with source id, source run id, ingest stats, PostgreSQL sync summary, and
downstream Kafka publish count. Deadlettered jobs are counted in `results` and
`deadlettered_messages` but are not included in `executions`.

## Risk Explanation

Recall enforcement ingestion creates evidence-backed recall/quality risk cases. Explain a stored case from `DATA_DIR`:

```bash
DATA_DIR=/tmp/platform-enforcement uv run platform explain-case 'risk:recall_quality:<recall-key>'
```

The explanation includes component scores, confidence values, evidence spans, source document summaries, graph relationships tied to the same evidence, alerts, verdict limitations, and unresolved conflicts if present.

## Risk Engine

The local risk engine can replay stored successful extraction runs and create missing recall/quality or shortage risk candidates, cases, verdicts, alerts, and risk events idempotently:

```bash
DATA_DIR=/tmp/platform-enforcement uv run platform run-risk-engine
uv run platform run-risk-engine --data-dir /tmp/platform-enforcement
```

It scans `extraction_runs.jsonl` for `MedicalExtractionOutput` records, rebuilds recall/quality candidates and cases from source-backed recall events and shortage candidates and cases from source-backed shortage events, skips already-created candidates/cases/verdicts/events, and updates existing alert rows by `alert_key` without creating duplicates.

Each created risk case also writes one `risk_feature_snapshots.jsonl` row per component score, carrying the case scope, feature name, value, evidence span IDs, computed timestamp, and feature version. PostgreSQL-backed runs persist the same history in `risk_feature_snapshots`, keyed by risk case, feature name, feature version, and window for idempotent updates.

The risk engine can also run as a bounded Kafka worker against local Redpanda or Aiven Kafka:

```bash
DATA_DIR=/tmp/platform-scheduler \
KAFKA_BOOTSTRAP_SERVERS='...' \
KAFKA_SECURITY_PROTOCOL=SSL \
KAFKA_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
KAFKA_CLIENT_CERT_PATH=.platform-secrets/aiven/kafka-service.cert \
KAFKA_CLIENT_KEY_PATH=.platform-secrets/aiven/kafka-service.key \
uv run platform run-risk-engine --consume-kafka --max-messages 25 --idle-timeout-seconds 30
```

Kafka mode consumes `ingest.extraction_completed`, ignores non-succeeded or unsupported extraction schemas, loads the referenced successful `MedicalExtractionOutput` from `DATA_DIR`, writes the same idempotent risk candidates, cases, verdicts, alerts, feature snapshots, and risk events, publishes newly-created `risk.candidates`, `risk.case_created`, `risk.verdicts`, and `risk.alerts` envelopes to Kafka, then commits after durable local writes and downstream publication finish. Permanent state mismatches such as missing extraction runs, missing raw documents, missing validated output, or extraction/document mismatches are published to `ingest.deadletter` before commit.

## Agent Swarm

The local agent swarm reads a stored risk case and writes `agent_findings.jsonl`, an
investigation-stage `risk_verdicts.jsonl` verdict, and audit events:

```bash
DATA_DIR=/tmp/platform-enforcement uv run platform run-agent-swarm --case-key 'risk:recall_quality:<recall-key>'
```

Current local agents:

- `EvidenceVerifierAgent`
- `GraphBlastRadiusAgent`
- `CriticAgent`
- `VerdictAgent`

The swarm emits `risk.agent_findings` events for each finding, one `risk.verdicts`
event for the VerdictAgent verdict, and one `agents.audit_log` event for the run.
Each `agent_findings` row and `risk.agent_findings` payload carries non-secret runtime
metadata: model name, prompt hash, input hash, output schema/version, usage, and
error. Deterministic local swarm runs use `deterministic-local` as the model name
and stable hashes over the case key, verdict, evidence IDs, and graph-path count.

The swarm can also run as a bounded Kafka worker:

```bash
DATA_DIR=/tmp/platform-scheduler \
KAFKA_BOOTSTRAP_SERVERS='...' \
KAFKA_SECURITY_PROTOCOL=SSL \
KAFKA_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
KAFKA_CLIENT_CERT_PATH=.platform-secrets/aiven/kafka-service.cert \
KAFKA_CLIENT_KEY_PATH=.platform-secrets/aiven/kafka-service.key \
uv run platform run-agent-swarm --consume-kafka --max-messages 25 --idle-timeout-seconds 30
```

Kafka mode consumes `risk.case_created`, runs the same evidence verifier, graph blast-radius,
critic, and verdict agents for the referenced case key, writes idempotent findings, the
VerdictAgent verdict, and audit events, publishes newly-created `risk.agent_findings`,
`risk.verdicts`, and `agents.audit_log` envelopes to Kafka, and commits after durable
local writes and downstream publication finish. Missing referenced risk cases are treated
as permanent state mismatches and published to `ops.errors`.

## Graph Replay

Fixture ingestion writes graph command JSONL files under `DATA_DIR`. Inspect the replay plan without touching Neo4j:

```bash
DATA_DIR=/tmp/platform-ndc uv run platform run-graph-writer
uv run platform run-graph-writer --data-dir /tmp/platform-ndc
```

Apply those upserts to `NEO4J_URI` after `init-neo4j --apply` has succeeded:

```bash
uv run platform run-graph-writer --data-dir /tmp/platform-ndc --apply
```

After local evidence has been synced into PostgreSQL/Aiven, replay the durable graph audit table
instead of local JSONL:

```bash
DATABASE_URL_FILE=.platform-secrets/aiven/postgres-url \
DATABASE_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
uv run platform run-graph-writer --source postgres --limit 100

DATABASE_URL_FILE=.platform-secrets/aiven/postgres-url \
DATABASE_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
uv run platform run-graph-writer --source postgres --limit 100 --apply --summary-only
```

When only the local Neo4j container is available, the same replay path can populate Neo4j from
Aiven/PostgreSQL audit without local PostgreSQL or Redpanda:

```bash
uv run platform init-neo4j --apply

DATABASE_URL_FILE=.platform-secrets/aiven/postgres-url \
DATABASE_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
uv run platform run-graph-writer --source postgres --apply --summary-only
```

`--summary-only` keeps the replay counts, aggregate Neo4j write counters, and returned-record
totals, while omitting the per-statement result list that can be very large during Aiven
audit replays.

To consume graph upsert commands from Kafka instead of replaying JSONL, use the opt-in consumer mode:

```bash
uv run platform run-graph-writer --consume-kafka --max-messages 25 --idle-timeout-seconds 30
```

Open the local graph in Neo4j Browser at `http://localhost:17474`. Use username `neo4j` and password `platform`. Host-side CLI commands connect through `NEO4J_URI=neo4j://localhost:17687`; inside the Docker Compose network the container port is `7687`.

Useful browser sanity queries:

```cypher
MATCH (n) RETURN count(n) AS nodes;
MATCH ()-[r]->() RETURN count(r) AS relationships;
MATCH p=()-[r:AFFECTS]->() RETURN p LIMIT 50;
```

Refresh the custom frontend dashboard snapshot after a deterministic local
fixture refresh. This file-store path reads `graph_node_upserts.jsonl` and
`graph_relationship_upserts.jsonl`, preserves node/edge provenance fields in the
frontend JSON contract, and writes the asset consumed by the TanStack dashboard:

```bash
uv run platform export-graph-snapshot \
  --source file \
  --data-dir /tmp/platform-ndc \
  --output public/platform-demo/supply-chain-graph.json \
  --limit 500
```

After graph replay, export from Neo4j instead. This reads `NEO4J_URI` and is the
preferred path when Neo4j is running:

```bash
uv run platform export-graph-snapshot \
  --source neo4j \
  --output public/platform-demo/supply-chain-graph.json \
  --limit 500
```

The dashboard then merges the curated demo graph with the exported platform
graph nodes. Use `devme up` and open `http://localhost:3000/`; the navigation
pill shows the count of exported platform nodes, and selecting an exported node
opens provenance, confidence, source, evidence, and fact details in the right
panel. The snapshot is static by design; rerun `export-graph-snapshot` after new
`run-graph-writer` replays until a live graph API replaces the file-backed path.

The right-side graph chat calls `/api/graph-chat` against the same merged graph.
It writes JSONL audit rows to `GRAPH_CHAT_AUDIT_PATH`, or
`DATA_DIR/dashboard_graph_chat_audit.jsonl` when unset; set
`GRAPH_CHAT_AUDIT_DISABLED=true` only for throwaway local runs. Each row carries
`topic` and `eventType` `dashboard.graph_chat_answered`, input/output hashes,
selected/neighbor/related node ids, source refs, graph stats, snapshot mode,
snapshot generated time, source graph node/relationship totals, and safety
flags. The Kafka topic `dashboard.graph_chat_answered` is checked in for
streaming this same contract once the dashboard runtime has a Kafka producer.

Convert local graph-chat audit rows into the platform Kafka envelope before
publishing from the outbox. The importer validates the frontend JSONL contract,
normalizes camelCase dashboard fields to the Python event schema, preserves the
dashboard timestamp as `emitted_at`, and writes idempotent
`dashboard.graph_chat_answered:<audit_id>` events into `events.jsonl`:

```bash
uv run platform import-dashboard-graph-chat-audit --data-dir /tmp/platform-ndc
```

Plan the outbox replay before sending anything to Kafka:

```bash
uv run platform publish-events \
  --data-dir /tmp/platform-ndc \
  --event-type dashboard.graph_chat_answered
```

When Kafka credentials are configured and the topic exists, publish the selected
envelopes with the same event-key rules used by workers. The command emits
`ops.metrics` producer metrics and records the matching local `ops_metrics`
rows idempotently:

```bash
uv run platform publish-events \
  --data-dir /tmp/platform-ndc \
  --event-type dashboard.graph_chat_answered \
  --publish-kafka
```

Record graph totals into `ops_metrics` so the PostgreSQL-backed graph-growth
dashboard can show actual graph size, not only audit-command volume. For local
demo data, read the idempotent graph upsert JSONL files produced by the ingest
pipeline:

```bash
uv run platform record-graph-metrics --source file --data-dir /tmp/platform-ndc
```

When Neo4j is populated and reachable, read live graph totals instead:

```bash
uv run platform record-graph-metrics --source neo4j --data-dir /tmp/platform-ndc

DATABASE_URL_FILE=.platform-secrets/aiven/postgres-url \
DATABASE_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
uv run platform record-graph-metrics --source neo4j --backend postgres
```

The command stores `graph_nodes_total` and `graph_relationships_total` with
stable idempotency keys for the observation timestamp. File-backed metrics use
`service = 'file-graph'` with local graph-upsert provenance in metadata; Neo4j
metrics use `service = 'neo4j'` with non-secret query provenance.

Node and relationship upserts use `MERGE` and carry provenance fields such as `source_document_id`, `evidence_span_id`, `extraction_run_id`, confidence, source name, source URL, and extraction method. Relationship writes must return a row from Neo4j; a zero-row result means one of the endpoint node keys was not present, and replay fails clearly instead of silently dropping the edge.

## Operator Queries

Inspect checked-in source configs with local source-health status:

```bash
uv run platform query-sources
uv run platform query-sources --status failed
uv run platform query-sources --priority P0
uv run platform query-sources --endpoint-access requires_env
DATABASE_URL_FILE=.platform-secrets/aiven/postgres-url \
DATABASE_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
uv run platform query-sources --backend postgres --priority P0
```

`query-sources` reads checked-in YAML configs and joins local `DATA_DIR/source_health.jsonl` when present. Each row includes non-secret endpoint metadata: `auth_type`, `auth_env`, `auth_required`, `auth_env_configured`, `endpoint_access`, robots policy, and rate-limit settings. `endpoint_access` is `public` for unauthenticated sources, `public_limited` when optional auth such as `OPENFDA_API_KEY` is absent, `configured` when the referenced env var is set, and `requires_env` when a required credential such as `EIA_API_KEY`, `UN_COMTRADE_API_KEY`, or `RELIEFWEB_APPNAME` is missing. Use `--backend postgres` to read `source_health`, raw document counts, chunk counts, and latest raw fetch timestamps from `DATABASE_URL` instead. `--status failed` matches failing or failed source health records.

Inspect individual source run audit trails locally or from PostgreSQL/Aiven:

```bash
uv run platform query-source-runs --source-id openfda_drug_ndc --limit 5
uv run platform query-source-runs --source-id openfda_drug_ndc --status succeeded --include-cursors
DATABASE_URL_FILE=.platform-secrets/aiven/postgres-url \
DATABASE_CA_CERT_PATH=.platform-secrets/aiven/project-ca.pem \
uv run platform query-source-runs --backend postgres --source-id openfda_drug_ndc --limit 5
```

`query-source-runs` returns the run id, source id, run type, status, document counters,
error count, correlation id, idempotency key, error metadata, and timestamps. Cursor
snapshots are omitted by default because they can be verbose; use `--include-cursors`
when debugging scheduler and incremental-fetch behavior.

Register or update a checked-in source definition before scheduler/bootstrap tests:

```bash
uv run platform register-source sources/openfda_drug_ndc.yaml --actor '<operator-or-job>'
uv run platform register-source sources/openfda_drug_ndc.yaml --backend postgres
```

The file backend upserts `DATA_DIR/registered_sources.jsonl` by stable `source_id`, so repeat registrations do not create duplicate source rows. Every CLI registration writes a typed `source_registry_audit.jsonl` record with the backend, result, config path, actor, and the same source config hash the scheduler uses for stale-job protection.

Plan named graph queries without touching Neo4j:

```bash
uv run platform query-graph drug-supply-chain --drug-key 'Drug:ndc_product:<product-ndc>'
uv run platform query-graph risk-case-context --risk-case-key 'risk:recall_quality:<recall-key>'
```

Named graph queries currently cover:

- `drug-supply-chain --drug-key`
- `facility-downstream-products --facility-key`
- `ingredient-dependency --ingredient-key`
- `port-exposure --port-key`
- `recall-blast-radius --recall-key`
- `shortage-blast-radius --shortage-key`
- `disaster-facility-exposure --disaster-key`
- `commodity-input-exposure --commodity-key`
- `risk-case-context --risk-case-key`

Run the same query against `NEO4J_URI` only when explicitly requested:

```bash
uv run platform query-graph drug-supply-chain --drug-key 'Drug:ndc_product:<product-ndc>' --apply
```

## Kafka Backbone

Kafka topic specs live in `infra/kafka/topics.yaml`. The event abstraction validates every `EventEnvelope` and registered payload model before produce or consume. Consumers commit only after durable side effects succeed or after a deadletter event is produced.

Export the current event envelope and payload JSON Schema bundle:

```bash
uv run platform export-event-schemas --out docs/event-schemas.json
```

Known event types fail closed when no payload schema is registered or when payload validation fails. Add new payload models in `src/supply_intel/models/kafka.py` and register them in `src/supply_intel/events/schemas.py` before producing new event types.

When topic bootstrap or operator smoke tests use the Aiven MCP path, `InjectedAivenMCPController` wraps host-provided MCP tool calls and records each PostgreSQL/Kafka/service action through `AivenMCPController.audit_action`; the configured evidence store persists those records to `mcp_audit_log`. Direct Kafka AdminClient bootstrap remains the runtime fallback.

Runtime Kafka produce/consume uses the `DirectKafkaProducerClient` and `DirectKafkaConsumerClient` aiokafka wrappers with `KAFKA_*` settings. This keeps application workers independent of Aiven MCP and Kafka REST; MCP Kafka REST remains an operator convenience path when explicitly enabled. A bounded Aiven MCP smoke should produce one stored `ingest.jobs` envelope to the `ingest.jobs` topic and read it back from the returned partition/offset before using direct worker credentials.

Kafka publishing can emit typed `ops.metrics` envelopes for lightweight service telemetry. Scheduler Kafka publication records `events_produced_total` for `ingest.jobs`, writes the same metric to `DATA_DIR/ops_metrics.jsonl`, and syncs source-scoped metric rows into PostgreSQL through `sync-postgres-evidence`. Metrics use stable idempotency keys based on the causative event id, so retries do not inflate persisted counts.

Deadletter routing:

- `ingest.*` -> `ingest.deadletter`
- `graph.*` -> `graph.deadletter`
- all other topics -> `ops.errors`

## Dashboards

Generate Grafana dashboard JSON from definitions:

```bash
uv run platform create-dashboard all
```

Upload generated dashboards to local or Aiven Grafana when `GRAFANA_URL` and `GRAFANA_TOKEN` are configured:

```bash
uv run platform create-dashboard all --provision --folder-uid <folder-uid>
```

Create or update the Grafana PostgreSQL datasource through the Grafana HTTP API before dashboard upload:

```bash
GRAFANA_POSTGRES_HOST=<pg-host> \
GRAFANA_POSTGRES_PORT=<pg-port> \
GRAFANA_POSTGRES_USER=<pg-user> \
GRAFANA_POSTGRES_PASSWORD=<pg-password> \
GRAFANA_POSTGRES_DB=<pg-db> \
GRAFANA_POSTGRES_SSLMODE=verify-full \
uv run platform create-dashboard all --provision-datasource --provision
```

The command returns datasource uid/name/status only; it does not print the PostgreSQL password. For local Docker Compose, the checked-in `GRAFANA_POSTGRES_*` defaults point Grafana at the compose PostgreSQL service.

Local Docker Compose also provisions these dashboards automatically: Grafana mounts `dashboards/generated` at `/var/lib/grafana/dashboards/platform` and the provider in `infra/grafana/provisioning/dashboards/platform.yaml` watches that directory. The local PostgreSQL datasource uses `GRAFANA_POSTGRES_*` environment variables and defaults to the compose PostgreSQL service.

`source-freshness` joins `data_sources`, `source_health`, `raw_documents`, and `document_chunks` so the Aiven/PostgreSQL dashboard shows both freshness status and per-source evidence coverage after cloud syncs.

Generated files:

- `dashboards/generated/agent-activity.json`
- `dashboards/generated/evidence-coverage.json`
- `dashboards/generated/executive-risk-overview.json`
- `dashboards/generated/source-freshness.json`
- `dashboards/generated/ingestion-throughput.json`
- `dashboards/generated/graph-growth.json`
- `dashboards/generated/low-confidence-review.json`
- `dashboards/generated/mcp-audit-activity.json`
- `dashboards/generated/medicine-drug-manufacturing-risk.json`
- `dashboards/generated/operational-metrics.json`
- `dashboards/generated/risk-cases.json`
- `dashboards/generated/source-failures.json`

## Safety Gates

Default to read-only behavior for Aiven MCP and cloud resources. Require explicit approval before:

- service create/update/delete/power changes
- Kafka topic deletion or production topic changes
- PostgreSQL writes outside reviewed migrations
- credential retrieval
- public endpoint enablement
- Kafka REST, Kafka Connect, or Schema Registry enablement in production
- application deploy/redeploy

The application runtime must not depend on MCP. MCP usage belongs behind the `AivenMCPController` abstraction and must be auditable.

## Scope Guardrails

The platform provides supply-chain intelligence only. It does not provide medical advice, clinical decision support, patient triage, or patient-identifiable processing.
