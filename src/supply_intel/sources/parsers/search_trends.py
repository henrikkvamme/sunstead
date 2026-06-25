from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from supply_intel.models.documents import DocumentChunk
from supply_intel.models.source import RawDocument


def parse_search_trend_signals_document(document: RawDocument) -> list[DocumentChunk]:
    records = _trend_records(document)
    chunks: list[DocumentChunk] = []
    for index, record in enumerate(records):
        observed_at = str(record.get("observed_at", "")).strip()
        value = _float_value(record.get("value"))
        if not observed_at or value is None:
            continue
        text = _trend_text(record)
        chunks.append(
            DocumentChunk(
                raw_document_id=document.id,
                chunk_index=index,
                chunk_type="trend_signal_observation",
                title=f"{record.get('signal_name', 'Trend signal')} {observed_at}",
                text=text,
                structured_data=record,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return chunks


def _trend_records(document: RawDocument) -> list[dict[str, object]]:
    if not document.payload_text:
        return []
    try:
        payload = json.loads(document.payload_text)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        return [_normalized_record(record, {}) for record in payload if isinstance(record, dict)]
    if not isinstance(payload, dict):
        return []
    metadata = {
        "query": payload.get("query") or payload.get("search_query"),
        "mode": payload.get("mode") or "timelinevol",
        "timespan": payload.get("timespan") or payload.get("window"),
        "source_api": "gdelt_doc_2",
    }
    records = _records_from_payload(payload)
    return [_normalized_record(record, metadata) for record in records]


def _records_from_payload(payload: dict[str, object]) -> list[dict[str, object]]:
    for key in ("timeline", "data", "results", "timelinevol"):
        value = payload.get(key)
        if isinstance(value, list):
            return [record for record in value if isinstance(record, dict)]
    if payload.get("date") or payload.get("datetime") or payload.get("observed_at"):
        return [payload]
    return []


def _normalized_record(
    record: dict[str, object],
    metadata: dict[str, object],
) -> dict[str, object]:
    raw_date = _first_text(record, "date", "datetime", "timestamp", "observed_at")
    observed_at = _parse_gdelt_timeline_date(raw_date)
    value = _float_value(_first_raw(record, "value", "volume", "norm", "count"))
    return {
        "signal_name": "GDELT DOC news volume trend",
        "observed_at": observed_at.isoformat() if observed_at is not None else raw_date,
        "value": value,
        "unit": _unit_for_record(record),
        "query": _first_text(record, "query") or str(metadata.get("query") or ""),
        "window": _first_text(record, "window") or str(metadata.get("timespan") or ""),
        "mode": str(metadata.get("mode") or "timelinevol"),
        "source_api": str(metadata.get("source_api") or "gdelt_doc_2"),
        "raw_date": raw_date,
        "raw_value": _first_raw(record, "value", "volume", "norm", "count"),
        "article_count": _float_value(_first_raw(record, "count", "article_count")),
        "normalized_volume": _float_value(_first_raw(record, "norm", "normalized_volume")),
    }


def _unit_for_record(record: dict[str, object]) -> str:
    if _first_raw(record, "norm", "normalized_volume") is not None:
        return "normalized_news_volume"
    if _first_raw(record, "count", "article_count") is not None:
        return "article_count"
    return "timeline_value"


def _parse_gdelt_timeline_date(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    for date_format in ("%Y%m%d%H%M%S", "%Y%m%dT%H%M%SZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, date_format).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _first_text(record: dict[str, object], *keys: str) -> str:
    value = _first_raw(record, *keys)
    if value is None:
        return ""
    return str(value).strip()


def _first_raw(record: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _float_value(value: object | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text in {"NA", "N/A", "--", "-", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _trend_text(record: dict[str, Any]) -> str:
    fields = [
        f"Signal: {record.get('signal_name', '')}",
        f"Observed at: {record.get('observed_at', '')}",
        f"Value: {record.get('value', '')}",
        f"Unit: {record.get('unit', '')}",
        f"Query: {record.get('query', '')}",
        f"Window: {record.get('window', '')}",
        f"Mode: {record.get('mode', '')}",
        f"Source API: {record.get('source_api', '')}",
        f"Raw date: {record.get('raw_date', '')}",
        f"Raw value: {record.get('raw_value', '')}",
    ]
    return "\n".join(field for field in fields if not field.endswith(": "))
