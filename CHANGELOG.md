# Changelog / implementation status

## Unreleased

- Renamed to FinOps agent, removed consulting referrals and unused credential storage.
- Apache-2.0 license and contributor files. GitHub Actions are written but disabled while the repository is private.
- Safer defaults: local-only ports in development, sign-up closes after the first account, login rate limits.
- Server monitoring: read-only SSH collection, Servers page, plan suggestions, usage-based rightsizing evidence.
- One-command installer with a registry mirror option and offline bundles.
- Chabokan and MobinHost scrapers, twice-daily checks, reviewed manual price files for ArvanCloud.
- Alerts by email and Bale for price changes, failed updates, reviews and renewals.
- Signed shared price catalog.
- Fixed: re-importing the seed on restart overwrote newer scraped prices.


## 0.1.0 — 2026-10-04 (MVP build)

### Phase 0 — Bootstrap ✅
Monorepo layout, Docker Compose (Postgres 16, Redis, API, worker, beat, web), Alembic migration
(+ Postgres immutability triggers), idempotent seed import, JWT auth with orgs and roles, GitLab CI
(lint, tests, Postgres migration + double seed, web build, images), `.env.example`, health/readiness,
JSON logs.

### Phase 1 — Pricing core ✅
Versioned catalog (close + insert, never overwrite), Decimal-only engine with component / Liara plan /
fixed-SKU / discovery-only strategies, tax as a separate line, PRICE_UNAVAILABLE semantics, golden tests
for every seeded provider family and hypothesis property tests.

### Phase 2 — Inventory ✅
Guided builder API, review/confirmation gate with required-field rules per pricing shape and
"I don't know" acknowledgement, immutable quotes, source freshness (incl. Jalali price dates).

### Phase 3 — Comparison + recommendations ✅
Equivalence engine (hard constraints, weighted fit, confidence caps, explicit differences, Iran-only
default), REC-001..005, non-double-counted avoidable spend.

### Phase 4 — AI ✅
Chat → InventoryDraft (Claude structured output, or deterministic fa/en parser offline), invoice
(PDF/CSV) → draft with Rial/Toman detection and redaction, tool-calling advisor with numeric guard and
template fallback, `ai_runs` logging, per-user rate limits.

### Phase 5 — Provider sync ✅ (with one documented blocker)
Live parsers for Liara, Server.ir, IranServer against real pages; ArvanCloud blocked by a bot
challenge (fails visibly); guardrails + quarantine approval; nightly Celery schedule.
Live sync on 2026-10-04: Liara 23 rows / 0 changes, IranServer 5 / 0, Server.ir 24 / 5 changes
(IRFH download now metered at 1,600 Toman/GB; IRFH80612 delisted).

### Phase 6 — Pilot hardening (partial)
Done: bilingual HTML report, audit log, demo workspace, upload validation/signed URLs/retention,
encrypted read-only credentials, structured logs, deployment docs.
Web UI: all 9 sections, fa (RTL) / en, review table, compare matrix, catalog with history, advisor panel; smoke-tested against the live API and rendered at 390 px width.
Not done: PDF report (phase 2 by spec), OIDC, external alert routing (alerts are structured ERROR logs),
load testing. (pytest runs on SQLite; the Postgres path — migration, triggers, seed, full API flow, Celery sync — was verified via docker compose.)

## Definition of Done

| # | Item | Status |
|---|---|---|
| 1 | Import seed catalog | ✅ `make seed-pricing` (idempotent; tested) |
| 2 | Manually create an Iranian inventory | ✅ builder API + UI |
| 3 | Must confirm before analysis | ✅ 409 until confirmed; edits un-confirm |
| 4 | Exact costs for supported rows | ✅ golden tests |
| 5 | Compare a VM against alternatives | ✅ |
| 6 | Show why an alternative is / is not equivalent | ✅ constraints + differences + rejected list |
| 7 | Evidence-backed opportunities | ✅ |
| 8 | Chat → draft in Persian or English | ✅ (offline parser and Claude path) |
| 9 | Invoice → draft with uncertainty | ✅ PDF/CSV; images need OCR (not available — returns a clear 422) |
| 10 | AI cannot produce an unsupported number | ✅ guard + tests |
| 11 | Every price has source/freshness | ✅ |
| 12 | Sync failures visible | ✅ |
| 13 | Unit/golden tests pass | ✅ 117 Python tests + web typecheck/build |
| 14 | Full stack with one command | ✅ `docker compose up --build` verified: Postgres 16, Redis, api, worker, beat, web |
| 15 | README: setup, architecture, production deployment | ✅ |

## Known gaps / data the seed cannot support
- ArvanCloud: no hourly proration rule, traffic-direction semantics unverified, live page blocked.
- Fixed-SKU providers: no overage traffic, extra disk, or extra IPv4 prices; one IPv4 assumed included (visible).
- Liara PaaS/DBaaS traffic prices; Liara extra disk.
- Server.ir term discounts unverified (never applied).
- Provider invoice rounding rules unknown (engine does not round).
- `equivalence_rules.json`, `recommendation_rules.json`, `sample_inventory.json`, `sources.json` were
  missing from the build pack and were authored (no prices in them).
