from supply_intel.models.risk import RiskCandidate, RiskScope


def score_recall_quality_risk(
    *,
    classification: str | None,
    evidence_confidence: float,
    affected_relationships: int = 1,
) -> RiskCandidate:
    class_score = {"Class I": 90.0, "Class II": 70.0, "Class III": 45.0}.get(
        classification or "",
        55.0,
    )
    graph_amplification = min(15.0, affected_relationships * 2.5)
    score = min(100.0, class_score * evidence_confidence + graph_amplification)
    return RiskCandidate(
        candidate_key=f"recall_quality:{classification or 'unknown'}:{affected_relationships}",
        risk_type="recall_quality",
        scope=RiskScope(type="Drug"),
        initial_score=score,
        confidence=evidence_confidence,
        signals=[
            {
                "classification": classification,
                "affected_relationships": affected_relationships,
            }
        ],
    )


def score_shortage_risk(
    *,
    status: str | None,
    reason: str | None,
    evidence_confidence: float,
    affected_relationships: int = 1,
) -> RiskCandidate:
    normalized_status = (status or "").casefold()
    if "currently" in normalized_status or "shortage" in normalized_status:
        status_score = 78.0
    elif "resolved" in normalized_status:
        status_score = 35.0
    else:
        status_score = 55.0
    reason_multiplier = 1.10 if reason else 1.0
    graph_amplification = min(12.0, affected_relationships * 2.0)
    score = min(100.0, status_score * reason_multiplier * evidence_confidence + graph_amplification)
    return RiskCandidate(
        candidate_key=f"shortage:{status or 'unknown'}:{affected_relationships}",
        risk_type="shortage",
        scope=RiskScope(type="Drug"),
        initial_score=score,
        confidence=evidence_confidence,
        signals=[
            {
                "status": status,
                "reason": reason,
                "affected_relationships": affected_relationships,
            }
        ],
    )
