"""Golden tests: expected totals computed by hand from the seed catalog rows cited in each test."""

from decimal import Decimal as D

import pytest

from pricing_engine import BillingContext, PriceStatus, price_inventory, price_resource
from pricing_engine.money import FloatMoneyError, rial_to_toman, to_decimal, toman_to_rial
from tests.conftest import make


def arvan_vm(**kw):
    base = dict(provider_id="arvancloud", service_type="compute_vm", resource_class="standard", cpu_cores="2",
                ram_gb="4", storage_gb="50", storage_type="hot_ssd", requires_public_ipv4=True,
                expected_monthly_download_gb="0", expected_monthly_upload_gb="0")
    base.update(kw)
    return make(**base)


# ---------------------------------------------------------------- ArvanCloud


def test_arvan_cpu_ram_hot_ssd_first_ipv4(snapshot):
    bd = price_resource(arvan_vm(), snapshot)
    # IR-CPU-STANDARD 273000 x2 + IR-RAM-STANDARD 212600 x4 + IR-ST-HOT_SSD 15000 x50 + IR-IPV4-FIRST 195000
    assert bd.status == PriceStatus.EXACT
    assert bd.monthly_total_toman == D(546000) + D(850400) + D(750000) + D(195000) == D(2341400)
    codes = {l.code: l.subtotal_toman for l in bd.components}
    assert codes["compute.cpu"] == D(546000)
    assert codes["compute.ram"] == D(850400)
    assert codes["storage"] == D(750000)
    assert codes["ipv4.first"] == D(195000)


def test_arvan_premium_class_and_extra_ip_and_quantity(snapshot):
    bd = price_resource(arvan_vm(resource_class="premium", ipv4_count="2", quantity="3"), snapshot)
    # per server: 399000x2 + 310700x4 + 15000x50 + 195000 + 390000 = 798000+1242800+750000+585000 = 3375800
    assert bd.monthly_total_toman == D(3375800) * 3


def test_arvan_gpu(snapshot):
    bd = price_resource(arvan_vm(gpu_model="NVIDIA A100 80GB", gpu_count="2"), snapshot)
    assert bd.monthly_total_toman == D(2341400) + D(360000000) * 2


@pytest.mark.parametrize("upload_gb, expected", [
    ("0", D(0)),
    ("250", D(0)),                                  # end of free tier
    ("251", D(1800)),                               # first paid GB
    ("10240", D(9990) * 1800),                      # end of tier 2
    ("10241", D(9990) * 1800 + 1200),               # first GB of tier 3
    ("102400", D(9990) * 1800 + D(92160) * 1200),   # end of tier 3
    ("102401", D(9990) * 1800 + D(92160) * 1200 + 1050),
])
def test_arvan_inbound_traffic_tier_boundaries(snapshot, upload_gb, expected):
    bd = price_resource(arvan_vm(expected_monthly_upload_gb=upload_gb, storage_gb="0", requires_public_ipv4=False,
                                 cpu_cores="0", ram_gb="0"), snapshot)
    traffic = sum((l.subtotal_toman for l in bd.components if l.code.startswith("traffic.upload")), D(0))
    assert traffic == expected
    assert bd.monthly_total_toman == expected


def test_arvan_outbound_traffic_is_catalog_zero_with_visible_assumption(snapshot):
    bd = price_resource(arvan_vm(expected_monthly_download_gb="5000"), snapshot)
    assert bd.monthly_total_toman == D(2341400)
    assert any("not verified" in a for a in bd.assumptions)


def test_arvan_managed_db_components(snapshot):
    r = make(provider_id="arvancloud", service_type="dbaas", resource_class="standard", cpu_cores="2", ram_gb="4",
             storage_gb="100", storage_type="ssd", requires_public_ipv4=True)
    bd = price_resource(r, snapshot)
    # DB-CPU-STANDARD 682500x2 + DB-RAM-STANDARD 531400x4 + DB-ST-SSD 30000x100 + DB-IPV4 195000
    assert bd.monthly_total_toman == D(1365000) + D(2125600) + D(3000000) + D(195000) == D(6685600)


def test_arvan_object_storage_graduated(snapshot):
    r = make(provider_id="arvancloud", service_type="object_storage", storage_type="object_standard", storage_gb="6000")
    bd = price_resource(r, snapshot)
    # 0-5 free, 5-5120 @3000 (5115 GB), 5120-6000 @2600 (880 GB)
    assert bd.monthly_total_toman == D(5115) * 3000 + D(880) * 2600


def test_arvan_scheduled_runtime_is_full_month_with_assumption(snapshot):
    full = price_resource(arvan_vm(), snapshot)
    sched = price_resource(arvan_vm(active_hours_per_month="200", billing_mode="hourly"), snapshot)
    assert sched.monthly_total_toman == full.monthly_total_toman
    assert any("proration" in a for a in sched.assumptions)


# ---------------------------------------------------------------- Liara


def liara_vm(**kw):
    base = dict(provider_id="liara", service_type="compute_vm", sku="IAAS-SATURN", requires_public_ipv4=True,
                expected_monthly_download_gb="10", expected_monthly_upload_gb="5")
    base.update(kw)
    return make(**base)


def test_liara_monthly_iaas_ipv4_download(snapshot):
    bd = price_resource(liara_vm(), snapshot)
    # IAAS-SATURN 2650000 + IAAS-IPV4 200000 + IAAS-DOWNLOAD 2500x10 + upload 0
    assert bd.monthly_total_toman == D(2875000)


def test_liara_scheduled_hourly(snapshot):
    bd = price_resource(liara_vm(billing_mode="hourly", active_hours_per_month="220"), snapshot)
    # 3680x220 + 277x220 + 2500x10
    assert bd.monthly_total_toman == D(809600) + D(60940) + D(25000) == D(895540)


def test_liara_hourly_fractional_hours_exact(snapshot):
    bd = price_resource(liara_vm(billing_mode="hourly", active_hours_per_month="0.5", requires_public_ipv4=False,
                                 expected_monthly_download_gb="0"), snapshot)
    assert bd.monthly_total_toman == D("1840.0")


def test_liara_hourly_without_hours_is_unavailable(snapshot):
    bd = price_resource(liara_vm(billing_mode="hourly"), snapshot)
    assert bd.status == PriceStatus.PRICE_UNAVAILABLE
    assert bd.monthly_total_toman is None
    assert bd.unavailable[0].missing_field == "active_hours_per_month"


def test_liara_paas_unknown_traffic_is_unavailable(snapshot):
    r = make(provider_id="liara", service_type="paas", sku="PAAS-MARS")
    bd = price_resource(r, snapshot)
    assert bd.status == PriceStatus.PRICE_UNAVAILABLE
    r0 = make(provider_id="liara", service_type="paas", sku="PAAS-MARS", expected_monthly_download_gb="0",
              expected_monthly_upload_gb="0")
    assert price_resource(r0, snapshot).monthly_total_toman == D(1300000)


# ---------------------------------------------------------------- fixed SKUs


def serverir(**kw):
    base = dict(provider_id="serverir", service_type="compute_vm", sku="IRAT3024", expected_monthly_download_gb="150",
                expected_monthly_upload_gb="999", requires_public_ipv4=True)
    base.update(kw)
    return make(**base)


def test_serverir_base_plan_and_separate_vat(snapshot):
    no_tax = price_resource(serverir(), snapshot)
    assert no_tax.monthly_total_toman == D(1750000)
    assert no_tax.monthly_tax_toman is None
    assert any("VAT" in a for a in no_tax.assumptions)
    taxed = price_resource(serverir(), snapshot, BillingContext(include_tax=True))
    assert taxed.monthly_total_toman == D(1750000)          # base price unchanged
    assert taxed.monthly_tax_toman == D(175000)              # 10% from serverir-vat rule
    assert taxed.monthly_total_with_tax_toman == D(1925000)
    assert taxed.tax_lines[0].code == "tax.vat"


def test_serverir_download_over_quota_is_unavailable(snapshot):
    bd = price_resource(serverir(expected_monthly_download_gb="201"), snapshot)
    assert bd.status == PriceStatus.PRICE_UNAVAILABLE
    assert bd.monthly_total_toman is None
    assert bd.priced_subtotal_toman == D(1750000)
    assert bd.unavailable[0].missing_field == "overage_price"


def test_serverir_fair_use_plan(snapshot):
    ok = price_resource(serverir(sku="IRFH5024", expected_monthly_download_gb="1500"), snapshot)
    assert ok.monthly_total_toman == D(1690000)
    over = price_resource(serverir(sku="IRFH5024", expected_monthly_download_gb="1501"), snapshot)
    assert over.status == PriceStatus.PRICE_UNAVAILABLE


def test_iranserver_quota_counts_both_directions(snapshot):
    r = make(provider_id="iranserver", sku="NGP-small40", expected_monthly_download_gb="600",
             expected_monthly_upload_gb="401")
    assert price_resource(r, snapshot).status == PriceStatus.PRICE_UNAVAILABLE
    r2 = r.model_copy(update={"expected_monthly_upload_gb": D(400)})
    assert price_resource(r2, snapshot).monthly_total_toman == D(2012399)


def test_chabokan_30_day_plan_assumption(snapshot):
    r = make(provider_id="chabokan", sku="economic-tehran", expected_monthly_download_gb="100",
             expected_monthly_upload_gb="50")
    bd = price_resource(r, snapshot)
    assert bd.monthly_total_toman == D(1260000)
    assert any("30-day" in a for a in bd.assumptions)


def test_sold_out_current_plan_is_priced_but_flagged(snapshot):
    r = make(provider_id="mobinhost", sku="IR-VPS-2GB", expected_monthly_download_gb="10", expected_monthly_upload_gb="10")
    bd = price_resource(r, snapshot)
    assert bd.monthly_total_toman == D(695000)
    assert any("sold_out" in a for a in bd.assumptions)


def test_extra_disk_beyond_plan_is_unavailable(snapshot):
    bd = price_resource(serverir(storage_gb="31"), snapshot)
    assert bd.status == PriceStatus.PRICE_UNAVAILABLE
    assert any(u.component == "storage.extra" for u in bd.unavailable)


# ---------------------------------------------------------------- missing / discovery


def test_unknown_sku_is_price_unavailable_not_zero(snapshot):
    bd = price_resource(serverir(sku="DOES-NOT-EXIST"), snapshot)
    assert bd.status == PriceStatus.PRICE_UNAVAILABLE
    assert bd.monthly_total_toman is None
    assert bd.unavailable[0].code == "PRICE_UNAVAILABLE"


def test_unknown_provider_is_price_unavailable(snapshot):
    bd = price_resource(make(provider_id="aws", sku="t3.micro"), snapshot)
    assert bd.status == PriceStatus.PRICE_UNAVAILABLE


@pytest.mark.parametrize("pid, sku", [("abrha", "IRAN-STARTING")])
def test_discovery_only_providers_never_produce_totals(snapshot, pid, sku):
    bd = price_resource(make(provider_id=pid, sku=sku), snapshot)
    assert bd.status == PriceStatus.DISCOVERY_ONLY
    assert bd.monthly_total_toman is None
    assert bd.priced_subtotal_toman == 0
    assert all(l.status == "info" for l in bd.components)


def test_missing_arvan_class_is_unavailable(snapshot):
    bd = price_resource(arvan_vm(resource_class=None), snapshot)
    assert bd.status == PriceStatus.PRICE_UNAVAILABLE
    assert any(u.missing_field == "resource_class" for u in bd.unavailable)


def test_missing_traffic_is_unavailable(snapshot):
    bd = price_resource(arvan_vm(expected_monthly_upload_gb=None), snapshot)
    assert bd.status == PriceStatus.PRICE_UNAVAILABLE


# ---------------------------------------------------------------- inventory + currency + precision


def test_sample_inventory_quote(snapshot, sample_resources):
    q = price_inventory(sample_resources, snapshot)
    # web-prod 2x1750000 + staging 2875000 + db 6490600 + backups (795GB x 3000) + ci 5323839
    assert q.complete
    assert q.total_toman == D(3500000) + D(2875000) + D(6490600) + D(2385000) + D(5323839) == D(20574439)
    assert q.total_rial == D(205744390)
    assert q.content_hash and q.catalog_version.startswith("cat-")
    assert {s["provider_id"] for s in q.price_sources} == {"serverir", "liara", "arvancloud", "iranserver"}


def test_incomplete_inventory_has_no_total(snapshot, sample_resources):
    bad = sample_resources + [make(id="x", provider_id="abrha", sku="IRAN-STARTING")]
    q = price_inventory(bad, snapshot)
    assert not q.complete
    assert q.total_toman is None
    assert q.priced_subtotal_toman == D(20574439)


def test_quote_is_deterministic(snapshot, sample_resources):
    a = price_inventory(sample_resources, snapshot)
    b = price_inventory(sample_resources, snapshot)
    assert a.content_hash == b.content_hash


def test_toman_rial_conversion():
    assert toman_to_rial(D(1750000)) == D(17500000)
    assert rial_to_toman(D(17500000)) == D(1750000)
    assert rial_to_toman(D(5)) == D("0.5")


def test_floats_are_rejected():
    with pytest.raises(FloatMoneyError):
        to_decimal(0.1)
    with pytest.raises((FloatMoneyError, ValueError)):
        make(cpu_cores=2.5)


def test_decimal_precision_seed_fraction(snapshot):
    row = snapshot.find_one("chabokan", sku="SNAPSHOT-GB-HOUR")
    assert row.price_toman == D("2.77")
    assert isinstance(row.price_toman, D)
    assert row.price_toman * 3 == D("8.31")  # 2.77*3 in binary float is 8.309999999999999


def test_json_serialization_never_emits_floats(snapshot):
    bd = price_resource(liara_vm(), snapshot)
    dumped = bd.model_dump(mode="json")
    assert dumped["monthly_total_toman"] == "2875000"
    assert isinstance(dumped["components"][0]["unit_price_toman"], str)
