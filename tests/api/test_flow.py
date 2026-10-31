"""End-to-end API flow mirroring the MVP Definition of Done."""

import gzip
from datetime import UTC, datetime
from pathlib import Path

import pytest

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "providers"


def test_health(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    r = client.get("/health/ready")
    assert r.status_code == 200 and r.json()["checks"]["catalog_items"] == 123


def test_auth_required(client):
    assert client.get("/api/v1/catalog").status_code == 401


def test_seed_is_idempotent(api_env):
    from finops_api.catalog_store import seed_pricing
    from finops_api.config import get_settings
    from finops_api.db import SessionLocal

    with SessionLocal() as db:
        stats = seed_pricing(db, get_settings().seed_dir)
    assert stats["items_inserted"] == 0 and stats["items_unchanged"] == 123


def test_catalog_has_source_metadata_and_money_as_strings(client, auth):
    items = client.get("/api/v1/catalog", headers=auth).json()
    assert len(items) == 123
    for i in items:
        assert i["source_url"] and i["source_retrieved_at"]
        if i["price_toman"] is not None:
            assert isinstance(i["price_toman"], str)
    one = next(i for i in items if i["sku"] == "IRAT3024")
    assert one["price_toman"] == "1750000" and one["price_rial"] == "17500000"
    hist = client.get(f"/api/v1/catalog/{one['id']}/history", headers=auth).json()
    assert len(hist) == 1


def test_providers_listing(client, auth):
    provs = client.get("/api/v1/providers", headers=auth).json()
    assert [p["id"] for p in provs][:4] == ["arvancloud", "liara", "serverir", "iranserver"]
    pp = next(p for p in provs if p["id"] == "parspack")
    assert pp["exact_eligible"] is False and pp["adapter"] == "seed_only"


@pytest.fixture(scope="module")
def demo_inv(client, auth):
    r = client.post("/api/v1/inventories/demo", headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def test_analysis_blocked_until_confirmed(client, auth, demo_inv):
    assert demo_inv["status"] == "needs_confirmation"
    assert not demo_inv["can_analyze"]
    r = client.post(f"/api/v1/inventories/{demo_inv['id']}/quote", headers=auth, json={})
    assert r.status_code == 409
    r = client.post(f"/api/v1/inventories/{demo_inv['id']}/confirm", headers=auth, json={})
    assert r.status_code == 409  # rows not confirmed individually
    assert r.json()["detail"]["blocking"]


def test_confirm_quote_compare_recommend_report(client, auth, demo_inv):
    inv_id = demo_inv["id"]
    r = client.post(f"/api/v1/inventories/{inv_id}/confirm", headers=auth, json={"confirm_all_rows": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmed"

    q = client.post(f"/api/v1/inventories/{inv_id}/quote", headers=auth, json={"include_tax": True}).json()
    assert q["complete"] and q["total_toman"] == "20574439"
    assert q["total_tax_toman"] == "350000"  # Server.ir VAT only, separate
    assert q["content"]["price_sources"]

    web = next(r for r in demo_inv["resources"] if r["name"] == "web-prod")
    cmp = client.post(f"/api/v1/inventories/{inv_id}/compare", headers=auth,
                      json={"resource_ids": [web["id"]]}).json()
    res = cmp["results"][0]
    assert res["candidates"] and all(c["passed_hard_constraints"] for c in res["candidates"])
    assert any(r["label"] == "MobinHost IR-VPS-4GB" for r in res["rejected"])

    recs = client.post(f"/api/v1/inventories/{inv_id}/recommendations", headers=auth).json()
    assert recs["summary"]["avoidable_monthly_toman"] == "5343839"
    rec = next(r for r in recs["recommendations"] if r["rule_id"] == "REC-003" and r["resource_name"] == "web-prod")
    assert rec["payback_months"] == "16.33"
    got = client.get(f"/api/v1/recommendations/{rec['id']}", headers=auth).json()
    assert got["evidence"]["constraints"]

    ov = client.get(f"/api/v1/inventories/{inv_id}/overview", headers=auth).json()
    assert len(ov["top_opportunities"]) == 3 and ov["price_freshness"]

    for lang in ("fa", "en"):
        html = client.get(f"/api/v1/inventories/{inv_id}/report?lang={lang}", headers=auth)
        assert html.status_code == 200
        assert "20,574,439" in html.text
        assert ("dir=\"rtl\"" in html.text) == (lang == "fa")


def test_editing_after_confirmation_requires_reconfirmation(client, auth, demo_inv):
    inv_id = demo_inv["id"]
    rid = demo_inv["resources"][0]["id"]
    r = client.patch(f"/api/v1/inventories/{inv_id}/resources/{rid}", headers=auth,
                     json={"fields": {"expected_monthly_download_gb": "190"}}).json()
    assert r["status"] == "needs_confirmation"
    assert client.post(f"/api/v1/inventories/{inv_id}/quote", headers=auth, json={}).status_code == 409
    r = client.patch(f"/api/v1/inventories/{inv_id}/resources/{rid}", headers=auth,
                     json={"user_confirmed": True}).json()
    assert client.post(f"/api/v1/inventories/{inv_id}/confirm", headers=auth, json={}).status_code == 200


def test_unknown_field_can_be_acknowledged_and_shows_price_unavailable(client, auth):
    inv = client.post("/api/v1/inventories", headers=auth, json={"name": "builder", "resources": [
        {"name": "vm", "provider_id": "serverir", "sku": "IRAT3024", "environment": "production", "quantity": "1"}]}).json()
    row = inv["resources"][0]
    assert row["missing_fields"] == ["expected_monthly_download_gb"]
    assert not inv["can_confirm"]
    inv = client.patch(f"/api/v1/inventories/{inv['id']}/resources/{row['id']}", headers=auth,
                       json={"fields": {"unknown_fields": ["expected_monthly_download_gb"]}, "user_confirmed": True}).json()
    assert inv["can_confirm"]
    client.post(f"/api/v1/inventories/{inv['id']}/confirm", headers=auth, json={})
    q = client.post(f"/api/v1/inventories/{inv['id']}/quote", headers=auth, json={}).json()
    assert not q["complete"] and q["total_toman"] is None
    assert q["content"]["unavailable"][0]["code"] == "PRICE_UNAVAILABLE"


def test_chat_to_inventory_persian(client, auth):
    r = client.post("/api/v1/inventories/from-chat", headers=auth, json={
        "text": "ما ۳ تا سرور ایران داریم. دوتاشون ۴ گیگ رم و ۲ هسته هستن و staging فقط ساعت کاری استفاده میشه"})
    assert r.status_code == 200, r.text
    inv = r.json()
    assert inv["source_type"] == "chat" and inv["status"] == "needs_confirmation"
    assert [x["quantity"] for x in inv["resources"]] == ["2", "1"]
    assert inv["source_meta"]["questions"]
    assert all(x["review_status"] != "confirmed" for x in inv["resources"])


def test_invoice_csv_upload(client, auth):
    csv_text = ("Provider,Description,Qty,Amount\n"
                "Server.ir,VPS IRAT3024 Asiatech,2,35000000 ریال\n"
                "Server.ir,Customer ID: CUST-99887766,,\n")
    r = client.post("/api/v1/inventories/from-invoice", headers=auth,
                    files={"file": ("invoice.csv", csv_text.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    inv = r.json()
    meta = inv["source_meta"]["invoice"]
    assert meta["detected_currency"] == "RIAL" and not meta["currency_confirmation_required"]
    assert meta["redaction_counts"].get("labelled_id") == 1
    assert inv["resources"][0]["sku"] == "IRAT3024" and inv["resources"][0]["quantity"] == "2"
    assert "download_url" in inv["upload"]
    dl = client.get(inv["upload"]["download_url"])
    assert dl.status_code == 200
    assert client.get(inv["upload"]["download_url"].replace("sig=", "sig=x")).status_code == 403


def test_invoice_ambiguous_currency_blocks_confirmation(client, auth):
    r = client.post("/api/v1/inventories/from-invoice", headers=auth,
                    files={"file": ("inv.csv", b"Plan,Price\nNGP-small40,2012399\n", "text/csv")})
    inv = r.json()
    assert inv["currency"] == "UNCONFIRMED"
    assert client.post(f"/api/v1/inventories/{inv['id']}/confirm", headers=auth,
                       json={"confirm_all_rows": True}).status_code == 409
    client.post(f"/api/v1/inventories/{inv['id']}/currency", headers=auth, json={"currency": "TOMAN"})
    # still blocked by missing environment/traffic, not by currency
    r = client.post(f"/api/v1/inventories/{inv['id']}/confirm", headers=auth, json={"confirm_all_rows": True})
    assert r.status_code == 409 and "blocking" in r.json()["detail"]


def test_upload_rejects_bad_types(client, auth):
    r = client.post("/api/v1/inventories/from-invoice", headers=auth,
                    files={"file": ("x.exe", b"MZ....", "application/octet-stream")})
    assert r.status_code == 415
    r = client.post("/api/v1/inventories/from-invoice", headers=auth,
                    files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 415


def test_advisor_offline_is_evidence_bound(client, auth, demo_inv):
    r = client.post("/api/v1/advisor/chat", headers=auth, json={"inventory_id": demo_inv["id"],
                                                               "question": "کجا می‌توانیم صرفه‌جویی کنیم؟", "lang": "fa"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["guard"]["ok"] is True
    assert body["evidence_ids"]
    assert "تومان" in body["answer"]


def test_sync_from_saved_page_versions_prices(client, auth, api_env):
    """Server.ir live page: IRFH traffic changed and IRFH80612 removed -> new versions, history kept."""
    from finops_api.catalog_store import run_provider_sync
    from finops_api.db import SessionLocal
    from provider_adapters import ServerIrAdapter
    from provider_adapters.base import RawCatalog

    a = ServerIrAdapter()
    raw = RawCatalog("serverir", a.source_url, datetime(2026, 10, 5, tzinfo=UTC),
                     gzip.decompress((FIX / "serverir-2026-10-04.html.gz").read_bytes()).decode())
    with SessionLocal() as db:
        run = run_provider_sync(db, "serverir", triggered_by="test", raw=raw)
        assert run.status in ("ok", "warning"), run.error
    items = client.get("/api/v1/catalog?provider_id=serverir", headers=auth).json()
    assert "IRFH80612" not in {i["sku"] for i in items}
    irfh = next(i for i in items if i["sku"] == "IRFH5024")
    assert irfh["attributes"]["traffic_policy"] == "metered_download"
    hist = client.get(f"/api/v1/catalog/{irfh['id']}/history", headers=auth).json()
    assert len(hist) == 2 and hist[0]["valid_to"] is not None and hist[0]["attributes"]["traffic_policy"] == "fair_use"
    runs = client.get("/api/v1/admin/sync-runs", headers=auth).json()
    assert runs[0]["provider_id"] == "serverir"


def test_arvan_sync_failure_is_visible(client, auth, api_env):
    from finops_api.catalog_store import run_provider_sync
    from finops_api.db import SessionLocal
    from provider_adapters import ArvanCloudAdapter
    from provider_adapters.base import RawCatalog

    a = ArvanCloudAdapter()
    raw = RawCatalog("arvancloud", a.source_url, datetime(2026, 10, 5, tzinfo=UTC),
                     gzip.decompress((FIX / "arvan-2026-10-04.html.gz").read_bytes()).decode())
    with SessionLocal() as db:
        run = run_provider_sync(db, "arvancloud", triggered_by="test", raw=raw)
    assert run.status == "failed"
    provs = client.get("/api/v1/providers", headers=auth).json()
    arvan = next(p for p in provs if p["id"] == "arvancloud")
    assert arvan["last_sync"]["status"] == "failed"
    assert arvan["catalog_items"] == 50  # seed rows untouched


def test_catalog_versions_are_immutable(api_env):
    from sqlalchemy import select

    from finops_api.db import SessionLocal
    from finops_api.orm import CatalogItemVersion, ImmutableRowError

    with SessionLocal() as db:
        row = db.scalar(select(CatalogItemVersion).where(CatalogItemVersion.sku == "IRAT3024"))
        row.price_toman = 1
        with pytest.raises(ImmutableRowError):
            db.flush()
        db.rollback()


def test_quotes_are_immutable(api_env):
    from sqlalchemy import select

    from finops_api.db import SessionLocal
    from finops_api.orm import ImmutableRowError, QuoteRow

    with SessionLocal() as db:
        q = db.scalar(select(QuoteRow))
        q.complete = not q.complete
        with pytest.raises(ImmutableRowError):
            db.flush()
        db.rollback()


def test_viewer_cannot_mutate(client, api_env):
    from finops_api.db import SessionLocal
    from finops_api.security import create_user_with_org, issue_token

    with SessionLocal() as db:
        u, org = create_user_with_org(db, "viewer@example.ir", "viewer-password-1", "V", "ViewOrg", role="viewer")
        db.commit()
        tok = issue_token(u.id, org.id)
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/v1/catalog", headers=h).status_code == 200
    assert client.post("/api/v1/inventories/demo", headers=h).status_code == 403
    assert client.post("/api/v1/admin/providers/serverir/sync", headers=h).status_code == 403


def test_org_isolation(client, auth, demo_inv):
    r = client.post("/api/v1/auth/register", json={"email": "other@example.ir", "password": "other-password-1",
                                                   "organization_name": "Other"})
    other = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"/api/v1/inventories/{demo_inv['id']}", headers=other).status_code == 404




def test_audit_log_records_changes(client, auth):
    logs = client.get("/api/v1/audit-logs", headers=auth).json()
    actions = {l["action"] for l in logs}
    assert {"inventory.create", "inventory.confirm", "analysis.quote", "analysis.recommendations",
            "inventory.resource.update"} <= actions


def test_upload_info_survives_reload_and_unmatched_rows_reported(client, auth):
    r = client.post("/api/v1/inventories/from-invoice", headers=auth,
                    files={"file": ("i.csv", b"Plan,Price\nNGP-small40,2012399\nUnknownThing,5000\n", "text/csv")})
    inv = r.json()
    assert inv["source_meta"]["invoice"]["unmatched_lines"] == ["UnknownThing | 5000"]
    again = client.get(f"/api/v1/inventories/{inv['id']}", headers=auth).json()
    assert again["upload"]["download_url"] and again["upload"]["delete_after"]
    client.post(f"/api/v1/inventories/{inv['id']}/currency", headers=auth, json={"currency": "RIAL"})
    assert client.get(f"/api/v1/inventories/{inv['id']}", headers=auth).json()["invoice_currency"] == "RIAL"


def test_saving_day_rate_clears_sample_label(client, auth):
    client.post("/api/v1/inventories/demo", headers=auth)
    assert "engineer_day_rate_label" in client.get("/api/v1/settings", headers=auth).json()["settings"]
    s = client.put("/api/v1/settings", headers=auth, json={"engineer_day_rate_toman": "5000000"}).json()["settings"]
    assert s["engineer_day_rate_toman"] == "5000000" and "engineer_day_rate_label" not in s
