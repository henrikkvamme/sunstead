import json
from collections.abc import Sequence
from uuid import uuid4

import httpx

from supply_intel.agents.embeddings import OpenAICompatibleEmbeddingClient
from supply_intel.agents.factory import ModelFactory
from supply_intel.models.documents import DocumentChunk
from supply_intel.pipeline import attach_configured_chunk_embeddings
from supply_intel.settings import Settings

EMBEDDING_DIMENSIONS = 2


class FakeEmbeddingClient:
    def __init__(self, embeddings: list[list[float]]) -> None:
        self.embeddings = embeddings
        self.requests: list[str] = []

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.requests = list(texts)
        return self.embeddings


def test_openai_compatible_embedding_client_posts_batch_and_orders_vectors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert str(request.url) == "https://embedding.example.test/v1/embeddings"
        assert request.headers["authorization"] == "Bearer secret-value"
        assert payload == {
            "model": "text-embedding-test",
            "input": ["first", "second"],
            "dimensions": EMBEDDING_DIMENSIONS,
        }
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ]
            },
        )

    client = OpenAICompatibleEmbeddingClient(
        base_url="https://embedding.example.test/v1/",
        api_key="secret-value",
        model_name="text-embedding-test",
        dimensions=EMBEDDING_DIMENSIONS,
        timeout_seconds=5,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    vectors = client.embed_texts(["first", "second"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


def test_attach_configured_chunk_embeddings_sets_vector_and_model() -> None:
    factory = ModelFactory(
        Settings(
            embedding_base_url="https://embedding.example.test/v1",
            embedding_api_key="secret-value",
            embedding_model="text-embedding-test",
            embedding_dimensions=EMBEDDING_DIMENSIONS,
        )
    )
    chunks = [
        DocumentChunk(
            raw_document_id=uuid4(),
            chunk_index=0,
            chunk_type="json_record",
            text="Acetaminophen tablet",
            content_hash="hash-1",
        )
    ]
    fake_client = FakeEmbeddingClient([[0.1, 0.2]])
    stats: dict[str, int] = {}

    attach_configured_chunk_embeddings(
        chunks=chunks,
        model_factory=factory,
        stats=stats,
        embedding_client=fake_client,
    )

    assert fake_client.requests == ["Acetaminophen tablet"]
    assert chunks[0].embedding == [0.1, 0.2]
    assert chunks[0].embedding_model == "text-embedding-test"
    assert stats["chunk_embeddings"] == 1


def test_attach_configured_chunk_embeddings_skips_unconfigured_runtime() -> None:
    chunks = [
        DocumentChunk(
            raw_document_id=uuid4(),
            chunk_index=0,
            chunk_type="json_record",
            text="No provider configured",
            content_hash="hash-1",
        )
    ]
    fake_client = FakeEmbeddingClient([[0.1, 0.2]])
    stats: dict[str, int] = {}

    attach_configured_chunk_embeddings(
        chunks=chunks,
        model_factory=ModelFactory(Settings()),
        stats=stats,
        embedding_client=fake_client,
    )

    assert fake_client.requests == []
    assert chunks[0].embedding is None
    assert "chunk_embeddings" not in stats
