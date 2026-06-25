from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from supply_intel.models.source import SourceConfig, SourceCursor, SourceRun


@dataclass(frozen=True)
class FetchRequest:
    url: str
    params: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FetchPlan:
    requests: list[FetchRequest]
    max_documents: int | None = None


@dataclass(frozen=True)
class FetchedPayload:
    source_url: str
    status_code: int
    headers: dict[str, str]
    content_type: str | None
    text: str
    content_bytes: bytes | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    record: dict[str, Any] | None = None


class SourceAdapter(Protocol):
    adapter_type: str

    async def plan_fetch(
        self,
        config: SourceConfig,
        cursor: SourceCursor | None,
        run: SourceRun,
        *,
        max_documents: int | None = None,
    ) -> FetchPlan: ...

    def fetch(
        self,
        config: SourceConfig,
        plan: FetchPlan,
    ) -> AsyncIterator[FetchedPayload]: ...
