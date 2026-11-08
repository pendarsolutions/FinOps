/**
 * Pendar's marks, drawn from the generated paths in the logo tokens' colours, so dark mode reverses them by itself.
 * Persian readers get the Persian wordmark; the Latin one is only for English screens (logo guideline).
 */
import { MARKS } from "../pendar/logo";
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

export function Wordmark({ label }: { label?: string }) {
  const { lang } = useI18n();
  return <MarkSvg mark={lang === "en" ? MARKS.wordmarkEn : MARKS.wordmarkFa} className="wordmark" label={label} />;
}

/** Pendar's wordmark, a thin rule and the product name. `large` uses 6px bricks instead of 4px. */
export function Lockup({ large }: { large?: boolean }) {
  const { lang } = useI18n();
  return (
    <span className={large ? "lockup lockup-lg" : "lockup"}>
      <Wordmark label={lang === "en" ? "Pendar" : "پندار"} />
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
