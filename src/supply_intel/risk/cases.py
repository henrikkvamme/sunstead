from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from supply_intel.models.events import RecallEvent, ShortageEvent
from supply_intel.models.risk import (
    RiskAlert,
    RiskCandidate,
    RiskCase,
    RiskFeatureSnapshot,
    RiskScope,
    RiskVerdict,
    Severity,
)
from supply_intel.risk.scoring import score_recall_quality_risk, score_shortage_risk

CRITICAL_THRESHOLD = 90
HIGH_THRESHOLD = 75
MEDIUM_THRESHOLD = 55
LOW_THRESHOLD = 40


def build_recall_quality_case(
    recall: RecallEvent,
    *,
    evidence_span_id: UUID | None,
    affected_relationships: int,
) -> tuple[RiskCandidate, RiskCase, RiskVerdict, RiskAlert]:
    evidence_confidence = recall.confidence
    candidate = score_recall_quality_risk(
        classification=recall.classification,
        evidence_confidence=evidence_confidence,
        affected_relationships=affected_relationships,
    )
    evidence_span_ids = [evidence_span_id] if evidence_span_id else []
    candidate.candidate_key = f"risk_candidate:recall_quality:{recall.recall_key}"
    candidate.scope = RiskScope(type="Recall", graph_key=recall.recall_key)
    candidate.evidence_span_ids = evidence_span_ids
    severity = severity_for_score(candidate.initial_score)
    opened_at = datetime.now(UTC)
    case = RiskCase(
        case_key=f"risk:recall_quality:{recall.recall_key}",
        title=f"Recall quality risk: {recall.product_description}",
        risk_type="recall_quality",
        scope_type="Recall",
        graph_node_key=recall.recall_key,
        status="confirmed" if severity in {"critical", "high"} else "watch",
        severity=severity,
        risk_score=candidate.initial_score,
        confidence=candidate.confidence,
        component_scores={
            "recall_classification": candidate.initial_score,
            "evidence_confidence": candidate.confidence,
            "affected_relationships": float(affected_relationships),
        },
        opened_at=opened_at,
    )
    verdict = RiskVerdict(
        risk_case_id=case.id,
        verdict_type="confirmed_risk" if severity in {"critical", "high"} else "watch",
        severity=severity,
        risk_score=case.risk_score,
        confidence=case.confidence,
        summary=(
            "openFDA enforcement evidence indicates a recall/quality signal for "
            f"{recall.product_description}."
        ),
        key_drivers=[
            f"Recall classification: {recall.classification or 'unknown'}",
            f"Recall status: {recall.status or 'unknown'}",
            f"Reason: {recall.reason or 'not provided'}",
        ],
        affected_entities=[{"type": "Recall", "graph_key": recall.recall_key}],
        evidence_span_ids=evidence_span_ids,
        limitations=[
            "Supply-chain intelligence only; not medical advice or clinical guidance.",
            "Recall scope depends on source-provided product identifiers and graph coverage.",
        ],
        recommended_actions=[
            "Review source recall notice and affected product relationships.",
            (
                "Check related manufacturer, facility, and ingredient exposure before "
                "operational action."
            ),
        ],
    )
    case.latest_verdict_id = verdict.id
    alert = RiskAlert(
        alert_key=f"alert:{case.case_key}",
        risk_case_id=case.id,
        alert_type="risk_case_created",
        severity=severity,
        status="open",
        title=case.title,
        body=verdict.summary,
        channels=["dashboard"],
        payload={
            "case_key": case.case_key,
            "recall_key": recall.recall_key,
            "evidence_span_ids": [str(value) for value in evidence_span_ids],
        },
        first_emitted_at=opened_at,
        last_emitted_at=opened_at,
    )
    return candidate, case, verdict, alert


def build_shortage_case(
    shortage: ShortageEvent,
    *,
    evidence_span_id: UUID | None,
    affected_relationships: int,
) -> tuple[RiskCandidate, RiskCase, RiskVerdict, RiskAlert]:
    candidate = score_shortage_risk(
        status=shortage.status,
        reason=shortage.reason,
        evidence_confidence=shortage.confidence,
        affected_relationships=affected_relationships,
    )
    evidence_span_ids = [evidence_span_id] if evidence_span_id else []
    candidate.candidate_key = f"risk_candidate:shortage:{shortage.shortage_key}"
    candidate.scope = RiskScope(type="Shortage", graph_key=shortage.shortage_key)
    candidate.evidence_span_ids = evidence_span_ids
    severity = severity_for_score(candidate.initial_score)
    opened_at = datetime.now(UTC)
    case = RiskCase(
        case_key=f"risk:shortage:{shortage.shortage_key}",
        title=f"Shortage risk: {shortage.product_name}",
        risk_type="shortage",
        scope_type="Shortage",
        graph_node_key=shortage.shortage_key,
        status="confirmed" if severity in {"critical", "high"} else "watch",
        severity=severity,
        risk_score=candidate.initial_score,
        confidence=candidate.confidence,
        component_scores={
            "shortage_status": candidate.initial_score,
            "evidence_confidence": candidate.confidence,
            "affected_relationships": float(affected_relationships),
        },
        opened_at=opened_at,
    )
    verdict = RiskVerdict(
        risk_case_id=case.id,
        verdict_type="confirmed_risk" if severity in {"critical", "high"} else "watch",
        severity=severity,
        risk_score=case.risk_score,
        confidence=case.confidence,
        summary=(
            "FDA shortage evidence indicates an active supply-chain signal for "
            f"{shortage.product_name}."
        ),
        key_drivers=[
            f"Shortage status: {shortage.status}",
            f"Reason: {shortage.reason or 'not provided'}",
        ],
        affected_entities=[{"type": "Shortage", "graph_key": shortage.shortage_key}],
        evidence_span_ids=evidence_span_ids,
        limitations=[
            "Supply-chain intelligence only; not medical advice or clinical guidance.",
            (
                "Shortage impact depends on source updates, presentation-level details, "
                "and graph coverage."
            ),
        ],
        recommended_actions=[
            "Review the FDA shortage source record and presentation-level availability.",
            (
                "Check linked manufacturers, active ingredients, and substitute supply paths "
                "before action."
            ),
        ],
    )
    case.latest_verdict_id = verdict.id
    alert = RiskAlert(
        alert_key=f"alert:{case.case_key}",
        risk_case_id=case.id,
        alert_type="risk_case_created",
        severity=severity,
        status="open",
        title=case.title,
        body=verdict.summary,
        channels=["dashboard"],
        payload={
            "case_key": case.case_key,
            "shortage_key": shortage.shortage_key,
            "evidence_span_ids": [str(value) for value in evidence_span_ids],
        },
        first_emitted_at=opened_at,
        last_emitted_at=opened_at,
    )
    return candidate, case, verdict, alert


def severity_for_score(score: float) -> Severity:
    if score >= CRITICAL_THRESHOLD:
        return "critical"
    if score >= HIGH_THRESHOLD:
        return "high"
    if score >= MEDIUM_THRESHOLD:
        return "medium"
    if score >= LOW_THRESHOLD:
        return "low"
    return "info"


def feature_snapshots_for_case(
    case: RiskCase,
    *,
    evidence_span_ids: list[UUID],
) -> list[RiskFeatureSnapshot]:
    return [
        RiskFeatureSnapshot(
            risk_case_id=case.id,
            case_key=case.case_key,
            scope_type=case.scope_type,
            scope_entity_id=case.scope_entity_id,
            graph_node_key=case.graph_node_key,
            feature_name=feature_name,
            value=value,
            evidence_span_ids=evidence_span_ids,
            computed_at=case.updated_at,
        )
        for feature_name, value in sorted(case.component_scores.items())
    ]
