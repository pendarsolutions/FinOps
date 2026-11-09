import { Fragment, useRef, useState, type CSSProperties } from "react";
import { Lockup, PoweredBy } from "./Brand";
import { Icon, type IconName } from "./Icon";
import { formatWhole, localizeDigits } from "./format";
import { GUIDE, INSTALL_COMMAND, LICENSE, RELEASES, REPO } from "./links";
import { useReveal } from "./motion";
import { useT, type Key } from "./strings";

// Real engine output for data/seeds/sample_inventory.json (also asserted in tests/api/test_flow.py).
const DEMO = {
  total: "20574439",
  avoidable: "5343839",
  // in the app's provider order, which fixes each provider's chart colour (apps/web/src/lib/viz.ts)
  providers: [
    { id: "arvancloud", slot: 1, fa: "ابر آروان", en: "ArvanCloud", v: "8875600" },
    { id: "iranserver", slot: 4, fa: "ایران‌سرور", en: "IranServer", v: "5323839" },
    { id: "serverir", slot: 3, fa: "سرور.آی‌آر", en: "Server.ir", v: "3500000" },
    { id: "liara", slot: 2, fa: "لیارا", en: "Liara", v: "2875000" },
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

const STEPS: [Key, Key][] = [
  ["lpStep1T", "lpStep1B"],
  ["lpStep2T", "lpStep2B"],
  ["lpStep3T", "lpStep3B"],
  ["lpStep4T", "lpStep4B"],
  ["lpStep5T", "lpStep5B"],
];

const FEATURES: [IconName, Key, Key][] = [
  ["check", "lpF1T", "lpF1B"],
  ["rank", "lpF2T", "lpF2B"],
  ["file", "lpF3T", "lpF3B"],
  ["clock", "lpF4T", "lpF4B"],
  ["chat", "lpF5T", "lpF5B"],
  ["globe", "lpF6T", "lpF6B"],
];

/** A few of the `finops-agent` commands an installation is run with (deploy/finops-agent). */
const MANAGE: [Key, string][] = [
  ["lpManage1", "sudo finops-agent status"],
  ["lpManage2", "sudo finops-agent config set SMTP_HOST=mail.example.ir"],
  ["lpManage3", "sudo finops-agent upgrade"],
  ["lpManage4", "sudo finops-agent doctor"],
];

/** An item's place in its group, for the stagger in site.css (one by one, in reading order). */
const at = (i: number) => ({ "--i": i }) as CSSProperties;

/** Each word in its own box, so a heading can arrive, or light up, word by word in reading order. */
function Words({ text, from = 0 }: { text: string; from?: number }) {
  return (
    <>
      {text.split(" ").map((w, i) => (
        <Fragment key={i}>
          {i > 0 ? " " : null}
          <span className="w" style={at(from + i)}>
            {w}
          </span>
        </Fragment>
      ))}
    </>
  );
}

/** Command-line flags kept left to right inside Persian text, so `--registry-mirror` doesn't turn into `registry-mirror--`. */
function Flags({ text }: { text: string }) {
  return (
    <>
      {text.split(/(--[a-z-]+)/).map((part, i) =>
        part.startsWith("--") ? (
          <code key={i} dir="ltr">
            {part}
          </code>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

/** The closing band's top edge: a course of bricks that rises as the band scrolls in. */
const EDGE = Array.from({ length: 16 }, (_, i) => i);

/** A command to copy. Without clipboard access (plain http, an old browser) it selects the text instead. */
function Command({ text, label }: { text: string; label: string }) {
  const { t } = useT();
  const [done, setDone] = useState(false);
  const code = useRef<HTMLElement>(null);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setDone(true);
      window.setTimeout(() => setDone(false), 2000);
    } catch {
      const sel = window.getSelection();
      if (code.current && sel) {
        sel.selectAllChildren(code.current);
      }
    }
  };
  return (
    <div className="lp-command">
      <code ref={code} dir="ltr" aria-label={label}>
        {text}
      </code>
      <button type="button" className="btn btn-sm" onClick={copy}>
        <Icon name={done ? "check" : "copy"} className={done ? "icon-drawn" : undefined} /> {done ? t("copied") : t("copy")}
      </button>
    </div>
  );
}

function Preview() {
  const { t, lang } = useT();
  const toman = lang === "fa" ? "تومان" : "Toman";
  const total = Number(DEMO.total);
  return (
    <div className="lp-preview hero-in" style={at(2)} aria-label={t("lpPreviewLabel")}>
      <small className="muted">{t("lpPreviewLabel")}</small>
      <div className="lp-preview-stats">
        <div>
          <span className="stat-label">{t("lpPreviewSpend")}</span>
          <strong className="lp-figure">
            {formatWhole(DEMO.total, lang)} <small>{toman}</small>
          </strong>
        </div>
        <div>
          <span className="stat-label">{t("lpPreviewAvoidable")}</span>
          <strong className="lp-figure lp-figure-accent">
            {formatWhole(DEMO.avoidable, lang)} <small>{toman}</small>
          </strong>
        </div>
      </div>
      <div className="lp-preview-chart">
        <figure className="share">
          <div className="share-bar" role="img" aria-label={t("providerDist")}>
            {DEMO.providers.map((p, i) => (
              // bar widths only; every amount shown is the exact figure in the list below
              <span key={p.id} className="share-seg" style={{ flexGrow: Number(p.v) / total, background: `var(--series-${p.slot})`, ...at(i) }} />
            ))}
          </div>
          <ul className="legend-list">
            {DEMO.providers.map((p) => (
              <li key={p.id}>
                <i className="swatch" style={{ background: `var(--series-${p.slot})` }} aria-hidden />
                <span className="legend-label">{lang === "fa" ? p.fa : p.en}</span>
                <span className="legend-value">
                  {formatWhole(p.v, lang)} {toman}
                </span>
              </li>
            ))}
          </ul>
        </figure>
      </div>
    </div>
  );
}

export function Landing() {
  const { t, lang, setLang } = useT();
  useReveal();
  const pick = (pair: string[]) => (lang === "fa" ? pair[0] : pair[1]);

  return (
    <div className="lp" id="top">
      <header className="lp-nav">
        <a href="#top" className="brand brand-link" aria-label={t("appName")}>
          <Lockup large laid />
        </a>
        <nav className="lp-links" aria-label={lang === "fa" ? "بخش‌ها" : "Sections"}>
          <a href="#how">{t("lpNavHow")}</a>
          <a href="#features">{t("lpNavFeatures")}</a>
          <a href="#install">{t("lpNavInstall")}</a>
          <a href="#trust">{t("lpNavTrust")}</a>
        </nav>
        <div className="lp-actions">
          <button type="button" className="btn btn-ghost" onClick={() => setLang(lang === "fa" ? "en" : "fa")} lang={lang === "fa" ? "en" : "fa"}>
            {lang === "fa" ? "EN" : "فا"}
          </button>
          <a className="btn btn-ghost" href={REPO}>
            GitHub
          </a>
          <a className="btn" href="#install">
            {t("lpNavInstall")}
          </a>
        </div>
      </header>

      <section className="lp-hero">
        <div className="lp-hero-copy">
          <span className="badge lp-new">{t("lpBadge")}</span>
          <h1>
            <Words text={t("lpHeroA")} />{" "}
            <span className="lp-accent">
              <Words text={t("lpHeroB")} from={t("lpHeroA").split(" ").length} />
            </span>
          </h1>
          <p className="lp-sub hero-in" style={at(0)}>
            {t("lpHeroSub")}
          </p>
          <div className="lp-ctas hero-in" style={at(1)}>
            <a className="btn btn-primary btn-lg" href="#install">
              {t("lpCtaInstall")} <Icon name="arrow-forward" />
            </a>
            <a className="btn btn-lg" href="#how">
              {t("lpCtaHow")}
            </a>
          </div>
        </div>
        <Preview />
      </section>

      <section className="lp-strip" aria-label={t("lpProvidersTitle")} data-reveal>
        <p className="muted reveal" style={at(0)}>
          {t("lpProvidersTitle")}
        </p>
        <ul className="lp-providers">
          {PROVIDER_STRIP.map((p, i) => (
            <li key={p[1]} className="reveal" style={at(i + 1)}>
              {pick(p)}
            </li>
          ))}
        </ul>
      </section>

      <section id="how" className="lp-section" data-reveal>
        <h2 className="reveal" style={at(0)}>
          {t("lpHowTitle")}
        </h2>
        <ol className="lp-steps">
          {STEPS.map(([title, body], i) => (
            <li key={title} className="reveal" style={at(i + 1)}>
              <span className="lp-step-n">{localizeDigits(String(i + 1), lang)}</span>
              <h3>{t(title)}</h3>
              <p>{t(body)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section id="features" className="lp-section" data-reveal>
        <h2 className="reveal" style={at(0)}>
          {t("lpFeatTitle")}
        </h2>
        <div className="lp-features">
          {FEATURES.map(([icon, title, body], i) => (
            <article key={title} className="lp-feature reveal" style={at(i + 1)}>
              <span className="lp-icon">
                <Icon name={icon} />
              </span>
              <h3>{t(title)}</h3>
              <p>{t(body)}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="install" className="lp-section lp-install" data-reveal>
        <h2 className="reveal" style={at(0)}>
          {t("lpInstallTitle")}
        </h2>
        <p className="lp-lead reveal" style={at(1)}>
          {t("lpInstallBody")}
        </p>
        <div className="reveal" style={at(2)}>
          <Command text={INSTALL_COMMAND} label={t("lpInstallCommandLabel")} />
        </div>
        <p className="muted reveal" style={at(3)}>
          <Flags text={t("lpInstallBlocked")} />
        </p>
        <h3 className="reveal" style={at(4)}>
          {t("lpManageTitle")}
        </h3>
        <dl className="lp-manage reveal" style={at(5)}>
          {MANAGE.map(([label, command]) => (
            <div key={command}>
              <dt>{t(label)}</dt>
              <dd>
                <code dir="ltr">{command}</code>
              </dd>
            </div>
          ))}
        </dl>
        <ul className="lp-install-links reveal" style={at(6)}>
          <li>
            <a href={GUIDE}>
              {t("lpLinkGuide")} <Icon name="external" />
            </a>
          </li>
          <li>
            <a href={RELEASES}>
              {t("lpLinkReleases")} <Icon name="external" />
            </a>
          </li>
          <li>
            <a href={REPO}>
              {t("lpLinkSource")} <Icon name="external" />
            </a>
          </li>
        </ul>
      </section>

      <section id="trust" className="lp-section lp-trust" data-reveal>
        <h2 className="reveal" style={at(0)}>
          {t("lpTrustTitle")}
        </h2>
        <ul>
          {(["lpT1", "lpT2", "lpT3", "lpT4"] as Key[]).map((k, i) => (
            <li key={k} className="reveal" style={at(i + 1)}>
              <Icon name="ban" className="lp-x" />
              {t(k)}
            </li>
          ))}
        </ul>
      </section>

      <section className="lp-final" data-reveal>
        <div className="lp-edge" aria-hidden>
          {EDGE.map((i) => (
            <span key={i} style={at(i)} />
          ))}
        </div>
        <Lockup large laid />
        <h2 className="lp-statement">
          <Words text={t("lpFinalTitle")} />
        </h2>
        <p className="reveal" style={at(1)}>
          {t("lpFinalBody")}
        </p>
        <div className="lp-ctas reveal" style={at(2)}>
          <a className="btn btn-lg btn-primary" href="#install">
            {t("lpCtaInstall")}
          </a>
          <a className="btn btn-lg btn-on-inverse" href={REPO}>
            {t("lpCtaGithub")}
          </a>
        </div>
      </section>

      <footer className="lp-footer">
        <span>{t("lpFooter")}</span>
        <a href={REPO}>GitHub</a>
        <a href={GUIDE}>{t("lpLinkGuide")}</a>
        <a href={LICENSE}>{t("lpLicense")}</a>
        <span>© {localizeDigits("2026", lang)}</span>
        <PoweredBy />
      </footer>
    </div>
  );
}
