from __future__ import annotations

import csv
import hashlib
import io
from datetime import UTC, datetime, timedelta
from typing import Any

from supply_intel.models.documents import DocumentChunk
from supply_intel.models.source import RawDocument

EXCEL_DATE_ORIGIN = datetime(1899, 12, 30, tzinfo=UTC)


def parse_freight_proxy_prices_document(document: RawDocument) -> list[DocumentChunk]:
    record = _latest_gscpi_record(document)
    if record is None:
        return []
    text = _pressure_text(record)
    return [
        DocumentChunk(
            raw_document_id=document.id,
            chunk_index=0,
            chunk_type="logistics_pressure_observation",
            title=f"New York Fed GSCPI {record['observation_date']}",
            text=text,
            structured_data=record,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
    ]


def _latest_gscpi_record(document: RawDocument) -> dict[str, object] | None:
    if not document.payload_text:
        return None
    rows = list(csv.DictReader(io.StringIO(document.payload_text)))
    if not rows:
        return None
    value_columns = [column for column in rows[0] if column and column != "Date"]
    if not value_columns:
        return None
    latest_vintage_column = value_columns[-1]
    records: list[dict[str, object]] = []
    for row in rows:
        observed_at = _parse_observation_date(str(row.get("Date") or ""))
        value = _float_value(row.get(latest_vintage_column))
        if observed_at is None or value is None:
            continue
        records.append(
            {
                "index_name": "New York Fed Global Supply Chain Pressure Index",
                "source_series": "GSCPI",
                "observation_date": observed_at.date().isoformat(),
                "value": value,
                "unit": "standard_deviations_from_average",
                "latest_vintage_serial": latest_vintage_column,
                "latest_vintage_date": _excel_serial_date(latest_vintage_column),
                "source_file": "gscpi_interactive_data.csv",
            }
        )
    if not records:
        return None
    return max(records, key=lambda record: str(record["observation_date"]))


def _parse_observation_date(value: str) -> datetime | None:
    for date_format in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), date_format).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _excel_serial_date(value: str) -> str | None:
    if not value.isdigit():
        return None
    return (EXCEL_DATE_ORIGIN + timedelta(days=int(value))).date().isoformat()


def _float_value(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text in {"NA", "N/A", "--", "-", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _pressure_text(record: dict[str, Any]) -> str:
    fields = [
        f"Index: {record.get('index_name', '')}",
        f"Series: {record.get('source_series', '')}",
        f"Observation date: {record.get('observation_date', '')}",
        f"Value: {record.get('value', '')}",
        f"Unit: {record.get('unit', '')}",
        f"Latest vintage serial: {record.get('latest_vintage_serial', '')}",
        f"Latest vintage date: {record.get('latest_vintage_date', '')}",
        f"Source file: {record.get('source_file', '')}",
    ]
    return "\n".join(field for field in fields if not field.endswith(": "))
