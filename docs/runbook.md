# Runbook

## Local

```bash
make dev                    # Docker: postgres, redis, api, worker, beat, web -> http://localhost:8080
                            # demo login (dev only): demo@finops-agent.local / demo-password-1
```

Without Docker (SQLite at `var/finops-dev.db`, sync runs inline):

```bash
make install
make api                    # migrate + seed-pricing + demo user, API on :8000 (docs at /docs)
make web                    # Vite on :5173 (proxies /api to :8000)
make test                   # pytest + web typecheck
```

## Installing on a server

Use [the installer](installation.md). The steps below are for running from a checkout without it.

## Staging / production

1. `cp .env.example .env`; set `FINOPS_ENV=staging|prod`, `POSTGRES_PASSWORD`, `FINOPS_JWT_SECRET`
   (≥32 chars), `FINOPS_CREDENTIALS_KEY` (Fernet), `FINOPS_CORS_ORIGINS`.
2. `docker compose -f docker-compose.yml -f deploy/compose.prod.yml --env-file .env up -d --build`
3. The api container runs `migrate` and `seed-pricing` (idempotent) on start. No demo user outside dev.
4. Put TLS in front of the `web` container (nginx inside it proxies `/api` and `/health` to the api).
   Back up the `pgdata` and `uploads` volumes.

Health: `GET /health/live` (process), `GET /health/ready` (DB reachable, catalog non-empty, Redis if
configured) — returns 503 with the failing check.

## Price sync operations

| Symptom | Action |
|---|---|
| Sync `failed` for ArvanCloud with `SourceBlockedError` | Expected until the API connector exists. Seed snapshot remains active; watch freshness (warn 14 d, stale 45 d). |
| Sync `failed` with `ParseError` | Page layout changed. Save the page as a fixture, fix the parser, add a test. Nothing was applied. |
| Sync `quarantined` | Median price moved > 25%. Review `summary.changes` in Integrations; approve (`POST /api/v1/admin/sync-runs/{id}/approve`) or ignore. |
| `warning: key SKUs missing` | Provider delisted plans (closed as `removed`). Confirm on the website. |
| `hash changed but parser output unchanged` | The page changed in a way the parser ignores — check for new plans/families. |

Manual: `make sync-prices` (or `python -m finops_api.cli sync-prices --provider serverir --strict`).

## Server monitoring

The worker collects from every server every 5 minutes. To run it by hand: `python -m finops_api.cli collect-servers`.
Without the worker (SQLite, no Docker), use **Check now** on the Servers page. See [servers.md](servers.md).

## Data retention

Raw invoices are deleted after `FINOPS_INVOICE_RETENTION_DAYS` (worker 04:00, or
`make purge-uploads`). Extracted, redacted rows remain in the inventory.

## Logs and alerts

JSON lines on stdout. Alert on `{"alert": "price_sync", "status": "failed"|"quarantined"}` and on
`/health/ready` failures. Every response carries `x-request-id`.
