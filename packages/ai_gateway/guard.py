"""Evidence guard: every number in an AI answer must have been returned by a deterministic tool
(or typed by the user). Anything else is an unsupported financial claim and the answer is rejected."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")
NUM_RE = re.compile(r"\d[\d,٬]*(?:\.\d+)?")
#: small integers used for list numbering / counts in prose are allowed
SMALL_INT_MAX = Decimal(10)


def numbers_in(text: str) -> set[Decimal]:
    out: set[Decimal] = set()
    for m in NUM_RE.finditer(text.translate(DIGITS)):
        raw = m.group(0).replace(",", "").replace("٬", "").rstrip(".")
        try:
            out.add(Decimal(raw).normalize())
        except InvalidOperation:
            continue
    return out


def numbers_in_json(obj: Any) -> set[Decimal]:
    return numbers_in(json.dumps(obj, ensure_ascii=False, default=str))


@dataclass
class GuardResult:
    ok: bool
    unsupported: list[str] = field(default_factory=list)
    checked: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "unsupported_numbers": self.unsupported, "numbers_checked": self.checked}


def check_numbers(answer: str, tool_outputs: list[Any], user_text: str = "") -> GuardResult:
    allowed = numbers_in_json(tool_outputs) | numbers_in(user_text)
    found = numbers_in(answer)
    bad = sorted(format(n, "f") for n in found if n not in allowed and not (n == n.to_integral_value() and n <= SMALL_INT_MAX))
    return GuardResult(ok=not bad, unsupported=bad, checked=len(found))
