"""ParsPack: rows from the official calculator table (fixture cut from the page on 2026-11-02)."""

import gzip
import json
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path

import pytest

from pricing_engine import Resource, UsageMetrics, price_resource
from pricing_engine.models import PriceStatus
from provider_adapters import ParseError, ParsPackAdapter, RawCatalog, plan_sync
from recommendation_engine import recommend

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "providers" / "parspack-2026-11-02.html.gz"
NOW = datetime(2026, 11, 2, tzinfo=UTC)


def raw(content=None):
    a = ParsPackAdapter()
    return RawCatalog("parspack", a.source_url, NOW, content or gzip.decompress(FIX.read_bytes()).decode())


def server(**kw):
    values = {"id": "x", "name": "x", "provider_id": "parspack", "cpu_cores": "16", "ram_gb": "32", "storage_gb": "300",
              "requires_public_ipv4": True}
    return Resource(**{**values, **kw})


def test_formula_reproduces_the_pages_own_total():
    by = {i.sku: i for i in ParsPackAdapter().normalize_catalog(raw())}
    total = by["PP-CPU-1"].daily_price_toman + by["PP-RAM-2"].daily_price_toman + by["PP-DISK-25"].daily_price_toman
    assert total == D(37795)  # the page's selectedProductData.total_price for 1 CPU, 2 GB, 25 GB


def test_only_iranian_prices_and_monthly_is_30_days():
    items = ParsPackAdapter().normalize_catalog(raw())
    assert all(i.region_country == "IR" for i in items)
    assert all(i.price_toman == i.daily_price_toman * 30 for i in items)


def test_real_server_is_priced_from_specs_alone(snapshot):
    bd = price_resource(server(), snapshot)
    assert bd.status == PriceStatus.EXACT
    assert bd.monthly_total_toman == (D(181195) + D(229369) + D(27953)) * 30
    assert any("traffic" in a for a in bd.assumptions)
    assert {c.code: c.status.value for c in bd.components}["traffic"] == "assumed_included"


def test_reported_sizes_round_up_to_what_is_sold_and_say_so(snapshot):
    bd = price_resource(server(ram_gb="31.34", storage_gb="290"), snapshot)
    assert bd.monthly_total_toman == (D(181195) + D(229369) + D(27953)) * 30
    assert sum("next size sold" in a for a in bd.assumptions) == 2


def test_size_beyond_the_table_is_unavailable_not_guessed(snapshot):
    bd = price_resource(server(cpu_cores="64"), snapshot)
    assert bd.status == PriceStatus.PRICE_UNAVAILABLE and bd.monthly_total_toman is None


def test_quantity_multiplies(snapshot):
    assert price_resource(server(quantity="2"), snapshot).monthly_total_toman == (D(181195) + D(229369) + D(27953)) * 60


def test_underused_server_gets_a_downsize_to_sizes_really_sold(snapshot):
    m = UsageMetrics(p95_cpu_percent="2", p95_ram_percent="26", disk_used_gb="92", observation_days=20)
    rec = next(x for x in recommend([server(environment="production", metrics=m)], snapshot) if x.rule_id == "REC-002")
    assert rec.status == "actionable"
    # needs 0.416 CPU -> 1, and 10.8 GB -> the 16 GB size; the disk stays
    assert rec.candidate_cost_toman == (D(12102) + D(115544) + D(27953)) * 30
    assert rec.monthly_saving_toman == D(13155510) - D(4667970)
    assert "16" in rec.summary_en


def test_missing_table_and_changed_shape_fail_visibly():
    with pytest.raises(ParseError):
        ParsPackAdapter().normalize_catalog(raw("<html>nothing</html>"))
    content = gzip.decompress(FIX.read_bytes()).decode()
    head, rest = content.split("= ", 1)
    data, _ = json.JSONDecoder().raw_decode(rest)
    data["Iran"]["cities"][0]["data_centers"][1]["billings"]["pricingTable"]["linux"]["2048"]["ram"] += 1
    with pytest.raises(ParseError, match="different prices"):
        ParsPackAdapter().normalize_catalog(raw(f"{head}= {json.dumps(data)};"))


def test_sync_against_the_seed_changes_nothing(snapshot):
    a = ParsPackAdapter()
    plan = plan_sync(a, raw(), snapshot.provider_items("parspack"))
    assert plan.applicable and plan.changes == []
