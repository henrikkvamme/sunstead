# Local to Cloud Migration

The system starts local-first and migrates service by service to managed infrastructure. Cloud should not require rewriting business logic.

## Local Development Stack

Docker Compose services:

- PostgreSQL with `pgvector` and `pg_trgm`
- Redpanda or Kafka
- Neo4j Community or Enterprise local image
- Grafana

Local env:

```env
DATABASE_URL=postgresql://platform:platform@localhost:5432/platform
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
NEO4J_URI=neo4j://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=platform
GRAFANA_URL=http://localhost:3000
```

Do not assume these ports in this repo's frontend runtime. They apply to backend compose only and may be remapped by implementation.

## Aiven Cloud Target

Preferred cloud services:

- Aiven PostgreSQL for source/evidence DB, memory DB, metadata DB, and pgvector store.
- Aiven Kafka for event backbone and agent-to-agent communication.
- Aiven Grafana for dashboards and operational visibility.
- Local Neo4j initially.
- Neo4j Aura later.

## Migration Step 1: PostgreSQL

1. Discover or create Aiven PostgreSQL with explicit project/plan/cloud.
2. Verify service is running.
3. Confirm required extensions are available: `vector`, `pg_trgm`, UUID support.
4. Retrieve credentials only through approved secret path.
5. Configure TLS with Aiven CA; do not disable verification.
6. Run migrations.
7. Run repository integration tests against Aiven in a non-production project.

Fallback:

- stay on local PostgreSQL if extensions or credentials are unavailable.

## Migration Step 2: Kafka

1. Discover or create Aiven Kafka with explicit project/plan/cloud.
2. Ensure topic specs with partitions and replication.
3. Enable Kafka REST only if MCP produce/consume is operationally needed.
4. Enable Schema Registry only when schema governance is needed.
5. Configure clients with TLS/SASL or mTLS as provided.
6. Run event integration tests.

Fallback:

- local Redpanda/Kafka.
- direct Kafka AdminClient if MCP topic tools unavailable.

## Migration Step 3: Grafana

1. Discover or create Aiven Grafana.
2. Configure PostgreSQL datasource.
3. Provision dashboards through Grafana API or import JSON.
4. Validate dashboard SQL queries.
5. Add operational alerts later.

Fallback:

- local Grafana with provisioning files.

## Migration Step 4: Neo4j Aura

1. Keep graph access through `Neo4jClient`.
2. Apply constraints and indexes from `cypher/migrations`.
3. Export/replay graph from PostgreSQL `graph_upsert_audit`.
4. Validate graph counts and sampled paths.
5. Switch `NEO4J_URI` from local `neo4j://` to Aura `neo4j+s://`.
6. Run graph query integration tests.

Do not make local-only assumptions about file paths, plugins, APOC, or GDS in core writer code.

## Migration Step 5: Graph Analytics

After stable graph:

- evaluate Neo4j Graph Data Science locally.
- evaluate Aura Graph Analytics.
- add centrality, community detection, path finding, embeddings, node classification, and link prediction outputs as risk features.

Do not let analytics outputs become facts without evidence.

## Aiven MCP Use in Migration

Use MCP for:

- project discovery
- service discovery
- service status
- topic creation where allowed
- PostgreSQL read/write for small bootstrap statements where safe
- metrics/log inspection
- service integration discovery

Use fallbacks for:

- long migrations
- app runtime connections
- high-volume Kafka produce/consume
- secrets in production
- unsupported Grafana provisioning
- plan-gated Kafka Connect or PgBouncer

## Environment Separation

Recommended environments:

- `local`
- `dev-cloud`
- `staging`
- `production`

Each environment has:

- separate database
- separate Kafka topics or cluster
- separate Neo4j database
- separate Grafana folders
- explicit source enablement
- separate LLM keys and rate limits

## Data Migration and Replay

Because raw documents and graph audit are durable:

- PostgreSQL is the primary migration asset.
- Kafka does not need long-term replay beyond retention if PostgreSQL can re-emit derived events.
- Neo4j can be rebuilt from canonical entities, extraction outputs, and graph audit.
- Risk cases can be recomputed but old verdicts should remain auditable.

Replay commands:

```bash
uv run platform replay-raw --source-id openfda_drug_ndc --from 2026-01-01
uv run platform replay-graph --from-audit
uv run platform recompute-risk --scope all
```

## Rollback

Rollback principles:

- Keep local stack runnable at all times.
- Use migrations with clear rollback notes.
- Do not destroy Aiven services automatically.
- For graph migration, rollback is switching `NEO4J_URI` back to local and replaying missed writes.
- For Kafka migration, dual-produce only if required and carefully idempotent.
