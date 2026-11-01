"""Servers API with the SSH exchange replaced by recorded output."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from fleet import HostKeyChanged, SshError
from fleet.ssh import CollectResult

OUT = """hostname=web-1
os=Ubuntu 24.04
cpu_cores={cores}
cpu_total={total}
cpu_idle={idle}
mem_total_kb=3900000
mem_available_kb=3500000
disk_total_kb=39000000
disk_used_kb=5000000
rx_bytes={rx}
tx_bytes={tx}
"""


def output(total=1000, idle=900, rx=0, tx=0, cores=2):
    return OUT.format(total=total, idle=idle, rx=rx, tx=tx, cores=cores)


@pytest.fixture
def ssh(api_env, monkeypatch):
    import finops_api.fleet_service as fs

    state = {"output": output(), "error": None, "seen_known": []}

    def fake(host, port, key, known, timeout=15.0):
        assert "OPENSSH PRIVATE KEY" in key
        state["seen_known"].append(known)
        if state["error"]:
            raise state["error"]
        return CollectResult(state["output"], "ssh-ed25519 HOSTKEY")

    monkeypatch.setattr(fs, "collect", fake)
    return state


counter = {"n": 0}


@pytest.fixture
def server(client, auth, ssh):
    counter["n"] += 1
    r = client.post("/api/v1/servers", headers=auth, json={"name": f"web-{counter['n']}", "host": f"10.0.0.{counter['n']}"})
    assert r.status_code == 200, r.text
    yield r.json()
    client.delete(f"/api/v1/servers/{r.json()['id']}", headers=auth)


def viewer(client):
    r = client.post("/api/v1/members", headers=_owner(client), json={"email": f"v{counter['n']}@example.ir", "password": "viewer-password-1", "role": "viewer"})
    assert r.status_code == 200, r.text
    login = client.post("/api/v1/auth/login", json={"email": f"v{counter['n']}@example.ir", "password": "viewer-password-1"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _owner(client):
    r = client.post("/api/v1/auth/login", json={"email": "owner@example.ir", "password": "correct-horse-1"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_adding_a_server_collects_and_remembers_identity(server):
    assert server["status"] == "online"
    assert server["cpu_cores"] == 2 and server["hostname"] == "web-1"
    assert server["priced"] is False and server["monthly_total_toman"] is None  # never priced before confirmation


def test_duplicate_is_refused(client, auth, server):
    r = client.post("/api/v1/servers", headers=auth, json={"name": "again", "host": server["host"]})
    assert r.status_code == 409


@pytest.mark.parametrize("host", ["-oProxyCommand=evil", "a b", "x;rm", ""])
def test_unsafe_hosts_are_refused(client, auth, host):
    assert client.post("/api/v1/servers", headers=auth, json={"name": "x", "host": host}).status_code == 422


def test_suggestions_then_confirm_prices_with_the_engine(client, auth, server, ssh):
    detail = client.get(f"/api/v1/servers/{server['id']}", headers=auth).json()
    assert any(s["provider_id"] == "iranserver" for s in detail["suggestions"]) or detail["suggestions"]
    r = client.patch(f"/api/v1/servers/{server['id']}", headers=auth, json={"provider_id": "mobinhost", "sku": "IR-VPS-4GB", "environment": "production"})
    assert r.status_code == 200, r.text
    detail = client.get(f"/api/v1/servers/{server['id']}", headers=auth).json()
    # traffic is still unknown on a new server, so the engine must not claim an exact total
    assert detail["cost_status"] == "PRICE_UNAVAILABLE" and detail["monthly_total_toman"] is None
    r = client.patch(f"/api/v1/servers/{server['id']}", headers=auth, json={"download_gb_override": "10", "upload_gb_override": "5"})
    assert D(r.json()["monthly_total_toman"]) == D(795000)
    assert r.json()["cost_status"] == "EXACT"
    detail = client.get(f"/api/v1/servers/{server['id']}", headers=auth).json()
    assert "you entered" in detail["breakdown"]["assumptions"][0]
    totals = client.get("/api/v1/servers", headers=auth).json()["summary"]
    assert D(totals["monthly_total_toman"]) >= D(795000) and totals["exact_priced"] >= 1


def test_unknown_plan_is_refused(client, auth, server):
    r = client.patch(f"/api/v1/servers/{server['id']}", headers=auth, json={"provider_id": "mobinhost", "sku": "NOPE"})
    assert r.status_code == 422


def test_usage_reaches_rightsizing_evidence(client, auth, server, api_env):
    from finops_api.db import SessionLocal
    from finops_api.fleet_service import refresh_usage
    from finops_api.orm import Server, ServerSample

    now = datetime.now(UTC)
    with SessionLocal() as db:
        s = db.get(Server, server["id"])
        for day in range(0, 20):
            db.add(ServerSample(server_id=s.id, taken_at=now - timedelta(days=20 - day), cpu_total=day * 1000, cpu_idle=day * 950,
                                mem_total_kb=3_900_000, mem_available_kb=3_500_000, disk_total_kb=39_000_000,
                                disk_used_kb=5_000_000, rx_bytes=day * 10 ** 8, tx_bytes=day * 10 ** 8))
        db.flush()
        refresh_usage(db, s, now)
        db.commit()
        assert s.usage["observation_days"] >= 14
        assert D(s.usage["p95_cpu_percent"]) == D("5.00")
    client.patch(f"/api/v1/servers/{server['id']}", headers=auth, json={"provider_id": "mobinhost", "sku": "IR-VPS-4GB"})
    detail = client.get(f"/api/v1/servers/{server['id']}", headers=auth).json()
    assert detail["cost_status"] == "EXACT"
    assert not [r for r in detail["recommendations"] if r["status"] == "cannot_determine" and r["evidence"].get("blocked_rule") == "REC-002"]


def test_failure_is_visible_and_recoverable(client, auth, server, ssh):
    ssh["error"] = SshError("cannot reach")
    r = client.post(f"/api/v1/servers/{server['id']}/check", headers=auth).json()
    assert r["status"] == "unreachable" and "cannot reach" in r["last_error"]
    ssh["error"] = None
    assert client.post(f"/api/v1/servers/{server['id']}/check", headers=auth).json()["status"] == "online"


def test_changed_identity_stops_until_an_admin_trusts_it(client, auth, server, ssh):
    client.post(f"/api/v1/servers/{server['id']}/check", headers=auth)
    assert ssh["seen_known"][-1] == "ssh-ed25519 HOSTKEY"
    ssh["error"] = HostKeyChanged("changed")
    assert client.post(f"/api/v1/servers/{server['id']}/check", headers=auth).json()["status"] == "host_key_changed"
    ssh["error"] = None
    r = client.post(f"/api/v1/servers/{server['id']}/trust-new-identity", headers=auth).json()
    assert r["status"] == "online" and ssh["seen_known"][-1] is None


def test_enroll_command_has_no_private_key(client, auth, api_env):
    r = client.get("/api/v1/servers/enroll-command", headers=auth).json()
    assert r["public_key"].startswith("ssh-ed25519 ")
    assert "PRIVATE" not in r["command"] and "PRIVATE" not in r["public_key"]
    from finops_api.db import SessionLocal
    from finops_api.orm import FleetKey

    with SessionLocal() as db:
        assert all("PRIVATE KEY" not in k.private_key_encrypted for k in db.query(FleetKey))


def test_servers_are_isolated_between_organizations(client, auth, server):
    r = client.post("/api/v1/auth/register", json={"email": "iso@example.ir", "password": "iso-password-12", "organization_name": "Iso"})
    other = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"/api/v1/servers/{server['id']}", headers=other).status_code == 404
    assert client.post(f"/api/v1/servers/{server['id']}/check", headers=other).status_code == 404
    assert client.delete(f"/api/v1/servers/{server['id']}", headers=other).status_code == 404
    assert client.get("/api/v1/servers", headers=other).json()["servers"] == []


def test_viewers_can_read_but_not_change(client, server, ssh):
    h = viewer(client)
    assert client.get("/api/v1/servers", headers=h).status_code == 200
    assert client.post("/api/v1/servers", headers=h, json={"name": "x", "host": "1.1.1.1"}).status_code == 403
    assert client.get("/api/v1/servers/enroll-command", headers=h).status_code == 403
    assert client.delete(f"/api/v1/servers/{server['id']}", headers=h).status_code == 403


def test_inventory_from_servers_still_needs_confirming(client, auth, server):
    client.patch(f"/api/v1/servers/{server['id']}", headers=auth, json={"provider_id": "mobinhost", "sku": "IR-VPS-4GB", "download_gb_override": "1", "upload_gb_override": "1"})
    r = client.post("/api/v1/servers/inventory", headers=auth)
    assert r.status_code == 200, r.text
    inv = client.get(f"/api/v1/inventories/{r.json()['id']}", headers=auth).json()
    assert inv["status"] == "needs_confirmation" and inv["resources"]
    assert client.post(f"/api/v1/inventories/{inv['id']}/quote", headers=auth, json={"include_tax": False}).status_code == 409


def test_purge_keeps_recent_samples(server, api_env):
    from finops_api.db import SessionLocal
    from finops_api.fleet_service import purge_samples
    from finops_api.orm import ServerSample

    old = datetime.now(UTC) - timedelta(days=200)
    with SessionLocal() as db:
        db.add(ServerSample(server_id=server["id"], taken_at=old, cpu_total=1, cpu_idle=1, mem_total_kb=1, mem_available_kb=1,
                            disk_total_kb=1, disk_used_kb=1, rx_bytes=1, tx_bytes=1))
        db.commit()
        assert purge_samples(db) >= 1
        assert db.query(ServerSample).filter(ServerSample.server_id == server["id"]).count() >= 1


def test_renewal_alert_days(server, client, auth, monkeypatch):
    from finops_api import alerts
    from finops_api.db import SessionLocal

    sent = []
    monkeypatch.setattr(alerts, "notify", lambda s, b: sent.append(s))
    due = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
    client.patch(f"/api/v1/servers/{server['id']}", headers=auth, json={"renewal_date": due})
    with SessionLocal() as db:
        alerts.renewal_alerts(db)
    assert any("Renewal in 3" in s for s in sent)


def test_component_priced_provider_needs_class_and_disk_type(client, auth, server):
    r = client.patch(f"/api/v1/servers/{server['id']}", headers=auth, json={"provider_id": "arvancloud", "sku": None,
                     "download_gb_override": "10", "upload_gb_override": "5"})
    assert r.json()["cost_status"] == "PRICE_UNAVAILABLE"
    rows = client.get("/api/v1/catalog?provider_id=arvancloud", headers=auth).json()
    cls = next(i["resource_class"] for i in rows if i["service_type"] == "compute_component")
    storage = next(i["storage_type"] for i in rows if i["service_type"] == "storage_component")
    r = client.patch(f"/api/v1/servers/{server['id']}", headers=auth, json={"resource_class": cls, "storage_type": storage})
    assert r.json()["cost_status"] == "EXACT", r.text
    assert D(r.json()["monthly_total_toman"]) > 0
