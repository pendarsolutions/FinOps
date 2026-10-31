from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from shared_types import InventoryDraft, ResourceDraft

DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫٬", "01234567890123456789.,")

REDACTIONS = [
    ("iban", re.compile(r"\bIR\d{2}[\s-]?(?:\d{4}[\s-]?){5}\d{2}\b", re.I)),
    ("card", re.compile(r"\b(?:\d{4}[\s-]?){3}\d{4}\b")),
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("phone", re.compile(r"(?:\+98|0098|\b0)9\d{9}\b")),
    ("labelled_id", re.compile(r"((?:customer|account|client|user|national|tax|economic)\s*(?:id|no|number|code)?|"
                               r"شناسه(?:\s*(?:مشتری|حساب|ملی|اقتصادی|کاربری))?|کد\s*(?:مشتری|ملی|اقتصادی|اشتراک)|"
                               r"شماره\s*(?:حساب|مشتری|اشتراک))\s*[:：#]?\s*[\w-]{4,}", re.I)),
    ("national_id", re.compile(r"\b\d{10}\b")),
]

PROVIDER_HINTS = {
    "arvancloud": ["arvancloud", "arvan", "آروان"], "liara": ["liara", "لیارا"],
    "serverir": ["server.ir", "سرور.آی‌آر", "سرور آی آر"], "iranserver": ["iranserver", "ایران سرور", "ایران‌سرور"],
    "chabokan": ["chabokan", "چابکان"], "parspack": ["parspack", "پارس پک", "پارس‌پک"],
    "mobinhost": ["mobinhost", "مبین هاست", "مبین‌هاست"], "abrha": ["abrha", "ابرها"],
}


@dataclass
class InvoiceLine:
    text: str
    matched_sku: str | None
    provider_id: str | None
    quantity: Decimal | None
    amount: Decimal | None
    amount_currency: str
    confidence: float


@dataclass
class InvoiceExtraction:
    draft: InventoryDraft
    detected_currency: Literal["TOMAN", "RIAL", "UNKNOWN"]
    currency_evidence: list[str]
    currency_confirmation_required: bool
    provider_id: str | None
    lines: list[InvoiceLine] = field(default_factory=list)
    redaction_counts: dict[str, int] = field(default_factory=dict)
    unmatched_lines: list[str] = field(default_factory=list)
    text_chars: int = 0

    def meta(self) -> dict[str, Any]:
        return {
            "detected_currency": self.detected_currency, "currency_evidence": self.currency_evidence,
            "currency_confirmation_required": self.currency_confirmation_required, "provider_id": self.provider_id,
            "redaction_counts": self.redaction_counts, "unmatched_lines": self.unmatched_lines[:50],
            "lines": [{"text": l.text, "matched_sku": l.matched_sku, "provider_id": l.provider_id,
                       "quantity": str(l.quantity) if l.quantity is not None else None,
                       "invoice_amount": str(l.amount) if l.amount is not None else None,
                       "invoice_amount_currency": l.amount_currency, "confidence": l.confidence} for l in self.lines],
            "note": "Invoice amounts are evidence only; costs are recomputed from the versioned catalog.",
        }


def extract_text(data: bytes, kind: str) -> str:
    if kind == "application/pdf":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if kind == "text/csv":
        rows = csv.reader(io.StringIO(data.decode("utf-8-sig")))
        return "\n".join(" | ".join(c.strip() for c in row) for row in rows)
    raise ValueError("image invoices need OCR, which is not available in this deployment; upload a PDF or CSV")


def redact(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for name, pattern in REDACTIONS:
        text, n = pattern.subn(f"[REDACTED:{name}]", text)
        if n:
            counts[name] = n
    return text, counts


def detect_currency(text: str) -> tuple[Literal["TOMAN", "RIAL", "UNKNOWN"], list[str]]:
    t = text.lower()
    rial = re.findall(r"ریال|rial|\birr\b", t)
    toman = re.findall(r"تومان|toman|\birt\b", t)
    evidence = [f"'{w}' x{len(rial)}" for w in set(rial)] + [f"'{w}' x{len(toman)}" for w in set(toman)]
    if rial and not toman:
        return "RIAL", evidence
    if toman and not rial:
        return "TOMAN", evidence
    return "UNKNOWN", evidence or ["no currency word found"]


def _amount(line: str) -> Decimal | None:
    nums = re.findall(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{5,}(?:\.\d+)?", line)
    if not nums:
        return None
    try:
        return Decimal(nums[-1].replace(",", ""))
    except InvalidOperation:
        return None


def parse_invoice(text: str, sku_map: dict[str, str], provider_names: dict[str, str] | None = None) -> InvoiceExtraction:
    """sku_map: exact catalog SKU (case-insensitive) -> provider_id."""
    norm = text.translate(DIGITS)
    redacted, counts = redact(norm)
    currency, evidence = detect_currency(redacted)
    low = redacted.lower()
    providers = [pid for pid, keys in PROVIDER_HINTS.items() if any(k in low for k in keys)]
    invoice_provider = providers[0] if len(providers) == 1 else None
    lines: list[InvoiceLine] = []
    unmatched: list[str] = []
    sku_re = {sku: re.compile(rf"(?<![\w-]){re.escape(sku)}(?![\w-])", re.I) for sku in sku_map}
    qty_col: int | None = None
    header_seen = False
    for raw in redacted.splitlines():
        line = raw.strip()
        if not line:
            continue
        cells = [c.strip() for c in line.split("|")] if "|" in line else []
        is_header = False
        if cells and not header_seen and not any(rx.search(line) for rx in sku_re.values()):
            header_seen = is_header = True
            qty_col = next((i for i, c in enumerate(cells) if re.fullmatch(r"qty|quantity|count|تعداد", c, re.I)), None)
        if is_header:
            continue
        hit = next((s for s, rx in sku_re.items() if rx.search(line)), None)
        if hit is None:
            # every unmatched CSV data row is surfaced; free text only when it looks like infrastructure
            if cells and any(c for c in cells):
                unmatched.append(line)
            elif re.search(r"vps|server|سرور|cloud|ابر|plan|پلن", line, re.I) and _amount(line) is not None:
                unmatched.append(line)
            continue
        pid = sku_map[hit]
        qty = None
        if qty_col is not None and qty_col < len(cells) and re.fullmatch(r"\d+", cells[qty_col]):
            qty = Decimal(cells[qty_col])
        elif m := re.search(r"(?:qty|quantity|تعداد)\s*[:：]?\s*(\d+)|\b(\d+)\s*(?:x|عدد)\b|\bx\s*(\d+)\b", line, re.I):
            qty = Decimal(m.group(1) or m.group(2) or m.group(3))
        conf = 0.95 if (invoice_provider in (None, pid)) else 0.6
        lines.append(InvoiceLine(text=line, matched_sku=hit, provider_id=pid, quantity=qty, amount=_amount(line),
                                 amount_currency=currency, confidence=conf))
    resources: list[ResourceDraft] = []
    for i, l in enumerate(lines):
        resources.append(ResourceDraft(
            name=f"{l.matched_sku}-{i + 1}", provider_id=l.provider_id, sku=l.matched_sku, quantity=l.quantity,
            service_type="compute_vm" if not (l.matched_sku or "").upper().startswith(("PAAS", "DBAAS", "OBJECT"))
            else ("paas" if l.matched_sku.upper().startswith("PAAS") else "dbaas" if l.matched_sku.upper().startswith("DBAAS")
                  else "object_storage"),
            field_confidence={"sku": l.confidence, "provider_id": l.confidence,
                              "quantity": 0.9 if l.quantity is not None else 0.4, "environment": 0.0,
                              "expected_monthly_download_gb": 0.0},
            notes=f"From invoice line: {l.text[:200]}",
        ))
        if resources[-1].quantity is None:
            resources[-1].quantity = Decimal(1)
    questions = []
    if currency == "UNKNOWN":
        questions.append("Is this invoice in Rial (ریال) or Toman (تومان)? It could not be determined automatically.")
    if unmatched:
        questions.append(f"{len(unmatched)} invoice line(s) look like infrastructure but did not match a catalog plan; "
                         "add them manually.")
    questions.append("Invoices do not show environment or monthly traffic - please fill them in for each row.")
    return InvoiceExtraction(
        draft=InventoryDraft(name="Invoice draft", resources=resources, questions=questions, detected_currency=currency),
        detected_currency=currency, currency_evidence=evidence, currency_confirmation_required=currency == "UNKNOWN",
        provider_id=invoice_provider, lines=lines, redaction_counts=counts, unmatched_lines=unmatched,
        text_chars=len(text),
    )
