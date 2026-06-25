from pathlib import Path

import httpx
import pytest

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.infra.aiven_api import (
    AivenApiController,
    AivenApiError,
    AivenApiUnsupportedOperation,
)
from supply_intel.models.infra import KafkaTopicSpec, MCPAuditAction
from supply_intel.settings import Settings

EXPECTED_SERVICE_COUNT = 2


def _ok_transport() -> httpx.MockTransport:
    return httpx.MockTransport(lambda _: httpx.Response(200))


async def test_aiven_api_controller_discovers_projects_and_services(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []
    store = FileEvidenceStore(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-token"
        if request.url.path == "/v1/project":
            return httpx.Response(
                200,
                json={
                    "projects": [
                        {
                            "project_name": "demo-project",
                            "default_cloud": "google-europe-north1",
                        }
                    ]
                },
            )
        if request.url.path == "/v1/project/demo-project/service":
            return httpx.Response(
                200,
                json={
                    "services": [
                        {
                            "service_name": "platform-pg",
                            "service_type": "pg",
                            "state": "RUNNING",
                        },
                        {
                            "service_name": "platform-kafka",
                            "service_type": "kafka",
                            "state": "RUNNING",
                        },
                    ]
                },
            )
        if request.url.path == "/v1/project/demo-project/service/platform-pg":
            return httpx.Response(
                200,
                json={
                    "service_name": "platform-pg",
                    "service_type": "pg",
                    "state": "RUNNING",
                },
            )
        return httpx.Response(404, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        controller = AivenApiController(
            api_token="test-token",
            base_url="https://api.aiven.io/v1",
            default_project="demo-project",
            audit_sink=store,
            client=client,
        )

        projects = await controller.discover_projects()
        services = await controller.discover_services()
        service = await controller.get_service("demo-project", "platform-pg")

    assert projects[0].project_name == "demo-project"
    assert projects[0].default_cloud == "google-europe-north1"
    assert [item.service_name for item in services] == ["platform-pg", "platform-kafka"]
    assert service.service_type == "pg"
    assert [request.url.path for request in requests] == [
        "/v1/project",
        "/v1/project/demo-project/service",
        "/v1/project/demo-project/service/platform-pg",
    ]
    audit_rows = store.read_collection("mcp_audit_log")
    assert [row["action"] for row in audit_rows] == [
        "discover_projects",
        "discover_services",
        "get_service",
    ]
    assert [row["status"] for row in audit_rows] == ["succeeded", "succeeded", "succeeded"]
    assert audit_rows[0]["response_summary"]["project_count"] == 1
    assert audit_rows[1]["response_summary"]["service_count"] == EXPECTED_SERVICE_COUNT
    assert audit_rows[2]["service_name"] == "platform-pg"


async def test_aiven_api_controller_requires_project_for_service_discovery(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    async with httpx.AsyncClient(transport=_ok_transport()) as client:
        controller = AivenApiController(
            api_token="test-token",
            audit_sink=store,
            client=client,
        )

        with pytest.raises(AivenApiError, match="project is required"):
            await controller.discover_services()

    audit_rows = store.read_collection("mcp_audit_log")
    assert audit_rows[0]["action"] == "discover_services"
    assert audit_rows[0]["status"] == "failed"
    assert "project is required" in audit_rows[0]["error"]


async def test_aiven_api_controller_raises_clear_unsupported_operation() -> None:
    async with httpx.AsyncClient(transport=_ok_transport()) as client:
        controller = AivenApiController(api_token="test-token", client=client)

        with pytest.raises(AivenApiUnsupportedOperation, match="direct Kafka AdminClient"):
            await controller.ensure_kafka_topic(
                KafkaTopicSpec(topic_name="ingest.jobs", partitions=1, replication=1)
            )


async def test_aiven_api_controller_can_be_created_from_settings(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        aiven_api_token="test-token",
        aiven_api_base_url="https://api.example.test/v1",
        aiven_api_auth_scheme="aivenv1",
        aiven_project="demo-project",
    )
    async with httpx.AsyncClient(transport=_ok_transport()) as client:
        controller = AivenApiController.from_settings(settings, client=client)

    assert controller.base_url == "https://api.example.test/v1"
    assert controller.auth_scheme == "aivenv1"
    assert controller.default_project == "demo-project"


async def test_aiven_api_controller_persists_audit_actions(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    async with httpx.AsyncClient(transport=_ok_transport()) as client:
        controller = AivenApiController(
            api_token="test-token",
            audit_sink=store,
            client=client,
        )

        await controller.audit_action(
            MCPAuditAction(
                controller="aiven_api",
                action="discover_projects",
                safety_level="safe_read",
                request={},
                status="succeeded",
            )
        )

    rows = store.read_collection("mcp_audit_log")
    assert rows[0]["controller"] == "aiven_api"
    assert rows[0]["action"] == "discover_projects"
    assert rows[0]["metadata"]["safety_level"] == "safe_read"
