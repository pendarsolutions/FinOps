/** Display-only digit formatting, as in the app (apps/web/src/lib/money.ts): no arithmetic on amounts. */
import type { Lang } from "./lang";

const FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

export function localizeDigits(s: string, lang: Lang): string {
  return lang === "fa" ? s.replace(/[0-9]/g, (d) => FA_DIGITS[Number(d)]) : s;
}

/** Group a whole number's digits in threes: ٢٠٬٥٧٤٬٤٣٩ in Persian, 20,574,439 in English. */
export function formatWhole(digits: string, lang: Lang): string {
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, lang === "fa" ? "٬" : ",");
  return localizeDigits(grouped, lang);
}
