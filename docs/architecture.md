# Architecture

## Flow

```
describe / upload / build ──► InventoryDraft ──► review table ──► CONFIRMED inventory
   (chat, invoice, builder)    (shared_types)    (human, mandatory)        │
                                                                           ▼
 versioned catalog (Postgres) ──► CatalogSnapshot ──► pricing_engine ──► immutable Quote
                                        │                 │
                                        │                 ├─► equivalence (compare_resource / find_equivalents)
                                        │                 └─► recommendation_engine ──► Recommendations (+evidence)
                                        ▼
                                 ai_gateway advisor ── calls the same deterministic tools, explains, never computes
```

The AI never sits on the path that produces a number. It can only (a) turn text into an
`InventoryDraft` that a human must confirm, and (b) explain tool results under a numeric guard.

## Components

| Path | Role | Depends on |
|---|---|---|
| `packages/pricing_engine` | Pure deterministic pricing: money (Decimal-only), catalog snapshot, `price_resource`, `price_inventory`, equivalence engine. No web/DB/LLM. | pydantic |
| `packages/recommendation_engine` | Deterministic rules REC-001..005, `summarize()` (no double counting). | pricing_engine |
| `packages/provider_adapters` | `ProviderAdapter` protocol, HTML adapters (Liara, Server.ir, IranServer, ArvanCloud-blocked), `plan_sync` guardrails. `InventoryConnector` reserved. | pricing_engine, httpx, bs4 |
| `packages/shared_types` | `ResourceDraft` / `InventoryDraft` contract and the required-field rules that gate confirmation. | pricing_engine |
| `packages/invoice_parser` | PDF/CSV text, Rial/Toman detection, ID redaction, SKU mapping with confidence. | pypdf |
| `packages/ai_gateway` | Claude extraction (structured output) + advisor tool loop, offline parser/template, numeric guard. | anthropic |
| `apps/api` | FastAPI: auth/orgs/roles, versioned catalog store, inventory, analysis, advisor, reports, audit. | all packages, SQLAlchemy |
| `apps/worker` | Celery: nightly sync (03:15 Tehran), invoice purge (04:00). | apps/api |
| `apps/web` | React + TS + Vite SPA, fa (RTL, default) / en. | API only |
| `data/seeds` | Build-pack dataset + authored policy files (see below). | — |
| `migrations` | Alembic (single source of schema; includes Postgres immutability triggers). | — |

The pricing and recommendation packages import nothing from FastAPI or SQLAlchemy so they can be
published as an open-source CLI/library.

## Data model highlights

- **Catalog history**: `catalog_item_versions` – one row per price version, `item_id` stable across
  versions, `valid_from`/`valid_to`. A change closes the open version and inserts a new one; an ORM
  hook and a Postgres trigger both reject any other UPDATE. `price_sources` records URL, retrieval
  time, provider price date, content hash, sync status.
- **Billing rules**: `billing_rule_versions` (same pattern).
- **Quotes**: `price_quotes` is immutable (ORM hook + trigger) and stores the inventory snapshot,
  catalog version hash, policy version, engine version, full breakdown, assumptions, and a content hash.
- **Recommendations**: grouped by `analysis_id`, each with rule id, costs, saving, %, migration cost,
  payback, risk, effort, confidence, price dates, missing inputs, evidence JSON.
- **Money**: `Money` column type = `NUMERIC(24,4)` on Postgres; on SQLite (tests/dev) it is stored as
  TEXT so it never round-trips through float. Every money field name carries its unit (`*_toman`).
  The API encodes all Decimals as exact strings.

## Seed and policy files (`data/seeds`)

| File | Origin | Contains prices? |
|---|---|---|
| `iran_finops_dataset.json`, `catalog_items.csv`, `schema.sql` | build pack | yes (source material) |
| `providers.json`, `catalog_items.json`, `billing_rules.json` | split from the bundle | yes (copies) |
| `sources.json` | derived from catalog rows (original missing) | no |
| `engine_policy.json` | **authored** – calculation conventions + declared data gaps | no |
| `equivalence_rules.json` | **authored** (original missing) | no |
| `recommendation_rules.json` | **authored** (original missing) | no |
| `sample_inventory.json` | **authored** demo fixture (original missing) | no (one labelled sample day rate) |

The build pack referenced `equivalence_rules.json`, `recommendation_rules.json`, `sample_inventory.json`
and `sources.json`, but they were not in the folder. The authored versions contain only rules and
thresholds; every price still comes from the dataset. Replace them if the originals turn up.
Their `version` / `policy_version` is recorded on every quote, so changes are traceable.

## Security

- JWT bearer auth (no cookies, so no CSRF surface), PBKDF2-SHA256 passwords, org-scoped data, roles
  `viewer < analyst < admin < owner` (`require("analyst")` etc.).
- Provider credentials: Fernet-encrypted at rest, read-only enforced, only a 4-char hint is returned.
- Uploads: extension + magic-byte validation, size cap, private storage outside the web root, HMAC-signed
  expiring download URLs, retention purge (`PENDAR_INVOICE_RETENTION_DAYS`), redaction before anything
  is stored in inventory metadata or AI logs.
- AI endpoints rate limited per user (Redis-backed when configured). Prompts/inputs stored in
  `ai_runs` are redacted.
- JSON logs with secret redaction; `x-request-id` on every response. Audit log for inventory edits,
  confirmations, quotes, analyses, reports, settings, credentials and syncs.
- staging/prod refuse to start without a ≥32-char JWT secret and a credentials key.
