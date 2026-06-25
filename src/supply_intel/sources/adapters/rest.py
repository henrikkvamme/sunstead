from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from json import JSONDecodeError
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser  # type: ignore[import-untyped]
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from supply_intel.models.source import SourceConfig, SourceCursor, SourceRun
from supply_intel.sources.adapters.base import FetchedPayload, FetchPlan, FetchRequest

MIN_RETRY_SECONDS = 5
MAX_RETRY_SECONDS = 30


def _raise_for_retryable_status(response: httpx.Response) -> None:
    if response.status_code in {httpx.codes.REQUEST_TIMEOUT, httpx.codes.TOO_MANY_REQUESTS}:
        response.raise_for_status()
    if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
        response.raise_for_status()


def _auth_params(config: SourceConfig) -> dict[str, str]:
    if config.auth.type == "query_param" and config.auth.env and config.auth.param:
        value = os.getenv(config.auth.env)
        return {config.auth.param: value} if value else {}
    return {}


def _headers(config: SourceConfig) -> dict[str, str]:
    headers = {
        key: expanded
        for key, value in config.headers.items()
        if (expanded := _expand_env_template(value))
    }
    if config.auth.type == "header" and config.auth.env and config.auth.header:
        value = os.getenv(config.auth.env)
        if value:
            headers[config.auth.header] = value
    if config.auth.type == "bearer_env" and config.auth.env:
        value = os.getenv(config.auth.env)
        if value:
            headers["Authorization"] = f"Bearer {value}"
    return headers


def _expand_env_template(value: str) -> str:
    if value == "${PLATFORM_USER_AGENT}":
        return os.getenv("PLATFORM_USER_AGENT", "unnamed-platform-dev/0.1")
    expanded = os.path.expandvars(value)
    return "" if expanded.startswith("${") and expanded.endswith("}") else expanded


def _redacted_response_url(url: httpx.URL, config: SourceConfig) -> str:
    if config.auth.type != "query_param" or not config.auth.param:
        return str(url)
    parts = urlsplit(str(url))
    sensitive_params = {config.auth.param.casefold()}
    query = [
        (key, "REDACTED" if key.casefold() in sensitive_params else value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


def _request_url_and_params(
    config: SourceConfig,
    params: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    parts = urlsplit(config.base_url)
    merged_params = _query_pairs_to_params(parse_qsl(parts.query, keep_blank_values=True))
    merged_params.update(params or {})
    return (
        urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment)),
        merged_params,
    )


def _query_pairs_to_params(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key, value in pairs:
        if key not in params:
            params[key] = value
            continue
        existing = params[key]
        if isinstance(existing, list):
            existing.append(value)
        else:
            params[key] = [existing, value]
    return params


class PaginatedRestAdapter:
    adapter_type = "paginated_rest"

    async def plan_fetch(
        self,
        config: SourceConfig,
        cursor: SourceCursor | None,
        run: SourceRun,
        *,
        max_documents: int | None = None,
    ) -> FetchPlan:
        del cursor, run
        url, params = _request_url_and_params(config, _auth_params(config))
        if config.pagination.type == "skip_limit":
            params[config.pagination.limit_param] = min(
                config.pagination.page_size,
                max_documents or config.pagination.page_size,
            )
            params[config.pagination.offset_param] = 0
        return FetchPlan(
            requests=[FetchRequest(url=url, params=params, headers=_headers(config))],
            max_documents=max_documents,
        )

    @retry(
        wait=wait_exponential(multiplier=1, min=MIN_RETRY_SECONDS, max=MAX_RETRY_SECONDS),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _get(self, request: FetchRequest) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(request.url, params=request.params, headers=request.headers)
            _raise_for_retryable_status(response)
            return response

    async def fetch(self, config: SourceConfig, plan: FetchPlan) -> AsyncIterator[FetchedPayload]:
        emitted = 0
        for request in plan.requests:
            offset = int(request.params.get(config.pagination.offset_param, 0))
            while True:
                params = dict(request.params)
                if config.pagination.type == "skip_limit":
                    params[config.pagination.offset_param] = offset
                response = await self._get(FetchRequest(request.url, params, request.headers))
                response.raise_for_status()
                data = _json_response(response, config=config)
                records = _records_at_path(data, config.pagination.results_path)
                if not records:
                    break
                for record in records:
                    if plan.max_documents is not None and emitted >= plan.max_documents:
                        return
                    emitted += 1
                    yield FetchedPayload(
                        source_url=_redacted_response_url(response.url, config),
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        content_type=response.headers.get("content-type"),
                        text=json.dumps(record, sort_keys=True),
                        record=record if isinstance(record, dict) else {"value": record},
                    )
                if config.pagination.type != "skip_limit":
                    break
                offset += config.pagination.page_size
                if (
                    config.pagination.max_offset is not None
                    and offset > config.pagination.max_offset
                ):
                    break


def _json_response(response: httpx.Response, *, config: SourceConfig) -> Any:
    try:
        return response.json()
    except JSONDecodeError as exc:
        content_type = response.headers.get("content-type") or "unknown"
        preview = response.text[:240].replace("\n", " ").strip()
        raise ValueError(
            "REST source returned a non-JSON response "
            f"for {config.source_id}: status={response.status_code} "
            f"content_type={content_type} "
            f"url={_redacted_response_url(response.url, config)} "
            f"body_preview={preview!r}"
        ) from exc


def _records_at_path(data: Any, path: str | None) -> list[Any]:
    if not path:
        return [data]
    current = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return []
        current = current.get(part)
    return current if isinstance(current, list) else []


class HtmlScraperAdapter:
    adapter_type = "html_scraper"

    async def plan_fetch(
        self,
        config: SourceConfig,
        cursor: SourceCursor | None,
        run: SourceRun,
        *,
        max_documents: int | None = None,
    ) -> FetchPlan:
        del cursor, run, max_documents
        url, params = _request_url_and_params(config, _auth_params(config))
        return FetchPlan(
            requests=[
                FetchRequest(
                    url=url,
                    params=params,
                    headers=_headers(config),
                )
            ],
            max_documents=1,
        )

    @retry(
        wait=wait_exponential(multiplier=1, min=MIN_RETRY_SECONDS, max=MAX_RETRY_SECONDS),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _get(self, request: FetchRequest) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(request.url, params=request.params, headers=request.headers)
            _raise_for_retryable_status(response)
            return response

    async def fetch(self, config: SourceConfig, plan: FetchPlan) -> AsyncIterator[FetchedPayload]:
        for request in plan.requests:
            response = await self._get(request)
            response.raise_for_status()
            source_url = _redacted_response_url(response.url, config)
            yield FetchedPayload(
                source_url=source_url,
                status_code=response.status_code,
                headers=dict(response.headers),
                content_type=response.headers.get("content-type"),
                text=response.text,
                record={"canonical_url": source_url},
            )


class RssAtomAdapter:
    adapter_type = "rss"

    async def plan_fetch(
        self,
        config: SourceConfig,
        cursor: SourceCursor | None,
        run: SourceRun,
        *,
        max_documents: int | None = None,
    ) -> FetchPlan:
        del run
        headers = _headers(config)
        if cursor is not None:
            if cursor.etag:
                headers["If-None-Match"] = cursor.etag
            last_modified = cursor.cursor_state.get("last_modified")
            if isinstance(last_modified, str):
                headers["If-Modified-Since"] = last_modified
        url, params = _request_url_and_params(config, _auth_params(config))
        return FetchPlan(
            requests=[
                FetchRequest(
                    url=url,
                    params=params,
                    headers=headers,
                )
            ],
            max_documents=max_documents,
        )

    @retry(
        wait=wait_exponential(multiplier=1, min=MIN_RETRY_SECONDS, max=MAX_RETRY_SECONDS),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _get(self, request: FetchRequest) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(request.url, params=request.params, headers=request.headers)
            _raise_for_retryable_status(response)
            return response

    async def fetch(self, config: SourceConfig, plan: FetchPlan) -> AsyncIterator[FetchedPayload]:
        del config
        emitted = 0
        for request in plan.requests:
            response = await self._get(request)
            if response.status_code == httpx.codes.NOT_MODIFIED:
                continue
            response.raise_for_status()
            feed = feedparser.parse(response.text)
            entries = feed.get("entries", [])
            for entry in entries:
                if plan.max_documents is not None and emitted >= plan.max_documents:
                    return
                record = _rss_entry_record(entry)
                emitted += 1
                yield FetchedPayload(
                    source_url=record["canonical_url"],
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    content_type=response.headers.get("content-type"),
                    text=json.dumps(record, sort_keys=True),
                    record=record,
                )


def _rss_entry_record(entry: Any) -> dict[str, Any]:
    guid = str(
        _rss_entry_value(entry, "id")
        or _rss_entry_value(entry, "guid")
        or _rss_entry_value(entry, "link")
        or ""
    )
    link = str(_rss_entry_value(entry, "link") or guid)
    title = str(_rss_entry_value(entry, "title") or "")
    published = _rss_entry_value(entry, "published") or _rss_entry_value(entry, "created")
    updated = _rss_entry_value(entry, "updated") or published
    summary = _rss_entry_value(entry, "summary") or _rss_entry_value(entry, "description")
    raw_tags = _rss_entry_value(entry, "tags")
    tags = raw_tags if isinstance(raw_tags, list) else []
    record = {
        "guid": guid,
        "link": link,
        "canonical_url": link or guid,
        "title": title,
        "summary": str(summary or ""),
        "published": str(published or ""),
        "updated": str(updated or ""),
        "tags": [
            str(tag.get("term"))
            for tag in tags
            if isinstance(tag, dict) and tag.get("term") is not None
        ],
    }
    for key, value in entry.items():
        if key.startswith(("gdacs_", "geo_", "georss_", "dc_")) and key not in record:
            record[key] = _jsonable_entry_value(value)
    return record


def _rss_entry_value(entry: Any, key: str) -> Any:
    if key not in entry:
        return None
    return entry[key]


def _jsonable_entry_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable_entry_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable_entry_value(item) for item in value]
    return value
