/**
 * Chart color roles. Categorical slots come from the validated reference palette (fixed order, never cycled;
 * validated on the #ffffff card surface: all hard gates pass, 3 slots < 3:1 so every chart prints visible
 * labels + exact values). Color follows the ENTITY, never its rank: a provider keeps its slot on every chart.
 */

export const SERIES_SLOTS = 8;

/** Provider -> slot, by the product's provider priority. Unknown providers fold into the neutral "other". */
const PROVIDER_ORDER = ["arvancloud", "liara", "serverir", "iranserver", "chabokan", "parspack", "mobinhost", "abrha"];
const ENV_ORDER = ["production", "staging", "dev", "test", "ci", "qa"];

export type SeriesColor = { slot: number | null; css: string };

function slotColor(slot: number | null): SeriesColor {
  return { slot, css: slot === null ? "var(--series-other)" : `var(--series-${slot})` };
}

export function providerColor(id: string | null | undefined): SeriesColor {
  const i = PROVIDER_ORDER.indexOf(id ?? "");
  return slotColor(i >= 0 ? i + 1 : null);
}

export function environmentColor(env: string | null | undefined): SeriesColor {
  const key = (env ?? "").toLowerCase();
  const i = ENV_ORDER.indexOf(key === "development" ? "dev" : key);
  return slotColor(i >= 0 ? i + 1 : null);
}

/** Respect the user's reduced-motion preference for chart entrance animations. */
export function prefersReducedMotion(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}
