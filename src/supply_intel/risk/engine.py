from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from pydantic import Field

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
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.extraction import MedicalExtractionOutput
from supply_intel.models.kafka import (
    EventEnvelope,
    EventProcessingResult,
    ExtractionCompletedPayload,
    RiskAlertPayload,
    RiskCandidatePayload,
    RiskCaseCreatedPayload,
    RiskVerdictPayload,
    TraceMetadata,
)
from supply_intel.models.risk import RiskAlert, RiskCandidate, RiskCase, RiskVerdict
from supply_intel.risk.cases import (
    build_recall_quality_case,
    build_shortage_case,
    feature_snapshots_for_case,
)
from supply_intel.settings import Settings

RISK_ENGINE_GROUP = "platform-risk-engine"
RISK_ENGINE_STAGE = "score-risk"
EXTRACTION_COMPLETED_TOPIC = "ingest.extraction_completed"
SUPPORTED_EXTRACTION_SCHEMA = "MedicalExtractionOutput"


class RiskEngineSummary(StrictBaseModel):
    data_dir: str
    extraction_runs_scanned: int
    recall_events_seen: int
    shortage_events_seen: int
    risk_candidates_created: int
    risk_candidates_existing: int
    risk_cases_created: int
    risk_cases_existing: int
    risk_verdicts_created: int
    risk_alerts_created: int
    risk_feature_snapshots_created: int
    events_emitted: int
    kafka_events_published: int = 0
    case_keys: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)


class RiskWorkerRunSummary(StrictBaseModel):
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
class RiskRuntime:
    consumer_client: KafkaConsumerClient
    producer_client: KafkaProducerClient
    direct_consumer: DirectKafkaConsumerClient | None = None
    direct_producer: DirectKafkaProducerClient | None = None

    async def close(self) -> None:
        if self.direct_consumer is not None:
            await self.direct_consumer.stop()
        if self.direct_producer is not None:
            await self.direct_producer.stop()


def run_local_risk_engine(data_dir: Path) -> RiskEngineSummary:
    store = FileEvidenceStore(data_dir)
    extraction_runs = store.read_collection("extraction_runs")
    raw_documents = {
        str(row["id"]): row for row in store.read_collection("raw_documents") if row.get("id")
    }

    summary = _new_summary(data_dir)

    for row in extraction_runs:
        _process_extraction_run_row(
            store=store,
            summary=summary,
            row=row,
            raw_document=raw_documents.get(str(row.get("raw_document_id"))),
        )

    return summary


async def execute_risk_event(
    *,
    settings: Settings,
    event: EventEnvelope,
    producer: EventProducer | None = None,
) -> RiskEngineSummary:
    event = validate_event_payload(event)
    if event.event_type != EXTRACTION_COMPLETED_TOPIC:
        raise PermanentEventError(
            f"Unsupported risk engine event type: {event.event_type}",
            error_type="unsupported_risk_event",
        )

    payload = ExtractionCompletedPayload.model_validate(event.payload)
    summary = _new_summary(settings.data_dir)
    if payload.status != "succeeded" or payload.output_schema != SUPPORTED_EXTRACTION_SCHEMA:
        return summary

    store = FileEvidenceStore(settings.data_dir)
    row = _extraction_run_row_by_id(store, payload.extraction_run_id)
    if row is None:
        raise PermanentEventError(
            f"Extraction run for risk event is missing: {payload.extraction_run_id}",
            error_type="extraction_run_missing",
        )
    if row.get("status") != "succeeded":
        raise PermanentEventError(
            f"Extraction run status does not match succeeded event: {payload.extraction_run_id}",
            error_type="extraction_run_status_mismatch",
        )
    if row.get("output_schema") != SUPPORTED_EXTRACTION_SCHEMA:
        return summary
    if not row.get("validated_output"):
        raise PermanentEventError(
            f"Extraction run has no validated output: {payload.extraction_run_id}",
            error_type="extraction_output_missing",
        )

    raw_document = _raw_document_row_by_id(store, payload.raw_document_id)
    if raw_document is None:
        raise PermanentEventError(
            f"Raw document for risk event is missing: {payload.raw_document_id}",
            error_type="raw_document_missing",
        )
    if str(row.get("raw_document_id")) != str(payload.raw_document_id):
        raise PermanentEventError(
            "Risk event raw document does not match extraction run raw document",
            error_type="risk_event_document_mismatch",
        )

    _process_extraction_run_row(
        store=store,
        summary=summary,
        row=row,
        raw_document=raw_document,
    )
    if producer is not None:
        summary.kafka_events_published = await publish_events_by_ids(
            store=store,
            producer=producer,
            event_ids=summary.event_ids,
        )
    return summary


async def run_risk_engine_once(
    *,
    settings: Settings,
    consumer_client: KafkaConsumerClient | None = None,
    producer_client: KafkaProducerClient | None = None,
) -> EventProcessingResult:
    summary = await run_risk_engine_consumer(
        settings=settings,
        max_messages=1,
        consumer_client=consumer_client,
        producer_client=producer_client,
    )
    if not summary.results:
        raise RuntimeError("Risk engine exited before processing a message.")
    return summary.results[0]


async def run_risk_engine_consumer(
    *,
    settings: Settings,
    max_messages: int | None = None,
    idle_timeout_seconds: float | None = None,
    consumer_client: KafkaConsumerClient | None = None,
    producer_client: KafkaProducerClient | None = None,
) -> RiskWorkerRunSummary:
    if max_messages is not None and max_messages < 1:
        raise ValueError("max_messages must be greater than zero when provided.")

    runtime = await _start_risk_runtime(
        settings=settings,
        consumer_client=consumer_client,
        producer_client=producer_client,
    )
    producer = EventProducer(runtime.producer_client)
    consumer = EventConsumer(
        runtime.consumer_client,
        producer,
        consumer_group=RISK_ENGINE_GROUP,
        stage=RISK_ENGINE_STAGE,
    )

    async def handler(received: EventEnvelope) -> None:
        await execute_risk_event(settings=settings, event=received, producer=producer)

    summary = RiskWorkerRunSummary(requested_messages=max_messages)
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


async def _start_risk_runtime(
    *,
    settings: Settings,
    consumer_client: KafkaConsumerClient | None,
    producer_client: KafkaProducerClient | None,
) -> RiskRuntime:
    direct_consumer: DirectKafkaConsumerClient | None = None
    direct_producer: DirectKafkaProducerClient | None = None
    selected_consumer = consumer_client
    selected_producer = producer_client
    if selected_consumer is None:
        direct_consumer = DirectKafkaConsumerClient(
            settings,
            topics=[EXTRACTION_COMPLETED_TOPIC],
            group_id=RISK_ENGINE_GROUP,
        )
        selected_consumer = direct_consumer
        await direct_consumer.start()
    if selected_producer is None:
        direct_producer = DirectKafkaProducerClient(settings)
        selected_producer = direct_producer
        await direct_producer.start()
    return RiskRuntime(
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


def _new_summary(data_dir: Path) -> RiskEngineSummary:
    return RiskEngineSummary(
        data_dir=str(data_dir),
        extraction_runs_scanned=0,
        recall_events_seen=0,
        shortage_events_seen=0,
        risk_candidates_created=0,
        risk_candidates_existing=0,
        risk_cases_created=0,
        risk_cases_existing=0,
        risk_verdicts_created=0,
        risk_alerts_created=0,
        risk_feature_snapshots_created=0,
        events_emitted=0,
    )


def _process_extraction_run_row(
    *,
    store: FileEvidenceStore,
    summary: RiskEngineSummary,
    row: dict[str, object],
    raw_document: dict[str, object] | None,
) -> None:
    if row.get("status") != "succeeded" or row.get("output_schema") != SUPPORTED_EXTRACTION_SCHEMA:
        return
    if not row.get("validated_output"):
        return

    summary.extraction_runs_scanned += 1
    output = MedicalExtractionOutput.model_validate(row["validated_output"])
    source_run_id = _uuid_or_none(raw_document.get("source_run_id")) if raw_document else None
    raw_document_id = _uuid_or_none(row.get("raw_document_id"))
    source_id = str(raw_document.get("source_id")) if raw_document else None
    for recall in output.recall_events:
        summary.recall_events_seen += 1
        evidence_span_id = recall.evidence[0].evidence_span_id if recall.evidence else None
        candidate, case, verdict, alert = build_recall_quality_case(
            recall,
            evidence_span_id=evidence_span_id,
            affected_relationships=max(1, len(output.relationships)),
        )
        _write_case_outputs(
            store=store,
            summary=summary,
            candidate=candidate,
            case=case,
            verdict=verdict,
            alert=alert,
            source_id=source_id,
            source_run_id=source_run_id,
            raw_document_id=raw_document_id,
        )
    for shortage in output.shortage_events:
        summary.shortage_events_seen += 1
        evidence_span_id = shortage.evidence[0].evidence_span_id if shortage.evidence else None
        candidate, case, verdict, alert = build_shortage_case(
            shortage,
            evidence_span_id=evidence_span_id,
            affected_relationships=max(1, len(output.relationships)),
        )
        _write_case_outputs(
            store=store,
            summary=summary,
            candidate=candidate,
            case=case,
            verdict=verdict,
            alert=alert,
            source_id=source_id,
            source_run_id=source_run_id,
            raw_document_id=raw_document_id,
        )


def _extraction_run_row_by_id(
    store: FileEvidenceStore,
    extraction_run_id: UUID,
) -> dict[str, object] | None:
    for row in store.read_collection("extraction_runs"):
        if row.get("id") == str(extraction_run_id):
            return row
    return None


def _raw_document_row_by_id(
    store: FileEvidenceStore,
    raw_document_id: UUID,
) -> dict[str, object] | None:
    for row in store.read_collection("raw_documents"):
        if row.get("id") == str(raw_document_id):
            return row
    return None


def _write_case_outputs(
    *,
    store: FileEvidenceStore,
    summary: RiskEngineSummary,
    candidate: RiskCandidate,
    case: RiskCase,
    verdict: RiskVerdict,
    alert: RiskAlert,
    source_id: str | None,
    source_run_id: UUID | None,
    raw_document_id: UUID | None,
) -> None:
    candidate_created = store.write_risk_candidate(candidate)
    case_created = store.write_risk_case(case)
    verdict.risk_case_id = case.id
    alert.risk_case_id = case.id
    verdict_created = store.write_risk_verdict(verdict)
    alert_created = store.write_risk_alert(alert)
    for snapshot in feature_snapshots_for_case(case, evidence_span_ids=verdict.evidence_span_ids):
        if store.write_risk_feature_snapshot(snapshot):
            summary.risk_feature_snapshots_created += 1

    if candidate_created:
        summary.risk_candidates_created += 1
    else:
        summary.risk_candidates_existing += 1
    if case_created:
        summary.risk_cases_created += 1
    else:
        summary.risk_cases_existing += 1
    if verdict_created:
        summary.risk_verdicts_created += 1
    if alert_created:
        summary.risk_alerts_created += 1
    summary.case_keys.append(case.case_key)

    _emit_case_events(
        store=store,
        summary=summary,
        candidate=candidate,
        case=case,
        verdict=verdict,
        alert=alert,
        source_id=source_id,
        source_run_id=source_run_id,
        raw_document_id=raw_document_id,
        candidate_created=candidate_created,
        case_created=case_created,
        verdict_created=verdict_created,
        alert_created=alert_created,
    )


def _emit_case_events(
    *,
    store: FileEvidenceStore,
    summary: RiskEngineSummary,
    candidate: RiskCandidate,
    case: RiskCase,
    verdict: RiskVerdict,
    alert: RiskAlert,
    source_id: str | None,
    source_run_id: UUID | None,
    raw_document_id: UUID | None,
    candidate_created: bool,
    case_created: bool,
    verdict_created: bool,
    alert_created: bool,
) -> None:
    if candidate_created:
        event = _risk_candidate_event(
            candidate,
            source_id=source_id,
            source_run_id=source_run_id,
            raw_document_id=raw_document_id,
        )
        _record_risk_event(store=store, summary=summary, event=event)
    if case_created:
        event = _risk_case_event(
            case,
            verdict,
            source_id=source_id,
            source_run_id=source_run_id,
            raw_document_id=raw_document_id,
        )
        _record_risk_event(store=store, summary=summary, event=event)
    if verdict_created:
        event = _risk_verdict_event(
            case,
            verdict,
            source_id=source_id,
            source_run_id=source_run_id,
            raw_document_id=raw_document_id,
        )
        _record_risk_event(store=store, summary=summary, event=event)
    if alert_created:
        event = _risk_alert_event(
            case,
            alert,
            source_id=source_id,
            source_run_id=source_run_id,
            raw_document_id=raw_document_id,
        )
        _record_risk_event(store=store, summary=summary, event=event)


def _record_risk_event(
    *,
    store: FileEvidenceStore,
    summary: RiskEngineSummary,
    event: EventEnvelope,
) -> None:
    if not store.write_event(event):
        return
    summary.events_emitted += 1
    summary.event_ids.append(str(event.event_id))


def _risk_case_event(
    case: RiskCase,
    verdict: RiskVerdict,
    *,
    source_id: str | None,
    source_run_id: UUID | None,
    raw_document_id: UUID | None,
) -> EventEnvelope:
    payload = RiskCaseCreatedPayload(
        risk_case_id=case.id,
        case_key=case.case_key,
        risk_type=case.risk_type,
        severity=case.severity,
        status=case.status,
        risk_score=case.risk_score,
        confidence=case.confidence,
        evidence_span_ids=verdict.evidence_span_ids,
    )
    return build_event(
        event_type="risk.case_created",
        service="risk-engine",
        source_id=source_id,
        payload=payload.model_dump(mode="json"),
        idempotency_key=f"risk.case_created:{case.case_key}",
        trace=TraceMetadata(source_run_id=source_run_id, raw_document_id=raw_document_id),
    )


def _risk_candidate_event(
    candidate: RiskCandidate,
    *,
    source_id: str | None,
    source_run_id: UUID | None,
    raw_document_id: UUID | None,
) -> EventEnvelope:
    payload = RiskCandidatePayload(
        candidate_key=candidate.candidate_key,
        risk_type=candidate.risk_type,
        scope=candidate.scope,
        signals=candidate.signals,
        initial_score=candidate.initial_score,
        confidence=candidate.confidence,
        evidence_span_ids=candidate.evidence_span_ids,
    )
    return build_event(
        event_type="risk.candidates",
        service="risk-engine",
        source_id=source_id,
        payload=payload.model_dump(mode="json"),
        idempotency_key=f"risk.candidates:{candidate.candidate_key}",
        trace=TraceMetadata(source_run_id=source_run_id, raw_document_id=raw_document_id),
    )


def _risk_verdict_event(
    case: RiskCase,
    verdict: RiskVerdict,
    *,
    source_id: str | None,
    source_run_id: UUID | None,
    raw_document_id: UUID | None,
) -> EventEnvelope:
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
        service="verdict-agent",
        source_id=source_id,
        payload=payload.model_dump(mode="json"),
        idempotency_key=f"risk.verdicts:{case.case_key}:{verdict.verdict_type}",
        trace=TraceMetadata(source_run_id=source_run_id, raw_document_id=raw_document_id),
    )


def _risk_alert_event(
    case: RiskCase,
    alert: RiskAlert,
    *,
    source_id: str | None,
    source_run_id: UUID | None,
    raw_document_id: UUID | None,
) -> EventEnvelope:
    payload = RiskAlertPayload(
        alert_key=alert.alert_key,
        risk_case_id=alert.risk_case_id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        status=alert.status,
        title=alert.title,
        channels=alert.channels,
    )
    return build_event(
        event_type="risk.alerts",
        service="alert-worker",
        source_id=source_id,
        payload=payload.model_dump(mode="json"),
        idempotency_key=f"risk.alerts:{case.case_key}:{alert.alert_type}",
        trace=TraceMetadata(source_run_id=source_run_id, raw_document_id=raw_document_id),
    )


def _uuid_or_none(value: object) -> UUID | None:
    if value is None:
        return None
    return value if isinstance(value, UUID) else UUID(str(value))
