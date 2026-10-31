"""Adapter tests against REAL official pages saved on 2026-10-04 (gzipped). No live network in CI."""

import gzip
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import pytest

from pricing_engine import price_resource
from pricing_engine.catalog import CatalogSnapshot
from provider_adapters import (
    ArvanCloudAdapter,
    IranServerAdapter,
    LiaraAdapter,
    ParseError,
    RawCatalog,
    ServerIrAdapter,
    SourceBlockedError,
    plan_sync,
)
from tests.conftest import make

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "providers"
NOW = datetime(2026, 10, 4, tzinfo=UTC)


def raw(adapter, name):
    content = gzip.decompress((FIX / f"{name}-2026-10-04.html.gz").read_bytes()).decode("utf-8")
    return RawCatalog(adapter.provider_id, adapter.source_url, NOW, content)


def test_serverir_parses_all_cards_matching_seed_prices(snapshot):
    a = ServerIrAdapter()
    items = a.normalize_catalog(raw(a, "serverir"))
    assert len(items) == 24
    by = {i.sku: i for i in items}
    # IRFH80612 is in the seed but no longer on the live page -> must surface as 'removed' in sync
    assert "IRFH80612" not in by
    for seed in snapshot.provider_items("serverir"):
        if seed.sku == "IRFH80612":
            continue
        assert by[seed.sku].price_toman == seed.price_toman, seed.sku
        assert by[seed.sku].cpu_cores == seed.cpu_cores
        assert by[seed.sku].ram_gb == seed.ram_gb
        assert by[seed.sku].storage_gb == seed.storage_gb
    assert by["IRAT3024"].datacenter == "Asiatech"
    assert by["IRAT3024"].included_traffic_gb == D(200)
    assert by["IRFH5024"].resource_class == "optimized_core" and by["IRFH5024"].cpu_shared is False
    assert by["IRAF2-4024"].attributes["traffic_policy"] == "unlimited_rate_limited"
    assert by["IRAF2-4024"].attributes["rate_limit_mbps"] == "8"
    assert by["IRFH100816"].attributes["traffic_policy"] == "unlimited"
    assert by["IRAT3024"].tax_included is False  # VAT kept separate


def test_serverir_live_page_changed_irfh_traffic_terms(snapshot):
    """The live page meters IRFH download at 1600 Toman/GB; the seed said fair-use. Sync must version it."""
    a = ServerIrAdapter()
    by = {i.sku: i for i in a.normalize_catalog(raw(a, "serverir"))}
    assert by["IRFH5024"].attributes["traffic_policy"] == "metered_download"
    assert by["IRFH5024"].attributes["download_toman_per_gb"] == "1600"
    plan = plan_sync(a, raw(a, "serverir"), snapshot.provider_items("serverir"))
    changed = {c.new.sku: c for c in plan.changes if c.kind == "changed"}
    assert "IRFH5024" in changed and "traffic_policy" in changed["IRFH5024"].changed_fields
    assert plan.status in ("ok", "warning")
    assert plan.median_price_move == 0
    assert any(c.kind == "removed" and c.old.sku == "IRFH80612" for c in plan.changes)


def test_metered_download_priced_from_catalog_row(snapshot):
    a = ServerIrAdapter()
    items = a.normalize_catalog(raw(a, "serverir"))
    snap = CatalogSnapshot(providers=snapshot.providers, items=items, billing_rules=snapshot.billing_rules,
                           policy=snapshot.policy, equivalence_rules=snapshot.equivalence_rules,
                           recommendation_rules=snapshot.recommendation_rules, snapshot_at=NOW)
    bd = price_resource(make(provider_id="serverir", sku="IRFH5024", expected_monthly_download_gb="100"), snap)
    assert bd.monthly_total_toman == D(1690000) + D(100) * 1600


def test_iranserver_parses_ngp_rows(snapshot):
    a = IranServerAdapter()
    items = a.normalize_catalog(raw(a, "iranserver"))
    assert {i.sku for i in items} == {s.sku for s in snapshot.provider_items("iranserver")}
    by = {i.sku: i for i in items}
    for seed in snapshot.provider_items("iranserver"):
        assert by[seed.sku].price_toman == seed.price_toman
        assert by[seed.sku].included_traffic_gb == D(1000)
    assert by["NGP-small40"].cpu_shared is True


def test_liara_parses_plans_and_network(snapshot):
    a = LiaraAdapter()
    items = a.normalize_catalog(raw(a, "liara"))
    by = {i.sku: i for i in items}
    for seed in snapshot.provider_items("liara"):
        if seed.service_type == "object_storage":
            assert seed.sku not in by  # not on this page; sync scope leaves it untouched
            continue
        assert by[seed.sku].price_toman == seed.price_toman, seed.sku
        assert by[seed.sku].hourly_price_toman == seed.hourly_price_toman, seed.sku
    assert by["IAAS-DOWNLOAD"].price_toman == D(2500)
    assert by["IAAS-IPV4"].price_toman == D(200000) and by["IAAS-IPV4"].hourly_price_toman == D(277)
    assert by["PAAS-EARTH"].ram_gb == D("0.512")
    plan = plan_sync(a, raw(a, "liara"), snapshot.provider_items("liara"))
    assert not [c for c in plan.changes if c.kind == "changed"]
    assert not [c for c in plan.changes if c.kind == "removed"]


def test_arvan_bot_challenge_fails_visibly(snapshot):
    a = ArvanCloudAdapter()
    with pytest.raises(SourceBlockedError):
        a.normalize_catalog(raw(a, "arvan"))
    plan = plan_sync(a, raw(a, "arvan"), snapshot.provider_items("arvancloud"))
    assert plan.status == "failed" and "bot-challenge" in plan.error
    assert plan.changes == []


# ---------------------------------------------------------------- guardrails


class FakeAdapter:
    provider_id = "serverir"
    source_url = "https://example.invalid"
    scope = {("compute_vm", "iran_vps")}
    key_skus = {"IRAT3024"}

    def __init__(self, items):
        self._items = items

    def normalize_catalog(self, raw):
        if isinstance(self._items, Exception):
            raise self._items
        return self._items


def _raw(content="x"):
    return RawCatalog("serverir", "https://example.invalid", NOW, content)


def test_zero_items_fails(snapshot):
    plan = plan_sync(FakeAdapter([]), _raw(), snapshot.provider_items("serverir"))
    assert plan.status == "failed" and not plan.applicable


def test_parse_error_fails(snapshot):
    plan = plan_sync(FakeAdapter(ParseError("layout changed")), _raw(), snapshot.provider_items("serverir"))
    assert plan.status == "failed" and "layout changed" in plan.error


def test_mass_price_change_is_quarantined(snapshot):
    prev = snapshot.provider_items("serverir")
    doubled = [p.model_copy(update={"price_toman": p.price_toman * 2}) for p in prev]
    plan = plan_sync(FakeAdapter(doubled), _raw(), prev)
    assert plan.status == "quarantined" and not plan.applicable
    assert plan.median_price_move == D(1)


def test_small_change_applies_with_new_version(snapshot):
    prev = snapshot.provider_items("serverir")
    new = [p.model_copy(update={"price_toman": p.price_toman + 10000}) if p.sku == "IRAT3024" else p.model_copy()
           for p in prev]
    plan = plan_sync(FakeAdapter(new), _raw(), prev)
    assert plan.status == "ok"
    [c] = plan.changes
    assert c.kind == "changed" and c.old.price_toman == D(1750000) and c.new.price_toman == D(1760000)


def test_missing_key_sku_warns(snapshot):
    prev = snapshot.provider_items("serverir")
    new = [p.model_copy() for p in prev if p.sku != "IRAT3024"]
    plan = plan_sync(FakeAdapter(new), _raw(), prev)
    assert plan.status == "warning"
    assert any("IRAT3024" in w for w in plan.warnings)
    assert any(c.kind == "removed" and c.old.sku == "IRAT3024" for c in plan.changes)


def test_hash_changed_but_output_same_warns(snapshot):
    prev = snapshot.provider_items("serverir")
    plan = plan_sync(FakeAdapter([p.model_copy() for p in prev]), _raw("new html"), prev,
                     previous_content_hash="sha256:old")
    assert any("hash changed" in w for w in plan.warnings)


def test_stale_source_date_warns(snapshot):
    prev = snapshot.provider_items("serverir")
    old = [p.model_copy(update={"source_price_date": "2026-01-01"}) for p in prev]
    plan = plan_sync(FakeAdapter(old), _raw(), prev, stale_after_days=45)
    assert any("older than 45 days" in w for w in plan.warnings)
