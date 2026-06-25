# Repository Structure

The implementation should add a Python monorepo alongside the existing frontend repository without disrupting current Vite+ conventions.

## Target Layout

```text
.
├── implementation/
├── pyproject.toml
├── uv.lock
├── src/
│   └── platform/
│       ├── __init__.py
│       ├── cli.py
│       ├── settings.py
│       ├── logging.py
│       ├── db/
│       │   ├── postgres.py
│       │   ├── migrations.py
│       │   └── repositories/
│       ├── events/
│       │   ├── envelope.py
│       │   ├── producer.py
│       │   ├── consumer.py
│       │   └── topics.py
│       ├── infra/
│       │   ├── aiven_mcp.py
│       │   ├── aiven_api.py
│       │   ├── local.py
│       │   └── bootstrap.py
│       ├── sources/
│       │   ├── registry.py
│       │   ├── scheduler.py
│       │   ├── adapters/
│       │   ├── parsers/
│       │   └── profiles/
│       ├── models/
│       │   ├── source.py
│       │   ├── documents.py
│       │   ├── extraction.py
│       │   ├── medical.py
│       │   ├── events.py
│       │   ├── graph.py
│       │   ├── risk.py
│       │   ├── kafka.py
│       │   └── infra.py
│       ├── agents/
│       │   ├── factory.py
│       │   ├── source_onboarding.py
│       │   ├── fetch_planner.py
│       │   ├── medical_extraction.py
│       │   ├── entity_resolution.py
│       │   ├── graph_mapping.py
│       │   ├── risk_signal.py
│       │   ├── evidence_verifier.py
│       │   ├── graph_blast_radius.py
│       │   ├── critic.py
│       │   ├── verdict.py
│       │   └── infra_ops.py
│       ├── entity_resolution/
│       ├── graph/
│       │   ├── neo4j_client.py
│       │   ├── writer.py
│       │   └── queries.py
│       ├── risk/
│       │   ├── scoring.py
│       │   ├── cases.py
│       │   ├── swarm.py
│       │   └── alerts.py
│       └── observability/
│           ├── metrics.py
│           └── grafana.py
├── migrations/
├── cypher/
│   ├── migrations/
│   └── queries/
├── sources/
│   ├── openfda_drug_ndc.yaml
│   └── ...
├── dashboards/
│   ├── definitions/
│   └── generated/
├── infra/
│   ├── docker-compose.yml
│   ├── kafka/topics.yaml
│   └── grafana/provisioning/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── fixtures/
│   └── e2e/
├── scripts/
└── docs/
```

## Python Tooling

Dependencies:

- Python 3.12+
- `uv`
- `pydantic>=2`
- `pydantic-ai`
- `httpx`
- `tenacity`
- async PostgreSQL client, preferably `asyncpg`
- migration tool, preferably Alembic
- Kafka client, preferably `aiokafka` or `confluent-kafka`
- `neo4j`
- `typer` for CLI
- `ruff`
- `mypy` or `pyright`
- `pytest`
- `pytest-asyncio`
- parsing libraries as needed: `beautifulsoup4`, `feedparser`, `lxml`, `pandas`, `openpyxl`, `pypdf` or equivalent
- `playwright` only when JS rendering is required

## CLI Commands

Required commands:

- `bootstrap-infra`
- `init-db`
- `init-kafka`
- `init-neo4j`
- `validate-source`
- `register-source`
- `ingest-once`
- `run-scheduler`
- `run-extractor`
- `run-graph-writer`
- `run-risk-engine`
- `run-agent-swarm`
- `create-dashboard`
- `query-sources`
- `query-graph`
- `explain-case`

Recommended command shape:

```bash
uv run platform bootstrap-infra --mode local
uv run platform init-db
uv run platform init-kafka
uv run platform init-neo4j
uv run platform validate-source sources/openfda_drug_ndc.yaml
uv run platform register-source sources/openfda_drug_ndc.yaml
uv run platform ingest-once openfda_drug_ndc --max-documents 100
uv run platform run-scheduler
uv run platform run-extractor
uv run platform run-graph-writer
uv run platform run-risk-engine
uv run platform run-agent-swarm --case-id <uuid>
uv run platform create-dashboard all --provision
uv run platform query-sources --status failed
uv run platform query-graph drug-supply-chain --drug-key <key>
uv run platform graph-insights --data-dir /tmp/platform-large-graph --top 10
uv run platform explain-case <case-key>
```

Additional operator shortcuts can compose the required spine without becoming
runtime dependencies. The current demo shortcut is:

```bash
uv run platform prepare-demo \
  --data-dir /tmp/platform-ndc \
  --snapshot-output public/platform-demo/supply-chain-graph.json \
  --max-documents-per-source 1
```

For a larger local graph that can be replayed into Neo4j and exported to the
custom dashboard, run:

```bash
uv run platform backfill-graph \
  --mode live \
  --data-dir /tmp/platform-large-graph \
  --priority P0 \
  --priority P1 \
  --target-graph-nodes 10000 \
  --max-documents-per-source 200 \
  --max-rounds 10

uv run platform sync-graph-view \
  --data-dir /tmp/platform-large-graph \
  --apply-neo4j \
  --snapshot-source neo4j \
  --output public/platform-demo/supply-chain-graph.json \
  --limit 5000
```

## Configuration Files

- `.env.example`: all required env vars without secrets.
- `sources/*.yaml`: source configs.
- `infra/kafka/topics.yaml`: topic specs.
- `infra/docker-compose.yml`: local PostgreSQL, Redpanda/Kafka, Neo4j, Grafana.
- `cypher/migrations/*.cypher`: graph schema.
- `dashboards/definitions/*.yaml`: dashboard definitions.

## Existing Frontend

The existing TanStack/Vite+ app can later become the product UI. For now:

- Do not replace existing `src/routes` frontend files during backend planning implementation.
- Keep Python package paths under `src/platform`.
- If Python packaging conflicts with frontend `src`, configure pyproject package discovery explicitly.

## Handoff Commands

After implementation changes:

- Python: `uv run ruff check .`, `uv run mypy src/platform`, `uv run pytest`.
- Existing repo requirement: `vp check` and `vp test`.
- `vp build` only if frontend/build behavior changes.
