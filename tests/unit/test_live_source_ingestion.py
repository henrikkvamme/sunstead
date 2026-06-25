import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pytest

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.models.source import SourceCursor, SourceRun
from supply_intel.pipeline import (
    fetch_source_sample,
    ingest_openfda_ndc_live,
    process_live_source_run,
)
from supply_intel.settings import Settings
from supply_intel.sources.adapters.base import FetchedPayload, FetchPlan, FetchRequest
from supply_intel.sources.adapters.rest import PaginatedRestAdapter
from supply_intel.sources.registry import load_source_config

EXPECTED_NDC_ENTITY_COUNT = 4
EXPECTED_NDC_RELATIONSHIP_COUNT = 3
EXPECTED_BASE_EVENT_COUNT = 3


class FakeAdapter:
    adapter_type = "paginated_rest"

    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records
        self.planned_cursor: object | None = None

    async def plan_fetch(
        self,
        config: object,
        cursor: object,
        run: object,
        *,
        max_documents: int | None = None,
    ) -> FetchPlan:
        del config, run
        self.planned_cursor = cursor
        return FetchPlan(
            requests=[FetchRequest(url="https://example.test/openfda")],
            max_documents=max_documents,
        )

    async def fetch(
        self,
        config: object,
        plan: FetchPlan,
    ) -> AsyncIterator[FetchedPayload]:
        del config
        for record in self.records[: plan.max_documents]:
            yield FetchedPayload(
                source_url="https://example.test/openfda?limit=1&skip=0",
                status_code=200,
                headers={
                    "content-type": "application/json",
                    "etag": '"live-v1"',
                    "last-modified": "Wed, 24 Jun 2026 10:00:00 GMT",
                },
                content_type="application/json",
                text=json.dumps(record, sort_keys=True),
                record=record,
            )


class InterruptingAdapter(FakeAdapter):
    async def fetch(
        self,
        config: object,
        plan: FetchPlan,
    ) -> AsyncIterator[FetchedPayload]:
        del config, plan
        raise KeyboardInterrupt
        yield  # pragma: no cover


class NonJsonRestAdapter(PaginatedRestAdapter):
    async def _get(self, request: FetchRequest) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="Queries containing OR'd terms must be surrounded by ().",
            request=httpx.Request("GET", request.url),
        )


class EiaRestAdapter(PaginatedRestAdapter):
    async def _get(self, request: FetchRequest) -> httpx.Response:
        query = urlencode(request.params)
        separator = "&" if "?" in request.url else "?"
        url = f"{request.url}{separator}{query}"
        return httpx.Response(
            200,
            json={
                "response": {
                    "data": [
                        {
                            "period": "2026-06-22",
                            "product": "EPD2D",
                            "product-name": "No 2 Diesel",
                            "duoarea": "NUS",
                            "area-name": "U.S.",
                            "process": "PRS",
                            "process-name": "Retail",
                            "series": "EMD_EPD2D_PTE_NUS_DPG",
                            "series-description": "Diesel retail price",
                        }
                    ]
                }
            },
            request=httpx.Request("GET", url),
        )


def fixture_ndc_record() -> dict[str, object]:
    data = json.loads(
        Path("tests/fixtures/sources/openfda_drug_ndc/success.json").read_text(encoding="utf-8")
    )
    record = data["results"][0]
    assert isinstance(record, dict)
    return record


async def test_fetch_source_sample_uses_adapter_without_storing() -> None:
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))

    sample = await fetch_source_sample(
        config=config,
        max_documents=1,
        adapter=FakeAdapter([fixture_ndc_record()]),
    )

    assert sample["source_id"] == "openfda_drug_ndc"
    assert sample["fetched"] == 1
    records = sample["records"]
    assert isinstance(records, list)
    assert records[0]["source_url"] == "https://example.test/openfda?limit=1&skip=0"
    assert "product_ndc" in records[0]["record_keys"]


async def test_live_ndc_ingestion_runs_raw_first_pipeline(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    settings = Settings(data_dir=tmp_path)
    store = FileEvidenceStore(tmp_path)
    store.write_source_cursor(
        SourceCursor(
            source_id=config.source_id,
            cursor_state={"skip": 0},
            watermark=datetime(2026, 6, 23, tzinfo=UTC),
            etag='"live-v0"',
        )
    )
    adapter = FakeAdapter([fixture_ndc_record()])

    stats = await ingest_openfda_ndc_live(
        config=config,
        settings=settings,
        max_documents=1,
        adapter=adapter,
    )

    assert stats["raw_documents_created"] == 1
    assert stats["chunks_created"] == 1
    assert stats["entities_resolved"] == EXPECTED_NDC_ENTITY_COUNT
    raw_documents = [
        json.loads(line)
        for line in (tmp_path / "raw_documents.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert raw_documents[0]["source_url"] == "https://example.test/openfda?limit=1&skip=0"
    assert raw_documents[0]["dedupe_key"]
    assert isinstance(adapter.planned_cursor, SourceCursor)
    assert adapter.planned_cursor.etag == '"live-v0"'
    source_runs = [
        json.loads(line)
        for line in (tmp_path / "source_runs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    completed_run = source_runs[-1]
    assert completed_run["cursor_before"]["etag"] == '"live-v0"'
    assert completed_run["cursor_after"]["etag"] == '"live-v1"'
    assert completed_run["cursor_after"]["cursor_state"]["documents_seen"] == 1
    source_cursors = [
        json.loads(line)
        for line in (tmp_path / "source_cursors.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(source_cursors) == 1
    assert source_cursors[0]["etag"] == '"live-v1"'
    assert source_cursors[0]["updated_by_run_id"] == completed_run["id"]
    events = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    event_types = [event["event_type"] for event in events]
    assert event_types[:EXPECTED_BASE_EVENT_COUNT] == [
        "ingest.raw_document_created",
        "ingest.document_parsed",
        "ingest.extraction_completed",
    ]
    assert event_types.count("graph.node_upsert") == EXPECTED_NDC_ENTITY_COUNT
    assert event_types.count("graph.relationship_upsert") == EXPECTED_NDC_RELATIONSHIP_COUNT


async def test_process_live_source_run_records_keyboard_interrupt(tmp_path: Path) -> None:
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    settings = Settings(data_dir=tmp_path)
    run = SourceRun(
        source_id=config.source_id,
        run_type="backfill",
        status="running",
        idempotency_key="interrupting-backfill",
    )

    with pytest.raises(KeyboardInterrupt):
        await process_live_source_run(
            config=config,
            settings=settings,
            run=run,
            max_documents=1,
            adapter=InterruptingAdapter([]),
        )

    source_runs = [
        json.loads(line)
        for line in (tmp_path / "source_runs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    interrupted_run = source_runs[-1]
    assert interrupted_run["status"] == "failed"
    assert interrupted_run["error_count"] == 1
    assert interrupted_run["documents_seen"] == 0
    assert interrupted_run["metadata"]["error"] == "KeyboardInterrupt"
    assert interrupted_run["metadata"]["interrupted"] is True
    assert interrupted_run["finished_at"] is not None


async def test_paginated_rest_plan_expands_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PLATFORM_USER_AGENT", raising=False)
    config = load_source_config(Path("sources/openfda_drug_ndc.yaml"))
    run = SourceRun(
        source_id=config.source_id,
        run_type="test",
        status="running",
        idempotency_key="test",
    )

    plan = await PaginatedRestAdapter().plan_fetch(
        config,
        None,
        run,
        max_documents=1,
    )

    assert plan.requests[0].headers["User-Agent"] == "unnamed-platform-dev/0.1"
    assert plan.requests[0].params["limit"] == 1


async def test_paginated_rest_plan_preserves_base_url_query_params() -> None:
    config = load_source_config(Path("sources/eia_energy_prices.yaml"))
    run = SourceRun(
        source_id=config.source_id,
        run_type="test",
        status="running",
        idempotency_key="test",
    )

    plan = await PaginatedRestAdapter().plan_fetch(
        config,
        None,
        run,
        max_documents=1,
    )

    assert plan.requests[0].url == "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
    assert plan.requests[0].params["length"] == 1
    assert plan.requests[0].params["data[0]"] == "value"
    assert plan.requests[0].params["facets[product][]"] == "EPD2D"


async def test_paginated_rest_non_json_response_includes_source_context() -> None:
    config = load_source_config(Path("sources/gdelt_doc_search.yaml"))
    run = SourceRun(
        source_id=config.source_id,
        run_type="test",
        status="running",
        idempotency_key="test",
    )
    adapter = NonJsonRestAdapter()
    plan = await adapter.plan_fetch(config, None, run, max_documents=1)

    with pytest.raises(ValueError) as exc_info:
        _ = [payload async for payload in adapter.fetch(config, plan)]

    message = str(exc_info.value)
    assert "REST source returned a non-JSON response" in message
    assert "gdelt_doc_search" in message
    assert "text/html" in message
    assert "OR'd terms" in message


async def test_paginated_rest_redacts_query_param_auth_from_source_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EIA_API_KEY", "configured-secret")
    config = load_source_config(Path("sources/eia_energy_prices.yaml"))
    run = SourceRun(
        source_id=config.source_id,
        run_type="test",
        status="running",
        idempotency_key="test",
    )
    adapter = EiaRestAdapter()
    plan = await adapter.plan_fetch(config, None, run, max_documents=1)

    payloads = [payload async for payload in adapter.fetch(config, plan)]

    assert len(payloads) == 1
    assert "api_key=REDACTED" in payloads[0].source_url
    assert "data%5B0%5D=value" in payloads[0].source_url
    assert "facets%5Bproduct%5D%5B%5D=EPD2D" in payloads[0].source_url
    assert "configured-secret" not in payloads[0].source_url
