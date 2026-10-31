# FinOps agent — Iran MVP

FinOps advisor for Iranian small businesses: describe or upload your infrastructure, confirm it, and
get exact, source-dated costs, equivalent-provider comparisons and evidence-backed savings across
ArvanCloud, Liara, Server.ir and IranServer (plus seeded Chabokan, ParsPack, MobinHost, Abrha).

**Rule zero: the AI never calculates a price or saving.** All numbers come from the tested
deterministic engine in `packages/pricing_engine` and `packages/recommendation_engine`. Missing data
returns `PRICE_UNAVAILABLE`, never an estimate.

## Quick start

```bash
cp .env.example .env        # defaults work for local dev
make dev                    # docker compose: postgres 16, redis, api, worker, beat, web
open http://localhost:8080  # login: demo@finops-agent.local / demo-password-1 → "Load demo workspace"
```

Without Docker (SQLite, Python 3.12+, Node 20+):

```bash
make install
make api      # http://localhost:8000/docs
make web      # http://localhost:5173
```

On Windows without `make`, use the same targets via `.\scripts\finops.ps1 <target>`.

Other commands: `make seed-pricing` (idempotent import of `data/seeds`), `make sync-prices` (fetch
official pages → normalize → guardrails → versioned prices), `make test`, `make lint`.

## How it works

1. **Input** — guided builder, chat (Persian/English), or invoice upload (PDF/CSV).
2. **Review** — editable table with confidence, missing fields and "I don't know"; analysis stays
   disabled until every row is confirmed.
3. **Quote** — immutable, tied to the catalog version, policy version and engine version; every line
   cites its catalog row, source URL and price date.
4. **Compare** — hard constraints → fit score → exact cost → explicit differences;
   `NEEDS_HUMAN_REVIEW` when confidence is low. Iran-only unless the user opts in.
5. **Recommend** — hourly scheduling, metrics-based downsizing, migration with payback, billing cadence,
   and explicit "cannot determine yet".
6. **Explain** — AI advisor calls the same tools; a numeric guard rejects any unsupported number.
7. **Report** — bilingual downloadable HTML (fa/en).

## Repository

```
apps/api        FastAPI service (auth, catalog store, inventory, analysis, advisor, reports)
apps/worker     Celery nightly sync + invoice retention
apps/web        React + TypeScript + Vite (fa RTL default, en)
packages/       pricing_engine, recommendation_engine, provider_adapters, ai_gateway,
                invoice_parser, shared_types  (framework-free)
data/seeds      build-pack dataset + authored policy files
migrations      Alembic (incl. Postgres immutability triggers)
tests/          pricing, providers (real saved pages), recommendations, ai, api
docs/           architecture, pricing-model, provider-adapters, ai-safety, runbook
```

Read next: [docs/architecture.md](docs/architecture.md) · [docs/pricing-model.md](docs/pricing-model.md) ·
[docs/provider-adapters.md](docs/provider-adapters.md) · [docs/ai-safety.md](docs/ai-safety.md) ·
[docs/runbook.md](docs/runbook.md) (production deployment) · [CHANGELOG.md](CHANGELOG.md) (status)

## Configuration

See `.env.example`. Notable: `FINOPS_AI_PROVIDER=offline|anthropic` (offline = no external calls;
anthropic uses Claude `claude-opus-5-5`), `FINOPS_INVOICE_RETENTION_DAYS`, `FINOPS_SYNC_MODE`.
Staging/prod refuse to start without `FINOPS_JWT_SECRET` and `FINOPS_CREDENTIALS_KEY`.
