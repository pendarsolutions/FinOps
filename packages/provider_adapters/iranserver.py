"""IranServer Iran VPS adapter - parses the General Purpose (NGP) table on the official page.

Only rows exposed in the server-rendered HTML are emitted; other families are dynamic and are
NOT fabricated (build-pack rule).
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from pricing_engine.models import CatalogItem

from .base import HttpAdapterMixin, ParseError, RawCatalog, base_item, parse_number

SKU_RE = re.compile(r"^\s*(NGP-[A-Za-z0-9]+)\s*$")


class IranServerAdapter(HttpAdapterMixin):
    provider_id = "iranserver"
    source_url = "https://www.iranserver.com/vps/iran/"
    scope = {("compute_vm", "general_purpose")}
    key_skus = {"NGP-small40", "NGP-medium40", "NGP-large80"}

    def normalize_catalog(self, raw: RawCatalog) -> list[CatalogItem]:
        soup = BeautifulSoup(raw.content, "lxml")
        seen: set[str] = set()
        items: list[CatalogItem] = []
        for row in soup.select("tr"):
            tds = row.find_all("td")
            if len(tds) < 6:
                continue
            first = tds[0].find("span")
            m = SKU_RE.match(first.get_text() if first else "")
            if not m or m.group(1) in seen:
                continue
            sku = m.group(1)
            seen.add(sku)
            tip = tds[0].select_one("[title]")
            tooltip = BeautifulSoup(tip["title"], "lxml").get_text(" ", strip=True) if tip else ""
            price = parse_number(tds[5].get_text())
            if price is None:
                raise ParseError(f"{sku}: price cell empty")
            items.append(base_item(
                self.provider_id, raw, service_type="compute_vm", pricing_model="fixed_sku",
                product_family="general_purpose", sku=sku, name=sku, cpu_cores=parse_number(tds[1].get_text()),
                cpu_shared=True if "اشتراکی" in tooltip else None, ram_gb=parse_number(tds[2].get_text()),
                storage_gb=parse_number(tds[3].get_text()), included_traffic_gb=parse_number(tds[4].get_text()),
                billing_period="month", price_toman=price, unit="plan_month",
                notes="General-purpose family; official tooltip: " + tooltip if tooltip else "General-purpose family.",
                attributes={"traffic_policy": "included_quota", "tooltip_fa": tooltip},
            ))
        if not items:
            raise ParseError("no NGP-* rows found in any table")
        return items
