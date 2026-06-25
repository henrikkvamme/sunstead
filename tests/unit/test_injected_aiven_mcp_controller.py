from pathlib import Path
from typing import Any

import pytest

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.infra.aiven_mcp import InjectedAivenMCPController
from supply_intel.models.infra import KafkaRecord


class FakeMCPTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool_name, arguments))
        if tool_name == "aiven_pg_read":
            return {
                "meta": {"fields": ["table_name", "row_count"]},
                "rows": [{"table_name": "raw_documents", "row_count": 1}],
            }
        if tool_name == "aiven_pg_write":
            return {
                "meta": {"fields": ["table_name", "affected_rows"]},
                "rows": [{"table_name": "source_health", "affected_rows": 1}],
            }
        if tool_name == "aiven_kafka_topic_message_produce":
            return {"offsets": [{"partition": 0, "offset": 42}]}
        if tool_name == "aiven_kafka_topic_message_list":
            return {
                "messages": [
                    {
                        "key": {"source_id": "openfda_drug_ndc"},
                        "value": {
                            "event_type": "ingest.jobs",
                            "payload": {"source_id": "openfda_drug_ndc"},
                        },
                    }
                ]
            }
        raise AssertionError(f"Unexpected MCP tool call: {tool_name}")


def controller(tmp_path: Path, tools: FakeMCPTools) -> InjectedAivenMCPController:
    return InjectedAivenMCPController(
        invoke_tool=tools,
        project="demo-project",
        postgres_service="platform-pg",
        kafka_service="platform-kafka",
        audit_sink=FileEvidenceStore(tmp_path),
    )


async def test_injected_aiven_mcp_controller_reads_and_writes_postgres(
    tmp_path: Path,
) -> None:
    tools = FakeMCPTools()
    mcp = controller(tmp_path, tools)

    read_result = await mcp.pg_read("SELECT 'raw_documents' AS table_name, 1 AS row_count")
    write_result = await mcp.pg_write("INSERT INTO source_health (source_id) VALUES ('x')")

    assert read_result.columns == ["table_name", "row_count"]
    assert read_result.rows[0]["row_count"] == 1
    assert write_result.columns == ["table_name", "affected_rows"]
    assert [name for name, _ in tools.calls] == ["aiven_pg_read", "aiven_pg_write"]
    assert tools.calls[0][1]["service_name"] == "platform-pg"

    audit_rows = FileEvidenceStore(tmp_path).read_collection("mcp_audit_log")
    assert [row["action"] for row in audit_rows] == ["pg_read", "pg_write"]
    assert [row["status"] for row in audit_rows] == ["succeeded", "succeeded"]
    assert audit_rows[0]["metadata"]["safety_level"] == "safe_read"
    assert audit_rows[1]["metadata"]["safety_level"] == "safe_write_dev"


async def test_injected_aiven_mcp_controller_produces_and_reads_kafka(
    tmp_path: Path,
) -> None:
    tools = FakeMCPTools()
    mcp = controller(tmp_path, tools)

    produced = await mcp.kafka_produce(
        "ingest.jobs",
        [
            KafkaRecord(
                key="openfda_drug_ndc",
                value={"event_type": "ingest.jobs", "payload": {"source_id": "openfda_drug_ndc"}},
            )
        ],
    )
    consumed = await mcp.kafka_read("ingest.jobs", {0: 42})

    assert produced.topic == "ingest.jobs"
    assert produced.produced == 1
    assert consumed.records[0].value["event_type"] == "ingest.jobs"
    assert consumed.records[0].key == '{"source_id":"openfda_drug_ndc"}'
    assert [name for name, _ in tools.calls] == [
        "aiven_kafka_topic_message_produce",
        "aiven_kafka_topic_message_list",
    ]
    assert tools.calls[0][1]["records"][0]["key"] == {"key": "openfda_drug_ndc"}
    assert tools.calls[1][1]["partitions"] == {"0": {"offset": 42}}

    audit_rows = FileEvidenceStore(tmp_path).read_collection("mcp_audit_log")
    assert [row["action"] for row in audit_rows] == ["kafka_produce", "kafka_read"]
    assert audit_rows[0]["response_summary"] == {"topic": "ingest.jobs", "produced": 1}
    assert audit_rows[1]["response_summary"] == {"topic": "ingest.jobs", "record_count": 1}


async def test_injected_aiven_mcp_controller_audits_failures(tmp_path: Path) -> None:
    async def failing_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        del tool_name, arguments
        raise RuntimeError("MCP unavailable")

    mcp = InjectedAivenMCPController(
        invoke_tool=failing_tool,
        project="demo-project",
        postgres_service="platform-pg",
        audit_sink=FileEvidenceStore(tmp_path),
    )

    with pytest.raises(RuntimeError, match="MCP unavailable"):
        await mcp.pg_read("SELECT 1")

    audit_rows = FileEvidenceStore(tmp_path).read_collection("mcp_audit_log")
    assert audit_rows[0]["action"] == "pg_read"
    assert audit_rows[0]["status"] == "failed"
    assert "MCP unavailable" in audit_rows[0]["error"]
