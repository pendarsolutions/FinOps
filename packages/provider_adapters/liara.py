"""Liara adapter - parses PaaS / DBaaS / IaaS plan cards and the IaaS network/IPv4 sentence."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from pricing_engine.models import CatalogItem

from .base import HttpAdapterMixin, ParseError, RawCatalog, base_item, parse_number, to_ascii_digits

PLANETS = {"زمین": "EARTH", "مریخ": "MARS", "مشتری": "JUPITER", "زحل": "SATURN", "اورانوس": "URANUS",
           "نپتون": "NEPTUNE", "پلوتون": "PLUTO", "اریس": "ERIS"}
PLANET_EN = {v: v.title() for v in PLANETS.values()}
SECTIONS = {  # heading text fragment -> (service_type, product_family, sku prefix)
    "(PaaS)": ("paas", "paas", "PAAS"),
    "(DBaaS)": ("dbaas", "dbaas", "DBAAS"),
    "سرور مجازی ابری": ("compute_vm", "iaas", "IAAS"),
}


class LiaraAdapter(HttpAdapterMixin):
    provider_id = "liara"
    source_url = "https://liara.ir/pricing/"
    scope = {("paas", "paas"), ("dbaas", "dbaas"), ("compute_vm", "iaas"), ("network_traffic", "iaas"),
             ("ipv4", "iaas")}
    key_skus = {"IAAS-SATURN", "PAAS-MARS", "DBAAS-MARS", "IAAS-IPV4", "IAAS-DOWNLOAD"}

    def normalize_catalog(self, raw: RawCatalog) -> list[CatalogItem]:
        soup = BeautifulSoup(raw.content, "lxml")
        items: list[CatalogItem] = []
        for swiper in soup.select(".swiper"):
            heading = swiper.find_previous(["h1", "h2", "h3", "h4"])
            htext = heading.get_text(" ", strip=True) if heading else ""
            section = next((v for k, v in SECTIONS.items() if k in htext), None)
            if section is None:
                continue  # email / AI / WordPress hosting are out of FinOps scope
            service_type, family, prefix = section
            for slide in swiper.select(".swiper-slide"):
                name_el = slide.select_one(".plan-name")
                if not name_el:
                    continue
                name_fa = name_el.get_text(strip=True)
                code = PLANETS.get(name_fa)
                if code is None:
                    raise ParseError(f"unknown Liara plan name '{name_fa}' in section '{htext}' - update PLANETS map")
                specs = {}
                for sp in slide.select(".spec"):
                    lab, val = sp.select_one(".label"), sp.select_one(".value")
                    if lab and val:
                        specs[lab.get_text(strip=True)] = val.get_text(" ", strip=True)
                monthly, hourly = parse_number(specs.get("قیمت ماهانه")), parse_number(specs.get("قیمت ساعتی"))
                if monthly is None or hourly is None:
                    raise ParseError(f"{prefix}-{code}: monthly/hourly price missing")
                items.append(base_item(
                    self.provider_id, raw, service_type=service_type, pricing_model="fixed_sku_hourly_monthly",
                    product_family=family, sku=f"{prefix}-{code}", name=f"{name_fa} / {PLANET_EN[code]}",
                    cpu_cores=parse_number(specs.get("vCPU(CORE)")), ram_gb=parse_number(specs.get("RAM(GB)")),
                    storage_gb=parse_number(specs.get("Disk(GB SSD)")), storage_type="ssd",
                    bandwidth="10Gbps shared" if service_type == "compute_vm" else None, billing_period="month",
                    price_toman=monthly, hourly_price_toman=hourly, unit="plan_month",
                ))
        if not items:
            raise ParseError("no PaaS/DBaaS/IaaS plan cards found")
        items.extend(self._network(raw, soup))
        return items

    def _network(self, raw: RawCatalog, soup: BeautifulSoup) -> list[CatalogItem]:
        text = to_ascii_digits(soup.get_text(" ", strip=True)).replace(",", "")
        dl = re.search(r"هر گیگابایت ترافیک دانلود،?\s*(\d+)\s*تومان", text)
        ul_free = re.search(r"ترافیک آپلود رایگان", text)
        ip = re.search(r"ماهانه\s*(\d+)\s*(هزار)?\s*تومان\s*\(ساعتی\s*(\d+)\s*تومان\)\s*هزینه‌?\s*ی?\s*IPv4", text)
        if not (dl and ul_free and ip):
            raise ParseError("IaaS network/IPv4 sentence not found or changed")
        ip_month = parse_number(ip.group(1)) * (1000 if ip.group(2) else 1)
        common = dict(service_type="network_traffic", pricing_model="component_rate", product_family="iaas", unit="gb")
        return [
            base_item(self.provider_id, raw, sku="IAAS-DOWNLOAD", name="IaaS download traffic",
                      traffic_direction="download", price_toman=parse_number(dl.group(1)), **common),
            base_item(self.provider_id, raw, sku="IAAS-UPLOAD", name="IaaS upload traffic", traffic_direction="upload",
                      price_toman=parse_number("0"), **common),
            base_item(self.provider_id, raw, service_type="ipv4", pricing_model="component_rate", product_family="iaas",
                      sku="IAAS-IPV4", name="IaaS IPv4", billing_period="month", price_toman=ip_month,
                      hourly_price_toman=parse_number(ip.group(3)), unit="ip_month"),
        ]
