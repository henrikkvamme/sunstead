from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from supply_intel.models.kafka import (
    AgentAuditLogPayload,
    AgentFindingPayload,
    DashboardGraphChatAnsweredPayload,
    DeadLetterPayload,
    DocumentParsedPayload,
    EventEnvelope,
    ExtractionCompletedPayload,
    GraphNodeUpsertPayload,
    GraphRelationshipUpsertPayload,
    IngestJobPayload,
    OpsMetricPayload,
    RawDocumentCreatedPayload,
    RiskAlertPayload,
    RiskCandidatePayload,
    RiskCaseCreatedPayload,
    RiskVerdictPayload,
)

EVENT_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "agents.audit_log": AgentAuditLogPayload,
    "dashboard.graph_chat_answered": DashboardGraphChatAnsweredPayload,
    "graph.node_upsert": GraphNodeUpsertPayload,
    "graph.relationship_upsert": GraphRelationshipUpsertPayload,
    "ingest.document_parsed": DocumentParsedPayload,
    "ingest.extraction_completed": ExtractionCompletedPayload,
    "ingest.jobs": IngestJobPayload,
    "ingest.raw_document_created": RawDocumentCreatedPayload,
    "ops.deadletter": DeadLetterPayload,
    "ops.metrics": OpsMetricPayload,
    "risk.agent_findings": AgentFindingPayload,
    "risk.alerts": RiskAlertPayload,
    "risk.candidates": RiskCandidatePayload,
    "risk.case_created": RiskCaseCreatedPayload,
    "risk.verdicts": RiskVerdictPayload,
}


def validate_event_payload(event: EventEnvelope) -> EventEnvelope:
    payload_model = EVENT_PAYLOAD_MODELS.get(event.event_type)
    if payload_model is None:
        raise ValueError(f"No payload schema registered for event type: {event.event_type}")
    payload = payload_model.model_validate(event.payload)
    return EventEnvelope.model_validate(
        {
            **event.model_dump(mode="json"),
            "payload": payload.model_dump(mode="json"),
        }
    )


def export_event_schema_bundle() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "envelope": EventEnvelope.model_json_schema(),
        "payloads": {
            event_type: model.model_json_schema()
            for event_type, model in sorted(EVENT_PAYLOAD_MODELS.items())
        },
    }
