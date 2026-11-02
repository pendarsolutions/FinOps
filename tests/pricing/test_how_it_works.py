"""The "How it works" page shows worked examples. They must stay true, so they are recalculated here."""

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from pricing_engine import Resource, UsageMetrics, price_resource
from recommendation_engine import recommend

EXAMPLES = json.loads((Path(__file__).resolve().parents[2] / "apps/web/src/lib/howItWorksExamples.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("example", EXAMPLES["pricing"], ids=lambda e: e["id"])
def test_pricing_examples_match_the_engine(example, snapshot):
    bd = price_resource(Resource(id="x", name="x", **example["resource"]), snapshot)
    assert bd.status.value == "EXACT"
    assert bd.monthly_total_toman == Decimal(example["total"])
    lines = {c.code: c for c in bd.components if c.subtotal_toman is not None}
    assert set(lines) == {line["code"] for line in example["lines"]}
    for line in example["lines"]:
        got = lines[line["code"]]
        assert got.subtotal_toman == Decimal(line["subtotal"]), line["code"]
        assert got.quantity == Decimal(line["qty"]), line["code"]
        if got.unit_price_toman is not None:
            assert got.unit_price_toman == Decimal(line["unit_price"]), line["code"]


def test_downsize_example_matches_the_engine(snapshot):
    ex = EXAMPLES["downsize"]
    r = Resource(id="x", name="x", metrics=UsageMetrics(**ex["metrics"]), **ex["resource"])
    rec = next(x for x in recommend([r], snapshot) if x.rule_id == "REC-002")
    assert rec.status == "actionable"
    assert rec.current_cost_toman == Decimal(ex["current"])
    assert rec.candidate_cost_toman == Decimal(ex["candidate"])
    assert rec.monthly_saving_toman == Decimal(ex["saving"])
    assert rec.monthly_saving_percent == Decimal(ex["saving_percent"])
    assert ex["candidate_sku"] in rec.summary_en
    required = Decimal(ex["ram_gb"]) * Decimal(ex["ram_p95"]) / 100 * Decimal(ex["headroom"])
    assert required == Decimal(ex["required_ram_gb"])
    assert Decimal(ex["headroom"]) == Decimal(snapshot.recommendation_rules["rules"][1]["params"]["headroom_factor"])


def test_payback_example_is_correct_arithmetic():
    ex = EXAMPLES["payback"]
    assert Decimal(ex["days"]) * Decimal(ex["day_rate"]) == Decimal(ex["cost"])
    months = (Decimal(ex["cost"]) / Decimal(ex["saving"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert months == Decimal(ex["months"])
