# Provider adapters

Interface (`packages/provider_adapters/base.py`):

```python
class ProviderAdapter(Protocol):
    provider_id: str
    source_url: str
    scope: set[tuple[str, str | None]]   # (service_type, product_family) this adapter is authoritative for
    key_skus: set[str]                   # absence -> warning
    async def fetch_catalog(self) -> RawCatalog: ...
    def normalize_catalog(self, raw: RawCatalog) -> list[CatalogItem]: ...
    async def healthcheck(self) -> AdapterHealth: ...

class InventoryConnector(Protocol):      # reserved, post-MVP, read-only credentials only
    async def list_resources(self, credentials): ...
    async def get_billing_export(self, credentials, month): ...
```

Adapters never invent values: an unstated field stays `None`; an unrecognised page raises
`ParseError` (a failed sync), never an empty or zero price. Rows from adapters go through the same
`derive_attributes` normalization as the seed so seed and live rows compare like-for-like.

## Status (verified against the official pages on 2026-10-04)

| Provider | Adapter | Source | Status | Notes |
|---|---|---|---|---|
| ArvanCloud | `ArvanCloudAdapter` | /fa/pricing/all | **blocked** | Non-browser clients get a JS bot-challenge page. The adapter detects it and fails the sync visibly (`SourceBlockedError`). Seed snapshot (price date 1405-03-30 = 2026-06-20) stays active and ages via freshness warnings. Next: ArvanCloud API connector (documented API exists). |
| Liara | `LiaraAdapter` | /pricing/ | **live** | Parses PaaS / DBaaS / IaaS cards (sections found by heading), Persian digits, and the IaaS sentence for download/upload/IPv4. Email, AI and WordPress plans are out of scope and skipped. Object storage (`OBJECT-20GB`) is not on this page — outside the adapter's scope, so sync leaves it untouched. Live = seed (0 changes). |
| Server.ir | `ServerIrAdapter` | /vps/iran/ | **live** | Parses `div.isotope-item` cards: SKU, vCore vs Core (+ "نوع سرور" class), RAM, disk, traffic text, datacenter, monthly price from `data-price`, VAT kept separate. **Live differs from seed**: IRFH5024/5048/8048/1001224 now meter download at 1,600 Toman/GB (seed: fair-use 50 GB/day) and IRFH80612 is delisted. A sync versions these; history keeps the seed values. |
| IranServer | `IranServerAdapter` | /vps/iran/ | **live** | Parses the NGP-* General Purpose table only; other families are dynamic and not fabricated. Live = seed. |
| Chabokan | — | — | seed only | Large dynamic plan list. Sync reports `not_implemented`. |
| ParsPack | — | — | seed only (discovery) | Use the documented Cloud Server API for an exact catalog; the HTML configurator is not exact. |
| MobinHost | — | — | seed only | Server-rendered pages; parser to be written. Sold-out flags matter. |
| Abrha | — | — | seed only (discovery) | Only a starting price is public. |

Fixtures: real pages saved on 2026-10-04 in `tests/fixtures/providers/*.html.gz`. CI never hits live
sites. Refresh a fixture by saving the page again and re-running `tests/providers`.

## Sync pipeline

`run_provider_sync` (API `POST /api/v1/admin/providers/{id}/sync`, CLI `make sync-prices`, worker
nightly 03:15 Asia/Tehran):

1. fetch → 2. normalize → 3. `plan_sync` guardrails → 4. apply (close + insert versions) or hold.

| Guardrail | Result |
|---|---|
| fetch/parse error, bot challenge | `failed` (nothing applied, visible on Providers/Integrations) |
| zero items | `failed` |
| median \|price change\| > 25% across matched rows | `quarantined`: new rows stored in `pending_items`, admin approves via `POST /admin/sync-runs/{id}/approve` |
| key SKU missing | `warning` (row closed as `removed`) |
| source hash changed, parser output unchanged | `warning` |
| provider price date older than `stale_after_days` | `warning` |

Only rows inside an adapter's `scope` can be closed. Failures and quarantines are logged at ERROR as
structured JSON (`{"alert": "price_sync", ...}`) for the alerting stack.

## Adding an adapter

1. Save the official page as a gzipped fixture.
2. Implement `normalize_catalog` with `base_item(...)`; set `scope` and `key_skus`.
3. Assert in a test that parsed rows match the current seed rows (or document each difference).
4. Register in `provider_adapters/__init__.py: ADAPTERS`.
