from __future__ import annotations

import hashlib
import json
from typing import Any

from supply_intel.models.documents import DocumentChunk
from supply_intel.models.source import RawDocument


def parse_un_comtrade_trade_flows_document(document: RawDocument) -> list[DocumentChunk]:
    records = _trade_flow_records(document)
    chunks: list[DocumentChunk] = []
    for index, record in enumerate(records):
        normalized = _normalized_record(record)
        commodity_code = str(normalized.get("commodity_code", "")).strip()
        reporter_name = str(normalized.get("reporter_name", "")).strip()
        period = str(normalized.get("period", "")).strip()
        if not commodity_code or not reporter_name or not period:
            continue
        text = _trade_flow_text(normalized)
        chunks.append(
            DocumentChunk(
                raw_document_id=document.id,
                chunk_index=index,
                chunk_type="trade_flow_observation",
                title=f"{reporter_name} {normalized.get('flow', '')} {commodity_code} {period}",
                text=text,
                structured_data=normalized,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return chunks


def _trade_flow_records(document: RawDocument) -> list[dict[str, object]]:
    if not document.payload_text:
        return []
    try:
        data = json.loads(document.payload_text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        if isinstance(data.get("data"), list):
            return [record for record in data["data"] if isinstance(record, dict)]
        if _looks_like_trade_record(data):
            return [data]
    if isinstance(data, list):
        return [record for record in data if isinstance(record, dict)]
    return []


def _looks_like_trade_record(data: dict[str, object]) -> bool:
    return any(key in data for key in ("cmdCode", "commodity_code", "cmd_code")) and any(
        key in data for key in ("reporterCode", "reporter_code")
    )


def _normalized_record(record: dict[str, object]) -> dict[str, object]:
    return {
        "type_code": _first_text(record, "typeCode", "type_code"),
        "frequency_code": _first_text(record, "freqCode", "frequency_code"),
        "classification_code": _first_text(record, "classificationCode", "classification_code"),
        "period": _first_text(record, "period", "refPeriodId", "ref_period_id"),
        "ref_year": _first_text(record, "refYear", "ref_year"),
        "ref_month": _first_text(record, "refMonth", "ref_month"),
        "reporter_code": _first_text(record, "reporterCode", "reporter_code"),
        "reporter_iso": _first_text(record, "reporterISO", "reporter_iso"),
        "reporter_name": _first_text(record, "reporterDesc", "reporter_name"),
        "partner_code": _first_text(record, "partnerCode", "partner_code"),
        "partner_iso": _first_text(record, "partnerISO", "partner_iso"),
        "partner_name": _first_text(record, "partnerDesc", "partner_name") or "World",
        "flow_code": _first_text(record, "flowCode", "flow_code"),
        "flow": _first_text(record, "flowDesc", "flow"),
        "commodity_code": _first_text(record, "cmdCode", "commodity_code", "cmd_code"),
        "commodity_description": _first_text(
            record,
            "cmdDesc",
            "commodity_description",
            "cmd_description",
        ),
        "customs_code": _first_text(record, "customsCode", "customs_code"),
        "mode_of_transport_code": _first_text(record, "motCode", "mode_of_transport_code"),
        "mode_of_transport": _first_text(record, "motDesc", "mode_of_transport"),
        "quantity_unit": _first_text(record, "qtyUnitAbbr", "quantity_unit"),
        "quantity": _float_value(_first_raw(record, "qty", "quantity")),
        "alt_quantity_unit": _first_text(record, "altQtyUnitAbbr", "alt_quantity_unit"),
        "alt_quantity": _float_value(_first_raw(record, "altQty", "alt_quantity")),
        "net_weight_kg": _float_value(_first_raw(record, "netWgt", "net_weight_kg")),
        "gross_weight_kg": _float_value(_first_raw(record, "grossWgt", "gross_weight_kg")),
        "primary_value_usd": _float_value(_first_raw(record, "primaryValue", "primary_value_usd")),
        "cif_value_usd": _float_value(_first_raw(record, "cifvalue", "cif_value_usd")),
        "fob_value_usd": _float_value(_first_raw(record, "fobvalue", "fob_value_usd")),
        "is_reported": _first_raw(record, "isReported", "is_reported"),
        "is_aggregate": _first_raw(record, "isAggregate", "is_aggregate"),
        "is_quantity_estimated": _first_raw(record, "isQtyEstimated", "is_quantity_estimated"),
        "is_net_weight_estimated": _first_raw(
            record,
            "isNetWgtEstimated",
            "is_net_weight_estimated",
        ),
    }


def _first_text(record: dict[str, object], *keys: str) -> str:
    value = _first_raw(record, *keys)
    if value is None:
        return ""
    return str(value).strip()


def _first_raw(record: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _float_value(value: object | None) -> float | None:
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


def _trade_flow_text(record: dict[str, Any]) -> str:
    fields = [
        f"Reporter: {record.get('reporter_name', '')}",
        f"Reporter code: {record.get('reporter_code', '')}",
        f"Partner: {record.get('partner_name', '')}",
        f"Partner code: {record.get('partner_code', '')}",
        f"Flow: {record.get('flow', '')}",
        f"Flow code: {record.get('flow_code', '')}",
        f"Commodity code: {record.get('commodity_code', '')}",
        f"Commodity description: {record.get('commodity_description', '')}",
        f"Period: {record.get('period', '')}",
        f"Primary value USD: {record.get('primary_value_usd', '')}",
        f"Net weight kg: {record.get('net_weight_kg', '')}",
        f"Quantity: {record.get('quantity', '')}",
        f"Quantity unit: {record.get('quantity_unit', '')}",
        f"Classification: {record.get('classification_code', '')}",
        f"Mode of transport: {record.get('mode_of_transport', '')}",
    ]
    return "\n".join(field for field in fields if not field.endswith(": "))
