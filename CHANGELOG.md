# Changelog

All notable changes to FinOps agent. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/). Until 1.0, a minor version can change behaviour.

## [0.3.0] — unreleased

A team can now run its own installation without touching the database, and the interface follows the Pendar design
system.

### Added

- **Backups.** A nightly backup at 03:30 that keeps the newest 14, and one command to back up or restore
  (`/opt/finops-agent/backup.sh`). A backup holds the database, the uploaded invoices and the settings with the keys
  that decrypt stored SSH keys. A restore asks first, backs up the current data before changing anything, and keeps
  the settings that belong to the machine. `--no-daily-backup` turns the nightly backup off.
- **Getting back in.** With email set up, "Forgot your password?" sends a one-time link that works for 30 minutes.
  Without email, an admin sets a temporary password, and a server command resets a locked-out owner's password.
- **Members.** Admins change roles and remove members. They manage only roles below their own, and nobody changes
  their own membership. Removed members lose access at once and can be added back.
- **Change your password** under Settings. It signs you out everywhere else.
- **Motion** from Pendar's motion guideline. The wordmark is laid brick by brick, page blocks arrive in reading
  order, and chart bars are laid instead of stretched. With reduced motion turned on, everything is in place at once.

### Changed

- **Pendar design system** (version 3): Estedad replaces Vazirmatn, with Pendar's colours, icons, wordmark and
  loader. Dark mode follows the system.
- **Solar Hijri dates** throughout the Persian interface (۱۴۰۵/۰۸/۱۷), with moments shown in the reader's time.
- **The Persian report is Persian:** headers, status words, Persian digits and separators, and Solar Hijri dates.
- Price update statuses are written out ("Updated", "Held for review") instead of `OK` and `FAILED`, and common
  error messages appear in Persian.
- Form fields line up at the top, with each form's button on its own row.
- The installer writes `FINOPS_PUBLIC_URL` (used for links in emails) and passes `FINOPS_SMTP_FROM` and
  `FINOPS_SMTP_STARTTLS` to the app.

### Fixed

- `sudo ./install.sh` failed with "Permission denied" on a fresh clone: the scripts weren't executable in git.
- A password change didn't end sessions that were already signed in.
- On a development server, the welcome tour opened on every page load, even after it was dismissed.

### Upgrading

Run the new installer as before. The database is upgraded when the app starts, the nightly backup is set up, and
`FINOPS_PUBLIC_URL` is added to your settings from your domain or IP address.

## [0.2.0] — 2026-11-05

First public release.

### Added

- **Server monitoring.** Add servers from the dashboard and their real CPU, memory and disk use is read over SSH. The
  key can run only one read-only script, server identities are pinned, and a changed identity stops collection until
  an admin approves it. The Servers page shows each server's cost, unused capacity and renewal date.
- **Installer that works next to other services.** If ports 80 and 443 are taken, it picks a free port and leaves
  the existing services alone. It also takes a registry mirror, and an offline bundle is attached to every release.
- **More providers with automatic prices.** Scrapers for Chabokan, MobinHost and ParsPack, checked twice a day.
  ParsPack is priced exactly from a server's specs using the daily price table behind its official calculator.
  ArvanCloud prices are updated from reviewed price files, because its site blocks scraping.
- **Alerts** by email and Bale for price changes, failed updates, price moves held for review, and renewals.
- **Shared, signed price catalog,** so one installation can scrape for the others.
- **"How it works" page** that explains every calculation with worked examples. Tests check every number on it.
- **Plain-language suggestions.** Each one says what changes, what to ask the new provider before moving, and how
  long a move takes to pay for itself.
- Release workflow: tests, an offline bundle with checksums, and images on GitHub Container Registry for every tag.

### Changed

- Renamed to FinOps agent. Consulting referrals and unused credential storage were removed.
- Apache-2.0 license, contributor guide, security policy and an issue template for reporting a wrong price.
- Safer defaults: development ports listen only on your own computer, sign-up closes after the first account, and
  sign-in is rate limited.
- The Persian interface no longer shows raw field names, internal codes or JSON, and the Vazirmatn font is bundled
  instead of loaded from Google Fonts, which is unreliable from Iran and doesn't work offline.
- The Compare table shows only the rows where an option differs from your current server.
- CI runs on every push and pull request.

### Fixed

- Re-importing the starting catalog on restart overwrote newer scraped prices.
- A sync that found unchanged prices didn't count as a check, so prices read twice a day were shown as getting old.
- Upgrades kept serving the old Caddy configuration.
- An offline bundle couldn't be built on Windows, and a bundle built at another version or image prefix looked for
  images it didn't contain.

### Known limitations

- Prices are public list prices. Discounts, negotiated rates and fees not on the price page aren't included, and the
  totals haven't yet been checked against many real invoices. Please [report a wrong price](../../issues/new?template=wrong-price.md).
- When a provider changes a plan's specs but keeps its name, a server bought on the old plan is priced at the new
  plan's price, and the app doesn't warn about the mismatch yet.
- Price guardrails hold a sync for review when the median price moves more than 25%. A single plan that jumps is
  applied without review.
- ArvanCloud: no hourly proration rule, traffic direction unverified, prices updated by hand.
- Plan-based providers rarely publish prices for extra traffic, extra disk or extra IPv4 addresses. Those parts show
  as price unavailable, and one IPv4 address is assumed to be included (the quote says so).
- ParsPack's calculator doesn't price traffic or IPv4, and its one-time setup fee isn't part of the monthly figure.
- Liara PaaS and DBaaS traffic and Liara extra disk prices are unknown. Server.ir term discounts are unverified and
  never applied. Providers' invoice rounding rules are unknown, so the engine doesn't round.
- Downsizing suggestions need 14 days of measured usage.

## [0.1.0] — 2026-10-04

Internal MVP build. It was never published; the sections below record how it was built.

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

### Definition of Done

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
