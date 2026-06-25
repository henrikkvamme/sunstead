from __future__ import annotations

import asyncio
from typing import Any

from typer.testing import CliRunner

from supply_intel.agents.factory import ModelRuntimeMetadata
from supply_intel.agents.smoke import (
    DEFAULT_LLM_SMOKE_PROMPT,
    LLMSmokeOutput,
    LLMSmokeReport,
    run_llm_smoke,
)
from supply_intel.cli import app
from supply_intel.settings import Settings

SMOKE_INPUT_TOKENS = 14
SMOKE_OUTPUT_TOKENS = 21


class FakeUsage:
    def model_dump(self, *, mode: str) -> dict[str, int | str]:
        return {
            "mode": mode,
            "input_tokens": SMOKE_INPUT_TOKENS,
            "output_tokens": SMOKE_OUTPUT_TOKENS,
            "requests": 1,
        }


class FakeResult:
    output = LLMSmokeOutput(
        status="ok",
        risk_signal="Single supplier plus shortage pressure raises continuity risk.",
        extracted_entities=["injectable medicine", "FDA shortage", "energy prices"],
    )

    def usage(self) -> FakeUsage:
        return FakeUsage()


class FakeAgent:
    def __init__(self) -> None:
        self.prompt: str | None = None
        self.usage_limits: object | None = None

    async def run(self, prompt: str, *, usage_limits: object) -> FakeResult:
        self.prompt = prompt
        self.usage_limits = usage_limits
        return FakeResult()


class FakeFactory:
    def __init__(self) -> None:
        self.agent = FakeAgent()
        self.required = False

    def runtime_metadata(self) -> ModelRuntimeMetadata:
        return ModelRuntimeMetadata(
            provider="openai-compatible",
            model_name="demo-model",
            output_mode="prompted",
            configured=True,
            base_url_configured=True,
            api_key_configured=True,
            max_retries=2,
            max_output_tokens=256,
        )

    def require_llm_configured(self) -> None:
        self.required = True

    def structured_agent(
        self,
        output_type: type[LLMSmokeOutput],
        *,
        system_prompt: str,
        name: str,
    ) -> FakeAgent:
        assert output_type is LLMSmokeOutput
        assert "validated structured data" in system_prompt
        assert name == "llm-smoke"
        return self.agent

    def usage_limits(self) -> dict[str, bool]:
        return {"bounded": True}


def test_run_llm_smoke_returns_typed_output_and_usage() -> None:
    factory = FakeFactory()

    report = asyncio.run(run_llm_smoke(factory))  # type: ignore[arg-type]

    assert factory.required is True
    assert factory.agent.prompt == DEFAULT_LLM_SMOKE_PROMPT
    assert factory.agent.usage_limits == {"bounded": True}
    assert report.ok is True
    assert report.runtime.model_name == "demo-model"
    assert report.output is not None
    assert report.output.status == "ok"
    assert report.usage["input_tokens"] == SMOKE_INPUT_TOKENS
    assert report.usage["output_tokens"] == SMOKE_OUTPUT_TOKENS


def test_llm_smoke_cli_prints_success_report(monkeypatch: Any) -> None:
    async def fake_run_llm_smoke(*_args: object, **_kwargs: object) -> LLMSmokeReport:
        return LLMSmokeReport(
            ok=True,
            runtime=ModelRuntimeMetadata(
                provider="openai-compatible",
                model_name="demo-model",
                output_mode="prompted",
                configured=True,
                base_url_configured=True,
                api_key_configured=True,
                max_retries=2,
                max_output_tokens=256,
            ),
            output=LLMSmokeOutput(
                status="ok",
                risk_signal="The configured model returned structured output.",
                extracted_entities=["configured model"],
            ),
            usage={"requests": 1},
        )

    monkeypatch.setattr("supply_intel.cli.run_llm_smoke", fake_run_llm_smoke)
    monkeypatch.setattr(
        "supply_intel.cli.get_settings",
        lambda secret_file_loading="strict": Settings(
            _env_file=None,
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="secret-value",
            llm_model="demo-model",
        ),
    )

    result = CliRunner().invoke(app, ["llm-smoke"])

    assert result.exit_code == 0
    assert "demo-model" in result.output
    assert "secret-value" not in result.output


def test_llm_smoke_cli_hides_provider_exception_details(monkeypatch: Any) -> None:
    async def fake_run_llm_smoke(*_args: object, **_kwargs: object) -> LLMSmokeReport:
        raise RuntimeError("provider rejected secret-value")

    monkeypatch.setattr("supply_intel.cli.run_llm_smoke", fake_run_llm_smoke)
    monkeypatch.setattr(
        "supply_intel.cli.get_settings",
        lambda secret_file_loading="strict": Settings(
            _env_file=None,
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="secret-value",
            llm_model="demo-model",
        ),
    )

    result = CliRunner().invoke(app, ["llm-smoke"])

    assert result.exit_code == 1
    assert "RuntimeError" in result.output
    assert "Structured LLM smoke failed" in result.output
    assert "provider rejected" not in result.output
    assert "secret-value" not in result.output
