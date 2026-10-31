"""Catalog snapshots: an immutable, versioned view of prices + rules the engine computes against."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import BillingRule, CatalogItem, Provider

SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seeds"


def load_json(path: Path) -> Any:
    """Load JSON with every non-integer number parsed as Decimal (never float)."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh, parse_float=Decimal)


# --------------------------------------------------------------------------- dates


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> date:
    """Convert a Solar Hijri (Jalali) date to Gregorian. Standard arithmetic algorithm."""
    jy += 1595
    days = -355668 + (365 * jy) + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + jd
    days += (jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    month_days = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and gd > month_days[gm]:
        gd -= month_days[gm]
        gm += 1
    return date(gy, gm, gd)


def parse_price_date(value: str | None) -> date | None:
    """Parse a provider price date. Years < 1700 are treated as Jalali (e.g. Arvan '1405-03-30')."""
    if not value:
        return None
    y, m, d = (int(p) for p in str(value)[:10].split("-"))
    if y < 1700:
        return jalali_to_gregorian(y, m, d)
    return date(y, m, d)


# --------------------------------------------------------------------------- normalization


def derive_traffic_policy(item: dict[str, Any]) -> str:
    """Classify a fixed-SKU row's traffic terms from structured fields + official notes text.

    Deterministic and conservative: anything unrecognised is 'unknown'.
    """
    notes = (item.get("notes") or "").lower()
    if "download unlimited at" in notes:
        return "unlimited_rate_limited"
    if "fair-use" in notes or "fair use" in notes:
        return "fair_use"
    if "traffic shown as unlimited" in notes:
        return "unlimited"
    if item.get("included_traffic_gb") not in (None, ""):
        return "included_quota"
    return "unknown"


def derive_attributes(item: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = dict(item.get("attributes") or {})
    if item.get("service_type") == "compute_vm":
        attrs.setdefault("traffic_policy", derive_traffic_policy(item))
        notes = (item.get("notes") or "").lower()
        if "fair-use 50gb/day" in notes:
            attrs.setdefault("fair_use_download_gb_per_day", "50")
        if "8mbps" in notes:
            attrs.setdefault("rate_limit_mbps", "8")
    return attrs


def normalize_seed_item(raw: dict[str, Any], valid_from: datetime) -> CatalogItem:
    data = {k: v for k, v in raw.items() if k != "price_rial"}  # rial is always derived
    data["attributes"] = derive_attributes(raw)
    data.setdefault("valid_from", valid_from)
    return CatalogItem.model_validate(data)


# --------------------------------------------------------------------------- snapshot


@dataclass
class CatalogSnapshot:
    providers: dict[str, Provider]
    items: list[CatalogItem]
    billing_rules: dict[str, BillingRule]
    policy: dict[str, Any]
    equivalence_rules: dict[str, Any]
    recommendation_rules: dict[str, Any]
    snapshot_at: datetime
    _by_provider: dict[str, list[CatalogItem]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.items = [i for i in self.items if self._valid_at(i, self.snapshot_at)]
        for it in self.items:
            self._by_provider.setdefault(it.provider_id, []).append(it)

    @staticmethod
    def _valid_at(item: CatalogItem, at: datetime) -> bool:
        if item.valid_from and item.valid_from > at:
            return False
        if item.valid_to and item.valid_to <= at:
            return False
        return True

    # -- lookups -----------------------------------------------------------
    def provider_items(self, provider_id: str) -> list[CatalogItem]:
        return self._by_provider.get(provider_id, [])

    def find(self, provider_id: str, **criteria: Any) -> list[CatalogItem]:
        out = []
        for it in self.provider_items(provider_id):
            if all(getattr(it, k) == v for k, v in criteria.items()):
                out.append(it)
        return out

    def find_one(self, provider_id: str, **criteria: Any) -> CatalogItem | None:
        rows = self.find(provider_id, **criteria)
        return rows[0] if len(rows) == 1 else None

    def item_by_id(self, item_id: str) -> CatalogItem | None:
        for it in self.items:
            if it.id == item_id:
                return it
        return None

    def provider_policy(self, provider_id: str | None) -> dict[str, Any] | None:
        if provider_id is None:
            return None
        return self.policy.get("providers", {}).get(provider_id)

    @property
    def hours_per_month(self) -> Decimal:
        return Decimal(str(self.policy["hours_per_month"]["value"]))

    @property
    def policy_version(self) -> str:
        return str(self.policy.get("policy_version", "unknown"))

    @property
    def catalog_version(self) -> str:
        """Content hash of every price-bearing field of every item in the snapshot."""
        h = hashlib.sha256()
        for it in sorted(self.items, key=lambda i: i.id):
            h.update(
                json.dumps(
                    it.model_dump(mode="json", exclude={"attributes", "notes"}), sort_keys=True, default=str
                ).encode()
            )
        for rid in sorted(self.billing_rules):
            h.update(self.billing_rules[rid].model_dump_json().encode())
        h.update(self.policy_version.encode())
        return "cat-" + h.hexdigest()[:16]

    def source_freshness(self, today: date | None = None) -> list[dict[str, Any]]:
        today = today or self.snapshot_at.date()
        warn = int(self.policy.get("freshness", {}).get("warn_after_days", 14))
        stale = int(self.policy.get("freshness", {}).get("stale_after_days", 45))
        seen: dict[tuple[str, str], dict[str, Any]] = {}
        for it in self.items:
            key = (it.provider_id, it.source_url or "")
            if key in seen:
                continue
            retrieved = parse_price_date(it.source_retrieved_at)
            price_date = parse_price_date(it.source_price_date)
            age = (today - retrieved).days if retrieved else None
            status = "unknown" if age is None else "fresh" if age <= warn else "aging" if age <= stale else "stale"
            seen[key] = {
                "provider_id": it.provider_id,
                "source_url": it.source_url,
                "retrieved_at": it.source_retrieved_at,
                "provider_price_date": it.source_price_date,
                "provider_price_date_gregorian": price_date.isoformat() if price_date else None,
                "age_days": age,
                "freshness": status,
            }
        return list(seen.values())


def load_seed_snapshot(seed_dir: Path = SEED_DIR, snapshot_at: datetime | None = None) -> CatalogSnapshot:
    """Build a snapshot straight from the seed files (used by tests, the CLI and the seed importer)."""
    bundle = load_json(seed_dir / "iran_finops_dataset.json")
    meta_date = datetime.fromisoformat(bundle["metadata"]["snapshot_date"]).replace(tzinfo=UTC)
    snapshot_at = snapshot_at or meta_date
    return CatalogSnapshot(
        providers={p["provider_id"]: Provider.model_validate(p) for p in bundle["providers"]},
        items=[normalize_seed_item(i, meta_date) for i in bundle["catalog_items"]],
        billing_rules={r["rule_id"]: BillingRule.model_validate(r) for r in bundle["billing_rules"]},
        policy=load_json(seed_dir / "engine_policy.json"),
        equivalence_rules=load_json(seed_dir / "equivalence_rules.json"),
        recommendation_rules=load_json(seed_dir / "recommendation_rules.json"),
        snapshot_at=snapshot_at,
    )
