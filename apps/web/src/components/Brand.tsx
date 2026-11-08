/**
 * Pendar's marks, drawn from the generated paths in the logo tokens' colours, so dark mode reverses them by itself.
 * Persian readers get the Persian wordmark; the Latin one is only for English screens (logo guideline).
 */
import type { CSSProperties } from "react";
import { LAYING, MARKS } from "../pendar/logo";
import { useI18n } from "../lib/i18n";

/** The product's own name, set beside Pendar's wordmark (products guideline). */
export const PRODUCT_NAME = "FinOps agent";

type Mark = { viewBox: string; brick: string; glaze: readonly string[] };

function MarkSvg({ mark, className, label }: { mark: Mark; className: string; label?: string }) {
  return (
    <svg className={className} viewBox={mark.viewBox} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true} focusable="false">
      <path className="mark-brick" d={mark.brick} />
      {mark.glaze.map((d) => (
        <path key={d} className="mark-glaze" d={d} />
      ))}
    </svg>
  );
}

/**
 * The wordmark as Pendar's animated logo lays it: brick by brick in its writing direction, then the tiles of «پ»
 * glazing one by one (motion guideline). The timing is all in CSS, from the motion tokens.
 */
function LaidWordmark({ lang, label }: { lang: "fa" | "en"; label?: string }) {
  const plan = LAYING[lang];
  const bricks: readonly (readonly number[])[] = plan.bricks;
  return (
    <svg
      className="wordmark is-laying"
      viewBox={plan.viewBox}
      shapeRendering="crispEdges"
      style={{ "--n": bricks.length } as CSSProperties}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      {bricks.map(([x, y, w, h, tile], i) => (
        <rect key={i} x={x} y={y} width={w} height={h} className={tile < 0 ? "mark-brick" : "mark-glaze"} style={{ "--i": i, "--t": tile } as CSSProperties} />
      ))}
    </svg>
  );
}

/** Pendar's wordmark. `laid` lays it brick by brick when it first appears. */
export function Wordmark({ label, laid }: { label?: string; laid?: boolean }) {
  const { lang } = useI18n();
  if (laid) return <LaidWordmark lang={lang === "en" ? "en" : "fa"} label={label} />;
  return <MarkSvg mark={lang === "en" ? MARKS.wordmarkEn : MARKS.wordmarkFa} className="wordmark" label={label} />;
}

/**
 * Pendar's wordmark, a thin rule and the product name. `large` uses 6px bricks instead of 4px.
 * `laid` lays the wordmark when it first appears; the rule and the name follow once the last brick has settled.
 */
export function Lockup({ large, laid }: { large?: boolean; laid?: boolean }) {
  const { lang } = useI18n();
  const bricks = LAYING[lang === "en" ? "en" : "fa"].bricks.length;
  return (
    <span className={`lockup${large ? " lockup-lg" : ""}${laid ? " is-laying" : ""}`} style={laid ? ({ "--n": bricks } as CSSProperties) : undefined}>
      <Wordmark label={lang === "en" ? "Pendar" : "پندار"} laid={laid} />
      <span className="lockup-rule" aria-hidden />
      <span className="lockup-name">{PRODUCT_NAME}</span>
    </span>
  );
}

/** Pendar's wall, its three tiles glazing one by one, for waits of unknown length. */
export function Loader({ large, label }: { large?: boolean; label?: string }) {
  return <MarkSvg mark={MARKS.symbol} className={large ? "loader loader-lg" : "loader"} label={label} />;
}

/** «قدرت‌گرفته از پندار» at the foot of the product's pages (voice guideline). */
export function PoweredBy() {
  const { t } = useI18n();
  return <p className="powered">{t("poweredBy")}</p>;
}
