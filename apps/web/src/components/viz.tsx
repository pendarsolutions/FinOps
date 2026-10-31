/**
 * Chart primitives (plain HTML/CSS, no chart library).
 *
 * Rules (dataviz method): thin bars (<=14px here) with a 4px rounded data-end and square baseline, 2px surface gaps
 * between touching segments, text in ink tokens (never the series color), a legend for >=2 series, a hover/focus
 * tooltip on every mark, and every value also printed in a visible list so nothing is gated behind hover.
 *
 * Bar geometry uses visualShare() — presentation only. Every amount shown is the exact decimal string from the API.
 */
import { createContext, useCallback, useContext, useState, type CSSProperties, type ReactNode } from "react";
import { useI18n } from "../lib/i18n";
import { formatToman, visualShare, type Decimalish } from "../lib/money";
import { Money } from "./ui";

// ------------------------------------------------------------------ tooltip

type Tip = { x: number; y: number; value: string; label: string; swatch?: string } | null;
const TipCtx = createContext<(t: Tip) => void>(() => {});

export function TooltipLayer({ children }: { children: ReactNode }) {
  const [tip, setTip] = useState<Tip>(null);
  return (
    <TipCtx.Provider value={setTip}>
      {children}
      {tip && (
        <div className="viz-tip" role="tooltip" style={{ left: 0, top: 0, transform: `translate(${tip.x}px, ${tip.y}px)` }}>
          <strong className="viz-tip-value">{tip.value}</strong>
          <span className="viz-tip-label">
            {tip.swatch ? <i className="viz-key-line" style={{ background: tip.swatch }} aria-hidden /> : null}
            {tip.label}
          </span>
        </div>
      )}
    </TipCtx.Provider>
  );
}

/** Pointer + keyboard handlers that show the shared tooltip for one mark. */
function useMarkTip(value: string, label: string, swatch?: string) {
  const setTip = useContext(TipCtx);
  const place = useCallback(
    (x: number, y: number) => setTip({ x: Math.min(x + 14, window.innerWidth - 240), y: y + 14, value, label, swatch }),
    [setTip, value, label, swatch],
  );
  return {
    onPointerMove: (e: React.PointerEvent) => place(e.clientX, e.clientY),
    onPointerLeave: () => setTip(null),
    onFocus: (e: React.FocusEvent) => {
      const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
      place(r.left + r.width / 2, r.bottom);
    },
    onBlur: () => setTip(null),
  };
}

// ------------------------------------------------------------------ part-to-whole

export type ShareItem = { key: string; label: string; value: Decimalish; color: string; sub?: ReactNode };

function Segment({ item, total, active, onHover }: { item: ShareItem; total: Decimalish; active: string | null; onHover: (k: string | null) => void }) {
  const { lang } = useI18n();
  const handlers = useMarkTip(formatToman(item.value, lang) ?? "—", item.label, item.color);
  const share = visualShare(item.value, total);
  if (share <= 0) return null;
  return (
    <span
      className={`share-seg ${active && active !== item.key ? "dim" : ""}`}
      style={{ flexGrow: share, background: item.color } as CSSProperties}
      tabIndex={0}
      aria-label={`${item.label}: ${formatToman(item.value, lang)}`}
      {...handlers}
      onPointerEnter={() => onHover(item.key)}
      onPointerLeave={() => {
        handlers.onPointerLeave();
        onHover(null);
      }}
    />
  );
}

/** Stacked horizontal share bar + legend list (the legend lists every exact value, so it is also the table view). */
export function ShareBar({ items, total, caption }: { items: ShareItem[]; total: Decimalish; caption: string }) {
  const [active, setActive] = useState<string | null>(null);
  const sorted = [...items].sort((a, b) => visualShare(b.value, total) - visualShare(a.value, total));
  return (
    <figure className="share">
      <div className="share-bar" role="img" aria-label={caption}>
        {sorted.map((it) => (
          <Segment key={it.key} item={it} total={total} active={active} onHover={setActive} />
        ))}
      </div>
      <ul className="legend-list">
        {sorted.map((it) => (
          <li
            key={it.key}
            className={active && active !== it.key ? "dim" : undefined}
            onPointerEnter={() => setActive(it.key)}
            onPointerLeave={() => setActive(null)}
          >
            <i className="swatch" style={{ background: it.color }} aria-hidden />
            <span className="legend-label">
              {it.label}
              {it.sub ? <small className="muted"> {it.sub}</small> : null}
            </span>
            <span className="legend-value">
              <Money v={it.value} />
            </span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

// ------------------------------------------------------------------ ranked bars

export type BarRow = { key: string; label: ReactNode; tipLabel: string; sub?: ReactNode; value: Decimalish; color?: string; emphasis?: boolean; trailing?: ReactNode };

function Bar({ row, max, emphasisMode }: { row: BarRow; max: Decimalish; emphasisMode: boolean }) {
  const { lang } = useI18n();
  const color = emphasisMode ? (row.emphasis ? "var(--viz-accent)" : "var(--viz-deemph)") : row.color ?? "var(--viz-accent)";
  const handlers = useMarkTip(formatToman(row.value, lang) ?? "PRICE_UNAVAILABLE", row.tipLabel, color);
  const share = visualShare(row.value, max);
  return (
    <div className={`rank-row ${row.emphasis ? "is-emph" : ""}`}>
      <div className="rank-label">
        <span className="rank-name">{row.label}</span>
        {row.sub ? <small className="muted">{row.sub}</small> : null}
      </div>
      <div className="rank-track" tabIndex={0} aria-label={`${row.tipLabel}: ${formatToman(row.value, lang) ?? "PRICE_UNAVAILABLE"}`} {...handlers}>
        {row.value === null || row.value === undefined ? (
          <span className="rank-missing">PRICE_UNAVAILABLE</span>
        ) : (
          <span className="rank-bar" style={{ inlineSize: `max(${share * 100}%, 3px)`, background: color }} />
        )}
      </div>
      <div className="rank-value">
        <Money v={row.value} />
        {row.trailing}
      </div>
    </div>
  );
}

/**
 * Horizontal ranked bars, one baseline. Pass `emphasis` on rows to switch to emphasis mode
 * (highlighted rows in the accent, the rest de-emphasized gray) — the honest form for "this one matters".
 */
export function RankedBars({ rows, caption, max }: { rows: BarRow[]; caption: string; max?: Decimalish }) {
  const ref = max ?? rows.reduce<Decimalish>((m, r) => (m === null || m === undefined || visualShare(r.value, m) >= 1 ? r.value ?? m : m), null);
  const emphasisMode = rows.some((r) => r.emphasis);
  return (
    <figure className="rank" aria-label={caption}>
      {rows.map((r) => (
        <Bar key={r.key} row={r} max={ref} emphasisMode={emphasisMode} />
      ))}
    </figure>
  );
}

// ------------------------------------------------------------------ before -> after meter

/**
 * Current cost as the full track (light step of the ramp), the cost after the change as the fill. The unfilled
 * remainder is the saving. All three amounts are printed exactly beside the meter.
 */
export function BeforeAfter({ current, after, saving }: { current: Decimalish; after: Decimalish; saving: Decimalish }) {
  const { t, lang } = useI18n();
  const afterTip = useMarkTip(formatToman(after, lang) ?? "—", t("afterChange"), "var(--viz-accent)");
  const share = visualShare(after, current);
  if (current === null || current === undefined || after === null || after === undefined) return null;
  return (
    <div className="meter-ba">
      <div className="meter-track" aria-hidden={false} role="img" aria-label={`${t("currentCost")} ${formatToman(current, lang)} → ${t("afterChange")} ${formatToman(after, lang)}`}>
        <span className="meter-fill" style={{ inlineSize: `${Math.max(share * 100, 1)}%` }} tabIndex={0} {...afterTip} />
        <span className="meter-gap-label">
          −<Money v={saving} />
        </span>
      </div>
      <div className="meter-legend small">
        <span>
          <i className="swatch swatch-track" aria-hidden /> {t("currentCost")} <Money v={current} />
        </span>
        <span>
          <i className="swatch" style={{ background: "var(--viz-accent)" }} aria-hidden /> {t("afterChange")} <Money v={after} />
        </span>
      </div>
    </div>
  );
}

/** Single-value meter (e.g. avoidable share of current spend). Fill = part, track = whole (same hue, lighter step). */
export function PartMeter({ part, whole, label }: { part: Decimalish; whole: Decimalish; label: string }) {
  const share = visualShare(part, whole);
  return (
    <div className="meter-part" role="img" aria-label={label}>
      <span style={{ inlineSize: `${Math.max(share * 100, part ? 1 : 0)}%` }} />
    </div>
  );
}
