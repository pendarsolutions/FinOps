/**
 * First-login product tour. A spotlight glides between [data-tour="…"] targets in the real UI and a popover
 * explains each part. Starts automatically once per user (localStorage), replayable from the topbar and Settings.
 */
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useI18n, type TKey } from "../lib/i18n";
import { formatDecimal } from "../lib/money";
import { Button } from "./ui";

type Step = { target: string | null; title: TKey; body: TKey };

const STEPS: Step[] = [
  { target: null, title: "tourWelcomeT", body: "tourWelcomeB" },
  { target: "inventory", title: "tourInvT", body: "tourInvB" },
  { target: "nav-overview", title: "tourOverviewT", body: "tourOverviewB" },
  { target: "nav-infrastructure", title: "tourInfraT", body: "tourInfraB" },
  { target: "nav-costs", title: "tourCostsT", body: "tourCostsB" },
  { target: "nav-opportunities", title: "tourOppsT", body: "tourOppsB" },
  { target: "nav-compare", title: "tourCompareT", body: "tourCompareB" },
  { target: "nav-reports", title: "tourReportsT", body: "tourReportsB" },
  { target: "nav-catalog", title: "tourCatalogT", body: "tourCatalogB" },
  { target: "nav-integrations", title: "tourIntegrationsT", body: "tourIntegrationsB" },
  { target: "nav-settings", title: "tourSettingsT", body: "tourSettingsB" },
  { target: "advisor", title: "tourAdvisorT", body: "tourAdvisorB" },
  { target: "lang", title: "tourLangT", body: "tourLangB" },
  { target: "help", title: "tourHelpT", body: "tourHelpB" },
];

const KEY = "finops.tour.v1.";

type TourApi = { start: () => void; maybeAutoStart: (userId: string) => void };
const Ctx = createContext<TourApi>({ start: () => {}, maybeAutoStart: () => {} });
export const useTour = () => useContext(Ctx);

type Rect = { top: number; left: number; width: number; height: number };

function measure(target: string | null): Rect | null {
  if (!target) return null;
  const el = document.querySelector<HTMLElement>(`[data-tour="${target}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width === 0 || r.height === 0) return null; // hidden (e.g. collapsed mobile nav) -> centered popover
  return { top: r.top, left: r.left, width: r.width, height: r.height };
}

export function TourProvider({ children, onNeedNav }: { children: ReactNode; onNeedNav?: (open: boolean) => void }) {
  const [i, setI] = useState<number | null>(null);
  const userRef = useRef<string | null>(null);

  const finish = useCallback(() => {
    setI(null);
    onNeedNav?.(false);
    try {
      if (userRef.current) localStorage.setItem(KEY + userRef.current, "done");
    } catch {
      /* storage unavailable: tour simply shows again next time */
    }
  }, [onNeedNav]);

  const api: TourApi = {
    start: () => setI(0),
    maybeAutoStart: (userId) => {
      userRef.current = userId;
      let done = false;
      try {
        done = localStorage.getItem(KEY + userId) === "done";
      } catch {
        done = false;
      }
      // Dev-only: ?tourStep=N opens the tour at step N (used for visual review screenshots).
      // Only when the parameter is there: Number(null) is 0, which used to open the tour on every dev page load.
      const devParam = import.meta.env.DEV ? new URLSearchParams(window.location.search).get("tourStep") : null;
      const devStep = devParam === null ? NaN : Number(devParam);
      if (Number.isInteger(devStep) && devStep >= 0 && devStep < STEPS.length) {
        window.setTimeout(() => setI(devStep), 700);
        return;
      }
      if (!done) window.setTimeout(() => setI((cur) => cur ?? 0), 700);
    },
  };

  return (
    <Ctx.Provider value={api}>
      {children}
      {i !== null && <TourOverlay index={i} setIndex={setI} onFinish={finish} onNeedNav={onNeedNav} />}
    </Ctx.Provider>
  );
}

function TourOverlay({ index, setIndex, onFinish, onNeedNav }: { index: number; setIndex: (n: number) => void; onFinish: () => void; onNeedNav?: (o: boolean) => void }) {
  const { t, lang } = useI18n();
  const step = STEPS[index];
  const [rect, setRect] = useState<Rect | null>(null);
  const pop = useRef<HTMLDivElement>(null);
  const [popPos, setPopPos] = useState<{ top: number; left: number } | null>(null);

  // On narrow screens the nav is a drawer: open it while nav steps are shown.
  useEffect(() => {
    onNeedNav?.(!!step.target?.startsWith("nav-"));
  }, [step.target, onNeedNav]);

  useLayoutEffect(() => {
    const update = () => {
      const el = step.target ? document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`) : null;
      el?.scrollIntoView({ block: "nearest", inline: "nearest" });
      setRect(measure(step.target));
    };
    update();
    const id = window.setTimeout(update, 260); // after the mobile drawer slides in
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.clearTimeout(id);
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [step.target]);

  useLayoutEffect(() => {
    const p = pop.current;
    if (!p) return;
    const pw = p.offsetWidth;
    const ph = p.offsetHeight;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const m = 12;
    if (!rect) {
      setPopPos({ top: Math.max(m, (vh - ph) / 2), left: Math.max(m, (vw - pw) / 2) });
      return;
    }
    // Prefer beside the target (nav items), else below, else above.
    const besideRoom = lang === "fa" ? rect.left : vw - (rect.left + rect.width);
    let top: number;
    let left: number;
    if (besideRoom > pw + 2 * m && rect.height < 80) {
      left = lang === "fa" ? rect.left - pw - m : rect.left + rect.width + m;
      top = rect.top + rect.height / 2 - ph / 2;
    } else if (rect.top + rect.height + ph + m < vh) {
      top = rect.top + rect.height + m;
      left = rect.left + rect.width / 2 - pw / 2;
    } else {
      top = rect.top - ph - m;
      left = rect.left + rect.width / 2 - pw / 2;
    }
    setPopPos({ top: Math.min(Math.max(m, top), vh - ph - m), left: Math.min(Math.max(m, left), vw - pw - m) });
  }, [rect, index, lang]);

  useEffect(() => {
    pop.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onFinish();
      if (e.key === "Enter") index < STEPS.length - 1 ? setIndex(index + 1) : onFinish();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, onFinish, setIndex]);

  const last = index === STEPS.length - 1;
  const pad = 6;
  return (
    <div className="tour" role="presentation">
      <div
        className={rect ? "tour-spot" : "tour-spot tour-spot-none"}
        style={
          rect
            ? { transform: `translate(${rect.left - pad}px, ${rect.top - pad}px)`, width: rect.width + 2 * pad, height: rect.height + 2 * pad }
            : { transform: `translate(${window.innerWidth / 2}px, ${window.innerHeight / 2}px)`, width: 0, height: 0 }
        }
        aria-hidden
      />
      <div
        ref={pop}
        className="tour-pop"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        tabIndex={-1}
        style={popPos ? { top: popPos.top, left: popPos.left } : { visibility: "hidden" }}
        key={index}
      >
        <div className="tour-progress" aria-hidden>
          {STEPS.map((_, n) => (
            <span key={n} className={n === index ? "on" : n < index ? "done" : undefined} />
          ))}
        </div>
        <small className="muted">
          {t("tourStepOf")} {formatDecimal(String(index + 1), lang)} / {formatDecimal(String(STEPS.length), lang)}
        </small>
        <h2 id="tour-title">{t(step.title)}</h2>
        <p>{t(step.body)}</p>
        <div className="tour-actions">
          <Button variant="ghost" onClick={onFinish}>
            {t("tourSkip")}
          </Button>
          <span className="row gap">
            {index > 0 && <Button onClick={() => setIndex(index - 1)}>{t("tourBack")}</Button>}
            <Button variant="primary" onClick={() => (last ? onFinish() : setIndex(index + 1))}>
              {last ? t("tourDone") : t("tourNext")}
            </Button>
          </span>
        </div>
      </div>
    </div>
  );
}
