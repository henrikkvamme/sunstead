from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

from pydantic import Field

from supply_intel.db.postgres import PostgresConnection
from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.db.sync import sync_local_evidence_to_postgres
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
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.kafka import EventEnvelope, EventProcessingResult, IngestJobPayload
from supply_intel.models.source import SourceConfig, SourceRun
from supply_intel.pipeline import process_live_source_run
from supply_intel.settings import Settings
from supply_intel.sources.adapters.base import SourceAdapter
from supply_intel.sources.registry import find_source_config, load_source_config
from supply_intel.sources.scheduler import source_config_hash

INGEST_WORKER_GROUP = "platform-ingester"
INGEST_WORKER_STAGE = "ingest-live"
INGEST_JOBS_TOPIC = "ingest.jobs"


class IngestJobExecutionSummary(StrictBaseModel):
    source_id: str
    source_run_id: str
    event_id: str
    status: Literal["succeeded", "already_succeeded"]
    stats: dict[str, int] = Field(default_factory=dict)
    postgres_sync: dict[str, object] | None = None
    events_published: int = 0


class IngestWorkerRunSummary(StrictBaseModel):
    requested_messages: int | None = None
    processed_messages: int = Field(default=0, ge=0)
    deadlettered_messages: int = Field(default=0, ge=0)
    committed_messages: int = Field(default=0, ge=0)
    timed_out: bool = False
    results: list[EventProcessingResult] = Field(default_factory=list)
    executions: list[IngestJobExecutionSummary] = Field(default_factory=list)

    @property
    def handled_messages(self) -> int:
        return self.processed_messages + self.deadlettered_messages


async def execute_ingest_job_event(
    *,
    settings: Settings,
    event: EventEnvelope,
    max_documents: int | None = None,
    adapter: SourceAdapter | None = None,
    evidence_backend: Literal["file", "postgres"] = "file",
    postgres_connection: PostgresConnection | None = None,
    producer: EventProducer | None = None,
) -> IngestJobExecutionSummary:
    event = validate_event_payload(event)
    if event.event_type != INGEST_JOBS_TOPIC:
        raise PermanentEventError(
            f"Unsupported ingest worker event type: {event.event_type}",
            error_type="unsupported_ingest_event",
        )

    payload = IngestJobPayload.model_validate(event.payload)
    if event.source.source_id is not None and event.source.source_id != payload.source_id:
        raise PermanentEventError(
            "Ingest job source id does not match envelope source id",
            error_type="source_id_mismatch",
        )

    config = _load_job_source_config(settings, payload.source_id)
    expected_hash = source_config_hash(config)
    if expected_hash != payload.config_hash:
        raise PermanentEventError(
            "Source config hash changed after the ingest job was scheduled",
            error_type="source_config_hash_mismatch",
        )

    run = _source_run_for_job(settings.data_dir, payload)
    if run.run_type != payload.run_type:
        raise PermanentEventError(
            "Ingest job run type does not match the stored source run",
            error_type="source_run_type_mismatch",
        )
    if run.status == "succeeded":
        return IngestJobExecutionSummary(
            source_id=payload.source_id,
            source_run_id=str(payload.source_run_id),
            event_id=str(event.event_id),
            status="already_succeeded",
        )

    store = FileEvidenceStore(settings.data_dir)
    event_ids_before = _event_ids(store)
    stats = await process_live_source_run(
        config=config,
        settings=settings,
        run=run,
        max_documents=max_documents,
        adapter=adapter,
    )
    postgres_sync: dict[str, object] | None = None
    if evidence_backend == "postgres":
        sync_summary = await sync_local_evidence_to_postgres(
            settings=settings,
            configs=[config],
            connection=postgres_connection,
        )
        postgres_sync = sync_summary.model_dump(mode="json")
    events_published = 0
    if producer is not None:
        events_published = await publish_events_by_ids(
            store=store,
            producer=producer,
            event_ids=_new_event_ids(store, event_ids_before),
        )
    return IngestJobExecutionSummary(
        source_id=payload.source_id,
        source_run_id=str(payload.source_run_id),
        event_id=str(event.event_id),
        status="succeeded",
        stats=stats,
        postgres_sync=postgres_sync,
        events_published=events_published,
    )


async def run_ingest_worker_once(
    *,
    settings: Settings,
    max_documents: int | None = None,
    consumer_client: KafkaConsumerClient | None = None,
    producer_client: KafkaProducerClient | None = None,
    adapter: SourceAdapter | None = None,
    evidence_backend: Literal["file", "postgres"] = "file",
    postgres_connection: PostgresConnection | None = None,
) -> EventProcessingResult:
    summary = await run_ingest_worker(
        settings=settings,
        max_messages=1,
        max_documents=max_documents,
        consumer_client=consumer_client,
        producer_client=producer_client,
        adapter=adapter,
        evidence_backend=evidence_backend,
        postgres_connection=postgres_connection,
    )
    if not summary.results:
        raise RuntimeError("Ingest worker exited before processing a message.")
    return summary.results[0]


async def run_ingest_worker(
    *,
    settings: Settings,
    max_messages: int | None = None,
    max_documents: int | None = None,
    idle_timeout_seconds: float | None = None,
    consumer_client: KafkaConsumerClient | None = None,
    producer_client: KafkaProducerClient | None = None,
    adapter: SourceAdapter | None = None,
    evidence_backend: Literal["file", "postgres"] = "file",
    postgres_connection: PostgresConnection | None = None,
) -> IngestWorkerRunSummary:
    if max_messages is not None and max_messages < 1:
        raise ValueError("max_messages must be greater than zero when provided.")

    direct_consumer: DirectKafkaConsumerClient | None = None
    direct_producer: DirectKafkaProducerClient | None = None
    if consumer_client is None:
        direct_consumer = DirectKafkaConsumerClient(
            settings,
            topics=[INGEST_JOBS_TOPIC],
            group_id=INGEST_WORKER_GROUP,
        )
        consumer_client = direct_consumer
        await direct_consumer.start()
    if producer_client is None:
        direct_producer = DirectKafkaProducerClient(settings)
        producer_client = direct_producer
        await direct_producer.start()

    producer = EventProducer(producer_client)
    consumer = EventConsumer(
        consumer_client,
        producer,
        consumer_group=INGEST_WORKER_GROUP,
        stage=INGEST_WORKER_STAGE,
    )

    async def handler(received: EventEnvelope) -> None:
        execution = await execute_ingest_job_event(
            settings=settings,
            event=received,
            max_documents=max_documents,
            adapter=adapter,
            evidence_backend=evidence_backend,
            postgres_connection=postgres_connection,
            producer=producer,
        )
        summary.executions.append(execution)

    summary = IngestWorkerRunSummary(requested_messages=max_messages)
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
        if direct_consumer is not None:
            await direct_consumer.stop()
        if direct_producer is not None:
            await direct_producer.stop()


async def _process_one_with_optional_timeout(
    consumer: EventConsumer,
    handler: EventHandler,
    *,
    idle_timeout_seconds: float | None,
) -> EventProcessingResult:
    if idle_timeout_seconds is None:
        return await consumer.process_one(handler)
    return await asyncio.wait_for(consumer.process_one(handler), timeout=idle_timeout_seconds)


def _load_job_source_config(settings: Settings, source_id: str) -> SourceConfig:
    try:
        return load_source_config(find_source_config(source_id, settings.source_dir))
    except (FileNotFoundError, ValueError) as exc:
        raise PermanentEventError(
            f"Cannot load source config for ingest job source {source_id}: {exc}",
            error_type="source_config_unavailable",
        ) from exc


def _source_run_for_job(data_dir: Path, payload: IngestJobPayload) -> SourceRun:
    store = FileEvidenceStore(data_dir)
    for row in reversed(store.read_collection("source_runs")):
        if str(row.get("id")) != str(payload.source_run_id):
            continue
        run = SourceRun.model_validate(row)
        if run.source_id != payload.source_id:
            raise PermanentEventError(
                "Ingest job source id does not match the stored source run",
                error_type="source_run_source_mismatch",
            )
        return run
    raise PermanentEventError(
        f"Scheduled source run not found: {payload.source_run_id}",
        error_type="source_run_missing",
    )


def _event_ids(store: FileEvidenceStore) -> set[str]:
    return {str(row.get("event_id")) for row in store.read_collection("events")}


def _new_event_ids(store: FileEvidenceStore, previous: set[str]) -> list[str]:
    return [
        str(row.get("event_id"))
        for row in store.read_collection("events")
        if str(row.get("event_id")) not in previous
    ]
