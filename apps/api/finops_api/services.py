"""Inventory + analysis services shared by routers, the advisor tools and the report generator."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from pricing_engine import BillingContext, CatalogSnapshot, Resource, UsageMetrics, price_inventory
from pricing_engine.models import Quote
from recommendation_engine import RECOMMENDATION_ENGINE_VERSION, OrgSettings, recommend, summarize
from shared_types import ResourceDraft, missing_required_fields, required_fields, review_status
from shared_types.inventory import low_confidence_fields

from .catalog_store import load_snapshot
from .config import get_settings
from .orm import Inventory, InventoryResource, QuoteRow, RecommendationRow, uid
from .security import Principal, audit

DRAFT_FIELDS = [f for f in ResourceDraft.model_fields if f != "notes"] + ["notes"]


def snapshot(db: Session) -> CatalogSnapshot:
    return load_snapshot(db, get_settings().seed_dir)


# --------------------------------------------------------------------------- conversion


def row_to_draft(row: InventoryResource) -> ResourceDraft:
    return ResourceDraft(**{f: getattr(row, f) for f in DRAFT_FIELDS})


def apply_draft(row: InventoryResource, draft: ResourceDraft) -> None:
    for f in DRAFT_FIELDS:
        setattr(row, f, getattr(draft, f))


def to_engine(row: InventoryResource) -> Resource:
    metrics = None
    if row.metrics:
        allowed = set(UsageMetrics.model_fields)
        metrics = UsageMetrics(**{k: v for k, v in row.metrics.items() if k in allowed})
    return Resource(
        id=row.id, name=row.name or row.external_ref or row.id[:8], provider_id=row.provider_id,
        service_type=row.service_type, sku=row.sku, resource_class=row.resource_class, environment=row.environment,
        datacenter=row.datacenter, quantity=row.quantity if row.quantity is not None else Decimal(1),
        cpu_cores=row.cpu_cores, cpu_shared=row.cpu_shared, ram_gb=row.ram_gb, storage_gb=row.storage_gb,
        storage_type=row.storage_type, gpu_model=row.gpu_model, gpu_count=row.gpu_count,
        expected_monthly_download_gb=row.expected_monthly_download_gb,
        expected_monthly_upload_gb=row.expected_monthly_upload_gb, active_hours_per_month=row.active_hours_per_month,
        requires_public_ipv4=row.requires_public_ipv4, ipv4_count=row.ipv4_count,
        billing_mode=row.billing_mode or "monthly", metrics=metrics,
    )


def resource_view(row: InventoryResource, policy: dict[str, Any]) -> dict[str, Any]:
    d = row_to_draft(row)
    data = d.model_dump(mode="json")
    data.update({
        "id": row.id, "position": row.position, "user_confirmed": row.user_confirmed,
        "required_fields": required_fields(d, policy), "missing_fields": missing_required_fields(d, policy),
        "low_confidence_fields": low_confidence_fields(d),
        "review_status": review_status(d, policy, row.user_confirmed).value,
        "extraction_confidence": min(d.field_confidence.values()) if d.field_confidence else 1.0,
    })
    return data


def get_inventory(db: Session, p: Principal, inventory_id: str) -> Inventory:
    inv = db.get(Inventory, inventory_id)
    if inv is None or inv.organization_id != p.org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "inventory not found")
    return inv


def resources_of(db: Session, inv: Inventory) -> list[InventoryResource]:
    return list(db.scalars(select(InventoryResource).where(InventoryResource.inventory_id == inv.id)
                           .order_by(InventoryResource.position)))


def inventory_view(db: Session, inv: Inventory, policy: dict[str, Any]) -> dict[str, Any]:
    rows = [resource_view(r, policy) for r in resources_of(db, inv)]
    upload = None
    if upload_id := (inv.source_meta or {}).get("upload_id"):
        from .orm import Upload
        from .platform import sign_download

        up = db.get(Upload, upload_id)
        if up is not None:
            upload = {"id": up.id, "filename": up.filename, "delete_after": up.delete_after,
                      "deleted": up.deleted_at is not None,
                      "download_url": None if up.deleted_at else sign_download(up.id)}
    blocking = [{"resource_id": r["id"], "name": r["name"], "review_status": r["review_status"],
                 "missing_fields": r["missing_fields"]} for r in rows if r["review_status"] != "confirmed"]
    return {
        "id": inv.id, "name": inv.name, "status": inv.status, "source_type": inv.source_type, "currency": inv.currency,
        "source_meta": inv.source_meta, "confirmed_at": inv.confirmed_at, "created_at": inv.created_at,
        # accounting unit is always Toman; this is the unit the user confirmed for the uploaded invoice's amounts
        "invoice_currency": (inv.source_meta or {}).get("invoice_currency_confirmed")
        or ((inv.source_meta or {}).get("invoice") or {}).get("detected_currency"),
        "upload": upload,
        "resources": rows,
        "can_confirm": bool(rows) and not blocking,
        "can_analyze": inv.status == "confirmed",
        "blocking": blocking,
    }


def create_inventory(db: Session, p: Principal, name: str, source_type: str, drafts: list[ResourceDraft],
                     source_meta: dict[str, Any] | None = None, user_confirmed: bool = False) -> Inventory:
    inv = Inventory(organization_id=p.org.id, name=name, source_type=source_type,
                    status="needs_confirmation" if drafts else "draft", source_meta=source_meta or {},
                    created_by=p.user.id)
    db.add(inv)
    db.flush()
    for i, d in enumerate(drafts):
        row = InventoryResource(inventory_id=inv.id, position=i, user_confirmed=user_confirmed,
                                raw_input=d.model_dump(mode="json"))
        apply_draft(row, d)
        db.add(row)
    audit(db, p, "inventory.create", "inventory", inv.id, {"source_type": source_type, "resources": len(drafts)})
    db.commit()
    return inv


def unconfirm(inv: Inventory) -> None:
    if inv.status == "confirmed":
        inv.status = "needs_confirmation"
        inv.confirmed_at = None
        inv.confirmed_by = None


def confirm_inventory(db: Session, p: Principal, inv: Inventory, confirm_all_rows: bool) -> Inventory:
    policy = snapshot(db).policy
    rows = resources_of(db, inv)
    if not rows:
        raise HTTPException(status.HTTP_409_CONFLICT, "inventory has no resources")
    if confirm_all_rows:
        for r in rows:
            if not missing_required_fields(row_to_draft(r), policy):
                r.user_confirmed = True
    blocking = []
    for r in rows:
        st = review_status(row_to_draft(r), policy, r.user_confirmed)
        if st.value != "confirmed":
            blocking.append({"resource_id": r.id, "name": r.name, "review_status": st.value,
                             "missing_fields": missing_required_fields(row_to_draft(r), policy)})
    if blocking:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, {"message": "inventory cannot be confirmed yet",
                                                       "blocking": blocking})
    inv.status = "confirmed"
    inv.confirmed_at = datetime.now(UTC)
    inv.confirmed_by = p.user.id
    audit(db, p, "inventory.confirm", "inventory", inv.id, {"resources": len(rows)})
    db.commit()
    return inv


def require_confirmed(inv: Inventory) -> None:
    if inv.status != "confirmed":
        raise HTTPException(status.HTTP_409_CONFLICT, "inventory must be confirmed before analysis "
                                                      "(review the table and confirm every row)")


# --------------------------------------------------------------------------- analysis


def org_settings(p: Principal) -> OrgSettings:
    return OrgSettings(engineer_day_rate_toman=(p.org.settings or {}).get("engineer_day_rate_toman"))


def create_quote(db: Session, p: Principal, inv: Inventory, include_tax: bool,
                 snap: CatalogSnapshot | None = None) -> tuple[QuoteRow, Quote]:
    require_confirmed(inv)
    snap = snap or snapshot(db)
    rows = resources_of(db, inv)
    resources = [to_engine(r) for r in rows]
    quote = price_inventory(resources, snap, BillingContext(include_tax=include_tax))
    row = QuoteRow(inventory_id=inv.id, organization_id=p.org.id,
                   inventory_snapshot=[r.model_dump(mode="json") for r in resources],
                   catalog_version=quote.catalog_version, policy_version=quote.policy_version,
                   deterministic_engine_version=quote.engine_version, catalog_snapshot_at=quote.catalog_snapshot_at,
                   complete=quote.complete, include_tax=include_tax, total_toman=quote.total_toman,
                   priced_subtotal_toman=quote.priced_subtotal_toman, total_tax_toman=quote.total_tax_toman,
                   content=quote.model_dump(mode="json"), content_hash=quote.content_hash, created_by=p.user.id)
    db.add(row)
    db.flush()
    audit(db, p, "analysis.quote", "quote", row.id, {"inventory_id": inv.id, "complete": quote.complete,
                                                     "catalog_version": quote.catalog_version})
    db.commit()
    return row, quote


def run_recommendations(db: Session, p: Principal, inv: Inventory) -> dict[str, Any]:
    require_confirmed(inv)
    snap = snapshot(db)
    quote_row, quote = create_quote(db, p, inv, include_tax=False, snap=snap)
    resources = [to_engine(r) for r in resources_of(db, inv)]
    recs = recommend(resources, snap, BillingContext(), org_settings(p))
    analysis_id = uid()
    stored = []
    for x in recs:
        row = RecommendationRow(
            key=x.key, inventory_id=inv.id, organization_id=p.org.id, quote_id=quote_row.id, analysis_id=analysis_id,
            rule_id=x.rule_id, resource_id=x.resource_id, resource_name=x.resource_name, provider_id=x.provider_id,
            recommendation_type=x.type, result_status=x.status, title_en=x.title_en, title_fa=x.title_fa,
            summary_en=x.summary_en, summary_fa=x.summary_fa, current_cost_toman=x.current_cost_toman,
            candidate_cost_toman=x.candidate_cost_toman, monthly_saving_toman=x.monthly_saving_toman,
            monthly_saving_percent=x.monthly_saving_percent,
            one_time_migration_cost_toman=x.one_time_migration_cost_toman, payback_months=x.payback_months,
            payback_status=x.payback_status, risk_level=x.risk, effort_level=x.effort, confidence=x.confidence,
            price_dates=x.price_dates, missing_inputs=x.missing_inputs, evidence=x.evidence,
        )
        db.add(row)
        stored.append(row)
    db.flush()
    summary = summarize(recs, quote.total_toman, snap)
    audit(db, p, "analysis.recommendations", "inventory", inv.id,
          {"analysis_id": analysis_id, "quote_id": quote_row.id, "count": len(recs),
           "engine": RECOMMENDATION_ENGINE_VERSION})
    db.commit()
    return {"analysis_id": analysis_id, "quote_id": quote_row.id, "quote_total_toman": quote.total_toman,
            "quote_complete": quote.complete, "summary": summary,
            "recommendations": [rec_view(r) for r in stored]}


def rec_view(r: RecommendationRow) -> dict[str, Any]:
    return {c: getattr(r, c) for c in (
        "id", "key", "analysis_id", "quote_id", "inventory_id", "rule_id", "resource_id", "resource_name",
        "provider_id", "recommendation_type", "result_status", "title_en", "title_fa", "summary_en", "summary_fa",
        "current_cost_toman", "candidate_cost_toman", "monthly_saving_toman", "monthly_saving_percent",
        "one_time_migration_cost_toman", "payback_months", "payback_status", "risk_level", "effort_level",
        "confidence", "price_dates", "missing_inputs", "evidence", "status", "created_at")}


def latest_analysis(db: Session, inv: Inventory) -> list[RecommendationRow]:
    last = db.scalar(select(RecommendationRow.analysis_id).where(RecommendationRow.inventory_id == inv.id)
                     .order_by(RecommendationRow.created_at.desc()).limit(1))
    if last is None:
        return []
    return list(db.scalars(select(RecommendationRow).where(RecommendationRow.analysis_id == last)))


def latest_quote(db: Session, inv: Inventory) -> QuoteRow | None:
    return db.scalar(select(QuoteRow).where(QuoteRow.inventory_id == inv.id).order_by(QuoteRow.created_at.desc())
                     .limit(1))
