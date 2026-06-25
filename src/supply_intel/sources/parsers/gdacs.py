from __future__ import annotations

import hashlib
import json
from typing import Any

import feedparser  # type: ignore[import-untyped]

from supply_intel.models.documents import DocumentChunk
from supply_intel.models.source import RawDocument


def parse_gdacs_events_document(document: RawDocument) -> list[DocumentChunk]:
    records = _event_records(document)
    chunks: list[DocumentChunk] = []
    for index, record in enumerate(records):
        event_id = str(record.get("gdacs_eventid") or record.get("event_id") or "").strip()
        event_type = str(record.get("gdacs_eventtype") or record.get("event_type") or "").strip()
        title = str(record.get("title", "")).strip()
        if not event_id and not title:
            continue
        text = _event_text(record)
        chunks.append(
            DocumentChunk(
                raw_document_id=document.id,
                chunk_index=index,
                chunk_type="rss_item",
                title=title or f"GDACS {event_type} {event_id}",
                text=text,
                structured_data=record,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return chunks


def _event_records(document: RawDocument) -> list[dict[str, object]]:
    if not document.payload_text:
        return []
    if records := _records_from_json(document.payload_text):
        return records
    feed = feedparser.parse(document.payload_text)
    return [_record_from_entry(entry) for entry in feed.entries]


def _records_from_json(payload: str) -> list[dict[str, object]]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        if isinstance(data.get("items"), list):
            return [item for item in data["items"] if isinstance(item, dict)]
        if data.get("gdacs_eventid") or data.get("guid") or data.get("title"):
            return [data]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _record_from_entry(entry: Any) -> dict[str, object]:
    tags_value = _entry_value(entry, "tags", default=[])
    tags = tags_value if isinstance(tags_value, list) else []
    record: dict[str, object] = {
        "guid": _entry_value(entry, "guid"),
        "link": _entry_value(entry, "link"),
        "canonical_url": _entry_value(entry, "link") or _entry_value(entry, "guid"),
        "title": _entry_value(entry, "title"),
        "summary": _entry_value(entry, "summary"),
        "published": _entry_value(entry, "published"),
        "updated": _entry_value(entry, "updated") or _entry_value(entry, "published"),
        "tags": [
            str(tag.get("term"))
            for tag in tags
            if isinstance(tag, dict) and tag.get("term") is not None
        ],
    }
    for key, value in entry.items():
        if key.startswith(("gdacs_", "geo_", "georss_", "dc_")):
            record[key] = _jsonable(value)
    return {key: value for key, value in record.items() if value not in (None, "")}


def _entry_value(entry: Any, key: str, default: object | None = None) -> object | None:
    if key not in entry:
        return default
    value: object = entry[key]
    return value


def _jsonable(value: Any) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _event_text(record: dict[str, Any]) -> str:
    severity = record.get("gdacs_severity")
    population = record.get("gdacs_population")
    fields = [
        f"Title: {record.get('title', '')}",
        f"Description: {record.get('summary', '')}",
        f"Event type: {record.get('gdacs_eventtype', '')}",
        f"Event ID: {record.get('gdacs_eventid', '')}",
        f"Episode ID: {record.get('gdacs_episodeid', '')}",
        f"Alert level: {record.get('gdacs_alertlevel', '')}",
        f"Alert score: {record.get('gdacs_alertscore', '')}",
        f"Episode alert level: {record.get('gdacs_episodealertlevel', '')}",
        f"From date: {record.get('gdacs_fromdate', '')}",
        f"To date: {record.get('gdacs_todate', '')}",
        f"Country: {record.get('gdacs_country', '')}",
        f"ISO3: {record.get('gdacs_iso3', '')}",
        f"Latitude: {record.get('geo_lat', '')}",
        f"Longitude: {record.get('geo_long', '')}",
        f"Severity: {_metric_text(severity)}",
        f"Population: {_metric_text(population)}",
        f"Vulnerability: {_metric_value(record.get('gdacs_vulnerability'))}",
        f"Link: {record.get('link', '')}",
        f"CAP: {record.get('gdacs_cap', '')}",
    ]
    return "\n".join(field for field in fields if not field.endswith(": "))


def _metric_text(value: object) -> str:
    if isinstance(value, dict):
        label = str(value.get("label") or value.get("value") or "").strip()
        unit = str(value.get("unit") or "").strip()
        if label and unit:
            return f"{label} {unit}"
        return label or unit
    return str(value or "").strip()


def _metric_value(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("value") or "").strip()
    return str(value or "").strip()
