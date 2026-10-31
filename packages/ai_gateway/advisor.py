"""AI advisor: orchestrates deterministic tools and explains their results.

System rule: if a number is not returned by a tool, do not state it. Enforced after generation by
guard.check_numbers - an answer with an unsupported number is regenerated once, then replaced by the
deterministic template answer.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import anthropic

from .guard import check_numbers
from .llm import FALLBACK_BETA, PROMPT_VERSION, LLMConfig, client_for

log = logging.getLogger(__name__)
MAX_STEPS = 8

ToolFn = Callable[[dict[str, Any]], Any]


def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required if required is not None else list(props),
            "additionalProperties": False}


TOOLS: list[dict[str, Any]] = [
    {"name": "get_inventory", "description": "Confirmed inventory rows (specs, environment, runtime, traffic) for the "
     "inventory in context.", "input_schema": _obj({})},
    {"name": "get_catalog_item", "description": "One current catalog price row with its source URL and dates.",
     "input_schema": _obj({"item_id": {"type": "string"}})},
    {"name": "price_inventory", "description": "Deterministic monthly quote for the inventory (per resource "
     "breakdown, assumptions, PRICE_UNAVAILABLE items). Returns the quote id.", "input_schema": _obj({})},
    {"name": "compare_providers", "description": "Equivalence-engine comparison of one inventory resource against "
     "compatible Iranian providers: hard constraints, fit score, confidence, exact costs and differences.",
     "input_schema": _obj({"resource_id": {"type": "string"}})},
    {"name": "list_recommendations", "description": "Deterministic recommendations from the latest analysis, with "
     "saving, risk, effort, confidence, evidence and recommendation ids.", "input_schema": _obj({})},
    {"name": "get_price_source", "description": "Official price sources and freshness (retrieved date, provider price "
     "date) for a provider.", "input_schema": _obj({"provider_id": {"type": "string"}})},
    {"name": "get_provider_documentation", "description": "Provider facts: pricing model, catalog quality, "
     "integration status, known data gaps.", "input_schema": _obj({"provider_id": {"type": "string"}})},
]
for _t in TOOLS:
    _t["strict"] = True

SYSTEM = """You are Pendar's FinOps advisor for Iranian small businesses.

You can only learn facts by calling the tools. Hard rules:
1. If a number is not returned by a tool, do not state it. Never add, subtract, multiply, average, convert currency or compute a saving or percentage yourself - quote the tool's numbers exactly, in Toman (تومان) unless the tool gave Rial.
2. Cite evidence ids for every claim: quote id, recommendation id, catalog version, or source URL + date.
3. If a tool reports PRICE_UNAVAILABLE, NEEDS_HUMAN_REVIEW or cannot_determine, say so and name the missing data. Never fill the gap.
4. Explain: what the deterministic engine found, why it matters, risk, effort, and the next action.
Answer in the user's language (Persian or English). Keep technical terms like FinOps, DevOps, Kubernetes, SLA, API in English."""


@dataclass
class AdvisorAnswer:
    answer: str
    path: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    guard: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


def _call(tools: dict[str, ToolFn], name: str, args: dict[str, Any], log_: list[dict[str, Any]]) -> Any:
    try:
        out = tools[name](args)
        log_.append({"tool": name, "input": args, "output": out, "error": None})
        return out
    except Exception as exc:  # noqa: BLE001 - tool errors go back to the model as is_error results
        log_.append({"tool": name, "input": args, "output": None, "error": str(exc)})
        raise


def _evidence(tool_log: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for entry in tool_log:
        out = entry.get("output")
        if not isinstance(out, dict):
            continue
        for key in ("quote_id", "catalog_version", "analysis_id"):
            if out.get(key) and out[key] not in ids:
                ids.append(str(out[key]))
        for rec in out.get("recommendations", []) or []:
            if isinstance(rec, dict) and rec.get("id") and rec["id"] not in ids:
                ids.append(rec["id"])
    return ids


# --------------------------------------------------------------------------- deterministic template


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    d = Decimal(str(v))
    return f"{d:,.0f}" if d == d.to_integral_value() else f"{d:,}"


def template_answer(question: str, lang: str, tools: dict[str, ToolFn], tool_log: list[dict[str, Any]]) -> str:
    quote = _call(tools, "price_inventory", {}, tool_log)
    recs = _call(tools, "list_recommendations", {}, tool_log)
    fa = lang == "fa"
    lines: list[str] = []
    if quote.get("complete"):
        lines.append((f"هزینه ماهانه فعلی (قطعی): {_fmt(quote['total_toman'])} تومان — شناسه quote: {quote['quote_id']}، "
                      f"نسخه کاتالوگ: {quote['catalog_version']}.") if fa else
                     (f"Current monthly cost (exact): {_fmt(quote['total_toman'])} Toman — quote {quote['quote_id']}, "
                      f"catalog {quote['catalog_version']}."))
    else:
        lines.append((f"قیمت‌گذاری کامل نیست؛ بخش قیمت‌گذاری‌شده: {_fmt(quote.get('priced_subtotal_toman'))} تومان. "
                      f"موارد PRICE_UNAVAILABLE باید تکمیل شوند (quote {quote.get('quote_id')}).") if fa else
                     (f"Pricing is incomplete; priced part: {_fmt(quote.get('priced_subtotal_toman'))} Toman. "
                      f"PRICE_UNAVAILABLE items must be resolved (quote {quote.get('quote_id')})."))
    actionable = [r for r in recs.get("recommendations", []) if r["result_status"] == "actionable"]
    blocked = [r for r in recs.get("recommendations", []) if r["result_status"] == "cannot_determine"]
    if summary := recs.get("summary"):
        lines.append((f"هزینه قابل اجتناب (بدون جمع گزینه‌های جایگزین یک منبع): {_fmt(summary.get('avoidable_monthly_toman'))} "
                      f"تومان در ماه ({summary.get('potential_saving_percent')}٪).") if fa else
                     (f"Avoidable spend (alternatives for one resource not added together): "
                      f"{_fmt(summary.get('avoidable_monthly_toman'))} Toman/month "
                      f"({summary.get('potential_saving_percent')}%)."))
    for r in actionable[:3]:
        title = r["title_fa"] if fa else r["title_en"]
        lines.append(f"• {title} — {r.get('resource_name')}: "
                     + (f"صرفه‌جویی {_fmt(r['monthly_saving_toman'])} تومان/ماه، ریسک {r['risk_level']}، "
                        f"تلاش {r['effort_level']}، اطمینان {r['confidence']} [{r['id']}]" if fa else
                        f"saves {_fmt(r['monthly_saving_toman'])} Toman/month, risk {r['risk_level']}, "
                        f"effort {r['effort_level']}, confidence {r['confidence']} [{r['id']}]"))
    if blocked:
        names = ", ".join(sorted({f"{b.get('resource_name') or '-'} ({', '.join(b['missing_inputs'])})" for b in blocked}))
        lines.append(("هنوز قابل تعیین نیست، داده لازم: " if fa else "Cannot determine yet — missing data: ") + names)
    if not actionable and not blocked:
        lines.append("پیشنهادی یافت نشد؛ ابتدا تحلیل را اجرا کنید." if fa else
                     "No recommendations yet — run the analysis first.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- LLM loop


def _llm_answer(cfg: LLMConfig, question: str, lang: str, tools: dict[str, ToolFn],
                tool_log: list[dict[str, Any]]) -> str:
    client = client_for(cfg)
    messages: list[dict[str, Any]] = [{"role": "user", "content": f"(language: {lang})\n{question}"}]
    retried_guard = False
    for _ in range(MAX_STEPS):
        resp = client.beta.messages.create(
            model=cfg.model, max_tokens=16000, betas=[FALLBACK_BETA], fallbacks="default", system=SYSTEM,
            tools=TOOLS, output_config={"effort": cfg.effort}, messages=messages,
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("model refusal")
        messages.append({"role": "assistant", "content": resp.content})  # append-only (keeps thinking blocks valid)
        uses = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason == "tool_use" and uses:
            results = []
            for u in uses:
                try:
                    out = _call(tools, u.name, dict(u.input or {}), tool_log)
                    results.append({"type": "tool_result", "tool_use_id": u.id,
                                    "content": json.dumps(out, ensure_ascii=False, default=str)})
                except Exception as exc:  # noqa: BLE001
                    results.append({"type": "tool_result", "tool_use_id": u.id, "content": f"Error: {exc}",
                                    "is_error": True})
            messages.append({"role": "user", "content": results})
            continue
        text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
        guard = check_numbers(text, [e["output"] for e in tool_log], question)
        if guard.ok or retried_guard:
            return text
        retried_guard = True
        messages.append({"role": "user", "content": "Your answer contains numbers that no tool returned: "
                         f"{', '.join(guard.unsupported)}. Rewrite it using only numbers exactly as returned by tools "
                         "(call tools again if needed)."})
    raise RuntimeError("advisor exceeded step limit")


def run_advisor(question: str, lang: str, tools: dict[str, ToolFn], *, provider: str,
                cfg: LLMConfig | None) -> AdvisorAnswer:
    tool_log: list[dict[str, Any]] = []
    path, meta = "offline_template", {"prompt_version": PROMPT_VERSION}
    answer = None
    if provider == "anthropic" and cfg is not None:
        try:
            answer = _llm_answer(cfg, question, lang, tools, tool_log)
            path, meta["model"] = "llm", cfg.model
        except (anthropic.APIConnectionError, anthropic.APIStatusError, RuntimeError) as exc:
            meta["fallback_reason"] = f"{type(exc).__name__}: {exc}"
    if answer is not None:
        guard = check_numbers(answer, [e["output"] for e in tool_log], question)
        if not guard.ok:
            meta["rejected_llm_answer_guard"] = guard.as_dict()
            answer = None
    if answer is None:
        answer = template_answer(question, lang, tools, tool_log)
        path = "offline_template" if path != "llm" else "template_after_guard_rejection"
    guard = check_numbers(answer, [e["output"] for e in tool_log], question)
    return AdvisorAnswer(answer=answer, path=path, tool_calls=[{k: v for k, v in e.items() if k != "output"}
                                                               for e in tool_log],
                         evidence_ids=_evidence(tool_log), guard=guard.as_dict(), meta=meta)
