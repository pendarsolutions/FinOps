"""Sync planning with guardrails. Pure: takes previous + new items, returns a plan the DB layer applies.

Guardrails (DEVELOPMENT_PROMPT section 10):
* zero items                                   -> failed
* median |price change| > 25% across matches   -> quarantined (nothing applied; needs review)
* key SKUs missing                             -> warning
* source hash changed but parser output same   -> warning
* source price date older than stale threshold -> warning
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pricing_engine.models import CatalogItem

from .base import ParseError, RawCatalog, natural_key

SIGNATURE_FIELDS = ("price_toman", "hourly_price_toman", "daily_price_toman", "cpu_cores", "ram_gb", "storage_gb",
                    "included_traffic_gb", "availability", "cpu_shared", "datacenter")
SIGNATURE_ATTRS = ("traffic_policy", "download_toman_per_gb", "rate_limit_mbps")
MAX_MEDIAN_MOVE = Decimal("0.25")


def signature(item: CatalogItem) -> tuple:
    return tuple(getattr(item, f) for f in SIGNATURE_FIELDS) + tuple(
        str(item.attributes.get(a)) if item.attributes.get(a) is not None else None for a in SIGNATURE_ATTRS)


@dataclass
class ItemChange:
    key: tuple
    old: CatalogItem | None
    new: CatalogItem | None
    kind: Literal["new", "changed", "removed"]
    changed_fields: list[str] = field(default_factory=list)


@dataclass
class SyncPlan:
    provider_id: str
    status: Literal["ok", "warning", "quarantined", "failed"]
    items_seen: int
    changes: list[ItemChange]
    warnings: list[str]
    error: str | None = None
    median_price_move: Decimal | None = None
    content_hash: str | None = None
    confirmed_ids: list[str] = field(default_factory=list)
    checked_at: str | None = None

    @property
    def items_changed(self) -> int:
        return len(self.changes)

    @property
    def applicable(self) -> bool:
        return self.status in ("ok", "warning")

    def summary(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id, "status": self.status, "items_seen": self.items_seen,
            "items_changed": self.items_changed, "warnings": self.warnings, "error": self.error,
            "median_price_move": str(self.median_price_move) if self.median_price_move is not None else None,
            "checked_at": self.checked_at, "confirmed_item_ids": self.confirmed_ids,
            "changes": [{"kind": c.kind, "sku": (c.new or c.old).sku, "fields": c.changed_fields,
                         "old_price_toman": str(c.old.price_toman) if c.old and c.old.price_toman is not None else None,
                         "new_price_toman": str(c.new.price_toman) if c.new and c.new.price_toman is not None else None}
                        for c in self.changes],
        }


def plan_sync(adapter: Any, raw: RawCatalog | None, previous: list[CatalogItem], *,
              previous_content_hash: str | None = None, today: date | None = None,
              stale_after_days: int = 45, parse_error: Exception | None = None) -> SyncPlan:
    pid = adapter.provider_id
    if parse_error is not None or raw is None:
        return SyncPlan(pid, "failed", 0, [], [], error=f"{type(parse_error).__name__}: {parse_error}")
    try:
        new_items = adapter.normalize_catalog(raw)
    except ParseError as exc:
        return SyncPlan(pid, "failed", 0, [], [], error=f"{type(exc).__name__}: {exc}", content_hash=raw.content_hash)
    if not new_items:
        return SyncPlan(pid, "failed", 0, [], [], error="parser returned zero items", content_hash=raw.content_hash)

    in_scope = [p for p in previous if (p.service_type, p.product_family) in adapter.scope]
    prev_by_key = {natural_key(p): p for p in in_scope}
    new_by_key = {natural_key(n): n for n in new_items}
    changes: list[ItemChange] = []
    moves: list[Decimal] = []
    confirmed: list[str] = []
    for key, new in new_by_key.items():
        old = prev_by_key.get(key)
        if old is None:
            changes.append(ItemChange(key, None, new, "new"))
            continue
        new.id = old.id  # stable item identity across versions
        if old.price_toman and new.price_toman is not None:
            moves.append(abs(new.price_toman - old.price_toman) / old.price_toman)
        if signature(old) != signature(new):
            diff = [f for f, a, b in zip(SIGNATURE_FIELDS + SIGNATURE_ATTRS, signature(old), signature(new), strict=True)
                    if a != b]
            changes.append(ItemChange(key, old, new, "changed", diff))
        elif old.id:
            confirmed.append(old.id)
    for key, old in prev_by_key.items():
        if key not in new_by_key and getattr(adapter, "removes_missing", True):
            changes.append(ItemChange(key, old, None, "removed"))

    warnings: list[str] = []
    median = Decimal(str(statistics.median(moves))) if moves else None
    status: Literal["ok", "warning", "quarantined", "failed"] = "ok"
    if median is not None and median > MAX_MEDIAN_MOVE:
        status = "quarantined"
        warnings.append(f"median price movement {median:.2%} exceeds {MAX_MEDIAN_MOVE:.0%}; changes held for review")
    missing = sorted(adapter.key_skus - {n.sku for n in new_items})
    if missing:
        warnings.append(f"key SKUs missing from source: {', '.join(missing)}")
    if previous_content_hash and previous_content_hash != raw.content_hash and not changes:
        warnings.append("source content hash changed but parser output is unchanged - check parser coverage")
    today = today or raw.fetched_at.date()
    for n in new_items:
        if n.source_price_date:
            from pricing_engine.catalog import parse_price_date

            d = parse_price_date(n.source_price_date)
            if d and (today - d).days > stale_after_days:
                warnings.append(f"provider price date {n.source_price_date} older than {stale_after_days} days")
                break
    if status == "ok" and warnings:
        status = "warning"
    return SyncPlan(pid, status, len(new_items), changes, warnings, median_price_move=median,
                    content_hash=raw.content_hash, confirmed_ids=confirmed, checked_at=raw.fetched_at.date().isoformat())


def fetched_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
