"""Property tests (hypothesis) for pricing invariants."""

from decimal import Decimal as D

from hypothesis import given, settings
from hypothesis import strategies as st

from pricing_engine import PriceStatus, load_seed_snapshot, price_resource
from tests.conftest import make

SNAP = load_seed_snapshot()

gb = st.integers(min_value=0, max_value=200_000).map(D)
small = st.integers(min_value=0, max_value=64).map(D)
qty = st.integers(min_value=1, max_value=20).map(D)
cls = st.sampled_from(["basic", "standard", "premium"])

FIXED = [(i.provider_id, i.sku) for i in SNAP.items
         if i.service_type == "compute_vm" and i.pricing_model in ("fixed_sku", "fixed_sku_hourly_monthly",
                                                                    "fixed_sku_flexible_period")]


def arvan(c, cpu, ram, disk, down, up, q):
    return make(provider_id="arvancloud", resource_class=c, cpu_cores=cpu, ram_gb=ram, storage_gb=disk,
                storage_type="hot_ssd", expected_monthly_download_gb=down, expected_monthly_upload_gb=up, quantity=q,
                requires_public_ipv4=True)


@settings(max_examples=150, deadline=None)
@given(c=cls, cpu=small, ram=small, disk=gb, down=gb, up=gb, q=qty)
def test_price_never_negative(c, cpu, ram, disk, down, up, q):
    bd = price_resource(arvan(c, cpu, ram, disk, down, up, q), SNAP)
    assert bd.status == PriceStatus.EXACT
    assert bd.monthly_total_toman >= 0
    assert all(l.subtotal_toman is None or l.subtotal_toman >= 0 for l in bd.components)


@settings(max_examples=150, deadline=None)
@given(c=cls, cpu=small, ram=small, disk=gb, up=gb, q=qty,
       field=st.sampled_from(["cpu_cores", "ram_gb", "storage_gb", "expected_monthly_upload_gb", "quantity"]),
       delta=st.integers(min_value=1, max_value=5000).map(D))
def test_adding_positive_quantity_never_decreases_cost(c, cpu, ram, disk, up, q, field, delta):
    """Arvan's tiers are graduated, so even the tiered meter is monotone non-decreasing."""
    base = arvan(c, cpu, ram, disk, D(0), up, q)
    bigger = base.model_copy(update={field: getattr(base, field) + delta})
    assert price_resource(bigger, SNAP).monthly_total_toman >= price_resource(base, SNAP).monthly_total_toman


@settings(max_examples=100, deadline=None)
@given(plan=st.sampled_from(FIXED), q=qty, down=st.one_of(st.none(), gb), up=st.one_of(st.none(), gb))
def test_missing_price_never_becomes_zero(plan, q, down, up):
    pid, sku = plan
    bd = price_resource(make(provider_id=pid, sku=sku, quantity=q, expected_monthly_download_gb=down,
                             expected_monthly_upload_gb=up, requires_public_ipv4=True), SNAP)
    if bd.unavailable:
        assert bd.status != PriceStatus.EXACT
        assert bd.monthly_total_toman is None
        assert all(l.subtotal_toman is None for l in bd.components if l.status == "unavailable")
    else:
        assert bd.monthly_total_toman > 0


@settings(max_examples=60, deadline=None)
@given(plan=st.sampled_from(FIXED), q=qty)
def test_fixed_plan_scales_linearly_with_quantity(plan, q):
    pid, sku = plan
    one = price_resource(make(provider_id=pid, sku=sku, expected_monthly_download_gb="0",
                              expected_monthly_upload_gb="0"), SNAP)
    many = price_resource(make(provider_id=pid, sku=sku, quantity=q, expected_monthly_download_gb="0",
                               expected_monthly_upload_gb="0"), SNAP)
    if one.monthly_total_toman is not None:
        assert many.monthly_total_toman == one.monthly_total_toman * q
