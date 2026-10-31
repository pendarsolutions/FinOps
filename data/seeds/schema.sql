-- Pendar FinOps MVP schema (PostgreSQL 16+)
-- Money is stored as integer TOMAN where possible. Never use float for money.
-- Chabokan snapshot has a fractional Toman hourly storage rate; store raw provider values in NUMERIC.

CREATE TABLE providers (
  id TEXT PRIMARY KEY,
  name_en TEXT NOT NULL,
  name_fa TEXT,
  website TEXT NOT NULL,
  official_pricing_url TEXT,
  country CHAR(2) NOT NULL DEFAULT 'IR',
  pricing_model TEXT NOT NULL,
  api_status TEXT NOT NULL DEFAULT 'not_verified',
  public_catalog_quality TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE price_sources (
  id BIGSERIAL PRIMARY KEY,
  provider_id TEXT NOT NULL REFERENCES providers(id),
  source_url TEXT NOT NULL,
  source_kind TEXT NOT NULL CHECK (source_kind IN ('official','secondary','invoice','api')),
  retrieved_at TIMESTAMPTZ NOT NULL,
  provider_price_date TEXT,
  content_hash TEXT,
  sync_status TEXT NOT NULL DEFAULT 'ok',
  raw_snapshot JSONB,
  UNIQUE(provider_id, source_url, retrieved_at)
);

CREATE TABLE catalog_items (
  id TEXT PRIMARY KEY,
  provider_id TEXT NOT NULL REFERENCES providers(id),
  service_type TEXT NOT NULL,
  product_family TEXT,
  sku TEXT,
  display_name TEXT NOT NULL,
  pricing_model TEXT NOT NULL,
  region_country CHAR(2),
  region TEXT,
  datacenter TEXT,
  resource_class TEXT,
  cpu_cores NUMERIC(10,3),
  cpu_unit TEXT,
  cpu_shared BOOLEAN,
  ram_gb NUMERIC(12,3),
  storage_gb NUMERIC(14,3),
  storage_type TEXT,
  gpu_model TEXT,
  gpu_count NUMERIC(10,3),
  included_traffic_gb NUMERIC(16,3),
  traffic_direction TEXT,
  bandwidth TEXT,
  billing_period TEXT,
  price_toman NUMERIC(24,4),
  hourly_price_toman NUMERIC(24,4),
  daily_price_toman NUMERIC(24,4),
  price_unit TEXT,
  tier_min NUMERIC(24,4),
  tier_max NUMERIC(24,4),
  tier_unit TEXT,
  availability TEXT NOT NULL DEFAULT 'available',
  confidence TEXT NOT NULL DEFAULT 'high',
  tax_included BOOLEAN,
  valid_from TIMESTAMPTZ NOT NULL,
  valid_to TIMESTAMPTZ,
  source_id BIGINT REFERENCES price_sources(id),
  attributes JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX catalog_provider_service_idx
  ON catalog_items(provider_id, service_type, valid_to);
CREATE INDEX catalog_specs_idx
  ON catalog_items(service_type, cpu_cores, ram_gb, storage_gb);

CREATE TABLE inventories (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  name TEXT NOT NULL,
  currency TEXT NOT NULL DEFAULT 'TOMAN',
  status TEXT NOT NULL CHECK (status IN ('draft','needs_confirmation','confirmed','archived')),
  source_type TEXT NOT NULL CHECK (source_type IN ('builder','chat','invoice','csv','cloud_connection','agent','terraform','kubernetes')),
  confirmed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE inventory_resources (
  id UUID PRIMARY KEY,
  inventory_id UUID NOT NULL REFERENCES inventories(id) ON DELETE CASCADE,
  external_ref TEXT,
  environment TEXT,
  service_type TEXT NOT NULL,
  provider_id TEXT REFERENCES providers(id),
  sku TEXT,
  region TEXT,
  datacenter TEXT,
  quantity NUMERIC(16,4) NOT NULL DEFAULT 1,
  cpu_cores NUMERIC(10,3),
  ram_gb NUMERIC(12,3),
  storage_gb NUMERIC(14,3),
  storage_type TEXT,
  expected_monthly_download_gb NUMERIC(18,3),
  expected_monthly_upload_gb NUMERIC(18,3),
  active_hours_per_month NUMERIC(10,2),
  requires_public_ipv4 BOOLEAN DEFAULT FALSE,
  user_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
  raw_input JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE price_quotes (
  id UUID PRIMARY KEY,
  inventory_id UUID NOT NULL REFERENCES inventories(id),
  provider_id TEXT NOT NULL REFERENCES providers(id),
  quote_month DATE NOT NULL,
  total_toman NUMERIC(24,4) NOT NULL,
  component_breakdown JSONB NOT NULL,
  assumptions JSONB NOT NULL,
  catalog_snapshot_at TIMESTAMPTZ NOT NULL,
  deterministic_engine_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE recommendations (
  id UUID PRIMARY KEY,
  inventory_id UUID NOT NULL REFERENCES inventories(id),
  rule_id TEXT NOT NULL,
  resource_id UUID REFERENCES inventory_resources(id),
  recommendation_type TEXT NOT NULL,
  current_cost_toman NUMERIC(24,4),
  candidate_cost_toman NUMERIC(24,4),
  monthly_saving_toman NUMERIC(24,4),
  monthly_saving_percent NUMERIC(10,4),
  one_time_migration_cost_toman NUMERIC(24,4),
  payback_months NUMERIC(12,3),
  risk_level TEXT NOT NULL,
  effort_level TEXT,
  confidence TEXT NOT NULL,
  evidence JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'proposed',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ai_runs (
  id UUID PRIMARY KEY,
  organization_id UUID NOT NULL,
  purpose TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  input_redacted JSONB NOT NULL,
  tool_calls JSONB NOT NULL,
  output_text TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE price_sync_runs (
  id UUID PRIMARY KEY,
  provider_id TEXT NOT NULL REFERENCES providers(id),
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  status TEXT NOT NULL,
  items_seen INTEGER NOT NULL DEFAULT 0,
  items_changed INTEGER NOT NULL DEFAULT 0,
  error TEXT
);