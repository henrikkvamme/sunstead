from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from pydantic import Field

from supply_intel.agents.factory import ModelFactory
from supply_intel.agents.medical_extraction import MedicalExtractionAgent, extraction_input_hash
from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.events.consumer import (
    EventConsumer,
    EventHandler,
    KafkaConsumerClient,
    PermanentEventError,
)
from supply_intel.events.kafka_clients import DirectKafkaConsumerClient, DirectKafkaProducerClient
from supply_intel.events.outbox import publish_events_by_ids
from supply_intel.events.producer import EventProducer, KafkaProducerClient
from supply_intel.events.schemas import validate_event_payload
from supply_intel.models.base import EvidenceRef, StrictBaseModel
from supply_intel.models.documents import DocumentChunk, EvidenceSpan
from supply_intel.models.events import (
    DisasterEvent,
    LogisticsPressureObservation,
    NewsEvent,
    PriceObservation,
    RecallEvent,
    RegulatoryEvent,
    ShortageEvent,
    StrikeEvent,
    TradeFlowObservation,
    TrendSignalObservation,
)
from supply_intel.models.extraction import ExtractionRun, MedicalExtractionOutput
from supply_intel.models.kafka import DocumentParsedPayload, EventEnvelope, EventProcessingResult
from supply_intel.models.medical import ExtractedRelationship, MedicalEntity
from supply_intel.models.source import IngestionError, RawDocument, SourceConfig, SourceRun
from supply_intel.pipeline import emit_extraction_completed_event, evidence_span_from_chunk
from supply_intel.settings import Settings
from supply_intel.sources.registry import find_source_config, load_source_config

PROMPT_HASH_BY_PROFILE = {
    "openfda.drug_ndc.v1": "deterministic_openfda_ndc_v1",
    "openfda.drug_enforcement.v1": "deterministic_openfda_drug_enforcement_v1",
    "openfda.device_registrationlisting.v1": (
        "deterministic_openfda_device_registrationlisting_v1"
    ),
    "openfda.device_enforcement.v1": "deterministic_openfda_device_enforcement_v1",
    "fda.drug_shortages_html.v1": "deterministic_fda_drug_shortages_html_v1",
    "fda.warning_letters_xlsx.v1": "deterministic_fda_warning_letters_xlsx_v1",
    "fda.inspections_dashboard.v1": "deterministic_fda_inspections_dashboard_v1",
    "gdelt.doc_search.v1": "deterministic_gdelt_doc_search_v1",
    "gdacs.events_rss.v1": "deterministic_gdacs_events_rss_v1",
    "reliefweb.reports.v1": "deterministic_reliefweb_reports_v1",
    "worldbank.commodity_prices_monthly.v1": (
        "deterministic_worldbank_commodity_prices_monthly_v1"
    ),
    "eia.energy_prices.v1": "deterministic_eia_energy_prices_v1",
    "sec.edgar_supplier_filings.v1": "deterministic_sec_edgar_supplier_filings_v1",
    "uncomtrade.trade_flows.v1": "deterministic_uncomtrade_trade_flows_v1",
    "nyfed.gscpi.v1": "deterministic_nyfed_gscpi_v1",
    "gdelt.search_trends.v1": "deterministic_gdelt_search_trends_v1",
}
EXTRACTOR_GROUP = "platform-extractor"
EXTRACTOR_STAGE = "extract"
DOCUMENT_PARSED_TOPIC = "ingest.document_parsed"


class MedicalExtractor(Protocol):
    agent_name: str
    agent_version: str

    def extract_openfda_ndc(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_openfda_drug_enforcement(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_openfda_device_registrationlisting(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_openfda_device_enforcement(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_fda_drug_shortages(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_fda_warning_letters(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_fda_inspections_dashboard(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_gdelt_doc_search(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_gdacs_events(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_reliefweb_reports(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_worldbank_commodity_prices(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_eia_energy_prices(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_sec_edgar_supplier_filings(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_un_comtrade_trade_flows(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_freight_proxy_prices(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...

    def extract_search_trend_signals(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput: ...


class ExtractorReplaySummary(StrictBaseModel):
    data_dir: str
    raw_documents_scanned: int
    chunks_scanned: int
    chunks_extracted: int
    chunks_failed: int
    extraction_runs_created: int
    extraction_runs_existing: int
    extraction_failures_created: int
    extraction_failures_existing: int
    evidence_spans_created: int
    ingestion_errors_created: int
    events_emitted: int
    kafka_events_published: int = 0
    skipped_chunks: int
    unsupported_profiles: list[str] = Field(default_factory=list)
    extraction_run_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)


class ExtractorWorkerRunSummary(StrictBaseModel):
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
class ExtractorRuntime:
    consumer_client: KafkaConsumerClient
    producer_client: KafkaProducerClient
    direct_consumer: DirectKafkaConsumerClient | None = None
    direct_producer: DirectKafkaProducerClient | None = None

    async def close(self) -> None:
        if self.direct_consumer is not None:
            await self.direct_consumer.stop()
        if self.direct_producer is not None:
            await self.direct_producer.stop()


def run_local_extractor(
    *,
    settings: Settings,
    data_dir: Path | None = None,
    source_id: str | None = None,
    limit: int | None = None,
    extractor: MedicalExtractor | None = None,
) -> ExtractorReplaySummary:
    replay_dir = data_dir or settings.data_dir
    store = FileEvidenceStore(replay_dir)
    documents = _load_raw_documents(store, source_id)
    source_runs = _load_source_runs(store)
    configs: dict[str, SourceConfig | None] = {}
    active_extractor: MedicalExtractor = (
        extractor if extractor is not None else MedicalExtractionAgent()
    )
    model_factory = ModelFactory(settings)
    summary = _new_summary(str(replay_dir), raw_documents_scanned=len(documents))

    processed = 0
    for chunk in _load_chunks(store):
        document = documents.get(str(chunk.raw_document_id))
        if document is None:
            summary.skipped_chunks += 1
            continue
        if limit is not None and processed >= limit:
            break
        config = _config_for_document(document, settings, configs)
        if config is None or not _is_supported_profile(config.parser.profile):
            _track_unsupported(summary, config.parser.profile if config else document.source_id)
            summary.skipped_chunks += 1
            continue

        _extract_chunk_from_store(
            store=store,
            summary=summary,
            document=document,
            chunk=chunk,
            config=config,
            source_run=_source_run_for_document(document, source_runs),
            extractor=active_extractor,
            model_factory=model_factory,
        )
        processed += 1

    return summary


async def execute_extraction_event(
    *,
    settings: Settings,
    event: EventEnvelope,
    extractor: MedicalExtractor | None = None,
    producer: EventProducer | None = None,
) -> ExtractorReplaySummary:
    event = validate_event_payload(event)
    if event.event_type != DOCUMENT_PARSED_TOPIC:
        raise PermanentEventError(
            f"Unsupported extractor event type: {event.event_type}",
            error_type="unsupported_extractor_event",
        )
    payload = DocumentParsedPayload.model_validate(event.payload)
    store = FileEvidenceStore(settings.data_dir)
    documents = _load_raw_documents(store, None)
    document = documents.get(str(payload.raw_document_id))
    if document is None:
        raise PermanentEventError(
            f"Raw document for extraction event is missing: {payload.raw_document_id}",
            error_type="raw_document_missing",
        )
    source_runs = _load_source_runs(store)
    chunks_by_id = {str(chunk.id): chunk for chunk in _load_chunks(store)}
    chunks: list[DocumentChunk] = []
    for chunk_id in payload.document_chunk_ids:
        chunk = chunks_by_id.get(str(chunk_id))
        if chunk is None:
            raise PermanentEventError(
                f"Document chunk for extraction event is missing: {chunk_id}",
                error_type="document_chunk_missing",
            )
        chunks.append(chunk)

    summary = _new_summary(str(settings.data_dir), raw_documents_scanned=1)
    active_extractor: MedicalExtractor = (
        extractor if extractor is not None else MedicalExtractionAgent()
    )
    model_factory = ModelFactory(settings)
    configs: dict[str, SourceConfig | None] = {}
    config = _config_for_document(document, settings, configs)
    if config is None:
        raise PermanentEventError(
            f"Source config for extraction event is missing: {document.source_id}",
            error_type="source_config_missing",
        )
    if not _is_supported_profile(config.parser.profile):
        raise PermanentEventError(
            f"Unsupported parser profile for extractor: {config.parser.profile}",
            error_type="unsupported_parser_profile",
        )
    for chunk in chunks:
        if chunk.raw_document_id != document.id:
            raise PermanentEventError(
                "Document parsed event chunk does not belong to the raw document",
                error_type="chunk_document_mismatch",
            )
        _extract_chunk_from_store(
            store=store,
            summary=summary,
            document=document,
            chunk=chunk,
            config=config,
            source_run=_source_run_for_document(document, source_runs),
            extractor=active_extractor,
            model_factory=model_factory,
        )
    if producer is not None:
        summary.kafka_events_published = await publish_events_by_ids(
            store=store,
            producer=producer,
            event_ids=summary.event_ids,
        )
    return summary


async def run_extractor_once(
    *,
    settings: Settings,
    consumer_client: KafkaConsumerClient | None = None,
    producer_client: KafkaProducerClient | None = None,
    extractor: MedicalExtractor | None = None,
) -> EventProcessingResult:
    summary = await run_extractor_consumer(
        settings=settings,
        max_messages=1,
        consumer_client=consumer_client,
        producer_client=producer_client,
        extractor=extractor,
    )
    if not summary.results:
        raise RuntimeError("Extractor exited before processing a message.")
    return summary.results[0]


async def run_extractor_consumer(
    *,
    settings: Settings,
    max_messages: int | None = None,
    idle_timeout_seconds: float | None = None,
    consumer_client: KafkaConsumerClient | None = None,
    producer_client: KafkaProducerClient | None = None,
    extractor: MedicalExtractor | None = None,
) -> ExtractorWorkerRunSummary:
    if max_messages is not None and max_messages < 1:
        raise ValueError("max_messages must be greater than zero when provided.")

    runtime = await _start_extractor_runtime(
        settings=settings,
        consumer_client=consumer_client,
        producer_client=producer_client,
    )
    producer = EventProducer(runtime.producer_client)
    consumer = EventConsumer(
        runtime.consumer_client,
        producer,
        consumer_group=EXTRACTOR_GROUP,
        stage=EXTRACTOR_STAGE,
    )

    async def handler(received: EventEnvelope) -> None:
        await execute_extraction_event(
            settings=settings,
            event=received,
            extractor=extractor,
            producer=producer,
        )

    summary = ExtractorWorkerRunSummary(requested_messages=max_messages)
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


async def _start_extractor_runtime(
    *,
    settings: Settings,
    consumer_client: KafkaConsumerClient | None,
    producer_client: KafkaProducerClient | None,
) -> ExtractorRuntime:
    direct_consumer: DirectKafkaConsumerClient | None = None
    direct_producer: DirectKafkaProducerClient | None = None
    selected_consumer = consumer_client
    selected_producer = producer_client
    if selected_consumer is None:
        direct_consumer = DirectKafkaConsumerClient(
            settings,
            topics=[DOCUMENT_PARSED_TOPIC],
            group_id=EXTRACTOR_GROUP,
        )
        selected_consumer = direct_consumer
        await direct_consumer.start()
    if selected_producer is None:
        direct_producer = DirectKafkaProducerClient(settings)
        selected_producer = direct_producer
        await direct_producer.start()
    return ExtractorRuntime(
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


def _new_summary(data_dir: str, *, raw_documents_scanned: int) -> ExtractorReplaySummary:
    return ExtractorReplaySummary(
        data_dir=data_dir,
        raw_documents_scanned=raw_documents_scanned,
        chunks_scanned=0,
        chunks_extracted=0,
        chunks_failed=0,
        extraction_runs_created=0,
        extraction_runs_existing=0,
        extraction_failures_created=0,
        extraction_failures_existing=0,
        evidence_spans_created=0,
        ingestion_errors_created=0,
        events_emitted=0,
        skipped_chunks=0,
    )


def _record_existing_extraction(
    *,
    store: FileEvidenceStore,
    summary: ExtractorReplaySummary,
    source_run: SourceRun,
    extraction_run: ExtractionRun,
    evidence_span: EvidenceSpan,
) -> None:
    summary.extraction_runs_existing += 1
    if extraction_run.status == "failed":
        summary.extraction_failures_existing += 1
        summary.chunks_failed += 1
    else:
        summary.chunks_extracted += 1
    _record_extraction_completed_event(
        store=store,
        summary=summary,
        source_run=source_run,
        extraction_run=extraction_run,
        evidence_span=evidence_span,
    )
    summary.extraction_run_ids.append(str(extraction_run.id))


def _extract_chunk_from_store(
    *,
    store: FileEvidenceStore,
    summary: ExtractorReplaySummary,
    document: RawDocument,
    chunk: DocumentChunk,
    config: SourceConfig,
    source_run: SourceRun,
    extractor: MedicalExtractor,
    model_factory: ModelFactory,
) -> None:
    summary.chunks_scanned += 1
    evidence_span = evidence_span_from_chunk(document, chunk)
    if store.write_evidence_span(evidence_span):
        summary.evidence_spans_created += 1

    prompt_hash = _prompt_hash_for_profile(config.parser.profile)
    input_hash = extraction_input_hash(chunk)
    existing_run = store.find_extraction_run(
        agent_name=extractor.agent_name,
        agent_version=extractor.agent_version,
        input_hash=input_hash,
        prompt_hash=prompt_hash,
        output_schema_version=1,
    )
    if existing_run is not None:
        _record_existing_extraction(
            store=store,
            summary=summary,
            source_run=source_run,
            extraction_run=existing_run,
            evidence_span=evidence_span,
        )
        return

    _run_new_extraction(
        store=store,
        summary=summary,
        extractor=extractor,
        model_factory=model_factory,
        config=config,
        source_run=source_run,
        document=document,
        chunk=chunk,
        evidence_span_id=evidence_span.id,
        evidence_span=evidence_span,
        prompt_hash=prompt_hash,
        input_hash=input_hash,
    )


def _run_new_extraction(
    *,
    store: FileEvidenceStore,
    summary: ExtractorReplaySummary,
    extractor: MedicalExtractor,
    model_factory: ModelFactory,
    config: SourceConfig,
    source_run: SourceRun,
    document: RawDocument,
    chunk: DocumentChunk,
    evidence_span_id: UUID,
    evidence_span: EvidenceSpan,
    prompt_hash: str,
    input_hash: str,
) -> None:
    extraction_run = _new_extraction_run(
        extractor=extractor,
        model_factory=model_factory,
        document=document,
        chunk=chunk,
        prompt_hash=prompt_hash,
        input_hash=input_hash,
    )
    try:
        output = _extract(
            config=config,
            extractor=extractor,
            document=document,
            chunk=chunk,
            evidence_span_id=evidence_span_id,
        )
    except Exception as exc:
        _record_failed_extraction(
            store=store,
            summary=summary,
            source_run=source_run,
            document=document,
            chunk=chunk,
            evidence_span=evidence_span,
            extraction_run=extraction_run,
            prompt_hash=prompt_hash,
            exc=exc,
        )
        return

    _record_succeeded_extraction(
        store=store,
        summary=summary,
        source_run=source_run,
        evidence_span=evidence_span,
        extraction_run=extraction_run,
        output=output,
    )


def _record_failed_extraction(
    *,
    store: FileEvidenceStore,
    summary: ExtractorReplaySummary,
    source_run: SourceRun,
    document: RawDocument,
    chunk: DocumentChunk,
    evidence_span: EvidenceSpan,
    extraction_run: ExtractionRun,
    prompt_hash: str,
    exc: Exception,
) -> None:
    extraction_run.status = "failed"
    extraction_run.finished_at = datetime.now(UTC)
    extraction_run.error = str(exc)
    extraction_run.raw_output = {"error_type": exc.__class__.__name__}
    if store.write_extraction_run(extraction_run):
        summary.extraction_failures_created += 1
        error = IngestionError(
            source_id=document.source_id,
            source_run_id=source_run.id,
            raw_document_id=document.id,
            stage="extractor",
            error_type=exc.__class__.__name__,
            message=str(exc),
            details={
                "document_chunk_id": str(chunk.id),
                "extraction_run_id": str(extraction_run.id),
                "prompt_hash": prompt_hash,
            },
            retryable=True,
        )
        summary.ingestion_errors_created += int(store.write_ingestion_error(error))
    else:
        summary.extraction_runs_existing += 1
        summary.extraction_failures_existing += 1
    _record_extraction_completed_event(
        store=store,
        summary=summary,
        source_run=source_run,
        extraction_run=extraction_run,
        evidence_span=evidence_span,
    )
    summary.extraction_run_ids.append(str(extraction_run.id))
    summary.chunks_failed += 1


def _record_succeeded_extraction(
    *,
    store: FileEvidenceStore,
    summary: ExtractorReplaySummary,
    source_run: SourceRun,
    evidence_span: EvidenceSpan,
    extraction_run: ExtractionRun,
    output: MedicalExtractionOutput,
) -> None:
    extraction_run.status = "succeeded"
    extraction_run.finished_at = datetime.now(UTC)
    _attach_extraction_run_id(output, extraction_run.id)
    extraction_run.validated_output = output.model_dump(mode="json")
    if store.write_extraction_run(extraction_run):
        summary.extraction_runs_created += 1
    else:
        summary.extraction_runs_existing += 1
        _attach_extraction_run_id(output, extraction_run.id)
    _record_extraction_completed_event(
        store=store,
        summary=summary,
        source_run=source_run,
        extraction_run=extraction_run,
        evidence_span=evidence_span,
    )
    summary.extraction_run_ids.append(str(extraction_run.id))
    summary.chunks_extracted += 1


def _record_extraction_completed_event(
    *,
    store: FileEvidenceStore,
    summary: ExtractorReplaySummary,
    source_run: SourceRun,
    extraction_run: ExtractionRun,
    evidence_span: EvidenceSpan,
) -> None:
    emitted = emit_extraction_completed_event(
        store,
        run=source_run,
        extraction_run=extraction_run,
        evidence_span=evidence_span,
    )
    summary.events_emitted += int(emitted)
    if not emitted:
        return
    event = _event_by_idempotency_key(
        store,
        f"ingest.extraction_completed:{extraction_run.id}",
    )
    if event is not None:
        summary.event_ids.append(str(event.event_id))


def _event_by_idempotency_key(
    store: FileEvidenceStore,
    idempotency_key: str,
) -> EventEnvelope | None:
    for row in store.read_collection("events"):
        if row.get("idempotency_key") == idempotency_key:
            return EventEnvelope.model_validate(row)
    return None


def _load_raw_documents(
    store: FileEvidenceStore,
    source_id: str | None,
) -> dict[str, RawDocument]:
    documents: dict[str, RawDocument] = {}
    for row in store.read_collection("raw_documents"):
        if source_id is not None and row.get("source_id") != source_id:
            continue
        document = RawDocument.model_validate(row)
        documents[str(document.id)] = document
    return documents


def _load_chunks(store: FileEvidenceStore) -> list[DocumentChunk]:
    return [
        DocumentChunk.model_validate(row)
        for row in store.read_collection("document_chunks")
        if row.get("raw_document_id")
    ]


def _load_source_runs(store: FileEvidenceStore) -> dict[str, SourceRun]:
    runs: dict[str, SourceRun] = {}
    for row in store.read_collection("source_runs"):
        run = SourceRun.model_validate(row)
        runs[str(run.id)] = run
    return runs


def _config_for_document(
    document: RawDocument,
    settings: Settings,
    cache: dict[str, SourceConfig | None],
) -> SourceConfig | None:
    if document.source_id not in cache:
        try:
            cache[document.source_id] = load_source_config(
                find_source_config(document.source_id, settings.source_dir)
            )
        except FileNotFoundError:
            cache[document.source_id] = None
    return cache[document.source_id]


def _source_run_for_document(
    document: RawDocument,
    source_runs: dict[str, SourceRun],
) -> SourceRun:
    run = source_runs.get(str(document.source_run_id))
    if run is not None:
        return run
    run = SourceRun(
        source_id=document.source_id,
        run_type="replay",
        status="succeeded",
        idempotency_key=f"extractor-replay:missing-source-run:{document.source_run_id}",
    )
    run.id = document.source_run_id
    run.finished_at = datetime.now(UTC)
    return run


def _is_supported_profile(profile: str) -> bool:
    return profile in PROMPT_HASH_BY_PROFILE


def _extract(
    *,
    config: SourceConfig,
    extractor: MedicalExtractor,
    document: RawDocument,
    chunk: DocumentChunk,
    evidence_span_id: UUID,
) -> MedicalExtractionOutput:
    extractor_by_profile = {
        "openfda.drug_ndc.v1": extractor.extract_openfda_ndc,
        "openfda.drug_enforcement.v1": extractor.extract_openfda_drug_enforcement,
        "openfda.device_registrationlisting.v1": (
            extractor.extract_openfda_device_registrationlisting
        ),
        "openfda.device_enforcement.v1": extractor.extract_openfda_device_enforcement,
        "fda.drug_shortages_html.v1": extractor.extract_fda_drug_shortages,
        "fda.warning_letters_xlsx.v1": extractor.extract_fda_warning_letters,
        "fda.inspections_dashboard.v1": extractor.extract_fda_inspections_dashboard,
        "gdelt.doc_search.v1": extractor.extract_gdelt_doc_search,
        "gdacs.events_rss.v1": extractor.extract_gdacs_events,
        "reliefweb.reports.v1": extractor.extract_reliefweb_reports,
        "worldbank.commodity_prices_monthly.v1": (extractor.extract_worldbank_commodity_prices),
        "eia.energy_prices.v1": extractor.extract_eia_energy_prices,
        "sec.edgar_supplier_filings.v1": extractor.extract_sec_edgar_supplier_filings,
        "uncomtrade.trade_flows.v1": extractor.extract_un_comtrade_trade_flows,
        "nyfed.gscpi.v1": extractor.extract_freight_proxy_prices,
        "gdelt.search_trends.v1": extractor.extract_search_trend_signals,
    }
    profile_extractor = extractor_by_profile.get(config.parser.profile)
    if profile_extractor is not None:
        return profile_extractor(document, chunk, evidence_span_id=evidence_span_id)
    raise ValueError(f"Unsupported parser profile: {config.parser.profile}")


def _new_extraction_run(
    *,
    extractor: MedicalExtractor,
    model_factory: ModelFactory,
    document: RawDocument,
    chunk: DocumentChunk,
    prompt_hash: str,
    input_hash: str,
) -> ExtractionRun:
    return ExtractionRun(
        raw_document_id=document.id,
        document_chunk_id=chunk.id,
        agent_name=extractor.agent_name,
        agent_version=extractor.agent_version,
        model_name=model_factory.configured_model_name,
        prompt_hash=prompt_hash,
        input_hash=input_hash,
        output_schema="MedicalExtractionOutput",
        status="running",
        idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
    )


def _prompt_hash_for_profile(profile: str) -> str:
    prompt_hash = PROMPT_HASH_BY_PROFILE.get(profile)
    if prompt_hash is not None:
        return prompt_hash
    raise ValueError(f"Unsupported parser profile: {profile}")


def _attach_extraction_run_id(
    output: MedicalExtractionOutput,
    extraction_run_id: UUID,
) -> None:
    for entity in output.entities:
        _attach_to_entity(entity, extraction_run_id)
    for relationship in output.relationships:
        _attach_to_relationship(relationship, extraction_run_id)
    for event in _all_events(output):
        _attach_to_refs(event.evidence, extraction_run_id)


def _attach_to_entity(entity: MedicalEntity, extraction_run_id: UUID) -> None:
    _attach_to_refs(entity.evidence, extraction_run_id)


def _attach_to_relationship(
    relationship: ExtractedRelationship,
    extraction_run_id: UUID,
) -> None:
    _attach_to_refs(relationship.evidence, extraction_run_id)


def _attach_to_refs(refs: list[EvidenceRef], extraction_run_id: UUID) -> None:
    for ref in refs:
        ref.extraction_run_id = extraction_run_id


def _all_events(
    output: MedicalExtractionOutput,
) -> list[
    RegulatoryEvent
    | RecallEvent
    | ShortageEvent
    | NewsEvent
    | DisasterEvent
    | StrikeEvent
    | PriceObservation
    | TradeFlowObservation
    | LogisticsPressureObservation
    | TrendSignalObservation
]:
    return [
        *output.regulatory_events,
        *output.recall_events,
        *output.shortage_events,
        *output.news_events,
        *output.disaster_events,
        *output.strike_events,
        *output.price_observations,
        *output.trade_flow_observations,
        *output.logistics_pressure_observations,
        *output.trend_signal_observations,
    ]


def _track_unsupported(summary: ExtractorReplaySummary, profile: str) -> None:
    if profile not in summary.unsupported_profiles:
        summary.unsupported_profiles.append(profile)
