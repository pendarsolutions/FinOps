from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from provider_adapters import ADAPTERS, SECOND_WAVE_STATUS

from ..catalog_store import approve_quarantined, row_to_item, run_provider_sync
from ..config import get_settings
from ..db import get_db
from ..orm import CatalogItemVersion, PriceSyncRun, ProviderRow
from ..security import Principal, audit, current_principal, require
from ..services import snapshot

router = APIRouter(prefix="/api/v1", tags=["catalog"])


def _item_view(row: CatalogItemVersion) -> dict[str, Any]:
    item = row_to_item(row)
    data = item.model_dump(mode="json")
    data["exact_eligible"] = item.pricing_model in ("component_rate", "tiered_meter", "fixed_sku",
                                                    "fixed_sku_hourly_monthly", "fixed_sku_flexible_period")
    return data


def _last_runs(db: Session) -> dict[str, PriceSyncRun]:
    out: dict[str, PriceSyncRun] = {}
    for run in db.scalars(select(PriceSyncRun).order_by(PriceSyncRun.started_at.desc())):
        out.setdefault(run.provider_id, run)
    return out


def run_view(r: PriceSyncRun) -> dict[str, Any]:
    return {"id": r.id, "provider_id": r.provider_id, "status": r.status, "started_at": r.started_at,
            "finished_at": r.finished_at, "items_seen": r.items_seen, "items_changed": r.items_changed,
            "error": r.error, "warnings": r.warnings, "summary": r.summary, "triggered_by": r.triggered_by,
            "has_pending_items": bool(r.pending_items)}


@router.get("/providers")
def list_providers(db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    snap = snapshot(db)
    freshness = snap.source_freshness()
    runs = _last_runs(db)
    out = []
    for p in db.scalars(select(ProviderRow)):
        pol = snap.provider_policy(p.id) or {}
        out.append({
            "id": p.id, "name_en": p.name_en, "name_fa": p.name_fa, "website": p.website,
            "official_pricing_url": p.official_pricing_url, "pricing_model": p.pricing_model,
            "integration_status": p.api_status, "catalog_quality": p.public_catalog_quality, "metadata": p.meta,
            "engine_strategy": pol.get("strategy"), "exact_eligible": pol.get("exact_eligible"),
            "adapter": "live_parser" if p.id in ADAPTERS else "seed_only",
            "adapter_note": SECOND_WAVE_STATUS.get(p.id),
            "catalog_items": len(snap.provider_items(p.id)),
            "sources": [f for f in freshness if f["provider_id"] == p.id],
            "last_sync": run_view(runs[p.id]) if p.id in runs else None,
        })
    out.sort(key=lambda x: x["metadata"].get("recommended_mvp_priority") or 99)
    return out


@router.get("/catalog")
def list_catalog(provider_id: str | None = None, service_type: str | None = None, q: str | None = None,
                 include_unavailable: bool = True, db: Session = Depends(get_db),
                 _: Principal = Depends(current_principal)):
    stmt = select(CatalogItemVersion).where(CatalogItemVersion.valid_to.is_(None))
    if provider_id:
        stmt = stmt.where(CatalogItemVersion.provider_id == provider_id)
    if service_type:
        stmt = stmt.where(CatalogItemVersion.service_type == service_type)
    rows = list(db.scalars(stmt))
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in (r.sku or "").lower() or ql in r.name.lower()]
    if not include_unavailable:
        rows = [r for r in rows if r.availability == "available"]
    versions: dict[str, int] = {}
    for item_id, in db.execute(select(CatalogItemVersion.item_id)):
        versions[item_id] = versions.get(item_id, 0) + 1
    out = []
    for r in sorted(rows, key=lambda r: (r.provider_id, r.service_type, r.sku or "", str(r.tier_min or ""))):
        v = _item_view(r)
        v["version_count"] = versions.get(r.item_id, 1)
        out.append(v)
    return out


@router.get("/catalog/freshness")
def catalog_freshness(db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    snap = snapshot(db)
    return {"catalog_version": snap.catalog_version, "policy_version": snap.policy_version,
            "sources": snap.source_freshness()}


@router.get("/catalog/{item_id}")
def get_catalog_item(item_id: str, db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    row = db.scalar(select(CatalogItemVersion).where(CatalogItemVersion.item_id == item_id,
                                                     CatalogItemVersion.valid_to.is_(None)))
    if row is None:
        raise HTTPException(404, "catalog item not found or no current version")
    return _item_view(row)


@router.get("/catalog/{item_id}/history")
def get_catalog_history(item_id: str, db: Session = Depends(get_db), _: Principal = Depends(current_principal)):
    rows = list(db.scalars(select(CatalogItemVersion).where(CatalogItemVersion.item_id == item_id)
                           .order_by(CatalogItemVersion.valid_from)))
    if not rows:
        raise HTTPException(404, "catalog item not found")
    return [_item_view(r) | {"source_id": r.source_id, "created_at": r.created_at} for r in rows]


# --------------------------------------------------------------------------- admin sync


@router.post("/admin/providers/{provider_id}/sync")
def trigger_sync(provider_id: str, db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    if db.get(ProviderRow, provider_id) is None:
        raise HTTPException(404, "unknown provider")
    if get_settings().sync_mode == "celery":
        from finops_worker.tasks import sync_provider

        task = sync_provider.delay(provider_id, f"user:{p.user.id}")
        audit(db, p, "catalog.sync.enqueue", "provider", provider_id, {"task_id": task.id})
        db.commit()
        return {"queued": True, "task_id": task.id}
    run = run_provider_sync(db, provider_id, triggered_by=f"user:{p.user.id}")
    audit(db, p, "catalog.sync", "provider", provider_id, {"run_id": run.id, "status": run.status})
    db.commit()
    return run_view(run)


@router.get("/admin/sync-runs")
def list_sync_runs(limit: int = Query(50, le=500), db: Session = Depends(get_db),
                   _: Principal = Depends(current_principal)):
    runs = db.scalars(select(PriceSyncRun).order_by(PriceSyncRun.started_at.desc()).limit(limit))
    return [run_view(r) for r in runs]


@router.post("/admin/sync-runs/{run_id}/approve")
def approve_run(run_id: str, db: Session = Depends(get_db), p: Principal = Depends(require("admin"))):
    run = db.get(PriceSyncRun, run_id)
    if run is None:
        raise HTTPException(404, "sync run not found")
    try:
        approve_quarantined(db, run, reviewer=p.user.email)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    audit(db, p, "catalog.sync.approve", "price_sync_run", run.id, {"provider_id": run.provider_id})
    db.commit()
    return run_view(run)
