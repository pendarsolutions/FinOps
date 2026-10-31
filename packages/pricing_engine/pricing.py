"""Deterministic pricing: price_resource / price_inventory.

Rules enforced here:
* every number comes from a CatalogItem row (or a BillingRule for tax) - nothing is hardcoded;
* a missing price yields a PRICE_UNAVAILABLE line, never a silent zero;
* discovery-only rows (starting_price / calculator_snapshot) are shown but never summed;
* no rounding (engine_policy.rounding.mode == "none") - exact Decimal throughout.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from . import ENGINE_VERSION
from .catalog import CatalogSnapshot
from .models import (
    BillingContext,
    CatalogItem,
    ComponentLine,
    LineStatus,
    PriceBreakdown,
    PriceStatus,
    PriceUnavailable,
    ProviderTotal,
    Quote,
    Resource,
)
from .money import ZERO, dsum

ONE = Decimal(1)


class _Builder:
    """Accumulates lines for one resource, then finalizes into a PriceBreakdown."""

    def __init__(self, resource: Resource, snapshot: CatalogSnapshot):
        self.r = resource
        self.snap = snapshot
        self.lines: list[ComponentLine] = []
        self.tax_lines: list[ComponentLine] = []
        self.unavailable: list[PriceUnavailable] = []
        self.assumptions: list[str] = []
        self.discovery_only = False

    # -- line helpers ------------------------------------------------------
    def priced(self, code: str, desc: str, item: CatalogItem, qty: Decimal, unit_price: Decimal | None, unit: str,
               note: str | None = None) -> None:
        if unit_price is None:
            self.missing(code, "price_toman", f"catalog row {item.id} has no price for this billing unit", item.source_url)
            return
        status = LineStatus.INCLUDED if unit_price == ZERO else LineStatus.PRICED
        self.lines.append(
            ComponentLine(
                code=code, description=desc, status=status, quantity=qty, unit=unit, unit_price_toman=unit_price,
                subtotal_toman=qty * unit_price, catalog_item_id=item.id, catalog_version_id=item.version_id,
                source_url=item.source_url, price_date=item.source_price_date, retrieved_at=item.source_retrieved_at,
                note=note,
            )
        )

    def missing(self, component: str, field: str, reason: str, source: str | None = None) -> None:
        self.unavailable.append(PriceUnavailable(component=component, missing_field=field, reason=reason, source=source))
        self.lines.append(ComponentLine(code=component, description=reason, status=LineStatus.UNAVAILABLE))

    def assumed_included(self, code: str, desc: str, note: str) -> None:
        self.lines.append(ComponentLine(code=code, description=desc, status=LineStatus.ASSUMED_INCLUDED, note=note))
        self.assume(note)

    def assume(self, text: str) -> None:
        if text not in self.assumptions:
            self.assumptions.append(text)

    def require(self, component: str, field: str) -> Any:
        value = getattr(self.r, field)
        if value is None:
            self.missing(component, field, f"'{field}' is not known for this resource; confirm it or mark it unknown")
        return value

    # -- finalize ----------------------------------------------------------
    def finish(self) -> PriceBreakdown:
        priced_sum = dsum(l.subtotal_toman for l in self.lines if l.subtotal_toman is not None
                          and l.status in (LineStatus.PRICED, LineStatus.INCLUDED))
        if self.discovery_only:
            status = PriceStatus.DISCOVERY_ONLY
        elif self.unavailable:
            status = PriceStatus.PRICE_UNAVAILABLE
        else:
            status = PriceStatus.EXACT
        total = priced_sum if status == PriceStatus.EXACT else None
        tax_total = dsum(l.subtotal_toman for l in self.tax_lines if l.subtotal_toman is not None) if self.tax_lines else None
        if tax_total is not None and total is None:
            tax_total = None
        return PriceBreakdown(
            resource_id=self.r.id, resource_name=self.r.name, provider_id=self.r.provider_id, status=status,
            quantity=self.r.quantity, components=self.lines, tax_lines=self.tax_lines if total is not None else [],
            monthly_total_toman=total, priced_subtotal_toman=priced_sum, monthly_tax_toman=tax_total,
            unavailable=self.unavailable, assumptions=self.assumptions,
        )


# =========================================================================== helpers


def graduated_tiers(volume: Decimal, tiers: list[CatalogItem]) -> list[tuple[CatalogItem, Decimal]] | None:
    """Split ``volume`` across contiguous tiers. Returns None if the tiers have a gap or do not start at 0."""
    ordered = sorted(tiers, key=lambda t: t.tier_min if t.tier_min is not None else ZERO)
    expected_lo = ZERO
    out: list[tuple[CatalogItem, Decimal]] = []
    for idx, t in enumerate(ordered):
        lo = t.tier_min if t.tier_min is not None else ZERO
        if lo != expected_lo:
            return None
        hi = t.tier_max
        if hi is None and idx != len(ordered) - 1:
            return None
        in_tier = max(ZERO, (volume if hi is None else min(volume, hi)) - lo)
        out.append((t, in_tier))
        if hi is None:
            return out
        expected_lo = hi
    # last tier has an upper bound: volume beyond it is unpriced
    if volume > expected_lo:
        return None
    return out


def _tax(b: _Builder, ctx: BillingContext, provider_policy: dict[str, Any]) -> None:
    rule_id = provider_policy.get("tax_rule")
    if not rule_id:
        return
    rule = b.snap.billing_rules.get(rule_id)
    if rule is None or rule.status != "active":
        return
    if not ctx.include_tax:
        b.assume(f"Prices exclude tax. Provider rule {rule_id} adds {rule.logic.get('vat_percent')}% VAT on invoices "
                 "(shown separately when tax context is requested).")
        return
    pre_tax = dsum(l.subtotal_toman for l in b.lines if l.subtotal_toman is not None)
    pct = Decimal(str(rule.logic["vat_percent"]))
    b.tax_lines.append(ComponentLine(
        code="tax.vat", description=f"VAT {pct}% ({rule_id})", status=LineStatus.PRICED, quantity=pre_tax,
        unit="toman", unit_price_toman=pct / Decimal(100), subtotal_toman=pre_tax * pct / Decimal(100),
        source_url=rule.source_url, retrieved_at=rule.retrieved_at, note="Separate invoice line; not part of base price.",
    ))


def _traffic_volume(b: _Builder, direction: str, component: str) -> Decimal | None:
    field = "expected_monthly_download_gb" if direction == "download" else "expected_monthly_upload_gb"
    v = b.require(component, field)
    return None if v is None else v * b.r.quantity


# =========================================================================== strategies


def _price_arvan(b: _Builder, ctx: BillingContext, pol: dict[str, Any]) -> None:
    r = b.r
    if r.billing_mode == "hourly" or (r.active_hours_per_month is not None and r.active_hours_per_month < b.snap.hours_per_month):
        b.assume("ArvanCloud: " + pol["hourly_proration_note"])
    if r.service_type == "compute_vm":
        _arvan_vm(b, pol)
    elif r.service_type == "dbaas":
        _arvan_db(b)
    elif r.service_type == "object_storage":
        _arvan_object(b, pol)
    else:
        b.missing("service", "service_type", f"ArvanCloud service '{r.service_type}' has no pricing in the seed catalog")


def _arvan_vm(b: _Builder, pol: dict[str, Any]) -> None:
    r, q = b.r, b.r.quantity
    cls = b.require("compute.cpu", "resource_class")
    cpu = b.require("compute.cpu", "cpu_cores")
    ram = b.require("compute.ram", "ram_gb")
    if cls is not None:
        cpu_row = b.snap.find_one("arvancloud", service_type="compute_component", resource_class=cls)
        ram_row = b.snap.find_one("arvancloud", service_type="memory_component", resource_class=cls)
        if cpu_row is None or ram_row is None:
            b.missing("compute", "resource_class", f"no ArvanCloud CPU/RAM rate for class '{cls}'")
        else:
            if cpu is not None:
                b.priced("compute.cpu", f"vCPU ({cls})", cpu_row, cpu * q, cpu_row.price_toman, "vcore_month")
            if ram is not None:
                b.priced("compute.ram", f"RAM GB ({cls})", ram_row, ram * q, ram_row.price_toman, "gb_ram_month")
    if r.storage_gb is not None and r.storage_gb > 0:
        st = b.require("storage", "storage_type")
        if st is not None:
            row = b.snap.find_one("arvancloud", service_type="storage_component", storage_type=st)
            if row is None:
                valid = sorted({i.storage_type for i in b.snap.find("arvancloud", service_type="storage_component")})
                b.missing("storage", "storage_type", f"ArvanCloud has no block-storage rate for '{st}'; valid: {valid}")
            else:
                b.priced("storage", f"Block storage ({st})", row, r.storage_gb * q, row.price_toman, "gb_month")
    elif r.storage_gb is None:
        b.require("storage", "storage_gb")
    if r.gpu_model:
        row = b.snap.find_one("arvancloud", service_type="gpu_component", gpu_model=r.gpu_model)
        if row is None:
            b.missing("gpu", "gpu_model", f"no ArvanCloud GPU rate for '{r.gpu_model}'")
        else:
            b.priced("gpu", r.gpu_model, row, (r.gpu_count or ONE) * q, row.price_toman, "gpu_month")
    ips = r.effective_ipv4_count
    if ips > 0:
        first = b.snap.find_one("arvancloud", service_type="ipv4", sku="IR-IPV4-FIRST")
        extra = b.snap.find_one("arvancloud", service_type="ipv4", sku="IR-IPV4-EXTRA")
        if first is None:
            b.missing("ipv4", "price_toman", "ArvanCloud first-IPv4 rate missing from catalog")
        else:
            b.priced("ipv4.first", "First IPv4", first, q, first.price_toman, "ip_month")
            b.assume("ArvanCloud: " + pol["ipv4_note"])
        if ips > 1:
            if extra is None:
                b.missing("ipv4.extra", "price_toman", "ArvanCloud additional-IPv4 rate missing from catalog")
            else:
                b.priced("ipv4.extra", "Additional IPv4", extra, (ips - 1) * q, extra.price_toman, "ip_month")
    _arvan_traffic(b, pol)


def _arvan_traffic(b: _Builder, pol: dict[str, Any]) -> None:
    for resource_dir, catalog_dir in pol["traffic_direction_map"].items():
        component = f"traffic.{resource_dir}"
        volume = _traffic_volume(b, resource_dir, component)
        if volume is None:
            continue
        tiers = b.snap.find("arvancloud", service_type="network_traffic", traffic_direction=catalog_dir)
        if not tiers:
            b.missing(component, "price_toman", f"no ArvanCloud '{catalog_dir}' traffic rate in catalog")
            continue
        split = graduated_tiers(volume, tiers)
        if split is None:
            b.missing(component, "tier", f"ArvanCloud '{catalog_dir}' tiers do not cover {volume} GB contiguously")
            continue
        for tier, gb in split:
            if gb > 0 or len(split) == 1:
                rng = f"{tier.tier_min}-{tier.tier_max if tier.tier_max is not None else '∞'} GB"
                b.priced(f"{component}.{tier.sku}", f"Traffic {resource_dir} ({catalog_dir}) {rng}", tier, gb,
                         tier.price_toman, "gb")
        if not pol.get("traffic_direction_verified", False):
            b.assume("ArvanCloud: " + pol["traffic_direction_note"])
        b.assume("ArvanCloud: " + pol["tier_note"] + " Tiers are evaluated per inventory resource.")


def _arvan_db(b: _Builder) -> None:
    r, q = b.r, b.r.quantity
    cls = b.require("db.cpu", "resource_class")
    cpu = b.require("db.cpu", "cpu_cores")
    ram = b.require("db.ram", "ram_gb")
    if cls is not None:
        cpu_row = b.snap.find_one("arvancloud", service_type="dbaas_compute_component", resource_class=cls)
        ram_row = b.snap.find_one("arvancloud", service_type="dbaas_memory_component", resource_class=cls)
        if cpu_row is None or ram_row is None:
            b.missing("db", "resource_class", f"no ArvanCloud managed-DB rate for class '{cls}'")
        else:
            if cpu is not None:
                b.priced("db.cpu", f"DB vCPU ({cls})", cpu_row, cpu * q, cpu_row.price_toman, "vcore_month")
            if ram is not None:
                b.priced("db.ram", f"DB RAM GB ({cls})", ram_row, ram * q, ram_row.price_toman, "gb_ram_month")
    size = b.require("db.storage", "storage_gb")
    st = b.require("db.storage", "storage_type")
    if size is not None and st is not None:
        row = b.snap.find_one("arvancloud", service_type="dbaas_storage_component", storage_type=st)
        if row is None:
            b.missing("db.storage", "storage_type", f"no ArvanCloud managed-DB storage rate for '{st}'")
        else:
            b.priced("db.storage", f"DB storage ({st})", row, size * q, row.price_toman, "gb_month")
    if r.effective_ipv4_count > 0:
        row = b.snap.find_one("arvancloud", service_type="dbaas_ipv4")
        if row is None:
            b.missing("db.ipv4", "price_toman", "ArvanCloud DB IPv4 rate missing")
        else:
            b.priced("db.ipv4", "DB public IPv4", row, r.effective_ipv4_count * q, row.price_toman, "ip_month")
    net = b.snap.find_one("arvancloud", service_type="dbaas_network")
    if net is not None:
        traffic = (r.expected_monthly_download_gb or ZERO) + (r.expected_monthly_upload_gb or ZERO)
        b.priced("db.traffic", "DB upload/download traffic", net, traffic * q, net.price_toman, "gb")


def _arvan_object(b: _Builder, pol: dict[str, Any]) -> None:
    r, q = b.r, b.r.quantity
    size = b.require("object_storage", "storage_gb")
    st = r.storage_type or "object_standard"
    if size is None:
        return
    rows = b.snap.find("arvancloud", service_type="object_storage", storage_type=st)
    if not rows:
        b.missing("object_storage", "storage_type", f"no ArvanCloud object-storage rate for '{st}'")
        return
    if len(rows) == 1 and rows[0].pricing_model == "component_rate":
        b.priced("object_storage", f"Object storage ({st})", rows[0], size * q, rows[0].price_toman, "gb_month")
        return
    split = graduated_tiers(size * q, rows)
    if split is None:
        b.missing("object_storage", "tier", f"object-storage tiers do not cover {size * q} GB")
        return
    for tier, gb in split:
        if gb > 0:
            rng = f"{tier.tier_min}-{tier.tier_max if tier.tier_max is not None else '∞'} GB"
            b.priced(f"object_storage.{tier.sku}", f"Object storage {rng}", tier, gb, tier.price_toman, "gb_month")
    b.assume("ArvanCloud: " + pol["tier_note"])


def _plan_row(b: _Builder) -> CatalogItem | None:
    sku = b.require("plan", "sku")
    if sku is None:
        return None
    rows = b.snap.find(b.r.provider_id or "", sku=sku)
    if len(rows) != 1:
        b.missing("plan", "sku", f"SKU '{sku}' not found (or ambiguous) in {b.r.provider_id} catalog snapshot")
        return None
    row = rows[0]
    if row.availability != "available":
        b.assume(f"{row.provider_id} {row.sku} is marked '{row.availability}' in the catalog; priced as the current "
                 "plan but never offered as a recommendation.")
    return row


def _price_liara(b: _Builder, ctx: BillingContext, pol: dict[str, Any]) -> None:
    r, q = b.r, b.r.quantity
    row = _plan_row(b)
    if row is None:
        return
    hours = None
    if r.billing_mode == "hourly":
        hours = b.require("plan", "active_hours_per_month")
        if hours is not None:
            b.priced("plan", f"{row.name} hourly x {hours} h", row, hours * q, row.hourly_price_toman, "plan_hour")
            b.assume("Liara: " + pol["runtime_policy_note"])
    else:
        b.priced("plan", f"{row.name} monthly", row, q, row.price_toman, "plan_month")
    if r.storage_gb is not None and row.storage_gb is not None and r.storage_gb > row.storage_gb:
        b.missing("storage.extra", "price_toman", f"{r.storage_gb} GB requested > {row.storage_gb} GB in plan; Liara "
                  "extra-disk price is not in the seed")
    if row.service_type in pol.get("ipv4_scope", []):
        ips = r.effective_ipv4_count
        if ips > 0:
            ip_row = b.snap.find_one("liara", service_type="ipv4")
            if ip_row is None:
                b.missing("ipv4", "price_toman", "Liara IPv4 rate missing")
            elif hours is not None:
                b.priced("ipv4", f"IPv4 hourly x {hours} h", ip_row, ips * hours * q, ip_row.hourly_price_toman, "ip_hour")
            else:
                b.priced("ipv4", "IPv4 monthly", ip_row, ips * q, ip_row.price_toman, "ip_month")
        for direction in ("download", "upload"):
            vol = _traffic_volume(b, direction, f"traffic.{direction}")
            if vol is None:
                continue
            t_row = b.snap.find_one("liara", service_type="network_traffic", traffic_direction=direction)
            if t_row is None:
                b.missing(f"traffic.{direction}", "price_toman", f"Liara {direction} traffic rate missing")
            else:
                b.priced(f"traffic.{direction}", f"Traffic {direction}", t_row, vol, t_row.price_toman, "gb",
                         note=f"billing rule {pol.get('network_rule_id')}")
    elif row.service_type in ("paas", "dbaas"):
        for direction in ("download", "upload"):
            field = f"expected_monthly_{direction}_gb"
            v = getattr(r, field)
            if v is None or v > 0:
                b.missing(f"traffic.{direction}", field, f"Liara {row.service_type} {direction} traffic price is not in "
                          "the seed catalog (enter 0 if the app has no meaningful traffic)")


def _price_fixed_sku(b: _Builder, ctx: BillingContext, pol: dict[str, Any]) -> None:
    r, q = b.r, b.r.quantity
    row = _plan_row(b)
    if row is None:
        return
    if row.billing_period == "30_days":
        b.assume(f"{row.provider_id}: 30-day plan price used as the monthly price "
                 f"(engine policy: {b.snap.policy['days_per_month']['value']} days per month).")
    if r.billing_mode == "hourly":
        b.assume(f"{row.provider_id} {row.sku}: no hourly rate in the seed; priced at the monthly plan price.")
    b.priced("plan", f"{row.name} monthly", row, q, row.price_toman, "plan_month")
    if r.storage_gb is not None and row.storage_gb is not None and r.storage_gb > row.storage_gb:
        b.missing("storage.extra", "price_toman", f"{r.storage_gb} GB requested > {row.storage_gb} GB in plan; "
                  "extra-disk price is not in the seed")
    _fixed_traffic(b, row, pol)
    if r.effective_ipv4_count > 1:
        b.missing("ipv4.extra", "price_toman", f"additional IPv4 price for {row.provider_id} is not in the seed")
    if r.effective_ipv4_count > 0:
        b.assumed_included("ipv4", "Public IPv4", f"{row.provider_id}: one public IPv4 assumed included with the VPS plan "
                           "(the seed catalog does not state it).")


def _fixed_traffic(b: _Builder, row: CatalogItem, pol: dict[str, Any]) -> None:
    r = b.r
    policy = row.attributes.get("traffic_policy", "unknown")
    if policy == "unlimited":
        b.lines.append(ComponentLine(code="traffic", description="Traffic: unlimited per catalog", status=LineStatus.INCLUDED,
                                     subtotal_toman=ZERO, catalog_item_id=row.id, source_url=row.source_url,
                                     price_date=row.source_price_date, retrieved_at=row.source_retrieved_at))
        return
    if policy == "unlimited_rate_limited":
        b.lines.append(ComponentLine(code="traffic", description="Traffic: unlimited at rate limit", status=LineStatus.INCLUDED,
                                     subtotal_toman=ZERO, catalog_item_id=row.id, source_url=row.source_url,
                                     note=f"rate limited to {row.attributes.get('rate_limit_mbps')} Mbps"))
        b.assume(f"{row.provider_id} {row.sku}: download is unlimited but rate-limited to "
                 f"{row.attributes.get('rate_limit_mbps')} Mbps.")
        return
    download = b.require("traffic.download", "expected_monthly_download_gb")
    if policy == "metered_download":
        rate = row.attributes.get("download_toman_per_gb")
        if rate is None:
            b.missing("traffic.download", "download_toman_per_gb", f"{row.sku}: metered download without a rate",
                      row.source_url)
        elif download is not None:
            b.priced("traffic.download", "Traffic download (metered per GB)", row, download * r.quantity,
                     Decimal(str(rate)), "gb", note="rate from official plan description")
        return
    if policy == "fair_use":
        per_day = Decimal(str(row.attributes.get("fair_use_download_gb_per_day", "0")))
        days = Decimal(str(b.snap.policy["days_per_month"]["value"]))
        if download is not None:
            if download > per_day * days:
                b.missing("traffic.download", "overage_price", f"{download} GB/month exceeds fair use "
                          f"({per_day} GB/day); no overage price in the seed", row.source_url)
            else:
                b.lines.append(ComponentLine(code="traffic", description=f"Traffic within fair use ({per_day} GB/day)",
                                             status=LineStatus.INCLUDED, subtotal_toman=ZERO, catalog_item_id=row.id,
                                             source_url=row.source_url))
        return
    if policy == "included_quota":
        direction = pol.get("included_traffic_direction", "unspecified")
        if direction == "download":
            used = download
        else:
            upload = b.require("traffic.upload", "expected_monthly_upload_gb")
            used = None if download is None or upload is None else download + upload
            b.assume(f"{row.provider_id}: catalog does not state which direction the included traffic covers; "
                     "download + upload is compared against the quota (conservative).")
        if used is None:
            return
        if used > row.included_traffic_gb:
            b.missing("traffic.overage", "overage_price", f"{used} GB/month exceeds the {row.included_traffic_gb} GB "
                      f"included in {row.sku}; {row.provider_id} overage price is not in the seed", row.source_url)
        else:
            b.lines.append(ComponentLine(code="traffic", description=f"Traffic within included {row.included_traffic_gb} GB",
                                         status=LineStatus.INCLUDED, quantity=used, unit="gb", subtotal_toman=ZERO,
                                         catalog_item_id=row.id, source_url=row.source_url,
                                         price_date=row.source_price_date, retrieved_at=row.source_retrieved_at))
        return
    b.missing("traffic", "traffic_policy", f"{row.provider_id} {row.sku}: traffic terms are not in the seed catalog")


def _price_discovery(b: _Builder, ctx: BillingContext, pol: dict[str, Any]) -> None:
    b.discovery_only = True
    rows = b.snap.find(b.r.provider_id or "", sku=b.r.sku) if b.r.sku else b.snap.provider_items(b.r.provider_id or "")
    for row in rows:
        shown = row.daily_price_toman if row.daily_price_toman is not None else row.price_toman
        b.lines.append(ComponentLine(
            code="discovery", description=f"{row.name} ({row.pricing_model})", status=LineStatus.INFO,
            unit_price_toman=shown, unit=row.unit, catalog_item_id=row.id, source_url=row.source_url,
            price_date=row.source_price_date, retrieved_at=row.source_retrieved_at,
            note="Discovery context only - never summed or used for savings.",
        ))
    b.unavailable.append(PriceUnavailable(component="plan", missing_field="exact_configuration_price",
                                          reason=pol.get("reason", "provider is discovery-only"),
                                          source=rows[0].source_url if rows else None))


STRATEGIES = {
    "component": _price_arvan,
    "liara_plan": _price_liara,
    "fixed_sku": _price_fixed_sku,
    "discovery_only": _price_discovery,
}


# =========================================================================== public API


def price_resource(resource: Resource, snapshot: CatalogSnapshot, ctx: BillingContext | None = None) -> PriceBreakdown:
    ctx = ctx or BillingContext()
    b = _Builder(resource, snapshot)
    if resource.quantity <= 0:
        b.missing("quantity", "quantity", "quantity must be positive")
        return b.finish()
    pol = snapshot.provider_policy(resource.provider_id)
    if pol is None:
        b.missing("provider", "provider_id", f"provider '{resource.provider_id}' is not in the catalog policy")
        return b.finish()
    STRATEGIES[pol["strategy"]](b, ctx, pol)
    if not b.discovery_only and not b.unavailable:
        _tax(b, ctx, pol)
    return b.finish()


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def price_inventory(resources: list[Resource], snapshot: CatalogSnapshot, ctx: BillingContext | None = None) -> Quote:
    ctx = ctx or BillingContext()
    breakdowns = [price_resource(r, snapshot, ctx) for r in resources]
    by_provider: dict[str, list[PriceBreakdown]] = {}
    for bd in breakdowns:
        by_provider.setdefault(bd.provider_id or "unknown", []).append(bd)
    provider_totals = []
    for pid, bds in sorted(by_provider.items()):
        complete = all(x.status == PriceStatus.EXACT for x in bds)
        provider_totals.append(ProviderTotal(
            provider_id=pid, complete=complete,
            priced_subtotal_toman=dsum(x.priced_subtotal_toman for x in bds),
            monthly_total_toman=dsum(x.monthly_total_toman for x in bds) if complete else None,
        ))
    complete = all(x.status == PriceStatus.EXACT for x in breakdowns) and bool(breakdowns)
    priced = dsum(x.priced_subtotal_toman for x in breakdowns)
    tax = None
    if ctx.include_tax and complete:
        tax = dsum(x.monthly_tax_toman for x in breakdowns if x.monthly_tax_toman is not None)
    assumptions: list[str] = []
    for bd in breakdowns:
        for a in bd.assumptions:
            if a not in assumptions:
                assumptions.append(a)
    used_providers = {bd.provider_id for bd in breakdowns}
    sources = [s for s in snapshot.source_freshness() if s["provider_id"] in used_providers]
    inventory_hash = _hash([r.model_dump(mode="json") for r in resources])
    quote = Quote(
        engine_version=ENGINE_VERSION, policy_version=snapshot.policy_version,
        catalog_version=snapshot.catalog_version, catalog_snapshot_at=snapshot.snapshot_at, complete=complete,
        total_toman=priced if complete else None, priced_subtotal_toman=priced, total_tax_toman=tax,
        breakdowns=breakdowns, provider_totals=provider_totals, assumptions=assumptions,
        unavailable=[u for bd in breakdowns for u in bd.unavailable], price_sources=sources,
        inventory_hash=inventory_hash,
    )
    quote.content_hash = _hash(quote.model_dump(mode="json", exclude={"content_hash"}))
    return quote
