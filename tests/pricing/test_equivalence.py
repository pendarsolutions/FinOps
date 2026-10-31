from decimal import Decimal as D

from pricing_engine import BillingContext, compare_resource, find_equivalents
from tests.conftest import make


def web_prod():
    return make(id="web", provider_id="serverir", sku="IRAT3024", quantity="2", expected_monthly_download_gb="150",
                expected_monthly_upload_gb="20", requires_public_ipv4=True)


def test_fixed_sku_comparison_exact_saving(snapshot):
    src = web_prod()
    cand = make(id="web", provider_id="chabokan", sku="economic-tehran", quantity="2",
                expected_monthly_download_gb="150", expected_monthly_upload_gb="20", requires_public_ipv4=True)
    c = compare_resource(src, cand, snapshot)
    assert c.passed_hard_constraints
    assert c.exact
    # (1750000 - 1260000) x 2
    assert c.monthly_saving_toman == D(980000)
    assert c.monthly_saving_percent == D("28.00")
    dims = {d.dimension: d for d in c.differences}
    assert dims["cpu_class"].verdict == "unknown"
    assert dims["storage_gb"].verdict == "better"


def test_sold_out_candidate_is_excluded(snapshot):
    src = make(provider_id="serverir", sku="IRAF2011", expected_monthly_download_gb="10", expected_monthly_upload_gb="5")
    res = find_equivalents(src, snapshot)
    assert all(c.candidate_label != "MobinHost IR-VPS-2GB" for c in res.candidates)
    rejected = {r.label: r for r in res.rejected}
    assert "MobinHost IR-VPS-2GB" in rejected
    assert any(f.constraint_id == "HC-AVAIL" for f in rejected["MobinHost IR-VPS-2GB"].failed_constraints)


def test_discovery_only_candidates_rejected(snapshot):
    res = find_equivalents(web_prod(), snapshot)
    labels = {r.label for r in res.rejected}
    assert any("ParsPack" in l for l in labels)
    assert any("Abrha" in l for l in labels)
    assert all(c.candidate_provider_id not in ("parspack", "abrha") for c in res.candidates)


def test_dedicated_source_never_matched_by_shared(snapshot):
    src = make(provider_id="serverir", sku="IRFH5048", expected_monthly_download_gb="100", expected_monthly_upload_gb="0")
    res = find_equivalents(src, snapshot)
    for c in res.candidates:
        cls = next(d for d in c.differences if d.dimension == "cpu_class")
        assert cls.candidate_value != "shared"


def test_undersized_candidate_rejected(snapshot):
    res = find_equivalents(web_prod(), snapshot)
    for c in res.candidates:
        assert c.candidate.status == "EXACT"
        spec = {d.dimension: d for d in c.differences}
        assert spec["ram_gb"].candidate_value >= D(4)
        assert spec["cpu_cores"].candidate_value >= D(2)


def test_quota_overflow_candidate_rejected_not_estimated(snapshot):
    # MobinHost IR-VPS-4GB includes 100GB (direction unspecified); 150+20 GB exceeds it and overage is unknown
    res = find_equivalents(web_prod(), snapshot)
    rej = {r.label: r for r in res.rejected}
    assert any(f.constraint_id == "HC-PRICEABLE" for f in rej["MobinHost IR-VPS-4GB"].failed_constraints)


def test_low_fit_is_needs_human_review(snapshot):
    res = find_equivalents(web_prod(), snapshot)
    big = [c for c in res.candidates if c.candidate_label == "Liara IAAS-URANUS"]
    assert big and big[0].confidence == "NEEDS_HUMAN_REVIEW"


def test_iran_only_by_default(snapshot):
    res = find_equivalents(web_prod(), snapshot)
    assert any("Iran-only" in n for n in res.notes)
    res2 = find_equivalents(web_prod(), snapshot, BillingContext(allow_outside_iran=True))
    assert not any("Iran-only" in n for n in res2.notes)
