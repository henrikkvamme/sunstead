# Testing Strategy

Testing must protect provenance, idempotency, typed outputs, and source extensibility. Tests should use fixtures and local infrastructure before relying on live services.

## Test Categories

### Unit Tests

Cover:

- source config validation
- cursor logic
- dedupe key generation
- content hashing
- parser profiles
- event envelope validation
- Pydantic domain models
- risk score formulas
- entity normalization
- graph key generation
- approval gate logic

### Contract Tests

Cover:

- source adapter output contracts
- parser profile expected chunks
- Pydantic AI output schemas
- Kafka event schemas
- graph upsert payloads
- Grafana dashboard definition schema

Use golden fixtures under `tests/fixtures/`.

### Integration Tests

Run against local compose:

- PostgreSQL migrations and repositories
- Kafka produce/consume/deadletter
- Neo4j constraints and graph writes
- local Grafana provisioning validation where practical

### End-to-End Tests

Use small fixtures or limited live fetches:

- source config -> ingest -> parse -> extract -> resolve -> graph -> risk -> alert.
- replay raw documents with a new extraction schema.
- graph writer idempotent replay.

### Live Source Smoke Tests

Optional and marked:

- openFDA small query
- FDA shortages page fetch
- ReliefWeb API small query if appname configured
- SEC metadata request with user agent

Never require live source tests in default CI.

## Test Data

Fixtures:

- openFDA NDC single and multi-record JSON.
- openFDA recall JSON.
- FDA shortage HTML/download sample.
- device registration/listing JSON.
- GDELT search result sample.
- GDACS RSS item sample.
- ReliefWeb report sample.
- SEC filing excerpt sample.
- World Bank commodity XLS sample.

Fixtures must be small, legally safe, and include expected extraction/evidence outputs.

## Invariants To Test

- No parsed output without a raw document.
- No evidence span without raw document and chunk reference.
- No graph relationship without provenance fields.
- No risk verdict without evidence span IDs or explicit limitation.
- No agent output persisted unless Pydantic validation succeeds.
- No entity merge below threshold.
- No destructive MCP action without approval.
- No source config with literal secrets.

## Idempotency Tests

Required:

- repeated `ingest-once` with same payload creates no duplicate raw document.
- same dedupe key with changed content creates a new version.
- repeated extraction with same prompt/input/schema reuses or no-ops.
- repeated graph upsert updates timestamps but does not duplicate relationships.
- repeated alert emission updates existing alert.

## Failure Tests

Required:

- HTTP timeout creates retryable ingestion error.
- 404 or parser mismatch creates non-retryable error where appropriate.
- invalid agent output marks extraction run failed.
- Kafka consumer deadletters invalid envelope.
- Neo4j failure writes graph deadletter.
- Aiven MCP unavailable uses fallback or fails clearly.

## Type Checking and Linting

Commands:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/platform
uv run pytest
```

If pyright is selected:

```bash
uv run pyright
```

Existing repo checks:

```bash
vp check
vp test
```

Run `vp build` only if frontend or build behavior changes.

## CI Plan

Stages:

1. formatting and lint
2. type check
3. unit tests
4. contract tests
5. integration tests with local compose service containers
6. optional live smoke tests on schedule or manual trigger

CI must not need Aiven credentials for default path.

## Performance Tests

Add after first end-to-end slice:

- ingest 10k JSON records from local fixture.
- parse and chunk 10k records.
- graph upsert batch performance.
- entity resolution candidate retrieval timing.
- risk scoring over graph sample.

## Evaluation Tests for Agents

Agent eval fixtures should include:

- supported extraction
- unsupported claim rejection
- ambiguous entity resolution
- critic finding overclaim
- evidence verifier contradiction
- verdict with limitations

Persist expected structured outputs and compare fields semantically, not exact prose.
