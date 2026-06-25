from __future__ import annotations

import hashlib

from bs4 import BeautifulSoup

from supply_intel.models.documents import DocumentChunk
from supply_intel.models.source import RawDocument


def parse_fda_drug_shortages_document(document: RawDocument) -> list[DocumentChunk]:
    if not document.payload_text:
        return []
    soup = BeautifulSoup(document.payload_text, "html.parser")
    rows = _table_rows(soup)
    chunks: list[DocumentChunk] = []
    for index, row in enumerate(rows):
        text = _row_text(row)
        if not text.strip():
            continue
        chunks.append(
            DocumentChunk(
                raw_document_id=document.id,
                chunk_index=index,
                chunk_type="html_section",
                title=row.get("generic_name") or row.get("drug_name"),
                text=text,
                structured_data=row,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return chunks


def _table_rows(soup: BeautifulSoup) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for table in soup.find_all("table"):
        headers = [
            _normalize_header(cell.get_text(" ", strip=True)) for cell in table.find_all("th")
        ]
        if not headers:
            continue
        for tr in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.find_all("td")]
            if not cells:
                continue
            row = {
                headers[index]: value
                for index, value in enumerate(cells[: len(headers)])
                if headers[index] and value
            }
            if row:
                rows.append(row)
    return rows


def _normalize_header(value: str) -> str:
    normalized = "_".join(part for part in value.casefold().split() if part)
    aliases = {
        "generic_name": "generic_name",
        "generic_name_or_active_ingredient": "generic_name",
        "active_ingredient": "generic_name",
        "drug_name": "generic_name",
        "status": "status",
        "presentation": "presentation",
        "availability": "presentation",
        "company": "company",
        "reason": "reason",
        "reason_for_shortage": "reason",
        "update_date": "update_date",
        "date_updated": "update_date",
    }
    return aliases.get(normalized, normalized)


def _row_text(row: dict[str, str]) -> str:
    fields = [
        f"Generic name: {row.get('generic_name', '')}",
        f"Status: {row.get('status', '')}",
        f"Presentation: {row.get('presentation', '')}",
        f"Company: {row.get('company', '')}",
        f"Reason: {row.get('reason', '')}",
        f"Update date: {row.get('update_date', '')}",
    ]
    return "\n".join(field for field in fields if not field.endswith(": "))
