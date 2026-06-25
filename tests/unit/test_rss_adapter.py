from supply_intel.models.source import (
    ComplianceConfig,
    CursorConfig,
    DedupeConfig,
    ParserConfig,
    ScheduleConfig,
    SourceConfig,
    SourceCursor,
    SourceRun,
)
from supply_intel.sources.adapters import adapter_for_source
from supply_intel.sources.adapters.base import FetchRequest
from supply_intel.sources.adapters.rest import RssAtomAdapter

HTTP_BAD_REQUEST = 400
MAX_DOCUMENTS = 2


class FakeResponse:
    def __init__(self, text: str, *, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code
        self.headers = {"content-type": "application/rss+xml", "etag": '"feed-v1"'}
        self.url = "https://example.test/feed.xml"

    def raise_for_status(self) -> None:
        if self.status_code >= HTTP_BAD_REQUEST:
            raise RuntimeError("unexpected status")


class FakeRssAdapter(RssAtomAdapter):
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests: list[FetchRequest] = []

    async def _get(self, request: FetchRequest) -> FakeResponse:
        self.requests.append(request)
        return self.response


async def test_rss_adapter_plan_uses_conditional_request_headers() -> None:
    config = _rss_config()
    cursor = SourceCursor(
        source_id=config.source_id,
        etag='"feed-v0"',
        cursor_state={"last_modified": "Wed, 24 Jun 2026 10:00:00 GMT"},
    )
    run = _source_run(config)

    plan = await RssAtomAdapter().plan_fetch(config, cursor, run, max_documents=MAX_DOCUMENTS)

    assert plan.max_documents == MAX_DOCUMENTS
    assert plan.requests[0].headers["If-None-Match"] == '"feed-v0"'
    assert plan.requests[0].headers["If-Modified-Since"] == "Wed, 24 Jun 2026 10:00:00 GMT"


async def test_rss_adapter_fetch_emits_entry_level_payloads() -> None:
    config = _rss_config()
    adapter = FakeRssAdapter(
        FakeResponse(
            """
            <rss version="2.0">
              <channel>
                <title>FDA Updates</title>
                <item>
                  <guid>notice-1</guid>
                  <link>https://example.test/notices/1</link>
                  <title>Supply notice</title>
                  <pubDate>Wed, 24 Jun 2026 10:00:00 GMT</pubDate>
                  <description>Manufacturer update</description>
                </item>
                <item>
                  <guid>notice-2</guid>
                  <link>https://example.test/notices/2</link>
                  <title>Second notice</title>
                </item>
              </channel>
            </rss>
            """
        )
    )
    run = _source_run(config)
    plan = await adapter.plan_fetch(config, None, run, max_documents=1)

    payloads = [payload async for payload in adapter.fetch(config, plan)]

    assert len(payloads) == 1
    assert payloads[0].source_url == "https://example.test/notices/1"
    assert payloads[0].content_type == "application/rss+xml"
    assert payloads[0].record is not None
    assert payloads[0].record["guid"] == "notice-1"
    assert payloads[0].record["summary"] == "Manufacturer update"


def test_adapter_for_source_supports_rss_runtime() -> None:
    assert isinstance(adapter_for_source(_rss_config()), RssAtomAdapter)


def _rss_config() -> SourceConfig:
    return SourceConfig(
        source_id="fda_rss_notices",
        name="FDA RSS Notices",
        source_type="government_feed",
        adapter="rss",
        base_url="https://example.test/feed.xml",
        headers={"User-Agent": "${PLATFORM_USER_AGENT}"},
        cursor=CursorConfig(strategy="etag"),
        dedupe=DedupeConfig(key_fields=["guid", "link"]),
        parser=ParserConfig(profile="openfda.drug_ndc.v1", chunking="feed_item"),
        compliance=ComplianceConfig(
            robots="validate_before_fetch",
            license_notes="Public test feed.",
            pii_expected=False,
        ),
        schedule=ScheduleConfig(cadence="1h"),
    )


def _source_run(config: SourceConfig) -> SourceRun:
    return SourceRun(
        source_id=config.source_id,
        run_type="test",
        status="running",
        idempotency_key=f"test:{config.source_id}",
    )
