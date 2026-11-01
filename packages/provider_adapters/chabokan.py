"""Chabokan adapter - reads the plan objects embedded in the official cloud-server page.

The page also lists foreign plans from other hubs; only plans located in Iran and sold by Chabokan are
emitted. Monthly prices only: the page's multi-month prices are kept as attributes and never applied.
"""

from __future__ import annotations

import json
import re

from pricing_engine.models import CatalogItem

from .base import HttpAdapterMixin, ParseError, RawCatalog, base_item

PLAN_RE = re.compile(r'\{\\"id\\":\\"\d+\\",\\"name\\".*?\\"source_hub\\":\\"[a-z]+\\"\}')
FAMILIES = {"زیرساخت ایران": "Iran Infrastructure", "چابکان": "Chabokan"}
#: stable identities for plans already in the catalog under an English SKU
KNOWN_SKUS = {"اقتصادی": "economic-tehran"}


def _plans(content: str) -> list[dict]:
    plans = []
    for m in PLAN_RE.finditer(content):
        try:
            plans.append(json.loads(json.loads(f'"{m.group(0)}"')))
        except json.JSONDecodeError:
            continue  # other objects on the page share the opening; plans have a fixed shape
    return plans


class ChabokanAdapter(HttpAdapterMixin):
    provider_id = "chabokan"
    source_url = "https://chabokan.net/products/cloudserver/"
    scope = {("compute_vm", "Iran Infrastructure"), ("compute_vm", "Chabokan")}
    key_skus = {"NCO-small40-MHD", "NGP-small40-THR"}

    def normalize_catalog(self, raw: RawCatalog) -> list[CatalogItem]:
        items: list[CatalogItem] = []
        seen: set[str] = set()
        for plan in _plans(raw.content):
            family = FAMILIES.get(plan.get("cloud"))
            if plan.get("country") != "IR" or plan.get("source_hub") != "chabokan" or family is None:
                continue
            limits, prices = plan.get("limits") or {}, plan.get("prices") or {}
            monthly = prices.get("monthly")
            if monthly is None:
                continue
            name, city = plan["name"], plan.get("city")
            sku = KNOWN_SKUS.get(name, name if family != "Chabokan" else f"{name}-{city}")
            if sku in seen:
                continue
            seen.add(sku)
            items.append(base_item(
                self.provider_id, raw, service_type="compute_vm", pricing_model="fixed_sku_flexible_period",
                product_family=family, sku=sku, name=name, datacenter=city, billing_period="30_days",
                cpu_cores=str(limits["cpu"]), ram_gb=str(limits["ram_mb"] / 1024), storage_gb=str(limits["disk_gb"]),
                included_traffic_gb=str(limits["bandwidth_gb"]), price_toman=str(monthly), unit="plan_month",
                attributes={"multi_month_prices_toman": {k: str(v) for k, v in prices.items() if k != "monthly"}},
            ))
        if not items:
            raise ParseError("no Iranian Chabokan plans found in the embedded page data")
        return items
