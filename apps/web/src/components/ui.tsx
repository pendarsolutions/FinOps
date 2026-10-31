import { useEffect, useId, useRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { ApiError } from "../api/client";
import type { BlockingRow, ComponentLine, PriceSource } from "../api/types";
import { useI18n, type TKey } from "../lib/i18n";
import { formatDate, formatDecimal, formatPercent, formatToman, localizeDigits, type Decimalish } from "../lib/money";

// ------------------------------------------------------------------ basics

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; busy?: boolean };

export function Button({ variant = "secondary", busy, className, children, disabled, ...rest }: BtnProps) {
  return (
    <button
      type="button"
      className={`btn btn-${variant} ${className ?? ""}`}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? <span className="spinner" aria-hidden /> : null}
      {children}
    </button>
  );
}

export type Tone = "neutral" | "good" | "warn" | "bad" | "info";

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

const TONE_ICON: Record<Tone, string> = { good: "✓", warn: "!", bad: "✕", info: "i", neutral: "•" };

/** Status = icon + label + tone. Never color alone. */
export function StatusChip({ tone, label, title }: { tone: Tone; label: ReactNode; title?: string }) {
  return (
    <span className={`status-chip status-chip-${tone}`} title={title}>
      <span className="status-chip-icon" aria-hidden>
        {TONE_ICON[tone]}
      </span>
      {label}
    </span>
  );
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className ?? ""}`}>
      {(title || actions) && (
        <header className="card-head">
          {title ? <h2>{title}</h2> : <span />}
          {actions ? <div className="row gap">{actions}</div> : null}
        </header>
      )}
      {children}
    </section>
  );
}

export function Loading() {
  const { t } = useI18n();
  return (
    <p className="muted" role="status">
      <span className="spinner" aria-hidden /> {t("loading")}
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Field({ label, children, hint, htmlFor }: { label: ReactNode; children: ReactNode; hint?: ReactNode; htmlFor?: string }) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint ? <small className="muted">{hint}</small> : null}
    </div>
  );
}

export function Tabs<K extends string>({ tabs, value, onChange }: { tabs: { key: K; label: string }[]; value: K; onChange: (k: K) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tb) => (
        <button
          key={tb.key}
          role="tab"
          type="button"
          aria-selected={tb.key === value}
          className={tb.key === value ? "tab active" : "tab"}
          onClick={() => onChange(tb.key)}
        >
          {tb.label}
        </button>
      ))}
    </div>
  );
}

export function Drawer({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; wide?: boolean }) {
  const { t } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      prev?.focus?.();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div
        className={`drawer ${wide ? "drawer-wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        ref={ref}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="drawer-head">
          <h2 id={titleId}>{title}</h2>
          <Button variant="ghost" onClick={onClose} aria-label={t("close")}>
            ✕
          </Button>
        </header>
        <div className="drawer-body">{children}</div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ numbers / money

export function Num({ v, max }: { v: Decimalish; max?: number }) {
  const { lang } = useI18n();
  return <span className="num">{v === null || v === undefined ? "—" : formatDecimal(v, lang, { maxFraction: max })}</span>;
}

export function Pct({ v }: { v: Decimalish }) {
  const { lang } = useI18n();
  return <span className="num">{formatPercent(v, lang)}</span>;
}

export function PriceUnavailableBadge() {
  const { t } = useI18n();
  return (
    <span className="price-unavailable" title="PRICE_UNAVAILABLE">
      ⚠ {t("priceUnavailable")} <code>PRICE_UNAVAILABLE</code>
    </span>
  );
}

/** Exact Toman display. `null` is PRICE_UNAVAILABLE, never zero. */
export function Money({ v, big, suffix }: { v: Decimalish; big?: boolean; suffix?: ReactNode }) {
  const { lang } = useI18n();
  const s = formatToman(v, lang);
  if (s === null) return <PriceUnavailableBadge />;
  return (
    <span className={big ? "money money-big" : "money"}>
      {s}
      {suffix ? <span className="muted"> {suffix}</span> : null}
    </span>
  );
}

export function Date_({ v }: { v: string | null | undefined }) {
  const { lang } = useI18n();
  return <span className="num">{formatDate(v, lang)}</span>;
}

export function Digits({ children }: { children: string }) {
  const { lang } = useI18n();
  return <>{localizeDigits(children, lang)}</>;
}

// ------------------------------------------------------------------ price source / freshness

export function FreshnessBadge({ f }: { f: string | null | undefined }) {
  const { t } = useI18n();
  const tone: Tone = f === "fresh" ? "good" : f === "aging" ? "warn" : f === "stale" ? "bad" : "neutral";
  const key = (["fresh", "aging", "stale"].includes(f ?? "") ? f : "unknown") as TKey;
  return <StatusChip tone={tone} label={t(key)} />;
}

/** Compact expandable source/freshness metadata attached to every displayed price. */
export function SourceInfo({
  url,
  retrieved,
  priceDate,
  freshness,
  compact,
}: {
  url: string | null | undefined;
  retrieved: string | null | undefined;
  priceDate?: string | null;
  freshness?: string | null;
  compact?: boolean;
}) {
  const { t } = useI18n();
  if (!url && !retrieved) return compact ? null : <span className="muted">—</span>;
  const tip = [url, `${t("retrieved")}: ${retrieved ?? "—"}`, `${t("providerPriceDate")}: ${priceDate ?? "—"}`].join("\n");
  return (
    <details className="source-info">
      <summary title={tip}>
        ⓘ {t("source")}
        {freshness ? <FreshnessBadge f={freshness} /> : null}
      </summary>
      <dl className="kv">
        <dt>{t("source")}</dt>
        <dd>
          {url ? (
            <a href={url} target="_blank" rel="noreferrer noopener" dir="ltr">
              {url}
            </a>
          ) : (
            "—"
          )}
        </dd>
        <dt>{t("retrieved")}</dt>
        <dd>
          <Date_ v={retrieved} />
        </dd>
        <dt>{t("providerPriceDate")}</dt>
        <dd>
          <Date_ v={priceDate} />
        </dd>
        {freshness ? (
          <>
            <dt>{t("freshness")}</dt>
            <dd>
              <FreshnessBadge f={freshness} />
            </dd>
          </>
        ) : null}
      </dl>
    </details>
  );
}

export function freshnessFor(sources: PriceSource[] | undefined, url: string | null | undefined) {
  return sources?.find((s) => s.source_url === url)?.freshness ?? null;
}

const LINE_TONE: Record<string, Tone> = { priced: "good", included: "info", assumed_included: "warn", unavailable: "bad", info: "neutral" };

export function LineStatusBadge({ s }: { s: string }) {
  const { t } = useI18n();
  const key = (["priced", "included", "assumed_included", "unavailable", "info"].includes(s) ? s : "unknown") as TKey;
  return <StatusChip tone={LINE_TONE[s] ?? "neutral"} label={t(key)} />;
}

/** Component lines of a price breakdown (priced / included / assumed_included / unavailable / info). */
export function LinesTable({ lines, sources }: { lines: ComponentLine[] | undefined; sources?: PriceSource[] }) {
  const { t } = useI18n();
  if (!lines?.length) return null;
  return (
    <div className="table-wrap">
      <table className="table compact lines">
        <thead>
          <tr>
            <th>{t("component")}</th>
            <th>{t("lineStatus")}</th>
            <th className="num-col">{t("quantity")}</th>
            <th className="num-col">{t("unitPrice")}</th>
            <th className="num-col">{t("subtotal")}</th>
            <th>{t("source")}</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={`${l.code}-${i}`}>
              <td>
                <div>{l.description}</div>
                <small className="muted" dir="ltr">
                  {l.code}
                </small>
                {l.note ? <div className="note">{l.note}</div> : null}
              </td>
              <td>
                <LineStatusBadge s={l.status} />
              </td>
              <td className="num-col">
                <Num v={l.quantity} /> <small className="muted">{l.unit}</small>
              </td>
              <td className="num-col">{l.unit_price_toman !== null ? <Money v={l.unit_price_toman} /> : <span className="muted">—</span>}</td>
              <td className="num-col">
                {l.status === "unavailable" ? (
                  <PriceUnavailableBadge />
                ) : l.subtotal_toman !== null ? (
                  <Money v={l.subtotal_toman} />
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td>
                <SourceInfo url={l.source_url} retrieved={l.retrieved_at} priceDate={l.price_date} freshness={freshnessFor(sources, l.source_url)} compact />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ------------------------------------------------------------------ errors

function BlockingList({ rows }: { rows: BlockingRow[] }) {
  const { t, fieldLabel } = useI18n();
  return (
    <ul className="blocking">
      {rows.map((b) => (
        <li key={b.resource_id}>
          <strong>{b.name || b.resource_id.slice(0, 8)}</strong> — <ReviewBadge s={b.review_status} />
          {b.missing_fields.length > 0 && (
            <span>
              {" "}
              {t("missing")}: {b.missing_fields.map(fieldLabel).join("، ")}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

export function ReviewBadge({ s }: { s: string }) {
  const { t } = useI18n();
  if (s === "confirmed") return <StatusChip tone="good" label={t("stConfirmed")} />;
  if (s === "needs_review") return <StatusChip tone="warn" label={t("stNeedsReview")} />;
  return <StatusChip tone="bad" label={t("stUnresolved")} />;
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useI18n();
  if (!error) return null;
  let title = t("errGeneric");
  let body: ReactNode = error instanceof Error ? error.message : String(error);
  if (error instanceof ApiError) {
    const d = error.detail as unknown;
    if (error.status === 0) body = t("errNetwork");
    else if (error.status === 403) {
      title = t("errForbidden");
      body = typeof d === "string" ? d : null;
    } else if (error.status === 409) {
      title = t("errConflict");
      if (d && typeof d === "object" && "blocking" in d) {
        const o = d as { message?: string; blocking: BlockingRow[] };
        body = (
          <>
            <p>{o.message}</p>
            <p>
              <strong>{t("blockingRows")}:</strong>
            </p>
            <BlockingList rows={o.blocking} />
          </>
        );
      } else body = typeof d === "string" ? d : JSON.stringify(d);
    } else if (error.status === 422) {
      title = t("errValidation");
      if (Array.isArray(d))
        body = (
          <ul>
            {d.map((e: { loc?: unknown[]; msg?: string }, i: number) => (
              <li key={i}>
                <code dir="ltr">{(e.loc ?? []).filter((x) => x !== "body").join(".")}</code> {e.msg}
              </li>
            ))}
          </ul>
        );
      else body = typeof d === "string" ? d : JSON.stringify(d);
    } else if (error.status === 429) {
      body = t("errRate");
    } else {
      body = typeof d === "string" ? d : JSON.stringify(d);
    }
    title = `${title} (${error.status || "network"})`;
  }
  return (
    <div className="alert alert-bad" role="alert">
      <strong>{title}</strong>
      {body ? <div>{body}</div> : null}
      {onRetry ? (
        <Button variant="ghost" onClick={onRetry}>
          {t("retry")}
        </Button>
      ) : null}
    </div>
  );
}

export function ToneBadge({ value, kind }: { value: string | null | undefined; kind: "risk" | "effort" | "confidence" }) {
  const v = (value ?? "").toLowerCase();
  let tone: Tone = "neutral";
  if (kind === "confidence") tone = v === "high" ? "good" : v === "medium" ? "info" : v === "needs_human_review" ? "warn" : "neutral";
  else tone = v === "low" || v === "none" ? "good" : v === "medium" ? "warn" : v === "high" ? "bad" : "neutral";
  return <StatusChip tone={tone} label={value ?? "—"} />;
}
