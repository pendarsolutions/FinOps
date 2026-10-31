/** Types mirroring the FinOps agent API responses. Money and quantities are exact decimal strings. */

export type Dec = string;
export type Role = "viewer" | "analyst" | "admin" | "owner";

export interface Session {
  access_token: string;
  token_type: string;
  user: { id: string; email: string; name: string; locale: string | null };
  organization: { id: string; name: string };
  role: Role;
}

export type ServiceType = "compute_vm" | "paas" | "dbaas" | "object_storage";
export type ReviewStatus = "confirmed" | "needs_review" | "unresolved";

/** shared_types.ResourceDraft */
export interface ResourceDraft {
  name: string;
  external_ref: string | null;
  environment: string | null;
  service_type: ServiceType;
  provider_id: string | null;
  sku: string | null;
  resource_class: string | null;
  region: string | null;
  datacenter: string | null;
  quantity: Dec | null;
  cpu_cores: Dec | null;
  cpu_shared: boolean | null;
  ram_gb: Dec | null;
  storage_gb: Dec | null;
  storage_type: string | null;
  gpu_model: string | null;
  gpu_count: Dec | null;
  expected_monthly_download_gb: Dec | null;
  expected_monthly_upload_gb: Dec | null;
  active_hours_per_month: Dec | null;
  requires_public_ipv4: boolean | null;
  ipv4_count: Dec | null;
  billing_mode: "monthly" | "hourly" | null;
  metrics: Record<string, unknown> | null;
  field_confidence: Record<string, number>;
  unknown_fields: string[];
  notes: string | null;
}

export type DraftField = Exclude<keyof ResourceDraft, "field_confidence" | "unknown_fields" | "metrics">;

export interface ResourceView extends ResourceDraft {
  id: string;
  position: number;
  user_confirmed: boolean;
  required_fields: string[];
  missing_fields: string[];
  low_confidence_fields: string[];
  review_status: ReviewStatus;
  extraction_confidence: number;
}

export interface BlockingRow {
  resource_id: string;
  name: string;
  review_status: ReviewStatus;
  missing_fields: string[];
}

export interface InvoiceLine {
  text: string;
  matched_sku: string | null;
  provider_id: string | null;
  quantity: Dec | null;
  invoice_amount: Dec | null;
  invoice_amount_currency: string;
  confidence: number;
}

export interface InvoiceMeta {
  detected_currency: string;
  currency_evidence: string[];
  currency_confirmation_required: boolean;
  provider_id: string | null;
  redaction_counts: Record<string, number>;
  unmatched_lines: string[];
  lines: InvoiceLine[];
  note: string;
}

export interface SourceMeta {
  questions?: string[];
  demo?: boolean;
  note?: string;
  extraction?: { prompt_version: string; path: string; model?: string };
  detected_currency?: string | null;
  invoice?: InvoiceMeta;
  upload_id?: string;
  invoice_currency_confirmed?: "TOMAN" | "RIAL";
}

export interface InventorySummary {
  id: string;
  name: string;
  status: string;
  source_type: string;
  created_at: string;
  confirmed_at: string | null;
}

export interface InventoryView {
  id: string;
  name: string;
  status: "draft" | "needs_confirmation" | "confirmed" | "archived" | string;
  source_type: string;
  currency: "TOMAN" | "UNCONFIRMED" | string;
  source_meta: SourceMeta;
  confirmed_at: string | null;
  created_at: string;
  resources: ResourceView[];
  can_confirm: boolean;
  can_analyze: boolean;
  blocking: BlockingRow[];
  upload?: { id: string; filename: string; download_url: string | null; delete_after: string; deleted: boolean } | null;
  invoice_currency?: "TOMAN" | "RIAL" | "UNKNOWN" | null;
}

// ------------------------------------------------------------------ pricing

export type LineStatus = "priced" | "included" | "assumed_included" | "unavailable" | "info";

export interface ComponentLine {
  code: string;
  description: string;
  status: LineStatus;
  quantity: Dec | null;
  unit: string | null;
  unit_price_toman: Dec | null;
  subtotal_toman: Dec | null;
  catalog_item_id: string | null;
  catalog_version_id: string | null;
  source_url: string | null;
  price_date: string | null;
  retrieved_at: string | null;
  note: string | null;
}

export interface PriceUnavailable {
  code: "PRICE_UNAVAILABLE";
  component: string;
  missing_field: string;
  reason: string;
  source: string | null;
}

export interface PriceBreakdown {
  resource_id: string;
  resource_name: string;
  provider_id: string | null;
  status: "EXACT" | "PRICE_UNAVAILABLE" | "DISCOVERY_ONLY";
  quantity: Dec;
  components: ComponentLine[];
  tax_lines: ComponentLine[];
  monthly_total_toman: Dec | null;
  priced_subtotal_toman: Dec;
  monthly_tax_toman: Dec | null;
  unavailable: PriceUnavailable[];
  assumptions: string[];
  monthly_total_rial?: Dec | null;
  monthly_total_with_tax_toman?: Dec | null;
}

export interface PriceSource {
  provider_id: string;
  source_url: string | null;
  retrieved_at: string | null;
  provider_price_date: string | null;
  provider_price_date_gregorian: string | null;
  age_days: number | null;
  freshness: "fresh" | "aging" | "stale" | "unknown";
}

export interface QuoteContent {
  engine_version: string;
  policy_version: string;
  catalog_version: string;
  catalog_snapshot_at: string;
  complete: boolean;
  total_toman: Dec | null;
  priced_subtotal_toman: Dec;
  total_tax_toman: Dec | null;
  breakdowns: PriceBreakdown[];
  provider_totals: { provider_id: string; monthly_total_toman: Dec | null; priced_subtotal_toman: Dec; complete: boolean }[];
  assumptions: string[];
  unavailable: PriceUnavailable[];
  price_sources: PriceSource[];
  inventory_hash: string;
  content_hash: string;
  total_rial?: Dec | null;
}

export interface QuoteSummary {
  id: string;
  inventory_id: string;
  created_at: string;
  catalog_version: string;
  policy_version: string;
  engine_version: string;
  complete: boolean;
  include_tax: boolean;
  total_toman: Dec | null;
  priced_subtotal_toman: Dec;
  total_tax_toman: Dec | null;
  content_hash: string;
}

export interface QuoteView extends QuoteSummary {
  content: QuoteContent;
}

// ------------------------------------------------------------------ equivalence

export type Verdict = "same" | "better" | "worse" | "different" | "unknown";

export interface Difference {
  dimension: string;
  source_value: unknown;
  candidate_value: unknown;
  verdict: Verdict;
  note: string | null;
}

export interface ConstraintResult {
  constraint_id: string;
  passed: boolean;
  detail: string;
}

export interface Comparison {
  resource_id: string;
  candidate_provider_id: string;
  candidate_label: string;
  candidate_catalog_item_ids: string[];
  current: PriceBreakdown;
  candidate: PriceBreakdown;
  constraints: ConstraintResult[];
  passed_hard_constraints: boolean;
  fit_score: Dec | null;
  score_breakdown: Record<string, Dec>;
  confidence: "high" | "medium" | "NEEDS_HUMAN_REVIEW" | "not_equivalent";
  differences: Difference[];
  monthly_saving_toman: Dec | null;
  monthly_saving_percent: Dec | null;
  exact: boolean;
  assumptions: string[];
}

export interface RejectedCandidate {
  provider_id: string;
  label: string;
  catalog_item_ids: string[];
  failed_constraints: ConstraintResult[];
}

export interface CompareResult {
  resource_id: string;
  resource_name: string;
  source_specs: Record<string, unknown>;
  candidates: Comparison[];
  rejected: RejectedCandidate[];
  notes: string[];
}

export interface CompareResponse {
  catalog_version: string;
  allow_outside_iran: boolean;
  results: CompareResult[];
}

// ------------------------------------------------------------------ recommendations

export interface Recommendation {
  id: string;
  key: string;
  analysis_id: string;
  quote_id: string;
  inventory_id: string;
  rule_id: string;
  resource_id: string | null;
  resource_name: string | null;
  provider_id: string | null;
  recommendation_type: string;
  result_status: "actionable" | "cannot_determine" | "informational";
  title_en: string;
  title_fa: string;
  summary_en: string;
  summary_fa: string;
  current_cost_toman: Dec | null;
  candidate_cost_toman: Dec | null;
  monthly_saving_toman: Dec | null;
  monthly_saving_percent: Dec | null;
  one_time_migration_cost_toman: Dec | null;
  payback_months: Dec | null;
  payback_status: string | null;
  risk_level: string;
  effort_level: string;
  confidence: string;
  price_dates: string[];
  missing_inputs: string[];
  evidence: Record<string, unknown> & {
    current?: Partial<PriceBreakdown>;
    candidate?: Partial<PriceBreakdown>;
    constraints?: ConstraintResult[];
    differences?: Difference[];
    candidate_label?: string;
    fit_score?: Dec;
  };
  status: string;
  created_at: string;
}

export interface RecSummary {
  avoidable_monthly_toman: Dec;
  potential_saving_percent: Dec | null;
  counted_recommendation_keys: string[];
  method: string;
  actionable_count: number;
  cannot_determine_count: number;
}

export interface RecsResponse {
  analysis_id: string | null;
  quote_id: string | null;
  summary: RecSummary | null;
  recommendations: Recommendation[];
  quote_total_toman?: Dec | null;
  quote_complete?: boolean;
}

export interface Overview {
  inventory: { id: string; name: string; status: string };
  quote: QuoteSummary | null;
  unavailable: PriceUnavailable[];
  summary: RecSummary | null;
  provider_distribution: { provider_id: string; monthly_toman: Dec }[];
  environment_distribution: { environment: string; monthly_toman: Dec }[];
  top_opportunities: Recommendation[];
  price_freshness: PriceSource[];
  catalog_version: string;
}

// ------------------------------------------------------------------ catalog / providers

export interface CatalogItem {
  id: string;
  provider_id: string;
  service_type: string;
  pricing_model: string;
  product_family: string | null;
  sku: string | null;
  name: string;
  region_country: string | null;
  region: string | null;
  datacenter: string | null;
  resource_class: string | null;
  cpu_cores: Dec | null;
  cpu_unit: string | null;
  cpu_shared: boolean | null;
  ram_gb: Dec | null;
  storage_gb: Dec | null;
  storage_type: string | null;
  gpu_model: string | null;
  gpu_count: Dec | null;
  included_traffic_gb: Dec | null;
  traffic_direction: string | null;
  bandwidth: string | null;
  billing_period: string | null;
  price_toman: Dec | null;
  hourly_price_toman: Dec | null;
  daily_price_toman: Dec | null;
  unit: string | null;
  tier_min: Dec | null;
  tier_max: Dec | null;
  tier_unit: string | null;
  availability: string;
  source_url: string | null;
  source_retrieved_at: string | null;
  source_price_date: string | null;
  confidence: string;
  tax_included: boolean | null;
  notes: string | null;
  valid_from: string | null;
  valid_to: string | null;
  version_id: string | null;
  attributes: Record<string, unknown>;
  price_rial?: Dec | null;
  exact_eligible: boolean;
  version_count?: number;
  source_id?: string;
  created_at?: string;
}

export interface SyncRun {
  id: string;
  provider_id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  items_seen: number | null;
  items_changed: number | null;
  error: string | null;
  warnings: unknown;
  summary: unknown;
  triggered_by: string | null;
  has_pending_items: boolean;
}

export interface ProviderInfo {
  id: string;
  name_en: string;
  name_fa: string | null;
  website: string;
  official_pricing_url: string | null;
  pricing_model: string;
  integration_status: string;
  catalog_quality: string;
  metadata: Record<string, unknown>;
  engine_strategy: string | null;
  exact_eligible: boolean | null;
  adapter: "live_parser" | "seed_only";
  adapter_note: string | null;
  catalog_items: number;
  sources: PriceSource[];
  last_sync: SyncRun | null;
}

export interface Integrations {
  price_adapters: { provider_id: string; status: string; note: string | null }[];
}

export interface OrgSettings {
  organization: { id: string; name: string };
  settings: { engineer_day_rate_toman?: string; engineer_day_rate_label?: string; default_language?: string } & Record<string, unknown>;
  role: Role;
}

export interface AuditEntry {
  id: string;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  user_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface AdvisorAnswer {
  answer: string;
  path: string;
  evidence_ids: string[];
  guard: { ok: boolean; unsupported_numbers?: string[]; numbers_checked?: number } & Record<string, unknown>;
  tool_calls: { tool: string; input: unknown; error: string | null }[];
  ai_run_id: string;
}

export interface Member {
  id: string;
  email: string;
  name: string;
  role: string;
}
