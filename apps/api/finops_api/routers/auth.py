from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..alerts import email_configured, send_email
from ..config import get_settings
from ..db import get_db
from ..orm import AuditLog, CatalogItemVersion, Membership, Organization, User
from ..platform import limiter
from ..security import (
    ROLES,
    Principal,
    audit,
    create_user_with_org,
    current_principal,
    hash_password,
    issue_token,
    outranks,
    require,
    set_password,
    verify_password,
)

router = APIRouter(tags=["auth"])
log = logging.getLogger("finops.auth")


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=10, max_length=200)
    name: str = ""
    organization_name: str = Field(min_length=1, max_length=200)


class LoginIn(BaseModel):
    email: str
    password: str
    organization_id: str | None = None


def _session(user: User, org: Organization, role: str) -> dict[str, Any]:
    return {"access_token": issue_token(user.id, org.id, user.session_version or 0), "token_type": "bearer",
            "user": {"id": user.id, "email": user.email, "name": user.name, "locale": user.locale},
            "organization": {"id": org.id, "name": org.name}, "role": role}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _registration_open(db: Session) -> bool:
    return get_settings().allow_registration or db.scalar(select(User.id).limit(1)) is None


def _reset_by_email() -> bool:
    """People can reset their own password only when email works and links can point at a known address."""
    return bool(get_settings().public_url) and email_configured()


@router.get("/api/v1/auth/status")
def auth_status(db: Session = Depends(get_db)):
    """Public: lets the sign-in page show only what applies to this installation."""
    return {"registration_open": _registration_open(db), "demo_user": get_settings().env == "dev",
            "password_reset_email": _reset_by_email()}


@router.post("/api/v1/auth/register")
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    limiter().check(f"register:{_client_ip(request)}", get_settings().login_rate_limit_per_minute)
    if not _registration_open(db):
        raise HTTPException(403, "registration is closed; ask an admin to add you")
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "email already registered")
    user, org = create_user_with_org(db, body.email, body.password, body.name, body.organization_name)
    db.add(AuditLog(organization_id=org.id, user_id=user.id, action="auth.register", entity_type="user",
                    entity_id=user.id))
    db.commit()
    return _session(user, org, "owner")


@router.post("/api/v1/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    limit = get_settings().login_rate_limit_per_minute
    limiter().check(f"login:{_client_ip(request)}:{body.email.lower().strip()}", limit)
    # across all addresses too, so a rotating or spoofed client address can't get around the limit
    limiter().check(f"login-any:{body.email.lower().strip()}", limit * 5)
    user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "invalid email or password")
    q = select(Membership).where(Membership.user_id == user.id)
    if body.organization_id:
        q = q.where(Membership.organization_id == body.organization_id)
    m = db.scalar(q)
    if m is None:
        raise HTTPException(403, "no organization membership")
    return _session(user, db.get(Organization, m.organization_id), m.role)


# --------------------------------------------------------------------------- passwords


class ForgotIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(min_length=10, max_length=200)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=10, max_length=200)


RESET_EMAIL = {
    "fa": ("بازنشانی رمز عبور FinOps agent",
           "برای انتخاب رمز تازه، این پیوند را باز کنید. پیوند فقط یک بار و تا {minutes} دقیقه کار می‌کند.\n\n{link}\n\n"
           "اگر شما این را نخواسته‌اید، این پیام را نادیده بگیرید؛ رمز فعلی‌تان تغییری نمی‌کند."),
    "en": ("Reset your FinOps agent password",
           "Open this link to choose a new password. It works once, for {minutes} minutes.\n\n{link}\n\n"
           "If you didn't ask for this, ignore this email; your password stays the same."),
}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _deliver_reset(to: str, subject: str, body: str) -> None:
    try:
        send_email(to, subject, body)
    except Exception as exc:  # noqa: BLE001 - the person sees the same answer either way
        log.error(json.dumps({"password_reset_email_failed": type(exc).__name__}))


@router.post("/api/v1/auth/forgot-password")
def forgot_password(body: ForgotIn, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Emails a one-time link. Always answers the same way, and sends in the background, so the reply never
    tells whether an address has an account."""
    s = get_settings()
    email = body.email.lower().strip()
    limiter().check(f"forgot:{_client_ip(request)}", s.login_rate_limit_per_minute)
    limiter().check(f"forgot-any:{email}", 3)
    user = db.scalar(select(User).where(User.email == email)) if _reset_by_email() else None
    if user is not None and db.scalar(select(Membership.id).where(Membership.user_id == user.id).limit(1)):
        token = secrets.token_urlsafe(32)
        user.reset_token_hash = _token_hash(token)
        user.reset_expires_at = datetime.now(UTC) + timedelta(minutes=s.password_reset_minutes)
        db.add(AuditLog(user_id=user.id, action="auth.reset_requested", entity_type="user", entity_id=user.id,
                        detail={}))
        db.commit()
        lang = "fa" if user.locale == "fa" else "en"
        subject, text_ = RESET_EMAIL[lang]
        minutes = str(s.password_reset_minutes)
        if lang == "fa":
            minutes = minutes.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
        # the token travels in the fragment, which browsers never send to a server or put in a Referer
        link = f"{s.public_url.rstrip('/')}/reset-password#token={token}"
        background.add_task(_deliver_reset, user.email, subject, text_.format(minutes=minutes, link=link))
    return {"status": "ok"}


@router.post("/api/v1/auth/reset-password")
def reset_password(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    limiter().check(f"reset:{_client_ip(request)}", get_settings().login_rate_limit_per_minute)
    user = db.scalar(select(User).where(User.reset_token_hash == _token_hash(body.token)))
    expires = user.reset_expires_at if user else None
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if user is None or expires is None or expires < datetime.now(UTC):
        raise HTTPException(400, "this reset link has expired or was already used")
    set_password(user, body.password)
    db.add(AuditLog(user_id=user.id, action="auth.password_reset", entity_type="user", entity_id=user.id,
                    detail={}))
    db.commit()
    return {"status": "ok"}


@router.post("/api/v1/auth/change-password")
def change_password(body: ChangePasswordIn, db: Session = Depends(get_db),
                    p: Principal = Depends(current_principal)):
    """Ends every other session too; the reply carries a fresh one for this browser."""
    limiter().check(f"change-password:{p.user.id}", get_settings().login_rate_limit_per_minute)
    user = db.get(User, p.user.id)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "the current password is wrong")
    set_password(user, body.new_password)
    audit(db, p, "auth.password_change", "user", user.id)
    db.commit()
    return _session(user, p.org, p.role)


@router.get("/api/v1/auth/me")
def me(p: Principal = Depends(current_principal)):
    return {"user": {"id": p.user.id, "email": p.user.email, "name": p.user.name, "locale": p.user.locale},
            "organization": {"id": p.org.id, "name": p.org.name, "settings": p.org.settings}, "role": p.role}


# --------------------------------------------------------------------------- members


class MemberIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=10, max_length=200)
    name: str = ""
    role: Literal["viewer", "analyst", "admin"] = "viewer"


@router.get("/api/v1/members")
def list_members(db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    rows = db.execute(select(User, Membership.role).join(Membership, Membership.user_id == User.id)
                      .where(Membership.organization_id == p.org.id).order_by(User.email))
    return [{"id": u.id, "email": u.email, "name": u.name, "role": role} for u, role in rows]


@router.post("/api/v1/members")
def add_member(body: MemberIn, db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    email = body.email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        # someone removed earlier can be added back; anyone still in an organization is someone else's account
        if db.scalar(select(Membership.id).where(Membership.user_id == user.id).limit(1)):
            raise HTTPException(409, "email already registered")
        set_password(user, body.password)
        user.name = body.name or user.name
    else:
        user = User(email=email, password_hash=hash_password(body.password), name=body.name)
        db.add(user)
        db.flush()
    db.add(Membership(user_id=user.id, organization_id=p.org.id, role=body.role))
    audit(db, p, "member.add", "user", user.id, {"role": body.role})
    db.commit()
    return {"id": user.id, "email": user.email, "name": user.name, "role": body.role}


class MemberRoleIn(BaseModel):
    role: Literal["viewer", "analyst", "admin"]


class MemberPasswordIn(BaseModel):
    password: str = Field(min_length=10, max_length=200)


def _managed_membership(db: Session, p: Principal, user_id: str) -> Membership:
    """A membership the caller may change: someone else's, in this organization, with a lower role."""
    if user_id == p.user.id:
        raise HTTPException(400, "you can't change your own membership; ask another admin")
    m = db.scalar(select(Membership).where(Membership.user_id == user_id, Membership.organization_id == p.org.id))
    if m is None:
        raise HTTPException(404, "not a member of this organization")
    if not outranks(p.role, m.role):
        raise HTTPException(403, "you can only manage members whose role is below yours")
    return m


@router.patch("/api/v1/members/{user_id}")
def change_member_role(user_id: str, body: MemberRoleIn, db: Session = Depends(get_db),
                       p: Principal = Depends(require("admin"))):
    m = _managed_membership(db, p, user_id)
    if ROLES.index(body.role) > ROLES.index(p.role):
        raise HTTPException(403, "you can't give a role above your own")
    old, m.role = m.role, body.role
    audit(db, p, "member.role", "user", user_id, {"from": old, "to": body.role})
    db.commit()
    user = db.get(User, user_id)
    return {"id": user.id, "email": user.email, "name": user.name, "role": m.role}


@router.delete("/api/v1/members/{user_id}")
def remove_member(user_id: str, db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    """Their sign-in stops working here at once: every request checks membership. Their history stays."""
    m = _managed_membership(db, p, user_id)
    audit(db, p, "member.remove", "user", user_id, {"role": m.role})
    db.delete(m)
    db.commit()
    return {"status": "removed"}


@router.post("/api/v1/members/{user_id}/password")
def set_member_password(user_id: str, body: MemberPasswordIn, db: Session = Depends(get_db),
                        p: Principal = Depends(require("admin"))):
    """A temporary password from an admin, for installations without email. Ends the member's sessions."""
    _managed_membership(db, p, user_id)
    elsewhere = db.scalar(select(func.count()).select_from(Membership)
                          .where(Membership.user_id == user_id, Membership.organization_id != p.org.id))
    if elsewhere:
        raise HTTPException(409, "this person also belongs to another organization, so only they can change it")
    set_password(db.get(User, user_id), body.password)
    audit(db, p, "member.password_reset", "user", user_id)
    db.commit()
    return {"status": "ok"}


# --------------------------------------------------------------------------- org settings + audit


class SettingsIn(BaseModel):
    engineer_day_rate_toman: str | None = Field(default=None, pattern=r"^\d+(\.\d+)?$")
    default_language: str | None = Field(default=None, pattern=r"^(fa|en)$")


@router.get("/api/v1/settings")
def get_org_settings(p: Principal = Depends(current_principal)):
    return {"organization": {"id": p.org.id, "name": p.org.name}, "settings": p.org.settings or {}, "role": p.role}


@router.put("/api/v1/settings")
def put_org_settings(body: SettingsIn, db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    org = db.get(Organization, p.org.id)
    new = dict(org.settings or {})
    updates = body.model_dump(exclude_unset=True)
    if "engineer_day_rate_toman" in updates:
        new.pop("engineer_day_rate_label", None)  # a user-entered rate is no longer the demo SAMPLE value
    for k, v in updates.items():
        if v is None:
            new.pop(k, None)
        else:
            new[k] = v
    org.settings = new
    audit(db, p, "settings.update", "organization", org.id, body.model_dump(exclude_unset=True))
    db.commit()
    return {"settings": org.settings}


@router.get("/api/v1/audit-logs")
def audit_logs(limit: int = 100, db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    rows = db.scalars(select(AuditLog).where(AuditLog.organization_id == p.org.id)
                      .order_by(AuditLog.created_at.desc()).limit(min(limit, 500)))
    return [{"id": r.id, "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id,
             "user_id": r.user_id, "detail": r.detail, "created_at": r.created_at} for r in rows]


# --------------------------------------------------------------------------- health


@router.get("/health/live")
def live():
    return {"status": "ok"}


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    checks: dict[str, Any] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
        n = db.query(CatalogItemVersion).filter(CatalogItemVersion.valid_to.is_(None)).count()
        checks["catalog_items"] = n
        if n == 0:
            checks["catalog"] = "empty - run `make seed-pricing`"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {type(exc).__name__}"
    url = get_settings().redis_url
    if url:
        try:
            import redis

            redis.Redis.from_url(url, socket_timeout=2).ping()
            checks["redis"] = "ok"
        except Exception as exc:  # noqa: BLE001
            checks["redis"] = f"error: {type(exc).__name__}"
    ok = checks.get("database") == "ok" and checks.get("catalog_items", 0) > 0 and checks.get("redis", "ok") == "ok"
    if not ok:
        raise HTTPException(503, {"status": "not_ready", "checks": checks})
    return {"status": "ready", "checks": checks}
