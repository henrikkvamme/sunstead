import json
from pathlib import Path
from uuid import uuid4

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.infra.aiven_mcp import NoopAivenMCPController
from supply_intel.infra.bootstrap import cloud_bootstrap_plan
from supply_intel.models.infra import MCPAuditAction
from supply_intel.settings import Settings


async def test_noop_aiven_controller_persists_local_audit_action(tmp_path: Path) -> None:
    store = FileEvidenceStore(tmp_path)
    controller = NoopAivenMCPController(audit_sink=store)
    action = MCPAuditAction(
        controller="noop",
        action="discover_services",
        safety_level="safe_read",
        request={"project": "demo"},
        response_summary={"service_count": 0},
        status="succeeded",
    )

    await controller.audit_action(action)

    assert len(controller.audit_log) == 1
    rows = _read_jsonl(tmp_path / "mcp_audit_log.jsonl")
    assert rows[0]["controller"] == "noop"
    assert rows[0]["action"] == "discover_services"
    assert rows[0]["status"] == "succeeded"
    assert rows[0]["metadata"]["safety_level"] == "safe_read"


def test_cloud_bootstrap_plan_blocks_without_project_or_service_choices(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, platform_env="dev-cloud")

    plan = cloud_bootstrap_plan(settings=settings, mode="hybrid")

    assert plan.ready_to_apply is False
    assert "Set AIVEN_PROJECT or pass --project before cloud discovery." in plan.required_decisions
    assert any("AIVEN_POSTGRES_SERVICE" in decision for decision in plan.required_decisions)
    assert any(action.action == "discover_projects" for action in plan.mcp_actions)
    blocked = [action for action in plan.mcp_actions if action.status == "blocked"]
    assert {action.action for action in blocked} >= {
        "discover_services",
        "verify_postgres_extensions",
        "ensure_kafka_topics",
        "provision_grafana_dashboards",
    }
    assert any(
        fallback.command == "uv run platform init-kafka --apply --backend direct"
        for fallback in plan.fallback_actions
    )


def test_cloud_bootstrap_plan_uses_configured_dev_cloud_services(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        platform_env="dev-cloud",
        aiven_project="demo-project",
        aiven_postgres_service="platform-pg",
        aiven_kafka_service="platform-kafka",
        aiven_grafana_service="platform-grafana",
    )

    plan = cloud_bootstrap_plan(settings=settings, mode="aiven")

    assert plan.required_decisions == []
    assert plan.ready_to_apply is True
    assert plan.project == "demo-project"
    assert plan.topic_count > 0
    assert plan.required_postgres_extensions == ["vector", "pg_trgm", "uuid-ossp"]
    assert {
        (service.service_role, service.target, service.status) for service in plan.services
    } >= {
        ("postgres", "aiven", "configured"),
        ("kafka", "aiven", "configured"),
        ("grafana", "aiven", "configured"),
        ("neo4j", "local", "deferred"),
    }
    migration_actions = [
        action for action in plan.mcp_actions if action.safety_level == "migration_write"
    ]
    assert migration_actions
    assert all(action.status == "planned" for action in migration_actions)
    assert all(action.requires_approval is False for action in migration_actions)


def test_cloud_bootstrap_plan_requires_production_approval(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        platform_env="production",
        aiven_project="prod-project",
        aiven_postgres_service="prod-pg",
        aiven_kafka_service="prod-kafka",
        aiven_grafana_service="prod-grafana",
    )

    plan = cloud_bootstrap_plan(settings=settings, mode="aiven")

    migration_actions = [
        action for action in plan.mcp_actions if action.safety_level == "migration_write"
    ]
    assert plan.ready_to_apply is False
    assert all(action.status == "requires_approval" for action in migration_actions)
    assert all(action.requires_approval is True for action in migration_actions)

    approval_id = uuid4()
    approved = cloud_bootstrap_plan(settings=settings, mode="aiven", approval_id=approval_id)

    approved_migrations = [
        action for action in approved.mcp_actions if action.safety_level == "migration_write"
    ]
    assert approved.ready_to_apply is True
    assert all(action.status == "planned" for action in approved_migrations)
    assert {action.approval_id for action in approved_migrations} == {approval_id}


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
