"""Server.ir Iran VPS adapter - parses the official https://server.ir/vps/iran/ product grid."""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from pricing_engine.models import CatalogItem

from .base import HttpAdapterMixin, ParseError, RawCatalog, base_item, parse_number, to_ascii_digits

DATACENTERS = {
    "آسیاتک": "Asiatech",
    "افرانت - افرا": "Afranet-Afra",
    "افرانت": "Afranet",
    "افرانت, پارس آنلاین": "Afranet / Pars Online",
    "پردیس": "Pardis",
}
SERVER_CLASS = {"استاندارد": "standard", "پردازش بهینه": "optimized_core"}


class ServerIrAdapter(HttpAdapterMixin):
    provider_id = "serverir"
    source_url = "https://server.ir/vps/iran/"
    scope = {("compute_vm", "iran_vps")}
    key_skus = {"IRAT3024", "IRAF3024", "IRFH5024", "IRAF2011"}

    def normalize_catalog(self, raw: RawCatalog) -> list[CatalogItem]:
        soup = BeautifulSoup(raw.content, "lxml")
        cards = soup.select("div.isotope-item")
        if not cards:
            raise ParseError("no div.isotope-item product cards found")
        items: list[CatalogItem] = []
        for card in cards:
            cells = card.select(":scope > span.item-data")
            if len(cells) < 7 or not card.select_one("span.item-data.price[data-price]"):
                continue  # header row
            sku = cells[0].get_text(" ", strip=True)
            cpu_text = cells[1].get_text(" ", strip=True)
            extra = {}
            for attr in card.select(".extra-attr"):
                strong = attr.find("strong")
                if strong:
                    key = strong.get_text(strip=True).rstrip(":")
                    extra[key] = attr.get_text(" ", strip=True).split(":", 1)[-1].strip()
            server_type = extra.get("نوع سرور", "")
            resource_class = SERVER_CLASS.get(server_type)
            if resource_class is None:
                resource_class = "standard" if "vCore" in cpu_text else "optimized_core" if "Core" in cpu_text else None
            price_json = json.loads(card.select_one("span.item-data.price")["data-price"])
            month = parse_number(re.sub(r"<[^>]+>", "", price_json.get("month", "")))
            if month is None:
                raise ParseError(f"{sku}: monthly price missing")
            dc_fa = cells[5].get_text(" ", strip=True)
            traffic_fa = cells[4].get_text(" ", strip=True)
            desc = extra.get("توضیحات", "")
            attrs, notes, included = self._traffic(traffic_fa, desc)
            attrs.update({"traffic_text_fa": traffic_fa, "description_fa": desc, "server_type_fa": server_type,
                          "datacenter_fa": dc_fa, "term_prices_raw": price_json})
            items.append(base_item(
                self.provider_id, raw, service_type="compute_vm", pricing_model="fixed_sku", product_family="iran_vps",
                sku=sku, name=sku, datacenter=DATACENTERS.get(dc_fa, dc_fa), resource_class=resource_class,
                cpu_cores=parse_number(cpu_text), cpu_unit="vCore" if "vCore" in cpu_text else "Core",
                cpu_shared=resource_class == "standard" if resource_class else None,
                ram_gb=parse_number(cells[2].get_text()), storage_gb=parse_number(cells[3].get_text()),
                included_traffic_gb=included, billing_period="month", price_toman=month, unit="plan_month",
                tax_included=False, notes=notes + "; official invoices add 10% VAT.", attributes=attrs,
            ))
        if not items:
            raise ParseError("product cards found but none had a price")
        return items

    @staticmethod
    def _traffic(traffic_fa: str, desc_fa: str) -> tuple[dict, str, object]:
        t = to_ascii_digits(traffic_fa + " " + desc_fa)
        m_rate = re.search(r"هر گیگابایت دانلود\s*(\d+)\s*تومان", t)
        if m_rate:
            return ({"traffic_policy": "metered_download", "download_toman_per_gb": m_rate.group(1)},
                    f"upload unlimited; download metered at {m_rate.group(1)} Toman/GB", None)
        m_bw = re.search(r"پهنای باند\s*(\d+)\s*Mbps", t)
        if m_bw:
            return ({"traffic_policy": "unlimited_rate_limited", "rate_limit_mbps": m_bw.group(1)},
                    f"upload unlimited; download unlimited at {m_bw.group(1)}Mbps", None)
        m_q = re.search(r"دانلود(?: ماهانه)?\s*(\d+)\s*GB", t)
        if m_q:
            return ({"traffic_policy": "included_quota"}, f"upload unlimited; download {m_q.group(1)}GB/month",
                    parse_number(m_q.group(1)))
        if traffic_fa.strip() == "نامحدود":
            return {"traffic_policy": "unlimited"}, "traffic shown as unlimited on catalog", None
        return {"traffic_policy": "unknown"}, "traffic terms not recognised by parser", None
