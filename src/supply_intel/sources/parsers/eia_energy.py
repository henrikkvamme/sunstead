from __future__ import annotations

import hashlib
import json
from typing import Any

from supply_intel.models.documents import DocumentChunk
from supply_intel.models.source import RawDocument


def parse_eia_energy_prices_document(document: RawDocument) -> list[DocumentChunk]:
    records = _energy_price_records(document)
    chunks: list[DocumentChunk] = []
    for index, record in enumerate(records):
        period = str(record.get("period", "")).strip()
        value = _float_value(record.get("value"))
        if not period or value is None:
            continue
        normalized = _normalized_record(record, value)
        text = _price_text(normalized)
        chunks.append(
            DocumentChunk(
                raw_document_id=document.id,
                chunk_index=index,
                chunk_type="energy_price_observation",
                title=f"{normalized['commodity_name']} {period}",
                text=text,
                structured_data=normalized,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return chunks


def _energy_price_records(document: RawDocument) -> list[dict[str, object]]:
    if not document.payload_text:
        return []
    try:
        data = json.loads(document.payload_text)
    except json.JSONDecodeError:
        return []
    records: list[object] = []
    if isinstance(data, dict):
        response = data.get("response")
        if isinstance(response, dict) and isinstance(response.get("data"), list):
            records = response["data"]
        elif isinstance(data.get("data"), list):
            records = data["data"]
        elif data.get("period") is not None and data.get("value") is not None:
            records = [data]
    elif isinstance(data, list):
        records = data
    return [record for record in records if isinstance(record, dict)]


def _normalized_record(record: dict[str, object], value: float) -> dict[str, object]:
    product_name = _first_text(
        record,
        "product-name",
        "product_name",
        "series-description",
        "series_description",
    )
    area_name = _first_text(record, "duoarea-name", "area-name", "area_name", "duoarea")
    process_name = _first_text(record, "process-name", "process_name", "process")
    series_description = _first_text(record, "series-description", "series_description")
    commodity_name = _commodity_name(
        product_name=product_name,
        area_name=area_name,
        series_description=series_description,
    )
    return {
        "period": str(record.get("period") or "").strip(),
        "frequency": str(record.get("frequency") or "").strip(),
        "commodity_name": commodity_name,
        "value": value,
        "raw_unit": _first_text(record, "units", "unit"),
        "product_code": _first_text(record, "product", "product_code"),
        "product_name": product_name,
        "process_code": _first_text(record, "process", "process_code"),
        "process_name": process_name,
        "area_code": _first_text(record, "duoarea", "area", "area_code"),
        "area_name": area_name,
        "series_description": series_description,
        "route": _first_text(record, "route"),
    }


def _commodity_name(
    *,
    product_name: str,
    area_name: str,
    series_description: str,
) -> str:
    if product_name and area_name:
        return f"{product_name}, {area_name}"
    return series_description or product_name or area_name or "EIA energy price"


def _first_text(record: dict[str, object], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return ""


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


def _price_text(record: dict[str, Any]) -> str:
    fields = [
        f"Commodity: {record.get('commodity_name', '')}",
        f"Period: {record.get('period', '')}",
        f"Frequency: {record.get('frequency', '')}",
        f"Value: {record.get('value', '')}",
        f"Unit: {record.get('raw_unit', '')}",
        f"Product code: {record.get('product_code', '')}",
        f"Product name: {record.get('product_name', '')}",
        f"Process code: {record.get('process_code', '')}",
        f"Process name: {record.get('process_name', '')}",
        f"Area code: {record.get('area_code', '')}",
        f"Area name: {record.get('area_name', '')}",
        f"Series description: {record.get('series_description', '')}",
    ]
    return "\n".join(field for field in fields if not field.endswith(": "))
