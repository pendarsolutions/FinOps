import { Fragment, useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { InventoryView, ResourceView } from "../api/types";
import { useI18n, type TKey } from "../lib/i18n";
import { environmentColor, providerColor } from "../lib/viz";
import { ConfidenceRing, Initial, Rec, RecList, ServiceIcon } from "./records";
import { Loader } from "./Brand";
import { useInventoryMutation, useProviders } from "../lib/hooks";
import { localizeDigits } from "../lib/money";
import { Badge, Button, Card, Date_, ErrorBox, ReviewBadge } from "./ui";
import { Icon } from "./Icon";

const DEC_RE = /^\d+(\.\d+)?$/;
export const ENVIRONMENTS = ["production", "staging", "development", "test", "ci", "other"];
export const SERVICE_TYPES = ["compute_vm", "paas", "dbaas", "object_storage"] as const;

/** Accept Persian/Arabic-Indic digits and separators typed by the user. */
export function normalizeDigits(s: string): string {
  return s
    .replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d)))
    .replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)))
    .replace(/[٫]/g, ".")
    .replace(/[,٬\s]/g, "");
}

type Kind = "dec" | "text" | "bool" | "select";
type Patch = (rid: string, body: { fields?: Record<string, unknown>; user_confirmed?: boolean }) => void;

function cellClass(r: ResourceView, field: string): string {
  if (r.missing_fields.includes(field)) return "cell cell-missing";
  if (r.unknown_fields.includes(field)) return "cell cell-unknown";
  if (r.low_confidence_fields.includes(field)) return "cell cell-low";
  return "cell";
}

function EditCell({ r, field, kind, options, patch, label, wide }: { r: ResourceView; field: keyof ResourceView & string; kind: Kind; options?: { value: string; label: string }[]; patch: Patch; label: string; wide?: boolean }) {
  const { t } = useI18n();
  const raw = r[field] as unknown;
  const current = raw === null || raw === undefined ? "" : String(raw);
  const [val, setVal] = useState(current);
  useEffect(() => setVal(current), [current]);
  const invalid = kind === "dec" && val !== "" && !DEC_RE.test(normalizeDigits(val));
  const commit = (v: string) => {
    if (v === current) return;
    let out: unknown = v === "" ? null : v;
    if (kind === "dec") {
      const n = normalizeDigits(v);
      if (n !== "" && !DEC_RE.test(n)) return;
      out = n === "" ? null : n;
      if (n === current) return;
    }
    if (kind === "bool") out = v === "" ? null : v === "true";
    patch(r.id, { fields: { [field]: out } });
  };
  const cls = `${cellClass(r, field)} ${invalid ? "cell-invalid" : ""}`;
  const title = r.low_confidence_fields.includes(field) ? `${label} — ${t("lowConfidenceLegend")}` : label;
  if (kind === "bool" || kind === "select") {
    const opts = kind === "bool" ? [{ value: "true", label: t("yes") }, { value: "false", label: t("no") }] : options ?? [];
    return (
      <select
        className={cls}
        aria-label={`${r.name}: ${label}`}
        title={title}
        value={val}
        onChange={(e) => {
          setVal(e.target.value);
          commit(e.target.value);
        }}
      >
        <option value="">{r.unknown_fields.includes(field) ? t("dontKnow") : "—"}</option>
        {opts.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
        {val && !opts.some((o) => o.value === val) ? <option value={val}>{val}</option> : null}
      </select>
    );
  }
  return (
    <input
      className={`${cls} ${wide ? "" : "narrow"}`}
      aria-label={`${r.name}: ${label}`}
      aria-invalid={invalid || undefined}
      title={title}
      inputMode={kind === "dec" ? "decimal" : undefined}
      dir={kind === "dec" ? "ltr" : "auto"}
      value={val}
      placeholder={r.unknown_fields.includes(field) ? t("dontKnow") : ""}
      onChange={(e) => setVal(e.target.value)}
      onBlur={() => commit(val)}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") setVal(current);
      }}
    />
  );
}

function MissingCell({ r, patch }: { r: ResourceView; patch: Patch }) {
  const { t, fieldLabel } = useI18n();
  const relevant = r.required_fields.filter((f) => r.missing_fields.includes(f) || r.unknown_fields.includes(f));
  if (!relevant.length) return null;
  const toggle = (f: string) => {
    const next = r.unknown_fields.includes(f) ? r.unknown_fields.filter((x) => x !== f) : [...r.unknown_fields, f];
    patch(r.id, { fields: { unknown_fields: next } });
  };
  return (
    <div className="rv-missing">
      <span className="rv-missing-title">
        <span aria-hidden>!</span> {t("rvMissingTitle")}
      </span>
      <ul className="missing-list">
      {relevant.map((f) => {
        const unknown = r.unknown_fields.includes(f);
        return (
          <li key={f} className={unknown ? "is-unknown" : "is-missing"}>
            <span>{fieldLabel(f)}</span>
            <label className="dontknow">
              <input type="checkbox" checked={unknown} onChange={() => toggle(f)} /> {t("dontKnow")}
            </label>
          </li>
        );
      })}
      </ul>
    </div>
  );
}

function InvoiceSummary({ inv }: { inv: InventoryView }) {
  const { t, lang } = useI18n();
  const providers = useProviders();
  const m = inv.source_meta.invoice;
  if (!m) return null;
  const red = Object.entries(m.redaction_counts ?? {});
  return (
    <Card title={t("invoiceExtraction")}>
      <dl className="kv">
        <dt>{t("detectedCurrency")}</dt>
        <dd>
          <Badge tone={m.detected_currency === "UNKNOWN" ? "warn" : "info"}>{m.detected_currency}</Badge>{" "}
          <small className="muted">{m.currency_evidence.join(" · ")}</small>
        </dd>
        <dt>{t("redactions")}</dt>
        <dd>{red.length ? red.map(([k, v]) => <Badge key={k}>{`${k}: ${localizeDigits(String(v), lang)}`}</Badge>) : "—"}</dd>
        {inv.upload && (
          <>
            <dt>{t("retentionUntil")}</dt>
            <dd>
              <Date_ v={inv.upload.delete_after} />
            </dd>
          </>
        )}
      </dl>
      {m.lines.length > 0 && (
        <RecList label={t("invoiceLine")} compact>
          {m.lines.map((l, i) => {
            const prov = providers.data?.find((p) => p.id === l.provider_id);
            const pName = prov ? (lang === "fa" ? prov.name_fa || prov.name_en : prov.name_en) : l.provider_id;
            return (
              <Rec
                key={i}
                accent={providerColor(l.provider_id).css}
                tone={l.confidence < 0.5 ? "bad" : l.confidence < 0.8 ? "warn" : undefined}
                icon={pName ? <Initial name={pName} /> : "?"}
                title={
                  <code dir="ltr" className="wrap-any">
                    {l.text}
                  </code>
                }
                meta={
                  <>
                    <span>{pName ?? "—"}</span>
                    <span>
                      SKU: <bdi>{l.matched_sku ?? "—"}</bdi>
                    </span>
                  </>
                }
                aside={<ConfidenceRing c={l.confidence} />}
              />
            );
          })}
        </RecList>
      )}
      {m.unmatched_lines.length > 0 && (
        <>
          <h3>{t("unmatchedLines")}</h3>
          <RecList label={t("unmatchedLines")} compact>
            {m.unmatched_lines.map((l, i) => (
              <Rec
                key={i}
                tone="warn"
                icon="?"
                title={
                  <code dir="ltr" className="wrap-any">
                    {l}
                  </code>
                }
              />
            ))}
          </RecList>
        </>
      )}
      <p className="muted small">{t("invoiceNote")}</p>
    </Card>
  );
}

const ENV_KEY: Record<string, TKey> = {
  production: "envProduction",
  staging: "envStaging",
  development: "envDevelopment",
  test: "envTest",
  ci: "envCi",
  other: "envOther",
};

/** Labelled field with an optional unit suffix; the control is the existing EditCell. */
function Field({ label, unit, children, wide }: { label: string; unit?: string; children: ReactNode; wide?: boolean }) {
  return (
    <label className={wide ? "rv-field rv-field-wide" : "rv-field"}>
      <span className="rv-label">{label}</span>
      <span className="rv-control">
        {children}
        {unit && <span className="rv-unit">{unit}</span>}
      </span>
    </label>
  );
}

/** Yes / No / unknown as a segmented control instead of a dropdown. */
function BoolSeg({ r, field, label, patch }: { r: ResourceView; field: keyof ResourceView & string; label: string; patch: Patch }) {
  const { t } = useI18n();
  const v = r[field] as boolean | null | undefined;
  const missing = r.missing_fields.includes(field);
  const opts: { val: boolean | null; text: string }[] = [
    { val: true, text: t("yes") },
    { val: false, text: t("no") },
    { val: null, text: "—" },
  ];
  return (
    <div className="rv-field">
      <span className="rv-label">{label}</span>
      <div className={`seg ${missing ? "seg-missing" : ""}`} role="radiogroup" aria-label={`${r.name}: ${label}`}>
        {opts.map((o) => {
          const on = (v ?? null) === o.val;
          return (
            <button
              key={String(o.val)}
              type="button"
              role="radio"
              aria-checked={on}
              className={on ? "on" : undefined}
              onClick={() => !on && patch(r.id, { fields: { [field]: o.val } })}
            >
              {o.text}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Summary({ r, provName }: { r: ResourceView; provName: string }) {
  const { t, lang } = useI18n();
  const d = (s: string | null | undefined) => localizeDigits(String(s), lang);
  const parts: string[] = [provName];
  if (r.environment) parts.push(ENV_KEY[r.environment] ? t(ENV_KEY[r.environment]) : r.environment);
  if (r.sku) parts.push(r.sku);
  if (r.cpu_cores) parts.push(`${d(r.cpu_cores)} ${t("rvCores")}`);
  if (r.ram_gb) parts.push(`${d(r.ram_gb)} GB RAM`);
  if (r.storage_gb) parts.push(`${d(r.storage_gb)} GB ${r.storage_type ?? ""}`.trim());
  // Each part is bidi-isolated so mixed Persian/Latin specs keep their own order.
  return (
    <span className="rv-summary">
      {parts.filter(Boolean).map((p, i) => (
        <Fragment key={i}>
          {i > 0 && <span aria-hidden> · </span>}
          <bdi>{p}</bdi>
        </Fragment>
      ))}
    </span>
  );
}

type Filter = "all" | "attention" | "confirmed";

function ResourceCard({
  r,
  open,
  onToggle,
  patch,
  opts,
  onDelete,
  deleting,
}: {
  r: ResourceView;
  open: boolean;
  onToggle: () => void;
  patch: Patch;
  opts: { prov: { value: string; label: string }[]; env: { value: string; label: string }[]; svc: { value: string; label: string }[]; bill: { value: string; label: string }[] };
  onDelete: () => void;
  deleting: boolean;
}) {
  const { t, fieldLabel: lbl } = useI18n();
  const [more, setMore] = useState(false);
  const prov = providerColor(r.provider_id);
  const env = environmentColor(r.environment);
  const provName = opts.prov.find((p) => p.value === r.provider_id)?.label ?? r.provider_id ?? "—";
  const bodyId = `rv-body-${r.id}`;
  const blocked = r.missing_fields.length > 0 && !r.user_confirmed;
  return (
    <article className={`rv-card rv-${r.review_status} ${open ? "is-open" : ""}`} style={{ "--prov": prov.css } as CSSProperties}>
      <header className="rv-head">
        <button type="button" className="rv-toggle" aria-expanded={open} aria-controls={bodyId} onClick={onToggle} aria-label={r.name}>
          <Icon name={open ? "chevron-down" : "chevron-forward"} className="rv-chevron" />
        </button>
        <span className="rv-avatar" aria-hidden>
          <ServiceIcon type={r.service_type} />
        </span>
        <div className="rv-title">
          <EditCell r={r} field="name" kind="text" patch={patch} label={lbl("name")} wide />
          <span className="rv-meta">
            <span className="rv-env">
              <span className="swatch" style={{ background: env.css }} aria-hidden />
              {r.environment ? (ENV_KEY[r.environment] ? t(ENV_KEY[r.environment]) : r.environment) : "—"}
            </span>
            {!open && <Summary r={r} provName={provName} />}
          </span>
        </div>
        <div className="rv-controls">
        <span className="rv-qty" title={lbl("quantity")}>
          <span aria-hidden>×</span>
          <EditCell r={r} field="quantity" kind="dec" patch={patch} label={lbl("quantity")} />
        </span>
        <ConfidenceRing c={r.extraction_confidence} />
        <ReviewBadge s={r.review_status} />
        <label className={`switch ${blocked ? "is-disabled" : ""}`} title={blocked ? t("analyzeDisabled") : undefined}>
          <input
            type="checkbox"
            role="switch"
            aria-label={`${t("colConfirm")}: ${r.name}`}
            checked={r.user_confirmed}
            disabled={blocked}
            onChange={(e) => patch(r.id, { user_confirmed: e.target.checked })}
          />
          <span className="switch-track" aria-hidden>
            <span className="switch-thumb" />
          </span>
          <span className="switch-text">{t("rvConfirmSwitch")}</span>
        </label>
        </div>
      </header>

      {open && (
        <div className="rv-body" id={bodyId}>
          <MissingCell r={r} patch={patch} />
          <div className="rv-groups">
            <fieldset className="rv-group">
              <legend>{t("rvGroupPlacement")}</legend>
              <Field label={lbl("provider_id")}>
                <EditCell r={r} field="provider_id" kind="select" options={opts.prov} patch={patch} label={lbl("provider_id")} />
              </Field>
              <Field label={lbl("environment")}>
                <EditCell r={r} field="environment" kind="select" options={opts.env} patch={patch} label={lbl("environment")} />
              </Field>
            </fieldset>
            <fieldset className="rv-group">
              <legend>{t("rvGroupService")}</legend>
              <Field label={lbl("service_type")}>
                <EditCell r={r} field="service_type" kind="select" options={opts.svc} patch={patch} label={lbl("service_type")} />
              </Field>
              <Field label={lbl("sku")}>
                <EditCell r={r} field="sku" kind="text" patch={patch} label={lbl("sku")} wide />
              </Field>
            </fieldset>
            <fieldset className="rv-group">
              <legend>{t("rvGroupSize")}</legend>
              <div className="rv-pair">
                <Field label="CPU" unit={t("rvCores")}>
                  <EditCell r={r} field="cpu_cores" kind="dec" patch={patch} label={lbl("cpu_cores")} wide />
                </Field>
                <Field label="RAM" unit="GB">
                  <EditCell r={r} field="ram_gb" kind="dec" patch={patch} label={lbl("ram_gb")} wide />
                </Field>
              </div>
              <div className="rv-pair">
                <Field label={t("colDisk").replace(" (GB)", "")} unit="GB">
                  <EditCell r={r} field="storage_gb" kind="dec" patch={patch} label={lbl("storage_gb")} wide />
                </Field>
                <Field label={lbl("storage_type")}>
                  <EditCell r={r} field="storage_type" kind="text" patch={patch} label={lbl("storage_type")} wide />
                </Field>
              </div>
            </fieldset>
            <fieldset className="rv-group">
              <legend>{t("rvGroupUsage")}</legend>
              <div className="rv-pair">
                <Field label={`↓ ${t("rvDownload")}`} unit={t("rvPerMonth")}>
                  <EditCell r={r} field="expected_monthly_download_gb" kind="dec" patch={patch} label={lbl("expected_monthly_download_gb")} wide />
                </Field>
                <Field label={`↑ ${t("rvUpload")}`} unit={t("rvPerMonth")}>
                  <EditCell r={r} field="expected_monthly_upload_gb" kind="dec" patch={patch} label={lbl("expected_monthly_upload_gb")} wide />
                </Field>
              </div>
              <div className="rv-pair">
                <Field label={lbl("billing_mode")}>
                  <EditCell r={r} field="billing_mode" kind="select" options={opts.bill} patch={patch} label={lbl("billing_mode")} />
                </Field>
                <Field label={lbl("active_hours_per_month")} unit={t("rvHoursMonth")}>
                  <EditCell r={r} field="active_hours_per_month" kind="dec" patch={patch} label={lbl("active_hours_per_month")} wide />
                </Field>
              </div>
              <BoolSeg r={r} field="requires_public_ipv4" label={lbl("requires_public_ipv4")} patch={patch} />
            </fieldset>
          </div>
          <div className="rv-foot">
            <button type="button" className="linkish" aria-expanded={more} onClick={() => setMore(!more)}>
              <Icon name={more ? "chevron-down" : "chevron-forward"} small /> {t("moreFields")}
            </button>
            <Button variant="ghost" className="rv-delete" busy={deleting} onClick={onDelete}>
              {t("deleteResource")}
            </Button>
          </div>
          {more && (
            <div className="form-grid rv-more">
              {(
                [
                  ["resource_class", "text"],
                  ["region", "text"],
                  ["datacenter", "text"],
                  ["cpu_shared", "bool"],
                  ["ipv4_count", "dec"],
                  ["gpu_model", "text"],
                  ["gpu_count", "dec"],
                  ["external_ref", "text"],
                  ["notes", "text"],
                ] as [keyof ResourceView & string, Kind][]
              ).map(([f, k]) => (
                <Field key={f} label={lbl(f)}>
                  <EditCell r={r} field={f} kind={k} patch={patch} label={lbl(f)} wide />
                </Field>
              ))}
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export function ReviewTable({ inv }: { inv: InventoryView }) {
  const { t, lang } = useI18n();
  const nav = useNavigate();
  const providers = useProviders();
  const patchM = useInventoryMutation((a: { rid: string; body: Parameters<Patch>[1] }) => api.patchResource(inv.id, a.rid, a.body));
  const patch: Patch = (rid, body) => patchM.mutate({ rid, body });
  const addM = useInventoryMutation(() => api.addResource(inv.id, { name: `resource-${inv.resources.length + 1}` }));
  const delM = useInventoryMutation((rid: string) => api.deleteResource(inv.id, rid));
  const currencyM = useInventoryMutation((c: "TOMAN" | "RIAL") => api.setCurrency(inv.id, c));
  const confirmAllM = useInventoryMutation(() => api.confirm(inv.id, true));
  const confirmM = useInventoryMutation(() => api.confirm(inv.id, false), () => nav("/costs"));
  const [filter, setFilter] = useState<Filter>("all");
  // Rows that still need work start open; confirmed rows collapse into a one-line summary.
  const [openIds, setOpenIds] = useState<Set<string>>(() => new Set(inv.resources.filter((r) => !r.user_confirmed).map((r) => r.id)));

  const opts = {
    prov: (providers.data ?? []).map((p) => ({ value: p.id, label: lang === "fa" ? p.name_fa || p.name_en : p.name_en })),
    env: ENVIRONMENTS.map((e) => ({ value: e, label: ENV_KEY[e] ? t(ENV_KEY[e]) : e })),
    svc: SERVICE_TYPES.map((s) => ({ value: s, label: s })),
    bill: [
      { value: "monthly", label: t("monthly") },
      { value: "hourly", label: t("hourly") },
    ],
  };
  const currencyPending = inv.currency === "UNCONFIRMED";
  const confirmed = inv.status === "confirmed";
  const canAnalyze = !currencyPending && (confirmed || inv.can_confirm);
  const questions = inv.source_meta.questions ?? [];
  const err = patchM.error || addM.error || delM.error || currencyM.error || confirmM.error || confirmAllM.error;

  const total = inv.resources.length;
  const nConfirmed = inv.resources.filter((r) => r.user_confirmed).length;
  const needsWork = (r: ResourceView) => !r.user_confirmed || r.review_status !== "confirmed";
  const nAttention = inv.resources.filter(needsWork).length;
  const shown = inv.resources.filter((r) => (filter === "all" ? true : filter === "attention" ? needsWork(r) : !needsWork(r)));
  const allOpen = shown.length > 0 && shown.every((r) => openIds.has(r.id));
  const d = (n: number) => localizeDigits(String(n), lang);
  const toggle = (id: string) =>
    setOpenIds((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  return (
    <div className="stack">
      {inv.source_meta.demo && (
        <div className="alert alert-info">
          <Badge>{t("demoNote")}</Badge> {inv.source_meta.note}
        </div>
      )}
      {questions.length > 0 && (
        <div className="alert alert-warn">
          <strong>{t("questions")}</strong>
          <ul>
            {questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </div>
      )}
      <InvoiceSummary inv={inv} />
      {currencyPending && (
        <div className="alert alert-bad" role="group" aria-labelledby="cur-q">
          <strong id="cur-q">{t("currencyRequired")}</strong>
          <div className="row gap">
            <Button variant="primary" busy={currencyM.isPending} onClick={() => currencyM.mutate("RIAL")}>
              {t("rial")} (ریال)
            </Button>
            <Button variant="primary" busy={currencyM.isPending} onClick={() => currencyM.mutate("TOMAN")}>
              {t("toman")} (تومان)
            </Button>
          </div>
        </div>
      )}
      {inv.source_meta.invoice_currency_confirmed && (
        <p className="small">
          {t("currencyConfirmed")}: <Badge tone="info">{inv.source_meta.invoice_currency_confirmed === "RIAL" ? t("rial") : t("toman")}</Badge>
        </p>
      )}

      <div className="rv-overview">
        <div className="rv-stat">
          <strong>{d(total)}</strong>
          <span>{t("rvResources")}</span>
        </div>
        <div className="rv-stat rv-stat-progress">
          <div className="row between">
            <span>
              <strong>{d(nConfirmed)}</strong> / {d(total)} {t("rvConfirmedOf")}
            </span>
            {patchM.isPending && <Loader label={t("loading")} />}
          </div>
          <div
            className="rv-progress"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={total}
            aria-valuenow={nConfirmed}
            aria-label={t("rvConfirmedOf")}
          >
            <span style={{ inlineSize: total ? `${(nConfirmed / total) * 100}%` : 0 }} />
          </div>
        </div>
        <div className={`rv-stat ${nAttention ? "rv-stat-warn" : "rv-stat-good"}`}>
          <strong>{d(nAttention)}</strong>
          <span>{t("rvAttention")}</span>
        </div>
      </div>

      <div className="rv-toolbar">
        <div className="seg" role="radiogroup" aria-label={t("colStatus")}>
          {(
            [
              ["all", t("rvFilterAll"), total],
              ["attention", t("rvFilterAttention"), nAttention],
              ["confirmed", t("rvFilterConfirmed"), total - nAttention],
            ] as [Filter, string, number][]
          ).map(([k, label, n]) => (
            <button key={k} type="button" role="radio" aria-checked={filter === k} className={filter === k ? "on" : undefined} onClick={() => setFilter(k)}>
              {label} <span className="seg-count">{d(n)}</span>
            </button>
          ))}
        </div>
        <span className="rv-legend small">
          <span className="legend legend-low">{t("lowConfidenceLegend")}</span>
          <span className="legend legend-missing">{t("missingLegend")}</span>
        </span>
        <button
          type="button"
          className="linkish"
          onClick={() => setOpenIds((s) => (allOpen ? new Set([...s].filter((id) => !shown.some((r) => r.id === id))) : new Set([...s, ...shown.map((r) => r.id)])))}
        >
          {allOpen ? t("collapseAll") : t("expandAll")}
        </button>
      </div>
      <ErrorBox error={err} />

      {total === 0 ? (
        <p className="muted">{t("noResources")}</p>
      ) : shown.length === 0 ? (
        <p className="muted">{t("rvNoMatch")}</p>
      ) : (
        <div className="rv-list">
          {shown.map((r) => (
            <ResourceCard
              key={r.id}
              r={r}
              open={openIds.has(r.id)}
              onToggle={() => toggle(r.id)}
              patch={patch}
              opts={opts}
              onDelete={() => delM.mutate(r.id)}
              deleting={delM.isPending && delM.variables === r.id}
            />
          ))}
        </div>
      )}

      <div className="rv-actionbar">
        <Button busy={addM.isPending} onClick={() => addM.mutate(undefined)}>
          + {t("addResource")}
        </Button>
        <Button busy={confirmAllM.isPending} onClick={() => confirmAllM.mutate(undefined)} disabled={currencyPending || confirmed}>
          {t("confirmAllComplete")}
        </Button>
        <span className="spacer" />
        <span id="analyze-why" className="small rv-actionbar-hint">
          {canAnalyze ? (
            confirmed && inv.confirmed_at ? (
              <>
                {t("confirmedAt")} <Date_ v={inv.confirmed_at} />
              </>
            ) : (
              t("rvReadyHint")
            )
          ) : (
            <>
              {t("analyzeDisabled")} ({d(inv.blocking.length)} {t("blockingRows")})
            </>
          )}
        </span>
        <Button
          variant="primary"
          disabled={!canAnalyze}
          busy={confirmM.isPending}
          aria-describedby="analyze-why"
          onClick={() => (confirmed ? nav("/costs") : confirmM.mutate(undefined))}
        >
          {t("analyzeCosts")} <Icon name="arrow-forward" />
        </Button>
      </div>
    </div>
  );
}
