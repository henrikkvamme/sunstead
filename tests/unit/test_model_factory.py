from pydantic import BaseModel

from supply_intel.agents.factory import (
    DETERMINISTIC_MODEL_NAME,
    EmbeddingFactoryConfigError,
    ModelFactory,
    ModelFactoryConfigError,
)
from supply_intel.settings import Settings

DEFAULT_REQUEST_LIMIT = 3
DEFAULT_OUTPUT_TOKENS = 4096
LIVE_REQUEST_LIMIT = 5
LIVE_OUTPUT_TOKENS = 512
LIVE_EMBEDDING_DIMENSIONS = 768


class ExampleOutput(BaseModel):
    answer: str


def test_model_factory_defaults_to_deterministic_metadata_without_llm_config() -> None:
    factory = ModelFactory(
        Settings(
            _env_file=None,
            llm_base_url=None,
            llm_api_key=None,
            llm_api_key_file=None,
            llm_model=None,
        )
    )

    metadata = factory.runtime_metadata()
    embedding = factory.embedding_metadata()
    limits = factory.usage_limits()

    assert factory.configured_model_name == DETERMINISTIC_MODEL_NAME
    assert factory.is_llm_configured() is False
    assert metadata.model_name == DETERMINISTIC_MODEL_NAME
    assert metadata.provider == "deterministic"
    assert metadata.output_mode == "tool"
    assert metadata.configured is False
    assert metadata.api_key_configured is False
    assert "platform" not in metadata.model_dump_json()
    assert embedding.provider == "not_configured"
    assert embedding.configured is False
    assert limits.request_limit == DEFAULT_REQUEST_LIMIT
    assert limits.output_tokens_limit == DEFAULT_OUTPUT_TOKENS


def test_model_factory_fails_closed_for_live_agent_without_complete_config() -> None:
    factory = ModelFactory(
        Settings(
            _env_file=None,
            llm_base_url="https://llm.example.test/v1",
            llm_api_key=None,
            llm_api_key_file=None,
            llm_model="example-model",
        )
    )

    try:
        factory.openai_chat_model()
    except ModelFactoryConfigError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected missing LLM API key to fail closed")

    assert "LLM_API_KEY or LLM_API_KEY_FILE" in message
    assert "example-model" not in message


def test_model_factory_fails_closed_for_embedding_client_without_complete_config() -> None:
    factory = ModelFactory(
        Settings(
            _env_file=None,
            embedding_base_url="https://embedding.example.test/v1",
            embedding_api_key=None,
            embedding_api_key_file=None,
            embedding_model="text-embedding-test",
        )
    )

    try:
        factory.embedding_client()
    except EmbeddingFactoryConfigError as exc:
        message = str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected missing embedding API key to fail closed")

    assert "EMBEDDING_API_KEY or EMBEDDING_API_KEY_FILE" in message
    assert "text-embedding-test" not in message


def test_model_factory_builds_typed_pydantic_ai_agent_when_configured() -> None:
    factory = ModelFactory(
        Settings(
            _env_file=None,
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="secret-value",
            llm_model="openai/gpt-test",
            llm_output_mode="prompted",
            llm_max_retries=4,
            llm_max_output_tokens=LIVE_OUTPUT_TOKENS,
            embedding_base_url="https://embedding.example.test/v1",
            embedding_api_key="embedding-secret",
            embedding_model="text-embedding-test",
            embedding_dimensions=LIVE_EMBEDDING_DIMENSIONS,
        )
    )

    metadata = factory.runtime_metadata()
    embedding = factory.embedding_metadata()
    limits = factory.usage_limits()
    agent = factory.structured_agent(
        ExampleOutput,
        system_prompt="Return only supported facts.",
        name="example-agent",
    )
    embedding_client = factory.embedding_client()

    assert factory.is_llm_configured() is True
    assert metadata.provider == "openai-compatible"
    assert metadata.model_name == "openai/gpt-test"
    assert metadata.output_mode == "prompted"
    assert metadata.configured is True
    assert metadata.api_key_configured is True
    assert "secret-value" not in metadata.model_dump_json()
    assert embedding.provider == "openai-compatible"
    assert embedding.model_name == "text-embedding-test"
    assert embedding.dimensions == LIVE_EMBEDDING_DIMENSIONS
    assert "embedding-secret" not in embedding.model_dump_json()
    assert limits.request_limit == LIVE_REQUEST_LIMIT
    assert limits.output_tokens_limit == LIVE_OUTPUT_TOKENS
    assert agent.name == "example-agent"
    assert embedding_client.model_name == "text-embedding-test"
    assert embedding_client.dimensions == LIVE_EMBEDDING_DIMENSIONS
