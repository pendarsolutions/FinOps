from decimal import Decimal as D

import pytest

from pricing_engine import UsageMetrics, price_inventory
from recommendation_engine import OrgSettings, recommend, summarize
from tests.conftest import make


def by(recs, rule_id, resource_id=None, status=None):
    return [r for r in recs if r.rule_id == rule_id and (resource_id is None or r.resource_id == resource_id)
            and (status is None or r.status == status)]


@pytest.fixture(scope="module")
def recs(snapshot, sample_resources):
    return recommend(sample_resources, snapshot, org=OrgSettings(engineer_day_rate_toman="4000000"))


def test_rec001_non_prod_hourly_schedule_exact(recs):
    [r] = by(recs, "REC-001", "staging-app")
    # monthly 2875000 vs hourly (3680+277) x 220 + 2500 x 10 = 895540
    assert r.current_cost_toman == D(2875000)
    assert r.candidate_cost_toman == D(895540)
    assert r.monthly_saving_toman == D(1979460)
    assert r.confidence == "high"
    assert r.evidence["inputs"]["active_hours_per_month"] == "220"
    assert r.price_dates


def test_rec001_unknown_runtime_cannot_determine(snapshot):
    r = make(id="s", name="s", environment="staging", provider_id="liara", sku="IAAS-SATURN",
             expected_monthly_download_gb="0", expected_monthly_upload_gb="0")
    out = recommend([r], snapshot)
    assert by(out, "REC-001") == []
    cannot = [x for x in out if x.status == "cannot_determine" and x.evidence["blocked_rule"] == "REC-001"]
    assert cannot and cannot[0].missing_inputs == ["active_hours_per_month"]


def test_rec001_arvan_has_no_hourly_rate(snapshot):
    r = make(id="a", name="a", environment="dev", provider_id="arvancloud", resource_class="basic", cpu_cores="2",
             ram_gb="2", storage_gb="20", storage_type="hot_ssd", expected_monthly_download_gb="0",
             expected_monthly_upload_gb="0", active_hours_per_month="100")
    out = recommend([r], snapshot)
    assert by(out, "REC-001", status="actionable") == []
    assert any(x.evidence.get("blocked_rule") == "REC-001" and "hourly_price_toman" in x.missing_inputs for x in out)


def test_rec002_downsize_uses_metrics(recs):
    [r] = by(recs, "REC-002", "ci-runner")
    # NGP-large80 5323839 -> NGP-medium40 3093599
    assert r.candidate_cost_toman == D(3093599)
    assert r.monthly_saving_toman == D(2230240)
    assert r.evidence["never_from_allocation_alone"] is True
    assert r.evidence["inputs"]["observation_days"] == 30


def test_rec002_never_from_allocation_alone(snapshot):
    # a hugely over-allocated server with no metrics must NOT get a downsize recommendation
    r = make(id="big", name="big", environment="production", provider_id="iranserver", sku="NGP-2xlarge160",
             expected_monthly_download_gb="10", expected_monthly_upload_gb="10")
    out = recommend([r], snapshot)
    assert by(out, "REC-002", status="actionable") == []
    blocked = [x for x in out if x.evidence.get("blocked_rule") == "REC-002"]
    assert blocked


def test_rec002_high_usage_no_downsize(snapshot):
    r = make(id="hot", name="hot", provider_id="iranserver", sku="NGP-large80", expected_monthly_download_gb="10",
             expected_monthly_upload_gb="10",
             metrics=UsageMetrics(p95_cpu_percent="85", p95_ram_percent="70", observation_days=30))
    assert by(recommend([r], snapshot), "REC-002") == []


def test_rec003_migration_payback(recs):
    [r] = by(recs, "REC-003", "web-prod")
    # Server.ir IRAT3024 x2 (3500000) -> Chabokan economic-tehran x2 (2520000)
    assert r.monthly_saving_toman == D(980000)
    # 2 engineer-days x 2 instances x 4000000
    assert r.one_time_migration_cost_toman == D(16000000)
    assert r.payback_months == D("16.33")
    assert r.evidence["constraints"] and all(c["passed"] for c in r.evidence["constraints"])
    assert r.evidence["differences"]


def test_rec003_without_day_rate_is_unknown_payback(snapshot, sample_resources):
    out = recommend(sample_resources, snapshot)
    [r] = by(out, "REC-003", "web-prod")
    assert r.payback_months is None and r.payback_status == "UNKNOWN_MIGRATION_COST"
    assert any("organization.engineer_day_rate_toman" in x.missing_inputs for x in out)


def test_rec004_hourly_more_expensive_than_monthly(snapshot):
    r = make(id="p", name="p", environment="production", provider_id="liara", sku="IAAS-SATURN", billing_mode="hourly",
             active_hours_per_month="719", expected_monthly_download_gb="0", expected_monthly_upload_gb="0")
    # hourly 3680 x 719 = 2645920 < 2650000 -> no switch; at 720 h hourly = 2649600, still cheaper -> none
    assert by(recommend([r], snapshot), "REC-004", status="actionable") == []


def test_rec004_informational_term_discount_has_no_number(recs):
    [r] = by(recs, "REC-004", "web-prod", status="informational")
    assert r.monthly_saving_toman is None
    assert r.confidence == "unverified"


def test_unpriceable_resource_yields_cannot_determine(snapshot):
    r = make(id="pp", name="pp", provider_id="parspack", sku="CONFIGURATOR-DEFAULT")
    [x] = recommend([r], snapshot)
    assert x.status == "cannot_determine" and x.monthly_saving_toman is None


def test_every_actionable_has_evidence_and_dates(recs):
    for r in recs:
        if r.status == "actionable":
            assert r.evidence["current"]["components"]
            assert r.evidence["candidate"]["components"]
            assert r.evidence["catalog_version"].startswith("cat-")
            assert r.price_dates
            assert r.current_cost_toman - r.candidate_cost_toman == r.monthly_saving_toman


def test_summary_does_not_double_count(snapshot, sample_resources, recs):
    q = price_inventory(sample_resources, snapshot)
    s = summarize(recs, q.total_toman, snapshot)
    # best per resource: ci-runner 2283839 (REC-003) + staging 2080000 (REC-003) + web-prod 980000
    assert s["avoidable_monthly_toman"] == D(2283839) + D(2080000) + D(980000)
    assert len(s["counted_recommendation_keys"]) == 3
