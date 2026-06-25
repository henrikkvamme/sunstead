from __future__ import annotations

import json
import mimetypes
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from supply_intel.models.source import SourceConfig, SourceCursor, SourceRun
from supply_intel.sources.adapters.base import FetchedPayload, FetchPlan, FetchRequest


class ManualSeedAdapter:
    adapter_type = "manual_seed"

    async def plan_fetch(
        self,
        config: SourceConfig,
        cursor: SourceCursor | None,
        run: SourceRun,
        *,
        max_documents: int | None = None,
    ) -> FetchPlan:
        del cursor, run
        seed_path = config.fixtures.success or _path_from_base_url(config.base_url)
        if seed_path is None:
            raise ValueError("manual_seed sources require fixtures.success or a file:// base_url")
        return FetchPlan(
            requests=[FetchRequest(url=_file_url(seed_path))],
            max_documents=max_documents,
        )

    async def fetch(self, config: SourceConfig, plan: FetchPlan) -> AsyncIterator[FetchedPayload]:
        del config
        emitted = 0
        for request in plan.requests:
            seed_path = _path_from_base_url(request.url)
            if seed_path is None:
                raise ValueError(f"manual_seed request must be a local file URL: {request.url}")
            content_type = _content_type_for_path(seed_path)
            text = seed_path.read_text(encoding="utf-8")
            for index, record in enumerate(_records_from_seed(seed_path, text)):
                if plan.max_documents is not None and emitted >= plan.max_documents:
                    return
                emitted += 1
                yield FetchedPayload(
                    source_url=f"{_file_url(seed_path)}#record={index}",
                    status_code=200,
                    headers={},
                    content_type=content_type,
                    text=json.dumps(record, sort_keys=True),
                    record=record,
                )


def _path_from_base_url(value: str) -> Path | None:
    parsed = urlparse(value)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path))
    if parsed.scheme:
        return None
    return Path(value)


def _file_url(path: Path) -> str:
    return path.resolve().as_uri()


def _content_type_for_path(path: Path) -> str:
    if path.suffix == ".jsonl":
        return "application/x-ndjson"
    if path.suffix == ".json":
        return "application/json"
    return mimetypes.guess_type(path.name)[0] or "text/plain"


def _records_from_seed(path: Path, text: str) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return [_record_from_value(json.loads(line)) for line in text.splitlines() if line.strip()]
    if path.suffix == ".json":
        parsed = json.loads(text)
        if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
            return [_record_from_value(item) for item in parsed["results"]]
        if isinstance(parsed, list):
            return [_record_from_value(item) for item in parsed]
        return [_record_from_value(parsed)]
    return [{"value": text, "canonical_url": _file_url(path)}]


def _record_from_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"value": value}
