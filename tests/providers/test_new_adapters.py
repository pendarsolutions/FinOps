"""Chabokan and MobinHost, from trimmed fixtures cut from their official pages on 2026-10-31."""

import gzip
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import pytest

from provider_adapters import ADAPTERS, ChabokanAdapter, MobinHostAdapter, ParseError, RawCatalog, plan_sync

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "providers"
NOW = datetime(2026, 10, 31, tzinfo=UTC)


def raw(adapter, name):
    content = gzip.decompress((FIX / f"{name}-2026-10-31.html.gz").read_bytes()).decode("utf-8")
    return RawCatalog(adapter.provider_id, adapter.source_url, NOW, content)


def test_chabokan_reads_iranian_plans_only():
    a = ChabokanAdapter()
    by = {i.sku: i for i in a.normalize_catalog(raw(a, "chabokan"))}
    assert "vc2-1c-2gb" not in by  # foreign plan on the same page
    assert by["NCO-small40-MHD"].price_toman == D(1758475)
    assert by["NCO-small40-MHD"].ram_gb == D(2)
    assert by["NCO-small40-MHD"].included_traffic_gb == D(1000)
    assert by["NCO-small40-MHD"].datacenter == "مشهد"
    assert by["economic-tehran"].price_toman == D(1496250)


def test_chabokan_price_change_versions_the_seed_row(snapshot):
    a = ChabokanAdapter()
    plan = plan_sync(a, raw(a, "chabokan"), snapshot.provider_items("chabokan"))
    changed = {c.new.sku: c for c in plan.changes if c.kind == "changed"}
    assert changed["NCO-small40-MHD"].old.price_toman == D(1691006)
    assert changed["NCO-small40-MHD"].new.price_toman == D(1758475)
    assert plan.applicable


def test_mobinhost_reads_both_pages_and_skips_foreign_cards():
    a = MobinHostAdapter()
    by = {i.sku: i for i in a.normalize_catalog(raw(a, "mobinhost"))}
    assert set(by) == {"IR-VPS-2GB", "IR-VPS-4GB", "IR-VPS-6GB", "IR-VDS-16GB", "IR-VDS-24GB", "IR-VDS-32GB"}
    assert by["IR-VPS-4GB"].price_toman == D(795000)
    assert (by["IR-VPS-4GB"].cpu_cores, by["IR-VPS-4GB"].ram_gb, by["IR-VPS-4GB"].storage_gb) == (D(2), D(4), D(40))
    assert by["IR-VPS-4GB"].included_traffic_gb == D(100)
    assert by["IR-VDS-16GB"].price_toman == D(3040000)
    assert by["IR-VDS-16GB"].source_url.endswith("/iran-vds/")


def test_mobinhost_seed_prices_match_live_rows(snapshot):
    a = MobinHostAdapter()
    by = {i.sku: i for i in a.normalize_catalog(raw(a, "mobinhost"))}
    for seed in snapshot.provider_items("mobinhost"):
        if seed.sku in by:
            assert by[seed.sku].price_toman == seed.price_toman, seed.sku


def test_mobinhost_unknown_price_unit_fails_instead_of_guessing():
    a = MobinHostAdapter()
    r = raw(a, "mobinhost")
    r.content = r.content.replace("هزار", "دلار").replace("میلیون", "دلار")
    with pytest.raises(ParseError):
        a.normalize_catalog(r)


def test_starting_price_only_provider_stays_without_a_scraper():
    assert "abrha" not in ADAPTERS and "parspack" in ADAPTERS
