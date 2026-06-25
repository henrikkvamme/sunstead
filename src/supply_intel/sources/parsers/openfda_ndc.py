from __future__ import annotations

import hashlib
import json
from typing import Any

from supply_intel.models.documents import DocumentChunk
from supply_intel.models.source import RawDocument


def parse_openfda_ndc_document(document: RawDocument) -> list[DocumentChunk]:
    if not document.payload_text:
        return []
    record = json.loads(document.payload_text)
    text = _record_text(record)
    return [
        DocumentChunk(
            raw_document_id=document.id,
            chunk_index=0,
            chunk_type="json_fragment",
            title=record.get("product_ndc") or record.get("brand_name"),
            text=text,
            structured_data=record,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
    ]


def _record_text(record: dict[str, Any]) -> str:
    active = ", ".join(
        item.get("name", "")
        for item in record.get("active_ingredients", [])
        if isinstance(item, dict)
    )
    fields = [
        f"Product NDC: {record.get('product_ndc', '')}",
        f"Brand name: {record.get('brand_name', '')}",
        f"Generic name: {record.get('generic_name', '')}",
        f"Labeler name: {record.get('labeler_name', '')}",
        f"Active ingredients: {active}",
    ]
    return "\n".join(field for field in fields if not field.endswith(": "))
