from datetime import UTC, datetime

from supply_intel.models.extraction import MedicalExtractionOutput
from supply_intel.models.graph import (
    GraphMappingOutput,
    GraphNodeUpsert,
    GraphRelationshipUpsert,
    RelationshipProvenance,
)
from supply_intel.models.source import RawDocument

LABEL_BY_ENTITY_TYPE = {
    "Drug": "Drug",
    "NDC": "NDC",
    "ActiveIngredient": "ActiveIngredient",
    "Manufacturer": "Manufacturer",
    "Supplier": "Supplier",
    "Facility": "Facility",
    "MedicalDevice": "MedicalDevice",
    "DeviceCategory": "DeviceCategory",
    "RegulatoryAgency": "RegulatoryAgency",
    "Country": "Country",
    "Region": "Region",
    "City": "City",
    "Port": "Port",
    "TransportRoute": "TransportRoute",
    "Commodity": "Commodity",
}


def map_extraction_to_graph(
    document: RawDocument,
    extraction: MedicalExtractionOutput,
) -> GraphMappingOutput:
    node_upserts: list[GraphNodeUpsert] = []
    relationship_upserts: list[GraphRelationshipUpsert] = []
    skipped: list[str] = []

    for entity in extraction.entities:
        label = LABEL_BY_ENTITY_TYPE.get(entity.entity_type)
        if label is None:
            skipped.append(entity.canonical_key)
            continue
        evidence = entity.evidence[0] if entity.evidence else None
        node_upserts.append(
            GraphNodeUpsert(
                graph_node_key=entity.canonical_key,
                labels=[label],
                properties={
                    "key": entity.canonical_key,
                    "name": entity.name,
                    "external_ids": entity.external_ids,
                    "attributes": entity.attributes,
                    "confidence": entity.confidence,
                    "status": "active",
                },
                source_document_id=document.id,
                evidence_span_id=evidence.evidence_span_id if evidence else None,
                extraction_run_id=evidence.extraction_run_id if evidence else None,
                confidence=entity.confidence,
            )
        )

    for recall in extraction.recall_events:
        node_upserts.append(
            GraphNodeUpsert(
                graph_node_key=recall.recall_key,
                labels=["Recall"],
                properties={
                    "key": recall.recall_key,
                    "name": recall.recall_number or recall.product_description,
                    "recall_number": recall.recall_number,
                    "product_description": recall.product_description,
                    "classification": recall.classification,
                    "reason": recall.reason,
                    "status": recall.status or "active",
                    "confidence": recall.confidence,
                },
                source_document_id=document.id,
                evidence_span_id=(recall.evidence[0].evidence_span_id if recall.evidence else None),
                confidence=recall.confidence,
            )
        )

    for shortage in extraction.shortage_events:
        node_upserts.append(
            GraphNodeUpsert(
                graph_node_key=shortage.shortage_key,
                labels=["Shortage"],
                properties={
                    "key": shortage.shortage_key,
                    "name": shortage.product_name,
                    "product_name": shortage.product_name,
                    "status": shortage.status,
                    "reason": shortage.reason,
                    "confidence": shortage.confidence,
                },
                source_document_id=document.id,
                evidence_span_id=(
                    shortage.evidence[0].evidence_span_id if shortage.evidence else None
                ),
                extraction_run_id=(
                    shortage.evidence[0].extraction_run_id if shortage.evidence else None
                ),
                confidence=shortage.confidence,
            )
        )

    for regulatory_event in extraction.regulatory_events:
        evidence = regulatory_event.evidence[0] if regulatory_event.evidence else None
        node_upserts.append(
            GraphNodeUpsert(
                graph_node_key=regulatory_event.event_key,
                labels=["RegulatoryNotice"],
                properties={
                    "key": regulatory_event.event_key,
                    "name": regulatory_event.title,
                    "event_type": regulatory_event.event_type,
                    "agency": regulatory_event.agency,
                    "observed_at": regulatory_event.observed_at,
                    "attributes": regulatory_event.attributes,
                    "confidence": regulatory_event.confidence,
                    "status": "active",
                },
                source_document_id=document.id,
                evidence_span_id=evidence.evidence_span_id if evidence else None,
                extraction_run_id=evidence.extraction_run_id if evidence else None,
                confidence=regulatory_event.confidence,
            )
        )

    for news_event in extraction.news_events:
        evidence = news_event.evidence[0] if news_event.evidence else None
        node_upserts.append(
            GraphNodeUpsert(
                graph_node_key=news_event.news_key,
                labels=["NewsEvent"],
                properties={
                    "key": news_event.news_key,
                    "name": news_event.title,
                    "title": news_event.title,
                    "url": news_event.url,
                    "event_status": news_event.event_status,
                    "observed_at": news_event.observed_at,
                    "attributes": news_event.attributes,
                    "confidence": news_event.confidence,
                    "status": "active",
                },
                source_document_id=document.id,
                evidence_span_id=evidence.evidence_span_id if evidence else None,
                extraction_run_id=evidence.extraction_run_id if evidence else None,
                confidence=news_event.confidence,
            )
        )

    for disaster_event in extraction.disaster_events:
        evidence = disaster_event.evidence[0] if disaster_event.evidence else None
        node_upserts.append(
            GraphNodeUpsert(
                graph_node_key=disaster_event.disaster_key,
                labels=["DisasterEvent"],
                properties={
                    "key": disaster_event.disaster_key,
                    "name": disaster_event.location_name or disaster_event.disaster_type,
                    "disaster_type": disaster_event.disaster_type,
                    "location_name": disaster_event.location_name,
                    "severity": disaster_event.severity,
                    "alert_level": disaster_event.alert_level,
                    "observed_at": disaster_event.observed_at,
                    "attributes": disaster_event.attributes,
                    "confidence": disaster_event.confidence,
                    "status": "active",
                },
                source_document_id=document.id,
                evidence_span_id=evidence.evidence_span_id if evidence else None,
                extraction_run_id=evidence.extraction_run_id if evidence else None,
                confidence=disaster_event.confidence,
            )
        )

    for price_observation in extraction.price_observations:
        evidence = price_observation.evidence[0] if price_observation.evidence else None
        node_upserts.append(
            GraphNodeUpsert(
                graph_node_key=price_observation.observation_key,
                labels=["PriceObservation"],
                properties={
                    "key": price_observation.observation_key,
                    "name": (
                        f"{price_observation.commodity_name} "
                        f"{price_observation.observed_at.date().isoformat()}"
                    ),
                    "commodity_name": price_observation.commodity_name,
                    "observed_at": price_observation.observed_at,
                    "value": price_observation.value,
                    "unit": price_observation.unit,
                    "currency": price_observation.currency,
                    "attributes": price_observation.attributes,
                    "confidence": price_observation.confidence,
                    "status": "active",
                },
                source_document_id=document.id,
                evidence_span_id=evidence.evidence_span_id if evidence else None,
                extraction_run_id=evidence.extraction_run_id if evidence else None,
                confidence=price_observation.confidence,
            )
        )

    for trade_flow in extraction.trade_flow_observations:
        evidence = trade_flow.evidence[0] if trade_flow.evidence else None
        node_upserts.append(
            GraphNodeUpsert(
                graph_node_key=trade_flow.trade_flow_key,
                labels=["TradeFlowObservation"],
                properties={
                    "key": trade_flow.trade_flow_key,
                    "name": (
                        f"{trade_flow.flow} {trade_flow.commodity_code} "
                        f"{trade_flow.reporter_name} {trade_flow.period}"
                    ),
                    "reporter_name": trade_flow.reporter_name,
                    "partner_name": trade_flow.partner_name,
                    "commodity_code": trade_flow.commodity_code,
                    "commodity_description": trade_flow.commodity_description,
                    "flow": trade_flow.flow,
                    "period": trade_flow.period,
                    "observed_at": trade_flow.observed_at,
                    "primary_value_usd": trade_flow.primary_value_usd,
                    "net_weight_kg": trade_flow.net_weight_kg,
                    "quantity": trade_flow.quantity,
                    "quantity_unit": trade_flow.quantity_unit,
                    "attributes": trade_flow.attributes,
                    "confidence": trade_flow.confidence,
                    "status": "active",
                },
                source_document_id=document.id,
                evidence_span_id=evidence.evidence_span_id if evidence else None,
                extraction_run_id=evidence.extraction_run_id if evidence else None,
                confidence=trade_flow.confidence,
            )
        )

    for logistics_pressure in extraction.logistics_pressure_observations:
        evidence = logistics_pressure.evidence[0] if logistics_pressure.evidence else None
        node_upserts.append(
            GraphNodeUpsert(
                graph_node_key=logistics_pressure.observation_key,
                labels=["LogisticsPressureObservation"],
                properties={
                    "key": logistics_pressure.observation_key,
                    "name": (
                        f"{logistics_pressure.index_name} "
                        f"{logistics_pressure.observed_at.date().isoformat()}"
                    ),
                    "index_name": logistics_pressure.index_name,
                    "observed_at": logistics_pressure.observed_at,
                    "value": logistics_pressure.value,
                    "unit": logistics_pressure.unit,
                    "attributes": logistics_pressure.attributes,
                    "confidence": logistics_pressure.confidence,
                    "status": "active",
                },
                source_document_id=document.id,
                evidence_span_id=evidence.evidence_span_id if evidence else None,
                extraction_run_id=evidence.extraction_run_id if evidence else None,
                confidence=logistics_pressure.confidence,
            )
        )

    for trend_signal in extraction.trend_signal_observations:
        evidence = trend_signal.evidence[0] if trend_signal.evidence else None
        node_upserts.append(
            GraphNodeUpsert(
                graph_node_key=trend_signal.signal_key,
                labels=["TrendSignalObservation"],
                properties={
                    "key": trend_signal.signal_key,
                    "name": (
                        f"{trend_signal.signal_name} {trend_signal.observed_at.date().isoformat()}"
                    ),
                    "signal_name": trend_signal.signal_name,
                    "observed_at": trend_signal.observed_at,
                    "value": trend_signal.value,
                    "unit": trend_signal.unit,
                    "query": trend_signal.query,
                    "window": trend_signal.window,
                    "attributes": trend_signal.attributes,
                    "confidence": trend_signal.confidence,
                    "status": "active",
                },
                source_document_id=document.id,
                evidence_span_id=evidence.evidence_span_id if evidence else None,
                extraction_run_id=evidence.extraction_run_id if evidence else None,
                confidence=trend_signal.confidence,
            )
        )

    for relationship in extraction.relationships:
        evidence = relationship.evidence[0]
        relationship_upserts.append(
            GraphRelationshipUpsert(
                relationship_key=(
                    f"{relationship.from_entity_key}|{relationship.relationship_type}|"
                    f"{relationship.to_entity_key}"
                ),
                from_key=relationship.from_entity_key,
                to_key=relationship.to_entity_key,
                relationship_type=relationship.relationship_type,
                properties=RelationshipProvenance(
                    confidence=relationship.confidence,
                    source_document_id=document.id,
                    evidence_span_id=evidence.evidence_span_id,
                    extraction_run_id=evidence.extraction_run_id,
                    observed_at=evidence.observed_at,
                    valid_from=datetime.now(UTC),
                    source_name=document.source_id,
                    source_url=document.source_url,
                    method=evidence.method,
                    status="active",
                ),
            )
        )

    return GraphMappingOutput(
        node_upserts=node_upserts,
        relationship_upserts=relationship_upserts,
        skipped_items=skipped,
    )
