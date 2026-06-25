from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from pydantic_ai import Agent, NativeOutput, PromptedOutput, ToolOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from supply_intel.agents.embeddings import OpenAICompatibleEmbeddingClient
from supply_intel.models.base import StrictBaseModel
from supply_intel.settings import LLMOutputMode, Settings

OutputT = TypeVar("OutputT")
DETERMINISTIC_MODEL_NAME = "deterministic-local"


class ModelFactoryConfigError(ValueError):
    """Raised when a live model is requested without complete configuration."""


class EmbeddingFactoryConfigError(ValueError):
    """Raised when embeddings are requested without complete configuration."""


class ModelRuntimeMetadata(StrictBaseModel):
    provider: str
    model_name: str
    output_mode: LLMOutputMode
    configured: bool
    base_url_configured: bool
    api_key_configured: bool
    max_retries: int
    max_output_tokens: int


class EmbeddingRuntimeMetadata(StrictBaseModel):
    provider: str
    model_name: str | None
    configured: bool
    base_url_configured: bool
    api_key_configured: bool
    dimensions: int


@dataclass(frozen=True)
class ModelFactory:
    settings: Settings

    @property
    def configured_model_name(self) -> str:
        return self.settings.llm_model or DETERMINISTIC_MODEL_NAME

    def is_llm_configured(self) -> bool:
        return bool(
            self.settings.llm_base_url and self.settings.llm_api_key and self.settings.llm_model
        )

    def is_embedding_configured(self) -> bool:
        return bool(
            self.settings.embedding_base_url
            and self.settings.embedding_api_key
            and self.settings.embedding_model
        )

    def runtime_metadata(self) -> ModelRuntimeMetadata:
        return ModelRuntimeMetadata(
            provider="openai-compatible" if self.is_llm_configured() else "deterministic",
            model_name=self.configured_model_name,
            output_mode=self.settings.llm_output_mode,
            configured=self.is_llm_configured(),
            base_url_configured=self.settings.llm_base_url is not None,
            api_key_configured=self.settings.llm_api_key is not None,
            max_retries=self.settings.llm_max_retries,
            max_output_tokens=self.settings.llm_max_output_tokens,
        )

    def embedding_metadata(self) -> EmbeddingRuntimeMetadata:
        return EmbeddingRuntimeMetadata(
            provider="openai-compatible" if self.is_embedding_configured() else "not_configured",
            model_name=self.settings.embedding_model,
            configured=self.is_embedding_configured(),
            base_url_configured=self.settings.embedding_base_url is not None,
            api_key_configured=self.settings.embedding_api_key is not None,
            dimensions=self.settings.embedding_dimensions,
        )

    def usage_limits(self) -> UsageLimits:
        return UsageLimits(
            request_limit=max(1, self.settings.llm_max_retries + 1),
            output_tokens_limit=self.settings.llm_max_output_tokens,
        )

    def openai_provider(self) -> OpenAIProvider:
        self.require_llm_configured()
        return OpenAIProvider(
            base_url=self.settings.llm_base_url,
            api_key=self.settings.llm_api_key,
        )

    def openai_chat_model(self) -> OpenAIChatModel:
        self.require_llm_configured()
        return OpenAIChatModel(
            cast(Any, self.settings.llm_model),
            provider=self.openai_provider(),
        )

    def structured_agent(
        self,
        output_type: type[OutputT],
        *,
        system_prompt: str | Sequence[str] = (),
        name: str | None = None,
    ) -> Agent[object, OutputT]:
        return Agent(
            self.openai_chat_model(),
            output_type=cast(Any, self.structured_output_spec(output_type)),
            system_prompt=system_prompt,
            name=name,
            retries=self.settings.llm_max_retries,
        )

    def structured_output_spec(self, output_type: type[OutputT]) -> object:
        if self.settings.llm_output_mode == "prompted":
            return PromptedOutput(output_type)
        if self.settings.llm_output_mode == "native":
            return NativeOutput(output_type)
        return ToolOutput(output_type)

    def embedding_client(self) -> OpenAICompatibleEmbeddingClient:
        self.require_embedding_configured()
        return OpenAICompatibleEmbeddingClient(
            base_url=cast(str, self.settings.embedding_base_url),
            api_key=cast(str, self.settings.embedding_api_key),
            model_name=cast(str, self.settings.embedding_model),
            dimensions=self.settings.embedding_dimensions,
            timeout_seconds=self.settings.llm_timeout_seconds,
        )

    def require_llm_configured(self) -> None:
        missing = []
        if not self.settings.llm_base_url:
            missing.append("LLM_BASE_URL")
        if not self.settings.llm_api_key:
            missing.append("LLM_API_KEY or LLM_API_KEY_FILE")
        if not self.settings.llm_model:
            missing.append("LLM_MODEL")
        if missing:
            raise ModelFactoryConfigError(
                "Live Pydantic AI agents require " + ", ".join(missing) + "."
            )

    def require_embedding_configured(self) -> None:
        missing = []
        if not self.settings.embedding_base_url:
            missing.append("EMBEDDING_BASE_URL")
        if not self.settings.embedding_api_key:
            missing.append("EMBEDDING_API_KEY or EMBEDDING_API_KEY_FILE")
        if not self.settings.embedding_model:
            missing.append("EMBEDDING_MODEL")
        if missing:
            raise EmbeddingFactoryConfigError(
                "Chunk embeddings require " + ", ".join(missing) + "."
            )
