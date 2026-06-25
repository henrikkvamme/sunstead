# Kafka Event Design

Kafka is the transport backbone for asynchronous work and agent communication. PostgreSQL remains the durable source of truth.

## Event Envelope

Every event must use this envelope:

```json
{
  "event_id": "uuid",
  "event_type": "ingest.raw_document_created",
  "schema_version": 1,
  "source": {
    "service": "ingester",
    "source_id": "openfda_drug_ndc",
    "instance_id": "worker-1"
  },
  "emitted_at": "2026-06-24T12:00:00Z",
  "correlation_id": "uuid",
  "causation_id": "uuid-or-null",
  "idempotency_key": "stable-string",
  "trace": {
    "trace_id": "uuid",
    "span_id": "uuid",
    "source_run_id": "uuid",
    "raw_document_id": "uuid-or-null"
  },
  "payload": {}
}
```

Required fields:

- `event_id`
- `event_type`
- `schema_version`
- `source`
- `emitted_at`
- `correlation_id`
- `causation_id`
- `idempotency_key`
- `payload`
- trace metadata

## Serialization

Initial implementation:

- JSON event envelope.
- Pydantic validation on produce and consume.
- `schema_version` integer on every payload model.

Future:

- Enable Aiven Schema Registry/Karapace when deployment requires stronger schema governance.
- Add JSON Schema export from Pydantic models.
- Keep topic names and envelope stable.

## Topic Plan

| Topic                         | Key                      | Producer              | Consumer                                   | Retention | Notes                                  |
| ----------------------------- | ------------------------ | --------------------- | ------------------------------------------ | --------- | -------------------------------------- |
| `ingest.jobs`                 | `source_id`              | scheduler, CLI        | ingester                                   | 7d        | Work queue for source fetches.         |
| `ingest.raw_document_created` | `raw_document_id`        | ingester              | parser, extractor trigger                  | 30d       | Raw document exists in PostgreSQL.     |
| `ingest.document_parsed`      | `document_chunk_id`      | parser                | extractor                                  | 30d       | Parsed chunks ready.                   |
| `ingest.extraction_requested` | `document_chunk_id`      | parser, CLI           | extractor                                  | 14d       | Explicit extraction work.              |
| `ingest.extraction_completed` | `extraction_run_id`      | extractor             | entity resolver, graph mapper, risk engine | 30d       | Validated typed output stored.         |
| `ingest.deadletter`           | `source_id`              | ingestion services    | ops                                        | 30d       | Failed ingestion/parse/extract events. |
| `graph.node_upsert`           | `graph_node_key`         | graph mapper          | graph writer                               | 30d       | Node upsert command.                   |
| `graph.relationship_upsert`   | `graph_relationship_key` | graph mapper          | graph writer                               | 30d       | Relationship upsert command.           |
| `graph.batch_upsert`          | `batch_id`               | graph mapper          | graph writer                               | 30d       | Ordered batch command.                 |
| `graph.deadletter`            | `graph_key`              | graph writer          | ops                                        | 30d       | Failed graph writes.                   |
| `risk.candidates`             | `candidate_key`          | risk engine           | risk engine, swarm                         | 30d       | Initial signals.                       |
| `risk.case_created`           | `risk_case_id`           | risk engine           | swarm, alert worker, dashboards            | 90d       | Durable case in PostgreSQL.            |
| `risk.investigation_tasks`    | `risk_case_id`           | swarm planner         | agents                                     | 30d       | Agent work queue.                      |
| `risk.agent_findings`         | `risk_case_id`           | agents                | verdict agent, critic                      | 90d       | Findings stored in PostgreSQL.         |
| `risk.verdicts`               | `risk_case_id`           | verdict agent         | alert worker, dashboards                   | 90d       | Final or updated verdict.              |
| `risk.alerts`                 | `alert_key`              | alert worker          | notification sinks                         | 90d       | Alert created/updated.                 |
| `agents.commands`             | `agent_name`             | CLI, scheduler, swarm | agents                                     | 7d        | Operational commands.                  |
| `agents.status`               | `agent_name`             | agents                | ops dashboards                             | 7d        | Heartbeats and status.                 |
| `agents.audit_log`            | `correlation_id`         | agents                | audit sink                                 | 90d       | Agent action summary.                  |
| `ops.mcp_actions`             | `action_id`              | AivenMCPController    | audit sink                                 | 90d       | MCP operation events.                  |
| `ops.metrics`                 | `metric_name`            | all services          | metrics sink                               | 7d        | Lightweight app metrics.               |
| `ops.errors`                  | `service`                | all services          | ops                                        | 30d       | Structured errors.                     |

Recommended partitions:

- Development: 1 partition per topic.
- Shared/staging: 3 partitions for high-throughput topics (`ingest.*`, `graph.*`, `risk.*`), 1 for audit.
- Production: choose based on source volume; key by source/document/case to preserve local ordering.

Replication:

- Local Redpanda: 1.
- Aiven Kafka: 3 where broker count permits. Do not set replication above broker count.

## Topic Bootstrap

`init-kafka` must:

- Read topic specs from `infra/kafka/topics.yaml`.
- Use Aiven MCP topic tools if available and allowed.
- Fall back to Kafka AdminClient.
- Set `cleanup.policy=delete` for normal event topics.
- Set `cleanup.policy=compact,delete` for command/status topics where latest state matters.
- Use explicit partitions and replication for every topic.

## Payload Models

### Ingestion

`ingest.jobs` payload:

```json
{
  "schema_version": 1,
  "source_id": "openfda_drug_ndc",
  "source_run_id": "uuid",
  "run_type": "scheduled",
  "cursor": {},
  "config_hash": "sha256",
  "requested_at": "timestamp"
}
```

`ingest.raw_document_created` payload:

```json
{
  "schema_version": 1,
  "source_id": "openfda_drug_ndc",
  "source_run_id": "uuid",
  "raw_document_id": "uuid",
  "source_url": "https://api.fda.gov/drug/ndc.json?...",
  "content_hash": "sha256",
  "content_type": "application/json",
  "fetched_at": "timestamp"
}
```

`ingest.document_parsed` payload:

```json
{
  "schema_version": 1,
  "raw_document_id": "uuid",
  "document_chunk_ids": ["uuid"],
  "parser_profile": "openfda.drug_ndc.v1",
  "chunk_count": 24
}
```

`ingest.extraction_completed` payload:

```json
{
  "schema_version": 1,
  "extraction_run_id": "uuid",
  "raw_document_id": "uuid",
  "document_chunk_id": "uuid",
  "agent_name": "MedicalExtractionAgent",
  "output_schema": "MedicalExtractionOutput",
  "entity_mention_ids": ["uuid"],
  "evidence_span_ids": ["uuid"],
  "status": "succeeded"
}
```

### Graph

`graph.node_upsert` payload:

```json
{
  "schema_version": 1,
  "graph_node_key": "Drug:ndc_product:0002-8215",
  "labels": ["Drug"],
  "properties": {},
  "source_document_id": "uuid",
  "evidence_span_id": "uuid",
  "extraction_run_id": "uuid",
  "confidence": 0.96
}
```

`graph.relationship_upsert` payload:

```json
{
  "schema_version": 1,
  "relationship_key": "Drug:...|CONTAINS_ACTIVE_INGREDIENT|ActiveIngredient:...",
  "from_key": "Drug:...",
  "to_key": "ActiveIngredient:...",
  "relationship_type": "CONTAINS_ACTIVE_INGREDIENT",
  "properties": {
    "confidence": 0.94,
    "source_document_id": "uuid",
    "evidence_span_id": "uuid",
    "extraction_run_id": "uuid",
    "observed_at": "timestamp",
    "valid_from": "timestamp",
    "valid_to": null,
    "source_name": "openFDA Drug NDC",
    "source_url": "https://...",
    "method": "agent_extraction",
    "status": "active"
  }
}
```

### Risk

`risk.candidates` payload:

```json
{
  "schema_version": 1,
  "candidate_key": "shortage:Drug:...",
  "risk_type": "shortage",
  "scope": { "type": "Drug", "graph_key": "Drug:..." },
  "signals": [],
  "initial_score": 72.5,
  "confidence": 0.84,
  "evidence_span_ids": ["uuid"]
}
```

`risk.verdicts` payload:

```json
{
  "schema_version": 1,
  "risk_case_id": "uuid",
  "verdict_type": "confirmed_risk",
  "severity": "high",
  "risk_score": 83.2,
  "confidence": 0.79,
  "summary": "Evidence-backed summary",
  "evidence_span_ids": ["uuid"],
  "recommended_actions": []
}
```

## Consumer Rules

- Validate envelope before payload.
- Validate payload against event type and `schema_version`.
- Check idempotency store before side effects.
- Commit Kafka offsets only after durable side effects are complete.
- Deadletter invalid or permanently failed messages with original event and error.
- Retry transient failures with bounded backoff.
- Preserve `correlation_id` and `causation_id` for every downstream event.

## Schema Evolution

- Additive fields: increment minor model version if using code package versioning; keep `schema_version` if consumers can ignore unknown fields.
- Breaking changes: increment `schema_version`, support old and new consumers during transition.
- Never change meaning of an existing field.
- Never remove provenance fields.
- Keep old payload models in `src/platform/events/versions/`.

## Observability

Emit `ops.metrics` for:

- events produced by topic
- events consumed by topic and consumer group
- validation failures
- processing latency
- retries
- deadletters
- consumer lag if available

Persist event processing errors in `ingestion_errors` or an ops error table depending on stage.
