"""Deterministic recommendation engine. Every number is produced by pricing_engine; this package only
decides which priced alternatives are worth surfacing, under rules loaded from recommendation_rules.json."""

from .engine import RECOMMENDATION_ENGINE_VERSION, OrgSettings, Recommendation, recommend, summarize

__all__ = ["RECOMMENDATION_ENGINE_VERSION", "OrgSettings", "Recommendation", "recommend", "summarize"]
