/** Pendar's marks, as in the app (apps/web/src/components/Brand.tsx): the Persian wordmark for Persian readers. */
import type { CSSProperties } from "react";
import { LAYING, MARKS } from "@pendar/logo";
import { useT } from "./strings";

export const PRODUCT_NAME = "FinOps agent";

/** The wordmark as Pendar's animated logo lays it: brick by brick, then the tiles of «پ» glaze one by one. */
function LaidWordmark({ lang, label }: { lang: "fa" | "en"; label?: string }) {
  const bricks: readonly (readonly number[])[] = LAYING[lang].bricks;
  return (
    <svg
      className="wordmark is-laying"
      viewBox={LAYING[lang].viewBox}
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

function Wordmark({ label, laid }: { label?: string; laid?: boolean }) {
  const { lang } = useT();
  if (laid) return <LaidWordmark lang={lang} label={label} />;
  const mark = lang === "en" ? MARKS.wordmarkEn : MARKS.wordmarkFa;
  return (
    <svg className="wordmark" viewBox={mark.viewBox} role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true} focusable="false">
      <path className="mark-brick" d={mark.brick} />
      {mark.glaze.map((d) => (
        <path key={d} className="mark-glaze" d={d} />
      ))}
    </svg>
  );
}

/** Pendar's wordmark, a thin rule and the product name. `laid` lays the wordmark when it first appears. */
export function Lockup({ large, laid }: { large?: boolean; laid?: boolean }) {
  const { lang } = useT();
  return (
    <span className={`lockup${large ? " lockup-lg" : ""}${laid ? " is-laying" : ""}`} style={laid ? ({ "--n": LAYING[lang].bricks.length } as CSSProperties) : undefined}>
      <Wordmark label={lang === "en" ? "Pendar" : "پندار"} laid={laid} />
      <span className="lockup-rule" aria-hidden />
      <span className="lockup-name">{PRODUCT_NAME}</span>
    </span>
  );
}

export function PoweredBy() {
  const { t } = useT();
  return <p className="powered">{t("poweredBy")}</p>;
}
