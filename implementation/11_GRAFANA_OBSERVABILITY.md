# Grafana and Observability

Grafana is the first operational and product intelligence surface. Use Aiven Grafana with PostgreSQL datasource in cloud, and local Grafana with the same dashboard JSON in development.

## Data Source Strategy

Primary datasource:

- PostgreSQL, queried directly for source health, ingestion metrics, graph audit, risk cases, alerts, and agent activity.

Future datasources:

- Kafka lag exporter or Aiven Kafka metrics.
- Neo4j metrics.
- Prometheus/OpenTelemetry.
- Aiven service metrics API snapshots written into PostgreSQL.

Provisioning:

- Local Grafana: checked-in provisioning files under `infra/grafana/provisioning/`.
- Aiven Grafana: use Grafana HTTP API or Aiven service integration where available.
- Dashboards are generated from templates in `dashboards/` and committed as JSON.

Example PostgreSQL datasource provisioning:

```yaml
apiVersion: 1
datasources:
  - name: Platform PostgreSQL
    type: postgres
    access: proxy
    url: ${GRAFANA_POSTGRES_HOST}:${GRAFANA_POSTGRES_PORT}
    user: ${GRAFANA_POSTGRES_USER}
    secureJsonData:
      password: ${GRAFANA_POSTGRES_PASSWORD}
    jsonData:
      database: ${GRAFANA_POSTGRES_DB}
      sslmode: verify-full
      postgresVersion: 1700
      timescaledb: false
```

For local compose, use `sslmode: disable`. For Aiven PostgreSQL, use TLS verification and the Aiven CA.

## Dashboards

### Executive Risk Overview

Panels:

- open risk cases by severity
- top 20 current risk cases
- risk score trend
- new/updated alerts
- cases needing human review
- highest-risk drugs, ingredients, devices, suppliers, and facilities

Primary tables:

- `risk_cases`
- `risk_alerts`
- `agent_findings`
- `canonical_entities`

Example query:

```sql
SELECT severity, count(*) AS cases
FROM risk_cases
WHERE status IN ('candidate', 'investigating', 'watch', 'confirmed', 'needs_human_review')
GROUP BY severity;
```

### Medicine and Drug Manufacturing Risk

Panels:

- drugs in shortage
- active ingredients with rising risk
- manufacturers with recurring recalls
- facilities linked to high-risk products
- graph dependency risk by ingredient

Example:

```sql
SELECT ce.display_name, rc.risk_type, rc.risk_score, rc.confidence, rc.status
FROM risk_cases rc
JOIN canonical_entities ce ON ce.id = rc.scope_entity_id
WHERE rc.scope_type IN ('Drug', 'ActiveIngredient', 'Manufacturer', 'Facility')
ORDER BY rc.risk_score DESC
LIMIT 50;
```

### Source Freshness

Panels:

- source status
- freshness lag
- consecutive failures
- last successful run
- source records created per day

Example:

```sql
SELECT ds.source_id, sh.status, sh.last_success_at, sh.freshness_lag_seconds, sh.consecutive_failures
FROM data_sources ds
LEFT JOIN source_health sh ON sh.source_id = ds.source_id
WHERE ds.enabled = true
ORDER BY sh.status, sh.freshness_lag_seconds DESC NULLS LAST;
```

### Ingestion Throughput

Panels:

- documents created per hour
- unchanged documents per run
- parser/extraction backlog
- ingestion errors by stage
- deadletter counts

Example:

```sql
SELECT date_trunc('hour', fetched_at) AS bucket, count(*) AS raw_documents
FROM raw_documents
WHERE fetched_at >= now() - interval '7 days'
GROUP BY bucket
ORDER BY bucket;
```

### Agent Activity

Panels:

- extraction runs by status
- model usage
- average run duration
- validation failures
- findings by agent

Example:

```sql
SELECT agent_name, status, count(*) AS runs
FROM extraction_runs
WHERE started_at >= now() - interval '24 hours'
GROUP BY agent_name, status;
```

### MCP Audit Activity

Panels:

- MCP actions by safety level
- destructive actions pending approval
- failed MCP actions
- credential access attempts

Example:

```sql
SELECT action, status, destructive, count(*) AS actions
FROM mcp_audit_log
WHERE started_at >= now() - interval '7 days'
GROUP BY action, status, destructive
ORDER BY actions DESC;
```

### Risk Cases

Panels:

- case lifecycle funnel
- verdict distribution
- median investigation time
- cases by source driver
- cases by graph scope

### Source Failures

Panels:

- error rate by source/stage
- retryable versus non-retryable
- latest errors
- sources disabled by policy

### Graph Growth

Panels:

- graph upserts by label/type
- failed graph writes
- node/relationship growth snapshots
- evidence document coverage

If Neo4j metrics are not available directly, write periodic graph stats to PostgreSQL.

### Evidence Coverage

Panels:

- percentage of risk cases with evidence spans
- unsupported/partially supported claims
- extraction confidence distribution
- source reliability mix

### Low-Confidence Relationships Needing Review

Panels:

- entity matches needing review
- graph relationships below confidence threshold
- high-impact unresolved entities
- conflicting evidence cases

## Dashboard Generation

Implement:

```bash
uv run platform create-dashboard executive-risk-overview --out dashboards/executive-risk-overview.json
uv run platform create-dashboard all --provision
```

Dashboard definitions:

- `dashboards/definitions/*.yaml` for logical panels.
- `dashboards/generated/*.json` for Grafana import.
- `infra/grafana/provisioning/dashboards/*.yaml` for local provisioning.

Avoid hand-editing generated JSON unless the generator supports round-trip.

## Operational Metrics

Every service should emit structured metrics to `ops.metrics` and optionally PostgreSQL:

- `documents_fetched_total`
- `documents_unchanged_total`
- `ingestion_errors_total`
- `extraction_runs_total`
- `extraction_latency_seconds`
- `agent_tokens_input_total`
- `agent_tokens_output_total`
- `graph_upserts_total`
- `graph_upsert_failures_total`
- `risk_cases_created_total`
- `alerts_emitted_total`
- `mcp_actions_total`

## Alerting

Grafana alerts can be added after dashboards stabilize:

- no successful source run past SLA
- ingestion errors above threshold
- extraction failures above threshold
- graph deadletters nonzero
- high/critical risk case created
- MCP destructive action failed or pending
- evidence coverage below threshold

Product alerts should still be stored in `risk_alerts`; Grafana alerting is operational.
