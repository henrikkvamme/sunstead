from __future__ import annotations

import hashlib
import json
from typing import Any

from supply_intel.models.documents import DocumentChunk
from supply_intel.models.source import RawDocument


def parse_openfda_drug_enforcement_document(document: RawDocument) -> list[DocumentChunk]:
    if not document.payload_text:
        return []
    record = json.loads(document.payload_text)
    text = _record_text(record)
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


def _record_text(record: dict[str, Any]) -> str:
    fields = [
        f"Recall number: {record.get('recall_number', '')}",
        f"Classification: {record.get('classification', '')}",
        f"Status: {record.get('status', '')}",
        f"Product description: {record.get('product_description', '')}",
        f"Reason for recall: {record.get('reason_for_recall', '')}",
        f"Recalling firm: {record.get('recalling_firm', '')}",
        f"Distribution pattern: {record.get('distribution_pattern', '')}",
        f"Report date: {record.get('report_date', '')}",
    ]
    return "\n".join(field for field in fields if not field.endswith(": "))
