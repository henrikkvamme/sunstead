import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from typer.testing import CliRunner

from supply_intel.cli import app
from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.events.envelope import build_event, deserialize_event, serialize_event
from supply_intel.extraction.replay import run_extractor_consumer, run_local_extractor
from supply_intel.models.documents import DocumentChunk
from supply_intel.models.extraction import MedicalExtractionOutput
from supply_intel.models.kafka import DocumentParsedPayload, EventEnvelope
from supply_intel.models.source import RawDocument, SourceConfig, SourceRun
from supply_intel.pipeline import (
    load_fixture_records,
    raw_document_from_record,
    raw_document_from_text,
)
from supply_intel.settings import Settings
from supply_intel.sources.parsers.eia_energy import parse_eia_energy_prices_document
from supply_intel.sources.parsers.fda_inspections import parse_fda_inspections_dashboard_document
from supply_intel.sources.parsers.fda_warning_letters import parse_fda_warning_letters_document
from supply_intel.sources.parsers.freight_proxy import parse_freight_proxy_prices_document
from supply_intel.sources.parsers.gdacs import parse_gdacs_events_document
from supply_intel.sources.parsers.gdelt_doc import parse_gdelt_doc_search_document
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
from supply_intel.sources.registry import load_source_config

EXPECTED_WARNING_LETTER_ROWS = 2
EXPECTED_INSPECTION_ROWS = 3
EXPECTED_GDELT_ARTICLES = 2
EXPECTED_GDACS_EVENTS = 2
EXPECTED_RELIEFWEB_REPORTS = 2
EXPECTED_WORLDBANK_PRICE_OBSERVATIONS = 3
EXPECTED_EIA_PRICE_OBSERVATIONS = 3
EXPECTED_SEC_FILINGS = 3
EXPECTED_UN_COMTRADE_TRADE_FLOWS = 2
EXPECTED_FREIGHT_PROXY_OBSERVATIONS = 1
EXPECTED_SEARCH_TREND_OBSERVATIONS = 2
EXTRACTOR_CONSUMER_MESSAGES = 1


@dataclass
class FakeMessage:
    topic: str
    key: bytes | None
    value: bytes | None


class FakeConsumerClient:
    def __init__(self, messages: list[FakeMessage]) -> None:
        self.messages = messages
        self.commits = 0

    async def getone(self) -> FakeMessage:
        return self.messages.pop(0)

    async def commit(self) -> None:
        self.commits += 1


class FakeProducerClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, bytes | None, list[tuple[str, bytes]] | None]] = []

    async def send_and_wait(
        self,
        topic: str,
        value: bytes,
        *,
        key: bytes | None = None,
        headers: list[tuple[str, bytes]] | None = None,
    ) -> object:
        self.sent.append((topic, value, key, headers))
        return {"topic": topic}


def test_local_extractor_replays_parsed_ndc_chunks_idempotently(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_parsed_source(
        tmp_path,
        config=load_source_config(Path("sources/openfda_drug_ndc.yaml")),
        fixture_path=Path("tests/fixtures/sources/openfda_drug_ndc/success.json"),
        parser=parse_openfda_ndc_document,
    )

    first = run_local_extractor(settings=settings, source_id="openfda_drug_ndc")
    second = run_local_extractor(settings=settings, source_id="openfda_drug_ndc")

    assert first.raw_documents_scanned == 1
    assert first.chunks_scanned == 1
    assert first.chunks_extracted == 1
    assert first.evidence_spans_created == 1
    assert first.extraction_runs_created == 1
    assert first.extraction_runs_existing == 0
    assert first.events_emitted == 1
    assert second.extraction_runs_created == 0
    assert second.extraction_runs_existing == 1
    assert second.evidence_spans_created == 0
    assert second.events_emitted == 0

    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    evidence_spans = _read_jsonl(tmp_path / "evidence_spans.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")
    assert len(extraction_runs) == 1
    assert len(evidence_spans) == 1
    assert len(events) == 1
    assert events[0]["event_type"] == "ingest.extraction_completed"
    assert events[0]["payload"]["extraction_run_id"] == extraction_runs[0]["id"]
    assert events[0]["payload"]["evidence_span_ids"] == [evidence_spans[0]["id"]]

    output = extraction_runs[0]["validated_output"]
    entity_refs = [ref for entity in output["entities"] for ref in entity["evidence"]]
    assert entity_refs
    assert all(ref["extraction_run_id"] == extraction_runs[0]["id"] for ref in entity_refs)


async def test_extractor_consumer_processes_document_parsed_event_and_commits(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_parsed_source(
        tmp_path,
        config=load_source_config(Path("sources/openfda_drug_ndc.yaml")),
        fixture_path=Path("tests/fixtures/sources/openfda_drug_ndc/success.json"),
        parser=parse_openfda_ndc_document,
    )
    event = _document_parsed_event_from_store(tmp_path)
    consumer = FakeConsumerClient([_fake_message(event)])
    producer = FakeProducerClient()

    summary = await run_extractor_consumer(
        settings=settings,
        max_messages=EXTRACTOR_CONSUMER_MESSAGES,
        consumer_client=consumer,
        producer_client=producer,
    )

    assert summary.processed_messages == EXTRACTOR_CONSUMER_MESSAGES
    assert summary.deadlettered_messages == 0
    assert summary.committed_messages == EXTRACTOR_CONSUMER_MESSAGES
    assert consumer.commits == EXTRACTOR_CONSUMER_MESSAGES
    assert [topic for topic, _, _, _ in producer.sent] == ["ingest.extraction_completed"]
    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")
    assert len(extraction_runs) == 1
    assert extraction_runs[0]["status"] == "succeeded"
    assert events[-1]["event_type"] == "ingest.extraction_completed"


async def test_extractor_consumer_deadletters_missing_chunk(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_parsed_source(
        tmp_path,
        config=load_source_config(Path("sources/openfda_drug_ndc.yaml")),
        fixture_path=Path("tests/fixtures/sources/openfda_drug_ndc/success.json"),
        parser=parse_openfda_ndc_document,
    )
    event = _document_parsed_event_from_store(
        tmp_path,
        document_chunk_ids=[uuid4()],
    )
    consumer = FakeConsumerClient([_fake_message(event)])
    producer = FakeProducerClient()

    summary = await run_extractor_consumer(
        settings=settings,
        max_messages=EXTRACTOR_CONSUMER_MESSAGES,
        consumer_client=consumer,
        producer_client=producer,
    )

    assert summary.processed_messages == 0
    assert summary.deadlettered_messages == EXTRACTOR_CONSUMER_MESSAGES
    assert summary.committed_messages == EXTRACTOR_CONSUMER_MESSAGES
    assert consumer.commits == EXTRACTOR_CONSUMER_MESSAGES
    topic, value, key, headers = producer.sent[0]
    assert topic == "ingest.deadletter"
    assert key == b"document-parsed"
    deadletter = deserialize_event(value)
    assert deadletter.payload["error_type"] == "document_chunk_missing"
    assert deadletter.payload["original_topic"] == "ingest.document_parsed"
    assert headers is not None


def test_run_extractor_cli_requires_consume_for_kafka_options() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["run-extractor", "--max-messages", "1"])

    assert result.exit_code != 0
    assert "--consume-kafka" in result.output


def test_local_extractor_replays_enforcement_recall_profile(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_parsed_source(
        tmp_path,
        config=load_source_config(Path("sources/openfda_drug_enforcement.yaml")),
        fixture_path=Path("tests/fixtures/sources/openfda_drug_enforcement/success.json"),
        parser=parse_openfda_drug_enforcement_document,
    )

    summary = run_local_extractor(settings=settings, source_id="openfda_drug_enforcement")

    assert summary.extraction_runs_created == 1
    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    output = extraction_runs[0]["validated_output"]
    assert len(output["recall_events"]) == 1
    assert (
        output["recall_events"][0]["evidence"][0]["extraction_run_id"] == extraction_runs[0]["id"]
    )


def test_local_extractor_replays_warning_letter_profile(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_text_source(
        tmp_path,
        config=load_source_config(Path("sources/fda_warning_letters.yaml")),
        fixture_path=Path("tests/fixtures/sources/fda_warning_letters/success.csv"),
        content_type="text/csv",
        parser=parse_fda_warning_letters_document,
    )

    summary = run_local_extractor(settings=settings, source_id="fda_warning_letters")

    assert summary.chunks_scanned == EXPECTED_WARNING_LETTER_ROWS
    assert summary.extraction_runs_created == EXPECTED_WARNING_LETTER_ROWS
    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    event_refs = [
        ref
        for run in extraction_runs
        for event in run["validated_output"]["regulatory_events"]
        for ref in event["evidence"]
    ]
    assert event_refs
    assert all(ref["extraction_run_id"] for ref in event_refs)


def test_local_extractor_replays_inspections_dashboard_profile(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_text_source(
        tmp_path,
        config=load_source_config(Path("sources/fda_inspections_dashboard.yaml")),
        fixture_path=Path("tests/fixtures/sources/fda_inspections_dashboard/success.csv"),
        content_type="text/csv",
        parser=parse_fda_inspections_dashboard_document,
    )

    summary = run_local_extractor(settings=settings, source_id="fda_inspections_dashboard")

    assert summary.chunks_scanned == EXPECTED_INSPECTION_ROWS
    assert summary.extraction_runs_created == EXPECTED_INSPECTION_ROWS
    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    event_types = {
        event["event_type"]
        for run in extraction_runs
        for event in run["validated_output"]["regulatory_events"]
    }
    assert event_types == {
        "fda_inspection_classification",
        "fda_inspection_citation",
        "fda_published_483",
    }


def test_local_extractor_replays_gdelt_doc_search_profile(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_text_source(
        tmp_path,
        config=load_source_config(Path("sources/gdelt_doc_search.yaml")),
        fixture_path=Path("tests/fixtures/sources/gdelt_doc_search/success.json"),
        content_type="application/json",
        parser=parse_gdelt_doc_search_document,
    )

    summary = run_local_extractor(settings=settings, source_id="gdelt_doc_search")

    assert summary.chunks_scanned == EXPECTED_GDELT_ARTICLES
    assert summary.extraction_runs_created == EXPECTED_GDELT_ARTICLES
    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    assert {
        event["event_status"]
        for run in extraction_runs
        for event in run["validated_output"]["news_events"]
    } == {"unverified"}


def test_local_extractor_replays_gdacs_events_profile(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_text_source(
        tmp_path,
        config=load_source_config(Path("sources/gdacs_events.yaml")),
        fixture_path=Path("tests/fixtures/sources/gdacs_events/success.xml"),
        content_type="application/rss+xml",
        parser=parse_gdacs_events_document,
    )

    summary = run_local_extractor(settings=settings, source_id="gdacs_events")

    assert summary.chunks_scanned == EXPECTED_GDACS_EVENTS
    assert summary.extraction_runs_created == EXPECTED_GDACS_EVENTS
    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    disaster_events = [
        event for run in extraction_runs for event in run["validated_output"]["disaster_events"]
    ]
    assert {event["disaster_type"] for event in disaster_events} == {
        "earthquake",
        "tropical_cyclone",
    }
    assert {event["alert_level"] for event in disaster_events} == {"Green", "Orange"}
    assert all(event["evidence"][0]["extraction_run_id"] for event in disaster_events)


def test_local_extractor_replays_reliefweb_reports_profile(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_text_source(
        tmp_path,
        config=load_source_config(Path("sources/reliefweb_reports.yaml")),
        fixture_path=Path("tests/fixtures/sources/reliefweb_reports/success.json"),
        content_type="application/json",
        parser=parse_reliefweb_reports_document,
    )

    summary = run_local_extractor(settings=settings, source_id="reliefweb_reports")

    assert summary.chunks_scanned == EXPECTED_RELIEFWEB_REPORTS
    assert summary.extraction_runs_created == EXPECTED_RELIEFWEB_REPORTS
    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    news_events = [
        event for run in extraction_runs for event in run["validated_output"]["news_events"]
    ]
    assert {event["event_status"] for event in news_events} == {"unverified"}
    assert {event["attributes"]["reliefweb_id"] for event in news_events} == {
        "4110001",
        "4110002",
    }
    assert all(event["evidence"][0]["extraction_run_id"] for event in news_events)


def test_local_extractor_replays_worldbank_commodity_prices_profile(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_text_source(
        tmp_path,
        config=load_source_config(Path("sources/worldbank_commodity_prices.yaml")),
        fixture_path=Path("tests/fixtures/sources/worldbank_commodity_prices/success.csv"),
        content_type="text/csv",
        parser=parse_worldbank_commodity_prices_document,
    )

    summary = run_local_extractor(settings=settings, source_id="worldbank_commodity_prices")

    assert summary.chunks_scanned == EXPECTED_WORLDBANK_PRICE_OBSERVATIONS
    assert summary.extraction_runs_created == EXPECTED_WORLDBANK_PRICE_OBSERVATIONS
    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    observations = [
        observation
        for run in extraction_runs
        for observation in run["validated_output"]["price_observations"]
    ]
    assert {observation["commodity_name"] for observation in observations} == {
        "Crude oil, Brent",
        "DAP",
        "Natural gas, US",
    }
    assert {observation["currency"] for observation in observations} == {"USD"}
    assert all(observation["evidence"][0]["extraction_run_id"] for observation in observations)


def test_local_extractor_replays_eia_energy_prices_profile(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_text_source(
        tmp_path,
        config=load_source_config(Path("sources/eia_energy_prices.yaml")),
        fixture_path=Path("tests/fixtures/sources/eia_energy_prices/success.json"),
        content_type="application/json",
        parser=parse_eia_energy_prices_document,
    )

    summary = run_local_extractor(settings=settings, source_id="eia_energy_prices")

    assert summary.chunks_scanned == EXPECTED_EIA_PRICE_OBSERVATIONS
    assert summary.extraction_runs_created == EXPECTED_EIA_PRICE_OBSERVATIONS
    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    observations = [
        observation
        for run in extraction_runs
        for observation in run["validated_output"]["price_observations"]
    ]
    assert {observation["commodity_name"] for observation in observations} == {
        "No 2 Diesel, U.S.",
    }
    assert {observation["currency"] for observation in observations} == {"USD"}
    assert {observation["unit"] for observation in observations} == {"USD/gal"}
    assert all(observation["evidence"][0]["extraction_run_id"] for observation in observations)


def test_local_extractor_replays_sec_edgar_supplier_filings_profile(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_text_source(
        tmp_path,
        config=load_source_config(Path("sources/sec_edgar_supplier_filings.yaml")),
        fixture_path=Path("tests/fixtures/sources/sec_edgar_supplier_filings/success.json"),
        content_type="application/json",
        parser=parse_sec_edgar_supplier_filings_document,
    )

    summary = run_local_extractor(settings=settings, source_id="sec_edgar_supplier_filings")

    assert summary.chunks_scanned == EXPECTED_SEC_FILINGS
    assert summary.extraction_runs_created == EXPECTED_SEC_FILINGS
    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    regulatory_events = [
        event for run in extraction_runs for event in run["validated_output"]["regulatory_events"]
    ]
    assert {event["attributes"]["form"] for event in regulatory_events} == {
        "10-K",
        "10-Q",
        "8-K",
    }
    assert {event["agency"] for event in regulatory_events} == {"SEC"}
    assert all(event["evidence"][0]["extraction_run_id"] for event in regulatory_events)


def test_local_extractor_replays_un_comtrade_trade_flows_profile(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_text_source(
        tmp_path,
        config=load_source_config(Path("sources/un_comtrade_trade_flows.yaml")),
        fixture_path=Path("tests/fixtures/sources/un_comtrade_trade_flows/success.json"),
        content_type="application/json",
        parser=parse_un_comtrade_trade_flows_document,
    )

    summary = run_local_extractor(settings=settings, source_id="un_comtrade_trade_flows")

    assert summary.chunks_scanned == EXPECTED_UN_COMTRADE_TRADE_FLOWS
    assert summary.extraction_runs_created == EXPECTED_UN_COMTRADE_TRADE_FLOWS
    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    observations = [
        observation
        for run in extraction_runs
        for observation in run["validated_output"]["trade_flow_observations"]
    ]
    assert {observation["commodity_code"] for observation in observations} == {"3004"}
    assert {observation["reporter_name"] for observation in observations} == {"USA"}
    assert {observation["flow"] for observation in observations} == {"Import"}
    assert all(observation["evidence"][0]["extraction_run_id"] for observation in observations)


def test_local_extractor_replays_freight_proxy_prices_profile(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_text_source(
        tmp_path,
        config=load_source_config(Path("sources/freight_proxy_prices.yaml")),
        fixture_path=Path("tests/fixtures/sources/freight_proxy_prices/success.csv"),
        content_type="text/csv",
        parser=parse_freight_proxy_prices_document,
    )

    summary = run_local_extractor(settings=settings, source_id="freight_proxy_prices")

    assert summary.chunks_scanned == EXPECTED_FREIGHT_PROXY_OBSERVATIONS
    assert summary.extraction_runs_created == EXPECTED_FREIGHT_PROXY_OBSERVATIONS
    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    observations = [
        observation
        for run in extraction_runs
        for observation in run["validated_output"]["logistics_pressure_observations"]
    ]
    assert {observation["index_name"] for observation in observations} == {
        "New York Fed Global Supply Chain Pressure Index",
    }
    assert {observation["value"] for observation in observations} == {0.452}
    assert all(observation["evidence"][0]["extraction_run_id"] for observation in observations)


def test_local_extractor_replays_search_trend_signals_profile(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_text_source(
        tmp_path,
        config=load_source_config(Path("sources/search_trend_signals.yaml")),
        fixture_path=Path("tests/fixtures/sources/search_trend_signals/success.json"),
        content_type="application/json",
        parser=parse_search_trend_signals_document,
    )

    summary = run_local_extractor(settings=settings, source_id="search_trend_signals")

    assert summary.chunks_scanned == EXPECTED_SEARCH_TREND_OBSERVATIONS
    assert summary.extraction_runs_created == EXPECTED_SEARCH_TREND_OBSERVATIONS
    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    observations = [
        observation
        for run in extraction_runs
        for observation in run["validated_output"]["trend_signal_observations"]
    ]
    assert {observation["signal_name"] for observation in observations} == {
        "GDELT DOC news volume trend",
    }
    assert {observation["value"] for observation in observations} == {0.72, 1.31}
    assert {observation["unit"] for observation in observations} == {"normalized_news_volume"}
    assert all(observation["evidence"][0]["extraction_run_id"] for observation in observations)


def test_local_extractor_persists_failed_extraction_idempotently(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    _seed_parsed_source(
        tmp_path,
        config=load_source_config(Path("sources/openfda_drug_ndc.yaml")),
        fixture_path=Path("tests/fixtures/sources/openfda_drug_ndc/success.json"),
        parser=parse_openfda_ndc_document,
    )
    extractor = FailingExtractor()

    first = run_local_extractor(
        settings=settings,
        source_id="openfda_drug_ndc",
        extractor=extractor,
    )
    second = run_local_extractor(
        settings=settings,
        source_id="openfda_drug_ndc",
        extractor=extractor,
    )

    assert extractor.calls == 1
    assert first.chunks_extracted == 0
    assert first.chunks_failed == 1
    assert first.extraction_runs_created == 0
    assert first.extraction_failures_created == 1
    assert first.ingestion_errors_created == 1
    assert first.events_emitted == 1
    assert second.extraction_failures_created == 0
    assert second.extraction_failures_existing == 1
    assert second.ingestion_errors_created == 0
    assert second.events_emitted == 0

    extraction_runs = _read_jsonl(tmp_path / "extraction_runs.jsonl")
    ingestion_errors = _read_jsonl(tmp_path / "ingestion_errors.jsonl")
    events = _read_jsonl(tmp_path / "events.jsonl")
    assert len(extraction_runs) == 1
    assert extraction_runs[0]["status"] == "failed"
    assert extraction_runs[0]["validated_output"] is None
    assert extraction_runs[0]["raw_output"]["error_type"] == "RuntimeError"
    assert "synthetic extraction failure" in extraction_runs[0]["error"]
    assert len(ingestion_errors) == 1
    assert ingestion_errors[0]["stage"] == "extractor"
    assert ingestion_errors[0]["details"]["extraction_run_id"] == extraction_runs[0]["id"]
    assert len(events) == 1
    assert events[0]["event_type"] == "ingest.extraction_completed"
    assert events[0]["payload"]["status"] == "failed"
    assert events[0]["payload"]["extraction_run_id"] == extraction_runs[0]["id"]


class FailingExtractor:
    agent_name = "MedicalExtractionAgent"
    agent_version = "0.1.0"

    def __init__(self) -> None:
        self.calls = 0

    def extract_openfda_ndc(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        self.calls += 1
        raise RuntimeError("synthetic extraction failure")

    def extract_openfda_drug_enforcement(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")

    def extract_openfda_device_registrationlisting(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")

    def extract_openfda_device_enforcement(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")

    def extract_fda_drug_shortages(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")

    def extract_fda_warning_letters(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")

    def extract_fda_inspections_dashboard(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")

    def extract_gdelt_doc_search(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")

    def extract_gdacs_events(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")

    def extract_reliefweb_reports(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")

    def extract_worldbank_commodity_prices(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")

    def extract_eia_energy_prices(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")

    def extract_sec_edgar_supplier_filings(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")

    def extract_un_comtrade_trade_flows(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")

    def extract_freight_proxy_prices(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")

    def extract_search_trend_signals(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        del document, chunk, evidence_span_id
        raise RuntimeError("synthetic extraction failure")


def _seed_parsed_source(
    data_dir: Path,
    *,
    config: SourceConfig,
    fixture_path: Path,
    parser: Callable[[RawDocument], list[DocumentChunk]],
) -> None:
    store = FileEvidenceStore(data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="succeeded",
        idempotency_key=f"seed:{config.source_id}",
    )
    store.write_source_run(run)
    document = raw_document_from_record(
        config=config,
        run=run,
        record=load_fixture_records(fixture_path)[0],
        source_url=config.base_url,
    )
    assert store.write_raw_document(document)
    for chunk in parser(document):
        store.write_chunk(chunk)


def _seed_text_source(
    data_dir: Path,
    *,
    config: SourceConfig,
    fixture_path: Path,
    content_type: str,
    parser: Callable[[RawDocument], list[DocumentChunk]],
) -> None:
    store = FileEvidenceStore(data_dir)
    run = SourceRun(
        source_id=config.source_id,
        run_type="manual",
        status="succeeded",
        idempotency_key=f"seed:{config.source_id}",
    )
    store.write_source_run(run)
    document = raw_document_from_text(
        config=config,
        run=run,
        text=fixture_path.read_text(encoding="utf-8"),
        source_url=config.base_url,
        content_type=content_type,
    )
    assert store.write_raw_document(document)
    for chunk in parser(document):
        store.write_chunk(chunk)


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _document_parsed_event_from_store(
    data_dir: Path,
    *,
    document_chunk_ids: list[UUID] | None = None,
) -> EventEnvelope:
    raw_document = _read_jsonl(data_dir / "raw_documents.jsonl")[0]
    selected_chunk_ids = document_chunk_ids or [
        UUID(str(row["id"])) for row in _read_jsonl(data_dir / "document_chunks.jsonl")
    ]
    payload = DocumentParsedPayload(
        raw_document_id=UUID(str(raw_document["id"])),
        document_chunk_ids=selected_chunk_ids,
        parser_profile="openfda.drug_ndc.v1",
        chunk_count=len(selected_chunk_ids),
    )
    return build_event(
        event_type="ingest.document_parsed",
        service="parser",
        source_id=str(raw_document["source_id"]),
        payload=payload.model_dump(mode="json"),
        idempotency_key=f"ingest.document_parsed:{raw_document['id']}:{len(selected_chunk_ids)}",
    )


def _fake_message(event: EventEnvelope) -> FakeMessage:
    return FakeMessage(
        topic="ingest.document_parsed",
        key=b"document-parsed",
        value=serialize_event(event),
    )
