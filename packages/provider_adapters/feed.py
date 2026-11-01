"""Signed price catalog: one installation scrapes, signs and publishes; the others download and verify.

Signing is Ed25519 over the exact file bytes, so a mirror or a compromised host can't change a price. Applying a
feed still goes through the normal guardrails and versioning.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from pricing_engine.models import CatalogItem

from .base import AdapterHealth, ParseError, RawCatalog

SCHEMA = 1
EXCLUDED = {"price_rial", "version_id", "valid_from", "valid_to"}


class FeedError(ValueError):
    """The feed is unsigned, tampered with or not understood."""


def generate_signing_key() -> tuple[str, str]:
    """(private key as base64, public key as base64)."""
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(private).decode(), base64.b64encode(public).decode()


def build_feed(items: list[CatalogItem], generated_at: datetime) -> bytes:
    rows = [i.model_dump(mode="json", exclude=EXCLUDED) for i in sorted(items, key=lambda i: i.id)]
    return json.dumps({"schema": SCHEMA, "generated_at": generated_at.isoformat(), "items": rows},
                      ensure_ascii=False, sort_keys=True).encode()


def sign_feed(content: bytes, private_key_b64: str) -> str:
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64))
    return base64.b64encode(key.sign(content)).decode()


def read_feed(content: bytes, signature_b64: str, public_key_b64: str) -> tuple[datetime, dict[str, list[dict[str, Any]]]]:
    """Verify first and parse afterwards. Returns (generated_at, rows per provider)."""
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
        key.verify(base64.b64decode(signature_b64), content)
    except (InvalidSignature, ValueError) as exc:
        raise FeedError("catalog signature is not valid") from exc
    data = json.loads(content)
    if data.get("schema") != SCHEMA:
        raise FeedError(f"unsupported catalog schema {data.get('schema')!r}")
    by_provider: dict[str, list[dict[str, Any]]] = {}
    for row in data["items"]:
        by_provider.setdefault(row["provider_id"], []).append(row)
    return datetime.fromisoformat(data["generated_at"]), by_provider


class FeedAdapter:
    """Presents one provider's verified feed rows to the normal sync pipeline."""

    key_skus: set[str] = set()
    source_url = "catalog-feed"

    def __init__(self, provider_id: str, current: list[CatalogItem], rows: list[dict[str, Any]]):
        self.provider_id = provider_id
        self.rows = rows
        self.scope = {(i.service_type, i.product_family) for i in current} | {
            (r["service_type"], r.get("product_family")) for r in rows}

    async def fetch_catalog(self) -> RawCatalog:
        raise ParseError("feed rows are already downloaded")

    async def healthcheck(self) -> AdapterHealth:
        return AdapterHealth(self.provider_id, True, "catalog feed")

    def normalize_catalog(self, raw: RawCatalog) -> list[CatalogItem]:
        return [CatalogItem.model_validate({**r, "valid_from": raw.fetched_at}) for r in self.rows]
