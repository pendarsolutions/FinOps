# Pricing model

All arithmetic lives in `packages/pricing_engine` and uses `Decimal`. Floats are rejected at the
boundary (`to_decimal`, pydantic validators, the `Money` column type). The engine does not round
(`engine_policy.rounding.mode = "none"`): no provider in the seed documents its invoice rounding
boundary, so results stay exact and only the UI rounds for display.

Currency: Toman is the accounting/display unit. `*_rial = *_toman × 10` is always derived, never stored
independently.

## Result statuses

| Status | Meaning |
|---|---|
| `EXACT` | Every component priced from catalog rows. `monthly_total_toman` set. |
| `PRICE_UNAVAILABLE` | At least one component has no price (missing field, unknown SKU, overage price not published, …). `monthly_total_toman` is **null**; `priced_subtotal_toman` shows what *was* priced; `unavailable[]` names the component, missing field, reason and source. |
| `DISCOVERY_ONLY` | Abrha `starting_price`. Shown as `info` lines, never summed, never used for savings. |

A quote is `complete` only if every resource is `EXACT`; otherwise `total_toman` is null.

Line statuses: `priced`, `included` (catalog explicitly says 0 / unlimited), `assumed_included`
(visible assumption, no number — e.g. one IPv4 with a VPS), `unavailable`, `info`.

## Strategies (`engine_policy.json → providers.*.strategy`)

### `component` — ArvanCloud
- CPU = vCores × `IR-CPU-{CLASS}`; RAM = GB × `IR-RAM-{CLASS}`; class ∈ basic/standard/premium (required).
- Block storage = GB × rate for the exact `storage_type` (`hot_ssd`, `eco`, `warm`, `local`, …).
- GPU = count × the row whose `gpu_model` matches exactly.
- IPv4: first IP per server at `IR-IPV4-FIRST`, each additional at `IR-IPV4-EXTRA` (assumption recorded).
- Traffic: **graduated** tiers (each tier's price applies only to the GB inside it), evaluated per
  inventory resource. Resource `download` → catalog `outbound` (0), `upload` → catalog `inbound`
  tiers. The direction semantics on Arvan's page are **not verified**; every Arvan traffic quote says so
  and the equivalence score is capped at `medium`.
- Managed DB: `DB-CPU/RAM-{CLASS}` (starter/basic/standard/premium), `DB-ST-{HDD|SSD|LOCAL}`, `DB-IPV4`,
  traffic at the catalog's explicit 0.
- Object storage: graduated `OBJ-STD-*` tiers or flat `OBJ-HIOPS`.
- Scheduled runtime: the seed only has monthly rates and no proration rule → full month + assumption.

### `liara_plan` — Liara
- `billing_mode = hourly` (runtime explicitly limited): plan hourly × `active_hours_per_month`, IPv4 hourly × hours.
- otherwise: monthly plan + monthly IPv4.
- The engine never silently picks the cheaper cadence; REC-001/REC-004 compare both.
- IaaS: download 2,500 Toman/GB, upload 0 (catalog rows backed by `liara-iaas-network`).
- PaaS/DBaaS traffic is not in the seed → any non-zero (or unknown) traffic is `PRICE_UNAVAILABLE`.
- 720 h/month: Liara publishes both rates and only 720 h reconciles them
  (2,048 × 720 = 1,474,560 ≈ 1,475,000; 277 × 720 = 199,440 ≈ 200,000).

### `fixed_sku` — Server.ir, IranServer, MobinHost, Chabokan
- Base = plan monthly price × quantity. Chabokan 30-day plans = monthly (assumption recorded).
- Disk above the plan's disk → `PRICE_UNAVAILABLE` (extra-disk prices not in seed).
- Traffic by `traffic_policy` (derived at normalization from structured fields + official notes):
  `included_quota` (Server.ir counts download only; others download+upload, conservative) — overage
  is `PRICE_UNAVAILABLE` because no overage price is published; `fair_use` (50 GB/day × 30);
  `unlimited`; `unlimited_rate_limited` (8 Mbps, assumption); `metered_download` (rate from the
  official plan description, e.g. 1,600 Toman/GB on Server.ir IRFH since the 2026-10-04 live sync).
- Tax only when the provider has an **active** tax rule: Server.ir `serverir-vat` 10%, emitted as a
  separate `tax.vat` line when `include_tax=true`, never folded into the base price.
- Sold-out plans can still be priced as the *current* plan (flagged) but never as a candidate.
- Term discounts (`serverir-discounts`, `needs_checkout_verification`) are never applied; REC-004
  surfaces them as information with no number.

### `daily_table` — ParsPack
- Each size has its own daily price: month = (CPU + RAM + disk daily prices) × 30 × quantity.
- A size between two sold sizes uses the next one up, with a recorded assumption. A size beyond the table is `PRICE_UNAVAILABLE`.
- The official calculator prices no traffic or IPv4, and the price list mentions a 7-day setup fee. These are visible
  assumptions on every quote, not numbers.
- Not yet offered as a candidate when comparing other providers' servers.

## Equivalence (`equivalence_rules.json`)

1. Candidate generation: every exact-eligible compute SKU of other providers, plus synthesized
   ArvanCloud configurations (same vCPU/RAM/disk at each class; disk type mapped via `storage_type_map`).
2. Hard constraints: CPU ≥, RAM ≥, disk ≥, available, exact-eligible pricing model, Iran-only unless
   the user opts in, no dedicated→shared CPU downgrade, and the candidate must price **exactly** for the
   same workload (traffic, IPv4, …).
3. Weighted fit score (cpu .25, ram .25, storage .15, cpu class .15, traffic .10, datacenter .05,
   cadence .05). Oversizing lowers the score.
4. Confidence: high ≥ .85, medium ≥ .70, else `NEEDS_HUMAN_REVIEW`; unknown CPU class or unverified
   traffic direction caps at medium.
5. Differences listed explicitly: cores, CPU class, RAM, disk size/type, included traffic, traffic
   cost, IPv4 cost, datacenter, billing cadence, unknown features.

## Recommendations (`recommendation_rules.json`)

| Rule | When | Number source |
|---|---|---|
| REC-001 | non-prod, billed monthly, known runtime < 720 h, hourly rate exists | monthly vs hourly quote of the same SKU |
| REC-002 | p95 CPU/RAM over ≥14 days, utilisation below thresholds, smaller SKU covers p95 × 1.3 (+ measured disk) | quote of the smaller SKU; **never from allocation alone** |
| REC-003 | equivalence candidate with confidence ≥ medium and lower exact cost | candidate quote; migration cost = effort days × org day rate (else `UNKNOWN_MIGRATION_COST`) |
| REC-004 | the other cadence is cheaper for the stated runtime; unverified term discounts as info | both cadence quotes |
| REC-005 | a rule could apply but input is missing, or the current cost is not exact | none (lists missing inputs) |

Thresholds: saving ≥ 50,000 Toman and ≥ 3%. "Avoidable spend" counts only the single largest
actionable saving per resource — alternatives for the same resource are never added together.
