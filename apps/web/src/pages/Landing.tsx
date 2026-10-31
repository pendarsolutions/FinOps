import { useEffect, useRef, type ReactNode } from "react";
import { Link, Navigate } from "react-router-dom";
import { useI18n, type TKey } from "../lib/i18n";
import { useSession } from "../lib/session";
import { formatDecimal, localizeDigits } from "../lib/money";
import { providerColor } from "../lib/viz";
import { ShareBar, TooltipLayer } from "../components/viz";

/** Adds `.in` to every [data-reveal] descendant when it scrolls into view (CSS does the motion). */
function useReveal() {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const els = root.current?.querySelectorAll<HTMLElement>("[data-reveal]") ?? [];
    if (!("IntersectionObserver" in window)) {
      els.forEach((e) => e.classList.add("in"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((en) => {
          if (en.isIntersecting) {
            en.target.classList.add("in");
            io.unobserve(en.target);
          }
        }),
      { threshold: 0.15, rootMargin: "0px 0px -40px 0px" },
    );
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, []);
  return root;
}

// Real engine output for data/seeds/sample_inventory.json (also asserted in tests/api/test_flow.py).
const DEMO = {
  total: "20574439",
  avoidable: "5343839",
  providers: [
    { id: "arvancloud", fa: "ابر آروان", en: "ArvanCloud", v: "8875600" },
    { id: "iranserver", fa: "ایران‌سرور", en: "IranServer", v: "5323839" },
    { id: "serverir", fa: "سرور.آی‌آر", en: "Server.ir", v: "3500000" },
    { id: "liara", fa: "لیارا", en: "Liara", v: "2875000" },
  ],
};

const PROVIDER_STRIP = [
  ["ابر آروان", "ArvanCloud"],
  ["لیارا", "Liara"],
  ["سرور.آی‌آر", "Server.ir"],
  ["ایران‌سرور", "IranServer"],
  ["چابکان", "Chabokan"],
  ["پارس‌پک", "ParsPack"],
  ["مبین‌هاست", "MobinHost"],
  ["ابرها", "Abrha"],
];

const ICONS: Record<string, ReactNode> = {
  exact: <path d="M4 12l5 5L20 6" />,
  equal: <path d="M5 9h14M5 15h14M17 4L7 20" />,
  evidence: <path d="M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6" />,
  history: <path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 3" />,
  advisor: <path d="M4 5h16v11H9l-5 4zM8 9h8M8 12h5" />,
  lang: <path d="M4 5h9M8.5 3v2M6 5c0 4 3 7 6 8M11 5c0 3-2 7-6 9M13 21l4-9 4 9M14.5 18h5" />,
};

function Icon({ name }: { name: string }) {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {ICONS[name]}
    </svg>
  );
}

export function LandingPage() {
  const { t, lang, setLang } = useI18n();
  const { session } = useSession();
  const root = useReveal();
  if (session) return <Navigate to="/" replace />;
  const pick = (pair: string[]) => (lang === "fa" ? pair[0] : pair[1]);

  const steps: [TKey, TKey][] = [
    ["lpStep1T", "lpStep1B"],
    ["lpStep2T", "lpStep2B"],
    ["lpStep3T", "lpStep3B"],
    ["lpStep4T", "lpStep4B"],
    ["lpStep5T", "lpStep5B"],
  ];
  const features: [string, TKey, TKey][] = [
    ["exact", "lpF1T", "lpF1B"],
    ["equal", "lpF2T", "lpF2B"],
    ["evidence", "lpF3T", "lpF3B"],
    ["history", "lpF4T", "lpF4B"],
    ["advisor", "lpF5T", "lpF5B"],
    ["lang", "lpF6T", "lpF6B"],
  ];

  return (
    <div className="lp" ref={root}>
      <div className="lp-bg" aria-hidden>
        <span className="blob b1" />
        <span className="blob b2" />
        <span className="blob b3" />
        <span className="grid-fade" />
      </div>

      <header className="lp-nav">
        <div className="brand">
          <span className="logo" aria-hidden>
            P
          </span>
          <span>{t("appName")}</span>
        </div>
        <nav className="lp-links" aria-label="Landing">
          <a href="#how">{t("lpNavHow")}</a>
          <a href="#features">{t("lpNavFeatures")}</a>
          <a href="#trust">{t("lpNavTrust")}</a>
        </nav>
        <div className="lp-actions">
          <button type="button" className="btn btn-ghost" onClick={() => setLang(lang === "fa" ? "en" : "fa")} lang={lang === "fa" ? "en" : "fa"}>
            {lang === "fa" ? "EN" : "فا"}
          </button>
          <Link className="btn btn-ghost" to="/login">
            {t("lpCtaLogin")}
          </Link>
          <Link className="btn btn-primary" to="/register">
            {t("lpCtaStart")}
          </Link>
        </div>
      </header>

      <section className="lp-hero">
        <div className="lp-hero-copy">
          <span className="lp-pill rise" style={{ animationDelay: "0ms" }}>
            <span className="pulse-dot" aria-hidden /> {t("lpBadge")}
          </span>
          <h1 className="rise" style={{ animationDelay: "80ms" }}>
            {t("lpHeroA")} <span className="lp-grad">{t("lpHeroB")}</span>
          </h1>
          <p className="lp-sub rise" style={{ animationDelay: "160ms" }}>
            {t("lpHeroSub")}
          </p>
          <div className="lp-ctas rise" style={{ animationDelay: "240ms" }}>
            <Link className="btn btn-primary btn-lg" to="/register">
              {t("lpCtaStart")} <span aria-hidden>{lang === "fa" ? "←" : "→"}</span>
            </Link>
            <a className="btn btn-lg btn-glass" href="#how">
              {t("lpCtaHow")}
            </a>
          </div>
        </div>

        <TooltipLayer>
          <div className="lp-preview float-in" aria-label={t("lpPreviewLabel")}>
            <div className="lp-preview-chrome" aria-hidden>
              <span />
              <span />
              <span />
            </div>
            <small className="muted">{t("lpPreviewLabel")}</small>
            <div className="lp-preview-stats">
              <div>
                <span className="stat-label">{t("lpPreviewSpend")}</span>
                <strong className="lp-figure">
                  {formatDecimal(DEMO.total, lang)} <small>{lang === "fa" ? "تومان" : "Toman"}</small>
                </strong>
              </div>
              <div>
                <span className="stat-label">{t("lpPreviewAvoidable")}</span>
                <strong className="lp-figure lp-figure-accent">
                  {formatDecimal(DEMO.avoidable, lang)} <small>{lang === "fa" ? "تومان" : "Toman"}</small>
                </strong>
              </div>
            </div>
            <div className="lp-preview-chart">
              <ShareBar
                caption={t("providerDist")}
                total={DEMO.total}
                items={DEMO.providers.map((p) => ({ key: p.id, label: lang === "fa" ? p.fa : p.en, value: p.v, color: providerColor(p.id).css }))}
              />
            </div>
          </div>
        </TooltipLayer>
      </section>

      <section className="lp-strip" aria-label={t("lpProvidersTitle")}>
        <p className="muted">{t("lpProvidersTitle")}</p>
        <div className="marquee">
          <div className="marquee-track">
            {[...PROVIDER_STRIP, ...PROVIDER_STRIP].map((p, i) => (
              <span key={i} className="marquee-item" aria-hidden={i >= PROVIDER_STRIP.length}>
                {pick(p)}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section id="how" className="lp-section">
        <h2 data-reveal>{t("lpHowTitle")}</h2>
        <ol className="lp-steps">
          {steps.map(([title, body], i) => (
            <li key={title} data-reveal style={{ transitionDelay: `${i * 90}ms` }}>
              <span className="lp-step-n">{formatDecimal(String(i + 1), lang)}</span>
              <h3>{t(title)}</h3>
              <p>{t(body)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section id="features" className="lp-section">
        <h2 data-reveal>{t("lpFeatTitle")}</h2>
        <div className="lp-features">
          {features.map(([icon, title, body], i) => (
            <article key={title} className="lp-feature" data-reveal style={{ transitionDelay: `${(i % 3) * 90}ms` }}>
              <span className="lp-icon">
                <Icon name={icon} />
              </span>
              <h3>{t(title)}</h3>
              <p>{t(body)}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="trust" className="lp-section lp-trust" data-reveal>
        <h2>{t("lpTrustTitle")}</h2>
        <ul>
          {(["lpT1", "lpT2", "lpT3", "lpT4"] as TKey[]).map((k) => (
            <li key={k}>
              <span className="lp-x" aria-hidden>
                ✕
              </span>
              {t(k)}
            </li>
          ))}
        </ul>
      </section>

      <section className="lp-final" data-reveal>
        <h2>{t("lpFinalTitle")}</h2>
        <p>{t("lpFinalBody")}</p>
        <div className="lp-ctas">
          <Link className="btn btn-lg btn-light" to="/register">
            {t("lpCtaStart")}
          </Link>
          <Link className="btn btn-lg btn-glass-dark" to="/login">
            {t("lpCtaLogin")}
          </Link>
        </div>
      </section>

      <footer className="lp-footer">
        <span>{t("lpFooter")}</span>
        <span className="muted">© {localizeDigits("2026", lang)}</span>
      </footer>
    </div>
  );
}
