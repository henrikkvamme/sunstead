from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.models.base import StrictBaseModel


class RiskCaseExplanation(StrictBaseModel):
    case_key: str
    found: bool
    risk_case: dict[str, Any] | None = None
    latest_verdict: dict[str, Any] | None = None
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    score_formula: str
    component_values: dict[str, Any] = Field(default_factory=dict)
    confidence: dict[str, Any] = Field(default_factory=dict)
    evidence_spans: list[dict[str, Any]] = Field(default_factory=list)
    source_documents: list[dict[str, Any]] = Field(default_factory=list)
    graph_paths: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    unresolved_conflicts: list[str] = Field(default_factory=list)


def explain_case_from_store(data_dir: Path, case_key: str) -> RiskCaseExplanation:
    store = FileEvidenceStore(data_dir)
    cases = store.read_collection("risk_cases")
    case = next((row for row in cases if row.get("case_key") == case_key), None)
    if case is None:
        return RiskCaseExplanation(
            case_key=case_key,
            found=False,
            score_formula="case not found",
            unresolved_conflicts=["No stored risk case matched the requested case_key."],
        )

    verdicts = [
        row
        for row in store.read_collection("risk_verdicts")
        if row.get("risk_case_id") == case.get("id")
    ]
    latest_verdict = _latest_by_created_at(verdicts)
    alerts = [
        row
        for row in store.read_collection("risk_alerts")
        if row.get("risk_case_id") == case.get("id")
    ]
    evidence_ids = set(_evidence_ids_from_case(case, latest_verdict))
    evidence_spans = [
        row for row in store.read_collection("evidence_spans") if str(row.get("id")) in evidence_ids
    ]
    raw_document_ids = {str(row.get("raw_document_id")) for row in evidence_spans}
    source_documents = [
        _summarize_raw_document(row)
        for row in store.read_collection("raw_documents")
        if str(row.get("id")) in raw_document_ids
    ]
    graph_paths = [
        row
        for row in store.read_collection("graph_relationship_upserts")
        if _relationship_matches_evidence(row, evidence_ids, raw_document_ids)
    ]

    limitations = list(latest_verdict.get("limitations", [])) if latest_verdict else []
    return RiskCaseExplanation(
        case_key=case_key,
        found=True,
        risk_case=case,
        latest_verdict=latest_verdict,
        alerts=alerts,
        score_formula=(
            "risk_score = transparent component scores adjusted by evidence confidence "
            "and graph amplification; see component_values."
        ),
        component_values=dict(case.get("component_scores", {})),
        confidence={
            "risk_case_confidence": case.get("confidence"),
            "verdict_confidence": latest_verdict.get("confidence") if latest_verdict else None,
            "evidence_span_confidences": [
                row.get("confidence") for row in evidence_spans if row.get("confidence") is not None
            ],
        },
        evidence_spans=evidence_spans,
        source_documents=source_documents,
        graph_paths=graph_paths,
        limitations=limitations,
        unresolved_conflicts=[],
    )


def _latest_by_created_at(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return sorted(rows, key=lambda row: str(row.get("created_at", "")))[-1]


def _evidence_ids_from_case(
    case: dict[str, Any],
    verdict: dict[str, Any] | None,
) -> list[str]:
    values: list[str] = []
    if verdict is not None:
        values.extend(str(value) for value in verdict.get("evidence_span_ids", []))
    for value in case.get("metadata", {}).get("evidence_span_ids", []):
        values.append(str(value))
    return values


def _summarize_raw_document(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "source_id": row.get("source_id"),
        "source_url": row.get("source_url"),
        "canonical_url": row.get("canonical_url"),
        "content_hash": row.get("content_hash"),
        "dedupe_key": row.get("dedupe_key"),
        "fetched_at": row.get("fetched_at"),
    }


def _relationship_matches_evidence(
    row: dict[str, Any],
    evidence_ids: set[str],
    raw_document_ids: set[str],
) -> bool:
    properties = row.get("properties", {})
    if not isinstance(properties, dict):
        return False
    evidence_span_id = properties.get("evidence_span_id")
    source_document_id = properties.get("source_document_id")
    return str(evidence_span_id) in evidence_ids or str(source_document_id) in raw_document_ids
