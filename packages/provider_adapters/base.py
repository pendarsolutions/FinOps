"""Adapter contracts. Adapters fetch an official source and normalize it into CatalogItem rows.

They never invent prices: a field that the source does not state stays None, and a page the
parser cannot understand raises ParseError (surfaced as a failed sync, never as empty prices).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

import httpx

from pricing_engine.catalog import derive_attributes
from pricing_engine.models import CatalogItem

USER_AGENT = "PendarFinOpsBot/0.1 (+https://pendar.example/finops; price transparency)"

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")


class ParseError(Exception):
    """The source was fetched but could not be understood."""


class SourceBlockedError(ParseError):
    """The source returned a bot challenge / interstitial instead of the pricing page."""


@dataclass
class RawCatalog:
    provider_id: str
    source_url: str
    fetched_at: datetime
    content: str
    status_code: int = 200
    content_type: str = "text/html"

    @property
    def content_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass
class AdapterHealth:
    provider_id: str
    ok: bool
    detail: str
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@runtime_checkable
class ProviderAdapter(Protocol):
    provider_id: str
    source_url: str
    #: (service_type, product_family) pairs this adapter is authoritative for. Sync only closes
    #: catalog rows inside this scope, so a partial parser never deletes rows it does not cover.
    scope: set[tuple[str, str | None]]
    #: SKUs whose absence after a sync produces a warning.
    key_skus: set[str]

    async def fetch_catalog(self) -> RawCatalog: ...

    def normalize_catalog(self, raw: RawCatalog) -> list[CatalogItem]: ...

    async def healthcheck(self) -> AdapterHealth: ...


@runtime_checkable
class InventoryConnector(Protocol):
    """Reserved for read-only provider account connections (post-MVP). Credentials must be read-only."""

    provider_id: str

    async def list_resources(self, credentials: dict[str, str]) -> list[dict[str, Any]]: ...

    async def get_billing_export(self, credentials: dict[str, str], month: str) -> list[dict[str, Any]]: ...


# --------------------------------------------------------------------------- helpers


def to_ascii_digits(text: str) -> str:
    return text.translate(PERSIAN_DIGITS)


def parse_number(text: str | None) -> Decimal | None:
    """'۲,۶۵۰,۰۰۰ تومان' -> Decimal('2650000'). Returns None when no number is present."""
    if text is None:
        return None
    t = to_ascii_digits(text).replace("٬", ",").replace(",", "")
    m = re.search(r"\d+(?:\.\d+)?", t)
    return Decimal(m.group(0)) if m else None


def natural_key(item: CatalogItem) -> tuple:
    """Identity of a catalog row across versions (prices excluded)."""
    return (item.provider_id, item.service_type, item.product_family, item.sku, item.gpu_model, item.storage_type,
            item.traffic_direction, str(item.tier_min) if item.tier_min is not None else None)


def make_item_id(*parts: Any) -> str:
    return hashlib.sha256("|".join("" if p is None else str(p) for p in parts).encode()).hexdigest()[:16]


class HttpAdapterMixin:
    provider_id: str
    source_url: str
    timeout_s: float = 30.0

    async def fetch_catalog(self) -> RawCatalog:
        async with httpx.AsyncClient(follow_redirects=True, timeout=self.timeout_s,
                                     headers={"User-Agent": USER_AGENT, "Accept-Language": "fa,en"}) as client:
            resp = await client.get(self.source_url)
        return RawCatalog(provider_id=self.provider_id, source_url=self.source_url, fetched_at=datetime.now(UTC),
                          content=resp.text, status_code=resp.status_code,
                          content_type=resp.headers.get("content-type", "text/html"))

    async def healthcheck(self) -> AdapterHealth:
        try:
            raw = await self.fetch_catalog()
            items = self.normalize_catalog(raw)  # type: ignore[attr-defined]
            return AdapterHealth(self.provider_id, bool(items), f"{len(items)} items parsed")
        except Exception as exc:  # noqa: BLE001 - health reports any failure
            return AdapterHealth(self.provider_id, False, f"{type(exc).__name__}: {exc}")


def base_item(provider_id: str, raw: RawCatalog, **fields: Any) -> CatalogItem:
    fields.setdefault("region_country", "IR")
    fields.setdefault("region", "Iran")
    fields.setdefault("availability", "available")
    fields.setdefault("confidence", "high")
    fields.setdefault("source_url", raw.source_url)
    fields.setdefault("source_retrieved_at", raw.fetched_at.date().isoformat())
    fields.setdefault("valid_from", raw.fetched_at)
    # same normalization as the seed importer, so seed and live rows compare like-for-like
    fields["attributes"] = derive_attributes({**fields, "provider_id": provider_id})
    item = CatalogItem(id="pending", provider_id=provider_id, **fields)
    item.id = make_item_id(*natural_key(item))
    return item
