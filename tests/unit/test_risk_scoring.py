from supply_intel.risk.scoring import score_recall_quality_risk

MAX_SCORE = 100
EVIDENCE_CONFIDENCE = 0.75


def test_recall_quality_score_is_confidence_adjusted() -> None:
    candidate = score_recall_quality_risk(
        classification="Class I",
        evidence_confidence=EVIDENCE_CONFIDENCE,
        affected_relationships=4,
    )

    assert candidate.risk_type == "recall_quality"
    assert 0 < candidate.initial_score <= MAX_SCORE
    assert candidate.confidence == EVIDENCE_CONFIDENCE
