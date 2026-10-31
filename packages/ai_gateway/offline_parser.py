"""Deterministic Persian/English infrastructure-description parser (no LLM).

Used when no LLM provider is configured, and as the fallback when the LLM refuses or fails.
It only extracts what is literally stated; anything unclear becomes a clarifying question with a
low field confidence - it never guesses runtimes, traffic or prices.
"""

from __future__ import annotations

import re
from decimal import Decimal

from shared_types import InventoryDraft, ResourceDraft

DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")
NUM_WORDS = {
    "یک": 1, "یه": 1, "دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "شیش": 6, "هفت": 7, "هشت": 8, "نه": 9, "ده": 10,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
PROVIDERS = {
    "arvancloud": ["آروان", "arvan"], "liara": ["لیارا", "liara"], "serverir": ["server.ir", "سرور.آی", "سرور آی آر"],
    "iranserver": ["ایران سرور", "ایران‌سرور", "iranserver"], "chabokan": ["چابکان", "chabokan"],
    "parspack": ["پارس پک", "پارس‌پک", "parspack"], "mobinhost": ["مبین هاست", "مبین‌هاست", "mobinhost"],
    "abrha": ["ابرها", "abrha"],
}
ENVIRONMENTS = {
    "production": ["production", "prod", "پروداکشن", "عملیاتی", "اصلی"],
    "staging": ["staging", "stage", "استیجینگ", "استیج"],
    "dev": ["dev", "development", "توسعه", "دولوپ"],
    "test": ["test", "testing", "تست"],
    "ci": [" ci ", "ci/cd", "gitlab runner", "runner", "رانر"],
}
SERVER_WORDS = r"(?:سرور|ماشین|vm|vms|server|servers|vps|instance|instances)"
COUNT_WORD = r"(\d+|" + "|".join(NUM_WORDS) + r")"
LOW, MID, HIGH = 0.5, 0.7, 0.9


def _norm(text: str) -> str:
    t = text.translate(DIGITS).replace("‌", " ")
    return re.sub(r"\s+", " ", t).strip()


def _num(tok: str) -> Decimal:
    tok = tok.strip().lower()
    return Decimal(NUM_WORDS[tok]) if tok in NUM_WORDS else Decimal(tok)


def _find_provider(text: str) -> str | None:
    low = text.lower()
    hits = [pid for pid, keys in PROVIDERS.items() if any(k in low for k in keys)]
    return hits[0] if len(hits) == 1 else None


def _find_env(text: str) -> str | None:
    low = f" {text.lower()} "
    for env, keys in ENVIRONMENTS.items():
        if any(k in low for k in keys):
            return env
    return None


def _specs(clause: str) -> dict[str, Decimal]:
    s: dict[str, Decimal] = {}
    if m := re.search(r"(\d+(?:\.\d+)?)\s*(?:گیگ|گیگابایت|gb|g)\s*(?:رم|ram|memory|حافظه)", clause, re.I):
        s["ram_gb"] = Decimal(m.group(1))
    elif m := re.search(r"(?:رم|ram)\s*(\d+(?:\.\d+)?)\s*(?:گیگ|gb)?", clause, re.I):
        s["ram_gb"] = Decimal(m.group(1))
    if m := re.search(r"(\d+)\s*(?:هسته|core|cores|vcpu|vcore|cpu)", clause, re.I):
        s["cpu_cores"] = Decimal(m.group(1))
    if m := re.search(r"(\d+)\s*(?:گیگ|گیگابایت|gb|g|ترابایت|tb)\s*(?:دیسک|هارد|disk|ssd|nvme|storage|فضا)", clause, re.I):
        mult = Decimal(1024) if re.search(r"ترابایت|tb", m.group(0), re.I) else Decimal(1)
        s["storage_gb"] = Decimal(m.group(1)) * mult
    if m := re.search(r"(\d+)\s*(?:گیگ|gb)\s*(?:ترافیک|traffic|دانلود|download)", clause, re.I):
        s["expected_monthly_download_gb"] = Decimal(m.group(1))
    if m := re.search(r"(\d+)\s*(?:ساعت|hours|h)\s*(?:در|per|/)\s*(?:ماه|month)", clause, re.I):
        s["active_hours_per_month"] = Decimal(m.group(1))
    return s


def _business_hours(clause: str) -> bool:
    return bool(re.search(r"ساعت کاری|ساعات اداری|business hours|office hours|working hours", clause, re.I))


SERVER_COUNT_RE = re.compile(COUNT_WORD + r"\s*(?:تا|عدد)?\s*" + SERVER_WORDS, re.I)
GROUP_RE = re.compile(COUNT_WORD + r"\s*(?:تا|تاش|تاشون|of them|x)\b|(یکی|دوتا|سه‌?تا|چهارتا)(?:شون|ش)", re.I)


def _starts_clause(piece: str) -> bool:
    return bool(_find_env(piece) or _find_provider(piece) or GROUP_RE.search(piece) or SERVER_COUNT_RE.search(piece))


def _clauses(norm: str) -> list[str]:
    """Sentences, further split on 'and/و/plus/,' only where the next piece introduces a new subject."""
    out: list[str] = []
    for sentence in re.split(r"\.(?:\s|$)|[؛;\n!؟?]", norm):  # keep 'Server.ir' intact
        pieces = [p.strip() for p in re.split(r"\s(?:و|and|plus)\s|[،,]\s*(?:plus\s)?", sentence) if p and p.strip()]
        for i, p in enumerate(pieces):
            if i == 0 or _starts_clause(p):
                out.append(p)
            else:
                out[-1] += " " + p
    return [c for c in out if c]


def parse_description(text: str, known_skus: dict[str, str] | None = None) -> InventoryDraft:
    """known_skus maps an exact SKU token (case-insensitive) to its provider_id, from the catalog."""
    norm = _norm(text)
    clauses = _clauses(norm)
    questions: list[str] = []
    global_provider = _find_provider(norm)
    resources: list[ResourceDraft] = []

    # "we have 3 servers" stated on its own (no specs in that clause) is the declared total
    total = None
    for c in clauses:
        m = SERVER_COUNT_RE.search(c)
        if m and not _specs(c) and not any(re.search(re.escape(s), c, re.I) for s in (known_skus or {})):
            total = _num(m.group(1))
            break

    for clause in clauses:
        sku_hit = None
        for sku, pid in (known_skus or {}).items():
            if re.search(rf"(?<![\w-]){re.escape(sku)}(?![\w-])", clause, re.I):
                sku_hit = (sku, pid)
                break
        specs = _specs(clause)
        if not specs and not sku_hit:
            continue
        qty = None
        if group := GROUP_RE.search(clause):
            g = group.group(1) or group.group(2)
            qty = Decimal({"یکی": 1, "دوتا": 2, "سهتا": 3, "سه‌تا": 3, "چهارتا": 4}.get(g, 0)) or _num(g)
        elif count := SERVER_COUNT_RE.search(clause):
            qty = _num(count.group(1))
        conf = {k: MID for k in specs}
        d = ResourceDraft(
            name=f"server-{len(resources) + 1}", service_type="compute_vm",
            provider_id=(sku_hit[1] if sku_hit else _find_provider(clause) or global_provider),
            sku=sku_hit[0] if sku_hit else None, environment=_find_env(clause), quantity=qty, **specs,
            field_confidence={**conf, **({"sku": HIGH, "provider_id": HIGH} if sku_hit else {})},
        )
        if d.environment:
            d.field_confidence["environment"] = MID
        resources.append(d)

    assigned = sum((r.quantity or Decimal(1)) for r in resources)
    remainder = (total - assigned) if total is not None else None
    env_clauses = [(c, _find_env(c)) for c in clauses if _find_env(c)]
    if remainder and remainder > 0:
        env_clause = next((c for c, e in env_clauses if not _specs(c)), None)
        d = ResourceDraft(name=f"server-{len(resources) + 1}", service_type="compute_vm", provider_id=global_provider,
                          quantity=remainder, environment=_find_env(env_clause) if env_clause else None,
                          field_confidence={"quantity": MID, "environment": LOW},
                          notes="Specs not stated in the description.")
        resources.append(d)
        questions.append(f"{remainder} server(s) have no CPU/RAM/disk stated - what are their specs or plan?")
    if total is not None and resources and assigned > total:
        questions.append("The server counts in the description do not add up - please check the quantities.")

    for clause in clauses:
        if _business_hours(clause):
            env = _find_env(clause)
            target = next((r for r in resources if env and r.environment == env), None)
            name = target.name if target else "the scheduled server"
            questions.append(f"'{clause}': how many hours per month does {name} actually run? "
                             "(Business hours are not converted to a number automatically.)")
            if target:
                target.billing_mode = None
                target.field_confidence["active_hours_per_month"] = LOW
    for r in resources:
        if r.quantity is None:
            r.quantity = Decimal(1)
            r.field_confidence["quantity"] = LOW
        if r.provider_id is None:
            questions.append(f"Which provider hosts {r.name}?")
        if r.expected_monthly_download_gb is None:
            r.field_confidence.setdefault("expected_monthly_download_gb", LOW)
    if not resources:
        questions.append("No servers or specs were recognised. Please list each server with provider, plan or "
                         "CPU/RAM/disk, environment and monthly traffic.")
    return InventoryDraft(name="Chat draft", resources=resources, questions=_dedupe(questions))


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out
