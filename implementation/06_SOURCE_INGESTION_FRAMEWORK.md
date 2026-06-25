# Source Ingestion Framework

The ingestion framework must make ordinary source additions configuration-driven while preserving enough extension points for unusual sources. The default path for a new source is one source config, one parser profile, fixtures, and tests. Custom adapter code is reserved for unusual auth, pagination, rendering, binary parsing, or webhook behavior.

## Raw-First Rule

Every adapter must store `raw_documents` before any parser, extraction agent, entity resolver, graph writer, risk engine, or dashboard metric consumes the data.

Minimum raw document metadata:

- `source_id`
- `source_run_id`
- `source_url`
- `request`
- `response_headers`
- `http_status`
- `content_type`
- `content_hash`
- `payload_storage`
- `payload_uri` or inline payload
- `source_published_at`
- `source_updated_at`
- `fetched_at`
- `dedupe_key`

If the payload cannot be parsed, the raw document still remains durable and the parser failure is recorded.

## Source Config Schema

Use YAML for checked-in source configs, validated into a Pydantic model.

```yaml
source_id: openfda_drug_ndc
name: openFDA Drug NDC
source_type: government_api
adapter: paginated_rest
enabled: true
priority: P0
base_url: https://api.fda.gov/drug/ndc.json
method: GET
auth:
  type: query_param
  env: OPENFDA_API_KEY
  param: api_key
headers:
  User-Agent: "${PLATFORM_USER_AGENT}"
pagination:
  type: skip_limit
  limit_param: limit
  offset_param: skip
  page_size: 1000
  max_offset: 25000
  results_path: results
cursor:
  strategy: date_window
  field: listing_expiration_date
  lag_seconds: 86400
rate_limit:
  requests_per_minute: 220
  burst: 10
  backoff:
    min_seconds: 1
    max_seconds: 60
dedupe:
  key_fields: [product_ndc]
  content_hash: sha256
  canonical_url: true
parser:
  profile: openfda.drug_ndc.v1
  chunking: json_record
compliance:
  robots: not_applicable_api
  license_notes: "openFDA public API. Follow openFDA terms and limits."
  pii_expected: false
schedule:
  cadence: 1d
  jitter_seconds: 900
fixtures:
  success: tests/fixtures/sources/openfda_drug_ndc/success.json
  empty: tests/fixtures/sources/openfda_drug_ndc/empty.json
```

Pydantic model families:

- `SourceConfig`
- `AuthConfig`
- `PaginationConfig`
- `CursorConfig`
- `RateLimitConfig`
- `DedupeConfig`
- `ParserConfig`
- `ComplianceConfig`
- `ScheduleConfig`
- `FixtureConfig`

Validation rules:

- `source_id` is lowercase snake case.
- `adapter` must map to a registered adapter.
- `parser.profile` must map to a registered parser profile.
- sources with scraping adapters must include robots/compliance notes.
- sources with API keys must use env refs, not literal secrets.
- `cadence` must be parseable and nonzero for scheduled sources.
- `dedupe` must specify stable key fields or a custom dedupe strategy.

## Adapter Base Class

```python
class SourceAdapter(Protocol):
    adapter_type: ClassVar[str]

    async def validate_config(self, config: SourceConfig) -> None: ...

    async def plan_fetch(
        self,
        config: SourceConfig,
        cursor: SourceCursor | None,
        run: SourceRun,
    ) -> FetchPlan: ...

    async def fetch(
        self,
        plan: FetchPlan,
        context: FetchContext,
    ) -> AsyncIterator[FetchedPayload]: ...

    async def checkpoint(
        self,
        payloads: list[FetchedPayload],
        previous_cursor: SourceCursor | None,
    ) -> SourceCursorUpdate: ...
```

Key supporting models:

- `FetchPlan`: request list, pagination state, time windows, limits.
- `FetchContext`: HTTP client, rate limiter, storage, logger, run IDs.
- `FetchedPayload`: raw bytes/text, URL, headers, status, timestamps, dedupe key.
- `SourceCursorUpdate`: cursor JSON, watermark, etag, last content hash.

## Built-In Adapters

### REST Adapter

Use for single endpoint JSON/XML/text requests.

Features:

- env-driven auth
- static query params and headers
- retry with tenacity
- timeout defaults
- content hash and dedupe

### Paginated REST Adapter

Pagination strategies:

- `skip_limit`
- `page_number`
- `cursor_token`
- `link_header`
- `next_url`
- `date_window`

Rules:

- Store every page response as raw data or split every result into stable raw documents depending on parser profile.
- Stop on empty page, missing next token, max pages, or max offset.
- For openFDA, use bulk download when `skip` would exceed 25000.

### RSS/Atom Adapter

Features:

- feed ETag and Last-Modified support
- item GUID/link dedupe
- feed raw storage plus per-item raw document records
- source published/updated timestamps

### HTML Scraper Adapter

Features:

- robots.txt preflight unless source is explicitly exempted
- polite rate limiting
- canonical URL extraction
- link discovery rules
- boilerplate stripping in parser stage, not adapter stage

### JavaScript-Rendered Scraper Adapter

Use only when static HTML is insufficient.

Features:

- Playwright-based rendering
- blocked resource policy
- max page time
- screenshot capture option for parser debugging
- robots/compliance requirement

### File Download Adapter

Use for CSV, JSON, XML, XLS/XLSX, ZIP, or bulk files.

Features:

- checksum if source provides one
- archive member extraction metadata
- large payload storage through object/file store
- content-addressed paths

### PDF/Document Adapter

Use for PDF, DOCX, and other documents.

Features:

- raw binary storage
- metadata extraction
- downstream parser profile for text, page, table, and OCR extraction

### Manual Seed Adapter

Use for curated seed files and mappings:

- commodity-to-input mappings
- company alias lists
- HS code mappings
- initial manufacturer/facility references

Manual seeds must still create raw documents and source runs.

### Webhook Adapter

Future adapter:

- validates signatures
- stores inbound raw payloads
- emits `ingest.raw_document_created`
- does not run on scheduler

## Parser Profiles

Parser profile names follow:

```text
<source_family>.<domain>.<version>
```

Examples:

- `openfda.drug_ndc.v1`
- `openfda.drug_enforcement.v1`
- `fda.drug_shortages_html.v1`
- `gdelt.doc_search.v1`
- `sec.edgar_10k.v1`
- `worldbank.commodity_prices_xlsx.v1`

Parser profiles define:

- payload type
- record path
- text fields
- table extraction rules
- chunking strategy
- evidence span locator strategy
- required fields
- golden fixture expectations

## Cursor and Checkpoint Strategy

Supported strategies:

- `none`: full fetch every run.
- `etag`: conditional HTTP requests.
- `last_modified`: conditional HTTP requests.
- `date_watermark`: time-based source fields.
- `date_window`: rolling overlap to catch late corrections.
- `cursor_token`: opaque API continuation token.
- `offset_checkpoint`: page/offset tracking for backfills.
- `content_hash`: detect corrected-in-place sources.

Rules:

- Update cursor only after raw documents are durably stored and event emission succeeds.
- Use overlap windows for sources that backfill or revise records.
- Store `cursor_before` and `cursor_after` in `source_runs`.
- Keep source cursor JSON opaque enough to support source-specific state without schema churn.

## Dedupe and Content Hashing

Dedupe keys should prefer:

1. official stable ID, such as `recall_number`, `product_ndc`, CIK accession number.
2. canonical URL.
3. source URL plus published timestamp.
4. deterministic hash of selected source fields.

Content hash:

- SHA-256 over canonical bytes.
- Normalize line endings for text if parser profile allows it.
- For JSON, keep raw bytes hash and optionally a canonical JSON hash.

If `dedupe_key` matches but `content_hash` changes, create a new raw document version. Do not overwrite the old version.

## CLI Commands

### `validate-source`

```bash
uv run platform validate-source sources/openfda_drug_ndc.yaml
```

Validates schema, adapter availability, parser profile, env refs, schedule, dedupe, and compliance metadata.

### `test-fetch`

```bash
uv run platform test-fetch openfda_drug_ndc --limit 2 --dry-run
```

Fetches a small sample, prints metadata, validates content type and parser compatibility, and stores nothing unless `--store` is supplied.

### `register-source`

```bash
uv run platform register-source sources/openfda_drug_ndc.yaml
```

Upserts `data_sources`, records config hash, and optionally schedules initial run.

### `ingest-once`

```bash
uv run platform ingest-once openfda_drug_ndc --max-documents 100
```

Creates a manual `source_run`, fetches raw documents, updates cursor, emits events.

### `run-scheduler`

```bash
uv run platform run-scheduler
```

Selects due sources, creates runs, and emits `ingest.jobs`.

## Scheduler Design

Use a database-backed scheduler first:

- Select enabled sources where `next_run_at <= now()`.
- Use `FOR UPDATE SKIP LOCKED` or advisory locks.
- Create `source_runs`.
- Emit `ingest.jobs`.
- Compute next run with cadence plus jitter.

Later options:

- APScheduler for local.
- Cloud scheduler for production.
- Kafka-native work queue for distributed workers.

## Backfill and Replay

Backfills:

- use explicit date windows or offset ranges.
- create `source_runs.run_type='backfill'`.
- do not mutate default cursor unless `--promote-cursor` is supplied.

Replays:

- start from existing `raw_documents`.
- re-run parser/extraction/graph/risk with new model or schema version.
- preserve old runs and outputs.

## Compliance Gates

Any source with `adapter` in `html_scraper` or `js_rendered_scraper` must include:

- robots status
- allowed paths
- rate limit
- user agent
- license notes
- data minimization statement
- parser fixture

The CLI should fail validation if these are missing.
