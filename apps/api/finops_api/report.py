"""Downloadable bilingual HTML report. Every number comes from the stored quote / recommendations."""

from __future__ import annotations

import re
from decimal import Decimal
from html import escape
from typing import Any

from sqlalchemy.orm import Session

from .dates import fa_number, format_day
from .orm import Inventory, QuoteRow
from .security import Principal
from .services import latest_analysis, latest_quote, rec_view, resources_of, run_recommendations, snapshot

T = {
    "title": ("گزارش FinOps agent", "FinOps agent report"),
    "s1": ("۱. خلاصه مدیریتی", "1. Executive summary"),
    "s2": ("۲. فهرست منابع تأییدشده", "2. Confirmed inventory"),
    "s3": ("۳. هزینه ماهانه فعلی", "3. Current monthly cost"),
    "s4": ("۴. ریز هزینه‌ها", "4. Cost breakdown"),
    "s5": ("۵. اتلاف و فرصت‌ها", "5. Waste / opportunities"),
    "s6": ("۶. گزینه‌های جایگزین ارائه‌دهندگان", "6. Cross-provider alternatives"),
    "s7": ("۷. جزئیات پیشنهادها", "7. Recommendation details"),
    "s8": ("۸. مهاجرت و بازگشت سرمایه", "8. Migration / payback"),
    "s9": ("۹. فرضیات", "9. Assumptions"),
    "s10": ("۱۰. منابع قیمت و تاریخ‌ها", "10. Price sources and dates"),
    "s11": ("۱۱. داده‌های ناقص", "11. What data is missing"),
    "toman": ("تومان", "Toman"),
    "incomplete": ("قیمت‌گذاری کامل نیست؛ موارد PRICE_UNAVAILABLE در بخش ۱۱ آمده‌اند.",
                   "Pricing is incomplete; PRICE_UNAVAILABLE items are listed in section 11."),
    "avoidable": ("هزینه قابل اجتناب ماهانه", "Avoidable monthly spend"),
    "current": ("هزینه ماهانه فعلی", "Current monthly spend"),
    "none": ("موردی وجود ندارد.", "None."),
    "generated": ("تولیدشده از برآورد", "Generated from quote"),
    "catalog": ("نسخه کاتالوگ", "catalog"),
    "engine": ("نسخه موتور", "engine"),
    "rial": ("ریال", "Rial"),
    "price_unavailable": ("قیمت موجود نیست (PRICE_UNAVAILABLE)", "PRICE_UNAVAILABLE"),
}

#: table headers
H = {
    "resource": ("منبع", "Resource"), "provider": ("ارائه‌دهنده", "Provider"), "sku": ("پلن", "SKU"),
    "env": ("محیط", "Env"), "qty": ("تعداد", "Qty"), "vcpu": ("پردازنده", "vCPU"), "ram": ("حافظه (GB)", "RAM GB"),
    "disk": ("دیسک (GB)", "Disk GB"), "download": ("دانلود (GB)", "Download GB"),
    "runtime": ("ساعت کار در ماه", "Runtime h"), "component": ("جزء", "Component"), "status": ("وضعیت", "Status"),
    "unit_price": ("قیمت واحد", "Unit price"), "subtotal": ("جمع", "Subtotal"), "opportunity": ("فرصت", "Opportunity"),
    "saving": ("صرفه‌جویی ماهانه", "Saving/month"), "percent": ("درصد", "%"), "risk": ("ریسک", "Risk"),
    "effort": ("زحمت", "Effort"), "confidence": ("اطمینان", "Confidence"), "id": ("شناسه", "ID"),
    "alternative": ("جایگزین", "Alternative"), "fit": ("تطابق", "Fit"), "cost": ("هزینه ماهانه", "Cost/month"),
    "differences": ("تفاوت‌ها", "Differences"), "migration_cost": ("هزینه مهاجرت", "Migration cost"),
    "payback": ("بازگشت سرمایه (ماه)", "Payback (months)"), "source": ("منبع قیمت", "Source"),
    "retrieved": ("زمان خواندن", "Retrieved"), "price_date": ("تاریخ قیمت ارائه‌دهنده", "Provider price date"),
    "freshness": ("تازگی", "Freshness"), "item": ("مورد", "Item"), "missing": ("چه کم است", "Missing"),
    "why": ("چرا", "Why"),
}

#: status words, in the same words the app uses (apps/web/src/lib/plain.ts); anything unlisted is shown as is
V = {
    "low": "کم", "medium": "متوسط", "high": "زیاد", "unverified": "تأییدنشده", "NEEDS_HUMAN_REVIEW": "نیاز به بررسی",
    "not_equivalent": "معادل نیست", "priced": "قیمت دقیق", "included": "شامل است", "assumed_included": "فرض: شامل است",
    "unavailable": "بدون قیمت", "info": "برای اطلاع", "fresh": "تازه", "aging": "رو به قدیمی", "stale": "قدیمی",
    "unknown": "نامعلوم", "computed": "محاسبه‌شده", "UNKNOWN_MIGRATION_COST": "هزینه مهاجرت نامعلوم",
    "production": "عملیاتی", "staging": "پیش از انتشار", "development": "توسعه",
    "same": "یکسان", "better": "بهتر", "worse": "بدتر", "different": "متفاوت",
}

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ][\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)?")


def _t(key: str, lang: str) -> str:
    return T[key][0 if lang == "fa" else 1]


def money(v: Any, lang: str) -> str:
    if v is None:
        return _t("price_unavailable", lang)
    d = Decimal(str(v))
    s = f"{d:,.0f}" if d == d.to_integral_value() else f"{d:,}"
    return f"{fa_number(s) if lang == 'fa' else s} {_t('toman', lang)}"


_NUMBER = re.compile(r"-?[0-9][0-9,]*(?:[.][0-9]+)?")


def _value(v: Any, lang: str) -> str:
    """One cell. In Persian: status words translated, a date in Solar Hijri, a number in Persian digits. Anything
    else (names, plan codes, addresses) stays exactly as written."""
    if v is None:
        return "—"
    s = str(v)
    if lang != "fa":
        return s
    if s in V:
        return V[s]
    if _ISO_DATE.fullmatch(s):
        return format_day(s, "fa")
    if _NUMBER.fullmatch(s):
        return fa_number(s)
    return s


def _table(headers: list[str], rows: list[list[Any]], lang: str = "en") -> str:
    h = "".join(f"<th>{escape(H[x][0 if lang == 'fa' else 1] if x in H else str(x))}</th>" for x in headers)
    b = "".join("<tr>" + "".join(f"<td>{escape(_value(c, lang))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"


def _price_dates(items: list[str], lang: str) -> str:
    """The engine writes "<provider>: price date <ISO>" and "<provider>: retrieved <ISO>"."""
    text = ", ".join(items)
    if lang != "fa":
        return text
    text = text.replace(": price date ", ": تاریخ قیمت ").replace(": retrieved ", ": خوانده‌شده در ").replace(", ", "، ")
    return _ISO_DATE.sub(lambda m: format_day(m.group(0), "fa"), text)


def render_report(db: Session, p: Principal, inv: Inventory, lang: str) -> str:
    rows = latest_analysis(db, inv)
    if not rows:
        run_recommendations(db, p, inv)
        rows = latest_analysis(db, inv)
    quote: QuoteRow | None = db.get(QuoteRow, rows[0].quote_id) if rows else latest_quote(db, inv)
    recs = [rec_view(r) for r in rows]
    snap = snapshot(db)
    from .routers.analysis import _summary_from_rows

    summary = _summary_from_rows(rows, quote.total_toman if quote else None, db) if rows else {}
    c = quote.content if quote else {"breakdowns": [], "assumptions": [], "unavailable": [], "price_sources": []}
    fa = lang == "fa"
    actionable = sorted([r for r in recs if r["result_status"] == "actionable"],
                        key=lambda r: -(r["monthly_saving_toman"] or 0))
    blocked = [r for r in recs if r["result_status"] == "cannot_determine"]
    migrations = [r for r in actionable if r["rule_id"] == "REC-003"]
    parts: list[str] = []

    def section(key: str, body: str) -> None:
        parts.append(f"<section><h2>{_t(key, lang)}</h2>{body}</section>")

    exec_lines = [f"<p><b>{_t('current', lang)}:</b> {money(quote.total_toman if quote else None, lang)}</p>"]
    if quote and not quote.complete:
        exec_lines.append(f"<p class='warn'>{_t('incomplete', lang)}</p>")
    if summary:
        exec_lines.append(f"<p><b>{_t('avoidable', lang)}:</b> {money(summary['avoidable_monthly_toman'], lang)} "
                          f"({_value(summary['potential_saving_percent'], lang)}%)</p>"
                          f"<p class='muted'>{escape(summary['method'])}</p>")
    exec_lines += [f"<p>• {escape(r['title_fa' if fa else 'title_en'])} — {escape(r['resource_name'] or '')}: "
                   f"{money(r['monthly_saving_toman'], lang)}</p>" for r in actionable[:3]]
    section("s1", "".join(exec_lines))
    res_rows = resources_of(db, inv)
    section("s2", _table(["resource", "provider", "sku", "env", "qty", "vcpu", "ram", "disk", "download", "runtime"],
                         [[r.name, r.provider_id, r.sku or r.resource_class, r.environment, r.quantity, r.cpu_cores,
                           r.ram_gb, r.storage_gb, r.expected_monthly_download_gb, r.active_hours_per_month]
                          for r in res_rows], lang))
    section("s3", f"<p class='big'>{money(quote.total_toman if quote else None, lang)}</p>"
                  + (f"<p class='muted'>{_t('rial', lang)}: "
                     f"{money(c.get('total_rial'), lang).replace(_t('toman', lang), _t('rial', lang))}</p>"
                     if c.get("total_rial") else ""))
    bd_rows = []
    for b in c["breakdowns"]:
        for l in b["components"]:
            bd_rows.append([b["resource_name"], b["provider_id"], l["description"], l["status"], l.get("quantity"),
                            money(l.get("unit_price_toman"), lang) if l.get("unit_price_toman") is not None else None,
                            money(l.get("subtotal_toman"), lang) if l.get("subtotal_toman") is not None else None])
    section("s4", _table(["resource", "provider", "component", "status", "qty", "unit_price", "subtotal"], bd_rows,
                         lang))
    section("s5", _table(["opportunity", "resource", "saving", "percent", "risk", "effort", "confidence", "id"],
                         [[r["title_fa" if fa else "title_en"], r["resource_name"], money(r["monthly_saving_toman"], lang),
                           r["monthly_saving_percent"], r["risk_level"], r["effort_level"], r["confidence"], r["id"]]
                          for r in actionable], lang) if actionable else f"<p>{_t('none', lang)}</p>")
    alt = []
    for r in migrations:
        ev = r["evidence"]
        diffs = "; ".join(f"{d['dimension']}: {d['source_value']} → {d['candidate_value']} "
                          f"({V.get(d['verdict'], d['verdict']) if fa else d['verdict']})"
                          for d in ev.get("differences", []))
        alt.append([r["resource_name"], ev.get("candidate_label"), ev.get("fit_score"), r["confidence"],
                    money(r["candidate_cost_toman"], lang), diffs])
    section("s6", _table(["resource", "alternative", "fit", "confidence", "cost", "differences"], alt, lang)
            if alt else f"<p>{_t('none', lang)}</p>")
    details = "".join(f"<div class='card'><h3>{escape(r['title_fa' if fa else 'title_en'])} [{r['id']}]</h3>"
                      f"<p>{escape(r['summary_fa' if fa else 'summary_en'])}</p>"
                      f"<p>{money(r['current_cost_toman'], lang)} → {money(r['candidate_cost_toman'], lang)}</p>"
                      f"<p class='muted'>{escape(_price_dates(r['price_dates'], lang))}</p></div>"
                      for r in actionable)
    section("s7", details or f"<p>{_t('none', lang)}</p>")
    section("s8", _table(["resource", "migration_cost", "saving", "payback", "status"],
                         [[r["resource_name"], money(r["one_time_migration_cost_toman"], lang)
                           if r["one_time_migration_cost_toman"] is not None else None,
                           money(r["monthly_saving_toman"], lang), r["payback_months"], r["payback_status"]]
                          for r in migrations], lang) if migrations else f"<p>{_t('none', lang)}</p>")
    section("s9", "<ul>" + "".join(f"<li>{escape(a)}</li>" for a in c["assumptions"]) + "</ul>")
    section("s10", _table(["provider", "source", "retrieved", "price_date", "freshness"],
                          [[s["provider_id"], s["source_url"], s["retrieved_at"], s["provider_price_date"], s["freshness"]]
                           for s in snap.source_freshness()], lang))
    missing = [[u["component"], u["missing_field"], u["reason"]] for u in c["unavailable"]]
    missing += [[r["resource_name"], ", ".join(r["missing_inputs"]), r["summary_fa" if fa else "summary_en"]]
                for r in blocked]
    section("s11", _table(["item", "missing", "why"], missing, lang) if missing else f"<p>{_t('none', lang)}</p>")
    footer = (f"<footer>{_t('generated', lang)} {quote.id if quote else '—'} · {_t('catalog', lang)} "
              f"{quote.catalog_version if quote else '—'} · {_t('engine', lang)} "
              f"{quote.deterministic_engine_version if quote else '—'}</footer>")
    direction = "rtl" if fa else "ltr"
    return f"""<!doctype html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_t('title', lang)} — {escape(inv.name)}</title>
<style>
body{{font-family:Vazirmatn,Tahoma,system-ui,sans-serif;margin:0 auto;max-width:1100px;padding:24px;color:#1f2430;background:#fff;line-height:1.7}}
h1{{font-size:26px}}h2{{border-bottom:2px solid #e3e6ee;padding-bottom:4px;margin-top:32px;font-size:19px}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}}th,td{{border:1px solid #e3e6ee;padding:6px;text-align:start;vertical-align:top}}
th{{background:#f4f6fa}}.muted{{color:#69708a;font-size:13px}}.warn{{color:#a4430a;font-weight:600}}.big{{font-size:24px;font-weight:700}}
.card{{border:1px solid #e3e6ee;border-radius:8px;padding:8px 14px;margin:8px 0}}footer{{margin-top:40px;color:#69708a;font-size:12px}}
@media print{{section{{break-inside:avoid}}}}
</style></head><body><h1>{_t('title', lang)} — {escape(inv.name)}</h1>{''.join(parts)}{footer}</body></html>"""
