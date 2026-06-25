from __future__ import annotations

import hashlib
import json
from typing import Any

from supply_intel.models.documents import DocumentChunk
from supply_intel.models.source import RawDocument

RECENT_FILINGS_PATH = ("filings", "recent")


def parse_sec_edgar_supplier_filings_document(
    document: RawDocument,
    *,
    max_records: int | None = None,
) -> list[DocumentChunk]:
    records = _filing_records(document)
    if max_records is not None:
        records = records[:max_records]
    chunks: list[DocumentChunk] = []
    for index, record in enumerate(records):
        accession_number = str(record.get("accession_number", "")).strip()
        form = str(record.get("form", "")).strip()
        if not accession_number or not form:
            continue
        text = _filing_text(record)
        chunks.append(
            DocumentChunk(
                raw_document_id=document.id,
                chunk_index=index,
                chunk_type="sec_filing_metadata",
                title=f"{record.get('issuer_name', 'SEC issuer')} {form} {accession_number}",
                text=text,
                structured_data=record,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return chunks


def _filing_records(document: RawDocument) -> list[dict[str, object]]:
    if not document.payload_text:
        return []
    try:
        data = json.loads(document.payload_text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict) and isinstance(data.get("filings"), list):
        return [record for record in data["filings"] if isinstance(record, dict)]
    if not isinstance(data, dict):
        return []
    recent = _recent_filings(data)
    issuer = _issuer_metadata(data)
    return [_normalize_filing(record, issuer) for record in recent]


def _recent_filings(data: dict[str, object]) -> list[dict[str, object]]:
    current: object = data
    for path_part in RECENT_FILINGS_PATH:
        if not isinstance(current, dict):
            return []
        current = current.get(path_part)
    if not isinstance(current, dict):
        return []
    accession_numbers = current.get("accessionNumber")
    if not isinstance(accession_numbers, list):
        return []
    records: list[dict[str, object]] = []
    for index, accession_number in enumerate(accession_numbers):
        record = {
            _snake_case(key): _column_value(value, index)
            for key, value in current.items()
            if isinstance(value, list)
        }
        record["accession_number"] = accession_number
        records.append(record)
    return records


def _issuer_metadata(data: dict[str, object]) -> dict[str, object]:
    cik = str(data.get("cik") or "").strip()
    cik_padded = cik.zfill(10) if cik.isdigit() else cik
    return {
        "issuer_cik": cik_padded,
        "issuer_cik_int": str(int(cik)) if cik.isdigit() else cik,
        "issuer_name": str(data.get("name") or "").strip(),
        "entity_type": str(data.get("entityType") or "").strip(),
        "sic": str(data.get("sic") or "").strip(),
        "sic_description": str(data.get("sicDescription") or "").strip(),
        "owner_org": str(data.get("ownerOrg") or "").strip(),
        "tickers": _string_list(data.get("tickers")),
        "exchanges": _string_list(data.get("exchanges")),
        "category": str(data.get("category") or "").strip(),
        "fiscal_year_end": str(data.get("fiscalYearEnd") or "").strip(),
    }


def _normalize_filing(
    record: dict[str, object],
    issuer: dict[str, object],
) -> dict[str, object]:
    accession_number = str(record.get("accession_number") or "").strip()
    primary_document = str(record.get("primary_document") or "").strip()
    normalized = dict(issuer)
    normalized.update(record)
    normalized["accession_number"] = accession_number
    normalized["accession_no_dashes"] = accession_number.replace("-", "")
    normalized["primary_document"] = primary_document
    normalized["primary_document_url"] = _primary_document_url(
        issuer_cik_int=str(issuer.get("issuer_cik_int") or ""),
        accession_no_dashes=str(normalized["accession_no_dashes"]),
        primary_document=primary_document,
    )
    normalized["accession_index_url"] = _accession_index_url(
        issuer_cik_int=str(issuer.get("issuer_cik_int") or ""),
        accession_no_dashes=str(normalized["accession_no_dashes"]),
    )
    return normalized


def _primary_document_url(
    *,
    issuer_cik_int: str,
    accession_no_dashes: str,
    primary_document: str,
) -> str:
    if not issuer_cik_int or not accession_no_dashes or not primary_document:
        return ""
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{issuer_cik_int}/{accession_no_dashes}/{primary_document}"
    )


def _accession_index_url(*, issuer_cik_int: str, accession_no_dashes: str) -> str:
    if not issuer_cik_int or not accession_no_dashes:
        return ""
    return f"https://www.sec.gov/Archives/edgar/data/{issuer_cik_int}/{accession_no_dashes}/"


def _column_value(value: list[object], index: int) -> object:
    if index >= len(value):
        return ""
    item = value[index]
    return item if item is not None else ""


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _snake_case(value: str) -> str:
    chars: list[str] = []
    for char in value:
        if char.isupper() and chars:
            chars.append("_")
        chars.append(char.lower() if char.isalnum() else "_")
    return "_".join(part for part in "".join(chars).split("_") if part)


def _filing_text(record: dict[str, Any]) -> str:
    tickers = record.get("tickers")
    ticker_text = ", ".join(tickers) if isinstance(tickers, list) else ""
    fields = [
        f"Issuer: {record.get('issuer_name', '')}",
        f"CIK: {record.get('issuer_cik', '')}",
        f"Tickers: {ticker_text}",
        f"SIC: {record.get('sic', '')}",
        f"SIC description: {record.get('sic_description', '')}",
        f"Form: {record.get('form', '')}",
        f"Accession number: {record.get('accession_number', '')}",
        f"Filing date: {record.get('filing_date', '')}",
        f"Report date: {record.get('report_date', '')}",
        f"Acceptance date time: {record.get('acceptance_date_time', '')}",
        f"Items: {record.get('items', '')}",
        f"Primary document: {record.get('primary_document', '')}",
        f"Primary document description: {record.get('primary_doc_description', '')}",
        f"Primary document URL: {record.get('primary_document_url', '')}",
    ]
    return "\n".join(field for field in fields if not field.endswith(": "))
