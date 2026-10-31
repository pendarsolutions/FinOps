# Contributing

Thanks for helping Iranian teams understand their infrastructure costs.

## Setup

```bash
make install
make test
make api      # http://localhost:8000/docs
make web      # http://localhost:5173
```

On Windows without `make`, use `.\scripts\finops.ps1 <target>`.

## Rules that are not negotiable

1. **The AI never calculates a price or saving.** Every number comes from the deterministic engine.
2. **Never invent a price.** Missing data stays missing and surfaces as `PRICE_UNAVAILABLE`.
3. **Money is `Decimal`, never float,** and field names carry their unit (`price_toman`).
4. **Price history is never overwritten.** Close the old version and insert a new one.
5. **Server access stays read-only.** Nothing may change, resize or delete anything on a monitored server.

## Adding a provider scraper

Read [docs/provider-adapters.md](docs/provider-adapters.md). In short:

1. Save the official page as a small fixture in `tests/fixtures/providers/`.
2. Add an adapter in `packages/provider_adapters/` and register it in `ADAPTERS`.
3. Declare its `scope` and `key_skus`, and raise `ParseError` when the page can't be understood.
4. Add tests against the fixture. CI never touches live websites.
5. Check that the provider's terms allow automated reading. Don't bypass bot protection.

## Pull requests

Keep them small, add tests, and run `make test` and `make lint` first.
