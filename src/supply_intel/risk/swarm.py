from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

from pydantic import Field

from supply_intel.agents.factory import DETERMINISTIC_MODEL_NAME
from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.events.consumer import (
    EventConsumer,
    EventHandler,
    KafkaConsumerClient,
    PermanentEventError,
)
from supply_intel.events.envelope import build_event
from supply_intel.events.kafka_clients import DirectKafkaConsumerClient, DirectKafkaProducerClient
from supply_intel.events.outbox import publish_events_by_ids
from supply_intel.events.producer import EventProducer, KafkaProducerClient
from supply_intel.events.schemas import validate_event_payload
from supply_intel.models.agents import (
    AffectedGraphNode,
    AgentFinding,
    BlastRadiusOutput,
    CriticIssue,
    CriticOutput,
    EvidenceVerificationOutput,
    RiskPath,
)
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.kafka import (
    AgentAuditLogPayload,
    AgentFindingPayload,
    EventEnvelope,
    EventProcessingResult,
    RiskCaseCreatedPayload,
    RiskVerdictPayload,
)
from supply_intel.models.risk import RiskVerdict, Severity
from supply_intel.risk.explain import RiskCaseExplanation, explain_case_from_store
from supply_intel.settings import Settings

AGENT_VERSION = "0.1.0"
AGENT_SWARM_GROUP = "platform-agent-swarm"
AGENT_SWARM_STAGE = "investigate-risk"
RISK_CASE_CREATED_TOPIC = "risk.case_created"


class SwarmRunSummary(StrictBaseModel):
    case_key: str
    risk_case_id: UUID | None = None
    status: str
    findings_created: int
    verdicts_created: int = 0
    kafka_events_published: int = 0
    event_ids: list[str] = Field(default_factory=list)
    agent_names: list[str] = Field(default_factory=list)


class SwarmWorkerRunSummary(StrictBaseModel):
    requested_messages: int | None = None
    processed_messages: int = Field(default=0, ge=0)
    deadlettered_messages: int = Field(default=0, ge=0)
    committed_messages: int = Field(default=0, ge=0)
    timed_out: bool = False
    results: list[EventProcessingResult] = Field(default_factory=list)

    @property
    def handled_messages(self) -> int:
        return self.processed_messages + self.deadlettered_messages


@dataclass
class SwarmRuntime:
    consumer_client: KafkaConsumerClient
    producer_client: KafkaProducerClient
    direct_consumer: DirectKafkaConsumerClient | None = None
    direct_producer: DirectKafkaProducerClient | None = None

    async def close(self) -> None:
        if self.direct_consumer is not None:
            await self.direct_consumer.stop()
        if self.direct_producer is not None:
            await self.direct_producer.stop()


def run_local_agent_swarm(data_dir: Path, case_key: str) -> SwarmRunSummary:
    explanation = explain_case_from_store(data_dir, case_key)
    if not explanation.found or explanation.risk_case is None:
        return SwarmRunSummary(
            case_key=case_key,
            status="case_not_found",
            findings_created=0,
        )

    store = FileEvidenceStore(data_dir)
    risk_case_id = UUID(str(explanation.risk_case["id"]))
    findings = [
        _evidence_verifier_finding(risk_case_id, explanation),
        _graph_blast_radius_finding(risk_case_id, explanation),
    ]
    findings.append(_critic_finding(risk_case_id, explanation, findings))

    event_ids: list[str] = []
    created_findings: list[AgentFinding] = []
    for finding in findings:
        if store.write_agent_finding(finding):
            created_findings.append(finding)
        event = _finding_event(case_key, finding)
        if store.write_event(event):
            event_ids.append(str(event.event_id))

    verdict = _verdict_agent_verdict(risk_case_id, explanation, findings)
    verdict_created = store.write_risk_verdict(verdict)
    if verdict_created:
        verdict_event = _verdict_event(case_key, verdict)
        if store.write_event(verdict_event):
            event_ids.append(str(verdict_event.event_id))

    agent_names = [finding.agent_name for finding in findings] + ["VerdictAgent"]
    audit_event = _audit_event(
        case_key,
        risk_case_id,
        agent_names=agent_names,
        finding_ids=[finding.id for finding in findings],
    )
    if store.write_event(audit_event):
        event_ids.append(str(audit_event.event_id))

    return SwarmRunSummary(
        case_key=case_key,
        risk_case_id=risk_case_id,
        status="completed",
        findings_created=len(created_findings),
        verdicts_created=1 if verdict_created else 0,
        event_ids=event_ids,
        agent_names=agent_names,
    )


async def execute_agent_swarm_event(
    *,
    settings: Settings,
    event: EventEnvelope,
    producer: EventProducer | None = None,
) -> SwarmRunSummary:
    event = validate_event_payload(event)
    if event.event_type != RISK_CASE_CREATED_TOPIC:
        raise PermanentEventError(
            f"Unsupported agent swarm event type: {event.event_type}",
            error_type="unsupported_agent_swarm_event",
        )
    payload = RiskCaseCreatedPayload.model_validate(event.payload)
    summary = run_local_agent_swarm(settings.data_dir, payload.case_key)
    if summary.status == "case_not_found":
        raise PermanentEventError(
            f"Risk case for swarm event is missing: {payload.case_key}",
            error_type="risk_case_missing",
        )
    if producer is not None:
        summary.kafka_events_published = await publish_events_by_ids(
            store=FileEvidenceStore(settings.data_dir),
            producer=producer,
            event_ids=summary.event_ids,
        )
    return summary


async def run_agent_swarm_once(
    *,
    settings: Settings,
    consumer_client: KafkaConsumerClient | None = None,
    producer_client: KafkaProducerClient | None = None,
) -> EventProcessingResult:
    summary = await run_agent_swarm_consumer(
        settings=settings,
        max_messages=1,
        consumer_client=consumer_client,
        producer_client=producer_client,
    )
    if not summary.results:
        raise RuntimeError("Agent swarm exited before processing a message.")
    return summary.results[0]


async def run_agent_swarm_consumer(
    *,
    settings: Settings,
    max_messages: int | None = None,
    idle_timeout_seconds: float | None = None,
    consumer_client: KafkaConsumerClient | None = None,
    producer_client: KafkaProducerClient | None = None,
) -> SwarmWorkerRunSummary:
    if max_messages is not None and max_messages < 1:
        raise ValueError("max_messages must be greater than zero when provided.")

    runtime = await _start_swarm_runtime(
        settings=settings,
        consumer_client=consumer_client,
        producer_client=producer_client,
    )
    producer = EventProducer(runtime.producer_client)
    consumer = EventConsumer(
        runtime.consumer_client,
        producer,
        consumer_group=AGENT_SWARM_GROUP,
        stage=AGENT_SWARM_STAGE,
    )

    async def handler(received: EventEnvelope) -> None:
        await execute_agent_swarm_event(settings=settings, event=received, producer=producer)

    summary = SwarmWorkerRunSummary(requested_messages=max_messages)
    try:
        while max_messages is None or summary.handled_messages < max_messages:
            try:
                result = await _process_one_with_optional_timeout(
                    consumer,
                    handler,
                    idle_timeout_seconds=idle_timeout_seconds,
                )
            except TimeoutError:
                summary.timed_out = True
                break
            summary.results.append(result)
            if result.status == "processed":
                summary.processed_messages += 1
            if result.status == "deadlettered":
                summary.deadlettered_messages += 1
            if result.committed:
                summary.committed_messages += 1
        return summary
    finally:
        await runtime.close()


async def _start_swarm_runtime(
    *,
    settings: Settings,
    consumer_client: KafkaConsumerClient | None,
    producer_client: KafkaProducerClient | None,
) -> SwarmRuntime:
    direct_consumer: DirectKafkaConsumerClient | None = None
    direct_producer: DirectKafkaProducerClient | None = None
    selected_consumer = consumer_client
    selected_producer = producer_client
    if selected_consumer is None:
        direct_consumer = DirectKafkaConsumerClient(
            settings,
            topics=[RISK_CASE_CREATED_TOPIC],
            group_id=AGENT_SWARM_GROUP,
        )
        selected_consumer = direct_consumer
        await direct_consumer.start()
    if selected_producer is None:
        direct_producer = DirectKafkaProducerClient(settings)
        selected_producer = direct_producer
        await direct_producer.start()
    return SwarmRuntime(
        consumer_client=selected_consumer,
        producer_client=selected_producer,
        direct_consumer=direct_consumer,
        direct_producer=direct_producer,
    )


async def _process_one_with_optional_timeout(
    consumer: EventConsumer,
    handler: EventHandler,
    *,
    idle_timeout_seconds: float | None,
) -> EventProcessingResult:
    if idle_timeout_seconds is None:
        return await consumer.process_one(handler)
    return await asyncio.wait_for(consumer.process_one(handler), timeout=idle_timeout_seconds)


def _evidence_verifier_finding(
    risk_case_id: UUID,
    explanation: RiskCaseExplanation,
) -> AgentFinding:
    evidence_ids = _evidence_ids(explanation)
    missing = [] if evidence_ids else ["No evidence spans were available for the latest verdict."]
    status = "supported" if evidence_ids else "unsupported"
    confidence = _average_evidence_confidence(explanation) if evidence_ids else 0.0
    output = EvidenceVerificationOutput(
        claim_id=explanation.case_key,
        status=status,
        supported_spans=evidence_ids,
        missing_evidence=missing,
        contradictions=[],
        confidence=confidence,
    )
    return AgentFinding(
        risk_case_id=risk_case_id,
        agent_name="EvidenceVerifierAgent",
        agent_version=AGENT_VERSION,
        model_name=DETERMINISTIC_MODEL_NAME,
        prompt_hash=_deterministic_prompt_hash("EvidenceVerifierAgent", "evidence_verification"),
        input_hash=_agent_input_hash(
            explanation,
            agent_name="EvidenceVerifierAgent",
            finding_type="evidence_verification",
        ),
        output_schema="EvidenceVerificationOutput",
        output_schema_version=output.schema_version,
        finding_type="evidence_verification",
        finding=output.model_dump(mode="json"),
        evidence_span_ids=evidence_ids,
        confidence=output.confidence,
        status="created",
    )


def _graph_blast_radius_finding(
    risk_case_id: UUID,
    explanation: RiskCaseExplanation,
) -> AgentFinding:
    paths = [_risk_path(row) for row in explanation.graph_paths]
    affected_nodes = [
        AffectedGraphNode(
            graph_key=path.to_key,
            relationship_type=path.relationship_type,
            distance=1,
            confidence=path.confidence,
        )
        for path in paths
    ]
    root_graph_key = str(
        explanation.risk_case.get("graph_node_key") if explanation.risk_case else ""
    )
    output = BlastRadiusOutput(
        root_graph_key=root_graph_key,
        affected_nodes=affected_nodes,
        paths=paths,
        path_query_name="local_risk_case_context",
        max_depth=1,
        confidence=_average([path.confidence for path in paths], default=0.0),
    )
    return AgentFinding(
        risk_case_id=risk_case_id,
        agent_name="GraphBlastRadiusAgent",
        agent_version=AGENT_VERSION,
        model_name=DETERMINISTIC_MODEL_NAME,
        prompt_hash=_deterministic_prompt_hash("GraphBlastRadiusAgent", "graph_blast_radius"),
        input_hash=_agent_input_hash(
            explanation,
            agent_name="GraphBlastRadiusAgent",
            finding_type="graph_blast_radius",
        ),
        output_schema="BlastRadiusOutput",
        output_schema_version=output.schema_version,
        finding_type="graph_blast_radius",
        finding=output.model_dump(mode="json"),
        evidence_span_ids=[path.evidence_span_id for path in paths if path.evidence_span_id],
        confidence=output.confidence,
        status="created",
    )


def _critic_finding(
    risk_case_id: UUID,
    explanation: RiskCaseExplanation,
    prior_findings: list[AgentFinding],
) -> AgentFinding:
    evidence_finding = prior_findings[0]
    issues: list[CriticIssue] = []
    required_changes: list[str] = []
    decision = "approve"
    if evidence_finding.confidence <= 0:
        decision = "reject"
        issues.append(
            CriticIssue(
                issue_type="missing_evidence",
                detail="The risk verdict has no linked evidence spans.",
                severity="high",
            )
        )
        required_changes.append("Attach source evidence before using this verdict.")
    if not explanation.limitations:
        decision = "revise" if decision == "approve" else decision
        issues.append(
            CriticIssue(
                issue_type="missing_limitations",
                detail="The verdict should state operational and non-medical limitations.",
                severity="medium",
            )
        )
        required_changes.append("Add explicit limitations to the verdict.")
    output = CriticOutput(
        target_id=risk_case_id,
        target_type="risk_case",
        decision=decision,
        issues=issues,
        required_changes=required_changes,
        confidence=0.9 if decision == "approve" else 0.7,
    )
    return AgentFinding(
        risk_case_id=risk_case_id,
        agent_name="CriticAgent",
        agent_version=AGENT_VERSION,
        model_name=DETERMINISTIC_MODEL_NAME,
        prompt_hash=_deterministic_prompt_hash("CriticAgent", "critic_review"),
        input_hash=_agent_input_hash(
            explanation,
            agent_name="CriticAgent",
            finding_type="critic_review",
        ),
        output_schema="CriticOutput",
        output_schema_version=output.schema_version,
        finding_type="critic_review",
        finding=output.model_dump(mode="json"),
        evidence_span_ids=_evidence_ids(explanation),
        confidence=output.confidence,
        critic_status=decision,
        status="created",
    )


def _finding_event(case_key: str, finding: AgentFinding) -> EventEnvelope:
    payload = AgentFindingPayload(
        risk_case_id=finding.risk_case_id,
        agent_name=finding.agent_name,
        model_name=finding.model_name,
        prompt_hash=finding.prompt_hash,
        input_hash=finding.input_hash,
        output_schema=finding.output_schema,
        output_schema_version=finding.output_schema_version,
        finding_type=finding.finding_type,
        finding_id=finding.id,
        evidence_span_ids=finding.evidence_span_ids,
        confidence=finding.confidence,
        status=finding.status,
    )
    return build_event(
        event_type="risk.agent_findings",
        service=finding.agent_name,
        payload=payload.model_dump(mode="json"),
        idempotency_key=f"risk.agent_findings:{case_key}:{finding.agent_name}:{finding.finding_type}",
        correlation_id=finding.correlation_id,
    )


def _verdict_agent_verdict(
    risk_case_id: UUID,
    explanation: RiskCaseExplanation,
    findings: list[AgentFinding],
) -> RiskVerdict:
    risk_case = explanation.risk_case or {}
    latest = explanation.latest_verdict or {}
    critic = findings[-1]
    critic_decision = str(critic.finding.get("decision", "approve"))
    evidence_ids = _evidence_ids(explanation)
    severity = _severity(str(risk_case.get("severity", "info")))
    verdict_type = _verdict_type(critic_decision, severity)
    confidence_values = [finding.confidence for finding in findings]
    confidence_values.append(float(risk_case.get("confidence", 0.0) or 0.0))
    confidence = min(1.0, _average(confidence_values, default=0.0))
    affected_entities = latest.get("affected_entities", [])
    if not isinstance(affected_entities, list):
        affected_entities = []
    key_drivers = [
        f"Evidence verification: {findings[0].finding.get('status', 'unknown')}",
        f"Graph blast radius paths: {len(explanation.graph_paths)}",
        f"Critic decision: {critic_decision}",
    ]
    limitations = list(explanation.limitations)
    if not limitations:
        limitations = [
            "Supply-chain intelligence only; not medical advice or clinical guidance.",
            "Agent verdict depends on currently stored source evidence and graph coverage.",
        ]
    return RiskVerdict(
        risk_case_id=risk_case_id,
        verdict_type=verdict_type,
        severity=severity if verdict_type != "dismissed" else "info",
        risk_score=float(risk_case.get("risk_score", 0.0) or 0.0)
        if verdict_type != "dismissed"
        else 0.0,
        confidence=confidence,
        summary=(
            "VerdictAgent synthesized source evidence, graph blast radius, and critic feedback "
            f"for {risk_case.get('title', explanation.case_key)}."
        ),
        key_drivers=key_drivers,
        affected_entities=affected_entities,
        evidence_span_ids=evidence_ids,
        limitations=limitations,
        recommended_actions=[
            "Review the linked source evidence before operational decisions.",
            "Use graph context to assess affected products, facilities, and suppliers.",
        ],
        metadata={
            "verdict_key": f"verdict-agent:{explanation.case_key}",
            "agent_name": "VerdictAgent",
            "critic_decision": critic_decision,
        },
    )


def _verdict_event(case_key: str, verdict: RiskVerdict) -> EventEnvelope:
    payload = RiskVerdictPayload(
        risk_case_id=verdict.risk_case_id,
        verdict_type=verdict.verdict_type,
        severity=verdict.severity,
        risk_score=verdict.risk_score,
        confidence=verdict.confidence,
        summary=verdict.summary,
        evidence_span_ids=verdict.evidence_span_ids,
        recommended_actions=verdict.recommended_actions,
    )
    return build_event(
        event_type="risk.verdicts",
        service="VerdictAgent",
        payload=payload.model_dump(mode="json"),
        idempotency_key=f"risk.verdicts:{case_key}:VerdictAgent",
    )


def _audit_event(
    case_key: str,
    risk_case_id: UUID,
    *,
    agent_names: list[str],
    finding_ids: list[UUID],
) -> EventEnvelope:
    payload = AgentAuditLogPayload(
        risk_case_id=risk_case_id,
        case_key=case_key,
        action="local_agent_swarm_completed",
        agent_names=agent_names,
        finding_ids=finding_ids,
        status="completed",
    )
    return build_event(
        event_type="agents.audit_log",
        service="agent-swarm",
        payload=payload.model_dump(mode="json"),
        idempotency_key=f"agents.audit_log:{case_key}:local_agent_swarm_completed",
    )


def _verdict_type(
    critic_decision: str,
    severity: Severity,
) -> Literal["confirmed_risk", "possible_risk", "watch", "dismissed", "resolved"]:
    if critic_decision == "reject":
        return "dismissed"
    if critic_decision in {"revise", "needs_human_review"}:
        return "watch"
    if severity in {"critical", "high"}:
        return "confirmed_risk"
    return "possible_risk"


def _severity(value: str) -> Severity:
    if value in {"critical", "high", "medium", "low", "info"}:
        return cast(Severity, value)
    return "info"


def _risk_path(row: dict[str, object]) -> RiskPath:
    properties = row.get("properties", {})
    if not isinstance(properties, dict):
        properties = {}
    evidence_span_id = properties.get("evidence_span_id")
    return RiskPath(
        from_key=str(row.get("from_key", "")),
        to_key=str(row.get("to_key", "")),
        relationship_type=str(row.get("relationship_type", "")),
        evidence_span_id=UUID(str(evidence_span_id)) if evidence_span_id else None,
        confidence=float(properties.get("confidence", 0.0)),
    )


def _evidence_ids(explanation: RiskCaseExplanation) -> list[UUID]:
    return [UUID(str(row["id"])) for row in explanation.evidence_spans if row.get("id")]


def _average_evidence_confidence(explanation: RiskCaseExplanation) -> float:
    values = [
        float(row["confidence"])
        for row in explanation.evidence_spans
        if row.get("confidence") is not None
    ]
    return _average(values, default=0.0)


def _average(values: list[float], *, default: float) -> float:
    return sum(values) / len(values) if values else default


def _deterministic_prompt_hash(agent_name: str, finding_type: str) -> str:
    return _stable_hash(
        {
            "agent_name": agent_name,
            "agent_version": AGENT_VERSION,
            "finding_type": finding_type,
            "runtime": DETERMINISTIC_MODEL_NAME,
        }
    )


def _agent_input_hash(
    explanation: RiskCaseExplanation,
    *,
    agent_name: str,
    finding_type: str,
) -> str:
    risk_case = explanation.risk_case or {}
    return _stable_hash(
        {
            "agent_name": agent_name,
            "finding_type": finding_type,
            "case_key": explanation.case_key,
            "risk_case_id": str(risk_case.get("id", "")),
            "latest_verdict_id": str((explanation.latest_verdict or {}).get("id", "")),
            "evidence_span_ids": [str(value) for value in _evidence_ids(explanation)],
            "graph_path_count": len(explanation.graph_paths),
        }
    )


def _stable_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
