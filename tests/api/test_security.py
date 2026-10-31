"""Safe defaults a self-hosted installation inherits."""

import pytest


def test_registration_closes_after_first_user(client, auth, monkeypatch):
    from finops_api.config import get_settings

    monkeypatch.setattr(get_settings(), "allow_registration", False)
    assert client.get("/api/v1/auth/status").json()["registration_open"] is False
    r = client.post("/api/v1/auth/register", json={"email": "late@example.ir", "password": "late-password-1",
                                                   "organization_name": "Late"})
    assert r.status_code == 403


def test_login_is_rate_limited(client, monkeypatch):
    from finops_api.config import get_settings

    monkeypatch.setattr(get_settings(), "login_rate_limit_per_minute", 3)
    codes = [client.post("/api/v1/auth/login", json={"email": "brute@example.ir", "password": "x"}).status_code
             for _ in range(5)]
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]


def test_admin_adds_member_who_can_log_in(client, auth):
    r = client.post("/api/v1/members", headers=auth, json={"email": "new@example.ir", "password": "member-password-1",
                                                           "role": "analyst"})
    assert r.status_code == 200, r.text
    assert any(m["email"] == "new@example.ir" for m in client.get("/api/v1/members", headers=auth).json())
    login = client.post("/api/v1/auth/login", json={"email": "new@example.ir", "password": "member-password-1"})
    assert login.status_code == 200 and login.json()["role"] == "analyst"
    member = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/api/v1/members", headers=member).status_code == 403


def test_owner_role_cannot_be_granted_to_new_members(client, auth):
    r = client.post("/api/v1/members", headers=auth, json={"email": "o@example.ir", "password": "member-password-1",
                                                           "role": "owner"})
    assert r.status_code == 422


def test_prod_refuses_default_database_password(api_env, monkeypatch):
    from finops_api.config import get_settings

    monkeypatch.setenv("FINOPS_ENV", "prod")
    monkeypatch.setenv("FINOPS_JWT_SECRET", "x" * 40)
    monkeypatch.setenv("FINOPS_CREDENTIALS_KEY", "k")
    monkeypatch.setenv("FINOPS_DATABASE_URL", "postgresql+psycopg://finops:finops-dev-password@postgres/finops")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="POSTGRES_PASSWORD"):
            get_settings()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
