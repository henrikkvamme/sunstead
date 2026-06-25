from __future__ import annotations

import hashlib
import json
from typing import Any

from supply_intel.models.documents import DocumentChunk
from supply_intel.models.source import RawDocument


def parse_gdelt_doc_search_document(document: RawDocument) -> list[DocumentChunk]:
    records = _article_records(document)
    chunks: list[DocumentChunk] = []
    for index, record in enumerate(records):
        url = str(record.get("url", "")).strip()
        title = str(record.get("title", "")).strip()
        if not url and not title:
            continue
        text = _article_text(record)
        chunks.append(
            DocumentChunk(
                raw_document_id=document.id,
                chunk_index=index,
                chunk_type="news_article_metadata",
                title=title or url,
                text=text,
                structured_data=record,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return chunks


def _article_records(document: RawDocument) -> list[dict[str, object]]:
    if not document.payload_text:
        return []
    try:
        payload = json.loads(document.payload_text)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        articles = payload.get("articles")
        if isinstance(articles, list):
            return [article for article in articles if isinstance(article, dict)]
        if payload.get("url") or payload.get("title"):
            return [payload]
    if isinstance(payload, list):
        return [article for article in payload if isinstance(article, dict)]
    return []


def _article_text(record: dict[str, Any]) -> str:
    fields = [
        f"Title: {record.get('title', '')}",
        f"URL: {record.get('url', '')}",
        f"Mobile URL: {record.get('url_mobile', '')}",
        f"Seen date: {record.get('seendate', '')}",
        f"Domain: {record.get('domain', '')}",
        f"Language: {record.get('language', '')}",
        f"Source country: {record.get('sourcecountry', '')}",
        f"Social image: {record.get('socialimage', '')}",
    ]
    return "\n".join(field for field in fields if not field.endswith(": "))
