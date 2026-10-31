# Architecture (summary)

Full document: [docs/architecture.md](docs/architecture.md).

- Deterministic core (`packages/pricing_engine`, `packages/recommendation_engine`) is framework-free and
  is the only producer of financial numbers. Decimal-only; floats rejected; no rounding in the engine.
- Versioned catalog in Postgres (`catalog_item_versions`, close + insert, immutable via ORM hook and DB
  trigger). Quotes are immutable and pinned to catalog version + policy version + engine version.
- Inventory must be human-confirmed before any quote, comparison or recommendation (409 otherwise).
- Provider adapters parse official pages (Liara, Server.ir, IranServer live; ArvanCloud blocked by a bot
  challenge and failing visibly) behind sync guardrails (zero items, >25% median move → quarantine,
  missing SKUs, unchanged parser output, stale dates).
- AI gateway: structured-output extraction into `InventoryDraft`, and a tool-calling advisor whose answers
  pass a numeric guard; deterministic offline mode by default.
- FastAPI API + Celery worker + React SPA; Docker Compose for dev, override file for staging/prod.
