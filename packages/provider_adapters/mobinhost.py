"""MobinHost adapter - reads the Iran VPS and Iran VDS plan cards from two official pages.

Cards located outside Iran on the same pages are skipped. The card's number is shown in thousands of
Toman under both the "هزار" and "میلیون" labels (695 -> 695,000; 3,040 -> 3,040,000).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup

from pricing_engine.models import CatalogItem

from .base import USER_AGENT, HttpAdapterMixin, ParseError, RawCatalog, base_item, parse_number, to_ascii_digits

PAGES = {
    "iran_economic_vps": ("https://www.mobinhost.com/economic-vps/", "IR-VPS"),
    "iran_vds": ("https://www.mobinhost.com/iran-vds/", "IR-VDS"),
}
PAGE_MARKER = "<!--finops-page:{}-->"
IRAN_ALT = "سرور ایران"
GB_RE = re.compile(r"پلن\s*(\d+)\s*گیگابایت\s*$")


def _spec(card, icon: str) -> str | None:
    for prop in card.select(".property"):
        img = prop.find("img")
        if img and f"/{icon}.svg" in (img.get("src") or ""):
            return prop.get_text(" ", strip=True)
    return None


class MobinHostAdapter(HttpAdapterMixin):
    provider_id = "mobinhost"
    source_url = PAGES["iran_economic_vps"][0]
    scope = {("compute_vm", "iran_economic_vps"), ("compute_vm", "iran_vds")}
    key_skus = {"IR-VPS-2GB", "IR-VDS-16GB"}

    async def fetch_catalog(self) -> RawCatalog:
        parts = []
        async with httpx.AsyncClient(follow_redirects=True, timeout=self.timeout_s,
                                     headers={"User-Agent": USER_AGENT, "Accept-Language": "fa,en"}) as client:
            for family, (url, _) in PAGES.items():
                resp = await client.get(url)
                resp.raise_for_status()
                parts.append(PAGE_MARKER.format(family) + resp.text)
        return RawCatalog(provider_id=self.provider_id, source_url=self.source_url, fetched_at=datetime.now(UTC),
                          content="".join(parts))

    def normalize_catalog(self, raw: RawCatalog) -> list[CatalogItem]:
        items: list[CatalogItem] = []
        for family, (url, prefix) in PAGES.items():
            start = raw.content.find(PAGE_MARKER.format(family))
            if start < 0:
                raise ParseError(f"page for {family} missing from fetched content")
            end = raw.content.find("<!--finops-page:", start + 1)
            soup = BeautifulSoup(raw.content[start:end if end > 0 else None], "lxml")
            items += self._cards(soup, raw, family, url, prefix)
        if not items:
            raise ParseError("no Iranian plan cards found")
        return items

    def _cards(self, soup, raw: RawCatalog, family: str, url: str, prefix: str) -> list[CatalogItem]:
        out: dict[str, CatalogItem] = {}
        for card in soup.select(".mh-vps"):
            thumb = card.select_one(".thumbnail img")
            title = card.select_one(".title")
            if thumb is None or title is None or thumb.get("alt") != IRAN_ALT:
                continue
            m = GB_RE.search(to_ascii_digits(title.get_text(strip=True)))
            if not m:
                continue
            sku = f"{prefix}-{m.group(1)}GB"
            price = parse_number((card.select_one(".regular-price .price") or title).get_text())
            unit = card.select_one(".regular-price .unit")
            if price is None or unit is None or not ("هزار" in unit.get_text() or "میلیون" in unit.get_text()):
                raise ParseError(f"{sku}: price or its unit not recognised")
            availability = "sold_out" if "ناموجود" in card.get_text() else "available"
            out.setdefault(sku, base_item(
                self.provider_id, raw, service_type="compute_vm", pricing_model="fixed_sku", product_family=family,
                sku=sku, name=title.get_text(strip=True), billing_period="month", source_url=url,
                price_toman=price * 1000, unit="plan_month", availability=availability,
                cpu_cores=parse_number(_spec(card, "cpu")), ram_gb=parse_number(_spec(card, "ram")),
                storage_gb=parse_number(_spec(card, "storage")), included_traffic_gb=parse_number(_spec(card, "traffic")),
                bandwidth=_spec(card, "bw"),
            ))
        return list(out.values())
