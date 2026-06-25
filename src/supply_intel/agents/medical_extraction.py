from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from uuid import UUID

from supply_intel.models.base import EvidenceRef, EvidenceSpanCandidate
from supply_intel.models.documents import DocumentChunk
from supply_intel.models.events import (
    DisasterEvent,
    LogisticsPressureObservation,
    NewsEvent,
    PriceObservation,
    RecallEvent,
    RegulatoryEvent,
    ShortageEvent,
    TradeFlowObservation,
    TrendSignalObservation,
)
from supply_intel.models.extraction import MedicalExtractionOutput
from supply_intel.models.medical import ExtractedRelationship, MedicalEntity
from supply_intel.models.source import RawDocument

YEAR_DIGIT_COUNT = 4
MONTHS_PER_QUARTER = 3


class MedicalExtractionAgent:
    agent_name = "MedicalExtractionAgent"
    agent_version = "0.1.0"

    def extract_openfda_ndc(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        product_ndc = str(record.get("product_ndc", "")).strip()
        brand_name = str(record.get("brand_name", "")).strip()
        generic_name = str(record.get("generic_name", "")).strip()
        labeler_name = str(record.get("labeler_name", "")).strip()
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=document.fetched_at,
            confidence=1.0,
            method="deterministic_openfda_ndc_v1",
        )

        entities: list[MedicalEntity] = []
        relationships: list[ExtractedRelationship] = []
        spans: list[EvidenceSpanCandidate] = [
            EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
        ]

        if product_ndc:
            ndc_key = f"NDC:product:{product_ndc}"
            entities.append(
                MedicalEntity(
                    entity_type="NDC",
                    name=product_ndc,
                    canonical_key=ndc_key,
                    external_ids={"product_ndc": product_ndc},
                    attributes={"product_type": record.get("product_type")},
                    evidence=[evidence],
                )
            )
        else:
            ndc_key = ""

        drug_name = brand_name or generic_name or product_ndc
        if drug_name and product_ndc:
            drug_key = f"Drug:ndc_product:{product_ndc}"
            entities.append(
                MedicalEntity(
                    entity_type="Drug",
                    name=drug_name,
                    canonical_key=drug_key,
                    external_ids={"product_ndc": product_ndc},
                    attributes={
                        "brand_name": brand_name,
                        "generic_name": generic_name,
                        "dosage_form": record.get("dosage_form"),
                        "route": record.get("route"),
                    },
                    evidence=[evidence],
                )
            )
            relationships.append(
                ExtractedRelationship(
                    relationship_type="HAS_NDC",
                    from_entity_key=drug_key,
                    to_entity_key=ndc_key,
                    evidence=[evidence],
                    confidence=1.0,
                )
            )
        else:
            drug_key = ""

        if labeler_name:
            manufacturer_key = f"Manufacturer:labeler:{_slug(labeler_name)}"
            entities.append(
                MedicalEntity(
                    entity_type="Manufacturer",
                    name=labeler_name,
                    canonical_key=manufacturer_key,
                    attributes={"labeler_name": labeler_name},
                    evidence=[evidence],
                    confidence=0.95,
                )
            )
            if drug_key:
                relationships.append(
                    ExtractedRelationship(
                        relationship_type="LABELS",
                        from_entity_key=manufacturer_key,
                        to_entity_key=drug_key,
                        evidence=[evidence],
                        confidence=0.95,
                    )
                )

        for item in record.get("active_ingredients", []):
            if not isinstance(item, dict) or not item.get("name"):
                continue
            ingredient_name = str(item["name"]).strip()
            ingredient_key = f"ActiveIngredient:name:{_slug(ingredient_name)}"
            entities.append(
                MedicalEntity(
                    entity_type="ActiveIngredient",
                    name=ingredient_name,
                    canonical_key=ingredient_key,
                    attributes={"strength": item.get("strength")},
                    evidence=[evidence],
                    confidence=0.98,
                )
            )
            if drug_key:
                relationships.append(
                    ExtractedRelationship(
                        relationship_type="CONTAINS_ACTIVE_INGREDIENT",
                        from_entity_key=drug_key,
                        to_entity_key=ingredient_key,
                        evidence=[evidence],
                        attributes={"strength": item.get("strength")},
                        confidence=0.98,
                    )
                )

        return MedicalExtractionOutput(
            entities=entities,
            relationships=relationships,
            evidence_spans=spans,
            warnings=[],
        )

    def extract_openfda_drug_enforcement(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        recall_number = str(record.get("recall_number", "")).strip()
        product_description = str(record.get("product_description", "")).strip()
        classification = str(record.get("classification", "")).strip() or None
        recalling_firm = str(record.get("recalling_firm", "")).strip()
        reason = str(record.get("reason_for_recall", "")).strip() or None
        status = str(record.get("status", "")).strip() or None
        product_ndc = _first_openfda_value(record, "product_ndc")
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=document.fetched_at,
            confidence=0.98,
            method="deterministic_openfda_drug_enforcement_v1",
        )
        recall_key = f"Recall:openfda:{recall_number or _slug(product_description)}"
        recall = RecallEvent(
            recall_key=recall_key,
            recall_number=recall_number or None,
            product_description=product_description or "Unknown recalled product",
            classification=classification,
            reason=reason,
            status=status,
            evidence=[evidence],
            confidence=0.98,
        )

        entities: list[MedicalEntity] = []
        relationships: list[ExtractedRelationship] = []
        if product_ndc:
            drug_key = f"Drug:ndc_product:{product_ndc}"
            entities.append(
                MedicalEntity(
                    entity_type="Drug",
                    name=product_description or product_ndc,
                    canonical_key=drug_key,
                    external_ids={"product_ndc": product_ndc},
                    attributes={"source": "openfda_drug_enforcement"},
                    evidence=[evidence],
                    confidence=0.86,
                    needs_review=not product_description,
                    review_reason=(
                        None if product_description else "Recall product description missing"
                    ),
                )
            )
            relationships.append(
                ExtractedRelationship(
                    relationship_type="AFFECTS",
                    from_entity_key=recall_key,
                    to_entity_key=drug_key,
                    evidence=[evidence],
                    attributes={"classification": classification, "reason": reason},
                    confidence=0.90,
                )
            )

        if recalling_firm:
            manufacturer_key = f"Manufacturer:recalling_firm:{_slug(recalling_firm)}"
            entities.append(
                MedicalEntity(
                    entity_type="Manufacturer",
                    name=recalling_firm,
                    canonical_key=manufacturer_key,
                    attributes={"recalling_firm": recalling_firm},
                    evidence=[evidence],
                    confidence=0.90,
                )
            )
            relationships.append(
                ExtractedRelationship(
                    relationship_type="INVOLVES",
                    from_entity_key=recall_key,
                    to_entity_key=manufacturer_key,
                    evidence=[evidence],
                    confidence=0.88,
                )
            )

        return MedicalExtractionOutput(
            entities=entities,
            recall_events=[recall],
            relationships=relationships,
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )

    def extract_openfda_device_registrationlisting(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        registration_number = str(record.get("registration_number", "")).strip()
        fei_number = str(record.get("fei_number", "")).strip()
        listing_number = _first_record_value(record, "listing_number")
        product_code = str(record.get("product_code", "")).strip()
        device_name = _device_name_from_registration(record)
        owner_operator = record.get("owner_operator")
        owner_firm = (
            str(owner_operator.get("firm_name", "")).strip()
            if isinstance(owner_operator, dict)
            else ""
        )
        manufacturer_name = owner_firm or str(record.get("firm_name", "")).strip()
        specialty = str(record.get("medical_specialty_description", "")).strip()
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=document.fetched_at,
            confidence=0.96,
            method="deterministic_openfda_device_registrationlisting_v1",
        )

        entities: list[MedicalEntity] = []
        relationships: list[ExtractedRelationship] = []
        device_key = (
            f"MedicalDevice:listing:{listing_number}"
            if listing_number
            else f"MedicalDevice:registration_product:{registration_number}:{product_code}"
        )
        if device_name and (listing_number or product_code or registration_number):
            entities.append(
                MedicalEntity(
                    entity_type="MedicalDevice",
                    name=device_name,
                    canonical_key=device_key,
                    external_ids=_compact_ids(
                        {
                            "listing_number": listing_number,
                            "product_code": product_code,
                            "registration_number": registration_number,
                        }
                    ),
                    attributes={
                        "device_name": device_name,
                        "proprietary_name": _first_record_value(record, "proprietary_name"),
                        "medical_specialty_description": specialty,
                    },
                    evidence=[evidence],
                    confidence=0.94,
                )
            )

        if product_code:
            category_key = f"DeviceCategory:product_code:{product_code}"
            entities.append(
                MedicalEntity(
                    entity_type="DeviceCategory",
                    name=specialty or product_code,
                    canonical_key=category_key,
                    external_ids={"product_code": product_code},
                    attributes={"medical_specialty_description": specialty},
                    evidence=[evidence],
                    confidence=0.92,
                )
            )
            if device_key:
                relationships.append(
                    ExtractedRelationship(
                        relationship_type="BELONGS_TO_CATEGORY",
                        from_entity_key=device_key,
                        to_entity_key=category_key,
                        evidence=[evidence],
                        confidence=0.92,
                    )
                )

        manufacturer_key = ""
        if manufacturer_name:
            manufacturer_key = f"Manufacturer:owner_operator:{_slug(manufacturer_name)}"
            entities.append(
                MedicalEntity(
                    entity_type="Manufacturer",
                    name=manufacturer_name,
                    canonical_key=manufacturer_key,
                    external_ids=_compact_ids(
                        {
                            "owner_operator_number": _owner_operator_number(record),
                            "registration_number": registration_number,
                        }
                    ),
                    attributes={"establishment_type": record.get("establishment_type")},
                    evidence=[evidence],
                    confidence=0.91,
                )
            )
            if device_key:
                relationships.append(
                    ExtractedRelationship(
                        relationship_type="MANUFACTURED_BY",
                        from_entity_key=device_key,
                        to_entity_key=manufacturer_key,
                        evidence=[evidence],
                        confidence=0.90,
                    )
                )

        if registration_number or fei_number:
            facility_key = f"Facility:fei:{fei_number or registration_number}"
            facility_name = (
                f"{manufacturer_name or 'Registered facility'} {fei_number or registration_number}"
            )
            entities.append(
                MedicalEntity(
                    entity_type="Facility",
                    name=facility_name,
                    canonical_key=facility_key,
                    external_ids=_compact_ids(
                        {"fei_number": fei_number, "registration_number": registration_number}
                    ),
                    attributes={
                        "address_1": record.get("address_1"),
                        "city": record.get("city"),
                        "state_code": record.get("state_code"),
                        "country_code": record.get("country_code"),
                    },
                    evidence=[evidence],
                    confidence=0.89,
                )
            )
            if manufacturer_key:
                relationships.append(
                    ExtractedRelationship(
                        relationship_type="OPERATES",
                        from_entity_key=manufacturer_key,
                        to_entity_key=facility_key,
                        evidence=[evidence],
                        confidence=0.88,
                    )
                )
            if device_key:
                relationships.append(
                    ExtractedRelationship(
                        relationship_type="MANUFACTURED_AT",
                        from_entity_key=device_key,
                        to_entity_key=facility_key,
                        evidence=[evidence],
                        confidence=0.87,
                    )
                )

        return MedicalExtractionOutput(
            entities=entities,
            relationships=relationships,
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )

    def extract_openfda_device_enforcement(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        recall_number = str(record.get("recall_number", "")).strip()
        product_description = str(record.get("product_description", "")).strip()
        classification = str(record.get("classification", "")).strip() or None
        recalling_firm = str(record.get("recalling_firm", "")).strip()
        reason = str(record.get("reason_for_recall", "")).strip() or None
        status = str(record.get("status", "")).strip() or None
        product_code = _first_openfda_value(record, "product_code")
        device_name = _first_openfda_value(record, "device_name") or product_description
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=document.fetched_at,
            confidence=0.97,
            method="deterministic_openfda_device_enforcement_v1",
        )
        recall_key = f"Recall:openfda_device:{recall_number or _slug(product_description)}"
        recall = RecallEvent(
            recall_key=recall_key,
            recall_number=recall_number or None,
            product_description=product_description or "Unknown recalled device",
            classification=classification,
            reason=reason,
            status=status,
            evidence=[evidence],
            confidence=0.97,
        )

        entities: list[MedicalEntity] = []
        relationships: list[ExtractedRelationship] = []
        if product_code or device_name:
            device_key = (
                f"MedicalDevice:product_code:{product_code}"
                if product_code
                else f"MedicalDevice:name:{_slug(device_name)}"
            )
            entities.append(
                MedicalEntity(
                    entity_type="MedicalDevice",
                    name=device_name or product_code or product_description,
                    canonical_key=device_key,
                    external_ids=_compact_ids({"product_code": product_code}),
                    attributes={"source": "openfda_device_enforcement"},
                    evidence=[evidence],
                    confidence=0.84,
                    needs_review=not product_code,
                    review_reason=None if product_code else "Device product code missing",
                )
            )
            relationships.append(
                ExtractedRelationship(
                    relationship_type="AFFECTS",
                    from_entity_key=recall_key,
                    to_entity_key=device_key,
                    evidence=[evidence],
                    attributes={"classification": classification, "reason": reason},
                    confidence=0.88,
                )
            )

        if recalling_firm:
            manufacturer_key = f"Manufacturer:recalling_firm:{_slug(recalling_firm)}"
            entities.append(
                MedicalEntity(
                    entity_type="Manufacturer",
                    name=recalling_firm,
                    canonical_key=manufacturer_key,
                    attributes={"recalling_firm": recalling_firm},
                    evidence=[evidence],
                    confidence=0.90,
                )
            )
            relationships.append(
                ExtractedRelationship(
                    relationship_type="INVOLVES",
                    from_entity_key=recall_key,
                    to_entity_key=manufacturer_key,
                    evidence=[evidence],
                    confidence=0.87,
                )
            )

        return MedicalExtractionOutput(
            entities=entities,
            recall_events=[recall],
            relationships=relationships,
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )

    def extract_fda_drug_shortages(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        product_name = str(record.get("generic_name", "")).strip()
        status = str(record.get("status", "")).strip() or "Unknown"
        reason = str(record.get("reason", "")).strip() or None
        company = str(record.get("company", "")).strip()
        presentation = str(record.get("presentation", "")).strip()
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=document.fetched_at,
            confidence=0.95,
            method="deterministic_fda_drug_shortages_html_v1",
        )
        shortage_key = f"Shortage:fda:{_slug(product_name)}:{_slug(presentation or status)}"
        shortage = ShortageEvent(
            shortage_key=shortage_key,
            product_name=product_name or "Unknown shortage product",
            status=status,
            reason=reason,
            evidence=[evidence],
            confidence=0.95,
        )

        entities: list[MedicalEntity] = []
        relationships: list[ExtractedRelationship] = []
        drug_key = ""
        if product_name:
            drug_key = f"Drug:name:{_slug(product_name)}"
            entities.append(
                MedicalEntity(
                    entity_type="Drug",
                    name=product_name,
                    canonical_key=drug_key,
                    attributes={"presentation": presentation, "shortage_status": status},
                    evidence=[evidence],
                    confidence=0.88,
                )
            )
            relationships.append(
                ExtractedRelationship(
                    relationship_type="AFFECTS",
                    from_entity_key=shortage_key,
                    to_entity_key=drug_key,
                    evidence=[evidence],
                    attributes={"status": status, "reason": reason, "presentation": presentation},
                    confidence=0.88,
                )
            )

        if company:
            manufacturer_key = f"Manufacturer:fda_shortage_company:{_slug(company)}"
            entities.append(
                MedicalEntity(
                    entity_type="Manufacturer",
                    name=company,
                    canonical_key=manufacturer_key,
                    attributes={"source": "fda_drug_shortages"},
                    evidence=[evidence],
                    confidence=0.86,
                    needs_review=True,
                    review_reason=(
                        "FDA shortage company names can reflect labelers, suppliers, or applicants."
                    ),
                )
            )
            relationships.append(
                ExtractedRelationship(
                    relationship_type="INVOLVES",
                    from_entity_key=shortage_key,
                    to_entity_key=manufacturer_key,
                    evidence=[evidence],
                    confidence=0.82,
                    inferred=True,
                )
            )
            if drug_key:
                relationships.append(
                    ExtractedRelationship(
                        relationship_type="MARKETS",
                        from_entity_key=manufacturer_key,
                        to_entity_key=drug_key,
                        evidence=[evidence],
                        confidence=0.80,
                        inferred=True,
                    )
                )

        return MedicalExtractionOutput(
            entities=entities,
            shortage_events=[shortage],
            relationships=relationships,
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )

    def extract_fda_warning_letters(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        company = str(record.get("company_name", "")).strip()
        issuing_office = str(record.get("issuing_office", "")).strip()
        subject = str(record.get("subject", "")).strip()
        issue_date = str(record.get("letter_issue_date", "")).strip()
        posted_date = str(record.get("posted_date", "")).strip()
        response_letter_url = str(record.get("response_letter_url", "")).strip()
        closeout_letter_url = str(record.get("closeout_letter_url", "")).strip()
        observed_at = _parse_source_date(issue_date) or _parse_source_date(posted_date)
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=observed_at or document.fetched_at,
            confidence=0.94,
            method="deterministic_fda_warning_letters_xlsx_v1",
        )
        event_key = (
            f"RegulatoryNotice:fda_warning_letter:{_slug(issue_date or posted_date)}:"
            f"{_slug(company)}:{_slug(subject)[:48]}"
        )
        event = RegulatoryEvent(
            event_key=event_key,
            event_type="fda_warning_letter",
            title=f"FDA warning letter: {company or subject or 'Unknown recipient'}",
            agency="FDA",
            observed_at=observed_at,
            attributes={
                "posted_date": posted_date,
                "letter_issue_date": issue_date,
                "issuing_office": issuing_office,
                "subject": subject,
                "response_letter_url": response_letter_url,
                "closeout_letter_url": closeout_letter_url,
                "source_caveat": (
                    "FDA warning-letter matters may have changed after later interaction "
                    "with the recipient."
                ),
            },
            evidence=[evidence],
            confidence=0.94,
        )

        entities: list[MedicalEntity] = []
        relationships: list[ExtractedRelationship] = []
        if company:
            company_key = f"Manufacturer:fda_warning_letter_company:{_slug(company)}"
            entities.append(
                MedicalEntity(
                    entity_type="Manufacturer",
                    name=company,
                    canonical_key=company_key,
                    attributes={
                        "source": "fda_warning_letters",
                        "latest_warning_letter_subject": subject,
                    },
                    evidence=[evidence],
                    confidence=0.78,
                    needs_review=True,
                    review_reason=(
                        "FDA warning letter recipient names need review before treating them "
                        "as canonical manufacturers or suppliers."
                    ),
                )
            )
            relationships.append(
                ExtractedRelationship(
                    relationship_type="ISSUED_TO",
                    from_entity_key=event_key,
                    to_entity_key=company_key,
                    evidence=[evidence],
                    attributes={"subject": subject, "letter_issue_date": issue_date},
                    confidence=0.90,
                )
            )

        agency_key = "RegulatoryAgency:fda"
        entities.append(
            MedicalEntity(
                entity_type="RegulatoryAgency",
                name="FDA",
                canonical_key=agency_key,
                attributes={"issuing_office": issuing_office},
                evidence=[evidence],
                confidence=0.99,
            )
        )
        relationships.append(
            ExtractedRelationship(
                relationship_type="ISSUED_BY",
                from_entity_key=event_key,
                to_entity_key=agency_key,
                evidence=[evidence],
                attributes={"issuing_office": issuing_office},
                confidence=0.99,
            )
        )

        return MedicalExtractionOutput(
            entities=entities,
            regulatory_events=[event],
            relationships=relationships,
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )

    def extract_fda_inspections_dashboard(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        dataset_type = str(record.get("dataset_type", "inspection")).strip() or "inspection"
        inspection_id = str(record.get("inspection_id", "")).strip()
        citation_id = str(record.get("citation_id", "")).strip()
        fei_number = str(record.get("fei_number", "")).strip()
        legal_name = str(record.get("legal_name", "")).strip()
        classification = str(record.get("classification", "")).strip()
        inspection_end_date = str(record.get("inspection_end_date", "")).strip()
        record_date = str(record.get("record_date", "")).strip()
        publish_date = str(record.get("publish_date", "")).strip()
        observed_at = (
            _parse_source_date(inspection_end_date)
            or _parse_source_date(record_date)
            or _parse_source_date(publish_date)
        )
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=observed_at or document.fetched_at,
            confidence=0.92,
            method="deterministic_fda_inspections_dashboard_v1",
        )
        event_type = _inspection_event_type(dataset_type)
        event_key = (
            f"RegulatoryNotice:{event_type}:{_slug(inspection_id or citation_id or fei_number)}:"
            f"{_slug(citation_id or legal_name or classification)[:48]}"
        )
        event = RegulatoryEvent(
            event_key=event_key,
            event_type=event_type,
            title=_inspection_event_title(
                dataset_type=dataset_type,
                inspection_id=inspection_id,
                citation_id=citation_id,
                legal_name=legal_name,
            ),
            agency="FDA",
            observed_at=observed_at,
            attributes={
                "dataset_type": dataset_type,
                "inspection_id": inspection_id,
                "citation_id": citation_id,
                "fei_number": fei_number,
                "legal_name": legal_name,
                "city_name": record.get("city_name"),
                "inspection_state": record.get("inspection_state"),
                "country_name": record.get("country_name"),
                "fiscal_year": record.get("fiscal_year"),
                "product_type": record.get("product_type"),
                "program_area": record.get("program_area"),
                "project_area": record.get("project_area"),
                "classification": classification,
                "inspection_end_date": inspection_end_date,
                "posted_citations": record.get("posted_citations"),
                "short_description": record.get("short_description"),
                "long_description": record.get("long_description"),
                "cfr_section": record.get("cfr_section"),
                "fdca_section": record.get("fdca_section"),
                "record_date": record_date,
                "publish_date": publish_date,
                "form_483_url": record.get("form_483_url"),
                "additional_details": record.get("additional_details"),
                "source_caveat": (
                    "FDA inspections dashboard data is updated weekly, includes only final "
                    "actions and selected posted records, and absence of records must not be "
                    "interpreted as evidence of facility or product quality."
                ),
            },
            evidence=[evidence],
            confidence=0.92,
        )

        entities: list[MedicalEntity] = []
        relationships: list[ExtractedRelationship] = []
        company_key = ""
        if legal_name:
            company_key = f"Manufacturer:fda_inspection_legal_name:{_slug(legal_name)}"
            entities.append(
                MedicalEntity(
                    entity_type="Manufacturer",
                    name=legal_name,
                    canonical_key=company_key,
                    attributes={
                        "source": "fda_inspections_dashboard",
                        "latest_inspection_classification": classification,
                        "product_type": record.get("product_type"),
                    },
                    evidence=[evidence],
                    confidence=0.80,
                    needs_review=True,
                    review_reason=(
                        "FDA inspection legal names need review before treating them as "
                        "canonical manufacturers or suppliers."
                    ),
                )
            )

        facility_key = ""
        if fei_number or legal_name:
            facility_key = (
                f"Facility:fei:{fei_number}"
                if fei_number
                else f"Facility:fda_inspection:{_slug(legal_name)}"
            )
            entities.append(
                MedicalEntity(
                    entity_type="Facility",
                    name=_inspection_facility_name(legal_name, fei_number),
                    canonical_key=facility_key,
                    external_ids=_compact_ids({"fei_number": fei_number}),
                    attributes={
                        "legal_name": legal_name,
                        "city_name": record.get("city_name"),
                        "inspection_state": record.get("inspection_state"),
                        "country_name": record.get("country_name"),
                        "latest_inspection_classification": classification,
                    },
                    evidence=[evidence],
                    confidence=0.90 if fei_number else 0.74,
                    needs_review=not fei_number,
                    review_reason=(
                        None if fei_number else "FDA inspection facility row lacks an FEI number."
                    ),
                )
            )
            relationships.append(
                ExtractedRelationship(
                    relationship_type="ISSUED_TO",
                    from_entity_key=event_key,
                    to_entity_key=facility_key,
                    evidence=[evidence],
                    attributes={
                        "inspection_id": inspection_id,
                        "citation_id": citation_id,
                        "classification": classification,
                    },
                    confidence=0.90 if fei_number else 0.78,
                )
            )
        elif company_key:
            relationships.append(
                ExtractedRelationship(
                    relationship_type="ISSUED_TO",
                    from_entity_key=event_key,
                    to_entity_key=company_key,
                    evidence=[evidence],
                    attributes={
                        "inspection_id": inspection_id,
                        "citation_id": citation_id,
                        "classification": classification,
                    },
                    confidence=0.78,
                )
            )

        agency_key = "RegulatoryAgency:fda"
        entities.append(
            MedicalEntity(
                entity_type="RegulatoryAgency",
                name="FDA",
                canonical_key=agency_key,
                attributes={"source": "fda_inspections_dashboard"},
                evidence=[evidence],
                confidence=0.99,
            )
        )
        relationships.append(
            ExtractedRelationship(
                relationship_type="ISSUED_BY",
                from_entity_key=event_key,
                to_entity_key=agency_key,
                evidence=[evidence],
                attributes={"dataset_type": dataset_type},
                confidence=0.99,
            )
        )

        return MedicalExtractionOutput(
            entities=entities,
            regulatory_events=[event],
            relationships=relationships,
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )

    def extract_gdelt_doc_search(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        url = str(record.get("url", "")).strip()
        title = str(record.get("title", "")).strip()
        seen_date = str(record.get("seendate", "")).strip()
        observed_at = _parse_gdelt_seen_date(seen_date)
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=observed_at or document.fetched_at,
            confidence=0.70,
            method="deterministic_gdelt_doc_search_v1",
        )
        url_hash = hashlib.sha256((url or title).encode("utf-8")).hexdigest()[:16]
        news_key = f"NewsEvent:gdelt_doc:{_slug(seen_date)}:{url_hash}"
        news_event = NewsEvent(
            news_key=news_key,
            title=title or url or "Untitled GDELT article",
            url=url or None,
            event_status="unverified",
            observed_at=observed_at,
            attributes={
                "url_mobile": record.get("url_mobile"),
                "seendate": seen_date,
                "socialimage": record.get("socialimage"),
                "domain": record.get("domain"),
                "language": record.get("language"),
                "sourcecountry": record.get("sourcecountry"),
                "source_caveat": (
                    "GDELT DOC search records are news metadata signals. Publisher article "
                    "claims are unverified until evidence verification runs."
                ),
            },
            evidence=[evidence],
            confidence=0.70,
        )
        return MedicalExtractionOutput(
            news_events=[news_event],
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )

    def extract_sec_edgar_supplier_filings(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        issuer_name = str(record.get("issuer_name", "")).strip()
        issuer_cik = str(record.get("issuer_cik", "")).strip()
        accession_number = str(record.get("accession_number", "")).strip()
        accession_no_dashes = str(record.get("accession_no_dashes", "")).strip()
        form = str(record.get("form", "")).strip()
        filing_date = str(record.get("filing_date", "")).strip()
        report_date = str(record.get("report_date", "")).strip()
        acceptance_date_time = str(record.get("acceptance_date_time", "")).strip()
        observed_at = (
            _parse_source_date(filing_date)
            or _parse_source_date(report_date)
            or _parse_iso_datetime(acceptance_date_time)
        )
        primary_document_url = str(record.get("primary_document_url", "")).strip()
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=primary_document_url or document.source_url,
            observed_at=observed_at or document.fetched_at,
            confidence=0.96,
            method="deterministic_sec_edgar_supplier_filings_v1",
        )
        event_key = (
            f"RegulatoryNotice:sec_filing:{_slug(issuer_cik)}:"
            f"{_slug(accession_no_dashes or accession_number)}"
        )
        event = RegulatoryEvent(
            event_key=event_key,
            event_type="sec_company_filing",
            title=f"SEC {form or 'filing'}: {issuer_name or issuer_cik or accession_number}",
            agency="SEC",
            observed_at=observed_at,
            attributes={
                "issuer_cik": issuer_cik,
                "issuer_name": issuer_name,
                "tickers": record.get("tickers"),
                "exchanges": record.get("exchanges"),
                "sic": record.get("sic"),
                "sic_description": record.get("sic_description"),
                "entity_type": record.get("entity_type"),
                "form": form,
                "accession_number": accession_number,
                "filing_date": filing_date,
                "report_date": report_date,
                "acceptance_date_time": acceptance_date_time,
                "items": record.get("items"),
                "file_number": record.get("file_number"),
                "film_number": record.get("film_number"),
                "primary_document": record.get("primary_document"),
                "primary_doc_description": record.get("primary_doc_description"),
                "primary_document_url": primary_document_url,
                "accession_index_url": record.get("accession_index_url"),
                "source_caveat": (
                    "SEC EDGAR submissions metadata identifies company filing events. "
                    "Supplier, manufacturing, shortage, and regulatory proceeding claims "
                    "require filing-document text extraction before being treated as facts."
                ),
            },
            evidence=[evidence],
            confidence=0.96,
        )

        entities: list[MedicalEntity] = []
        relationships: list[ExtractedRelationship] = []
        if issuer_name or issuer_cik:
            ticker = _first_list_item(record.get("tickers"))
            supplier_key = f"Supplier:sec_cik:{_slug(issuer_cik or issuer_name)}"
            entities.append(
                MedicalEntity(
                    entity_type="Supplier",
                    name=issuer_name or f"SEC issuer {issuer_cik}",
                    canonical_key=supplier_key,
                    external_ids=_compact_ids({"sec_cik": issuer_cik, "ticker": ticker}),
                    attributes={
                        "source": "sec_edgar_supplier_filings",
                        "tickers": record.get("tickers"),
                        "exchanges": record.get("exchanges"),
                        "sic": record.get("sic"),
                        "sic_description": record.get("sic_description"),
                        "entity_type": record.get("entity_type"),
                        "owner_org": record.get("owner_org"),
                        "category": record.get("category"),
                        "fiscal_year_end": record.get("fiscal_year_end"),
                        "latest_sec_form": form,
                        "latest_sec_filing_date": filing_date,
                    },
                    evidence=[evidence],
                    confidence=0.82,
                    needs_review=True,
                    review_reason=(
                        "SEC issuers need review before treating them as confirmed platform "
                        "suppliers or manufacturers for a specific product chain."
                    ),
                )
            )
            relationships.append(
                ExtractedRelationship(
                    relationship_type="FILED_BY",
                    from_entity_key=event_key,
                    to_entity_key=supplier_key,
                    evidence=[evidence],
                    attributes={"form": form, "filing_date": filing_date},
                    confidence=0.94,
                )
            )

        agency_key = "RegulatoryAgency:sec"
        entities.append(
            MedicalEntity(
                entity_type="RegulatoryAgency",
                name="SEC",
                canonical_key=agency_key,
                attributes={"source": "sec_edgar"},
                evidence=[evidence],
                confidence=0.99,
            )
        )
        relationships.append(
            ExtractedRelationship(
                relationship_type="FILED_WITH",
                from_entity_key=event_key,
                to_entity_key=agency_key,
                evidence=[evidence],
                attributes={"form": form, "filing_date": filing_date},
                confidence=0.99,
            )
        )
        return MedicalExtractionOutput(
            entities=entities,
            regulatory_events=[event],
            relationships=relationships,
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )

    def extract_un_comtrade_trade_flows(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        reporter_name = str(record.get("reporter_name", "")).strip()
        partner_name = str(record.get("partner_name", "")).strip()
        commodity_code = str(record.get("commodity_code", "")).strip()
        commodity_description = str(record.get("commodity_description", "")).strip()
        flow = str(record.get("flow", "")).strip()
        period = str(record.get("period", "")).strip()
        observed_at = _parse_trade_period(period)
        if observed_at is None:
            return MedicalExtractionOutput(
                warnings=[f"Skipped invalid UN Comtrade trade-flow row: {commodity_code} {period}"]
            )
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=observed_at,
            confidence=0.97,
            method="deterministic_uncomtrade_trade_flows_v1",
        )
        trade_flow = TradeFlowObservation(
            trade_flow_key=(
                "TradeFlowObservation:uncomtrade:"
                f"{_slug(str(record.get('reporter_code', '')))}:"
                f"{_slug(str(record.get('partner_code', '')))}:"
                f"{_slug(commodity_code)}:{_slug(str(record.get('flow_code', flow)))}:"
                f"{_slug(period)}"
            ),
            reporter_name=reporter_name,
            partner_name=partner_name or "World",
            commodity_code=commodity_code,
            commodity_description=commodity_description,
            flow=flow or str(record.get("flow_code", "")).strip(),
            period=period,
            observed_at=observed_at,
            primary_value_usd=_maybe_float(record.get("primary_value_usd")),
            net_weight_kg=_maybe_float(record.get("net_weight_kg")),
            quantity=_maybe_float(record.get("quantity")),
            quantity_unit=str(record.get("quantity_unit", "")).strip() or None,
            attributes={
                "type_code": record.get("type_code"),
                "frequency_code": record.get("frequency_code"),
                "classification_code": record.get("classification_code"),
                "reporter_code": record.get("reporter_code"),
                "reporter_iso": record.get("reporter_iso"),
                "partner_code": record.get("partner_code"),
                "partner_iso": record.get("partner_iso"),
                "flow_code": record.get("flow_code"),
                "customs_code": record.get("customs_code"),
                "mode_of_transport_code": record.get("mode_of_transport_code"),
                "mode_of_transport": record.get("mode_of_transport"),
                "alt_quantity": record.get("alt_quantity"),
                "alt_quantity_unit": record.get("alt_quantity_unit"),
                "gross_weight_kg": record.get("gross_weight_kg"),
                "cif_value_usd": record.get("cif_value_usd"),
                "fob_value_usd": record.get("fob_value_usd"),
                "is_reported": record.get("is_reported"),
                "is_aggregate": record.get("is_aggregate"),
                "is_quantity_estimated": record.get("is_quantity_estimated"),
                "is_net_weight_estimated": record.get("is_net_weight_estimated"),
                "source_caveat": (
                    "UN Comtrade records are aggregate official trade statistics. "
                    "Use them as supply-chain exposure signals, not as company-specific "
                    "shipment evidence."
                ),
            },
            evidence=[evidence],
            confidence=0.97,
        )

        entities: list[MedicalEntity] = [
            MedicalEntity(
                entity_type="Commodity",
                name=f"HS {commodity_code} {commodity_description}".strip(),
                canonical_key=f"Commodity:hs:{_slug(commodity_code)}",
                external_ids=_compact_ids({"hs_code": commodity_code}),
                attributes={"description": commodity_description, "classification": "HS"},
                evidence=[evidence],
                confidence=0.95,
            )
        ]
        relationships: list[ExtractedRelationship] = [
            ExtractedRelationship(
                relationship_type="OBSERVED_FOR",
                from_entity_key=trade_flow.trade_flow_key,
                to_entity_key=f"Commodity:hs:{_slug(commodity_code)}",
                evidence=[evidence],
                attributes={"period": period, "flow": flow},
                confidence=0.95,
            )
        ]
        if reporter_name:
            reporter_key = f"Country:uncomtrade:{_slug(str(record.get('reporter_code', '')))}"
            entities.append(
                MedicalEntity(
                    entity_type="Country",
                    name=reporter_name,
                    canonical_key=reporter_key,
                    external_ids=_compact_ids(
                        {
                            "un_comtrade_code": str(record.get("reporter_code", "")).strip(),
                            "iso3": str(record.get("reporter_iso", "")).strip(),
                        }
                    ),
                    attributes={"role": "reporter"},
                    evidence=[evidence],
                    confidence=0.95,
                )
            )
            relationships.append(
                ExtractedRelationship(
                    relationship_type="ABOUT",
                    from_entity_key=trade_flow.trade_flow_key,
                    to_entity_key=reporter_key,
                    evidence=[evidence],
                    attributes={"role": "reporter"},
                    confidence=0.92,
                )
            )
        if partner_name:
            partner_key = f"Country:uncomtrade:{_slug(str(record.get('partner_code', '')))}"
            entities.append(
                MedicalEntity(
                    entity_type="Country",
                    name=partner_name,
                    canonical_key=partner_key,
                    external_ids=_compact_ids(
                        {
                            "un_comtrade_code": str(record.get("partner_code", "")).strip(),
                            "iso3": str(record.get("partner_iso", "")).strip(),
                        }
                    ),
                    attributes={"role": "partner"},
                    evidence=[evidence],
                    confidence=0.95,
                )
            )
            relationships.append(
                ExtractedRelationship(
                    relationship_type="ABOUT",
                    from_entity_key=trade_flow.trade_flow_key,
                    to_entity_key=partner_key,
                    evidence=[evidence],
                    attributes={"role": "partner"},
                    confidence=0.92,
                )
            )
        return MedicalExtractionOutput(
            entities=entities,
            trade_flow_observations=[trade_flow],
            relationships=relationships,
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )

    def extract_freight_proxy_prices(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        observation_date = str(record.get("observation_date", "")).strip()
        observed_at = _parse_source_date(observation_date)
        value = _maybe_float(record.get("value"))
        if observed_at is None or value is None:
            return MedicalExtractionOutput(
                warnings=[f"Skipped invalid freight proxy row: {observation_date}"]
            )
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=observed_at,
            confidence=0.98,
            method="deterministic_nyfed_gscpi_v1",
        )
        observation = LogisticsPressureObservation(
            observation_key=f"LogisticsPressureObservation:nyfed_gscpi:{_slug(observation_date)}",
            index_name=str(record.get("index_name", "")).strip()
            or "New York Fed Global Supply Chain Pressure Index",
            observed_at=observed_at,
            value=value,
            unit=str(record.get("unit", "")).strip() or "standard_deviations_from_average",
            attributes={
                "source_series": record.get("source_series"),
                "observation_date": observation_date,
                "latest_vintage_serial": record.get("latest_vintage_serial"),
                "latest_vintage_date": record.get("latest_vintage_date"),
                "source_file": record.get("source_file"),
                "source_caveat": (
                    "GSCPI is a public aggregate supply-chain pressure index. "
                    "Use it as a logistics and freight-pressure proxy, not as a "
                    "route-specific freight price."
                ),
            },
            evidence=[evidence],
            confidence=0.98,
        )
        return MedicalExtractionOutput(
            logistics_pressure_observations=[observation],
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )

    def extract_search_trend_signals(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        observed_at = _parse_iso_datetime(str(record.get("observed_at", "")).strip())
        value = _maybe_float(record.get("value"))
        if observed_at is None or value is None:
            return MedicalExtractionOutput(
                warnings=[f"Skipped invalid search trend observation: {record.get('raw_date')}"]
            )
        query = str(record.get("query", "")).strip() or None
        signal_name = str(record.get("signal_name", "")).strip() or "GDELT DOC news volume trend"
        unit = str(record.get("unit", "")).strip() or "timeline_value"
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=observed_at,
            confidence=0.82,
            method="deterministic_gdelt_search_trends_v1",
        )
        observation = TrendSignalObservation(
            signal_key=(
                "TrendSignalObservation:gdelt:"
                f"{_slug(query or signal_name)}:{_slug(observed_at.isoformat())}"
            ),
            signal_name=signal_name,
            observed_at=observed_at,
            value=value,
            unit=unit,
            query=query,
            window=str(record.get("window", "")).strip() or None,
            attributes={
                "mode": record.get("mode"),
                "raw_date": record.get("raw_date"),
                "raw_value": record.get("raw_value"),
                "article_count": record.get("article_count"),
                "normalized_volume": record.get("normalized_volume"),
                "source_api": record.get("source_api"),
                "source_caveat": (
                    "GDELT timeline volume is an aggregate public news-volume proxy. "
                    "It is not verified search intent, product demand, or proof that "
                    "publisher article claims are true."
                ),
            },
            evidence=[evidence],
            confidence=0.82,
        )
        return MedicalExtractionOutput(
            trend_signal_observations=[observation],
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )

    def extract_reliefweb_reports(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        report_id = str(record.get("reliefweb_id", "")).strip()
        title = str(record.get("title", "")).strip()
        url = str(record.get("url", "")).strip()
        original_date = str(record.get("date_original", "")).strip()
        created_date = str(record.get("date_created", "")).strip()
        observed_at = _parse_iso_datetime(original_date) or _parse_iso_datetime(created_date)
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=observed_at or document.fetched_at,
            confidence=0.75,
            method="deterministic_reliefweb_reports_v1",
        )
        stable_key = report_id or hashlib.sha256((url or title).encode("utf-8")).hexdigest()[:16]
        news_event = NewsEvent(
            news_key=f"NewsEvent:reliefweb:{_slug(stable_key)}",
            title=title or url or f"ReliefWeb report {report_id}",
            url=url or None,
            event_status="unverified",
            observed_at=observed_at,
            attributes={
                "reliefweb_id": report_id,
                "api_href": record.get("api_href"),
                "score": record.get("score"),
                "status": record.get("status"),
                "date_original": original_date,
                "date_created": created_date,
                "date_changed": record.get("date_changed"),
                "source_names": record.get("source"),
                "source_shortnames": record.get("source_shortnames"),
                "countries": record.get("country"),
                "primary_countries": record.get("primary_country"),
                "themes": record.get("theme"),
                "disasters": record.get("disaster"),
                "formats": record.get("format"),
                "languages": record.get("language"),
                "source_caveat": (
                    "ReliefWeb report metadata is an official humanitarian information signal. "
                    "Partner report claims remain unverified until evidence verification runs."
                ),
            },
            evidence=[evidence],
            confidence=0.75,
        )
        return MedicalExtractionOutput(
            news_events=[news_event],
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )

    def extract_worldbank_commodity_prices(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        commodity_name = str(record.get("commodity_name", "")).strip()
        period = str(record.get("period", "")).strip()
        observed_at = _parse_worldbank_period(period)
        raw_unit = str(record.get("raw_unit", "")).strip()
        unit = _normalize_worldbank_unit(raw_unit)
        value = _maybe_float(record.get("value"))
        if observed_at is None or value is None:
            return MedicalExtractionOutput(
                warnings=[
                    f"Skipped invalid World Bank commodity price row: {commodity_name} {period}"
                ]
            )
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=observed_at,
            confidence=0.99,
            method="deterministic_worldbank_commodity_prices_monthly_v1",
        )
        observation = PriceObservation(
            observation_key=(f"PriceObservation:worldbank:{_slug(commodity_name)}:{_slug(period)}"),
            commodity_name=commodity_name,
            observed_at=observed_at,
            value=value,
            unit=unit,
            currency="USD" if "$" in raw_unit or unit.startswith("USD") else None,
            attributes={
                "period": period,
                "raw_unit": raw_unit,
                "updated_on": record.get("updated_on"),
                "source_table": record.get("source_table"),
                "source_caveat": (
                    "World Bank Pink Sheet prices are nominal monthly commodity price "
                    "observations. Use as input-cost signals, not product-specific costs."
                ),
            },
            evidence=[evidence],
            confidence=0.99,
        )
        return MedicalExtractionOutput(
            price_observations=[observation],
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )

    def extract_eia_energy_prices(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        commodity_name = str(record.get("commodity_name", "")).strip()
        period = str(record.get("period", "")).strip()
        observed_at = _parse_eia_period(period)
        raw_unit = str(record.get("raw_unit", "")).strip()
        unit = _normalize_eia_unit(raw_unit)
        value = _maybe_float(record.get("value"))
        if observed_at is None or value is None:
            return MedicalExtractionOutput(
                warnings=[f"Skipped invalid EIA energy price row: {commodity_name} {period}"]
            )
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=observed_at,
            confidence=0.99,
            method="deterministic_eia_energy_prices_v1",
        )
        observation = PriceObservation(
            observation_key=(
                "PriceObservation:eia:"
                f"{_slug(commodity_name)}:"
                f"{_slug(str(record.get('area_code', '')))}:"
                f"{_slug(period)}"
            ),
            commodity_name=commodity_name or "EIA energy price",
            observed_at=observed_at,
            value=value,
            unit=unit,
            currency="USD" if raw_unit.startswith("$") or unit.startswith("USD") else None,
            attributes={
                "period": period,
                "frequency": record.get("frequency"),
                "raw_unit": raw_unit,
                "product_code": record.get("product_code"),
                "product_name": record.get("product_name"),
                "process_code": record.get("process_code"),
                "process_name": record.get("process_name"),
                "area_code": record.get("area_code"),
                "area_name": record.get("area_name"),
                "series_description": record.get("series_description"),
                "source_caveat": (
                    "EIA Open Data energy prices are public input-cost indicators. "
                    "Use as manufacturing and transport cost signals, not product-specific costs."
                ),
            },
            evidence=[evidence],
            confidence=0.99,
        )
        return MedicalExtractionOutput(
            price_observations=[observation],
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )

    def extract_gdacs_events(
        self,
        document: RawDocument,
        chunk: DocumentChunk,
        evidence_span_id: UUID | None = None,
    ) -> MedicalExtractionOutput:
        record: dict[str, Any] = dict(chunk.structured_data)
        event_type_code = str(record.get("gdacs_eventtype", "")).strip()
        event_id = str(record.get("gdacs_eventid", "")).strip()
        episode_id = str(record.get("gdacs_episodeid", "")).strip()
        alert_level = str(record.get("gdacs_alertlevel", "")).strip() or None
        country = str(record.get("gdacs_country", "")).strip()
        from_date = str(record.get("gdacs_fromdate", "")).strip()
        published = str(record.get("published", "")).strip()
        observed_at = _parse_rfc2822_date(from_date) or _parse_rfc2822_date(published)
        evidence = EvidenceRef(
            raw_document_id=document.id,
            document_chunk_id=chunk.id,
            evidence_span_id=evidence_span_id,
            source_id=document.source_id,
            source_url=document.source_url,
            observed_at=observed_at or document.fetched_at,
            confidence=0.95,
            method="deterministic_gdacs_events_rss_v1",
        )
        disaster_key = (
            f"DisasterEvent:gdacs:{_slug(event_type_code)}:{_slug(event_id)}:{_slug(episode_id)}"
        )
        severity = _metric_text(record.get("gdacs_severity"))
        disaster = DisasterEvent(
            disaster_key=disaster_key,
            disaster_type=_gdacs_event_type_name(event_type_code),
            location_name=country or None,
            severity=severity or None,
            alert_level=alert_level,
            observed_at=observed_at,
            attributes={
                "event_type_code": event_type_code,
                "event_id": event_id,
                "episode_id": episode_id,
                "title": record.get("title"),
                "summary": record.get("summary"),
                "alert_score": _maybe_float(record.get("gdacs_alertscore")),
                "episode_alert_level": record.get("gdacs_episodealertlevel"),
                "episode_alert_score": _maybe_float(record.get("gdacs_episodealertscore")),
                "date_added": record.get("gdacs_dateadded"),
                "date_modified": record.get("gdacs_datemodified"),
                "from_date": from_date,
                "to_date": record.get("gdacs_todate"),
                "is_current": record.get("gdacs_iscurrent"),
                "iso3": record.get("gdacs_iso3"),
                "country": country,
                "latitude": _maybe_float(record.get("geo_lat")),
                "longitude": _maybe_float(record.get("geo_long")),
                "severity": _metric_details(record.get("gdacs_severity")),
                "population": _metric_details(record.get("gdacs_population")),
                "vulnerability": _metric_details(record.get("gdacs_vulnerability")),
                "report_url": record.get("link"),
                "cap_url": record.get("gdacs_cap"),
                "source_caveat": (
                    "GDACS disaster alerts are near-real-time humanitarian impact signals. "
                    "Use them for exposure screening and preserve source attribution."
                ),
            },
            evidence=[evidence],
            confidence=0.95,
        )
        return MedicalExtractionOutput(
            disaster_events=[disaster],
            evidence_spans=[
                EvidenceSpanCandidate(quote=chunk.text, char_start=0, char_end=len(chunk.text))
            ],
        )


def extraction_input_hash(chunk: DocumentChunk) -> str:
    return hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()


def now_utc() -> datetime:
    return datetime.now(UTC)


def _slug(value: str) -> str:
    chars = [char.lower() if char.isalnum() else "_" for char in value.strip()]
    slug = "_".join(part for part in "".join(chars).split("_") if part)
    return slug or hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _first_openfda_value(record: dict[str, Any], field: str) -> str | None:
    openfda = record.get("openfda")
    if not isinstance(openfda, dict):
        return None
    raw = openfda.get(field)
    if isinstance(raw, list) and raw:
        return str(raw[0]).strip()
    if isinstance(raw, str):
        return raw.strip()
    return None


def _first_record_value(record: dict[str, Any], field: str) -> str | None:
    raw = record.get(field)
    if isinstance(raw, list) and raw:
        return str(raw[0]).strip()
    if isinstance(raw, str):
        return raw.strip()
    return None


def _device_name_from_registration(record: dict[str, Any]) -> str:
    return (
        _first_record_value(record, "proprietary_name")
        or str(record.get("device_name", "")).strip()
        or str(record.get("product_code", "")).strip()
    )


def _owner_operator_number(record: dict[str, Any]) -> str | None:
    owner_operator = record.get("owner_operator")
    if not isinstance(owner_operator, dict):
        return None
    value = owner_operator.get("owner_operator_number")
    return str(value).strip() if value else None


def _compact_ids(values: dict[str, str | None]) -> dict[str, str]:
    return {key: value for key, value in values.items() if value}


def _first_list_item(value: object) -> str | None:
    if isinstance(value, list) and value:
        return str(value[0]).strip() or None
    if isinstance(value, str):
        return value.strip() or None
    return None


def _inspection_event_type(dataset_type: str) -> str:
    if dataset_type == "citation":
        return "fda_inspection_citation"
    if dataset_type == "published_483":
        return "fda_published_483"
    return "fda_inspection_classification"


def _inspection_event_title(
    *,
    dataset_type: str,
    inspection_id: str,
    citation_id: str,
    legal_name: str,
) -> str:
    target = legal_name or inspection_id or "Unknown facility"
    if dataset_type == "citation":
        return f"FDA inspection citation: {citation_id or inspection_id or target}"
    if dataset_type == "published_483":
        return f"FDA published 483: {inspection_id or target}"
    return f"FDA inspection classification: {inspection_id or target}"


def _inspection_facility_name(legal_name: str, fei_number: str) -> str:
    if legal_name and fei_number:
        return f"{legal_name} FEI {fei_number}"
    return legal_name or f"FDA inspected facility FEI {fei_number}"


def _parse_source_date(value: str) -> datetime | None:
    if not value:
        return None
    for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, date_format)
        except ValueError:
            continue
        return parsed.replace(tzinfo=UTC)
    return None


def _parse_gdelt_seen_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return _parse_source_date(value)


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return _parse_source_date(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_worldbank_period(value: str) -> datetime | None:
    if not value or "M" not in value:
        return None
    year, month = value.split("M", 1)
    try:
        return datetime(int(year), int(month), 1, tzinfo=UTC)
    except ValueError:
        return None


def _normalize_worldbank_unit(value: str) -> str:
    unit = value.strip().strip("()")
    if unit.startswith("$/"):
        return f"USD/{unit[2:]}"
    return unit or "unknown"


def _parse_eia_period(value: str) -> datetime | None:
    if not value:
        return None
    for date_format in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            parsed = datetime.strptime(value, date_format)
        except ValueError:
            continue
        return parsed.replace(tzinfo=UTC)
    if "Q" in value:
        year, quarter = value.split("Q", 1)
        if len(year) != YEAR_DIGIT_COUNT or not year.isdigit() or not quarter.isdigit():
            return None
        month = ((int(quarter) - 1) * MONTHS_PER_QUARTER) + 1
        try:
            return datetime(int(year), month, 1, tzinfo=UTC)
        except ValueError:
            return None
    return None


def _parse_trade_period(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    for date_format in ("%Y-%m-%d", "%Y%m", "%Y"):
        try:
            parsed = datetime.strptime(text, date_format)
        except ValueError:
            continue
        return parsed.replace(tzinfo=UTC)
    return None


def _normalize_eia_unit(value: str) -> str:
    unit = value.strip()
    unit_upper = unit.upper()
    if unit_upper.startswith("$/"):
        return f"USD/{unit[2:].lower()}"
    if unit_upper in {"DOLLARS PER GALLON", "DOLLAR PER GALLON"}:
        return "USD/gal"
    if unit_upper in {"DOLLARS PER MILLION BTU", "DOLLARS PER MMBTU"}:
        return "USD/mmbtu"
    return unit or "unknown"


def _parse_rfc2822_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return _parse_source_date(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _gdacs_event_type_name(value: str) -> str:
    return {
        "DR": "drought",
        "EQ": "earthquake",
        "FL": "flood",
        "TC": "tropical_cyclone",
        "VO": "volcano",
        "WF": "wildfire",
    }.get(value.upper(), value.lower() or "unknown_disaster")


def _metric_text(value: object) -> str:
    if isinstance(value, dict):
        label = str(value.get("label") or value.get("value") or "").strip()
        unit = str(value.get("unit") or "").strip()
        if label and unit:
            return f"{label} {unit}"
        return label or unit
    return str(value or "").strip()


def _metric_details(value: object) -> dict[str, object] | str | None:
    if isinstance(value, dict):
        return {
            str(key): item for key, item in value.items() if item is not None and str(item).strip()
        }
    rendered = str(value or "").strip()
    return rendered or None


def _maybe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("value")
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
