from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from supply_intel.models.source import SourceConfig, SourceCursor, SourceRun
from supply_intel.sources.adapters.base import FetchedPayload

COMPACT_DATE_LENGTH = 8


def source_cursor_snapshot(cursor: SourceCursor | None) -> dict[str, object]:
    if cursor is None:
        return {}
    return cursor.model_dump(
        mode="json",
        exclude={"id", "created_at", "updated_at", "metadata", "schema_version"},
    )


def source_cursor_from_payloads(
    *,
    config: SourceConfig,
    run: SourceRun,
    payloads: list[FetchedPayload],
) -> SourceCursor:
    if not payloads:
        raise ValueError("Cannot create a source cursor from an empty payload list")
    content_hashes = [_payload_hash(payload) for payload in payloads]
    last_payload = payloads[-1]
    headers = {key.casefold(): value for key, value in last_payload.headers.items()}
    cursor_state: dict[str, Any] = {
        "documents_seen": len(payloads),
        "last_source_url": last_payload.source_url,
        "last_fetched_at": last_payload.fetched_at,
        "content_hashes": content_hashes,
    }
    last_modified = headers.get("last-modified")
    if last_modified:
        cursor_state["last_modified"] = last_modified
    watermark = _watermark_from_payloads(config, payloads) or max(
        payload.fetched_at for payload in payloads
    )
    return SourceCursor(
        source_id=config.source_id,
        cursor_state=cursor_state,
        watermark=watermark,
        etag=headers.get("etag"),
        last_content_hash=content_hashes[-1],
        updated_by_run_id=run.id,
    )


def _payload_hash(payload: FetchedPayload) -> str:
    body = payload.content_bytes or payload.text.encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _watermark_from_payloads(
    config: SourceConfig,
    payloads: list[FetchedPayload],
) -> datetime | None:
    if config.cursor.field is None:
        return None
    values = [
        _coerce_datetime((payload.record or {}).get(config.cursor.field)) for payload in payloads
    ]
    parsed = [value for value in values if value is not None]
    return max(parsed) if parsed else None


def _coerce_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return None
    normalized = value.strip()
    if len(normalized) == COMPACT_DATE_LENGTH and normalized.isdigit():
        return datetime.fromisoformat(
            f"{normalized[0:4]}-{normalized[4:6]}-{normalized[6:8]}T00:00:00+00:00"
        )
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
