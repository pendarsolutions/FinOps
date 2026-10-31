from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..orm import AuditLog, CatalogItemVersion, Membership, Organization, User
from ..security import Principal, audit, create_user_with_org, current_principal, issue_token, require, verify_password

router = APIRouter(tags=["auth"])


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
    return {"access_token": issue_token(user.id, org.id), "token_type": "bearer",
            "user": {"id": user.id, "email": user.email, "name": user.name, "locale": user.locale},
            "organization": {"id": org.id, "name": org.name}, "role": role}


@router.post("/api/v1/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "email already registered")
    user, org = create_user_with_org(db, body.email, body.password, body.name, body.organization_name)
    db.add(AuditLog(organization_id=org.id, user_id=user.id, action="auth.register", entity_type="user",
                    entity_id=user.id))
    db.commit()
    return _session(user, org, "owner")


@router.post("/api/v1/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
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


@router.get("/api/v1/auth/me")
def me(p: Principal = Depends(current_principal)):
    return {"user": {"id": p.user.id, "email": p.user.email, "name": p.user.name, "locale": p.user.locale},
            "organization": {"id": p.org.id, "name": p.org.name, "settings": p.org.settings}, "role": p.role}


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
