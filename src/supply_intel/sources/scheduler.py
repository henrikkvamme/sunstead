from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.events.envelope import build_event
from supply_intel.events.kafka_clients import DirectKafkaProducerClient
from supply_intel.events.producer import EventProducer, KafkaProducerClient
from supply_intel.models.base import StrictBaseModel
from supply_intel.models.infra import OperationalMetric
from supply_intel.models.kafka import EventEnvelope, IngestJobPayload, TraceMetadata
from supply_intel.models.source import SourceConfig, SourceRun
from supply_intel.settings import Settings
from supply_intel.sources.cursors import source_cursor_snapshot
from supply_intel.sources.registry import load_all_source_configs


class SchedulerSummary(StrictBaseModel):
    data_dir: str
    scheduled: int
    skipped: int
    source_run_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    dry_run: bool = False


class SchedulerKafkaPublishSummary(StrictBaseModel):
    topic: str = "ingest.jobs"
    published: int
    event_ids: list[str] = Field(default_factory=list)
    metrics_recorded: int = 0


def source_config_hash(config: SourceConfig) -> str:
    payload = json.dumps(config.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_local_scheduler(
    *,
    settings: Settings,
    source_dir: Path | None = None,
    source_ids: set[str] | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> SchedulerSummary:
    configs = load_all_source_configs(source_dir or settings.source_dir)
    selected = [config for config in configs if config.enabled]
    if source_ids is not None:
        selected = [config for config in selected if config.source_id in source_ids]
    if limit is not None:
        selected = selected[:limit]

    skipped = len(configs) - len(selected)
    if dry_run:
        return SchedulerSummary(
            data_dir=str(settings.data_dir),
            scheduled=len(selected),
            skipped=skipped,
            dry_run=True,
        )

    store = FileEvidenceStore(settings.data_dir)
    source_run_ids: list[str] = []
    event_ids: list[str] = []
    requested_at = datetime.now(UTC)
    for config in selected:
        current_cursor = store.current_source_cursor(config.source_id)
        cursor = source_cursor_snapshot(current_cursor)
        run = SourceRun(
            source_id=config.source_id,
            run_type="scheduled",
            status="pending",
            cursor_before=cursor,
            idempotency_key=f"scheduler:{config.source_id}:{requested_at.isoformat()}",
        )
        store.write_source_run(run)
        source_run_ids.append(str(run.id))
        payload = IngestJobPayload(
            source_id=config.source_id,
            source_run_id=run.id,
            run_type=run.run_type,
            cursor=cursor,
            config_hash=source_config_hash(config),
            requested_at=requested_at,
        )
        event = build_event(
            event_type="ingest.jobs",
            service="scheduler",
            source_id=config.source_id,
            payload=payload.model_dump(mode="json"),
            idempotency_key=f"ingest.jobs:{config.source_id}:{run.id}",
            correlation_id=run.correlation_id,
            trace=TraceMetadata(source_run_id=run.id),
        )
        store.write_event(event)
        event_ids.append(str(event.event_id))

    return SchedulerSummary(
        data_dir=str(settings.data_dir),
        scheduled=len(selected),
        skipped=skipped,
        source_run_ids=source_run_ids,
        event_ids=event_ids,
    )


async def publish_scheduled_events_to_kafka(
    *,
    settings: Settings,
    event_ids: list[str],
    producer_client: KafkaProducerClient | None = None,
) -> SchedulerKafkaPublishSummary:
    events = _scheduled_events_for_ids(settings.data_dir, event_ids)
    store = FileEvidenceStore(settings.data_dir)
    if producer_client is not None:
        return await _publish_scheduled_events(events, producer_client, store=store)

    direct_client = DirectKafkaProducerClient(settings)
    await direct_client.start()
    try:
        return await _publish_scheduled_events(events, direct_client, store=store)
    finally:
        await direct_client.stop()


async def _publish_scheduled_events(
    events: list[EventEnvelope],
    producer_client: KafkaProducerClient,
    *,
    store: FileEvidenceStore,
) -> SchedulerKafkaPublishSummary:
    producer = EventProducer(
        producer_client,
        allowed_topics={"ingest.jobs", "ops.metrics"},
        emit_metrics=True,
    )
    published: list[str] = []
    metrics_recorded = 0
    for event in events:
        if event.event_type != "ingest.jobs":
            raise ValueError(f"Refusing to publish non-scheduler event: {event.event_type}")
        key = str(event.payload.get("source_run_id") or event.trace.source_run_id)
        await producer.produce("ingest.jobs", event, key=key)
        if store.write_operational_metric(_event_produced_metric(event, topic="ingest.jobs")):
            metrics_recorded += 1
        published.append(str(event.event_id))
    return SchedulerKafkaPublishSummary(
        published=len(published),
        event_ids=published,
        metrics_recorded=metrics_recorded,
    )


def _event_produced_metric(event: EventEnvelope, *, topic: str) -> OperationalMetric:
    idempotency_key = f"ops.metrics:events_produced_total:{topic}:{event.event_id}"
    return OperationalMetric(
        metric_name="events_produced_total",
        metric_value=1,
        service=event.source.service,
        source_id=event.source.source_id,
        topic=topic,
        unit="count",
        idempotency_key=idempotency_key,
        correlation_id=event.correlation_id,
        causation_id=event.event_id,
        observed_at=datetime.now(UTC),
        tags={"event_type": event.event_type},
    )


def _scheduled_events_for_ids(data_dir: Path, event_ids: list[str]) -> list[EventEnvelope]:
    requested = set(event_ids)
    events: list[EventEnvelope] = []
    found: set[str] = set()
    store = FileEvidenceStore(data_dir)
    for row in store.read_collection("events"):
        event_id = str(row.get("event_id", ""))
        if event_id not in requested:
            continue
        event = EventEnvelope.model_validate(row)
        events.append(event)
        found.add(event_id)
    missing = sorted(requested - found)
    if missing:
        raise ValueError(f"Scheduled events not found in local audit store: {missing}")
    return events
