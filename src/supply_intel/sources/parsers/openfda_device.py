from __future__ import annotations

import hashlib
import json
from typing import Any

from supply_intel.models.documents import DocumentChunk
from supply_intel.models.source import RawDocument


def parse_openfda_device_registrationlisting_document(
    document: RawDocument,
) -> list[DocumentChunk]:
    if not document.payload_text:
        return []
    record = json.loads(document.payload_text)
    chunks: list[DocumentChunk] = []
    for index, normalized in enumerate(_registration_records(record)):
        text = _registration_text(normalized)
        chunks.append(
            DocumentChunk(
                raw_document_id=document.id,
                chunk_index=index,
                chunk_type="json_fragment",
                title=_first_value(normalized.get("listing_number"))
                or str(normalized.get("registration_number") or ""),
                text=text,
                structured_data=normalized,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return chunks


def parse_openfda_device_enforcement_document(document: RawDocument) -> list[DocumentChunk]:
    if not document.payload_text:
        return []
    record = json.loads(document.payload_text)
    text = _enforcement_text(record)
    return [
        DocumentChunk(
            raw_document_id=document.id,
            chunk_index=0,
            chunk_type="json_fragment",
            title=record.get("recall_number") or record.get("product_description"),
            text=text,
            structured_data=record,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
    ]


def _registration_text(record: dict[str, Any]) -> str:
    owner_operator = record.get("owner_operator")
    owner_firm = (
        owner_operator.get("firm_name", "")
        if isinstance(owner_operator, dict)
        else record.get("firm_name", "")
    )
    fields = [
        f"Registration number: {record.get('registration_number', '')}",
        f"FEI number: {record.get('fei_number', '')}",
        f"Listing number: {_first_value(record.get('listing_number')) or ''}",
        f"Device name: {record.get('device_name', '')}",
        f"Proprietary name: {_first_value(record.get('proprietary_name')) or ''}",
        f"Product code: {record.get('product_code', '')}",
        f"Medical specialty: {record.get('medical_specialty_description', '')}",
        f"Owner operator: {owner_firm}",
        f"Establishment type: {', '.join(_as_strings(record.get('establishment_type')))}",
        f"Address: {record.get('address_1', '')}, {record.get('city', '')}, "
        f"{record.get('state_code', '')}, {record.get('country_code', '')}",
    ]
    return "\n".join(field for field in fields if not field.endswith(": "))


def _registration_records(record: dict[str, Any]) -> list[dict[str, Any]]:
    registration = record.get("registration")
    registration_data = registration if isinstance(registration, dict) else {}
    products = record.get("products")
    product_records = products if isinstance(products, list) and products else [None]
    normalized_records: list[dict[str, Any]] = []
    for product in product_records:
        product_data = product if isinstance(product, dict) else {}
        openfda = product_data.get("openfda")
        product_openfda = openfda if isinstance(openfda, dict) else {}
        owner_operator = registration_data.get("owner_operator") or record.get("owner_operator")
        owner_operator_data = owner_operator if isinstance(owner_operator, dict) else {}
        normalized = {
            "registration_number": _first_text(
                registration_data.get("registration_number"),
                record.get("registration_number"),
            ),
            "fei_number": _first_text(
                registration_data.get("fei_number"),
                record.get("fei_number"),
            ),
            "firm_name": _first_text(registration_data.get("name"), record.get("firm_name")),
            "owner_operator": {
                "firm_name": _first_text(owner_operator_data.get("firm_name")),
                "owner_operator_number": _first_text(
                    owner_operator_data.get("owner_operator_number"),
                    product_data.get("owner_operator_number"),
                ),
            },
            "establishment_type": _as_strings(record.get("establishment_type")),
            "address_1": _first_text(
                registration_data.get("address_line_1"),
                record.get("address_1"),
            ),
            "city": _first_text(registration_data.get("city"), record.get("city")),
            "state_code": _first_text(
                registration_data.get("state_code"),
                record.get("state_code"),
            ),
            "country_code": _first_text(
                registration_data.get("iso_country_code"),
                record.get("country_code"),
            ),
            "proprietary_name": _as_strings(record.get("proprietary_name")),
            "listing_number": _as_strings(record.get("listing_number")),
            "product_code": _first_text(
                product_data.get("product_code"),
                record.get("product_code"),
            ),
            "device_name": _first_text(
                product_openfda.get("device_name"),
                record.get("device_name"),
            ),
            "medical_specialty_description": _first_text(
                product_openfda.get("medical_specialty_description"),
                record.get("medical_specialty_description"),
            ),
            "device_class": _first_text(product_openfda.get("device_class")),
            "regulation_number": _first_text(product_openfda.get("regulation_number")),
            "created_date": _first_text(product_data.get("created_date")),
            "registration_status_code": _first_text(registration_data.get("status_code")),
            "registration_expiry_year": _first_text(
                registration_data.get("reg_expiry_date_year"),
                registration_data.get("expiry_date_year"),
            ),
        }
        normalized_records.append(normalized)
    return normalized_records


def _enforcement_text(record: dict[str, Any]) -> str:
    raw_openfda = record.get("openfda")
    openfda = raw_openfda if isinstance(raw_openfda, dict) else {}
    fields = [
        f"Recall number: {record.get('recall_number', '')}",
        f"Classification: {record.get('classification', '')}",
        f"Status: {record.get('status', '')}",
        f"Product description: {record.get('product_description', '')}",
        f"Reason for recall: {record.get('reason_for_recall', '')}",
        f"Recalling firm: {record.get('recalling_firm', '')}",
        f"Device name: {_first_value(openfda.get('device_name')) or ''}",
        f"Product code: {_first_value(openfda.get('product_code')) or ''}",
        f"Distribution pattern: {record.get('distribution_pattern', '')}",
        f"Report date: {record.get('report_date', '')}",
    ]
    return "\n".join(field for field in fields if not field.endswith(": "))


def _first_value(value: object) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0]).strip()
    if isinstance(value, str):
        return value.strip()
    return None


def _first_text(*values: object) -> str:
    for value in values:
        first = _first_value(value)
        if first:
            return first
    return ""


def _as_strings(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
