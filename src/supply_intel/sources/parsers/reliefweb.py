from __future__ import annotations

import hashlib
import json
from typing import Any

from supply_intel.models.documents import DocumentChunk
from supply_intel.models.source import RawDocument


def parse_reliefweb_reports_document(document: RawDocument) -> list[DocumentChunk]:
    records = _report_records(document)
    chunks: list[DocumentChunk] = []
    for index, record in enumerate(records):
        report_id = str(record.get("reliefweb_id") or record.get("id") or "").strip()
        title = str(record.get("title", "")).strip()
        if not report_id and not title:
            continue
        text = _report_text(record)
        chunks.append(
            DocumentChunk(
                raw_document_id=document.id,
                chunk_index=index,
                chunk_type="humanitarian_report_metadata",
                title=title or f"ReliefWeb report {report_id}",
                text=text,
                structured_data=record,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return chunks


def _report_records(document: RawDocument) -> list[dict[str, object]]:
    if not document.payload_text:
        return []
    try:
        payload = json.loads(document.payload_text)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [_normalize_report(item) for item in data if isinstance(item, dict)]
        if payload.get("fields") or payload.get("title") or payload.get("id"):
            return [_normalize_report(payload)]
    if isinstance(payload, list):
        return [_normalize_report(item) for item in payload if isinstance(item, dict)]
    return []


def _normalize_report(item: dict[str, Any]) -> dict[str, object]:
    fields = item.get("fields")
    source = fields if isinstance(fields, dict) else item
    date = source.get("date")
    date_fields = date if isinstance(date, dict) else {}
    record: dict[str, object] = {
        "reliefweb_id": str(item.get("id") or source.get("id") or "").strip(),
        "api_href": item.get("href") or source.get("href"),
        "score": item.get("score"),
        "title": source.get("title"),
        "url": source.get("url"),
        "status": source.get("status"),
        "body": source.get("body"),
        "format": _names(source.get("format")),
        "language": _names(source.get("language")),
        "source": _names(source.get("source")),
        "source_shortnames": _values(source.get("source"), "shortname"),
        "country": _names(source.get("country")),
        "primary_country": _names(source.get("primary_country")),
        "theme": _names(source.get("theme")),
        "disaster": _names(source.get("disaster")),
        "date_original": date_fields.get("original"),
        "date_created": date_fields.get("created"),
        "date_changed": date_fields.get("changed"),
    }
    return {key: value for key, value in record.items() if value not in (None, "", [])}


def _names(value: object) -> list[str]:
    return _values(value, "name")


def _values(value: object, key: str) -> list[str]:
    if isinstance(value, dict):
        raw = value.get(key)
        return [str(raw).strip()] if raw else []
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            if isinstance(item, dict):
                raw = item.get(key)
                if raw:
                    values.append(str(raw).strip())
            elif item:
                values.append(str(item).strip())
        return [item for item in values if item]
    if value:
        return [str(value).strip()]
    return []


def _report_text(record: dict[str, Any]) -> str:
    fields = [
        f"Title: {record.get('title', '')}",
        f"ReliefWeb ID: {record.get('reliefweb_id', '')}",
        f"URL: {record.get('url', '')}",
        f"API href: {record.get('api_href', '')}",
        f"Original date: {record.get('date_original', '')}",
        f"Created date: {record.get('date_created', '')}",
        f"Changed date: {record.get('date_changed', '')}",
        f"Sources: {_join(record.get('source'))}",
        f"Source shortnames: {_join(record.get('source_shortnames'))}",
        f"Countries: {_join(record.get('country'))}",
        f"Primary countries: {_join(record.get('primary_country'))}",
        f"Themes: {_join(record.get('theme'))}",
        f"Disasters: {_join(record.get('disaster'))}",
        f"Format: {_join(record.get('format'))}",
        f"Language: {_join(record.get('language'))}",
        f"Status: {record.get('status', '')}",
    ]
    return "\n".join(field for field in fields if not field.endswith(": "))


def _join(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item)
    return str(value or "").strip()
