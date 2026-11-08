import type { CSSProperties } from "react";
import { Link, Navigate } from "react-router-dom";
import { useI18n, type TKey } from "../lib/i18n";
import { useSession } from "../lib/session";
import { formatDecimal, localizeDigits } from "../lib/money";
import { providerColor } from "../lib/viz";
import { ShareBar, TooltipLayer } from "../components/viz";
import { Lockup, PoweredBy } from "../components/Brand";
import { Icon, type IconName } from "../components/Icon";

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

/** The hero copy arrives once, one line after another (motion guideline). */
const stagger = (n: number) => ({ animationDelay: `calc(var(--duration-stagger) * ${n * 2})` }) as CSSProperties;

export function LandingPage() {
  const { t, lang, setLang } = useI18n();
  const { session } = useSession();
  if (session) return <Navigate to="/" replace />;
  const pick = (pair: string[]) => (lang === "fa" ? pair[0] : pair[1]);

  const steps: [TKey, TKey][] = [
    ["lpStep1T", "lpStep1B"],
    ["lpStep2T", "lpStep2B"],
    ["lpStep3T", "lpStep3B"],
    ["lpStep4T", "lpStep4B"],
    ["lpStep5T", "lpStep5B"],
  ];
  const features: [IconName, TKey, TKey][] = [
    ["check", "lpF1T", "lpF1B"],
    ["rank", "lpF2T", "lpF2B"],
    ["file", "lpF3T", "lpF3B"],
    ["clock", "lpF4T", "lpF4B"],
    ["chat", "lpF5T", "lpF5B"],
    ["globe", "lpF6T", "lpF6B"],
  ];

  return (
    <div className="lp">
      <header className="lp-nav">
        <Link to="/welcome" className="brand brand-link" aria-label={t("appName")}>
          <Lockup large />
        </Link>
        <nav className="lp-links" aria-label="Landing">
          <Link to="/how-it-works">{t("navHowItWorks")}</Link>
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
          <Link className="btn" to="/register">
            {t("lpCtaStart")}
          </Link>
        </div>
      </header>

      <section className="lp-hero">
        <div className="lp-hero-copy">
          <span className="badge lp-new rise" style={stagger(0)}>
            {t("lpBadge")}
          </span>
          <h1 className="rise" style={stagger(1)}>
            {t("lpHeroA")} <span className="lp-accent">{t("lpHeroB")}</span>
          </h1>
          <p className="lp-sub rise" style={stagger(2)}>
            {t("lpHeroSub")}
          </p>
          <div className="lp-ctas rise" style={stagger(3)}>
            <Link className="btn btn-primary btn-lg" to="/register">
              {t("lpCtaStart")} <Icon name="arrow-forward" />
            </Link>
            <a className="btn btn-lg" href="#how">
              {t("lpCtaHow")}
            </a>
          </div>
        </div>

        <TooltipLayer>
          <div className="lp-preview" aria-label={t("lpPreviewLabel")}>
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
        <ul className="lp-providers">
          {PROVIDER_STRIP.map((p) => (
            <li key={p[1]}>{pick(p)}</li>
          ))}
        </ul>
      </section>

      <section id="how" className="lp-section">
        <h2>{t("lpHowTitle")}</h2>
        <ol className="lp-steps">
          {steps.map(([title, body], i) => (
            <li key={title}>
              <span className="lp-step-n">{formatDecimal(String(i + 1), lang)}</span>
              <h3>{t(title)}</h3>
              <p>{t(body)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section id="features" className="lp-section">
        <h2>{t("lpFeatTitle")}</h2>
        <div className="lp-features">
          {features.map(([icon, title, body]) => (
            <article key={title} className="lp-feature">
              <span className="lp-icon">
                <Icon name={icon} />
              </span>
              <h3>{t(title)}</h3>
              <p>{t(body)}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="trust" className="lp-section lp-trust">
        <h2>{t("lpTrustTitle")}</h2>
        <ul>
          {(["lpT1", "lpT2", "lpT3", "lpT4"] as TKey[]).map((k) => (
            <li key={k}>
              <Icon name="ban" className="lp-x" />
              {t(k)}
            </li>
          ))}
        </ul>
      </section>

      <section className="lp-final">
        <h2>{t("lpFinalTitle")}</h2>
        <p>{t("lpFinalBody")}</p>
        <div className="lp-ctas">
          <Link className="btn btn-lg btn-primary" to="/register">
            {t("lpCtaStart")}
          </Link>
          <Link className="btn btn-lg btn-on-inverse" to="/login">
            {t("lpCtaLogin")}
          </Link>
        </div>
      </section>

      <footer className="lp-footer">
        <span>{t("lpFooter")}</span>
        <Link to="/how-it-works">{t("navHowItWorks")}</Link>
        <span>© {localizeDigits("2026", lang)}</span>
        <PoweredBy />
      </footer>
    </div>
  );
}
