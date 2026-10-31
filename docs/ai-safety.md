# AI safety: the AI never calculates a price or saving

## Where the AI is allowed

| Use | Module | Output | Gate |
|---|---|---|---|
| Chat → inventory | `ai_gateway.extraction` | `InventoryDraft` (strict JSON schema via structured outputs) | Validated against `ResourceDraft`; unknown provider ids / SKUs are dropped into notes; low-confidence fields highlighted; **human confirmation required** before any pricing. |
| Invoice → inventory | `invoice_parser` (deterministic) | `InventoryDraft` + currency evidence | Same confirmation gate; ambiguous Rial/Toman blocks confirmation until the user chooses. |
| Advisor | `ai_gateway.advisor` | Explanation text | Tools only; numeric guard; evidence ids. |

## Advisor tools (deterministic)

`get_inventory`, `get_catalog_item`, `price_inventory`, `compare_providers`, `list_recommendations`,
`get_price_source`, `get_provider_documentation`. All are `strict: true` tools backed by the same
engine code as the API. `price_inventory` reuses the latest quote unless the catalog version changed.

## The numeric guard (`ai_gateway.guard`)

Every number in the final answer (ASCII or Persian digits, any thousands separator) must appear in a
tool output or in the user's question; integers ≤ 10 are allowed for counts/list numbering.

1. If the model's answer fails the guard, it is told which numbers are unsupported and asked once to
   rewrite using tool numbers only.
2. If it fails again, the answer is **discarded** and replaced with the deterministic template answer
   built from the tool outputs (`path = template_after_guard_rejection`).
3. Guard results, tool calls and the redacted question are stored in `ai_runs`.

Known limit: numbers written as words ("two million") are not caught by the regex guard. The system
prompt forbids them; the template fallback is the backstop. Tests:
`tests/ai/test_ai_safety.py` (hallucinated number → replaced; corrected on retry → kept; refusal →
template).

## Model configuration

- `PENDAR_AI_PROVIDER=offline` (default): deterministic Persian/English parser and templated advisor.
  No external calls — appropriate where the LLM API is unreachable from Iranian infrastructure or
  data must not leave the network.
- `PENDAR_AI_PROVIDER=anthropic`: Claude via the official SDK, model `claude-opus-5-5` (override with
  `PENDAR_AI_MODEL`), effort `medium`, server-side refusal fallback (`fallbacks: "default"`, beta
  `server-side-fallback-2026-07-01`). Refusals and API errors fall back to the offline path and are
  recorded in run metadata.
- The offline parser never turns "business hours" into a number; it asks.

## Things the AI is never given

Credentials, unredacted invoice text, other organisations' data. Inputs are redacted (IDs, emails,
cards, IBANs, phone numbers) before storage and before being sent to a model.
