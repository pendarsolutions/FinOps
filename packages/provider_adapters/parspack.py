"""ParsPack adapter - reads the pricing table embedded in the official cloud-server configurator.

The page's own calculator charges, per day: disk price + RAM price + CPU price, each looked up in this table.
Only Iranian datacenters and Linux prices are read. Monthly prices are 30 x the daily price, the engine's month.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from pricing_engine.models import CatalogItem

from .base import HttpAdapterMixin, ParseError, RawCatalog, base_item

MARKER = "const productDataAllLocations"
DAYS_PER_MONTH = Decimal(30)
FAMILY = "cloud_server"


def _table(content: str) -> dict[str, Any]:
    start = content.find(MARKER)
    if start < 0:
        raise ParseError("ParsPack pricing table not found on the page")
    try:
        locations = json.JSONDecoder().raw_decode(content[content.index("{", start):])[0]
        centers = [dc for city in locations["Iran"]["cities"] for dc in city["data_centers"]]
        tables = [dc["billings"]["pricingTable"]["linux"] for dc in centers]
    except (ValueError, KeyError, TypeError) as exc:
        raise ParseError(f"ParsPack pricing table not understood: {exc}") from exc
    if not tables:
        raise ParseError("no Iranian ParsPack datacenters found")
    if any(t != tables[0] for t in tables):
        raise ParseError("ParsPack datacenters now have different prices; this adapter assumes one price list")
    sizes = {k: v for k, v in tables[0].items() if k.isdigit()}
    if not sizes or len({json.dumps(v["cpu"], sort_keys=True) for v in sizes.values()}) != 1 \
            or len({json.dumps(v["hdd"], sort_keys=True) for v in sizes.values()}) != 1:
        raise ParseError("ParsPack CPU or disk prices now depend on RAM; this adapter assumes they don't")
    return sizes


class ParsPackAdapter(HttpAdapterMixin):
    provider_id = "parspack"
    source_url = "https://parspack.com/cloud-server"
    scope = {("compute_vm", FAMILY), ("compute_component", FAMILY), ("memory_component", FAMILY),
             ("storage_component", FAMILY)}
    key_skus = {"PP-CPU-1", "PP-RAM-2", "PP-DISK-25"}

    def _row(self, raw: RawCatalog, service_type: str, sku: str, name: str, daily: Any, **specs: Any) -> CatalogItem:
        daily_price = Decimal(str(daily))
        return base_item(self.provider_id, raw, service_type=service_type, pricing_model="component_rate",
                         product_family=FAMILY, sku=sku, name=name, billing_period="day", unit="config_day",
                         daily_price_toman=daily_price, price_toman=daily_price * DAYS_PER_MONTH, **specs)

    def normalize_catalog(self, raw: RawCatalog) -> list[CatalogItem]:
        sizes = _table(raw.content)
        first = next(iter(sizes.values()))
        items = [self._row(raw, "compute_component", f"PP-CPU-{n}", f"{n} CPU", price, cpu_cores=n)
                 for n, price in first["cpu"].items()]
        for mb, row in sizes.items():
            gb = Decimal(mb) / 1024
            items.append(self._row(raw, "memory_component", f"PP-RAM-{gb.normalize():f}", f"{gb.normalize():f} GB RAM",
                                   row["ram"], ram_gb=gb))
        items += [self._row(raw, "storage_component", f"PP-DISK-{gb}", f"{gb} GB disk", price, storage_gb=gb)
                  for gb, price in first["hdd"].items()]
        return items
