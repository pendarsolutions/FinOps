from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_gateway import LLMConfig, run_advisor
from pricing_engine import BillingContext, find_equivalents
from recommendation_engine import summarize
from recommendation_engine.engine import Recommendation

from ..config import get_settings
from ..db import get_db
from ..orm import AIRun, Inventory, QuoteRow, RecommendationRow
from ..platform import limiter, redact
from ..report import render_report
from ..security import Principal, audit, current_principal, require
from ..services import (
    create_quote,
    get_inventory,
    latest_analysis,
    latest_quote,
    rec_view,
    require_confirmed,
    resources_of,
    run_recommendations,
    snapshot,
    to_engine,
)

router = APIRouter(prefix="/api/v1", tags=["analysis"])


class QuoteIn(BaseModel):
    include_tax: bool = False


class CompareIn(BaseModel):
    resource_ids: list[str] | None = None
    allow_outside_iran: bool = False


def quote_view(row: QuoteRow) -> dict[str, Any]:
    return {"id": row.id, "inventory_id": row.inventory_id, "created_at": row.created_at,
            "catalog_version": row.catalog_version, "policy_version": row.policy_version,
            "engine_version": row.deterministic_engine_version, "complete": row.complete,
            "include_tax": row.include_tax, "total_toman": row.total_toman,
            "priced_subtotal_toman": row.priced_subtotal_toman, "total_tax_toman": row.total_tax_toman,
            "content_hash": row.content_hash, "content": row.content}


@router.post("/inventories/{inventory_id}/quote")
def quote(inventory_id: str, body: QuoteIn, db: Session = Depends(get_db), p: Principal = Depends(require("analyst"))):
    row, _ = create_quote(db, p, get_inventory(db, p, inventory_id), body.include_tax)
    return quote_view(row)


@router.get("/inventories/{inventory_id}/quotes")
def list_quotes(inventory_id: str, db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    inv = get_inventory(db, p, inventory_id)
    rows = db.scalars(select(QuoteRow).where(QuoteRow.inventory_id == inv.id).order_by(QuoteRow.created_at.desc()))
    return [{k: v for k, v in quote_view(r).items() if k != "content"} for r in rows]


@router.get("/quotes/{quote_id}")
def get_quote(quote_id: str, db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    row = db.get(QuoteRow, quote_id)
    if row is None or row.organization_id != p.org.id:
        raise HTTPException(404, "quote not found")
    return quote_view(row)


def _compare(db: Session, p: Principal, inv: Inventory, body: CompareIn) -> dict[str, Any]:
    require_confirmed(inv)
    snap = snapshot(db)
    ctx = BillingContext(allow_outside_iran=body.allow_outside_iran)
    out = []
    for r in resources_of(db, inv):
        if body.resource_ids and r.id not in body.resource_ids:
            continue
        res = find_equivalents(to_engine(r), snap, ctx)
        out.append({"resource_id": r.id, "resource_name": r.name, **res.model_dump(mode="json")})
    return {"catalog_version": snap.catalog_version, "allow_outside_iran": body.allow_outside_iran, "results": out}


@router.post("/inventories/{inventory_id}/compare")
def compare(inventory_id: str, body: CompareIn, db: Session = Depends(get_db),
            p: Principal = Depends(require("analyst"))):
    inv = get_inventory(db, p, inventory_id)
    result = _compare(db, p, inv, body)
    audit(db, p, "analysis.compare", "inventory", inv.id, {"resources": len(result["results"]),
                                                           "allow_outside_iran": body.allow_outside_iran})
    db.commit()
    return result


@router.post("/inventories/{inventory_id}/recommendations")
def recommendations(inventory_id: str, db: Session = Depends(get_db), p: Principal = Depends(require("analyst"))):
    return run_recommendations(db, p, get_inventory(db, p, inventory_id))


def _summary_from_rows(rows: list[RecommendationRow], total: Decimal | None, db: Session) -> dict[str, Any]:
    recs = [Recommendation(key=r.key, rule_id=r.rule_id, type=r.recommendation_type, status=r.result_status,
                           title_en=r.title_en, title_fa=r.title_fa, resource_id=r.resource_id,
                           monthly_saving_toman=r.monthly_saving_toman, risk=r.risk_level, effort=r.effort_level or "",
                           confidence=r.confidence, summary_en="", summary_fa="", evidence={}) for r in rows]
    return summarize(recs, total, snapshot(db))


@router.get("/inventories/{inventory_id}/recommendations")
def latest_recommendations(inventory_id: str, db: Session = Depends(get_db),
                           p: Principal = Depends(current_principal)):
    inv = get_inventory(db, p, inventory_id)
    rows = latest_analysis(db, inv)
    q = db.get(QuoteRow, rows[0].quote_id) if rows else None
    return {"analysis_id": rows[0].analysis_id if rows else None, "quote_id": q.id if q else None,
            "summary": _summary_from_rows(rows, q.total_toman if q else None, db) if rows else None,
            "recommendations": sorted([rec_view(r) for r in rows],
                                      key=lambda r: ({"actionable": 0, "informational": 1}.get(r["result_status"], 2),
                                                     -(r["monthly_saving_toman"] or 0)))}


@router.get("/recommendations/{rec_id}")
def get_recommendation(rec_id: str, db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    r = db.get(RecommendationRow, rec_id)
    if r is None or r.organization_id != p.org.id:
        raise HTTPException(404, "recommendation not found")
    return rec_view(r)


@router.get("/inventories/{inventory_id}/overview")
def overview(inventory_id: str, db: Session = Depends(get_db), p: Principal = Depends(current_principal)):
    inv = get_inventory(db, p, inventory_id)
    snap = snapshot(db)
    q = latest_quote(db, inv)
    rows = latest_analysis(db, inv)
    by_provider: dict[str, Decimal] = defaultdict(Decimal)
    by_env: dict[str, Decimal] = defaultdict(Decimal)
    env_of = {r.id: (r.environment or "unknown") for r in resources_of(db, inv)}
    if q:
        for bd in q.content["breakdowns"]:
            if bd["monthly_total_toman"] is not None:
                by_provider[bd["provider_id"]] += Decimal(bd["monthly_total_toman"])
                by_env[env_of.get(bd["resource_id"], "unknown")] += Decimal(bd["monthly_total_toman"])
    actionable = sorted([rec_view(r) for r in rows if r.result_status == "actionable"],
                        key=lambda r: -(r["monthly_saving_toman"] or 0))
    return {
        "inventory": {"id": inv.id, "name": inv.name, "status": inv.status},
        "quote": {k: v for k, v in quote_view(q).items() if k != "content"} if q else None,
        "unavailable": q.content["unavailable"] if q else [],
        "summary": _summary_from_rows(rows, q.total_toman if q else None, db) if rows else None,
        "provider_distribution": [{"provider_id": k, "monthly_toman": v} for k, v in sorted(by_provider.items())],
        "environment_distribution": [{"environment": k, "monthly_toman": v} for k, v in sorted(by_env.items())],
        "top_opportunities": actionable[:3],
        "price_freshness": snap.source_freshness(),
        "catalog_version": snap.catalog_version,
    }


@router.get("/inventories/{inventory_id}/report", response_class=HTMLResponse)
def report(inventory_id: str, lang: str = "fa", db: Session = Depends(get_db),
           p: Principal = Depends(current_principal)):
    inv = get_inventory(db, p, inventory_id)
    require_confirmed(inv)
    html = render_report(db, p, inv, lang if lang in ("fa", "en") else "fa")
    audit(db, p, "report.generate", "inventory", inv.id, {"lang": lang})
    db.commit()
    return HTMLResponse(html, headers={"Content-Disposition": f'attachment; filename="pendar-finops-{inv.id[:8]}-{lang}.html"'})


# --------------------------------------------------------------------------- advisor


class AdvisorIn(BaseModel):
    inventory_id: str
    question: str = Field(min_length=2, max_length=4000)
    lang: str = Field(default="fa", pattern="^(fa|en)$")


def advisor_tools(db: Session, p: Principal, inv: Inventory) -> dict[str, Any]:
    snap = snapshot(db)

    def get_inventory_tool(_: dict) -> dict:
        return {"inventory_id": inv.id, "status": inv.status,
                "resources": [to_engine(r).model_dump(mode="json") for r in resources_of(db, inv)]}

    def get_catalog_item(args: dict) -> dict:
        item = next((i for i in snap.items if i.id == args["item_id"]), None)
        if item is None:
            raise ValueError("catalog item not found")
        return {"catalog_version": snap.catalog_version, "item": item.model_dump(mode="json")}

    def price_inventory_tool(_: dict) -> dict:
        q = latest_quote(db, inv)
        if q is None or q.catalog_version != snap.catalog_version:
            q, _ = create_quote(db, p, inv, include_tax=False, snap=snap)
        c = q.content
        return {"quote_id": q.id, "catalog_version": q.catalog_version, "complete": q.complete,
                "total_toman": c["total_toman"], "priced_subtotal_toman": c["priced_subtotal_toman"],
                "breakdowns": [{k: b[k] for k in ("resource_id", "resource_name", "provider_id", "status",
                                                  "monthly_total_toman", "unavailable", "assumptions")}
                               for b in c["breakdowns"]],
                "price_sources": c["price_sources"]}

    def compare_providers(args: dict) -> dict:
        res = _compare(db, p, inv, CompareIn(resource_ids=[args["resource_id"]]))
        if not res["results"]:
            raise ValueError("resource not in this inventory")
        r = res["results"][0]
        return {"catalog_version": res["catalog_version"], "resource_id": r["resource_id"],
                "candidates": [{k: c[k] for k in ("candidate_label", "confidence", "fit_score", "monthly_saving_toman",
                                                  "monthly_saving_percent", "differences", "assumptions")}
                               | {"candidate_cost_toman": c["candidate"]["monthly_total_toman"],
                                  "current_cost_toman": c["current"]["monthly_total_toman"]}
                               for c in r["candidates"][:5]],
                "rejected_count": len(r["rejected"]), "notes": r["notes"]}

    def list_recommendations(_: dict) -> dict:
        rows = latest_analysis(db, inv)
        if not rows:
            return run_recommendations(db, p, inv)
        q = db.get(QuoteRow, rows[0].quote_id)
        return {"analysis_id": rows[0].analysis_id, "quote_id": q.id if q else None,
                "summary": _summary_from_rows(rows, q.total_toman if q else None, db),
                "recommendations": [{k: v for k, v in rec_view(r).items() if k != "evidence"} for r in rows]}

    def get_price_source(args: dict) -> dict:
        return {"catalog_version": snap.catalog_version,
                "sources": [s for s in snap.source_freshness() if s["provider_id"] == args["provider_id"]]}

    def get_provider_documentation(args: dict) -> dict:
        prov = snap.providers.get(args["provider_id"])
        if prov is None:
            raise ValueError("unknown provider")
        return {"provider": prov.model_dump(mode="json"), "engine_policy": snap.provider_policy(prov.provider_id)}

    return {"get_inventory": get_inventory_tool, "get_catalog_item": get_catalog_item,
            "price_inventory": price_inventory_tool, "compare_providers": compare_providers,
            "list_recommendations": list_recommendations, "get_price_source": get_price_source,
            "get_provider_documentation": get_provider_documentation}


@router.post("/advisor/chat")
def advisor_chat(body: AdvisorIn, db: Session = Depends(get_db), p: Principal = Depends(require("analyst"))):
    s = get_settings()
    limiter().check(f"ai:{p.user.id}", s.ai_rate_limit_per_minute)
    inv = get_inventory(db, p, body.inventory_id)
    require_confirmed(inv)
    cfg = LLMConfig(model=s.ai_model, api_key=s.anthropic_api_key) if s.ai_provider == "anthropic" else None
    ans = run_advisor(body.question, body.lang, advisor_tools(db, p, inv), provider=s.ai_provider, cfg=cfg)
    run = AIRun(organization_id=p.org.id, user_id=p.user.id, purpose="advisor", model=ans.meta.get("model", ans.path),
                prompt_version=ans.meta["prompt_version"], input_redacted={"question": redact(body.question)},
                tool_calls=ans.tool_calls, output_text=ans.answer, guard_result={**ans.guard, "path": ans.path,
                                                                                  **ans.meta})
    db.add(run)
    db.commit()
    return {"answer": ans.answer, "path": ans.path, "evidence_ids": ans.evidence_ids, "guard": ans.guard,
            "tool_calls": [{"tool": t["tool"], "input": t["input"], "error": t["error"]} for t in ans.tool_calls],
            "ai_run_id": run.id}
