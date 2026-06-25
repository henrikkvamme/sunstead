from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Protocol

import httpx

HTTP_BAD_REQUEST = 400


class EmbeddingClient(Protocol):
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...


class EmbeddingClientError(ValueError):
    """Raised when an embedding provider returns unusable output."""


class OpenAICompatibleEmbeddingClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        dimensions: int,
        timeout_seconds: int,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.dimensions = dimensions
        self.timeout_seconds = timeout_seconds
        self.http_client = http_client

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {
            "model": self.model_name,
            "input": list(texts),
            "dimensions": self.dimensions,
        }
        if self.http_client is not None:
            return self._embed_with_client(self.http_client, payload, expected_count=len(texts))
        with httpx.Client(timeout=self.timeout_seconds) as client:
            return self._embed_with_client(client, payload, expected_count=len(texts))

    def _embed_with_client(
        self,
        client: httpx.Client,
        payload: dict[str, object],
        *,
        expected_count: int,
    ) -> list[list[float]]:
        response = client.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
        )
        if response.status_code >= HTTP_BAD_REQUEST:
            raise EmbeddingClientError(
                f"Embedding provider request failed with HTTP {response.status_code}."
            )
        body = response.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != expected_count:
            raise EmbeddingClientError("Embedding provider returned an unexpected result count.")

        ordered = sorted(data, key=_embedding_index)
        return [self._parse_embedding(item) for item in ordered]

    def _parse_embedding(self, item: object) -> list[float]:
        if not isinstance(item, dict):
            raise EmbeddingClientError("Embedding provider returned a malformed item.")
        raw_embedding = item.get("embedding")
        if not isinstance(raw_embedding, list):
            raise EmbeddingClientError("Embedding provider returned a malformed vector.")
        vector = [_finite_float(value) for value in raw_embedding]
        if len(vector) != self.dimensions:
            raise EmbeddingClientError(
                f"Embedding provider returned {len(vector)} dimensions; expected {self.dimensions}."
            )
        return vector


def _embedding_index(item: object) -> int:
    if not isinstance(item, dict):
        return 0
    index = item.get("index")
    return index if isinstance(index, int) else 0


def _finite_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise EmbeddingClientError("Embedding provider returned a non-numeric value.") from exc
    if not math.isfinite(parsed):
        raise EmbeddingClientError("Embedding provider returned a non-finite value.")
    return parsed
