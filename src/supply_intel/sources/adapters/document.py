from __future__ import annotations

from collections.abc import AsyncIterator
from io import BytesIO
from typing import Any

from pypdf import PdfReader

from supply_intel.models.source import SourceConfig, SourceCursor, SourceRun
from supply_intel.sources.adapters.base import FetchedPayload, FetchPlan
from supply_intel.sources.adapters.file_download import FileDownloadAdapter


class PdfDocumentAdapter:
    adapter_type = "pdf_document"

    def __init__(self, downloader: FileDownloadAdapter | None = None) -> None:
        self.downloader = downloader or FileDownloadAdapter()

    async def plan_fetch(
        self,
        config: SourceConfig,
        cursor: SourceCursor | None,
        run: SourceRun,
        *,
        max_documents: int | None = None,
    ) -> FetchPlan:
        return await self.downloader.plan_fetch(
            config,
            cursor,
            run,
            max_documents=max_documents,
        )

    async def fetch(self, config: SourceConfig, plan: FetchPlan) -> AsyncIterator[FetchedPayload]:
        async for payload in self.downloader.fetch(config, plan):
            content = payload.content_bytes or payload.text.encode("utf-8")
            extracted = _extract_pdf_text(content)
            record = dict(payload.record or {})
            record.update(
                {
                    "page_count": len(extracted["pages"]),
                    "text_extraction_method": "pypdf",
                    "page_text_lengths": [len(page) for page in extracted["pages"]],
                }
            )
            yield FetchedPayload(
                source_url=payload.source_url,
                status_code=payload.status_code,
                headers=payload.headers,
                content_type=payload.content_type or "application/pdf",
                text=extracted["text"],
                content_bytes=content,
                fetched_at=payload.fetched_at,
                record=record,
            )


def _extract_pdf_text(content: bytes) -> dict[str, Any]:
    reader = PdfReader(BytesIO(content))
    pages = [page.extract_text() or "" for page in reader.pages]
    return {"text": "\n\n".join(page for page in pages if page), "pages": pages}
