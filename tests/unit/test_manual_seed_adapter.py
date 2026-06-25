import json
from pathlib import Path

from supply_intel.models.source import (
    ComplianceConfig,
    DedupeConfig,
    FixtureConfig,
    ParserConfig,
    ScheduleConfig,
    SourceConfig,
    SourceRun,
)
from supply_intel.sources.adapters import adapter_for_source
from supply_intel.sources.adapters.manual import ManualSeedAdapter

HTTP_OK = 200


async def test_manual_seed_adapter_emits_jsonl_records_with_stable_source_urls(
    tmp_path: Path,
) -> None:
    seed_path = tmp_path / "manual_seed.jsonl"
    seed_path.write_text(
        "\n".join(
            [
                json.dumps({"seed_id": "one", "name": "First"}),
                json.dumps({"seed_id": "two", "name": "Second"}),
            ]
        ),
        encoding="utf-8",
    )
    config = _manual_seed_config(seed_path)
    run = _source_run(config)
    adapter = ManualSeedAdapter()

    plan = await adapter.plan_fetch(config, None, run, max_documents=1)
    payloads = [payload async for payload in adapter.fetch(config, plan)]

    assert len(payloads) == 1
    assert payloads[0].source_url == f"{seed_path.resolve().as_uri()}#record=0"
    assert payloads[0].status_code == HTTP_OK
    assert payloads[0].content_type == "application/x-ndjson"
    assert payloads[0].record == {"seed_id": "one", "name": "First"}
    assert json.loads(payloads[0].text)["seed_id"] == "one"


async def test_manual_seed_adapter_reads_results_array_from_json(tmp_path: Path) -> None:
    seed_path = tmp_path / "manual_seed.json"
    seed_path.write_text(
        json.dumps({"results": [{"seed_id": "one"}, {"seed_id": "two"}]}),
        encoding="utf-8",
    )
    config = _manual_seed_config(seed_path)
    run = _source_run(config)
    adapter = ManualSeedAdapter()

    plan = await adapter.plan_fetch(config, None, run)
    payloads = [payload async for payload in adapter.fetch(config, plan)]

    assert [payload.record for payload in payloads] == [{"seed_id": "one"}, {"seed_id": "two"}]


def test_adapter_for_source_supports_manual_seed_runtime(tmp_path: Path) -> None:
    assert isinstance(
        adapter_for_source(_manual_seed_config(tmp_path / "seed.jsonl")), ManualSeedAdapter
    )


def _manual_seed_config(seed_path: Path) -> SourceConfig:
    return SourceConfig(
        source_id="manual_seed_source",
        name="Manual Seed Source",
        source_type="manual_seed",
        adapter="manual_seed",
        base_url=seed_path.as_posix(),
        dedupe=DedupeConfig(key_fields=["seed_id"]),
        parser=ParserConfig(profile="openfda.drug_ndc.v1", chunking="json_record"),
        compliance=ComplianceConfig(
            robots="not_applicable_manual_seed",
            license_notes="Local seed data approved for test ingestion.",
            pii_expected=False,
        ),
        schedule=ScheduleConfig(cadence="1d"),
        fixtures=FixtureConfig(success=seed_path),
    )


def _source_run(config: SourceConfig) -> SourceRun:
    return SourceRun(
        source_id=config.source_id,
        run_type="test",
        status="running",
        idempotency_key=f"test:{config.source_id}",
    )
