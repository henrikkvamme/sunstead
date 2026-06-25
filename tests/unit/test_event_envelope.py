from datetime import UTC, datetime
from uuid import uuid4

from supply_intel.events.envelope import build_event
from supply_intel.models.kafka import RawDocumentCreatedPayload


def test_event_envelope_contains_required_trace_and_idempotency() -> None:
    source_run_id = uuid4()
    raw_document_id = uuid4()
    payload = RawDocumentCreatedPayload(
        source_id="openfda_drug_ndc",
        source_run_id=source_run_id,
        raw_document_id=raw_document_id,
        source_url="https://api.fda.gov/drug/ndc.json",
        content_hash="hash-1",
        content_type="application/json",
        fetched_at=datetime.now(UTC),
    )
    event = build_event(
        event_type="ingest.raw_document_created",
        service="ingester",
        source_id="openfda_drug_ndc",
        idempotency_key="openfda_drug_ndc:0002-8215",
        payload=payload.model_dump(mode="json"),
    )

    assert event.schema_version == 1
    assert event.payload["schema_version"] == 1
    assert event.payload["raw_document_id"] == str(raw_document_id)
    assert event.source.source_id == "openfda_drug_ndc"
    assert event.idempotency_key == "openfda_drug_ndc:0002-8215"
    assert event.trace.trace_id is not None
