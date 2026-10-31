"""Deterministic pricing engine.

Pure library: no web framework, no database, no LLM. Every financial number the product shows
is produced here (or in recommendation_engine, which calls into here).
"""

ENGINE_VERSION = "pricing-engine/0.1.0"

from .catalog import CatalogSnapshot, load_seed_snapshot, parse_price_date  # noqa: E402
from .equivalence import EquivalenceResult, compare_resource, find_equivalents, resolve_specs  # noqa: E402
from .models import (  # noqa: E402
    BillingContext,
    CatalogItem,
    Comparison,
    PriceBreakdown,
    PriceStatus,
    Quote,
    Resource,
    UsageMetrics,
)
from .pricing import price_inventory, price_resource  # noqa: E402

__all__ = [
    "ENGINE_VERSION",
    "BillingContext",
    "CatalogItem",
    "CatalogSnapshot",
    "Comparison",
    "EquivalenceResult",
    "PriceBreakdown",
    "PriceStatus",
    "Quote",
    "Resource",
    "UsageMetrics",
    "compare_resource",
    "find_equivalents",
    "load_seed_snapshot",
    "parse_price_date",
    "price_inventory",
    "price_resource",
    "resolve_specs",
]
