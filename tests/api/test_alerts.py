"""Alerts and reviewed manual price files."""

import json
from decimal import Decimal as D

import pytest


@pytest.fixture
def sent(api_env, monkeypatch):
    from finops_api import alerts

    out = []
    monkeypatch.setattr(alerts, "notify", lambda subject, body: out.append((subject, body)))
    return out


def _run(db, provider, status, **kw):
    from finops_api.orm import PriceSyncRun

    run = PriceSyncRun(provider_id=provider, status=status, triggered_by="test", **kw)
    db.add(run)
    db.commit()
    return run


def test_repeated_failure_alerts_once(sent):
    from finops_api.alerts import sync_alert
    from finops_api.db import SessionLocal

    with SessionLocal() as db:
        sync_alert(db, _run(db, "abrha", "failed", error="blocked"))
        sync_alert(db, _run(db, "abrha", "failed", error="blocked"))
        sync_alert(db, _run(db, "abrha", "ok"))
        sync_alert(db, _run(db, "abrha", "failed", error="blocked"))
    assert len(sent) == 2 and all("failed" in s for s, _ in sent)


def test_price_change_lists_only_moved_prices(sent):
    from finops_api.alerts import sync_alert
    from finops_api.db import SessionLocal

    changes = [{"kind": "changed", "sku": "A", "old_price_toman": "100", "new_price_toman": "120"},
               {"kind": "changed", "sku": "SPEC", "old_price_toman": "5", "new_price_toman": "5"},
               {"kind": "new", "sku": "B", "old_price_toman": None, "new_price_toman": "7"}]
    with SessionLocal() as db:
        sync_alert(db, _run(db, "parspack", "ok", summary={"changes": changes}))
    assert len(sent) == 1
    assert "A: 100 -> 120" in sent[0][1] and "SPEC" not in sent[0][1] and "B:" not in sent[0][1]


def test_delivery_failure_never_breaks_the_job(api_env, monkeypatch):
    from finops_api import alerts
    from finops_api.config import get_settings

    monkeypatch.setattr(get_settings(), "bale_bot_token", "secret-token")
    monkeypatch.setattr(get_settings(), "bale_chat_id", "1")

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(alerts.httpx, "post", boom)
    alerts.notify("subject", "body")


def _file(prices, provider="arvancloud"):
    return json.dumps({"provider_id": provider, "source_url": "https://www.arvancloud.ir/fa/pricing/all",
                       "price_date": "2026-11-01", "prices": prices})


def _current(db, sku):
    from sqlalchemy import select

    from finops_api.orm import CatalogItemVersion

    return db.scalar(select(CatalogItemVersion).where(CatalogItemVersion.sku == sku, CatalogItemVersion.valid_to.is_(None)))


def test_manual_prices_version_one_row_and_keep_the_rest(api_env):
    from finops_api.catalog_store import import_manual_prices
    from finops_api.db import SessionLocal

    with SessionLocal() as db:
        cpu = _current(db, "IR-CPU-STANDARD")
        old_price, ram_price = cpu.price_toman, _current(db, "IR-RAM-STANDARD").price_toman
        new_price = old_price + 1000
        run = import_manual_prices(db, "arvancloud", _file([{"sku": "IR-CPU-STANDARD", "price_toman": str(new_price)}]), "t")
        assert run.status in ("ok", "warning"), run.error
        assert _current(db, "IR-CPU-STANDARD").price_toman == new_price
        assert _current(db, "IR-CPU-STANDARD").source_price_date == "2026-11-01"
        assert _current(db, "IR-RAM-STANDARD").price_toman == ram_price
        assert isinstance(old_price, D)


@pytest.mark.parametrize("content", [
    _file([{"sku": "NO-SUCH-SKU", "price_toman": "1"}]),
    _file([{"sku": "IR-CPU-STANDARD"}]),
    _file([{"sku": "IR-CPU-STANDARD", "price_toman": "1"}], provider="liara"),
    "not json",
])
def test_bad_price_files_change_nothing(api_env, content):
    from finops_api.catalog_store import import_manual_prices
    from finops_api.db import SessionLocal

    with SessionLocal() as db:
        before = _current(db, "IR-CPU-STANDARD").price_toman
        assert import_manual_prices(db, "arvancloud", content, "t").status == "failed"
        assert _current(db, "IR-CPU-STANDARD").price_toman == before


def test_sharp_manual_move_is_held_for_review(api_env):
    from finops_api.catalog_store import import_manual_prices
    from finops_api.db import SessionLocal

    with SessionLocal() as db:
        before = _current(db, "IR-RAM-STANDARD").price_toman
        run = import_manual_prices(db, "arvancloud", _file([{"sku": "IR-RAM-STANDARD", "price_toman": str(before * 3)}]), "t")
        assert run.status == "quarantined"
        assert _current(db, "IR-RAM-STANDARD").price_toman == before


def test_restart_reseed_does_not_undo_newer_prices(api_env):
    from finops_api.catalog_store import import_manual_prices, seed_pricing
    from finops_api.config import get_settings
    from finops_api.db import SessionLocal

    with SessionLocal() as db:
        new_price = _current(db, "IR-CPU-BASIC").price_toman + 500
        run = import_manual_prices(db, "arvancloud", _file([{"sku": "IR-CPU-BASIC", "price_toman": str(new_price)}]), "t")
        assert run.status in ("ok", "warning"), run.error
        stats = seed_pricing(db, get_settings().seed_dir)
        assert stats["items_inserted"] == 0
        assert _current(db, "IR-CPU-BASIC").price_toman == new_price
