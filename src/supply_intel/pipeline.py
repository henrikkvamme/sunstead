from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from supply_intel.agents.embeddings import EmbeddingClient
from supply_intel.agents.factory import ModelFactory
from supply_intel.agents.medical_extraction import MedicalExtractionAgent, extraction_input_hash
from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.entity_resolution.normalize import normalize_name
from supply_intel.entity_resolution.service import (
    EntityAlias,
    EntityResolutionService,
    HumanReviewTask,
)
from supply_intel.events.envelope import build_event
from supply_intel.graph.mapper import map_extraction_to_graph
from supply_intel.models.base import EvidenceRef
from supply_intel.models.documents import DocumentChunk, EvidenceSpan
from supply_intel.models.extraction import EntityMention, ExtractionRun, MedicalExtractionOutput
from supply_intel.models.graph import GraphNodeUpsert, GraphRelationshipUpsert
from supply_intel.models.kafka import (
    DocumentParsedPayload,
    ExtractionCompletedPayload,
    GraphNodeUpsertPayload,
    GraphRelationshipUpsertPayload,
    RawDocumentCreatedPayload,
    RiskAlertPayload,
    RiskCandidatePayload,
    RiskCaseCreatedPayload,
    RiskVerdictPayload,
    TraceMetadata,
)
from supply_intel.models.medical import MedicalEntity
from supply_intel.models.risk import RiskAlert, RiskCandidate, RiskCase, RiskVerdict
from supply_intel.models.source import RawDocument, SourceConfig, SourceCursor, SourceRun
from supply_intel.risk.cases import (
    build_recall_quality_case,
    build_shortage_case,
    feature_snapshots_for_case,
)
from supply_intel.settings import Settings
from supply_intel.sources.adapters import adapter_for_source
from supply_intel.sources.adapters.base import FetchedPayload, SourceAdapter
from supply_intel.sources.cursors import source_cursor_from_payloads, source_cursor_snapshot
from supply_intel.sources.parsers.eia_energy import parse_eia_energy_prices_document
from supply_intel.sources.parsers.fda_inspections import parse_fda_inspections_dashboard_document
from supply_intel.sources.parsers.fda_shortages import parse_fda_drug_shortages_document
from supply_intel.sources.parsers.fda_warning_letters import parse_fda_warning_letters_document
from supply_intel.sources.parsers.freight_proxy import parse_freight_proxy_prices_document
from supply_intel.sources.parsers.gdacs import parse_gdacs_events_document
from supply_intel.sources.parsers.gdelt_doc import parse_gdelt_doc_search_document
from supply_intel.sources.parsers.openfda_device import (
    parse_openfda_device_enforcement_document,
    parse_openfda_device_registrationlisting_document,
)
from supply_intel.sources.parsers.openfda_enforcement import (
    parse_openfda_drug_enforcement_document,
)
from supply_intel.sources.parsers.openfda_ndc import parse_openfda_ndc_document
from supply_intel.sources.parsers.reliefweb import parse_reliefweb_reports_document
from supply_intel.sources.parsers.search_trends import parse_search_trend_signals_document
from supply_intel.sources.parsers.sec_edgar import parse_sec_edgar_supplier_filings_document
from supply_intel.sources.parsers.un_comtrade import parse_un_comtrade_trade_flows_document
from supply_intel.sources.parsers.worldbank_commodities import (
    parse_worldbank_commodity_prices_document,
)

DocumentProcessor = Callable[..., None]


def load_fixture_records(path: Path) -> list[dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("results", data if isinstance(data, list) else [])
    if not isinstance(records, list):
        raise ValueError("Fixture must contain a list or a results list")
    return [record for record in records if isinstance(record, dict)]


def raw_document_from_record(
    *,
    config: SourceConfig,
    run: SourceRun,
    record: dict[str, object],
    source_url: str,
) -> RawDocument:
    payload = json.dumps(record, sort_keys=True)
    content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    dedupe_key = "|".join(str(record.get(field, "")) for field in config.dedupe.key_fields)
    if not dedupe_key.strip("|"):
        dedupe_key = content_hash
    return RawDocument(
        source_id=config.source_id,
        source_run_id=run.id,
        source_url=source_url,
        canonical_url=source_url,
        request={"method": config.method, "url": config.base_url},
        response_headers={},
        http_status=200,
        content_type="application/json",
        content_length=len(payload.encode("utf-8")),
        content_hash=content_hash,
        payload_storage="inline",
        payload_text=payload,
        fetched_at=datetime.now(UTC),
        dedupe_key=dedupe_key,
        raw_metadata={"source_name": config.name},
    )


def raw_document_from_payload(
    *,
    config: SourceConfig,
    run: SourceRun,
    payload: FetchedPayload,
) -> RawDocument:
    body = payload.content_bytes or payload.text.encode("utf-8")
    content_hash = hashlib.sha256(body).hexdigest()
    record = payload.record or {"value": payload.text}
    dedupe_key = "|".join(str(record.get(field, "")) for field in config.dedupe.key_fields)
    if not dedupe_key.strip("|"):
        dedupe_key = content_hash
    payload_text = _payload_text(payload)
    return RawDocument(
        source_id=config.source_id,
        source_run_id=run.id,
        source_url=payload.source_url,
        canonical_url=payload.source_url if config.dedupe.canonical_url else None,
        request={"method": config.method, "url": config.base_url},
        response_headers=payload.headers,
        http_status=payload.status_code,
        content_type=payload.content_type,
        content_length=len(body),
        content_hash=content_hash,
        payload_storage="inline",
        payload_bytes=payload.content_bytes,
        payload_text=payload_text,
        fetched_at=payload.fetched_at,
        dedupe_key=dedupe_key,
        raw_metadata={"source_name": config.name},
    )


def raw_document_from_text(
    *,
    config: SourceConfig,
    run: SourceRun,
    text: str,
    source_url: str,
    content_type: str,
) -> RawDocument:
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    record = {"canonical_url": source_url, "source_url": source_url}
    dedupe_key = "|".join(str(record.get(field, "")) for field in config.dedupe.key_fields)
    if not dedupe_key.strip("|"):
        dedupe_key = source_url or content_hash
    return RawDocument(
        source_id=config.source_id,
        source_run_id=run.id,
        source_url=source_url,
        canonical_url=source_url if config.dedupe.canonical_url else None,
        request={"method": config.method, "url": config.base_url},
        response_headers={},
        http_status=200,
        content_type=content_type,
        content_length=len(text.encode("utf-8")),
        content_hash=content_hash,
        payload_storage="inline",
        payload_text=text,
        fetched_at=datetime.now(UTC),
        dedupe_key=dedupe_key,
        raw_metadata={"source_name": config.name},
    )


def _payload_text(payload: FetchedPayload) -> str | None:
    if payload.content_bytes is None:
        return payload.text
    if payload.text:
        return payload.text
    try:
        return payload.content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _prepare_run_cursor(
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
) -> SourceCursor | None:
    current_cursor = store.current_source_cursor(config.source_id)
    run.cursor_before = source_cursor_snapshot(current_cursor)
    return current_cursor


def _source_cursor_from_snapshot(snapshot: dict[str, object] | None) -> SourceCursor | None:
    if not snapshot:
        return None
    return SourceCursor.model_validate(snapshot)


def _checkpoint_run_cursor(
    store: FileEvidenceStore,
    *,
    config: SourceConfig,
    run: SourceRun,
    payloads: list[FetchedPayload],
) -> None:
    if not payloads:
        run.cursor_after = run.cursor_before
        return
    cursor = source_cursor_from_payloads(config=config, run=run, payloads=payloads)
    run.cursor_after = source_cursor_snapshot(cursor)
    store.write_source_cursor(cursor)


def emit_raw_document_created_event(
    store: FileEvidenceStore,
    *,
    run: SourceRun,
    document: RawDocument,
) -> None:
    payload = RawDocumentCreatedPayload(
        source_id=document.source_id,
        source_run_id=run.id,
        raw_document_id=document.id,
        source_url=document.source_url,
        content_hash=document.content_hash,
        content_type=document.content_type,
        fetched_at=document.fetched_at,
    )
    store.write_event(
        build_event(
            event_type="ingest.raw_document_created",
            service="ingester",
            source_id=document.source_id,
            payload=payload.model_dump(mode="json"),
            idempotency_key=f"ingest.raw_document_created:{document.id}",
            correlation_id=run.correlation_id,
            trace=TraceMetadata(source_run_id=run.id, raw_document_id=document.id),
        )
    )


def emit_document_parsed_event(
    store: FileEvidenceStore,
    *,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    chunks: list[DocumentChunk],
) -> None:
    payload = DocumentParsedPayload(
        raw_document_id=document.id,
        document_chunk_ids=[chunk.id for chunk in chunks],
        parser_profile=config.parser.profile,
        chunk_count=len(chunks),
    )
    store.write_event(
        build_event(
            event_type="ingest.document_parsed",
            service="parser",
            source_id=document.source_id,
            payload=payload.model_dump(mode="json"),
            idempotency_key=f"ingest.document_parsed:{document.id}:{payload.chunk_count}",
            correlation_id=run.correlation_id,
            trace=TraceMetadata(source_run_id=run.id, raw_document_id=document.id),
        )
    )


def emit_extraction_completed_event(
    store: FileEvidenceStore,
    *,
    run: SourceRun,
    extraction_run: ExtractionRun,
    evidence_span: EvidenceSpan,
) -> bool:
    if extraction_run.raw_document_id is None:
        raise ValueError("Extraction completed events require raw_document_id")
    payload = ExtractionCompletedPayload(
        extraction_run_id=extraction_run.id,
        raw_document_id=extraction_run.raw_document_id,
        document_chunk_id=extraction_run.document_chunk_id,
        agent_name=extraction_run.agent_name,
        output_schema=extraction_run.output_schema,
        evidence_span_ids=[evidence_span.id],
        status=extraction_run.status,
    )
    return store.write_event(
        build_event(
            event_type="ingest.extraction_completed",
            service="extractor",
            source_id=evidence_span.source_id,
            payload=payload.model_dump(mode="json"),
            idempotency_key=f"ingest.extraction_completed:{extraction_run.id}",
            correlation_id=run.correlation_id,
            trace=TraceMetadata(
                source_run_id=run.id,
                raw_document_id=extraction_run.raw_document_id,
            ),
        )
    )


def emit_graph_node_upsert_event(
    store: FileEvidenceStore,
    *,
    run: SourceRun,
    document: RawDocument,
    upsert: GraphNodeUpsert,
) -> None:
    payload = GraphNodeUpsertPayload(
        graph_node_key=upsert.graph_node_key,
        labels=list(upsert.labels),
        properties=upsert.properties,
        source_document_id=upsert.source_document_id,
        evidence_span_id=upsert.evidence_span_id,
        extraction_run_id=upsert.extraction_run_id,
        confidence=upsert.confidence,
    )
    store.write_event(
        build_event(
            event_type="graph.node_upsert",
            service="graph-mapper",
            source_id=document.source_id,
            payload=payload.model_dump(mode="json"),
            idempotency_key=f"graph.node_upsert:{upsert.graph_node_key}:{document.id}",
            correlation_id=run.correlation_id,
            trace=TraceMetadata(source_run_id=run.id, raw_document_id=document.id),
        )
    )


def emit_graph_relationship_upsert_event(
    store: FileEvidenceStore,
    *,
    run: SourceRun,
    document: RawDocument,
    upsert: GraphRelationshipUpsert,
) -> None:
    payload = GraphRelationshipUpsertPayload(
        relationship_key=upsert.relationship_key,
        from_key=upsert.from_key,
        to_key=upsert.to_key,
        relationship_type=upsert.relationship_type,
        properties=upsert.properties.model_dump(mode="json"),
    )
    store.write_event(
        build_event(
            event_type="graph.relationship_upsert",
            service="graph-mapper",
            source_id=document.source_id,
            payload=payload.model_dump(mode="json"),
            idempotency_key=f"graph.relationship_upsert:{upsert.relationship_key}",
            correlation_id=run.correlation_id,
            trace=TraceMetadata(source_run_id=run.id, raw_document_id=document.id),
        )
    )


def emit_risk_case_created_event(
    store: FileEvidenceStore,
    *,
    run: SourceRun,
    document: RawDocument,
    risk_case: RiskCase,
    verdict: RiskVerdict,
) -> None:
    payload = RiskCaseCreatedPayload(
        risk_case_id=risk_case.id,
        case_key=risk_case.case_key,
        risk_type=risk_case.risk_type,
        severity=risk_case.severity,
        status=risk_case.status,
        risk_score=risk_case.risk_score,
        confidence=risk_case.confidence,
        evidence_span_ids=verdict.evidence_span_ids,
    )
    store.write_event(
        build_event(
            event_type="risk.case_created",
            service="risk-engine",
            source_id=document.source_id,
            payload=payload.model_dump(mode="json"),
            idempotency_key=f"risk.case_created:{risk_case.case_key}",
            correlation_id=run.correlation_id,
            trace=TraceMetadata(source_run_id=run.id, raw_document_id=document.id),
        )
    )


def emit_risk_candidate_event(
    store: FileEvidenceStore,
    *,
    run: SourceRun,
    document: RawDocument,
    candidate: RiskCandidate,
) -> None:
    payload = RiskCandidatePayload(
        candidate_key=candidate.candidate_key,
        risk_type=candidate.risk_type,
        scope=candidate.scope,
        signals=candidate.signals,
        initial_score=candidate.initial_score,
        confidence=candidate.confidence,
        evidence_span_ids=candidate.evidence_span_ids,
    )
    store.write_event(
        build_event(
            event_type="risk.candidates",
            service="risk-engine",
            source_id=document.source_id,
            payload=payload.model_dump(mode="json"),
            idempotency_key=f"risk.candidates:{candidate.candidate_key}",
            correlation_id=run.correlation_id,
            trace=TraceMetadata(source_run_id=run.id, raw_document_id=document.id),
        )
    )


def emit_risk_verdict_event(
    store: FileEvidenceStore,
    *,
    run: SourceRun,
    document: RawDocument,
    verdict: RiskVerdict,
) -> None:
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
    store.write_event(
        build_event(
            event_type="risk.verdicts",
            service="verdict-agent",
            source_id=document.source_id,
            payload=payload.model_dump(mode="json"),
            idempotency_key=f"risk.verdicts:{verdict.id}",
            correlation_id=run.correlation_id,
            trace=TraceMetadata(source_run_id=run.id, raw_document_id=document.id),
        )
    )


def emit_risk_alert_event(
    store: FileEvidenceStore,
    *,
    run: SourceRun,
    document: RawDocument,
    alert: RiskAlert,
) -> None:
    payload = RiskAlertPayload(
        alert_key=alert.alert_key,
        risk_case_id=alert.risk_case_id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        status=alert.status,
        title=alert.title,
        channels=alert.channels,
    )
    store.write_event(
        build_event(
            event_type="risk.alerts",
            service="alert-worker",
            source_id=document.source_id,
            payload=payload.model_dump(mode="json"),
            idempotency_key=f"risk.alerts:{alert.alert_key}",
            correlation_id=run.correlation_id,
            trace=TraceMetadata(source_run_id=run.id, raw_document_id=document.id),
        )
    )


def resolve_and_store_entity(
    *,
    store: FileEvidenceStore,
    resolver: EntityResolutionService,
    entity: MedicalEntity,
    document: RawDocument,
    chunk: DocumentChunk,
    extraction_run: ExtractionRun,
    evidence_span: EvidenceSpan,
    stats: dict[str, int],
) -> None:
    canonical = resolver.resolve(entity)
    if store.write_canonical_entity(canonical):
        _increment(stats, "canonical_entities")
    alias = EntityAlias(
        canonical_entity_id=canonical.id,
        alias=entity.name,
        normalized_alias=normalize_name(entity.name),
        alias_type="extracted_name",
        source_id=document.source_id,
        evidence_span_id=evidence_span.id,
        confidence=entity.confidence,
    )
    if store.write_entity_alias(alias):
        _increment(stats, "entity_aliases")
    for external_id_type, external_id in entity.external_ids.items():
        external_alias = EntityAlias(
            canonical_entity_id=canonical.id,
            alias=f"{external_id_type}:{external_id}",
            normalized_alias=normalize_name(str(external_id)),
            alias_type="external_id",
            source_id=document.source_id,
            evidence_span_id=evidence_span.id,
            confidence=1.0,
        )
        if store.write_entity_alias(external_alias):
            _increment(stats, "entity_aliases")
    mention = EntityMention(
        raw_document_id=document.id,
        document_chunk_id=chunk.id,
        extraction_run_id=extraction_run.id,
        evidence_span_id=evidence_span.id,
        entity_type=entity.entity_type,
        mention_text=entity.name,
        normalized_mention=normalize_name(entity.name),
        candidate_external_ids=entity.external_ids,
        canonical_entity_id=canonical.id,
        resolution_status="needs_human_review" if canonical.needs_review else "resolved",
        resolution_confidence=canonical.confidence,
        resolution_method="deterministic_key",
        needs_review=canonical.needs_review,
    )
    if store.write_entity_mention(mention):
        _increment(stats, "entity_mentions")
    if canonical.needs_review:
        review_task = HumanReviewTask(
            target_table="canonical_entities",
            target_id=canonical.id,
            review_type=review_type_for_reason(canonical.review_reason),
            reason=canonical.review_reason or "Entity resolution requires review.",
            priority="P1",
            evidence_span_ids=[evidence_span.id],
        )
        if store.write_human_review_task(review_task):
            _increment(stats, "human_review_tasks")


def review_type_for_reason(
    reason: str | None,
) -> Literal["low_confidence", "conflict", "high_impact_sparse_evidence"]:
    if reason and "Conflicting normalized names" in reason:
        return "conflict"
    if reason and "confidence" in reason.casefold():
        return "low_confidence"
    return "high_impact_sparse_evidence"


def write_risk_feature_snapshots(
    *,
    store: FileEvidenceStore,
    case: RiskCase,
    verdict: RiskVerdict,
    stats: dict[str, int],
) -> None:
    for snapshot in feature_snapshots_for_case(case, evidence_span_ids=verdict.evidence_span_ids):
        if store.write_risk_feature_snapshot(snapshot):
            _increment(stats, "risk_feature_snapshots")


def _increment(stats: dict[str, int], key: str) -> None:
    stats[key] = stats.get(key, 0) + 1


def attach_configured_chunk_embeddings(
    *,
    chunks: list[DocumentChunk],
    model_factory: ModelFactory,
    stats: dict[str, int],
    embedding_client: EmbeddingClient | None = None,
) -> None:
    if not chunks or not model_factory.is_embedding_configured():
        return
    metadata = model_factory.embedding_metadata()
    client = embedding_client or model_factory.embedding_client()
    embeddings = client.embed_texts([chunk.text for chunk in chunks])
    if len(embeddings) != len(chunks):
        raise ValueError(
            f"Embedding provider returned {len(embeddings)} vectors for {len(chunks)} chunks."
        )
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        chunk.embedding = embedding
        chunk.embedding_model = metadata.model_name
        _increment(stats, "chunk_embeddings")


def attach_extraction_run_id(
    output: MedicalExtractionOutput,
    extraction_run: ExtractionRun,
) -> None:
    for entity in output.entities:
        _attach_refs(entity.evidence, extraction_run)
    for relationship in output.relationships:
        _attach_refs(relationship.evidence, extraction_run)
    for regulatory_event in output.regulatory_events:
        _attach_refs(regulatory_event.evidence, extraction_run)
    for recall_event in output.recall_events:
        _attach_refs(recall_event.evidence, extraction_run)
    for shortage_event in output.shortage_events:
        _attach_refs(shortage_event.evidence, extraction_run)
    for news_event in output.news_events:
        _attach_refs(news_event.evidence, extraction_run)
    for disaster_event in output.disaster_events:
        _attach_refs(disaster_event.evidence, extraction_run)
    for strike_event in output.strike_events:
        _attach_refs(strike_event.evidence, extraction_run)
    for price_observation in output.price_observations:
        _attach_refs(price_observation.evidence, extraction_run)
    for trade_flow in output.trade_flow_observations:
        _attach_refs(trade_flow.evidence, extraction_run)
    for logistics_pressure in output.logistics_pressure_observations:
        _attach_refs(logistics_pressure.evidence, extraction_run)
    for trend_signal in output.trend_signal_observations:
        _attach_refs(trend_signal.evidence, extraction_run)


def _attach_refs(refs: list[EvidenceRef], extraction_run: ExtractionRun) -> None:
    for evidence in refs:
        evidence.extraction_run_id = extraction_run.id


def process_openfda_ndc_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_openfda_ndc_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(
        store,
        config=config,
        run=run,
        document=document,
        chunks=chunks,
    )
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_openfda_ndc(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_openfda_ndc_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            validated_output=output.model_dump(mode="json"),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        for entity in output.entities:
            resolve_and_store_entity(
                store=store,
                resolver=resolver,
                entity=entity,
                document=document,
                chunk=chunk,
                extraction_run=extraction_run,
                evidence_span=evidence_span,
                stats=stats,
            )
            stats["entities_resolved"] += 1
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(
                store,
                run=run,
                document=document,
                upsert=node_upsert,
            )
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1


def process_openfda_drug_enforcement_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_openfda_drug_enforcement_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(
        store,
        config=config,
        run=run,
        document=document,
        chunks=chunks,
    )
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_openfda_drug_enforcement(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_openfda_drug_enforcement_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            validated_output=output.model_dump(mode="json"),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        for entity in output.entities:
            resolve_and_store_entity(
                store=store,
                resolver=resolver,
                entity=entity,
                document=document,
                chunk=chunk,
                extraction_run=extraction_run,
                evidence_span=evidence_span,
                stats=stats,
            )
            stats["entities_resolved"] += 1
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(
                store,
                run=run,
                document=document,
                upsert=node_upsert,
            )
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1
        for recall in output.recall_events:
            stats["recall_events"] += 1
            candidate, case, verdict, alert = build_recall_quality_case(
                recall,
                evidence_span_id=evidence_span.id,
                affected_relationships=max(1, len(output.relationships)),
            )
            if store.write_risk_candidate(candidate):
                _increment(stats, "risk_candidates")
            store.write_risk_case(case)
            store.write_risk_verdict(verdict)
            store.write_risk_alert(alert)
            write_risk_feature_snapshots(
                store=store,
                case=case,
                verdict=verdict,
                stats=stats,
            )
            emit_risk_candidate_event(
                store,
                run=run,
                document=document,
                candidate=candidate,
            )
            emit_risk_case_created_event(
                store,
                run=run,
                document=document,
                risk_case=case,
                verdict=verdict,
            )
            emit_risk_verdict_event(
                store,
                run=run,
                document=document,
                verdict=verdict,
            )
            emit_risk_alert_event(
                store,
                run=run,
                document=document,
                alert=alert,
            )
            stats["risk_cases"] += 1
            stats["risk_alerts"] += 1


def process_openfda_device_registrationlisting_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_openfda_device_registrationlisting_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(store, config=config, run=run, document=document, chunks=chunks)
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_openfda_device_registrationlisting(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_openfda_device_registrationlisting_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        for entity in output.entities:
            resolve_and_store_entity(
                store=store,
                resolver=resolver,
                entity=entity,
                document=document,
                chunk=chunk,
                extraction_run=extraction_run,
                evidence_span=evidence_span,
                stats=stats,
            )
            stats["entities_resolved"] += 1
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(store, run=run, document=document, upsert=node_upsert)
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1


def process_openfda_device_enforcement_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_openfda_device_enforcement_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(store, config=config, run=run, document=document, chunks=chunks)
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_openfda_device_enforcement(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_openfda_device_enforcement_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        for entity in output.entities:
            resolve_and_store_entity(
                store=store,
                resolver=resolver,
                entity=entity,
                document=document,
                chunk=chunk,
                extraction_run=extraction_run,
                evidence_span=evidence_span,
                stats=stats,
            )
            stats["entities_resolved"] += 1
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(store, run=run, document=document, upsert=node_upsert)
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1
        for recall in output.recall_events:
            stats["recall_events"] += 1
            candidate, case, verdict, alert = build_recall_quality_case(
                recall,
                evidence_span_id=evidence_span.id,
                affected_relationships=max(1, len(output.relationships)),
            )
            if store.write_risk_candidate(candidate):
                _increment(stats, "risk_candidates")
            store.write_risk_case(case)
            store.write_risk_verdict(verdict)
            store.write_risk_alert(alert)
            write_risk_feature_snapshots(
                store=store,
                case=case,
                verdict=verdict,
                stats=stats,
            )
            emit_risk_candidate_event(
                store,
                run=run,
                document=document,
                candidate=candidate,
            )
            emit_risk_case_created_event(
                store,
                run=run,
                document=document,
                risk_case=case,
                verdict=verdict,
            )
            emit_risk_verdict_event(store, run=run, document=document, verdict=verdict)
            emit_risk_alert_event(store, run=run, document=document, alert=alert)
            stats["risk_cases"] += 1
            stats["risk_alerts"] += 1


def process_fda_drug_shortages_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_fda_drug_shortages_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(store, config=config, run=run, document=document, chunks=chunks)
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_fda_drug_shortages(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_fda_drug_shortages_html_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        for entity in output.entities:
            resolve_and_store_entity(
                store=store,
                resolver=resolver,
                entity=entity,
                document=document,
                chunk=chunk,
                extraction_run=extraction_run,
                evidence_span=evidence_span,
                stats=stats,
            )
            stats["entities_resolved"] += 1
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(store, run=run, document=document, upsert=node_upsert)
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1
        for shortage in output.shortage_events:
            stats["shortage_events"] += 1
            candidate, case, verdict, alert = build_shortage_case(
                shortage,
                evidence_span_id=evidence_span.id,
                affected_relationships=max(1, len(output.relationships)),
            )
            if store.write_risk_candidate(candidate):
                _increment(stats, "risk_candidates")
            store.write_risk_case(case)
            store.write_risk_verdict(verdict)
            store.write_risk_alert(alert)
            write_risk_feature_snapshots(
                store=store,
                case=case,
                verdict=verdict,
                stats=stats,
            )
            emit_risk_candidate_event(
                store,
                run=run,
                document=document,
                candidate=candidate,
            )
            emit_risk_case_created_event(
                store,
                run=run,
                document=document,
                risk_case=case,
                verdict=verdict,
            )
            emit_risk_verdict_event(store, run=run, document=document, verdict=verdict)
            emit_risk_alert_event(store, run=run, document=document, alert=alert)
            stats["risk_cases"] += 1
            stats["risk_alerts"] += 1


def process_fda_warning_letters_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_fda_warning_letters_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(store, config=config, run=run, document=document, chunks=chunks)
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_fda_warning_letters(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_fda_warning_letters_xlsx_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        stats["regulatory_events"] += len(output.regulatory_events)
        for entity in output.entities:
            resolve_and_store_entity(
                store=store,
                resolver=resolver,
                entity=entity,
                document=document,
                chunk=chunk,
                extraction_run=extraction_run,
                evidence_span=evidence_span,
                stats=stats,
            )
            stats["entities_resolved"] += 1
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(store, run=run, document=document, upsert=node_upsert)
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1


def process_fda_inspections_dashboard_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_fda_inspections_dashboard_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(store, config=config, run=run, document=document, chunks=chunks)
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_fda_inspections_dashboard(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_fda_inspections_dashboard_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        stats["regulatory_events"] += len(output.regulatory_events)
        for entity in output.entities:
            resolve_and_store_entity(
                store=store,
                resolver=resolver,
                entity=entity,
                document=document,
                chunk=chunk,
                extraction_run=extraction_run,
                evidence_span=evidence_span,
                stats=stats,
            )
            stats["entities_resolved"] += 1
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(store, run=run, document=document, upsert=node_upsert)
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1


def process_gdelt_doc_search_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    del resolver
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_gdelt_doc_search_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(store, config=config, run=run, document=document, chunks=chunks)
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_gdelt_doc_search(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_gdelt_doc_search_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        stats["news_events"] += len(output.news_events)
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(store, run=run, document=document, upsert=node_upsert)
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1


def process_sec_edgar_supplier_filings_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    del resolver
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_sec_edgar_supplier_filings_document(
        document,
        max_records=config.parser.max_chunks,
    )
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(store, config=config, run=run, document=document, chunks=chunks)
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_sec_edgar_supplier_filings(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_sec_edgar_supplier_filings_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        stats["regulatory_events"] += len(output.regulatory_events)
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(store, run=run, document=document, upsert=node_upsert)
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1


def process_reliefweb_reports_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    del resolver
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_reliefweb_reports_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(store, config=config, run=run, document=document, chunks=chunks)
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_reliefweb_reports(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_reliefweb_reports_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        stats["news_events"] += len(output.news_events)
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(store, run=run, document=document, upsert=node_upsert)
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1


def process_worldbank_commodity_prices_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    del resolver
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_worldbank_commodity_prices_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(store, config=config, run=run, document=document, chunks=chunks)
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_worldbank_commodity_prices(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_worldbank_commodity_prices_monthly_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        stats["price_observations"] += len(output.price_observations)
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(store, run=run, document=document, upsert=node_upsert)
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1


def process_eia_energy_prices_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    del resolver
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_eia_energy_prices_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(store, config=config, run=run, document=document, chunks=chunks)
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_eia_energy_prices(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_eia_energy_prices_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        stats["price_observations"] += len(output.price_observations)
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(store, run=run, document=document, upsert=node_upsert)
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1


def process_un_comtrade_trade_flows_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    del resolver
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_un_comtrade_trade_flows_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(store, config=config, run=run, document=document, chunks=chunks)
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_un_comtrade_trade_flows(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_uncomtrade_trade_flows_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        stats["trade_flow_observations"] += len(output.trade_flow_observations)
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(store, run=run, document=document, upsert=node_upsert)
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1


def process_freight_proxy_prices_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    del resolver
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_freight_proxy_prices_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(store, config=config, run=run, document=document, chunks=chunks)
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_freight_proxy_prices(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_nyfed_gscpi_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        stats["logistics_pressure_observations"] += len(output.logistics_pressure_observations)
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(store, run=run, document=document, upsert=node_upsert)
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1


def process_search_trend_signals_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    del resolver
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_search_trend_signals_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(store, config=config, run=run, document=document, chunks=chunks)
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_search_trend_signals(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_gdelt_search_trends_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        stats["trend_signal_observations"] += len(output.trend_signal_observations)
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(store, run=run, document=document, upsert=node_upsert)
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1


def process_gdacs_events_document(
    *,
    store: FileEvidenceStore,
    config: SourceConfig,
    run: SourceRun,
    document: RawDocument,
    extractor: MedicalExtractionAgent,
    model_factory: ModelFactory,
    resolver: EntityResolutionService,
    stats: dict[str, int],
) -> None:
    del resolver
    if not store.write_raw_document(document):
        stats["raw_documents_unchanged"] += 1
        return
    stats["raw_documents_created"] += 1
    emit_raw_document_created_event(store, run=run, document=document)
    chunks = parse_gdacs_events_document(document)
    attach_configured_chunk_embeddings(chunks=chunks, model_factory=model_factory, stats=stats)
    for chunk in chunks:
        store.write_chunk(chunk)
        stats["chunks_created"] += 1
    emit_document_parsed_event(store, config=config, run=run, document=document, chunks=chunks)
    for chunk in chunks:
        evidence_span = evidence_span_from_chunk(document, chunk)
        store.write_evidence_span(evidence_span)
        output = extractor.extract_gdacs_events(
            document,
            chunk,
            evidence_span_id=evidence_span.id,
        )
        extraction_run = ExtractionRun(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            agent_name=extractor.agent_name,
            agent_version=extractor.agent_version,
            model_name=model_factory.configured_model_name,
            prompt_hash="deterministic_gdacs_events_rss_v1",
            input_hash=extraction_input_hash(chunk),
            output_schema="MedicalExtractionOutput",
            status="succeeded",
            finished_at=datetime.now(UTC),
            idempotency_key=f"{document.id}:{chunk.id}:MedicalExtractionOutput:v1",
        )
        attach_extraction_run_id(output, extraction_run)
        extraction_run.validated_output = output.model_dump(mode="json")
        store.write_extraction_run(extraction_run)
        emit_extraction_completed_event(
            store,
            run=run,
            extraction_run=extraction_run,
            evidence_span=evidence_span,
        )
        stats["disaster_events"] += len(output.disaster_events)
        graph = map_extraction_to_graph(document, output)
        for node_upsert in graph.node_upserts:
            store.write_graph_node(node_upsert)
            emit_graph_node_upsert_event(store, run=run, document=document, upsert=node_upsert)
            stats["graph_nodes"] += 1
        for relationship_upsert in graph.relationship_upserts:
            store.write_graph_relationship(relationship_upsert)
            emit_graph_relationship_upsert_event(
                store,
                run=run,
                document=document,
                upsert=relationship_upsert,
            )
            stats["graph_relationships"] += 1


def ingest_openfda_ndc_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()

    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    records = load_fixture_records(fixture_path)
    for record in records[:max_documents]:
        document = raw_document_from_record(
            config=config,
            run=run,
            record=record,
            source_url=config.base_url,
        )
        process_openfda_ndc_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = len(records)
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_openfda_drug_enforcement_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "recall_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
        "risk_cases": 0,
        "risk_alerts": 0,
    }
    records = load_fixture_records(fixture_path)
    for record in records[:max_documents]:
        document = raw_document_from_record(
            config=config,
            run=run,
            record=record,
            source_url=config.base_url,
        )
        process_openfda_drug_enforcement_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = len(records)
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_openfda_device_registrationlisting_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    records = load_fixture_records(fixture_path)
    for record in records[:max_documents]:
        document = raw_document_from_record(
            config=config,
            run=run,
            record=record,
            source_url=config.base_url,
        )
        process_openfda_device_registrationlisting_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = len(records)
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_openfda_device_enforcement_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "recall_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
        "risk_cases": 0,
        "risk_alerts": 0,
    }
    records = load_fixture_records(fixture_path)
    for record in records[:max_documents]:
        document = raw_document_from_record(
            config=config,
            run=run,
            record=record,
            source_url=config.base_url,
        )
        process_openfda_device_enforcement_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = len(records)
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_fda_drug_shortages_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    del max_documents
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "shortage_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
        "risk_cases": 0,
        "risk_alerts": 0,
    }
    document = raw_document_from_text(
        config=config,
        run=run,
        text=fixture_path.read_text(encoding="utf-8"),
        source_url=config.base_url,
        content_type="text/html",
    )
    process_fda_drug_shortages_document(
        store=store,
        config=config,
        run=run,
        document=document,
        extractor=extractor,
        model_factory=model_factory,
        resolver=resolver,
        stats=stats,
    )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = 1
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_fda_warning_letters_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    del max_documents
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "regulatory_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    document = raw_document_from_text(
        config=config,
        run=run,
        text=fixture_path.read_text(encoding="utf-8"),
        source_url=config.base_url,
        content_type="text/csv",
    )
    process_fda_warning_letters_document(
        store=store,
        config=config,
        run=run,
        document=document,
        extractor=extractor,
        model_factory=model_factory,
        resolver=resolver,
        stats=stats,
    )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = 1
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_fda_inspections_dashboard_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    del max_documents
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "regulatory_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    document = raw_document_from_text(
        config=config,
        run=run,
        text=fixture_path.read_text(encoding="utf-8"),
        source_url=config.base_url,
        content_type="text/csv",
    )
    process_fda_inspections_dashboard_document(
        store=store,
        config=config,
        run=run,
        document=document,
        extractor=extractor,
        model_factory=model_factory,
        resolver=resolver,
        stats=stats,
    )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = 1
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_gdelt_doc_search_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    del max_documents
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "news_events": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    document = raw_document_from_text(
        config=config,
        run=run,
        text=fixture_path.read_text(encoding="utf-8"),
        source_url=config.base_url,
        content_type="application/json",
    )
    process_gdelt_doc_search_document(
        store=store,
        config=config,
        run=run,
        document=document,
        extractor=extractor,
        model_factory=model_factory,
        resolver=resolver,
        stats=stats,
    )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = 1
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_sec_edgar_supplier_filings_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    del max_documents
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "regulatory_events": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    document = raw_document_from_text(
        config=config,
        run=run,
        text=fixture_path.read_text(encoding="utf-8"),
        source_url=config.base_url,
        content_type="application/json",
    )
    process_sec_edgar_supplier_filings_document(
        store=store,
        config=config,
        run=run,
        document=document,
        extractor=extractor,
        model_factory=model_factory,
        resolver=resolver,
        stats=stats,
    )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = 1
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_reliefweb_reports_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    del max_documents
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "news_events": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    document = raw_document_from_text(
        config=config,
        run=run,
        text=fixture_path.read_text(encoding="utf-8"),
        source_url=config.base_url,
        content_type="application/json",
    )
    process_reliefweb_reports_document(
        store=store,
        config=config,
        run=run,
        document=document,
        extractor=extractor,
        model_factory=model_factory,
        resolver=resolver,
        stats=stats,
    )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = 1
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_worldbank_commodity_prices_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    del max_documents
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "price_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    document = raw_document_from_text(
        config=config,
        run=run,
        text=fixture_path.read_text(encoding="utf-8"),
        source_url=config.base_url,
        content_type="text/csv",
    )
    process_worldbank_commodity_prices_document(
        store=store,
        config=config,
        run=run,
        document=document,
        extractor=extractor,
        model_factory=model_factory,
        resolver=resolver,
        stats=stats,
    )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = 1
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_eia_energy_prices_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    del max_documents
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "price_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    document = raw_document_from_text(
        config=config,
        run=run,
        text=fixture_path.read_text(encoding="utf-8"),
        source_url=config.base_url,
        content_type="application/json",
    )
    process_eia_energy_prices_document(
        store=store,
        config=config,
        run=run,
        document=document,
        extractor=extractor,
        model_factory=model_factory,
        resolver=resolver,
        stats=stats,
    )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = 1
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_un_comtrade_trade_flows_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    del max_documents
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "trade_flow_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    document = raw_document_from_text(
        config=config,
        run=run,
        text=fixture_path.read_text(encoding="utf-8"),
        source_url=config.base_url,
        content_type="application/json",
    )
    process_un_comtrade_trade_flows_document(
        store=store,
        config=config,
        run=run,
        document=document,
        extractor=extractor,
        model_factory=model_factory,
        resolver=resolver,
        stats=stats,
    )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = 1
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_freight_proxy_prices_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    del max_documents
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "logistics_pressure_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    document = raw_document_from_text(
        config=config,
        run=run,
        text=fixture_path.read_text(encoding="utf-8"),
        source_url=config.base_url,
        content_type="text/csv",
    )
    process_freight_proxy_prices_document(
        store=store,
        config=config,
        run=run,
        document=document,
        extractor=extractor,
        model_factory=model_factory,
        resolver=resolver,
        stats=stats,
    )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = 1
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_search_trend_signals_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    del max_documents
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "trend_signal_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    document = raw_document_from_text(
        config=config,
        run=run,
        text=fixture_path.read_text(encoding="utf-8"),
        source_url=config.base_url,
        content_type="application/json",
    )
    process_search_trend_signals_document(
        store=store,
        config=config,
        run=run,
        document=document,
        extractor=extractor,
        model_factory=model_factory,
        resolver=resolver,
        stats=stats,
    )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = 1
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


def ingest_gdacs_events_fixture(
    *,
    config: SourceConfig,
    fixture_path: Path,
    settings: Settings,
    max_documents: int | None = None,
) -> dict[str, int]:
    del max_documents
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:{fixture_path}:{datetime.now(UTC).isoformat()}",
    )
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "disaster_events": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    document = raw_document_from_text(
        config=config,
        run=run,
        text=fixture_path.read_text(encoding="utf-8"),
        source_url=config.base_url,
        content_type="application/rss+xml",
    )
    process_gdacs_events_document(
        store=store,
        config=config,
        run=run,
        document=document,
        extractor=extractor,
        model_factory=model_factory,
        resolver=resolver,
        stats=stats,
    )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = 1
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)
    return stats


async def fetch_source_sample(
    *,
    config: SourceConfig,
    max_documents: int,
    adapter: SourceAdapter | None = None,
) -> dict[str, object]:
    source_adapter = adapter or adapter_for_source(config)
    run = SourceRun(
        source_id=config.source_id,
        run_type="test",
        status="running",
        idempotency_key=f"test-fetch:{config.source_id}:{datetime.now(UTC).isoformat()}",
    )
    plan = await source_adapter.plan_fetch(config, None, run, max_documents=max_documents)
    records: list[dict[str, object]] = []
    async for payload in source_adapter.fetch(config, plan):
        body = payload.content_bytes or payload.text.encode("utf-8")
        records.append(
            {
                "source_url": payload.source_url,
                "status_code": payload.status_code,
                "content_type": payload.content_type,
                "content_hash": hashlib.sha256(body).hexdigest(),
                "record_keys": sorted((payload.record or {}).keys()),
            }
        )
        if len(records) >= max_documents:
            break
    return {
        "source_id": config.source_id,
        "adapter": config.adapter,
        "planned_requests": len(plan.requests),
        "fetched": len(records),
        "records": records,
    }


LIVE_PROCESSORS_BY_PROFILE: dict[str, DocumentProcessor] = {
    "openfda.drug_ndc.v1": process_openfda_ndc_document,
    "openfda.drug_enforcement.v1": process_openfda_drug_enforcement_document,
    "openfda.device_registrationlisting.v1": process_openfda_device_registrationlisting_document,
    "openfda.device_enforcement.v1": process_openfda_device_enforcement_document,
    "fda.drug_shortages_html.v1": process_fda_drug_shortages_document,
    "fda.warning_letters_xlsx.v1": process_fda_warning_letters_document,
    "fda.inspections_dashboard.v1": process_fda_inspections_dashboard_document,
    "gdelt.doc_search.v1": process_gdelt_doc_search_document,
    "gdacs.events_rss.v1": process_gdacs_events_document,
    "reliefweb.reports.v1": process_reliefweb_reports_document,
    "worldbank.commodity_prices_monthly.v1": process_worldbank_commodity_prices_document,
    "eia.energy_prices.v1": process_eia_energy_prices_document,
    "sec.edgar_supplier_filings.v1": process_sec_edgar_supplier_filings_document,
    "uncomtrade.trade_flows.v1": process_un_comtrade_trade_flows_document,
    "nyfed.gscpi.v1": process_freight_proxy_prices_document,
    "gdelt.search_trends.v1": process_search_trend_signals_document,
}

LIVE_STATS_BY_PROFILE: dict[str, dict[str, int]] = {
    "openfda.drug_ndc.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    },
    "openfda.drug_enforcement.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "recall_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
        "risk_cases": 0,
        "risk_alerts": 0,
    },
    "openfda.device_registrationlisting.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    },
    "openfda.device_enforcement.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "recall_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
        "risk_cases": 0,
        "risk_alerts": 0,
    },
    "fda.drug_shortages_html.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "shortage_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
        "risk_cases": 0,
        "risk_alerts": 0,
    },
    "fda.warning_letters_xlsx.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "regulatory_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    },
    "fda.inspections_dashboard.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "regulatory_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    },
    "gdelt.doc_search.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "news_events": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    },
    "gdacs.events_rss.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "disaster_events": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    },
    "reliefweb.reports.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "news_events": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    },
    "worldbank.commodity_prices_monthly.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "price_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    },
    "eia.energy_prices.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "price_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    },
    "sec.edgar_supplier_filings.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "regulatory_events": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    },
    "uncomtrade.trade_flows.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "trade_flow_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    },
    "nyfed.gscpi.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "logistics_pressure_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    },
    "gdelt.search_trends.v1": {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "trend_signal_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    },
}

SINGLE_DOCUMENT_LIVE_PROFILES = {"fda.drug_shortages_html.v1"}


async def process_live_source_run(
    *,
    config: SourceConfig,
    settings: Settings,
    run: SourceRun,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    processor = LIVE_PROCESSORS_BY_PROFILE.get(config.parser.profile)
    if processor is None:
        raise ValueError(f"Live ingestion not implemented for {config.parser.profile}")
    stats_template = LIVE_STATS_BY_PROFILE.get(config.parser.profile)
    if stats_template is None:
        raise ValueError(f"Live ingestion stats not configured for {config.parser.profile}")

    store = FileEvidenceStore(settings.data_dir)
    current_cursor = (
        _source_cursor_from_snapshot(run.cursor_before)
        if run.cursor_before is not None
        else store.current_source_cursor(config.source_id)
    )
    if run.cursor_before is None:
        run.cursor_before = source_cursor_snapshot(current_cursor)
    run.status = "running"
    run.updated_at = datetime.now(UTC)
    store.write_source_run(run)

    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = dict(stats_template)
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    effective_max_documents = (
        1 if config.parser.profile in SINGLE_DOCUMENT_LIVE_PROFILES else max_documents
    )
    source_adapter = adapter or adapter_for_source(config)
    try:
        plan = await source_adapter.plan_fetch(
            config,
            current_cursor,
            run,
            max_documents=effective_max_documents,
        )
        async for payload in source_adapter.fetch(config, plan):
            payloads.append(payload)
            documents_seen += 1
            document = raw_document_from_payload(config=config, run=run, payload=payload)
            processor(
                store=store,
                config=config,
                run=run,
                document=document,
                extractor=extractor,
                model_factory=model_factory,
                resolver=resolver,
                stats=stats,
            )

        run.status = "succeeded"
        run.finished_at = datetime.now(UTC)
        run.documents_seen = documents_seen
        run.documents_created = stats["raw_documents_created"]
        run.documents_unchanged = stats["raw_documents_unchanged"]
        run.updated_at = datetime.now(UTC)
        _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
        store.write_source_run(run)
        return stats
    except KeyboardInterrupt:
        _mark_source_run_failed(
            store=store,
            run=run,
            stats=stats,
            documents_seen=documents_seen,
            error="KeyboardInterrupt",
            interrupted=True,
        )
        raise
    except Exception as exc:
        _mark_source_run_failed(
            store=store,
            run=run,
            stats=stats,
            documents_seen=documents_seen,
            error=str(exc),
        )
        raise


def _mark_source_run_failed(
    *,
    store: FileEvidenceStore,
    run: SourceRun,
    stats: Mapping[str, int],
    documents_seen: int,
    error: str,
    interrupted: bool = False,
) -> None:
    run.status = "failed"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.error_count = 1
    run.updated_at = datetime.now(UTC)
    run.metadata["error"] = error
    if interrupted:
        run.metadata["interrupted"] = True
    store.write_source_run(run)


async def ingest_openfda_ndc_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_openfda_ndc_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_openfda_drug_enforcement_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "recall_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
        "risk_cases": 0,
        "risk_alerts": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_openfda_drug_enforcement_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_openfda_device_registrationlisting_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_openfda_device_registrationlisting_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_openfda_device_enforcement_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "recall_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
        "risk_cases": 0,
        "risk_alerts": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_openfda_device_enforcement_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_fda_drug_shortages_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    del max_documents
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "shortage_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
        "risk_cases": 0,
        "risk_alerts": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=1)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_fda_drug_shortages_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_fda_warning_letters_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "regulatory_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_fda_warning_letters_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_fda_inspections_dashboard_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "regulatory_events": 0,
        "entities_resolved": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_fda_inspections_dashboard_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_gdelt_doc_search_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "news_events": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_gdelt_doc_search_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_sec_edgar_supplier_filings_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "regulatory_events": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_sec_edgar_supplier_filings_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_reliefweb_reports_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "news_events": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_reliefweb_reports_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_worldbank_commodity_prices_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "price_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_worldbank_commodity_prices_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_eia_energy_prices_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "price_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_eia_energy_prices_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_un_comtrade_trade_flows_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "trade_flow_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_un_comtrade_trade_flows_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_freight_proxy_prices_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "logistics_pressure_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_freight_proxy_prices_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_search_trend_signals_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "trend_signal_observations": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_search_trend_signals_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


async def ingest_gdacs_events_live(
    *,
    config: SourceConfig,
    settings: Settings,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
) -> dict[str, int]:
    store = FileEvidenceStore(settings.data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="running",
        idempotency_key=f"{config.source_id}:live:{datetime.now(UTC).isoformat()}",
    )
    current_cursor = _prepare_run_cursor(store, config, run)
    store.write_source_run(run)
    extractor = MedicalExtractionAgent()
    model_factory = ModelFactory(settings)
    resolver = EntityResolutionService()
    stats = {
        "raw_documents_created": 0,
        "raw_documents_unchanged": 0,
        "chunks_created": 0,
        "disaster_events": 0,
        "graph_nodes": 0,
        "graph_relationships": 0,
    }
    documents_seen = 0
    payloads: list[FetchedPayload] = []
    source_adapter = adapter or adapter_for_source(config)
    plan = await source_adapter.plan_fetch(config, current_cursor, run, max_documents=max_documents)
    async for payload in source_adapter.fetch(config, plan):
        payloads.append(payload)
        documents_seen += 1
        document = raw_document_from_payload(config=config, run=run, payload=payload)
        process_gdacs_events_document(
            store=store,
            config=config,
            run=run,
            document=document,
            extractor=extractor,
            model_factory=model_factory,
            resolver=resolver,
            stats=stats,
        )

    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    run.documents_seen = documents_seen
    run.documents_created = stats["raw_documents_created"]
    run.documents_unchanged = stats["raw_documents_unchanged"]
    run.updated_at = datetime.now(UTC)
    _checkpoint_run_cursor(store, config=config, run=run, payloads=payloads)
    store.write_source_run(run)
    return stats


def evidence_span_from_chunk(document: RawDocument, chunk: DocumentChunk) -> EvidenceSpan:
    quote_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
    return EvidenceSpan(
        raw_document_id=document.id,
        document_chunk_id=chunk.id,
        source_id=document.source_id,
        source_url=document.source_url,
        quote=chunk.text,
        normalized_text=chunk.text.casefold(),
        char_start=0,
        char_end=len(chunk.text),
        confidence=1.0,
        evidence_type="source_record",
        hash=quote_hash,
    )
