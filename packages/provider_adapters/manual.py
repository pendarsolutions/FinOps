"""Reviewed manual price updates, for providers whose pages can't be read automatically.

The file names rows that already exist in the catalog and gives their new prices. It goes through the same
guardrails and versioning as a scrape. An unknown SKU fails the whole file; rows it doesn't mention are kept.
"""

from __future__ import annotations

import json
from typing import Any

from pricing_engine.models import CatalogItem

from .base import AdapterHealth, ParseError, RawCatalog, natural_key
from .sync import fetched_now

PRICE_FIELDS = {"price_toman", "hourly_price_toman", "daily_price_toman"}


class ManualPriceAdapter:
    removes_missing = False
    key_skus: set[str] = set()

    def __init__(self, provider_id: str, current: list[CatalogItem]):
        self.provider_id = provider_id
        self.current = current
        self.source_url = ""
        self.scope = {(i.service_type, i.product_family) for i in current}

    def load(self, content: str) -> RawCatalog:
        try:
            data = json.loads(content)
            self.source_url = data["source_url"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ParseError(f"price file is not valid: {exc}") from exc
        return RawCatalog(self.provider_id, self.source_url, fetched_now(), content, content_type="application/json")

    async def fetch_catalog(self) -> RawCatalog:
        raise ParseError("manual prices come from a file")

    async def healthcheck(self) -> AdapterHealth:
        return AdapterHealth(self.provider_id, True, "manual")

    def normalize_catalog(self, raw: RawCatalog) -> list[CatalogItem]:
        data: dict[str, Any] = json.loads(raw.content)
        if data.get("provider_id") != self.provider_id:
            raise ParseError(f"file is for provider {data.get('provider_id')!r}, not {self.provider_id!r}")
        if not data.get("price_date"):
            raise ParseError("price_date is required")
        by_sku: dict[tuple, CatalogItem] = {}
        for item in self.current:
            by_sku[(item.sku, str(item.tier_min) if item.tier_min is not None else None)] = item
        out = []
        for row in data.get("prices") or []:
            tier = str(row["tier_min"]) if row.get("tier_min") is not None else None
            old = by_sku.get((row.get("sku"), tier))
            if old is None:
                raise ParseError(f"unknown SKU {row.get('sku')!r} for {self.provider_id}")
            updates = {k: v for k, v in row.items() if k in PRICE_FIELDS}
            if not updates:
                raise ParseError(f"{row['sku']}: no price given")
            values = {**old.model_dump(exclude={"price_rial", "version_id", "valid_to"}), **updates,
                      "source_url": raw.source_url, "source_retrieved_at": raw.fetched_at.date().isoformat(),
                      "source_price_date": data["price_date"], "valid_from": raw.fetched_at}
            item = CatalogItem.model_validate(values)
            assert natural_key(item) == natural_key(old)
            out.append(item)
        return out
