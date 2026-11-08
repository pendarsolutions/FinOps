"""Accounts a self-hosted team can run on its own: member roles, removal, and getting back in without help."""

import argparse
import re
from datetime import UTC, datetime, timedelta

import pytest


def _login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _add(client, auth, email, role="analyst", password="member-password-1"):
    r = client.post("/api/v1/members", headers=auth, json={"email": email, "password": password, "role": role})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _member_session(client, auth, email, role="analyst", password="member-password-1"):
    uid = _add(client, auth, email, role, password)
    r = _login(client, email, password)
    assert r.status_code == 200, r.text
    return uid, _bearer(r.json()["access_token"])


# --------------------------------------------------------------------------- roles


def test_owner_changes_a_members_role(client, auth):
    uid = _add(client, auth, "role-a@example.ir", "viewer")
    r = client.patch(f"/api/v1/members/{uid}", headers=auth, json={"role": "admin"})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert _login(client, "role-a@example.ir", "member-password-1").json()["role"] == "admin"


def test_admins_manage_only_members_below_them(client, auth):
    me = client.get("/api/v1/auth/me", headers=auth).json()["user"]["id"]
    _, admin = _member_session(client, auth, "role-admin@example.ir", "admin")
    other_admin = _add(client, auth, "role-admin2@example.ir", "admin")
    viewer = _add(client, auth, "role-viewer@example.ir", "viewer")
    assert client.patch(f"/api/v1/members/{viewer}", headers=admin, json={"role": "analyst"}).status_code == 200
    assert client.patch(f"/api/v1/members/{other_admin}", headers=admin, json={"role": "viewer"}).status_code == 403
    assert client.patch(f"/api/v1/members/{me}", headers=admin, json={"role": "viewer"}).status_code == 403
    assert client.delete(f"/api/v1/members/{me}", headers=admin).status_code == 403
    assert client.patch(f"/api/v1/members/{viewer}", headers=admin, json={"role": "owner"}).status_code == 422


def test_nobody_changes_their_own_membership(client, auth):
    me = client.get("/api/v1/auth/me", headers=auth).json()["user"]["id"]
    assert client.patch(f"/api/v1/members/{me}", headers=auth, json={"role": "viewer"}).status_code == 400
    assert client.delete(f"/api/v1/members/{me}", headers=auth).status_code == 400


def test_analysts_cannot_manage_members(client, auth):
    _, analyst = _member_session(client, auth, "role-analyst@example.ir", "analyst")
    viewer = _add(client, auth, "role-viewer2@example.ir", "viewer")
    assert client.delete(f"/api/v1/members/{viewer}", headers=analyst).status_code == 403


# --------------------------------------------------------------------------- removal


def test_removed_member_loses_access_at_once_and_can_be_added_back(client, auth):
    uid, member = _member_session(client, auth, "leaver@example.ir")
    assert client.get("/api/v1/auth/me", headers=member).status_code == 200
    assert client.delete(f"/api/v1/members/{uid}", headers=auth).status_code == 200
    assert client.get("/api/v1/auth/me", headers=member).status_code == 403
    assert _login(client, "leaver@example.ir", "member-password-1").status_code == 403
    assert not any(m["id"] == uid for m in client.get("/api/v1/members", headers=auth).json())
    # added back with a new password: the old one no longer works
    _add(client, auth, "leaver@example.ir", "viewer", password="returning-password-1")
    assert _login(client, "leaver@example.ir", "member-password-1").status_code == 401
    assert _login(client, "leaver@example.ir", "returning-password-1").json()["role"] == "viewer"


def test_someone_elses_account_cannot_be_taken_over_by_adding_it(client, auth):
    from finops_api.db import SessionLocal
    from finops_api.security import create_user_with_org

    with SessionLocal() as db:
        create_user_with_org(db, "elsewhere@example.ir", "their-password-1", "", "Other company")
        db.commit()
    r = client.post("/api/v1/members", headers=auth, json={"email": "elsewhere@example.ir",
                                                           "password": "attacker-password-1", "role": "viewer"})
    assert r.status_code == 409
    assert _login(client, "elsewhere@example.ir", "their-password-1").status_code == 200


# --------------------------------------------------------------------------- passwords


def test_admin_sets_a_temporary_password_and_old_sessions_end(client, auth):
    uid, old_session = _member_session(client, auth, "forgetful@example.ir")
    r = client.post(f"/api/v1/members/{uid}/password", headers=auth, json={"password": "temporary-password-1"})
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/auth/me", headers=old_session).status_code == 401
    assert _login(client, "forgetful@example.ir", "member-password-1").status_code == 401
    assert _login(client, "forgetful@example.ir", "temporary-password-1").status_code == 200


def test_admin_cannot_reset_the_password_of_someone_in_another_organization(client, auth):
    from sqlalchemy import select

    from finops_api.db import SessionLocal
    from finops_api.orm import Membership, Organization, User

    uid = _add(client, auth, "two-hats@example.ir", "viewer")
    with SessionLocal() as db:
        other = Organization(name="Second company", settings={})
        db.add(other)
        db.flush()
        user = db.scalar(select(User).where(User.id == uid))
        db.add(Membership(user_id=user.id, organization_id=other.id, role="owner"))
        db.commit()
    r = client.post(f"/api/v1/members/{uid}/password", headers=auth, json={"password": "takeover-password-1"})
    assert r.status_code == 409
    assert _login(client, "two-hats@example.ir", "member-password-1").status_code == 200


def test_changing_your_password_ends_other_sessions_and_keeps_this_one(client, auth):
    _, first = _member_session(client, auth, "changer@example.ir")
    wrong = client.post("/api/v1/auth/change-password", headers=first,
                        json={"current_password": "not-it-at-all", "new_password": "changed-password-1"})
    assert wrong.status_code == 400
    r = client.post("/api/v1/auth/change-password", headers=first,
                    json={"current_password": "member-password-1", "new_password": "changed-password-1"})
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/auth/me", headers=first).status_code == 401
    assert client.get("/api/v1/auth/me", headers=_bearer(r.json()["access_token"])).status_code == 200
    assert _login(client, "changer@example.ir", "changed-password-1").status_code == 200


@pytest.fixture
def outbox(monkeypatch):
    from finops_api.config import get_settings
    from finops_api.routers import auth as auth_router

    sent = []
    monkeypatch.setattr(get_settings(), "public_url", "https://finops.example.ir/")
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.example.ir")
    monkeypatch.setattr(auth_router, "send_email", lambda to, subject, body: sent.append((to, subject, body)))
    return sent


def _token_from(body):
    m = re.search(r"https://finops\.example\.ir/reset-password#token=(\S+)", body)
    assert m, body
    return m.group(1)


def test_forgotten_password_is_reset_by_an_emailed_link_that_works_once(client, auth, outbox):
    _add(client, auth, "lost@example.ir")
    assert client.get("/api/v1/auth/status").json()["password_reset_email"] is True
    assert client.post("/api/v1/auth/forgot-password", json={"email": "Lost@Example.ir"}).json() == {"status": "ok"}
    assert len(outbox) == 1 and outbox[0][0] == "lost@example.ir"
    token = _token_from(outbox[0][2])
    r = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "recovered-password-1"})
    assert r.status_code == 200, r.text
    assert _login(client, "lost@example.ir", "recovered-password-1").status_code == 200
    again = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "second-try-password"})
    assert again.status_code == 400


def test_unknown_addresses_get_the_same_answer_and_no_email(client, outbox):
    r = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.ir"})
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert outbox == []


def test_expired_reset_links_are_refused(client, auth, outbox):
    from sqlalchemy import select

    from finops_api.db import SessionLocal
    from finops_api.orm import User

    _add(client, auth, "slow@example.ir")
    client.post("/api/v1/auth/forgot-password", json={"email": "slow@example.ir"})
    token = _token_from(outbox[-1][2])
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "slow@example.ir"))
        user.reset_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    r = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "too-late-password-1"})
    assert r.status_code == 400


def test_without_email_set_up_nothing_is_sent(client, auth, monkeypatch):
    from finops_api.config import get_settings
    from finops_api.routers import auth as auth_router

    sent = []
    monkeypatch.setattr(get_settings(), "public_url", None)
    monkeypatch.setattr(auth_router, "send_email", lambda *a: sent.append(a))
    _add(client, auth, "no-mail@example.ir")
    assert client.get("/api/v1/auth/status").json()["password_reset_email"] is False
    assert client.post("/api/v1/auth/forgot-password", json={"email": "no-mail@example.ir"}).status_code == 200
    assert sent == []


def test_server_command_resets_a_password(client, auth, capsys):
    from finops_api.cli import cmd_reset_password

    _, old_session = _member_session(client, auth, "locked-out@example.ir")
    cmd_reset_password(argparse.Namespace(email="Locked-Out@example.ir", password_stdin=False))
    printed = capsys.readouterr().out
    password = re.search(r"new password for locked-out@example\.ir: (\S+)", printed).group(1)
    assert len(password) >= 10
    assert client.get("/api/v1/auth/me", headers=old_session).status_code == 401
    assert _login(client, "locked-out@example.ir", password).status_code == 200
