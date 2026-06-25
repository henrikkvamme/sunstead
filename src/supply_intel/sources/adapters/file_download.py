from __future__ import annotations

import hashlib
import mimetypes
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from supply_intel.models.source import SourceConfig, SourceCursor, SourceRun
from supply_intel.sources.adapters.base import FetchedPayload, FetchPlan, FetchRequest
from supply_intel.sources.adapters.rest import _auth_params, _headers

HTTP_OK = 200


class FileDownloadAdapter:
    adapter_type = "file_download"

    async def plan_fetch(
        self,
        config: SourceConfig,
        cursor: SourceCursor | None,
        run: SourceRun,
        *,
        max_documents: int | None = None,
    ) -> FetchPlan:
        del cursor, run
        return FetchPlan(
            requests=[
                FetchRequest(
                    url=_source_url(config.base_url),
                    params=_auth_params(config),
                    headers=_headers(config),
                )
            ],
            max_documents=max_documents,
        )

    @retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(3))
    async def _get(self, request: FetchRequest) -> httpx.Response:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            return await client.get(request.url, params=request.params, headers=request.headers)

    async def fetch(self, config: SourceConfig, plan: FetchPlan) -> AsyncIterator[FetchedPayload]:
        del config
        for emitted, request in enumerate(plan.requests):
            if plan.max_documents is not None and emitted >= plan.max_documents:
                return
            local_path = _path_from_url(request.url)
            if local_path is not None:
                content = local_path.read_bytes()
                source_url = local_path.resolve().as_uri()
                status_code = HTTP_OK
                content_type = _content_type_for_name(local_path.name)
                headers: dict[str, str] = {}
            else:
                response = await self._get(request)
                response.raise_for_status()
                content = response.content
                source_url = str(response.url)
                status_code = response.status_code
                content_type = response.headers.get("content-type")
                headers = dict(response.headers)
            yield FetchedPayload(
                source_url=source_url,
                status_code=status_code,
                headers=headers,
                content_type=content_type,
                text=_decode_text(content),
                content_bytes=content,
                record={
                    "canonical_url": source_url,
                    "filename": _filename_from_url(source_url),
                    "content_hash": hashlib.sha256(content).hexdigest(),
                    "content_length": len(content),
                },
            )


def _source_url(value: str) -> str:
    path = _path_from_url(value)
    if path is None:
        return value
    return path.resolve().as_uri()


def _path_from_url(value: str) -> Path | None:
    parsed = urlparse(value)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path))
    if parsed.scheme:
        return None
    return Path(value)


def _filename_from_url(value: str) -> str:
    parsed = urlparse(value)
    path = unquote(parsed.path)
    return Path(path).name


def _content_type_for_name(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def _decode_text(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return ""
