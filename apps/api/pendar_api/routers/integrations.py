"""Integrations: adapter status and (reserved) read-only provider credentials, encrypted at rest."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from provider_adapters import ADAPTERS, SECOND_WAVE_STATUS

from ..db import get_db
from ..orm import ProviderCredential, ProviderRow
from ..platform import encrypt_secret
from ..security import Principal, audit, current_principal, require

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


class CredentialIn(BaseModel):
    provider_id: str
    label: str = Field(min_length=1, max_length=200)
    secret: str = Field(min_length=8, max_length=4000)
    read_only: bool = True


@router.get("")
def integrations(db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    creds = db.scalars(select(ProviderCredential).where(ProviderCredential.organization_id == p.org.id))
    return {
        "price_adapters": [{"provider_id": pid, "status": "live_parser" if pid in ADAPTERS else "seed_only",
                            "note": SECOND_WAVE_STATUS.get(pid)} for pid in
                           [r.id for r in db.scalars(select(ProviderRow))]],
        "inventory_connectors": {"status": "reserved", "note": "Read-only account connectors are post-MVP. "
                                 "Credentials stored here are encrypted and are not used yet."},
        "credentials": [{"id": c.id, "provider_id": c.provider_id, "label": c.label, "read_only": c.read_only,
                         "secret_hint": c.secret_hint, "created_at": c.created_at} for c in creds],
    }


@router.post("/credentials")
def add_credential(body: CredentialIn, db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    if db.get(ProviderRow, body.provider_id) is None:
        raise HTTPException(404, "unknown provider")
    if not body.read_only:
        raise HTTPException(422, "only read-only credentials are accepted")
    c = ProviderCredential(organization_id=p.org.id, provider_id=body.provider_id, label=body.label, read_only=True,
                           secret_encrypted=encrypt_secret(body.secret), secret_hint="…" + body.secret[-4:])
    db.add(c)
    audit(db, p, "integration.credential.add", "provider_credential", None, {"provider_id": body.provider_id,
                                                                            "label": body.label})
    db.commit()
    return {"id": c.id, "provider_id": c.provider_id, "label": c.label, "secret_hint": c.secret_hint}


@router.delete("/credentials/{cred_id}")
def delete_credential(cred_id: str, db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    c = db.get(ProviderCredential, cred_id)
    if c is None or c.organization_id != p.org.id:
        raise HTTPException(404, "credential not found")
    db.delete(c)
    audit(db, p, "integration.credential.delete", "provider_credential", cred_id)
    db.commit()
    return {"deleted": cred_id}
