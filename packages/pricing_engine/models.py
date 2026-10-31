"""Domain models for the deterministic pricing engine.

Field names always carry their unit (``*_toman``, ``*_gb``, ``*_hours``) - there is no bare ``amount``.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from .money import RIAL_PER_TOMAN, Dec, OptDec


class _Model(BaseModel):
    model_config = ConfigDict(frozen=False, extra="forbid", populate_by_name=True)


# --------------------------------------------------------------------------- catalog


class CatalogItem(_Model):
    """One price row, valid over [valid_from, valid_to). Never mutated once stored."""

    id: str
    provider_id: str
    service_type: str
    pricing_model: str
    product_family: str | None = None
    sku: str | None = None
    name: str
    region_country: str | None = None
    region: str | None = None
    datacenter: str | None = None
    resource_class: str | None = None
    cpu_cores: OptDec = None
    cpu_unit: str | None = None
    cpu_shared: bool | None = None
    ram_gb: OptDec = None
    storage_gb: OptDec = None
    storage_type: str | None = None
    gpu_model: str | None = None
    gpu_count: OptDec = None
    included_traffic_gb: OptDec = None
    traffic_direction: str | None = None
    bandwidth: str | None = None
    billing_period: str | None = None
    price_toman: OptDec = None
    hourly_price_toman: OptDec = None
    daily_price_toman: OptDec = None
    unit: str | None = None
    tier_min: OptDec = None
    tier_max: OptDec = None
    tier_unit: str | None = None
    availability: str = "available"
    source_url: str | None = None
    source_retrieved_at: str | None = None
    source_price_date: str | None = None
    confidence: str = "high"
    tax_included: bool | None = None
    notes: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    version_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def price_rial(self) -> Decimal | None:
        return None if self.price_toman is None else self.price_toman * RIAL_PER_TOMAN


class Provider(_Model):
    provider_id: str
    name_en: str
    name_fa: str | None = None
    website: str
    official_pricing_url: str | None = None
    country: str = "IR"
    provider_type: list[str] = Field(default_factory=list)
    pricing_model: str
    public_catalog_quality: str
    api_status: str = "not_verified"
    automation_surfaces: list[str] = Field(default_factory=list)
    recommended_mvp_priority: int | None = None
    integration_strategy: str | None = None
    notes: str | None = None


class BillingRule(_Model):
    rule_id: str
    provider_id: str
    scope: str
    rule_type: str
    status: str
    logic: dict[str, Any]
    source_url: str
    retrieved_at: str
    notes: str | None = None


# --------------------------------------------------------------------------- inventory side


class UsageMetrics(_Model):
    p95_cpu_percent: OptDec = None
    p95_ram_percent: OptDec = None
    disk_used_gb: OptDec = None
    observation_days: int | None = None
    source: str | None = None


class Resource(_Model):
    """A confirmed inventory resource as the engine sees it. Traffic/storage are per instance."""

    id: str
    name: str = ""
    provider_id: str | None = None
    service_type: str = "compute_vm"
    sku: str | None = None
    resource_class: str | None = None
    environment: str | None = None
    region_country: str | None = "IR"
    datacenter: str | None = None
    quantity: Dec = Decimal(1)
    cpu_cores: OptDec = None
    cpu_shared: bool | None = None
    ram_gb: OptDec = None
    storage_gb: OptDec = None
    storage_type: str | None = None
    gpu_model: str | None = None
    gpu_count: OptDec = None
    expected_monthly_download_gb: OptDec = None
    expected_monthly_upload_gb: OptDec = None
    active_hours_per_month: OptDec = None
    requires_public_ipv4: bool | None = False
    ipv4_count: OptDec = None
    billing_mode: Literal["monthly", "hourly"] = "monthly"
    metrics: UsageMetrics | None = None

    @property
    def effective_ipv4_count(self) -> Decimal:
        if self.ipv4_count is not None:
            return self.ipv4_count
        return Decimal(1) if self.requires_public_ipv4 else Decimal(0)


class BillingContext(_Model):
    include_tax: bool = False
    as_of: datetime | None = None
    allow_outside_iran: bool = False


# --------------------------------------------------------------------------- results


class LineStatus(StrEnum):
    PRICED = "priced"  # exact catalog price x quantity
    INCLUDED = "included"  # catalog explicitly says it is included / free
    ASSUMED_INCLUDED = "assumed_included"  # not in catalog; visible assumption, no number
    UNAVAILABLE = "unavailable"  # PRICE_UNAVAILABLE
    INFO = "info"  # discovery context, never summed


class PriceStatus(StrEnum):
    EXACT = "EXACT"
    PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"
    DISCOVERY_ONLY = "DISCOVERY_ONLY"


class PriceUnavailable(_Model):
    code: Literal["PRICE_UNAVAILABLE"] = "PRICE_UNAVAILABLE"
    component: str
    missing_field: str
    reason: str
    source: str | None = None


class ComponentLine(_Model):
    code: str
    description: str
    status: LineStatus
    quantity: OptDec = None
    unit: str | None = None
    unit_price_toman: OptDec = None
    subtotal_toman: OptDec = None
    catalog_item_id: str | None = None
    catalog_version_id: str | None = None
    source_url: str | None = None
    price_date: str | None = None
    retrieved_at: str | None = None
    note: str | None = None


class PriceBreakdown(_Model):
    resource_id: str
    resource_name: str = ""
    provider_id: str | None
    status: PriceStatus
    quantity: Dec
    components: list[ComponentLine] = Field(default_factory=list)
    tax_lines: list[ComponentLine] = Field(default_factory=list)
    monthly_total_toman: OptDec = None
    priced_subtotal_toman: Dec = Decimal(0)
    monthly_tax_toman: OptDec = None
    unavailable: list[PriceUnavailable] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def monthly_total_rial(self) -> Decimal | None:
        return None if self.monthly_total_toman is None else self.monthly_total_toman * RIAL_PER_TOMAN

    @computed_field  # type: ignore[prop-decorator]
    @property
    def monthly_total_with_tax_toman(self) -> Decimal | None:
        if self.monthly_total_toman is None or self.monthly_tax_toman is None:
            return None
        return self.monthly_total_toman + self.monthly_tax_toman


class ProviderTotal(_Model):
    provider_id: str
    monthly_total_toman: OptDec = None
    priced_subtotal_toman: Dec = Decimal(0)
    complete: bool


class Quote(_Model):
    """Immutable quote content. Persistence layers add an id; the content hash pins its inputs."""

    engine_version: str
    policy_version: str
    catalog_version: str
    catalog_snapshot_at: datetime
    complete: bool
    total_toman: OptDec = None
    priced_subtotal_toman: Dec
    total_tax_toman: OptDec = None
    breakdowns: list[PriceBreakdown]
    provider_totals: list[ProviderTotal]
    assumptions: list[str]
    unavailable: list[PriceUnavailable]
    price_sources: list[dict[str, Any]]
    inventory_hash: str
    content_hash: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_rial(self) -> Decimal | None:
        return None if self.total_toman is None else self.total_toman * RIAL_PER_TOMAN


class Difference(_Model):
    dimension: str
    source_value: Any = None
    candidate_value: Any = None
    verdict: Literal["same", "better", "worse", "different", "unknown"]
    note: str | None = None


class ConstraintResult(_Model):
    constraint_id: str
    passed: bool
    detail: str


class Comparison(_Model):
    resource_id: str
    candidate_provider_id: str
    candidate_label: str
    candidate_catalog_item_ids: list[str]
    current: PriceBreakdown
    candidate: PriceBreakdown
    constraints: list[ConstraintResult]
    passed_hard_constraints: bool
    fit_score: OptDec = None
    score_breakdown: dict[str, Dec] = Field(default_factory=dict)
    confidence: Literal["high", "medium", "NEEDS_HUMAN_REVIEW", "not_equivalent"]
    differences: list[Difference]
    monthly_saving_toman: OptDec = None
    monthly_saving_percent: OptDec = None
    exact: bool
    assumptions: list[str] = Field(default_factory=list)


def today_from(as_of: datetime | None) -> date:
    return (as_of or datetime.now()).date()
