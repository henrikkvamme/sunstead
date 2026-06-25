# Neo4j Graph Schema

Neo4j is the dependency and blast-radius graph. It starts local and must migrate cleanly to Neo4j Aura. Every node and relationship upsert is idempotent and audited in PostgreSQL.

## Required Labels

- `Drug`
- `NDC`
- `ActiveIngredient`
- `Excipient`
- `RawMaterial`
- `ChemicalInput`
- `Manufacturer`
- `Supplier`
- `Facility`
- `MedicalDevice`
- `DeviceCategory`
- `RegulatoryAgency`
- `Country`
- `Region`
- `City`
- `Port`
- `TransportRoute`
- `Commodity`
- `Shortage`
- `Recall`
- `RegulatoryNotice`
- `NewsEvent`
- `DisasterEvent`
- `StrikeEvent`
- `PriceObservation`
- `RiskCase`
- `EvidenceDocument`
- `Source`

## Required Relationship Types

- `HAS_NDC`
- `CONTAINS_ACTIVE_INGREDIENT`
- `CONTAINS_EXCIPIENT`
- `USES_INPUT`
- `LINKED_TO_COMMODITY`
- `LABELS`
- `MARKETS`
- `PRODUCES`
- `OPERATES`
- `SUPPLIES`
- `SUPPLIES_INPUT`
- `LOCATED_IN`
- `NEAR_PORT`
- `CONNECTS`
- `MANUFACTURED_BY`
- `MANUFACTURED_AT`
- `BELONGS_TO_CATEGORY`
- `INVOLVES`
- `MENTIONS`
- `AFFECTS`
- `OBSERVED_FOR`
- `ABOUT`
- `SUPPORTED_BY`
- `HAS_EVIDENCE`

## Node Properties

All nodes:

- `key`: stable graph key, unique per label where possible
- `name`
- `source_entity_id`: PostgreSQL canonical entity UUID when applicable
- `external_ids`
- `created_at`
- `updated_at`
- `first_seen_at`
- `last_seen_at`
- `confidence`
- `status`

Event nodes:

- `event_id`
- `event_type`
- `observed_at`
- `started_at`
- `ended_at`
- `severity`
- `source_id`

Evidence nodes:

- `raw_document_id`
- `source_id`
- `source_url`
- `content_hash`
- `fetched_at`

## Relationship Provenance Properties

Every edge must support:

- `confidence`
- `source_document_id`
- `evidence_span_id`
- `extraction_run_id`
- `observed_at`
- `valid_from`
- `valid_to`
- `source_name`
- `source_url`
- `method`
- `status`

Additional recommended properties:

- `relationship_key`
- `first_seen_at`
- `last_seen_at`
- `schema_version`
- `support_count`
- `contradiction_count`

## Constraints and Indexes

Initial Cypher:

```cypher
CREATE CONSTRAINT drug_key IF NOT EXISTS FOR (n:Drug) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT ndc_key IF NOT EXISTS FOR (n:NDC) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT active_ingredient_key IF NOT EXISTS FOR (n:ActiveIngredient) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT excipient_key IF NOT EXISTS FOR (n:Excipient) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT raw_material_key IF NOT EXISTS FOR (n:RawMaterial) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT chemical_input_key IF NOT EXISTS FOR (n:ChemicalInput) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT manufacturer_key IF NOT EXISTS FOR (n:Manufacturer) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT supplier_key IF NOT EXISTS FOR (n:Supplier) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT facility_key IF NOT EXISTS FOR (n:Facility) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT device_key IF NOT EXISTS FOR (n:MedicalDevice) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT device_category_key IF NOT EXISTS FOR (n:DeviceCategory) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT agency_key IF NOT EXISTS FOR (n:RegulatoryAgency) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT country_key IF NOT EXISTS FOR (n:Country) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT region_key IF NOT EXISTS FOR (n:Region) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT city_key IF NOT EXISTS FOR (n:City) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT port_key IF NOT EXISTS FOR (n:Port) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT route_key IF NOT EXISTS FOR (n:TransportRoute) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT commodity_key IF NOT EXISTS FOR (n:Commodity) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT shortage_key IF NOT EXISTS FOR (n:Shortage) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT recall_key IF NOT EXISTS FOR (n:Recall) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT notice_key IF NOT EXISTS FOR (n:RegulatoryNotice) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT news_key IF NOT EXISTS FOR (n:NewsEvent) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT disaster_key IF NOT EXISTS FOR (n:DisasterEvent) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT strike_key IF NOT EXISTS FOR (n:StrikeEvent) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT price_key IF NOT EXISTS FOR (n:PriceObservation) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT risk_case_key IF NOT EXISTS FOR (n:RiskCase) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT evidence_document_key IF NOT EXISTS FOR (n:EvidenceDocument) REQUIRE n.key IS UNIQUE;
CREATE CONSTRAINT source_key IF NOT EXISTS FOR (n:Source) REQUIRE n.key IS UNIQUE;
```

Indexes:

```cypher
CREATE INDEX drug_name IF NOT EXISTS FOR (n:Drug) ON (n.name);
CREATE INDEX manufacturer_name IF NOT EXISTS FOR (n:Manufacturer) ON (n.name);
CREATE INDEX facility_location IF NOT EXISTS FOR (n:Facility) ON (n.country, n.city);
CREATE INDEX event_observed_at IF NOT EXISTS FOR (n:NewsEvent) ON (n.observed_at);
CREATE INDEX risk_status IF NOT EXISTS FOR (n:RiskCase) ON (n.status, n.severity);
```

## Idempotent MERGE Patterns

Node upsert:

```cypher
MERGE (n:Drug {key: $key})
ON CREATE SET
  n.created_at = datetime(),
  n.first_seen_at = datetime()
SET
  n += $properties,
  n.updated_at = datetime(),
  n.last_seen_at = datetime()
RETURN n.key AS key
```

Relationship upsert:

```cypher
MATCH (a {key: $from_key})
MATCH (b {key: $to_key})
MERGE (a)-[r:CONTAINS_ACTIVE_INGREDIENT {relationship_key: $relationship_key}]->(b)
ON CREATE SET
  r.created_at = datetime(),
  r.first_seen_at = datetime()
SET
  r += $properties,
  r.updated_at = datetime(),
  r.last_seen_at = datetime()
RETURN r.relationship_key AS key
```

Avoid dynamic labels/types in raw string interpolation. Use a small approved mapping from Pydantic enums to Cypher templates.

## Evidence Modeling

Two complementary patterns:

1. Edge properties contain provenance fields for fast traversal.
2. Evidence nodes allow explicit paths:

```text
(Source)-[:HAS_EVIDENCE]->(EvidenceDocument)
(EvidenceDocument)-[:MENTIONS]->(Drug)
(RiskCase)-[:SUPPORTED_BY]->(EvidenceDocument)
(Recall)-[:HAS_EVIDENCE]->(EvidenceDocument)
```

PostgreSQL remains the full evidence store. Neo4j carries enough evidence identity to navigate and explain graph results.

## Temporal Validity

Use:

- `observed_at`: when the source observed or reported the fact.
- `valid_from`: when the fact became true if known.
- `valid_to`: when the fact ended if known.
- `first_seen_at`: first platform ingestion.
- `last_seen_at`: most recent platform observation.
- `status`: `active`, `inactive`, `superseded`, `disputed`.

Do not delete old edges when facts change. Mark `valid_to` and status where appropriate.

## Query Library

Implement named graph queries in `cypher/queries/`:

- `drug_supply_chain.cypher`: Drug -> ingredients -> inputs -> suppliers/facilities.
- `facility_downstream_products.cypher`: Facility -> produced/manufactured products.
- `ingredient_dependency.cypher`: Ingredient -> drugs and shortages.
- `port_exposure.cypher`: Port/route -> facilities and products.
- `recall_blast_radius.cypher`: Recall -> affected drugs/devices/manufacturers.
- `shortage_blast_radius.cypher`: Shortage -> affected ingredients/products.
- `disaster_facility_exposure.cypher`: Disaster region -> facilities/suppliers.
- `commodity_input_exposure.cypher`: Commodity price -> linked inputs/products.
- `risk_case_context.cypher`: RiskCase -> evidence, affected nodes, paths.

Each query has:

- parameters schema
- expected result model
- fixture graph
- integration test

## Aura Migration Path

Keep connection settings generic:

- local URI: `neo4j://localhost:7687`
- Aura URI: `neo4j+s://<id>.databases.neo4j.io`

Migration steps:

1. Ensure all constraints and indexes are in `cypher/migrations`.
2. Export graph from local using `neo4j-admin database dump` or Cypher batch export, depending on deployment.
3. Recreate constraints in Aura.
4. Batch load nodes and relationships with stable keys.
5. Run graph writer in replay mode from PostgreSQL `graph_upsert_audit` to verify idempotency.
6. Swap `NEO4J_URI` and credentials.

## Future Graph Data Science

Plan future use of Neo4j Graph Data Science or Aura Graph Analytics for:

- centrality: critical suppliers, facilities, ingredients, ports.
- community detection: supply clusters and manufacturer ecosystems.
- path finding: shortest and weighted risk paths.
- node embeddings: graph-context entity resolution and risk features.
- node classification: risk-prone facility/supplier classification.
- link prediction: likely supplier/product connections needing verification.

GDS outputs must be written back as typed risk features with model version, run ID, and confidence. They must not replace evidence-backed facts.
