"""Auth: PBKDF2 password hashing, JWT bearer tokens, org-scoped roles.

Bearer tokens are sent in the Authorization header (never cookies), so cross-site request forgery
does not apply to the API; the SPA stores the token in memory/sessionStorage.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .orm import AuditLog, Membership, Organization, User

ROLES = ("viewer", "analyst", "admin", "owner")
PBKDF2_ITERATIONS = 390_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, dk_b64 = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt_b64), int(iters))
    return hmac.compare_digest(dk, base64.b64decode(dk_b64))


def issue_token(user_id: str, org_id: str) -> str:
    s = get_settings()
    payload = {"sub": user_id, "org": org_id, "exp": datetime.now(UTC) + timedelta(minutes=s.jwt_ttl_minutes),
               "iat": datetime.now(UTC)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


@dataclass
class Principal:
    user: User
    org: Organization
    role: str

    def can(self, minimum: str) -> bool:
        return ROLES.index(self.role) >= ROLES.index(minimum)


def current_principal(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        payload = jwt.decode(authorization[7:], get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    m = db.scalar(select(Membership).where(Membership.user_id == payload["sub"],
                                           Membership.organization_id == payload["org"]))
    if m is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a member of this organization")
    return Principal(user=db.get(User, m.user_id), org=db.get(Organization, m.organization_id), role=m.role)


def require(minimum: str):
    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if not p.can(minimum):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role >= {minimum}")
        return p

    return dep


def audit(db: Session, p: Principal | None, action: str, entity_type: str, entity_id: str | None,
          detail: dict[str, Any] | None = None) -> None:
    db.add(AuditLog(organization_id=p.org.id if p else None, user_id=p.user.id if p else None, action=action,
                    entity_type=entity_type, entity_id=entity_id, detail=detail or {}))


def create_user_with_org(db: Session, email: str, password: str, name: str, org_name: str,
                         role: str = "owner") -> tuple[User, Organization]:
    user = User(email=email.lower().strip(), password_hash=hash_password(password), name=name)
    org = Organization(name=org_name, settings={})
    db.add_all([user, org])
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=org.id, role=role))
    db.flush()
    return user, org
