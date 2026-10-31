"""Chat/text -> InventoryDraft. LLM when configured, deterministic parser otherwise (or on failure)."""

from __future__ import annotations

import logging
from typing import Any

import anthropic
from pydantic import ValidationError

from shared_types import InventoryDraft, ResourceDraft

from .llm import PROMPT_VERSION, LLMConfig, LLMRefusal, extract_inventory_json
from .offline_parser import parse_description

log = logging.getLogger(__name__)


def _from_llm_json(data: dict[str, Any], valid_providers: set[str], valid_skus: dict[str, str]) -> InventoryDraft:
    rows = []
    for r in data["resources"]:
        conf = {c["field"]: max(0.0, min(1.0, float(c["confidence"]))) for c in r.pop("field_confidence", [])}
        clean = {k: v for k, v in r.items() if v not in (None, "")}
        if clean.get("provider_id") not in valid_providers:
            clean.pop("provider_id", None)
        if clean.get("sku") and clean["sku"] not in valid_skus:
            clean["notes"] = (clean.get("notes") or "") + f" (unrecognised plan '{clean.pop('sku')}')"
        if clean.get("billing_mode") not in ("monthly", "hourly"):
            clean.pop("billing_mode", None)
        try:
            rows.append(ResourceDraft(**clean, field_confidence=conf))
        except ValidationError as exc:
            log.warning("dropping invalid extracted field set: %s", exc.errors()[:3])
            rows.append(ResourceDraft(name=clean.get("name", "unparsed"), notes="Extraction failed validation; "
                                      "please fill this row manually."))
    return InventoryDraft(name="Chat draft", resources=rows, questions=data.get("questions", []),
                          detected_currency=data.get("detected_currency"))


def extract_inventory(text: str, *, provider: str, cfg: LLMConfig | None, providers: list[str],
                      sku_map: dict[str, str]) -> tuple[InventoryDraft, dict[str, Any]]:
    """Returns the draft plus run metadata (which path ran, why a fallback happened)."""
    meta: dict[str, Any] = {"prompt_version": PROMPT_VERSION, "path": "offline"}
    if provider == "anthropic" and cfg is not None:
        try:
            data = extract_inventory_json(cfg, text, providers, sorted(sku_map))
            meta.update(path="llm", model=cfg.model)
            return _from_llm_json(data, set(providers), sku_map), meta
        except LLMRefusal as exc:
            meta["fallback_reason"] = f"model refusal: {exc}"
        except (anthropic.APIConnectionError, anthropic.APIStatusError) as exc:
            meta["fallback_reason"] = f"LLM unavailable: {type(exc).__name__}"
        except (ValueError, KeyError) as exc:
            meta["fallback_reason"] = f"invalid LLM output: {exc}"
    return parse_description(text, sku_map), meta
