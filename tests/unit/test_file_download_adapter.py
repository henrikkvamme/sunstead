import base64
import hashlib
import json
from pathlib import Path

from supply_intel.db.repositories.evidence import FileEvidenceStore
from supply_intel.models.source import (
    ComplianceConfig,
    DedupeConfig,
    ParserConfig,
    ScheduleConfig,
    SourceConfig,
    SourceRun,
)
from supply_intel.pipeline import raw_document_from_payload
from supply_intel.sources.adapters import adapter_for_source
from supply_intel.sources.adapters.file_download import FileDownloadAdapter

HTTP_OK = 200


async def test_file_download_adapter_reads_local_binary_file(tmp_path: Path) -> None:
    download_path = tmp_path / "safety-notice.pdf"
    content = b"%PDF-1.7\nbinary-\xff\n"
    download_path.write_bytes(content)
    config = _file_download_config(download_path)
    run = _source_run(config)
    adapter = FileDownloadAdapter()

    plan = await adapter.plan_fetch(config, None, run, max_documents=1)
    payloads = [payload async for payload in adapter.fetch(config, plan)]

    assert len(payloads) == 1
    assert payloads[0].source_url == download_path.resolve().as_uri()
    assert payloads[0].status_code == HTTP_OK
    assert payloads[0].content_type == "application/pdf"
    assert payloads[0].content_bytes == content
    assert payloads[0].record is not None
    assert payloads[0].record["content_hash"] == hashlib.sha256(content).hexdigest()


async def test_file_download_payload_becomes_raw_document_with_payload_bytes(
    tmp_path: Path,
) -> None:
    download_path = tmp_path / "safety-notice.pdf"
    content = b"%PDF-1.7\nbinary-\xff\n"
    download_path.write_bytes(content)
    config = _file_download_config(download_path)
    run = _source_run(config)
    adapter = FileDownloadAdapter()
    plan = await adapter.plan_fetch(config, None, run, max_documents=1)
    payload = [item async for item in adapter.fetch(config, plan)][0]

    document = raw_document_from_payload(config=config, run=run, payload=payload)
    store = FileEvidenceStore(tmp_path / "store")
    inserted = store.write_raw_document(document)

    assert inserted is True
    assert document.content_hash == hashlib.sha256(content).hexdigest()
    assert document.content_length == len(content)
    assert document.payload_bytes == content
    assert document.payload_text is None
    assert document.dedupe_key == download_path.resolve().as_uri()
    raw_rows = (tmp_path / "store" / "raw_documents.jsonl").read_text(encoding="utf-8")
    row = json.loads(raw_rows.splitlines()[0])
    assert row["payload_bytes"] == base64.b64encode(content).decode("ascii")


def test_adapter_for_source_supports_file_download_runtime(tmp_path: Path) -> None:
    assert isinstance(
        adapter_for_source(_file_download_config(tmp_path / "safety-notice.pdf")),
        FileDownloadAdapter,
    )


def _file_download_config(download_path: Path) -> SourceConfig:
    return SourceConfig(
        source_id="file_download_source",
        name="File Download Source",
        source_type="government_file",
        adapter="file_download",
        base_url=download_path.as_posix(),
        dedupe=DedupeConfig(key_fields=["canonical_url"]),
        parser=ParserConfig(profile="openfda.drug_ndc.v1", chunking="document"),
        compliance=ComplianceConfig(
            robots="validate_before_download",
            license_notes="Public test file.",
            pii_expected=False,
        ),
        schedule=ScheduleConfig(cadence="1d"),
    )


def _source_run(config: SourceConfig) -> SourceRun:
    return SourceRun(
        source_id=config.source_id,
        run_type="test",
        status="running",
        idempotency_key=f"test:{config.source_id}",
    )
