"""Inventory draft contract shared by the guided builder, chat extraction and invoice extraction,
plus the deterministic rules that decide which fields must be confirmed before pricing."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pricing_engine.money import OptDec


class ReviewStatus(StrEnum):
    CONFIRMED = "confirmed"
    NEEDS_REVIEW = "needs_review"
    UNRESOLVED = "unresolved"


class ResourceDraft(BaseModel):
    """One inventory row as produced by any entry path. Every spec may be unknown (None)."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    external_ref: str | None = None
    environment: str | None = None
    service_type: Literal["compute_vm", "paas", "dbaas", "object_storage"] = "compute_vm"
    provider_id: str | None = None
    sku: str | None = None
    resource_class: str | None = None
    region: str | None = None
    datacenter: str | None = None
    quantity: OptDec = None
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
    requires_public_ipv4: bool | None = None
    ipv4_count: OptDec = None
    billing_mode: Literal["monthly", "hourly"] | None = None
    metrics: dict[str, Any] | None = None
    #: per-field extraction confidence in [0,1] (chat/invoice paths); builder rows are 1.0
    field_confidence: dict[str, float] = Field(default_factory=dict)
    #: fields the user explicitly marked "I don't know"
    unknown_fields: list[str] = Field(default_factory=list)
    notes: str | None = None


class InventoryDraft(BaseModel):
    """Strict JSON contract the LLM must return for chat-to-inventory."""

    model_config = ConfigDict(extra="forbid")

    name: str = "Draft inventory"
    resources: list[ResourceDraft]
    questions: list[str] = Field(default_factory=list, description="Clarifying questions for the user")
    detected_currency: Literal["TOMAN", "RIAL", "UNKNOWN"] | None = None


FIELD_LABELS = {
    "provider_id": ("Provider", "ارائه‌دهنده"),
    "sku": ("SKU / plan", "پلن"),
    "resource_class": ("Resource class", "کلاس منابع"),
    "cpu_cores": ("vCPU", "پردازنده"),
    "ram_gb": ("RAM (GB)", "رم (GB)"),
    "storage_gb": ("Disk (GB)", "دیسک (GB)"),
    "storage_type": ("Disk type", "نوع دیسک"),
    "expected_monthly_download_gb": ("Download GB/month", "دانلود ماهانه (GB)"),
    "expected_monthly_upload_gb": ("Upload GB/month", "آپلود ماهانه (GB)"),
    "active_hours_per_month": ("Runtime h/month", "ساعات کارکرد ماهانه"),
    "requires_public_ipv4": ("Public IPv4", "IPv4 عمومی"),
    "billing_mode": ("Billing mode", "نوع صورتحساب"),
    "quantity": ("Quantity", "تعداد"),
    "environment": ("Environment", "محیط"),
}

LOW_CONFIDENCE = 0.8


def required_fields(r: ResourceDraft, policy: dict[str, Any]) -> list[str]:
    """Financial fields the pricing engine needs for this resource (depends on the provider's pricing shape)."""
    req = ["provider_id", "quantity", "environment"]
    pol = policy.get("providers", {}).get(r.provider_id or "")
    if pol is None:
        return req
    strategy = pol["strategy"]
    if strategy == "component":
        if r.service_type == "compute_vm":
            req += ["resource_class", "cpu_cores", "ram_gb", "storage_gb", "storage_type",
                    "expected_monthly_download_gb", "expected_monthly_upload_gb", "requires_public_ipv4"]
        elif r.service_type == "dbaas":
            req += ["resource_class", "cpu_cores", "ram_gb", "storage_gb", "storage_type", "requires_public_ipv4"]
        elif r.service_type == "object_storage":
            req += ["storage_gb", "storage_type"]
    elif strategy == "liara_plan":
        req += ["sku", "billing_mode", "expected_monthly_download_gb", "expected_monthly_upload_gb"]
        if r.service_type == "compute_vm":
            req += ["requires_public_ipv4"]
        if r.billing_mode == "hourly":
            req += ["active_hours_per_month"]
    elif strategy == "fixed_sku":
        req += ["sku", "expected_monthly_download_gb"]
        if pol.get("included_traffic_direction") != "download":
            req += ["expected_monthly_upload_gb"]
    elif strategy == "daily_table":
        req += ["cpu_cores", "ram_gb", "storage_gb"]
    elif strategy == "discovery_only":
        req += ["sku"]
    return req


def missing_required_fields(r: ResourceDraft, policy: dict[str, Any]) -> list[str]:
    """Required fields that are neither filled nor explicitly marked unknown by the user."""
    return [f for f in required_fields(r, policy) if getattr(r, f) is None and f not in r.unknown_fields]


def review_status(r: ResourceDraft, policy: dict[str, Any], user_confirmed: bool) -> ReviewStatus:
    if missing_required_fields(r, policy):
        return ReviewStatus.UNRESOLVED
    # Low-confidence extracted fields are highlighted in the UI; the explicit user confirmation of the
    # row is what clears them.
    return ReviewStatus.CONFIRMED if user_confirmed else ReviewStatus.NEEDS_REVIEW


def low_confidence_fields(r: ResourceDraft) -> list[str]:
    return sorted(f for f, c in r.field_confidence.items() if c < LOW_CONFIDENCE)
