/**
 * Display-only formatting of exact decimal strings.
 *
 * The backend sends money as exact decimal strings in Toman (e.g. "20574439"). The UI never converts
 * money through a JS Number and never does arithmetic on it: these helpers only re-group the digits
 * of the string and (in Persian) swap the digit glyphs.
 */
import type { Lang } from "./i18n";

export type Decimalish = string | number | null | undefined;

const FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const DECIMAL_RE = /^([+-]?)(\d*)(?:\.(\d*))?$/;

export function toPersianDigits(s: string): string {
  return s.replace(/[0-9]/g, (d) => FA_DIGITS[Number(d)]);
}

export function localizeDigits(s: string, lang: Lang): string {
  return lang === "fa" ? toPersianDigits(s) : s;
}

/** Normalize a decimal string: trims, drops trailing fractional zeros. Returns null when not a plain decimal. */
function parts(value: Decimalish): { sign: string; int: string; frac: string } | null {
  if (value === null || value === undefined || value === "") return null;
  // Numbers only ever reach here if the API sent a JSON number; stringify without arithmetic.
  const raw = typeof value === "number" ? String(value) : value.trim();
  // Python's Decimal writes a scaled zero as "0E-8".
  const s = /^[+-]?0*\.?0*E[+-]?\d+$/i.test(raw) ? "0" : raw;
  const m = DECIMAL_RE.exec(s);
  if (!m || (m[2] === "" && (m[3] ?? "") === "")) return null;
  const int = m[2].replace(/^0+(?=\d)/, "") || "0";
  const frac = (m[3] ?? "").replace(/0+$/, "");
  const sign = m[1] === "-" && (int !== "0" || frac !== "") ? "-" : "";
  return { sign, int, frac };
}

function group(int: string, sep: string): string {
  let out = "";
  for (let i = 0; i < int.length; i++) {
    const fromEnd = int.length - i;
    out += int[i];
    if (fromEnd > 1 && fromEnd % 3 === 1) out += sep;
  }
  return out;
}

/** Format a decimal string for display with thousand separators. Unknown input is returned unchanged. */
export function formatDecimal(value: Decimalish, lang: Lang, opts: { maxFraction?: number } = {}): string {
  const p = parts(value);
  if (!p) return value === null || value === undefined ? "—" : String(value);
  let frac = p.frac;
  if (opts.maxFraction !== undefined && frac.length > opts.maxFraction) {
    // Display truncation only (no rounding arithmetic) and only used for non-money ratios like fit scores.
    frac = frac.slice(0, opts.maxFraction).replace(/0+$/, "");
  }
  if (lang === "fa") {
    const s = p.sign + group(p.int, "٬") + (frac ? "٫" + frac : "");
    return toPersianDigits(s);
  }
  return p.sign + group(p.int, ",") + (frac ? "." + frac : "");
}

export function formatPercent(value: Decimalish, lang: Lang): string {
  if (value === null || value === undefined) return "—";
  return lang === "fa" ? formatDecimal(value, lang) + "٪" : formatDecimal(value, lang) + "%";
}

export function currencyLabel(lang: Lang): string {
  return lang === "fa" ? "تومان" : "Toman";
}

/** "20,574,439 Toman" / "۲۰٬۵۷۴٬۴۳۹ تومان"; null stays null so callers render PRICE_UNAVAILABLE. */
export function formatToman(value: Decimalish, lang: Lang): string | null {
  if (value === null || value === undefined) return null;
  return `${formatDecimal(value, lang)} ${currencyLabel(lang)}`;
}

/**
 * Bar-length ratio for the distribution lists. Presentation-only: the result sets a CSS width and is
 * never displayed or used as an amount. Compares integer digit strings at a fixed precision.
 */
export function visualShare(value: Decimalish, max: Decimalish): number {
  const a = parts(value);
  const b = parts(max);
  if (!a || !b || b.int === "0" || a.sign) return 0;
  const lenDiff = b.int.length - a.int.length;
  if (lenDiff > 6) return 0;
  const head = (s: string) => parseInt(s.slice(0, 9).padEnd(9, "0"), 10);
  const ratio = head(a.int) / head(b.int) / Math.pow(10, lenDiff);
  return Math.max(0, Math.min(1, ratio));
}

/**
 * Exact ordering of two decimal strings (for sorting only — no arithmetic, no floats).
 * Missing / unparseable values sort after every number.
 */
export function compareDecimal(a: Decimalish, b: Decimalish): number {
  const x = parts(a);
  const y = parts(b);
  if (!x || !y) return x ? -1 : y ? 1 : 0;
  if (x.sign !== y.sign) return x.sign ? -1 : 1;
  const flip = x.sign ? -1 : 1;
  if (x.int.length !== y.int.length) return (x.int.length < y.int.length ? -1 : 1) * flip;
  if (x.int !== y.int) return (x.int < y.int ? -1 : 1) * flip;
  const n = Math.max(x.frac.length, y.frac.length);
  const fx = x.frac.padEnd(n, "0");
  const fy = y.frac.padEnd(n, "0");
  return fx === fy ? 0 : (fx < fy ? -1 : 1) * flip;
}

// ------------------------------------------------------------------ dates

const DAY_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const HAS_OFFSET = /(?:[zZ]|[+-]\d{2}:?\d{2})$/;
const formatters = new Map<string, Intl.DateTimeFormat>();

function formatter(lang: Lang, dayOnly: boolean, withTime: boolean): Intl.DateTimeFormat {
  const key = `${lang}${dayOnly}${withTime}`;
  let f = formatters.get(key);
  if (!f) {
    // Persian: Solar Hijri calendar with Persian digits (voice guideline); English: Gregorian with Latin digits
    f = new Intl.DateTimeFormat(lang === "fa" ? "fa-IR-u-ca-persian-nu-arabext" : "en-CA-u-ca-gregory-nu-latn", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      ...(withTime ? { hour: "2-digit", minute: "2-digit", hourCycle: "h23" } : {}),
      // a calendar day from the API is the same day everywhere; a moment is shown in the reader's own time
      ...(dayOnly ? { timeZone: "UTC" } : {}),
    });
    formatters.set(key, f);
  }
  return f;
}

/**
 * A date from the API for people to read: ۱۴۰۵/۰۸/۱۷ in Persian, 2026-11-08 in English. Moments (with a time) are
 * shown in the reader's time zone, with the time unless `dayOnly`. The API sends UTC; a time without an offset
 * (as SQLite stores it) is UTC too.
 */
export function formatDate(iso: string | null | undefined, lang: Lang, opts: { dayOnly?: boolean } = {}): string {
  if (!iso) return "—";
  const isDay = DAY_ONLY.test(iso);
  const at = new Date(isDay ? `${iso}T00:00:00Z` : HAS_OFFSET.test(iso) ? iso : `${iso}Z`);
  if (Number.isNaN(at.getTime())) return localizeDigits(iso, lang);
  const p: Partial<Record<Intl.DateTimeFormatPartTypes, string>> = {};
  for (const part of formatter(lang, isDay, !isDay && !opts.dayOnly).formatToParts(at)) p[part.type] = part.value;
  const sep = lang === "fa" ? "/" : "-";
  const day = `${p.year}${sep}${p.month}${sep}${p.day}`;
  return p.hour === undefined ? day : `${day} ${p.hour}:${p.minute}`;
}
