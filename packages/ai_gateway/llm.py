"""Claude access (official Anthropic SDK). The model only parses text and explains tool results."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import anthropic

PROMPT_VERSION = "2026-10-04.1"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass
class LLMConfig:
    model: str = "claude-opus-5-5"
    api_key: str | None = None
    effort: str = "medium"


def client_for(cfg: LLMConfig) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=cfg.api_key) if cfg.api_key else anthropic.Anthropic()


class LLMRefusal(RuntimeError):
    pass


EXTRACTION_SYSTEM = """You convert a customer's description of their Iranian cloud/VPS infrastructure (Persian or English) into structured inventory rows for a FinOps tool.

Rules:
- Extract only what the text states. Use null for anything not stated. Never estimate traffic, runtime hours, specs or prices.
- Never output prices, costs or savings. Pricing is done later by a deterministic engine after the user reviews your rows.
- Convert Persian digits to ASCII digits. Numbers are strings (e.g. "4", "0.5").
- "Business hours" / "ساعت کاری" is not a number: leave active_hours_per_month null and add a question.
- provider_id must be one of the known provider ids or null. sku only when it exactly matches a known SKU.
- Give each extracted field a confidence in [0,1]; below 0.8 means the user must check it.
- Put every ambiguity in "questions", written in the user's language."""


def _nullable(t: str) -> dict[str, Any]:
    return {"type": ["string", "null"]} if t == "string" else {"type": [t, "null"]}


RESOURCE_FIELDS_STR = ["name", "environment", "provider_id", "sku", "resource_class", "datacenter", "quantity",
                       "cpu_cores", "ram_gb", "storage_gb", "storage_type", "expected_monthly_download_gb",
                       "expected_monthly_upload_gb", "active_hours_per_month", "billing_mode", "notes"]


def extraction_schema() -> dict[str, Any]:
    props: dict[str, Any] = {f: _nullable("string") for f in RESOURCE_FIELDS_STR}
    props["service_type"] = {"type": "string", "enum": ["compute_vm", "paas", "dbaas", "object_storage"]}
    props["requires_public_ipv4"] = _nullable("boolean")
    props["field_confidence"] = {"type": "array", "items": {
        "type": "object", "properties": {"field": {"type": "string"}, "confidence": {"type": "number"}},
        "required": ["field", "confidence"], "additionalProperties": False}}
    resource = {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    return {"type": "object", "properties": {
        "resources": {"type": "array", "items": resource},
        "questions": {"type": "array", "items": {"type": "string"}},
        "detected_currency": {"type": "string", "enum": ["TOMAN", "RIAL", "UNKNOWN"]},
    }, "required": ["resources", "questions", "detected_currency"], "additionalProperties": False}


def extract_inventory_json(cfg: LLMConfig, text: str, providers: list[str], known_skus: list[str]) -> dict[str, Any]:
    client = client_for(cfg)
    context = (f"Known provider ids: {', '.join(providers)}\nKnown SKUs: {', '.join(known_skus)}\n\n"
               f"<customer_text>\n{text}\n</customer_text>")
    resp = client.beta.messages.create(
        model=cfg.model, max_tokens=16000, betas=[FALLBACK_BETA], fallbacks="default",
        system=EXTRACTION_SYSTEM,
        output_config={"effort": cfg.effort, "format": {"type": "json_schema", "schema": extraction_schema()}},
        messages=[{"role": "user", "content": context}],
    )
    if resp.stop_reason == "refusal":
        raise LLMRefusal(getattr(resp.stop_details, "category", None) or "refusal")
    text_out = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text_out)
