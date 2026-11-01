"""Signed price catalog: a publisher's signature is required, and old feeds can't roll prices back."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from provider_adapters import FeedError, build_feed, generate_signing_key, read_feed, sign_feed


@pytest.fixture
def keys():
    return generate_signing_key()


def _items(db):
    from finops_api.catalog_store import current_versions, row_to_item

    return [row_to_item(r) for r in current_versions(db)]


def _current(db, sku):
    from sqlalchemy import select

    from finops_api.orm import CatalogItemVersion

    return db.scalar(select(CatalogItemVersion).where(CatalogItemVersion.sku == sku, CatalogItemVersion.valid_to.is_(None)))


def _feed_with_price(db, sku, price, at):
    items = _items(db)
    for i in items:
        if i.sku == sku:
            i.price_toman = D(price)
    return build_feed(items, at)


def test_tampered_feed_is_rejected(keys):
    private, public = keys
    content = build_feed([], datetime(2026, 11, 1, tzinfo=UTC))
    sig = sign_feed(content, private)
    assert read_feed(content, sig, public)[1] == {}
    with pytest.raises(FeedError):
        read_feed(content + b" ", sig, public)


def test_wrong_key_is_rejected(keys):
    private, _ = keys
    content = build_feed([], datetime(2026, 11, 1, tzinfo=UTC))
    with pytest.raises(FeedError):
        read_feed(content, sign_feed(content, private), generate_signing_key()[1])


def test_feed_applies_and_old_feed_cannot_roll_back(api_env, keys):
    from finops_api.catalog_feed import apply_feed
    from finops_api.db import SessionLocal

    private, public = keys
    base = datetime.now(UTC)
    with SessionLocal() as db:
        old_price = _current(db, "IR-VPS-6GB").price_toman
        new_price = old_price + 1000
        newer = _feed_with_price(db, "IR-VPS-6GB", new_price, base)
        older = _feed_with_price(db, "IR-VPS-6GB", old_price, base - timedelta(days=5))
        result = apply_feed(db, newer, sign_feed(newer, private), public)
        assert result["mobinhost"] in ("ok", "warning")
        assert _current(db, "IR-VPS-6GB").price_toman == new_price
        result = apply_feed(db, older, sign_feed(older, private), public)
        assert result["mobinhost"] == "skipped_not_newer"
        assert _current(db, "IR-VPS-6GB").price_toman == new_price


def test_publish_then_apply_roundtrip(api_env, keys, tmp_path):
    from finops_api.catalog_feed import apply_feed, publish
    from finops_api.db import SessionLocal

    private, public = keys
    with SessionLocal() as db:
        path = publish(db, tmp_path, private, datetime.now(UTC) + timedelta(hours=1))
        signature = (tmp_path / "catalog.json.sig").read_text()
        assert json.loads(path.read_bytes())["items"]
        result = apply_feed(db, path.read_bytes(), signature, public)
        assert set(result.values()) <= {"ok", "warning", "skipped_not_newer"}


def test_url_without_public_key_is_refused(api_env, monkeypatch):
    from finops_api.catalog_feed import pull
    from finops_api.config import get_settings
    from finops_api.db import SessionLocal

    monkeypatch.setattr(get_settings(), "catalog_url", "https://example.ir/catalog")
    monkeypatch.setattr(get_settings(), "catalog_public_key", None)
    with SessionLocal() as db, pytest.raises(FeedError, match="unverified"):
        pull(db)
