"""AI boundary: the advisor can never emit a number that no deterministic tool returned."""

from types import SimpleNamespace as NS

import pytest

import ai_gateway.advisor as advisor_mod
import ai_gateway.extraction as extraction_mod
from ai_gateway import LLMConfig, check_numbers, extract_inventory, parse_description, run_advisor
from invoice_parser import detect_currency, parse_invoice, redact

TOOL_OUT = {"quote_id": "q-1", "catalog_version": "cat-abc", "complete": True, "total_toman": "20574439",
            "priced_subtotal_toman": "20574439"}
RECS = {"analysis_id": "an-1", "quote_id": "q-1",
        "summary": {"avoidable_monthly_toman": "5343839", "potential_saving_percent": "25.97"},
        "recommendations": [{"id": "rec-1", "result_status": "actionable", "title_en": "Hourly", "title_fa": "ساعتی",
                             "resource_name": "staging-app", "monthly_saving_toman": "1979460", "risk_level": "low",
                             "effort_level": "low", "confidence": "high", "missing_inputs": []}]}
TOOLS = {"price_inventory": lambda _: TOOL_OUT, "list_recommendations": lambda _: RECS,
         "get_inventory": lambda _: {"resources": []}}


# ---------------------------------------------------------------- guard


def test_guard_accepts_tool_numbers_with_formatting():
    g = check_numbers("Your bill is 20,574,439 Toman; save ۱٬۹۷۹٬۴۶۰ per month [rec-1].", [TOOL_OUT, RECS])
    assert g.ok, g.unsupported


def test_guard_rejects_invented_numbers():
    g = check_numbers("You could save about 2,500,000 Toman (12%).", [TOOL_OUT, RECS])
    assert not g.ok and set(g.unsupported) == {"2500000", "12"}


def test_guard_allows_user_numbers_and_small_counts():
    assert check_numbers("Your 3 servers with 4 GB...", [], user_text="we have 3 servers 4 GB").ok
    assert check_numbers("Step 1, step 2", []).ok


# ---------------------------------------------------------------- advisor with a fake LLM


class FakeClient:
    """Scripted Claude: first asks for a tool, then answers with the given texts in order."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0
        self.beta = NS(messages=NS(create=self.create))

    def create(self, **kwargs):
        self.calls += 1
        assert kwargs["model"] == "claude-opus-5-5"
        assert all(t.get("strict") for t in kwargs["tools"])
        if self.calls == 1:
            return NS(stop_reason="tool_use", content=[NS(type="tool_use", id="tu1", name="price_inventory", input={})])
        return NS(stop_reason="end_turn", content=[NS(type="text", text=self.answers.pop(0))])


def _run(monkeypatch, answers):
    fake = FakeClient(answers)
    monkeypatch.setattr(advisor_mod, "client_for", lambda cfg: fake)
    return run_advisor("How much do we spend?", "en", dict(TOOLS), provider="anthropic", cfg=LLMConfig()), fake


def test_llm_answer_with_tool_numbers_passes(monkeypatch):
    ans, _ = _run(monkeypatch, ["Monthly cost is 20,574,439 Toman (quote q-1, catalog cat-abc)."])
    assert ans.path == "llm" and ans.guard["ok"]
    assert "q-1" in ans.evidence_ids


def test_llm_hallucinated_number_is_regenerated_then_replaced(monkeypatch):
    ans, fake = _run(monkeypatch, ["You will save roughly 3,000,000 Toman.", "Still about 3,000,000 Toman."])
    assert fake.calls == 3  # tool call, first answer, one forced rewrite
    assert "3,000,000" not in ans.answer
    assert ans.path == "template_after_guard_rejection"
    assert ans.guard["ok"]
    assert "20,574,439" in ans.answer


def test_llm_corrected_on_retry(monkeypatch):
    ans, fake = _run(monkeypatch, ["About 21 million Toman", "It is 20,574,439 Toman (quote q-1)."])
    assert ans.path == "llm" and "20,574,439" in ans.answer


def test_offline_template_is_guarded_and_cites_evidence():
    ans = run_advisor("کجا صرفه‌جویی کنیم؟", "fa", dict(TOOLS), provider="offline", cfg=None)
    assert ans.guard["ok"] and "تومان" in ans.answer and "rec-1" in ans.answer


def test_refusal_falls_back_to_template(monkeypatch):
    class Refuser(FakeClient):
        def create(self, **kwargs):
            return NS(stop_reason="refusal", content=[], stop_details=NS(category=None))

    monkeypatch.setattr(advisor_mod, "client_for", lambda cfg: Refuser([]))
    ans = run_advisor("q", "en", dict(TOOLS), provider="anthropic", cfg=LLMConfig())
    assert ans.path == "offline_template" and "refusal" in ans.meta["fallback_reason"]


# ---------------------------------------------------------------- extraction


def test_llm_extraction_output_is_validated(monkeypatch):
    def fake_extract(cfg, text, providers, skus):
        return {"resources": [{"name": "web", "environment": "production", "provider_id": "made-up-cloud",
                               "sku": "NOT-A-SKU", "resource_class": None, "datacenter": None, "quantity": "2",
                               "cpu_cores": "2", "ram_gb": "4", "storage_gb": None, "storage_type": None,
                               "expected_monthly_download_gb": None, "expected_monthly_upload_gb": None,
                               "active_hours_per_month": None, "billing_mode": "weekly", "notes": None,
                               "service_type": "compute_vm", "requires_public_ipv4": True,
                               "field_confidence": [{"field": "ram_gb", "confidence": 0.6}]}],
                "questions": ["Which provider?"], "detected_currency": "UNKNOWN"}

    monkeypatch.setattr(extraction_mod, "extract_inventory_json", fake_extract)
    draft, meta = extract_inventory("x", provider="anthropic", cfg=LLMConfig(), providers=["serverir"],
                                    sku_map={"IRAT3024": "serverir"})
    r = draft.resources[0]
    assert meta["path"] == "llm"
    assert r.provider_id is None and r.sku is None and "NOT-A-SKU" in r.notes  # nothing invented survives
    assert r.billing_mode is None and r.field_confidence == {"ram_gb": 0.6}


def test_offline_parser_never_converts_business_hours():
    d = parse_description("one staging server 2 cores 4GB RAM on liara, used only in business hours")
    assert d.resources[0].active_hours_per_month is None
    assert any("hours per month" in q for q in d.questions)


# ---------------------------------------------------------------- invoices


@pytest.mark.parametrize("text, cur", [("مبلغ کل: ۱۷,۵۰۰,۰۰۰ ریال", "RIAL"), ("Total 1,750,000 Toman", "TOMAN"),
                                       ("Total 1,750,000", "UNKNOWN"), ("ریال / تومان", "UNKNOWN")])
def test_currency_detection(text, cur):
    assert detect_currency(text)[0] == cur


def test_redaction():
    out, counts = redact("Customer ID: 88442211 email a.b@co.ir card 6037-9911-2233-4455 IR820540102680020817909002")
    assert "88442211" not in out and "a.b@co.ir" not in out and "6037" not in out and "IR8205" not in out
    assert counts["email"] == 1 and counts["card"] == 1 and counts["iban"] == 1


def test_invoice_mapping_and_confidence():
    ext = parse_invoice("Server.ir invoice\nIRAT3024 x 2  3,500,000 تومان\nIRFH5024 1 1,690,000 تومان\n"
                        "Backup VPS custom 500,000 تومان", {"IRAT3024": "serverir", "IRFH5024": "serverir"})
    assert ext.detected_currency == "TOMAN" and not ext.currency_confirmation_required
    assert [r.sku for r in ext.draft.resources] == ["IRAT3024", "IRFH5024"]
    assert ext.draft.resources[0].quantity == 2
    assert ext.unmatched_lines == ["Backup VPS custom 500,000 تومان"]
    assert ext.draft.resources[0].field_confidence["environment"] == 0.0
