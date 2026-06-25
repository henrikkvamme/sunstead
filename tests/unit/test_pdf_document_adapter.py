import hashlib
from pathlib import Path

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
from supply_intel.sources.adapters.document import PdfDocumentAdapter

HTTP_OK = 200
PDF_OBJECT_COUNT = 6
PDF_TEXT = "Supply chain notice"


async def test_pdf_document_adapter_extracts_text_and_preserves_bytes(tmp_path: Path) -> None:
    pdf_path = tmp_path / "notice.pdf"
    pdf_bytes = _minimal_pdf(PDF_TEXT)
    pdf_path.write_bytes(pdf_bytes)
    config = _pdf_config(pdf_path)
    run = _source_run(config)
    adapter = PdfDocumentAdapter()

    plan = await adapter.plan_fetch(config, None, run, max_documents=1)
    payloads = [payload async for payload in adapter.fetch(config, plan)]

    assert len(payloads) == 1
    assert payloads[0].status_code == HTTP_OK
    assert payloads[0].source_url == pdf_path.resolve().as_uri()
    assert payloads[0].content_type == "application/pdf"
    assert payloads[0].content_bytes == pdf_bytes
    assert payloads[0].text == PDF_TEXT
    assert payloads[0].record is not None
    assert payloads[0].record["page_count"] == 1
    assert payloads[0].record["content_hash"] == hashlib.sha256(pdf_bytes).hexdigest()


async def test_pdf_document_raw_document_keeps_bytes_and_extracted_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "notice.pdf"
    pdf_bytes = _minimal_pdf(PDF_TEXT)
    pdf_path.write_bytes(pdf_bytes)
    config = _pdf_config(pdf_path)
    run = _source_run(config)
    adapter = PdfDocumentAdapter()
    plan = await adapter.plan_fetch(config, None, run, max_documents=1)
    payload = [item async for item in adapter.fetch(config, plan)][0]

    document = raw_document_from_payload(config=config, run=run, payload=payload)

    assert document.content_hash == hashlib.sha256(pdf_bytes).hexdigest()
    assert document.content_length == len(pdf_bytes)
    assert document.payload_bytes == pdf_bytes
    assert document.payload_text == PDF_TEXT
    assert document.dedupe_key == pdf_path.resolve().as_uri()


def test_adapter_for_source_supports_pdf_document_runtime(tmp_path: Path) -> None:
    assert isinstance(adapter_for_source(_pdf_config(tmp_path / "notice.pdf")), PdfDocumentAdapter)


def _pdf_config(pdf_path: Path) -> SourceConfig:
    return SourceConfig(
        source_id="pdf_document_source",
        name="PDF Document Source",
        source_type="government_document",
        adapter="pdf_document",
        base_url=pdf_path.as_posix(),
        dedupe=DedupeConfig(key_fields=["canonical_url"]),
        parser=ParserConfig(profile="openfda.drug_ndc.v1", chunking="pdf_document"),
        compliance=ComplianceConfig(
            robots="validate_before_download",
            license_notes="Public test document.",
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


def _minimal_pdf(text: str) -> bytes:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = f"BT /F1 24 Tf 100 700 Td ({escaped}) Tj ET"
    objects = [
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            "3 0 obj\n"
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\n"
            "endobj\n"
        ),
        "4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        f"5 0 obj\n<< /Length {len(content)} >>\nstream\n{content}\nendstream\nendobj\n",
    ]
    header = b"%PDF-1.4\n"
    body = b""
    offsets: list[int] = []
    for item in objects:
        offsets.append(len(header) + len(body))
        body += item.encode("ascii")
    xref_offset = len(header) + len(body)
    xref_rows = ["0000000000 65535 f \n", *[f"{offset:010d} 00000 n \n" for offset in offsets]]
    xref = "xref\n0 6\n" + "".join(xref_rows)
    trailer = (
        f"trailer\n<< /Size {PDF_OBJECT_COUNT} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    )
    return header + body + xref.encode("ascii") + trailer.encode("ascii")
