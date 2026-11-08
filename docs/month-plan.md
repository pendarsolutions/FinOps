# One-month plan: 8 November – 6 December 2026

**Goal for the month:** a team that has never seen FinOps agent can install it on an Iranian server, and then use
it every month to see what they spent, who spent it, whether they're on budget, and which savings actually happened.

Today the app answers one question once: "what does this setup cost, and what could I save?". That is the first
step of FinOps (*Inform*), done as a one-off. The FinOps Foundation describes a cycle: **Inform** (visibility,
allocation, anomalies), **Optimize** (rightsizing, better plans), **Operate** (budgets, ownership, follow-through).
Most teams this app is for are at the first maturity stage ("Crawl"). They need to see real spend and who owns it
before optimisation helps, so the month is ordered that way.

## How we'll know it worked (by 6 December)

| Measure | Target |
|---|---|
| Install from the README on a clean Iranian server, with Docker Hub unreachable | Works first time, under 15 minutes |
| Published releases with images and an offline bundle | 0.2.0 now, 0.3.0 (week 1), 0.4.0 (week 4) |
| A team records three months of actual spend | Sees the trend, the budget status, and the cost per team |
| Every suggestion has an outcome | Accepted, dismissed with a reason, or done, with the realised saving measured |
| A monthly report reaches people without opening the app | By email or Bale, in Persian or English |
| Browser smoke test runs in CI on every change | Sign-in, costs, savings, both languages |

## Week 1 (8–14 Nov): a stranger can install it

**Status, 8 Nov:** the code is done. Also fixed on the way: `./install.sh` wasn't executable in git, so the README's install command failed on a fresh clone. What's left needs the maintainer.

**Goal:** someone following the README gets a working, maintainable installation.

| | Item | Why | Status |
|---|---|---|---|
| P0 | Publish **0.2.0**: tag it, so CI publishes the images, the offline bundle and the release page | The README's "latest release" link is dead and `install.sh` falls back to building from Docker Hub, which is often blocked in Iran | Waiting on maintainer: push the tag |
| P0 | Merge the Pendar redesign and motion into `main`; delete the stale `finops-agent-iran` branch on GitHub | `main` is the public source; the redesign exists only on one machine | Merged locally; Waiting on maintainer: push `main`, delete the branch |
| P0 | **Password reset**: an admin CLI command, and an emailed reset link when email is set up | There is no way back in after a forgotten password | Done |
| P0 | **Members**: change a member's role, remove a member | Members can only be added today | Done |
| P0 | **Backup and restore**: one command each (database, settings, uploads), plus a daily backup option and docs | Losing the database loses all price history and saved quotes | Done; full round trip on the test VPS |
| P1 | Jalali dates throughout the Persian interface | The README promises them; the app shows Gregorian dates | Done, and the Persian report |
| P1 | Translate the remaining English statuses (`OK`, `WARNING`, `FAILED`) | Mixed languages confuse Persian users | Done |
| P0 | Publish **0.3.0** (redesign, motion, the items above) | | Notes ready; after the VPS test |
| P0 | Clean install test on a fresh Iranian VPS with Docker Hub blocked, notes fixed in the docs | The real first-time path has never been walked end to end | Waiting on maintainer: a fresh VPS |

## Week 2 (15–21 Nov): what you actually paid

**Goal:** the app records real spend over time, not only what a setup *would* cost.

| | Item | Why | Status |
|---|---|---|---|
| P0 | **Spend ledger**: what was paid, per provider and month, from an invoice, a wallet top-up, or by hand | Every FinOps step after this needs actual spend over time | |
| P0 | Invoices create spend entries (they only create an inventory today) | Reuses the invoice parser the app already has | |
| P0 | **Spend page**: monthly totals per provider, trend chart, month-over-month change | The first reason to come back every month | |
| P0 | **Monthly snapshot**: on the 1st, the confirmed infrastructure is priced and saved automatically | Turns one-off quotes into a cost trend | |
| P1 | **Estimated vs paid**: compare the snapshot with the ledger and flag gaps | Catches missing resources and price changes; it's on the README roadmap | |
| P1 | Edits no longer lock the cost pages: the last confirmed version stays live until the new one is confirmed | One edit currently blocks Costs and Savings | |
| P2 | Import spend from CSV | For teams with a year of history in a spreadsheet | |

## Week 3 (22–28 Nov): who spent it, and are we on budget

**Goal:** every toman has an owner, and the team hears about overspend before the month ends.

| | Item | Why | Status |
|---|---|---|---|
| P0 | **Owners**: team or project on resources, servers and spend entries; unallocated spend shown as its own line | Showback (each team sees its cost) is the core of FinOps; unallocated spend is the signal to fix | |
| P0 | **Budgets**: monthly budget for the organisation and for each team, with month-to-date and a projected month-end | | |
| P0 | Budget alerts at 80% and 100%, through the existing email and Bale alerts | | |
| P1 | **Unusual change** alerts: a provider's or team's month jumps by more than a set percentage | Manual, monthly anomaly review is where Crawl teams start | |
| P2 | Per-team view of the Overview page | | |

## Week 4 (29 Nov – 5 Dec): savings that get done, and the monthly report

**Goal:** suggestions turn into decisions, and the month's story arrives by itself.

| | Item | Why | Status |
|---|---|---|---|
| P0 | **Suggestion outcomes**: accepted, dismissed with a reason, done; an owner and a target date | Every suggestion stays "proposed" forever today | |
| P0 | **Realised savings**: after a suggestion is done, compare the next month's cost and report realised vs potential | Proves the tool pays for itself | |
| P0 | **Monthly report** on the 1st, by email or Bale: spend, change, budget, biggest movers, open and realised savings | The habit that brings people back | |
| P0 | **Browser smoke test in CI** (no new dependencies) | The web app has no automated tests | |
| P0 | Publish **0.4.0**; update the README and roadmap | | |
| P2 | A public, read-only demo instance | Lets people try it before installing | |

## Not this month

ArvanCloud API import, the small agent for servers behind NAT, CDN, Kubernetes and domains in the catalog, a
hosted signed price catalog run by Pendar, and the product rename. These are next, in roughly that order.

## Risks

| Risk | Impact | What we'll do |
|---|---|---|
| Images published by GitHub Actions may be private | `install.sh` can't pull them | Check right after the release; the repository owner makes the two packages public once |
| ghcr.io slow or blocked from some Iranian networks | Install falls back to building | The offline bundle on the release page; document it first |
| Weeks 2–4 are large | Something slips | P1 and P2 items are cut first; P0 items ship |
| Upgrading existing installations | Data loss on upgrade | Every schema change is an Alembic migration, tested from a 0.2.0 database |

## Needs from the maintainer

- A fresh Iranian VPS for the week 1 install test (it can be deleted afterwards).
- Making the two GitHub packages public after the first release, if they come out private.
- An SMTP account or a Bale bot to test the monthly report in week 4.

## Definition of done (every item)

- Tests for the new behaviour, all tests passing, `ruff` and the type-check clean.
- Database changes are migrations that upgrade an existing 0.2.0 install.
- Persian and English text, right-to-left checked, Pendar tokens only.
- Docs updated where users or self-hosters would look.
