from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_gateway import LLMConfig, extract_inventory
from invoice_parser import extract_text, parse_invoice
from pricing_engine.catalog import load_json
from shared_types import ResourceDraft

from ..config import get_settings
from ..db import get_db
from ..orm import AIRun, Inventory, InventoryResource, Upload
from ..platform import limiter, redact, store_private, validate_upload, verify_download
from ..security import Principal, audit, current_principal, require
from ..services import (
    apply_draft,
    confirm_inventory,
    create_inventory,
    get_inventory,
    inventory_view,
    resources_of,
    row_to_draft,
    snapshot,
    unconfirm,
)

router = APIRouter(prefix="/api/v1", tags=["inventory"])


class InventoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    resources: list[ResourceDraft] = Field(default_factory=list)


class ChatIn(BaseModel):
    text: str = Field(min_length=3, max_length=8000)
    name: str = "Chat draft"


class ConfirmIn(BaseModel):
    confirm_all_rows: bool = False


def _sku_map(db: Session) -> dict[str, str]:
    return {i.sku: i.provider_id for i in snapshot(db).items if i.sku and i.service_type in
            ("compute_vm", "paas", "dbaas")}


def _llm_cfg() -> LLMConfig | None:
    s = get_settings()
    return LLMConfig(model=s.ai_model, api_key=s.anthropic_api_key) if s.ai_provider == "anthropic" else None


@router.get("/inventories")
def list_inventories(db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    rows = db.scalars(select(Inventory).where(Inventory.organization_id == p.org.id, Inventory.status != "archived")
                      .order_by(Inventory.created_at.desc()))
    return [{"id": i.id, "name": i.name, "status": i.status, "source_type": i.source_type, "created_at": i.created_at,
             "confirmed_at": i.confirmed_at} for i in rows]


@router.post("/inventories")
def create_from_builder(body: InventoryIn, db: Session = Depends(get_db), p: Principal = Depends(require("analyst"))):
    drafts = []
    for d in body.resources:
        d.field_confidence = {k: 1.0 for k in ResourceDraft.model_fields if getattr(d, k) is not None
                              and k not in ("field_confidence", "unknown_fields", "notes", "name")}
        drafts.append(d)
    inv = create_inventory(db, p, body.name, "builder", drafts)
    return inventory_view(db, inv, snapshot(db).policy)


@router.post("/inventories/demo")
def create_demo(db: Session = Depends(get_db), p: Principal = Depends(require("analyst"))):
    data = load_json(get_settings().seed_dir / "sample_inventory.json")
    drafts = [ResourceDraft(**{k: v for k, v in r.items()}) for r in data["resources"]]
    inv = create_inventory(db, p, data["name"], "builder", drafts, {"demo": True, "note": data["note"]})
    org_settings = dict(p.org.settings or {})
    if "engineer_day_rate_toman" not in org_settings:
        org_settings["engineer_day_rate_toman"] = data["organization_settings"]["engineer_day_rate_toman"]
        org_settings["engineer_day_rate_label"] = data["organization_settings"]["engineer_day_rate_label"]
        p.org.settings = org_settings
        db.commit()
    return inventory_view(db, inv, snapshot(db).policy)


@router.post("/inventories/from-chat")
def create_from_chat(body: ChatIn, db: Session = Depends(get_db), p: Principal = Depends(require("analyst"))):
    s = get_settings()
    limiter().check(f"ai:{p.user.id}", s.ai_rate_limit_per_minute)
    snap = snapshot(db)
    draft, meta = extract_inventory(body.text, provider=s.ai_provider, cfg=_llm_cfg(),
                                    providers=sorted(snap.providers), sku_map=_sku_map(db))
    inv = create_inventory(db, p, body.name, "chat", draft.resources,
                           {"questions": draft.questions, "extraction": meta,
                            "detected_currency": draft.detected_currency})
    db.add(AIRun(organization_id=p.org.id, user_id=p.user.id, purpose="chat_to_inventory",
                 model=meta.get("model", "offline-parser"), prompt_version=meta["prompt_version"],
                 input_redacted={"text": redact(body.text)}, tool_calls=[],
                 output_text=draft.model_dump_json(), guard_result={"path": meta["path"]}))
    db.commit()
    return inventory_view(db, inv, snap.policy)


@router.post("/inventories/from-invoice")
async def create_from_invoice(file: UploadFile = File(...), name: str = Form("Invoice draft"),
                              db: Session = Depends(get_db), p: Principal = Depends(require("analyst"))):
    s = get_settings()
    data = await file.read()
    kind = validate_upload(file.filename or "upload", file.content_type or "", data)
    try:
        text = extract_text(data, kind)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - malformed PDFs etc.
        raise HTTPException(422, f"could not read file: {type(exc).__name__}") from exc
    ext = parse_invoice(text, _sku_map(db))
    upload = Upload(organization_id=p.org.id, filename=file.filename or "upload", content_type=kind,
                    size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                    delete_after=datetime.now(UTC) + timedelta(days=s.invoice_retention_days))
    db.add(upload)
    db.flush()
    upload.storage_path = store_private(p.org.id, upload.id, data)
    inv = create_inventory(db, p, name, "invoice", ext.draft.resources,
                           {"questions": ext.draft.questions, "invoice": ext.meta(), "upload_id": upload.id})
    upload.inventory_id = inv.id
    if ext.currency_confirmation_required:
        inv.currency = "UNCONFIRMED"
    db.commit()
    return inventory_view(db, inv, snapshot(db).policy)


class CurrencyIn(BaseModel):
    currency: str = Field(pattern="^(TOMAN|RIAL)$")


@router.post("/inventories/{inventory_id}/currency")
def confirm_currency(inventory_id: str, body: CurrencyIn, db: Session = Depends(get_db),
                     p: Principal = Depends(require("analyst"))):
    inv = get_inventory(db, p, inventory_id)
    inv.source_meta = {**inv.source_meta, "invoice_currency_confirmed": body.currency}
    inv.currency = "TOMAN"  # catalog/accounting unit stays Toman; invoice evidence is interpreted with the confirmed unit
    audit(db, p, "inventory.currency_confirm", "inventory", inv.id, body.model_dump())
    db.commit()
    return inventory_view(db, inv, snapshot(db).policy)


@router.get("/inventories/{inventory_id}")
def get_inventory_view(inventory_id: str, db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    return inventory_view(db, get_inventory(db, p, inventory_id), snapshot(db).policy)


class ResourcePatch(BaseModel):
    model_config = {"extra": "forbid"}
    fields: dict[str, Any] = Field(default_factory=dict)
    user_confirmed: bool | None = None


@router.patch("/inventories/{inventory_id}/resources/{resource_id}")
def patch_resource(inventory_id: str, resource_id: str, body: ResourcePatch, db: Session = Depends(get_db),
                   p: Principal = Depends(require("analyst"))):
    inv = get_inventory(db, p, inventory_id)
    row = db.get(InventoryResource, resource_id)
    if row is None or row.inventory_id != inv.id:
        raise HTTPException(404, "resource not found")
    before = row_to_draft(row)
    merged = before.model_dump()
    for k, v in body.fields.items():
        if k in ("field_confidence",):
            raise HTTPException(422, "field_confidence is set by extraction, not editable")
        merged[k] = v
    try:
        draft = ResourceDraft(**merged)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False)) from exc
    changed = [k for k in body.fields if getattr(before, k) != getattr(draft, k)]
    for k in changed:  # a value typed/confirmed by the user is fully trusted
        draft.field_confidence[k] = 1.0
        if k in draft.unknown_fields and getattr(draft, k) is not None:
            draft.unknown_fields.remove(k)
    apply_draft(row, draft)
    if changed and body.user_confirmed is None:
        row.user_confirmed = False
    if body.user_confirmed is not None:
        row.user_confirmed = body.user_confirmed
    if changed or body.user_confirmed is False:
        unconfirm(inv)
    if inv.status == "draft":
        inv.status = "needs_confirmation"
    audit(db, p, "inventory.resource.update", "inventory_resource", row.id,
          {"inventory_id": inv.id, "changed": {k: str(getattr(draft, k)) for k in changed},
           "user_confirmed": row.user_confirmed})
    db.commit()
    return inventory_view(db, inv, snapshot(db).policy)


@router.post("/inventories/{inventory_id}/resources")
def add_resource(inventory_id: str, body: ResourceDraft, db: Session = Depends(get_db),
                 p: Principal = Depends(require("analyst"))):
    inv = get_inventory(db, p, inventory_id)
    pos = len(resources_of(db, inv))
    row = InventoryResource(inventory_id=inv.id, position=pos, raw_input=body.model_dump(mode="json"))
    apply_draft(row, body)
    db.add(row)
    unconfirm(inv)
    inv.status = "needs_confirmation"
    audit(db, p, "inventory.resource.add", "inventory", inv.id, {"name": body.name})
    db.commit()
    return inventory_view(db, inv, snapshot(db).policy)


@router.delete("/inventories/{inventory_id}/resources/{resource_id}")
def delete_resource(inventory_id: str, resource_id: str, db: Session = Depends(get_db),
                    p: Principal = Depends(require("analyst"))):
    inv = get_inventory(db, p, inventory_id)
    row = db.get(InventoryResource, resource_id)
    if row is None or row.inventory_id != inv.id:
        raise HTTPException(404, "resource not found")
    db.delete(row)
    unconfirm(inv)
    audit(db, p, "inventory.resource.delete", "inventory", inv.id, {"resource_id": resource_id, "name": row.name})
    db.commit()
    return inventory_view(db, inv, snapshot(db).policy)


@router.post("/inventories/{inventory_id}/confirm")
def confirm(inventory_id: str, body: ConfirmIn, db: Session = Depends(get_db),
            p: Principal = Depends(require("analyst"))):
    inv = get_inventory(db, p, inventory_id)
    if inv.currency == "UNCONFIRMED":
        raise HTTPException(409, "confirm whether the invoice is in Rial or Toman first")
    confirm_inventory(db, p, inv, body.confirm_all_rows)
    return inventory_view(db, inv, snapshot(db).policy)


@router.post("/inventories/{inventory_id}/archive")
def archive(inventory_id: str, db: Session = Depends(get_db), p: Principal = Depends(require("analyst"))):
    inv = get_inventory(db, p, inventory_id)
    inv.status = "archived"
    audit(db, p, "inventory.archive", "inventory", inv.id)
    db.commit()
    return {"id": inv.id, "status": inv.status}


@router.get("/uploads/{upload_id}/download")
def download_upload(upload_id: str, exp: int, sig: str, db: Session = Depends(get_db)):
    if not verify_download(upload_id, exp, sig):
        raise HTTPException(403, "invalid or expired link")
    up = db.get(Upload, upload_id)
    if up is None or up.deleted_at is not None or not up.storage_path:
        raise HTTPException(410, "file deleted under the retention policy")
    return FileResponse(up.storage_path, media_type=up.content_type, filename=up.filename)
