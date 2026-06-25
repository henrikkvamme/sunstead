from __future__ import annotations

from typing import Literal

from pydantic import Field

from supply_intel.agents.factory import ModelFactory, ModelRuntimeMetadata
from supply_intel.models.base import StrictBaseModel

DEFAULT_LLM_SMOKE_PROMPT = (
    "Extract a one sentence supply-chain risk signal from this note: "
    "An injectable medicine has one active supplier, an FDA shortage signal, "
    "and recent energy-price pressure near a key manufacturing region."
)


class LLMSmokeOutput(StrictBaseModel):
    status: Literal["ok"]
    risk_signal: str = Field(min_length=1, max_length=240)
    extracted_entities: list[str] = Field(default_factory=list, max_length=8)


class LLMSmokeReport(StrictBaseModel):
    ok: bool
    runtime: ModelRuntimeMetadata
    output: LLMSmokeOutput | None = None
    usage: dict[str, object] = Field(default_factory=dict)
    error_type: str | None = None
    error: str | None = None


async def run_llm_smoke(
    factory: ModelFactory,
    *,
    prompt: str = DEFAULT_LLM_SMOKE_PROMPT,
) -> LLMSmokeReport:
    metadata = factory.runtime_metadata()
    factory.require_llm_configured()
    agent = factory.structured_agent(
        LLMSmokeOutput,
        system_prompt=(
            "Return only validated structured data. Keep the risk signal concise, "
            "factual, and suitable for an operations dashboard."
        ),
        name="llm-smoke",
    )
    result = await agent.run(prompt, usage_limits=factory.usage_limits())
    output = LLMSmokeOutput.model_validate(result.output)
    return LLMSmokeReport(
        ok=True,
        runtime=metadata,
        output=output,
        usage=_usage_to_dict(result),
    )


def failed_llm_smoke_report(
    factory: ModelFactory,
    *,
    error_type: str,
    error: str,
) -> LLMSmokeReport:
    return LLMSmokeReport(
        ok=False,
        runtime=factory.runtime_metadata(),
        error_type=error_type,
        error=error,
    )


def _usage_to_dict(result: object) -> dict[str, object]:
    usage = getattr(result, "usage", None)
    if callable(usage):
        usage = usage()
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        dumped = usage.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    if isinstance(usage, dict):
        return dict(usage)
    return {
        key: value
        for key, value in vars(usage).items()
        if not key.startswith("_") and isinstance(key, str)
    }
