# Implementation Planning Index

This directory is the implementation-ready plan for the platform. The application is intentionally unnamed. Use "the platform", "the system", or "the application" until naming is explicitly requested.

## Mission

Build an agent-native, MCP-enabled intelligence platform for medicine, pharmaceuticals, medical devices, upstream inputs, suppliers, facilities, logistics, regulatory events, recalls, shortages, disasters, labor disruption, commodity prices, transportation prices, search/news signals, and production-chain risk.

The defining product constraint is provenance: every graph node, graph edge, risk score, alert, agent conclusion, extracted entity, dashboard metric, and user-facing verdict must be traceable back to raw source data, source URLs, raw payloads, extraction runs, timestamps, confidence scores, and evidence spans.

## Planning Assumptions

- The implementation will be a Python 3.12+ backend-first system with a small CLI-first operating surface before a full product UI is layered on.
- Aiven PostgreSQL, Aiven Kafka, and Aiven Grafana are preferred cloud services where credentials and MCP scope are available.
- Local PostgreSQL, Redpanda or Kafka, local Neo4j, and local Grafana must work without Aiven for development and contributor onboarding.
- Neo4j starts local because graph schema and query patterns will evolve quickly. The interface must keep migration to Neo4j Aura and later Aura Graph Analytics straightforward.
- Aiven MCP is an operations control plane, not a hard dependency for business logic. Every MCP operation needs a normal-client fallback.
- LLM providers are OpenAI-compatible and configured through `LLM_BASE_URL`, `LLM_API_KEY`, and `LLM_MODEL`. Embeddings are independently configurable through optional `EMBEDDING_*` variables.
- The system is supply-chain intelligence only. It must not provide medical advice, clinical decisions, patient triage, or patient-identifiable processing.

## Specialist Research Synthesis

1. Aiven MCP Research Agent:
   Aiven MCP is useful for project/service discovery, service lifecycle, Kafka topic operations, PostgreSQL read/write, Kafka REST produce/consume when enabled, metrics, logs, integrations, Kafka Connect, and documentation-backed Aiven questions. It is early/limited availability, supports read-only mode, scoped tools, and optional development-only secret exposure. Fallbacks are required for all runtime paths.

2. Aiven Data Infrastructure Agent:
   PostgreSQL should own raw source storage, provenance, agent memory, canonical entity metadata, risk cases, alerts, and pgvector search. Kafka should carry typed event envelopes between ingestion, extraction, graph, risk, agent, and ops services. Grafana should initially query PostgreSQL directly.

3. Medical Data Source Research Agent:
   OpenFDA NDC, drug enforcement, device registration/listing, and device enforcement are high-priority JSON APIs. FDA drug shortages are official but currently best handled as HTML/download ingestion from FDA AccessData unless a stable official API is later confirmed. GDELT, GDACS, ReliefWeb, SEC EDGAR, World Bank commodity data, EIA, and trade/freight proxies are suitable staged sources.

4. Scraping and Source Extensibility Agent:
   New sources should usually require a source config plus parser profile and fixtures. Adapter classes are reserved for unusual auth, pagination, JavaScript rendering, binary files, or webhook semantics.

5. Pydantic AI Agent Architecture Agent:
   All agent outputs should be Pydantic models. Agents may reason internally but must emit typed extraction outputs, graph upserts, risk signals, findings, verdicts, and alerts. No loose JSON enters PostgreSQL, Kafka, or Neo4j.

6. Entity Resolution Agent:
   Use deterministic keys first, then normalized aliases, `pg_trgm`, pgvector similarity, graph context, and human review queues. Preserve conflicts as first-class records rather than overwriting uncertain facts.

7. Neo4j Graph Schema Agent:
   Local Neo4j can model drugs, ingredients, devices, companies, facilities, suppliers, regions, ports, events, prices, risk cases, sources, and evidence documents. Relationship properties must preserve provenance and temporal validity.

8. Risk Model Agent:
   Start with transparent, explainable scores by risk category and scope. Store all component scores and evidence. Build feature history so later ML models can be trained without changing the traceability contract.

9. Grafana and Observability Agent:
   Initial dashboards should query PostgreSQL for executive risk, source freshness, ingestion throughput, agent activity, risk cases, graph growth, evidence coverage, MCP activity, and low-confidence review queues.

10. Security, Safety, and Governance Agent:
    Keep MCP destructive actions behind approval gates, avoid patient-identifiable data, honor source terms, enforce robots and scraping rules, store secrets outside logs, and audit all source, agent, graph, risk, and MCP activity.

11. Implementation Planner Agent:
    Implement phase by phase with a CLI-first spine: infrastructure bootstrap, migrations, source registry, ingestion, extraction, entity resolution, graph writing, risk scoring, investigation swarm, Grafana dashboards, and migration hardening.

## Document Map

- `01_RESEARCH_AIVEN_MCP.md`: verified Aiven MCP capabilities, limits, and fallbacks.
- `02_RESEARCH_DATA_SOURCES.md`: source candidates, auth, cadence, formats, priority, and caveats.
- `03_ARCHITECTURE.md`: end-to-end system architecture and service boundaries.
- `04_DATA_MODEL_POSTGRES.md`: PostgreSQL schemas, indexes, extensions, and idempotency.
- `05_KAFKA_EVENT_DESIGN.md`: Kafka topic plan, event envelope, versioning, and retention.
- `06_SOURCE_INGESTION_FRAMEWORK.md`: adapter plugin model, source config schema, scheduler, cursoring, dedupe.
- `07_PYDANTIC_AI_AGENTS.md`: agents, typed models, provider configuration, validation.
- `08_ENTITY_RESOLUTION.md`: canonical IDs, aliases, matching, thresholds, review workflow.
- `09_NEO4J_GRAPH_SCHEMA.md`: labels, relationships, constraints, evidence modeling, Aura migration.
- `10_RISK_MODEL.md`: transparent risk scoring, risk cases, features, verdicts.
- `11_GRAFANA_OBSERVABILITY.md`: dashboards, SQL examples, provisioning strategy.
- `12_SECURITY_GOVERNANCE.md`: MCP safety, source compliance, secrets, audit, disclaimers.
- `13_REPOSITORY_STRUCTURE.md`: Python monorepo layout and CLI command map.
- `14_IMPLEMENTATION_PHASES.md`: practical build sequence and dependency graph.
- `15_TESTING_STRATEGY.md`: unit, integration, contract, golden fixture, and end-to-end tests.
- `16_LOCAL_TO_CLOUD_MIGRATION.md`: local-first to Aiven and Neo4j Aura migration path.
- `GOAL.md`: compact `/goal` prompt for one long implementation session.

## Recommended Execution Order

1. Establish repository skeleton, tooling, settings, and CLI.
2. Create local compose stack and AivenMCPController abstraction.
3. Add PostgreSQL migrations and source/evidence schema.
4. Add Kafka topic bootstrap and typed event envelope.
5. Implement source registry, adapters, scheduler, cursors, dedupe, and raw-first storage.
6. Implement parsers, chunking, evidence spans, and Pydantic AI extraction.
7. Implement entity resolution and canonical entity writes.
8. Implement graph mapping, Neo4j constraints, graph writer, and audit.
9. Implement transparent risk detection, cases, findings, verdicts, and alerts.
10. Implement investigation swarm with critic and evidence verifier loops.
11. Provision Grafana dashboards and operational metrics.
12. Harden security, governance, tests, docs, migration, and deployment runbooks.

## Non-Negotiable Implementation Rules

- Raw source payloads are stored before parsing, extraction, graph writes, risk scoring, or alerts.
- Every derived object carries provenance IDs and confidence.
- Agent outputs are Pydantic models with explicit schema versions.
- Kafka events use the standard envelope in `05_KAFKA_EVENT_DESIGN.md`.
- Neo4j writes are idempotent and audited in PostgreSQL.
- MCP operations are audited, least-privilege, and optional.
- No source adapter silently ignores licensing, robots, rate limits, or scraping ethics.
- No patient-identifiable data is collected by default.

## Primary References Used

- Aiven MCP docs: https://aiven.io/docs/tools/mcp-server
- openFDA authentication and limits: https://open.fda.gov/apis/authentication/
- openFDA query parameters: https://open.fda.gov/apis/query-parameters/
- openFDA downloads: https://open.fda.gov/apis/downloads/
- PostgreSQL `pg_trgm`: https://www.postgresql.org/docs/current/pgtrgm.html
- pgvector: https://github.com/pgvector/pgvector
- Pydantic AI docs via Context7: https://ai.pydantic.dev/
- Neo4j docs via Context7: https://neo4j.com/docs/
- Grafana PostgreSQL provisioning docs via Context7: https://grafana.com/docs/
