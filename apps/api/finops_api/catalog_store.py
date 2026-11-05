"""Versioned catalog persistence. Prices are never overwritten: a change closes the open version
(valid_to) and inserts a new one."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from pricing_engine.catalog import CatalogSnapshot, load_json, normalize_seed_item
from pricing_engine.models import BillingRule, CatalogItem, Provider
from provider_adapters import SECOND_WAVE_STATUS, ManualPriceAdapter, ParseError, get_adapter, natural_key, plan_sync
from provider_adapters.base import RawCatalog
from provider_adapters.sync import signature

from .orm import BillingRuleVersion, CatalogItemVersion, PriceSource, PriceSyncRun, ProviderRow, now

ITEM_FIELDS = [f for f in CatalogItem.model_fields if f not in ("id", "version_id", "valid_from", "valid_to")]


def _sig(item: CatalogItem) -> str:
    return hashlib.sha256(json.dumps([str(x) for x in signature(item)]).encode()).hexdigest()


def row_to_item(row: CatalogItemVersion) -> CatalogItem:
    data = {f: getattr(row, f) for f in ITEM_FIELDS}
    return CatalogItem(id=row.item_id, version_id=row.version_id, valid_from=_aware(row.valid_from),
                       valid_to=_aware(row.valid_to) if row.valid_to else None, **data)


def _insert_version(db: Session, item: CatalogItem, valid_from: datetime, source_id: int | None) -> CatalogItemVersion:
    data = {f: getattr(item, f) for f in ITEM_FIELDS}
    row = CatalogItemVersion(item_id=item.id, valid_from=valid_from, valid_to=None, source_id=source_id,
                             signature=_sig(item), **data)
    db.add(row)
    return row


def _source(db: Session, provider_id: str, url: str, kind: str, retrieved_at: datetime, price_date: str | None,
            content_hash: str | None, status: str, raw: dict[str, Any] | None = None) -> PriceSource:
    existing = db.scalar(select(PriceSource).where(PriceSource.provider_id == provider_id,
                                                   PriceSource.source_url == url,
                                                   PriceSource.retrieved_at == retrieved_at))
    if existing:
        return existing
    src = PriceSource(provider_id=provider_id, source_url=url, source_kind=kind, retrieved_at=retrieved_at,
                      provider_price_date=price_date, content_hash=content_hash, sync_status=status, raw_snapshot=raw)
    db.add(src)
    db.flush()
    return src


def current_versions(db: Session, provider_id: str | None = None) -> list[CatalogItemVersion]:
    q = select(CatalogItemVersion).where(CatalogItemVersion.valid_to.is_(None))
    if provider_id:
        q = q.where(CatalogItemVersion.provider_id == provider_id)
    return list(db.scalars(q))


# --------------------------------------------------------------------------- seed import


def seed_pricing(db: Session, seed_dir: Path) -> dict[str, int]:
    """Idempotent: re-running with an unchanged seed inserts nothing. A seed never overrides prices that were
    updated (or rows removed) after its snapshot date, because this runs on every API start."""
    bundle = load_json(seed_dir / "iran_finops_dataset.json")
    snap_at = datetime.fromisoformat(bundle["metadata"]["snapshot_date"]).replace(tzinfo=UTC)
    stats = {"providers": 0, "items_inserted": 0, "items_unchanged": 0, "items_versioned": 0, "rules_inserted": 0}
    for p in bundle["providers"]:
        prov = Provider.model_validate(p)
        row = db.get(ProviderRow, prov.provider_id)
        meta = {k: v for k, v in p.items() if k in ("provider_type", "automation_surfaces", "recommended_mvp_priority",
                                                     "integration_strategy", "notes")}
        if row is None:
            db.add(ProviderRow(id=prov.provider_id, name_en=prov.name_en, name_fa=prov.name_fa, website=prov.website,
                               official_pricing_url=prov.official_pricing_url, country=prov.country,
                               pricing_model=prov.pricing_model, api_status=prov.api_status,
                               public_catalog_quality=prov.public_catalog_quality, meta=meta))
            stats["providers"] += 1
    db.flush()
    current = {r.item_id: r for r in current_versions(db)}
    latest: dict[str, datetime] = {}
    for item_id, valid_from in db.execute(select(CatalogItemVersion.item_id, CatalogItemVersion.valid_from)):
        latest[item_id] = max(latest.get(item_id, _aware(valid_from)), _aware(valid_from))
    sources: dict[tuple[str, str], PriceSource] = {}
    for raw in bundle["catalog_items"]:
        item = normalize_seed_item(raw, snap_at)
        if item.id in latest and latest[item.id] > snap_at:
            stats["items_unchanged"] += 1
            continue
        key = (item.provider_id, item.source_url or "")
        if key not in sources:
            sources[key] = _source(db, item.provider_id, item.source_url or "", "official", snap_at,
                                   item.source_price_date, None, "seed", {"origin": "iran_finops_dataset.json"})
        existing = current.get(item.id)
        if existing is not None and existing.signature == _sig(item):
            stats["items_unchanged"] += 1
            continue
        if existing is not None:
            existing.valid_to = snap_at
            stats["items_versioned"] += 1
        _insert_version(db, item, snap_at, sources[key].id)
        stats["items_inserted"] += 1
    for r in bundle["billing_rules"]:
        rule = BillingRule.model_validate(r)
        sig = hashlib.sha256(rule.model_dump_json().encode()).hexdigest()
        cur = db.scalar(select(BillingRuleVersion).where(BillingRuleVersion.rule_id == rule.rule_id,
                                                         BillingRuleVersion.valid_to.is_(None)))
        if cur is not None and cur.signature == sig:
            continue
        if cur is not None:
            cur.valid_to = snap_at
        db.add(BillingRuleVersion(rule_id=rule.rule_id, provider_id=rule.provider_id, scope=rule.scope,
                                  rule_type=rule.rule_type, status=rule.status, logic=json.loads(json.dumps(
                                      rule.logic, default=str)), source_url=rule.source_url,
                                  retrieved_at=rule.retrieved_at, notes=rule.notes, signature=sig, valid_from=snap_at))
        stats["rules_inserted"] += 1
    db.commit()
    return stats


# --------------------------------------------------------------------------- snapshot


def load_snapshot(db: Session, seed_dir: Path, as_of: datetime | None = None) -> CatalogSnapshot:
    as_of = as_of or datetime.now(UTC)
    q = select(CatalogItemVersion).where(CatalogItemVersion.valid_from <= as_of)
    rows = [r for r in db.scalars(q) if r.valid_to is None or _aware(r.valid_to) > as_of]
    providers = {}
    for p in db.scalars(select(ProviderRow)):
        providers[p.id] = Provider(provider_id=p.id, name_en=p.name_en, name_fa=p.name_fa, website=p.website,
                                   official_pricing_url=p.official_pricing_url, country=p.country,
                                   pricing_model=p.pricing_model, public_catalog_quality=p.public_catalog_quality,
                                   api_status=p.api_status, provider_type=p.meta.get("provider_type", []),
                                   automation_surfaces=p.meta.get("automation_surfaces", []),
                                   recommended_mvp_priority=p.meta.get("recommended_mvp_priority"),
                                   integration_strategy=p.meta.get("integration_strategy"), notes=p.meta.get("notes"))
    rules = {}
    for r in db.scalars(select(BillingRuleVersion).where(BillingRuleVersion.valid_to.is_(None))):
        rules[r.rule_id] = BillingRule(rule_id=r.rule_id, provider_id=r.provider_id, scope=r.scope,
                                       rule_type=r.rule_type, status=r.status, logic=r.logic, source_url=r.source_url,
                                       retrieved_at=r.retrieved_at, notes=r.notes)
    return CatalogSnapshot(
        providers=providers, items=[row_to_item(r) for r in rows], billing_rules=rules,
        source_checked=_source_checked(db, as_of),
        policy=load_json(seed_dir / "engine_policy.json"),
        equivalence_rules=load_json(seed_dir / "equivalence_rules.json"),
        recommendation_rules=load_json(seed_dir / "recommendation_rules.json"),
        snapshot_at=as_of,
    )


def _source_checked(db: Session, as_of: datetime) -> dict[str, str]:
    """Item id -> date the latest successful sync of its provider read the same price again."""
    ok = PriceSyncRun.status.in_(("ok", "warning"))
    latest = (select(PriceSyncRun.provider_id, func.max(PriceSyncRun.started_at).label("at"))
              .where(ok, PriceSyncRun.started_at <= as_of).group_by(PriceSyncRun.provider_id).subquery())
    runs = db.scalars(select(PriceSyncRun).join(latest, and_(PriceSyncRun.provider_id == latest.c.provider_id,
                                                             PriceSyncRun.started_at == latest.c.at)).where(ok))
    out: dict[str, str] = {}
    for run in runs:
        s = run.summary or {}
        if s.get("checked_at"):
            out.update(dict.fromkeys(s.get("confirmed_item_ids") or [], s["checked_at"]))
    return out


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# --------------------------------------------------------------------------- sync


def run_provider_sync(db: Session, provider_id: str, *, triggered_by: str, raw: RawCatalog | None = None,
                      stale_after_days: int = 45, today: date | None = None, adapter: Any = None) -> PriceSyncRun:
    run = PriceSyncRun(provider_id=provider_id, status="running", triggered_by=triggered_by)
    db.add(run)
    db.flush()
    adapter = adapter or get_adapter(provider_id)
    if adapter is None:
        run.status = "not_implemented"
        run.error = SECOND_WAVE_STATUS.get(provider_id, "no adapter registered")
        run.finished_at = now()
        db.commit()
        return run
    fetch_error = None
    if raw is None:
        try:
            raw = asyncio.run(adapter.fetch_catalog())
        except Exception as exc:  # noqa: BLE001 - any fetch failure is a visible failed sync
            fetch_error = exc
    previous = [row_to_item(r) for r in current_versions(db, provider_id)]
    last_hash = db.scalar(select(PriceSource.content_hash).where(PriceSource.provider_id == provider_id,
                                                                PriceSource.content_hash.is_not(None))
                          .order_by(PriceSource.retrieved_at.desc()).limit(1))
    plan = plan_sync(adapter, raw, previous, previous_content_hash=last_hash, parse_error=fetch_error,
                     stale_after_days=stale_after_days, today=today)
    run.items_seen, run.items_changed = plan.items_seen, plan.items_changed
    run.warnings, run.error, run.summary, run.content_hash = plan.warnings, plan.error, plan.summary(), plan.content_hash
    run.status = plan.status
    if plan.status == "quarantined":
        run.pending_items = [c.new.model_dump(mode="json") for c in plan.changes if c.new is not None]
    if plan.applicable and raw is not None:
        src = _source(db, provider_id, raw.source_url, "official", raw.fetched_at, None, raw.content_hash, plan.status)
        _apply_changes(db, plan.changes, raw.fetched_at, src.id)
    elif raw is not None and plan.status == "failed":
        _source(db, provider_id, raw.source_url, "official", raw.fetched_at, None, raw.content_hash, "failed")
    run.finished_at = now()
    db.commit()
    return run


def import_manual_prices(db: Session, provider_id: str, content: str, triggered_by: str) -> PriceSyncRun:
    """Apply a reviewed price file. Same guardrails and versioning as a scrape."""
    adapter = ManualPriceAdapter(provider_id, [row_to_item(r) for r in current_versions(db, provider_id)])
    try:
        raw = adapter.load(content)
    except ParseError as exc:
        run = PriceSyncRun(provider_id=provider_id, status="failed", triggered_by=triggered_by, error=str(exc),
                           finished_at=now())
        db.add(run)
        db.commit()
        return run
    return run_provider_sync(db, provider_id, triggered_by=triggered_by, raw=raw, adapter=adapter)


def _apply_changes(db: Session, changes, at: datetime, source_id: int | None) -> None:
    by_version = {r.version_id: r for r in current_versions(db)}
    for c in changes:
        if c.old is not None and c.old.version_id in by_version:
            by_version[c.old.version_id].valid_to = at
        if c.new is not None:
            _insert_version(db, c.new, at, source_id)


def approve_quarantined(db: Session, run: PriceSyncRun, reviewer: str) -> PriceSyncRun:
    """Human-approved application of a quarantined sync."""
    if run.status != "quarantined" or not run.pending_items:
        raise ValueError("only quarantined runs with pending items can be approved")
    at = datetime.now(UTC)
    current = {natural_key(row_to_item(r)): r for r in current_versions(db, run.provider_id)}
    for data in run.pending_items:
        item = CatalogItem.model_validate(data)
        old = current.get(natural_key(item))
        if old is not None:
            old.valid_to = at
        _insert_version(db, item, at, None)
    run.status = "applied_after_review"
    run.summary = {**run.summary, "approved_by": reviewer, "approved_at": at.isoformat()}
    db.commit()
    return run
