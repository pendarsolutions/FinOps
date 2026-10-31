"""Integrations: price adapter status."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from provider_adapters import ADAPTERS, SECOND_WAVE_STATUS

from ..db import get_db
from ..orm import ProviderRow
from ..security import Principal, current_principal

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


@router.get("")
def integrations(db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    return {
        "price_adapters": [{"provider_id": pid, "status": "live_parser" if pid in ADAPTERS else "seed_only",
                            "note": SECOND_WAVE_STATUS.get(pid)} for pid in
                           [r.id for r in db.scalars(select(ProviderRow))]],
    }
