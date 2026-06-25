from datetime import datetime
from typing import Literal

from pydantic import Field

from supply_intel.models.base import EvidenceRef, VersionedModel


class RegulatoryEvent(VersionedModel):
    event_key: str
    event_type: str
    title: str
    agency: str | None = None
    observed_at: datetime | None = None
    attributes: dict[str, object] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)


class RecallEvent(VersionedModel):
    recall_key: str
    recall_number: str | None = None
    product_description: str
    classification: str | None = None
    reason: str | None = None
    status: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)


class ShortageEvent(VersionedModel):
    shortage_key: str
    product_name: str
    status: str
    reason: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)


class NewsEvent(VersionedModel):
    news_key: str
    title: str
    url: str | None = None
    event_status: Literal["unverified", "verified"] = "unverified"
    observed_at: datetime | None = None
    attributes: dict[str, object] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)


class DisasterEvent(VersionedModel):
    disaster_key: str
    disaster_type: str
    location_name: str | None = None
    severity: str | None = None
    alert_level: str | None = None
    observed_at: datetime | None = None
    attributes: dict[str, object] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)


class StrikeEvent(VersionedModel):
    strike_key: str
    organization: str | None = None
    location_name: str | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0, le=1)


class PriceObservation(VersionedModel):
    observation_key: str
    commodity_name: str
    observed_at: datetime
    value: float
    unit: str
    currency: str | None = None
    attributes: dict[str, object] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)


class TradeFlowObservation(VersionedModel):
    trade_flow_key: str
    reporter_name: str
    partner_name: str
    commodity_code: str
    commodity_description: str
    flow: str
    period: str
    observed_at: datetime
    primary_value_usd: float | None = None
    net_weight_kg: float | None = None
    quantity: float | None = None
    quantity_unit: str | None = None
    attributes: dict[str, object] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)


class LogisticsPressureObservation(VersionedModel):
    observation_key: str
    index_name: str
    observed_at: datetime
    value: float
    unit: str
    attributes: dict[str, object] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)


class TrendSignalObservation(VersionedModel):
    signal_key: str
    signal_name: str
    observed_at: datetime
    value: float
    unit: str
    query: str | None = None
    window: str | None = None
    attributes: dict[str, object] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0, le=1)
