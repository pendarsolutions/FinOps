"""ORM models. Money columns are Money (exact decimal) and always carry their unit in the name."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    inspect,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Money

JSONType = JSON().with_variant(JSONB(), "postgresql")


def uid() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class ImmutableRowError(RuntimeError):
    pass


# --------------------------------------------------------------------------- tenancy / auth


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    settings: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    locale: Mapped[str] = mapped_column(String(5), default="fa")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))  # owner | admin | analyst | viewer


# --------------------------------------------------------------------------- catalog (versioned)


class ProviderRow(Base):
    __tablename__ = "providers"
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name_en: Mapped[str] = mapped_column(String(200))
    name_fa: Mapped[str | None] = mapped_column(String(200))
    website: Mapped[str] = mapped_column(String(500))
    official_pricing_url: Mapped[str | None] = mapped_column(String(500))
    country: Mapped[str] = mapped_column(String(2), default="IR")
    pricing_model: Mapped[str] = mapped_column(String(100))
    api_status: Mapped[str] = mapped_column(String(50), default="not_verified")
    public_catalog_quality: Mapped[str] = mapped_column(String(20))
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class PriceSource(Base):
    __tablename__ = "price_sources"
    __table_args__ = (UniqueConstraint("provider_id", "source_url", "retrieved_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"))
    source_url: Mapped[str] = mapped_column(String(500))
    source_kind: Mapped[str] = mapped_column(String(20))  # official | secondary | invoice | api | seed
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    provider_price_date: Mapped[str | None] = mapped_column(String(20))
    content_hash: Mapped[str | None] = mapped_column(String(100))
    sync_status: Mapped[str] = mapped_column(String(20), default="ok")
    raw_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType)


class CatalogItemVersion(Base):
    """One immutable price version. Only ``valid_to`` may ever be set (once) to close it."""

    __tablename__ = "catalog_item_versions"
    __table_args__ = (Index("catalog_item_current_idx", "item_id", "valid_to"),
                      Index("catalog_provider_service_idx", "provider_id", "service_type", "valid_to"))
    version_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"))
    service_type: Mapped[str] = mapped_column(String(50))
    pricing_model: Mapped[str] = mapped_column(String(50))
    product_family: Mapped[str | None] = mapped_column(String(100))
    sku: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(300))
    region_country: Mapped[str | None] = mapped_column(String(2))
    region: Mapped[str | None] = mapped_column(String(100))
    datacenter: Mapped[str | None] = mapped_column(String(200))
    resource_class: Mapped[str | None] = mapped_column(String(50))
    cpu_cores: Mapped[Decimal | None] = mapped_column(Money(10, 3))
    cpu_unit: Mapped[str | None] = mapped_column(String(20))
    cpu_shared: Mapped[bool | None] = mapped_column(Boolean)
    ram_gb: Mapped[Decimal | None] = mapped_column(Money(12, 3))
    storage_gb: Mapped[Decimal | None] = mapped_column(Money(14, 3))
    storage_type: Mapped[str | None] = mapped_column(String(50))
    gpu_model: Mapped[str | None] = mapped_column(String(100))
    gpu_count: Mapped[Decimal | None] = mapped_column(Money(10, 3))
    included_traffic_gb: Mapped[Decimal | None] = mapped_column(Money(16, 3))
    traffic_direction: Mapped[str | None] = mapped_column(String(20))
    bandwidth: Mapped[str | None] = mapped_column(String(50))
    billing_period: Mapped[str | None] = mapped_column(String(20))
    price_toman: Mapped[Decimal | None] = mapped_column(Money())
    hourly_price_toman: Mapped[Decimal | None] = mapped_column(Money())
    daily_price_toman: Mapped[Decimal | None] = mapped_column(Money())
    unit: Mapped[str | None] = mapped_column(String(50))
    tier_min: Mapped[Decimal | None] = mapped_column(Money())
    tier_max: Mapped[Decimal | None] = mapped_column(Money())
    tier_unit: Mapped[str | None] = mapped_column(String(10))
    availability: Mapped[str] = mapped_column(String(20), default="available")
    confidence: Mapped[str] = mapped_column(String(20), default="high")
    tax_included: Mapped[bool | None] = mapped_column(Boolean)
    notes: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(500))
    source_retrieved_at: Mapped[str | None] = mapped_column(String(20))
    source_price_date: Mapped[str | None] = mapped_column(String(20))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_id: Mapped[int | None] = mapped_column(ForeignKey("price_sources.id"))
    signature: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


@event.listens_for(CatalogItemVersion, "before_update")
def _catalog_versions_are_immutable(mapper, connection, target):  # noqa: ANN001
    state = inspect(target)
    for attr in state.attrs:
        hist = attr.history
        if not hist.has_changes():
            continue
        if attr.key == "valid_to" and all(d is None for d in hist.deleted):
            continue  # closing an open version is the only allowed change
        raise ImmutableRowError(f"catalog version {target.version_id}: '{attr.key}' is immutable (insert a new version)")


class BillingRuleVersion(Base):
    __tablename__ = "billing_rule_versions"
    version_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    rule_id: Mapped[str] = mapped_column(String(100), index=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"))
    scope: Mapped[str] = mapped_column(String(50))
    rule_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50))
    logic: Mapped[dict[str, Any]] = mapped_column(JSONType)
    source_url: Mapped[str] = mapped_column(String(500))
    retrieved_at: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    signature: Mapped[str] = mapped_column(String(64))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PriceSyncRun(Base):
    __tablename__ = "price_sync_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))  # ok | warning | quarantined | failed | not_implemented | applied_after_review
    items_seen: Mapped[int] = mapped_column(Integer, default=0)
    items_changed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list[str]] = mapped_column(JSONType, default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    pending_items: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType)
    content_hash: Mapped[str | None] = mapped_column(String(100))
    triggered_by: Mapped[str | None] = mapped_column(String(100))


# --------------------------------------------------------------------------- inventory


class Inventory(Base):
    __tablename__ = "inventories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(10), default="TOMAN")
    status: Mapped[str] = mapped_column(String(30), default="draft")  # draft|needs_confirmation|confirmed|archived
    source_type: Mapped[str] = mapped_column(String(30))  # builder|chat|invoice|csv|...
    source_meta: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[str | None] = mapped_column(String(36))
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class InventoryResource(Base):
    __tablename__ = "inventory_resources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    inventory_id: Mapped[str] = mapped_column(ForeignKey("inventories.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200), default="")
    external_ref: Mapped[str | None] = mapped_column(String(200))
    environment: Mapped[str | None] = mapped_column(String(50))
    service_type: Mapped[str] = mapped_column(String(50), default="compute_vm")
    provider_id: Mapped[str | None] = mapped_column(String(50))
    sku: Mapped[str | None] = mapped_column(String(100))
    resource_class: Mapped[str | None] = mapped_column(String(50))
    region: Mapped[str | None] = mapped_column(String(100))
    datacenter: Mapped[str | None] = mapped_column(String(200))
    quantity: Mapped[Decimal | None] = mapped_column(Money(16, 4))
    cpu_cores: Mapped[Decimal | None] = mapped_column(Money(10, 3))
    cpu_shared: Mapped[bool | None] = mapped_column(Boolean)
    ram_gb: Mapped[Decimal | None] = mapped_column(Money(12, 3))
    storage_gb: Mapped[Decimal | None] = mapped_column(Money(14, 3))
    storage_type: Mapped[str | None] = mapped_column(String(50))
    gpu_model: Mapped[str | None] = mapped_column(String(100))
    gpu_count: Mapped[Decimal | None] = mapped_column(Money(10, 3))
    expected_monthly_download_gb: Mapped[Decimal | None] = mapped_column(Money(18, 3))
    expected_monthly_upload_gb: Mapped[Decimal | None] = mapped_column(Money(18, 3))
    active_hours_per_month: Mapped[Decimal | None] = mapped_column(Money(10, 2))
    requires_public_ipv4: Mapped[bool | None] = mapped_column(Boolean)
    ipv4_count: Mapped[Decimal | None] = mapped_column(Money(10, 0))
    billing_mode: Mapped[str | None] = mapped_column(String(10))
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    field_confidence: Mapped[dict[str, float]] = mapped_column(JSONType, default=dict)
    unknown_fields: Mapped[list[str]] = mapped_column(JSONType, default=list)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    raw_input: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class QuoteRow(Base):
    __tablename__ = "price_quotes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    inventory_id: Mapped[str] = mapped_column(ForeignKey("inventories.id"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    inventory_snapshot: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    catalog_version: Mapped[str] = mapped_column(String(40))
    policy_version: Mapped[str] = mapped_column(String(40))
    deterministic_engine_version: Mapped[str] = mapped_column(String(60))
    catalog_snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    complete: Mapped[bool] = mapped_column(Boolean)
    include_tax: Mapped[bool] = mapped_column(Boolean, default=False)
    total_toman: Mapped[Decimal | None] = mapped_column(Money())
    priced_subtotal_toman: Mapped[Decimal] = mapped_column(Money())
    total_tax_toman: Mapped[Decimal | None] = mapped_column(Money())
    content: Mapped[dict[str, Any]] = mapped_column(JSONType)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


@event.listens_for(QuoteRow, "before_update")
def _quotes_are_immutable(mapper, connection, target):  # noqa: ANN001
    raise ImmutableRowError("quotes are immutable; create a new quote")


class RecommendationRow(Base):
    __tablename__ = "recommendations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    key: Mapped[str] = mapped_column(String(40), index=True)
    inventory_id: Mapped[str] = mapped_column(ForeignKey("inventories.id"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    quote_id: Mapped[str | None] = mapped_column(ForeignKey("price_quotes.id"))
    analysis_id: Mapped[str] = mapped_column(String(36), index=True)
    rule_id: Mapped[str] = mapped_column(String(20))
    resource_id: Mapped[str | None] = mapped_column(String(36))
    resource_name: Mapped[str | None] = mapped_column(String(200))
    provider_id: Mapped[str | None] = mapped_column(String(50))
    recommendation_type: Mapped[str] = mapped_column(String(50))
    result_status: Mapped[str] = mapped_column(String(30))  # actionable | cannot_determine | informational
    title_en: Mapped[str] = mapped_column(String(300))
    title_fa: Mapped[str] = mapped_column(String(300))
    summary_en: Mapped[str] = mapped_column(Text)
    summary_fa: Mapped[str] = mapped_column(Text)
    current_cost_toman: Mapped[Decimal | None] = mapped_column(Money())
    candidate_cost_toman: Mapped[Decimal | None] = mapped_column(Money())
    monthly_saving_toman: Mapped[Decimal | None] = mapped_column(Money())
    monthly_saving_percent: Mapped[Decimal | None] = mapped_column(Money(10, 4))
    one_time_migration_cost_toman: Mapped[Decimal | None] = mapped_column(Money())
    payback_months: Mapped[Decimal | None] = mapped_column(Money(12, 3))
    payback_status: Mapped[str | None] = mapped_column(String(40))
    risk_level: Mapped[str] = mapped_column(String(20))
    effort_level: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[str] = mapped_column(String(30))
    price_dates: Mapped[list[str]] = mapped_column(JSONType, default=list)
    missing_inputs: Mapped[list[str]] = mapped_column(JSONType, default=list)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONType)
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# --------------------------------------------------------------------------- ops / security


class AIRun(Base):
    __tablename__ = "ai_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[str | None] = mapped_column(String(36))
    purpose: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40))
    input_redacted: Mapped[dict[str, Any]] = mapped_column(JSONType)
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    output_text: Mapped[str | None] = mapped_column(Text)
    guard_result: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True)
    user_id: Mapped[str | None] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    inventory_id: Mapped[str | None] = mapped_column(String(36))
    filename: Mapped[str] = mapped_column(String(300))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    delete_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --------------------------------------------------------------------------- monitored servers


class FleetKey(Base):
    """One SSH key per organization. The private half is encrypted at rest."""

    __tablename__ = "fleet_keys"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    public_key: Mapped[str] = mapped_column(Text)
    private_key_encrypted: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Server(Base):
    __tablename__ = "servers"
    __table_args__ = (UniqueConstraint("organization_id", "host", "port", name="uq_server_host"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=22)
    #: pending | online | unreachable | host_key_changed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    host_key: Mapped[str | None] = mapped_column(Text)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    hostname: Mapped[str | None] = mapped_column(String(200))
    os: Mapped[str | None] = mapped_column(String(200))
    cpu_cores: Mapped[int | None] = mapped_column(Integer)
    mem_total_kb: Mapped[int | None] = mapped_column(BigInteger)
    disk_total_kb: Mapped[int | None] = mapped_column(BigInteger)
    usage: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    # what the user confirmed: nothing is priced until a provider is set
    environment: Mapped[str | None] = mapped_column(String(50))
    provider_id: Mapped[str | None] = mapped_column(String(50))
    sku: Mapped[str | None] = mapped_column(String(100))
    resource_class: Mapped[str | None] = mapped_column(String(50))
    storage_type: Mapped[str | None] = mapped_column(String(50))
    download_gb_override: Mapped[Decimal | None] = mapped_column(Money(18, 3))
    upload_gb_override: Mapped[Decimal | None] = mapped_column(Money(18, 3))
    renewal_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ServerSample(Base):
    """Raw cumulative counters. Percentages and traffic are derived from these, never stored as guesses."""

    __tablename__ = "server_samples"
    __table_args__ = (Index("ix_server_samples_server_time", "server_id", "taken_at"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    server_id: Mapped[str] = mapped_column(ForeignKey("servers.id", ondelete="CASCADE"))
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cpu_total: Mapped[int] = mapped_column(BigInteger)
    cpu_idle: Mapped[int] = mapped_column(BigInteger)
    mem_total_kb: Mapped[int] = mapped_column(BigInteger)
    mem_available_kb: Mapped[int] = mapped_column(BigInteger)
    disk_total_kb: Mapped[int] = mapped_column(BigInteger)
    disk_used_kb: Mapped[int] = mapped_column(BigInteger)
    rx_bytes: Mapped[int] = mapped_column(BigInteger)
    tx_bytes: Mapped[int] = mapped_column(BigInteger)
