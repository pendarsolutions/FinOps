from __future__ import annotations

import hashlib
import math
from decimal import ROUND_CEILING, Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

from pricing_engine import (
    BillingContext,
    CatalogSnapshot,
    PriceBreakdown,
    PriceStatus,
    Resource,
    find_equivalents,
    price_resource,
    resolve_specs,
)
from pricing_engine.models import Comparison
from pricing_engine.money import OptDec

RECOMMENDATION_ENGINE_VERSION = "recommendation-engine/0.1.0"
PCT = Decimal("0.01")


class OrgSettings(BaseModel):
    engineer_day_rate_toman: OptDec = None


class Handoff(BaseModel):
    service_id: str
    name_en: str
    name_fa: str
    reason: str


class Recommendation(BaseModel):
    key: str
    rule_id: str
    type: str
    status: Literal["actionable", "cannot_determine", "informational"]
    title_en: str
    title_fa: str
    resource_id: str | None
    resource_name: str | None = None
    provider_id: str | None = None
    current_cost_toman: OptDec = None
    candidate_cost_toman: OptDec = None
    monthly_saving_toman: OptDec = None
    monthly_saving_percent: OptDec = None
    one_time_migration_cost_toman: OptDec = None
    payback_months: OptDec = None
    payback_status: str | None = None
    risk: str
    effort: str
    confidence: str
    price_dates: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    summary_en: str
    summary_fa: str
    evidence: dict[str, Any]
    pendar_handoff: Handoff | None = None


def _rules(snapshot: CatalogSnapshot) -> dict[str, dict[str, Any]]:
    return {r["rule_id"]: r for r in snapshot.recommendation_rules["rules"]}


def _key(*parts: Any) -> str:
    return "rec-" + hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:12]


def _price_dates(*bds: PriceBreakdown) -> list[str]:
    out = set()
    for bd in bds:
        for l in bd.components:
            if l.price_date:
                out.add(f"{bd.provider_id}: price date {l.price_date}")
            if l.retrieved_at:
                out.add(f"{bd.provider_id}: retrieved {l.retrieved_at}")
    return sorted(out)


def _bd_evidence(bd: PriceBreakdown) -> dict[str, Any]:
    return bd.model_dump(mode="json", include={"provider_id", "status", "monthly_total_toman", "components",
                                               "assumptions", "unavailable", "quantity"})


def _worth_it(snapshot: CatalogSnapshot, saving: Decimal, current: Decimal) -> bool:
    g = snapshot.recommendation_rules["global"]
    if saving < Decimal(str(g["min_monthly_saving_toman"])):
        return False
    return current > 0 and saving * 100 / current >= Decimal(str(g["min_saving_percent"]))


def _handoff(snapshot: CatalogSnapshot, service_id: str | None, reason: str) -> Handoff | None:
    if not service_id:
        return None
    svc = snapshot.recommendation_rules["pendar_services"][service_id]
    return Handoff(service_id=service_id, name_en=svc["en"], name_fa=svc["fa"], reason=reason)


def _priced_rec(snapshot: CatalogSnapshot, rule: dict[str, Any], r: Resource, current: PriceBreakdown,
                cand: PriceBreakdown, confidence: str, summary_en: str, summary_fa: str, evidence: dict[str, Any],
                **extra: Any) -> Recommendation:
    saving = current.monthly_total_toman - cand.monthly_total_toman
    pct = (saving * 100 / current.monthly_total_toman).quantize(PCT) if current.monthly_total_toman else None
    ev = {"current": _bd_evidence(current), "candidate": _bd_evidence(cand), "catalog_version": snapshot.catalog_version,
          **evidence}
    return Recommendation(
        key=_key(rule["rule_id"], r.id, snapshot.catalog_version, cand.monthly_total_toman), rule_id=rule["rule_id"],
        type=rule["type"], status="actionable", title_en=rule["title_en"], title_fa=rule["title_fa"], resource_id=r.id,
        resource_name=r.name, provider_id=r.provider_id, current_cost_toman=current.monthly_total_toman,
        candidate_cost_toman=cand.monthly_total_toman, monthly_saving_toman=saving, monthly_saving_percent=pct,
        risk=extra.pop("risk", rule["risk"]), effort=extra.pop("effort", rule["effort"]), confidence=confidence,
        price_dates=_price_dates(current, cand), summary_en=summary_en, summary_fa=summary_fa, evidence=ev, **extra,
    )


def _cannot(snapshot: CatalogSnapshot, r: Resource | None, blocked_rule: str, missing: list[str], why_en: str,
            why_fa: str, handoff_reason: str | None = None) -> Recommendation:
    rule = _rules(snapshot)["REC-005"]
    return Recommendation(
        key=_key("REC-005", blocked_rule, r.id if r else "-", ",".join(missing)), rule_id="REC-005", type=rule["type"],
        status="cannot_determine", title_en=rule["title_en"], title_fa=rule["title_fa"],
        resource_id=r.id if r else None, resource_name=r.name if r else None, provider_id=r.provider_id if r else None,
        risk=rule["risk"], effort=rule["effort"], confidence="n/a", missing_inputs=missing, summary_en=why_en,
        summary_fa=why_fa, evidence={"blocked_rule": blocked_rule, "missing_inputs": missing},
        pendar_handoff=_handoff(snapshot, rule.get("pendar_service"), handoff_reason) if handoff_reason else None,
    )


def _is_non_prod(snapshot: CatalogSnapshot, r: Resource) -> bool:
    return (r.environment or "").lower() in snapshot.policy["non_production_environments"]


def _plan_row(snapshot: CatalogSnapshot, r: Resource):
    if not r.sku or not r.provider_id:
        return None
    return snapshot.find_one(r.provider_id, sku=r.sku)


# ---------------------------------------------------------------- REC-001 / REC-004


def _cadence_rules(snapshot: CatalogSnapshot, r: Resource, current: PriceBreakdown, ctx: BillingContext) -> list[Recommendation]:
    rules = _rules(snapshot)
    row = _plan_row(snapshot, r)
    hpm = snapshot.hours_per_month
    out: list[Recommendation] = []
    has_hourly = row is not None and row.hourly_price_toman is not None
    non_prod = _is_non_prod(snapshot, r)

    if r.billing_mode == "monthly" and non_prod:
        if r.active_hours_per_month is None:
            if has_hourly:
                out.append(_cannot(snapshot, r, "REC-001", ["active_hours_per_month"],
                                   "Non-production workload on a plan with an hourly rate, but its actual runtime is unknown.",
                                   "محیط غیرعملیاتی روی پلنی با نرخ ساعتی است اما زمان واقعی اجرا مشخص نیست."))
            return out
        if r.active_hours_per_month >= hpm:
            return out
        if not has_hourly:
            pol = snapshot.provider_policy(r.provider_id) or {}
            out.append(_cannot(snapshot, r, "REC-001", ["hourly_price_toman"],
                               f"Runs {r.active_hours_per_month} h/month but no hourly rate for {r.provider_id} "
                               f"{r.sku or ''} is in the catalog. {pol.get('hourly_proration_note', '')}".strip(),
                               "نرخ ساعتی این ارائه‌دهنده در کاتالوگ موجود نیست؛ صرفه‌جویی زمان‌بندی قابل محاسبه نیست."))
            return out
        cand = price_resource(r.model_copy(update={"billing_mode": "hourly"}), snapshot, ctx)
        if cand.status == PriceStatus.EXACT and current.status == PriceStatus.EXACT:
            saving = current.monthly_total_toman - cand.monthly_total_toman
            if _worth_it(snapshot, saving, current.monthly_total_toman):
                rule = rules["REC-001"]
                out.append(_priced_rec(
                    snapshot, rule, r, current, cand, "high",
                    f"{r.name} ({r.environment}) is used {r.active_hours_per_month} h/month but billed monthly. "
                    f"Hourly billing for the same plan costs less.",
                    f"{r.name} ({r.environment}) ماهانه {r.active_hours_per_month} ساعت استفاده می‌شود ولی ماهانه محاسبه می‌شود؛ "
                    "محاسبه ساعتی همان پلن ارزان‌تر است.",
                    {"inputs": {"environment": r.environment, "active_hours_per_month": str(r.active_hours_per_month),
                                "hours_per_month_policy": str(hpm)},
                     "rule_condition": rule["applies_when"]}))
        return out

    # REC-004: cadence correction for any environment
    if has_hourly and r.active_hours_per_month is not None and current.status == PriceStatus.EXACT:
        other = "monthly" if r.billing_mode == "hourly" else "hourly"
        if other == "hourly" and r.active_hours_per_month >= hpm:
            return out
        cand = price_resource(r.model_copy(update={"billing_mode": other}), snapshot, ctx)
        if cand.status == PriceStatus.EXACT:
            saving = current.monthly_total_toman - cand.monthly_total_toman
            if _worth_it(snapshot, saving, current.monthly_total_toman):
                rule = rules["REC-004"]
                out.append(_priced_rec(
                    snapshot, rule, r, current, cand, "high",
                    f"For {r.active_hours_per_month} h/month, {other} billing of {r.sku} is cheaper than {r.billing_mode}.",
                    f"برای {r.active_hours_per_month} ساعت در ماه، صورتحساب {other} برای {r.sku} ارزان‌تر است.",
                    {"inputs": {"billing_mode": r.billing_mode, "active_hours_per_month": str(r.active_hours_per_month)}}))
    return out


def _term_discount_info(snapshot: CatalogSnapshot, r: Resource) -> list[Recommendation]:
    pol = snapshot.provider_policy(r.provider_id) or {}
    rid = pol.get("term_discount_rule")
    rule = snapshot.billing_rules.get(rid) if rid else None
    if rule is None or rule.status == "active":
        return []
    rec_rule = _rules(snapshot)["REC-004"]
    return [Recommendation(
        key=_key("REC-004-info", r.id, rid), rule_id="REC-004", type=rec_rule["type"], status="informational",
        title_en=f"Term discount published by {r.provider_id} (unverified)",
        title_fa=f"تخفیف دوره‌ای اعلام‌شده توسط {r.provider_id} (تأییدنشده)",
        resource_id=r.id, resource_name=r.name, provider_id=r.provider_id, risk="low", effort="low",
        confidence="unverified",
        summary_en=f"{r.provider_id} lists longer-term discounts (rule {rid}, status '{rule.status}'). No saving is "
                   "calculated until the discount is verified at checkout.",
        summary_fa=f"{r.provider_id} برای دوره‌های بلندمدت تخفیف اعلام کرده (قانون {rid}). تا تأیید در صفحه پرداخت، صرفه‌جویی محاسبه نمی‌شود.",
        evidence={"billing_rule": rule.model_dump(mode="json")},
    )]


# ---------------------------------------------------------------- REC-002


def _ceil_needed(alloc: Decimal, p95: Decimal, headroom: Decimal) -> Decimal:
    return (alloc * p95 / 100 * headroom)


def _downsize(snapshot: CatalogSnapshot, r: Resource, current: PriceBreakdown, ctx: BillingContext) -> list[Recommendation]:
    rule = _rules(snapshot)["REC-002"]
    p = rule["params"]
    if r.service_type != "compute_vm":
        return []
    m = r.metrics
    missing = []
    if m is None or m.p95_cpu_percent is None:
        missing.append("metrics.p95_cpu_percent")
    if m is None or m.p95_ram_percent is None:
        missing.append("metrics.p95_ram_percent")
    if m is None or m.observation_days is None or m.observation_days < int(p["min_observation_days"]):
        missing.append(f"metrics.observation_days>={p['min_observation_days']}")
    if missing:
        return [_cannot(snapshot, r, "REC-002", missing,
                        "Rightsizing needs usage evidence (p95 CPU/RAM over enough days). Allocation alone is not used.",
                        "کوچک‌سازی نیازمند شواهد مصرف (p95 پردازنده/حافظه در بازه کافی) است؛ تخصیص منابع به‌تنهایی ملاک نیست.",
                        handoff_reason="No usage telemetry: an observation/monitoring setup is needed before rightsizing.")]
    if m.p95_cpu_percent > Decimal(p["max_p95_cpu_percent"]) or m.p95_ram_percent > Decimal(p["max_p95_ram_percent"]):
        return []
    if current.status != PriceStatus.EXACT:
        return []
    src = resolve_specs(r, snapshot)
    head = Decimal(p["headroom_factor"])
    need_cpu = _ceil_needed(src.cpu_cores, m.p95_cpu_percent, head)
    need_ram = _ceil_needed(src.ram_gb, m.p95_ram_percent, head)
    # Without a measured disk usage, the candidate must keep at least the current allocation.
    need_disk = m.disk_used_gb * head if m.disk_used_gb is not None else src.storage_gb
    inputs = {"p95_cpu_percent": str(m.p95_cpu_percent), "p95_ram_percent": str(m.p95_ram_percent),
              "observation_days": m.observation_days, "headroom_factor": str(head),
              "required_cpu_cores": str(need_cpu), "required_ram_gb": str(need_ram),
              "required_storage_gb": str(need_disk), "metrics_source": m.source}
    best: tuple[PriceBreakdown, Resource, Any] | None = None
    pol = snapshot.provider_policy(r.provider_id) or {}
    if pol.get("strategy") == "component":
        cores = Decimal(math.ceil(need_cpu)) if need_cpu > 0 else Decimal(1)
        ram = need_ram.to_integral_value(rounding=ROUND_CEILING) if need_ram > 0 else Decimal(1)
        if cores < src.cpu_cores or ram < src.ram_gb:
            cand_r = src.model_copy(update={"cpu_cores": min(cores, src.cpu_cores), "ram_gb": min(ram, src.ram_gb)})
            bd = price_resource(cand_r, snapshot, ctx)
            if bd.status == PriceStatus.EXACT:
                best = (bd, cand_r, None)
    else:
        row = _plan_row(snapshot, src)
        if row is None:
            return []
        for cand in snapshot.provider_items(src.provider_id):
            if (cand.service_type != row.service_type or cand.product_family != row.product_family
                    or cand.sku == row.sku or cand.availability != "available"):
                continue
            if cand.cpu_cores is None or cand.ram_gb is None or cand.cpu_cores < need_cpu or cand.ram_gb < need_ram:
                continue
            if need_disk is not None and (cand.storage_gb is None or cand.storage_gb < need_disk):
                continue
            if row.cpu_shared is False and cand.cpu_shared is not False:
                continue
            cand_r = src.model_copy(update={"sku": cand.sku, "cpu_cores": cand.cpu_cores, "ram_gb": cand.ram_gb,
                                            "storage_gb": cand.storage_gb})
            bd = price_resource(cand_r, snapshot, ctx)
            if bd.status != PriceStatus.EXACT or bd.monthly_total_toman >= current.monthly_total_toman:
                continue
            if best is None or bd.monthly_total_toman < best[0].monthly_total_toman:
                best = (bd, cand_r, cand)
    if best is None:
        return []
    bd, cand_r, row = best
    saving = current.monthly_total_toman - bd.monthly_total_toman
    if not _worth_it(snapshot, saving, current.monthly_total_toman):
        return []
    conf = "high" if m.observation_days >= 30 else "medium"
    label = row.sku if row is not None else f"{cand_r.cpu_cores} vCPU / {cand_r.ram_gb} GB"
    return [_priced_rec(
        snapshot, rule, r, current, bd, conf,
        f"{r.name}: p95 CPU {m.p95_cpu_percent}% and p95 RAM {m.p95_ram_percent}% over {m.observation_days} days. "
        f"{label} covers p95 x {head} headroom.",
        f"{r.name}: مصرف p95 پردازنده {m.p95_cpu_percent}٪ و حافظه {m.p95_ram_percent}٪ در {m.observation_days} روز. "
        f"{label} با ضریب اطمینان {head} کافی است.",
        {"inputs": inputs, "candidate_sku": label, "never_from_allocation_alone": True})]


# ---------------------------------------------------------------- REC-003


def _migration(snapshot: CatalogSnapshot, r: Resource, current: PriceBreakdown, ctx: BillingContext,
               org: OrgSettings) -> list[Recommendation]:
    rule = _rules(snapshot)["REC-003"]
    if current.status != PriceStatus.EXACT:
        return []
    eq = find_equivalents(r, snapshot, ctx)
    allowed = {"high"} if rule["params"]["min_confidence"] == "high" else {"high", "medium"}
    best: Comparison | None = None
    for c in eq.candidates:
        if c.confidence not in allowed or not c.exact or c.monthly_saving_toman is None:
            continue
        if not _worth_it(snapshot, c.monthly_saving_toman, current.monthly_total_toman):
            continue
        if best is None or c.monthly_saving_toman > best.monthly_saving_toman:
            best = c
    if best is None:
        return []
    days = Decimal(str(rule["params"]["migration_effort_days"].get(r.service_type, "2")))
    migration_cost = payback = None
    payback_status = "UNKNOWN_MIGRATION_COST"
    if org.engineer_day_rate_toman is not None:
        migration_cost = days * r.quantity * org.engineer_day_rate_toman
        payback = (migration_cost / best.monthly_saving_toman).quantize(PCT)
        payback_status = "computed"
    differences = [d.model_dump(mode="json") for d in best.differences if d.verdict != "same"]
    return [_priced_rec(
        snapshot, rule, r, current, best.candidate, best.confidence,
        f"{best.candidate_label} passes all hard constraints (fit {best.fit_score}, confidence {best.confidence}). "
        f"Review the listed differences before migrating.",
        f"{best.candidate_label} همه محدودیت‌های سخت را پاس می‌کند (امتیاز تطابق {best.fit_score}، اطمینان {best.confidence}). "
        "پیش از مهاجرت تفاوت‌ها را بررسی کنید.",
        {"candidate_label": best.candidate_label, "fit_score": str(best.fit_score),
         "score_breakdown": {k: str(v) for k, v in best.score_breakdown.items()},
         "constraints": [c.model_dump(mode="json") for c in best.constraints], "differences": differences,
         "migration_effort_days_per_instance": str(days),
         "engineer_day_rate_toman": str(org.engineer_day_rate_toman) if org.engineer_day_rate_toman is not None else None,
         "alternatives_considered": len(eq.candidates) + len(eq.rejected)},
        one_time_migration_cost_toman=migration_cost, payback_months=payback, payback_status=payback_status,
        pendar_handoff=_handoff(snapshot, rule.get("pendar_service"),
                                "Cross-provider move: optional implementation help. Does not change the numbers above."),
    )]


# ---------------------------------------------------------------- public API


def recommend(resources: list[Resource], snapshot: CatalogSnapshot, ctx: BillingContext | None = None,
              org: OrgSettings | None = None) -> list[Recommendation]:
    ctx = ctx or BillingContext()
    org = org or OrgSettings()
    out: list[Recommendation] = []
    for r in resources:
        current = price_resource(r, snapshot, ctx)
        if current.status != PriceStatus.EXACT:
            fields = sorted({u.missing_field for u in current.unavailable})
            out.append(_cannot(snapshot, r, "ALL", fields,
                               "The current cost of this resource cannot be priced exactly, so no saving can be computed: "
                               + "; ".join(u.reason for u in current.unavailable),
                               "هزینه فعلی این منبع به‌طور دقیق قابل محاسبه نیست؛ بنابراین صرفه‌جویی محاسبه نمی‌شود."))
            continue
        out.extend(_cadence_rules(snapshot, r, current, ctx))
        out.extend(_downsize(snapshot, r, current, ctx))
        out.extend(_migration(snapshot, r, current, ctx, org))
        out.extend(_term_discount_info(snapshot, r))
        if org.engineer_day_rate_toman is None and any(x.rule_id == "REC-003" and x.resource_id == r.id for x in out):
            out.append(_cannot(snapshot, r, "REC-003", ["organization.engineer_day_rate_toman"],
                               "Migration payback needs your engineer day rate (Settings).",
                               "برای محاسبه بازگشت سرمایه مهاجرت، نرخ روزانه مهندس را در تنظیمات وارد کنید."))
    order = {"actionable": 0, "informational": 1, "cannot_determine": 2}
    out.sort(key=lambda x: (order[x.status], -(x.monthly_saving_toman or 0)))
    return out


def summarize(recs: list[Recommendation], current_total_toman: Decimal | None, snapshot: CatalogSnapshot) -> dict[str, Any]:
    """Avoidable spend = per resource, the single largest actionable saving (alternatives are not additive)."""
    best: dict[str, Recommendation] = {}
    for x in recs:
        if x.status != "actionable" or x.monthly_saving_toman is None or x.resource_id is None:
            continue
        if x.resource_id not in best or x.monthly_saving_toman > best[x.resource_id].monthly_saving_toman:
            best[x.resource_id] = x
    avoidable = sum((x.monthly_saving_toman for x in best.values()), Decimal(0))
    pct = (avoidable * 100 / current_total_toman).quantize(PCT) if current_total_toman else None
    threshold = Decimal(str(snapshot.recommendation_rules["handoff_policy"]["cost_cut_min_total_monthly_saving_toman"]))
    handoff = _handoff(snapshot, "pendar_cost_cut", "Large total saving identified; optional hands-on implementation.") \
        if avoidable >= threshold else None
    return {
        "avoidable_monthly_toman": avoidable,
        "potential_saving_percent": pct,
        "counted_recommendation_keys": sorted(x.key for x in best.values()),
        "method": "Per resource, only the largest actionable saving is counted; alternatives for the same resource are not added.",
        "actionable_count": sum(1 for x in recs if x.status == "actionable"),
        "cannot_determine_count": sum(1 for x in recs if x.status == "cannot_determine"),
        "pendar_handoff": handoff.model_dump() if handoff else None,
    }
