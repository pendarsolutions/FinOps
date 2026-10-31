"""Cross-provider equivalence engine driven by equivalence_rules.json.

Pipeline per candidate: hard constraints -> compatibility -> weighted fit score -> exact pricing
(via price_resource) -> explicit differences. A cheaper machine is never "equivalent" by price alone.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from .catalog import CatalogSnapshot
from .models import (
    BillingContext,
    CatalogItem,
    Comparison,
    ConstraintResult,
    Difference,
    PriceBreakdown,
    PriceStatus,
    Resource,
)
from .pricing import price_resource

PCT = Decimal("0.01")


class RejectedCandidate(BaseModel):
    provider_id: str
    label: str
    catalog_item_ids: list[str]
    failed_constraints: list[ConstraintResult]


class EquivalenceResult(BaseModel):
    resource_id: str
    source_specs: dict[str, Any]
    candidates: list[Comparison] = Field(default_factory=list)
    rejected: list[RejectedCandidate] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def resolve_specs(resource: Resource, snapshot: CatalogSnapshot) -> Resource:
    """Fill missing specs of a SKU-pinned resource from its catalog row (never overrides user values)."""
    if not resource.sku or not resource.provider_id:
        return resource
    rows = snapshot.find(resource.provider_id, sku=resource.sku)
    if len(rows) != 1:
        return resource
    row = rows[0]
    updates: dict[str, Any] = {}
    for field in ("cpu_cores", "ram_gb", "storage_gb", "cpu_shared", "datacenter"):
        if getattr(resource, field) is None and getattr(row, field) is not None:
            updates[field] = getattr(row, field)
    return resource.model_copy(update=updates) if updates else resource


def _dec(v: Any) -> Decimal:
    return Decimal(str(v))


def _ratio(src: Decimal | None, cand: Decimal | None) -> Decimal:
    if src is None or cand is None or cand == 0:
        return Decimal("0.5")
    return min(Decimal(1), src / cand)


def _cpu_class_verdict(src_shared: bool | None, cand_shared: bool | None) -> str:
    if src_shared is None or cand_shared is None:
        return "unknown"
    if src_shared == cand_shared:
        return "match"
    return "upgrade" if src_shared and not cand_shared else "downgrade"


def _candidate_specs(snapshot: CatalogSnapshot, cand: Resource, row: CatalogItem | None) -> dict[str, Any]:
    if row is not None:
        return {"cpu_cores": row.cpu_cores, "ram_gb": row.ram_gb, "storage_gb": row.storage_gb,
                "cpu_shared": row.cpu_shared, "datacenter": row.datacenter, "availability": row.availability,
                "pricing_model": row.pricing_model, "region_country": row.region_country or "IR",
                "storage_type": row.storage_type, "included_traffic_gb": row.included_traffic_gb,
                "traffic_policy": row.attributes.get("traffic_policy"), "hourly": row.hourly_price_toman is not None,
                "resource_class": row.resource_class}
    return {"cpu_cores": cand.cpu_cores, "ram_gb": cand.ram_gb, "storage_gb": cand.storage_gb, "cpu_shared": None,
            "datacenter": None, "availability": "available", "pricing_model": "component_rate", "region_country": "IR",
            "storage_type": cand.storage_type, "included_traffic_gb": None, "traffic_policy": "metered",
            "hourly": False, "resource_class": cand.resource_class}


def _hard_constraints(rules: dict[str, Any], snapshot: CatalogSnapshot, src: Resource, spec: dict[str, Any],
                      priced: PriceBreakdown, ctx: BillingContext) -> list[ConstraintResult]:
    scope = rules["default_scope"]["region_countries"]
    exact_models = snapshot.policy["exact_pricing_models"]
    out: list[ConstraintResult] = []
    for hc in rules["hard_constraints"]:
        cid, field = hc["id"], hc["field"]
        if hc["op"] == "candidate_gte_source":
            s, c = getattr(src, field), spec.get(field)
            if s is None:
                out.append(ConstraintResult(constraint_id=cid, passed=True, detail=f"source {field} unknown - not constrained"))
            else:
                ok = c is not None and c >= s
                out.append(ConstraintResult(constraint_id=cid, passed=ok, detail=f"{field}: source {s}, candidate {c}"))
        elif hc["op"] == "equals":
            ok = spec.get(field) == hc["value"]
            out.append(ConstraintResult(constraint_id=cid, passed=ok, detail=f"{field}={spec.get(field)}"))
        elif hc["op"] == "exact_eligible":
            ok = spec.get("pricing_model") in exact_models
            out.append(ConstraintResult(constraint_id=cid, passed=ok, detail=f"pricing_model={spec.get('pricing_model')}"))
        elif hc["op"] == "in_scope":
            ok = ctx.allow_outside_iran or spec.get("region_country") in scope
            out.append(ConstraintResult(constraint_id=cid, passed=ok, detail=f"region_country={spec.get('region_country')}"))
        elif hc["op"] == "no_dedicated_to_shared":
            verdict = _cpu_class_verdict(src.cpu_shared, spec.get("cpu_shared"))
            out.append(ConstraintResult(constraint_id=cid, passed=verdict != "downgrade", detail=f"cpu class: {verdict}"))
        elif hc["op"] == "exact_price_available":
            ok = priced.status == PriceStatus.EXACT
            why = "; ".join(u.reason for u in priced.unavailable) if not ok else "exact"
            out.append(ConstraintResult(constraint_id=cid, passed=ok, detail=why))
    return out


def _differences(src: Resource, src_row: CatalogItem | None, spec: dict[str, Any], current: PriceBreakdown,
                 cand: PriceBreakdown) -> list[Difference]:
    def cmp(dim: str, s: Any, c: Any, higher_is_better: bool = True) -> Difference:
        if s is None or c is None:
            return Difference(dimension=dim, source_value=s, candidate_value=c, verdict="unknown")
        if s == c:
            return Difference(dimension=dim, source_value=s, candidate_value=c, verdict="same")
        better = (c > s) if higher_is_better else (c < s)
        return Difference(dimension=dim, source_value=s, candidate_value=c, verdict="better" if better else "worse")

    def line_total(bd: PriceBreakdown, prefix: str) -> Decimal | None:
        lines = [l for l in bd.components if l.code.startswith(prefix)]
        if not lines:
            return None
        if any(l.subtotal_toman is None for l in lines):
            return None
        return sum((l.subtotal_toman for l in lines), Decimal(0))

    cpu_v = _cpu_class_verdict(src.cpu_shared, spec.get("cpu_shared"))
    shared_label = {True: "shared", False: "dedicated/optimized", None: "unknown"}
    diffs = [
        cmp("cpu_cores", src.cpu_cores, spec.get("cpu_cores")),
        Difference(dimension="cpu_class", source_value=shared_label[src.cpu_shared],
                   candidate_value=shared_label[spec.get("cpu_shared")],
                   verdict={"match": "same", "upgrade": "better", "downgrade": "worse"}.get(cpu_v, "unknown"),
                   note="CPU class semantics for component providers are not published in the seed" if cpu_v == "unknown" else None),
        cmp("ram_gb", src.ram_gb, spec.get("ram_gb")),
        cmp("storage_gb", src.storage_gb, spec.get("storage_gb")),
        Difference(dimension="storage_type", source_value=src.storage_type or (src_row.storage_type if src_row else None),
                   candidate_value=spec.get("storage_type"),
                   verdict="unknown" if not spec.get("storage_type") else "different"),
        Difference(dimension="included_traffic_gb", source_value=src_row.included_traffic_gb if src_row else None,
                   candidate_value=spec.get("included_traffic_gb"), verdict="different",
                   note=f"candidate traffic policy: {spec.get('traffic_policy')}"),
        cmp("traffic_cost_toman", line_total(current, "traffic"), line_total(cand, "traffic"), higher_is_better=False),
        cmp("ipv4_cost_toman", line_total(current, "ipv4"), line_total(cand, "ipv4"), higher_is_better=False),
        Difference(dimension="datacenter", source_value=src.datacenter, candidate_value=spec.get("datacenter"),
                   verdict="same" if src.datacenter == spec.get("datacenter") else
                   ("unknown" if not src.datacenter or not spec.get("datacenter") else "different")),
        Difference(dimension="billing_cadence", source_value=src.billing_mode,
                   candidate_value="hourly+monthly" if spec.get("hourly") else "monthly",
                   verdict="same" if src.billing_mode == "monthly" or spec.get("hourly") else "worse"),
    ]
    unknown_features = [u.reason for u in cand.unavailable]
    if any(l.status == "assumed_included" for l in cand.components):
        unknown_features.append("public IPv4 inclusion not stated in catalog")
    if unknown_features:
        diffs.append(Difference(dimension="unknown_features", candidate_value=unknown_features, verdict="unknown"))
    return diffs


def _score(rules: dict[str, Any], src: Resource, spec: dict[str, Any], cand: PriceBreakdown) -> tuple[Decimal, dict[str, Decimal], list[str]]:
    w = {k: _dec(v) for k, v in rules["weights"].items()}
    sc = rules["scoring"]
    caps: list[str] = []
    cpu_v = _cpu_class_verdict(src.cpu_shared, spec.get("cpu_shared"))
    if cpu_v == "unknown":
        caps.append("cpu_class_unknown")
    traffic_unverified = any("direction" in a.lower() and "not verified" in a.lower() for a in cand.assumptions)
    if traffic_unverified:
        caps.append("traffic_direction_unverified")
    parts = {
        "cpu": _ratio(src.cpu_cores, spec.get("cpu_cores")),
        "ram": _ratio(src.ram_gb, spec.get("ram_gb")),
        "storage": _ratio(src.storage_gb, spec.get("storage_gb")),
        "cpu_class": _dec(sc["cpu_class"].get(cpu_v, sc["cpu_class"]["unknown"])) if cpu_v != "downgrade" else Decimal(0),
        "traffic": _dec(sc["traffic"]["direction_unverified"] if traffic_unverified else sc["traffic"]["known_and_covered"]),
        "datacenter": _dec(sc["datacenter"]["different"] if src.datacenter and spec.get("datacenter")
                           and src.datacenter != spec.get("datacenter") else sc["datacenter"]["same_or_unspecified"]),
        "billing_cadence": _dec(sc["billing_cadence"]["not_supported"] if src.billing_mode == "hourly" and not spec.get("hourly")
                                else sc["billing_cadence"]["supports_required"]),
    }
    weighted = {k: (w[k] * v).quantize(Decimal("0.0001")) for k, v in parts.items()}
    return sum(weighted.values(), Decimal(0)), weighted, caps


def _confidence(rules: dict[str, Any], passed: bool, score: Decimal, caps: list[str]) -> str:
    if not passed:
        return "not_equivalent"
    th = rules["confidence_thresholds"]
    level = "high" if score >= _dec(th["high"]) else "medium" if score >= _dec(th["medium"]) else rules["low_confidence_label"]
    for cap in rules.get("confidence_caps", []):
        if cap["when"] in caps and level == "high":
            level = cap["max"]
    return level


def compare_resource(resource: Resource, candidate: Resource, snapshot: CatalogSnapshot,
                     ctx: BillingContext | None = None, candidate_row: CatalogItem | None = None,
                     label: str | None = None) -> Comparison:
    ctx = ctx or BillingContext()
    rules = snapshot.equivalence_rules
    src = resolve_specs(resource, snapshot)
    src_row = snapshot.find_one(src.provider_id, sku=src.sku) if src.sku and src.provider_id else None
    if candidate_row is None and candidate.sku and candidate.provider_id:
        candidate_row = snapshot.find_one(candidate.provider_id, sku=candidate.sku)
    current = price_resource(src, snapshot, ctx)
    priced = price_resource(candidate, snapshot, ctx)
    spec = _candidate_specs(snapshot, candidate, candidate_row)
    constraints = _hard_constraints(rules, snapshot, src, spec, priced, ctx)
    passed = all(c.passed for c in constraints)
    score, breakdown, caps = _score(rules, src, spec, priced)
    saving = pct = None
    exact = current.status == PriceStatus.EXACT and priced.status == PriceStatus.EXACT
    if exact:
        saving = current.monthly_total_toman - priced.monthly_total_toman
        if current.monthly_total_toman:
            pct = (saving * 100 / current.monthly_total_toman).quantize(PCT)
    assumptions = list(priced.assumptions)
    if candidate_row is None and candidate.provider_id == "arvancloud":
        assumptions.append(f"Synthesized ArvanCloud configuration ({candidate.resource_class}, storage "
                           f"{candidate.storage_type}) from component rates; storage type mapped by equivalence_rules.")
    return Comparison(
        resource_id=src.id, candidate_provider_id=candidate.provider_id or "",
        candidate_label=label or (f"{candidate.provider_id} {candidate.sku}" if candidate.sku else f"{candidate.provider_id}"),
        candidate_catalog_item_ids=[l.catalog_item_id for l in priced.components if l.catalog_item_id] or
                                   ([candidate_row.id] if candidate_row else []),
        current=current, candidate=priced, constraints=constraints, passed_hard_constraints=passed,
        fit_score=score, score_breakdown=breakdown, confidence=_confidence(rules, passed, score, caps),
        differences=_differences(src, src_row, spec, current, priced), monthly_saving_toman=saving,
        monthly_saving_percent=pct, exact=exact, assumptions=assumptions,
    )


def _workload(src: Resource, **overrides: Any) -> Resource:
    base = src.model_dump()
    base.update({"sku": None, "resource_class": None, "datacenter": None, "cpu_shared": None, "metrics": None})
    base.update(overrides)
    return Resource.model_validate(base)


def find_equivalents(resource: Resource, snapshot: CatalogSnapshot, ctx: BillingContext | None = None,
                     include_same_provider: bool = False) -> EquivalenceResult:
    ctx = ctx or BillingContext()
    rules = snapshot.equivalence_rules
    src = resolve_specs(resource, snapshot)
    result = EquivalenceResult(resource_id=src.id, source_specs={
        k: getattr(src, k) for k in ("provider_id", "sku", "service_type", "cpu_cores", "ram_gb", "storage_gb",
                                     "cpu_shared", "datacenter", "environment", "billing_mode")})
    compatible = rules["compatible_service_types"].get(src.service_type)
    if not compatible:
        result.notes.append(f"No equivalence policy for service type '{src.service_type}'.")
        return result
    comparisons: list[Comparison] = []
    for pid, pol in snapshot.policy["providers"].items():
        if pid == src.provider_id and not include_same_provider:
            continue
        if pol["strategy"] == "component" and pid == "arvancloud" and src.service_type == "compute_vm":
            st_map = rules["storage_type_map"]
            st = st_map.get((src.storage_type or "").lower(), st_map["default"])
            for cls in rules["arvan_candidate_classes"]:
                cand = _workload(src, provider_id=pid, resource_class=cls, storage_type=st, billing_mode="monthly")
                comparisons.append(compare_resource(src, cand, snapshot, ctx, label=f"ArvanCloud {cls} (component)"))
            continue
        for row in snapshot.provider_items(pid):
            if row.service_type not in compatible or not row.sku:
                continue
            if pid == src.provider_id and row.sku == src.sku:
                continue
            mode = src.billing_mode if row.hourly_price_toman is not None else "monthly"
            cand = _workload(src, provider_id=pid, sku=row.sku, billing_mode=mode, storage_type=row.storage_type)
            comparisons.append(compare_resource(src, cand, snapshot, ctx, candidate_row=row,
                                                label=f"{snapshot.providers[pid].name_en} {row.sku}"))
    order = {"high": 0, "medium": 1, rules["low_confidence_label"]: 2}
    passing = [c for c in comparisons if c.passed_hard_constraints]
    passing.sort(key=lambda c: (order.get(c.confidence, 3), -(c.monthly_saving_toman or Decimal("-1e30")), -c.fit_score))
    result.candidates = passing[: int(rules.get("max_candidates", 10))]
    result.rejected = [RejectedCandidate(provider_id=c.candidate_provider_id, label=c.candidate_label,
                                         catalog_item_ids=c.candidate_catalog_item_ids,
                                         failed_constraints=[x for x in c.constraints if not x.passed])
                       for c in comparisons if not c.passed_hard_constraints]
    if not ctx.allow_outside_iran:
        result.notes.append("Iran-only comparison (outside-Iran providers require explicit opt-in).")
    return result
