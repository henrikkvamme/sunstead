from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from neo4j import AsyncGraphDatabase

from supply_intel.models.graph import GraphNodeUpsert, GraphRelationshipUpsert


@dataclass(frozen=True)
class Neo4jWriteStatement:
    cypher: str
    parameters: dict[str, object]


@dataclass(frozen=True)
class CypherMigrationResult:
    path: str
    statements: int
    results: list[dict[str, object]]


class Neo4jStatementRunner(Protocol):
    async def run_statement(self, statement: Neo4jWriteStatement) -> dict[str, object]: ...


class CypherRunner(Protocol):
    async def run_cypher(self, cypher: str) -> dict[str, object]: ...


class AsyncNeo4jClient:
    def __init__(self, uri: str, username: str, password: str) -> None:
        self._driver = AsyncGraphDatabase.driver(uri, auth=(username, password))

    async def close(self) -> None:
        await self._driver.close()

    async def run_statement(self, statement: Neo4jWriteStatement) -> dict[str, object]:
        async with self._driver.session() as session:
            result = await session.run(statement.cypher, statement.parameters)
            records = []
            async for record in result:
                record_keys = list(record.keys())
                records.append({key: _neo4j_result_value(record[key]) for key in record_keys})
            summary = await result.consume()
        counters = summary.counters
        return {
            "nodes_created": counters.nodes_created,
            "nodes_deleted": counters.nodes_deleted,
            "relationships_created": counters.relationships_created,
            "relationships_deleted": counters.relationships_deleted,
            "properties_set": counters.properties_set,
            "labels_added": counters.labels_added,
            "record_count": len(records),
            "records": records,
        }

    async def run_cypher(self, cypher: str) -> dict[str, object]:
        async with self._driver.session() as session:
            result = await session.run(cypher)
            summary = await result.consume()
        counters = summary.counters
        return {
            "constraints_added": counters.constraints_added,
            "indexes_added": counters.indexes_added,
        }

    async def run_read_query(
        self,
        cypher: str,
        parameters: dict[str, object],
    ) -> list[dict[str, object]]:
        async with self._driver.session() as session:
            result = await session.run(cypher, parameters)
            records = []
            async for record in result:
                record_keys = list(record.keys())
                records.append({key: _neo4j_result_value(record[key]) for key in record_keys})
            await result.consume()
        return records


def safe_cypher_name(value: str) -> str:
    if not value or not value.replace("_", "").isalnum():
        raise ValueError(f"Unsafe Cypher identifier: {value}")
    return value


def neo4j_properties(values: dict[str, object]) -> dict[str, object]:
    return {key: _neo4j_value(value) for key, value in values.items() if value is not None}


def node_statement(upsert: GraphNodeUpsert) -> Neo4jWriteStatement:
    labels = ":".join(safe_cypher_name(label) for label in upsert.labels)
    properties = neo4j_properties(upsert.properties)
    properties.update(
        neo4j_properties(
            {
                "key": upsert.graph_node_key,
                "graph_node_key": upsert.graph_node_key,
                "labels": list(upsert.labels),
                "source_document_id": upsert.source_document_id,
                "evidence_span_id": upsert.evidence_span_id,
                "extraction_run_id": upsert.extraction_run_id,
                "confidence": upsert.confidence,
            }
        )
    )
    return Neo4jWriteStatement(
        cypher=(
            f"MERGE (n:{labels} {{key: $key}}) "
            "ON CREATE SET n.created_at = datetime(), n.first_seen_at = datetime() "
            "SET n += $properties, n.updated_at = datetime(), n.last_seen_at = datetime() "
            "RETURN n.key AS key"
        ),
        parameters={"key": upsert.graph_node_key, "properties": properties},
    )


def relationship_statement(upsert: GraphRelationshipUpsert) -> Neo4jWriteStatement:
    rel_type = safe_cypher_name(upsert.relationship_type)
    properties = neo4j_properties(upsert.properties.model_dump(mode="json"))
    properties["relationship_key"] = upsert.relationship_key
    return Neo4jWriteStatement(
        cypher=(
            "MATCH (a {key: $from_key}) MATCH (b {key: $to_key}) "
            f"MERGE (a)-[r:{rel_type} {{relationship_key: $relationship_key}}]->(b) "
            "ON CREATE SET r.created_at = datetime(), r.first_seen_at = datetime() "
            "SET r += $properties, r.updated_at = datetime(), r.last_seen_at = datetime() "
            "RETURN r.relationship_key AS key"
        ),
        parameters={
            "from_key": upsert.from_key,
            "to_key": upsert.to_key,
            "relationship_key": upsert.relationship_key,
            "properties": properties,
        },
    )


async def apply_cypher_migrations(
    runner: CypherRunner,
    root: Path = Path("cypher/migrations"),
) -> list[CypherMigrationResult]:
    results: list[CypherMigrationResult] = []
    for path in sorted(root.glob("*.cypher")):
        statements = [
            statement.strip()
            for statement in path.read_text(encoding="utf-8").split(";")
            if statement.strip()
        ]
        statement_results = [await runner.run_cypher(statement) for statement in statements]
        results.append(
            CypherMigrationResult(
                path=str(path),
                statements=len(statements),
                results=statement_results,
            )
        )
    return results


def _neo4j_value(value: object) -> object:
    converted: object
    if value is None or isinstance(value, str | int | float | bool):
        converted = value
    elif isinstance(value, UUID):
        converted = str(value)
    elif isinstance(value, datetime | date):
        converted = value.isoformat()
    elif isinstance(value, list):
        converted = [_neo4j_value(item) for item in value]
        if not _is_scalar_iterable(converted):
            converted = json.dumps(value, default=str, sort_keys=True)
    elif isinstance(value, dict):
        converted = json.dumps(value, default=str, sort_keys=True)
    else:
        converted = str(value)
    return converted


def _is_scalar_iterable(values: Iterable[object]) -> bool:
    return all(value is None or isinstance(value, str | int | float | bool) for value in values)


def _neo4j_result_value(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, list):
        return [_neo4j_result_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _neo4j_result_value(item) for key, item in value.items()}
    return str(value)
