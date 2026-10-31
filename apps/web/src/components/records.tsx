/**
 * Record rows: the card-per-item look used by the inventory review, shared by every "one row per thing" list
 * (sync runs, adapters, saved quotes, audit log, builder cart, invoice lines). Dense numeric tables stay tables.
 */
import type { CSSProperties, ReactNode } from "react";
import { useI18n } from "../lib/i18n";
import { localizeDigits } from "../lib/money";
import type { Tone } from "./ui";

/** Small glyph per service type, so items are recognisable at a glance. */
export function ServiceIcon({ type }: { type: string | null | undefined }) {
  const p = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden>
      {type === "dbaas" ? (
        <g {...p}>
          <ellipse cx="12" cy="5.5" rx="7" ry="2.5" />
          <path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5" />
        </g>
      ) : type === "object_storage" ? (
        <g {...p}>
          <path d="M4 7h16l-1.6 12.2a2 2 0 0 1-2 1.8H7.6a2 2 0 0 1-2-1.8z" />
          <path d="M3 7c0-1.7 4-3 9-3s9 1.3 9 3" />
        </g>
      ) : type === "paas" ? (
        <g {...p}>
          <path d="M7 18a4.5 4.5 0 0 1-.6-9 6 6 0 0 1 11.5 1.5A3.8 3.8 0 0 1 17.5 18z" />
        </g>
      ) : (
        <g {...p}>
          <rect x="3.5" y="4" width="17" height="7" rx="1.6" />
          <rect x="3.5" y="13" width="17" height="7" rx="1.6" />
          <path d="M7 7.5h.01M7 16.5h.01M11 7.5h5M11 16.5h5" />
        </g>
      )}
    </svg>
  );
}

export function ConfidenceRing({ c }: { c: number }) {
  const { t, lang } = useI18n();
  const pct = Math.round(c * 100);
  const tone = c >= 0.8 ? "good" : c >= 0.5 ? "warn" : "bad";
  const txt = lang === "fa" ? localizeDigits(`${pct}`, lang) + "٪" : `${pct}%`;
  return (
    <span className={`conf-ring conf-${tone}`} style={{ "--p": pct } as CSSProperties} title={`${t("colConfidence")}: ${txt}`}>
      <span>{txt}</span>
    </span>
  );
}

/** First letter of a name in a tinted square — the avatar for providers and other named things. */
export function Initial({ name }: { name: string }) {
  return <span className="rec-initial">{(name.trim()[0] ?? "?").toUpperCase()}</span>;
}

/** Labelled figure inside a record (e.g. "seen 120"). */
export function RecStat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="rec-stat">
      <small>{label}</small>
      <strong>{children}</strong>
    </span>
  );
}

/** `compact` shrinks rows; `dense` also puts title and meta on one line (long logs). */
export function RecList({ children, label, compact, dense, grid }: { children: ReactNode; label?: string; compact?: boolean; dense?: boolean; grid?: boolean }) {
  const cls = ["rec-list", compact || dense ? "rec-list-compact" : "", dense ? "rec-list-dense" : "", grid ? "rec-grid" : ""].filter(Boolean).join(" ");
  return (
    <ul className={cls} aria-label={label}>
      {children}
    </ul>
  );
}

/**
 * One record. `accent` colours the edge stripe and avatar (a provider's chart colour); `tone` marks a problem row.
 * `aside` holds status/actions at the end of the row; `children` render under the head.
 */
export function Rec({
  accent,
  tone,
  icon,
  title,
  meta,
  aside,
  children,
  selected,
}: {
  accent?: string;
  tone?: Tone;
  icon?: ReactNode;
  title: ReactNode;
  meta?: ReactNode;
  aside?: ReactNode;
  children?: ReactNode;
  selected?: boolean;
}) {
  const cls = ["rec", tone && tone !== "neutral" ? `rec-${tone}` : "", selected ? "is-selected" : ""].filter(Boolean).join(" ");
  return (
    <li className={cls} style={accent ? ({ "--prov": accent } as CSSProperties) : undefined} aria-current={selected || undefined}>
      <div className="rec-head">
        {icon && (
          <span className="rec-avatar" aria-hidden>
            {icon}
          </span>
        )}
        <div className="rec-main">
          <div className="rec-title">{title}</div>
          {meta && <div className="rec-meta">{meta}</div>}
        </div>
        {aside && <div className="rec-aside">{aside}</div>}
      </div>
      {children && <div className="rec-body">{children}</div>}
    </li>
  );
}
