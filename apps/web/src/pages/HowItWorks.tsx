import { Link } from "react-router-dom";
import examples from "../lib/howItWorksExamples.json";
import { useI18n, type TKey } from "../lib/i18n";
import { useSession } from "../lib/session";
import { Button, Card, Money, Num, Pct } from "../components/ui";
import { Lockup } from "../components/Brand";

const STEPS: [TKey, TKey][] = [
  ["hwStep1T", "hwStep1B"],
  ["hwStep2T", "hwStep2B"],
  ["hwStep3T", "hwStep3B"],
  ["hwStep4T", "hwStep4B"],
  ["hwStep5T", "hwStep5B"],
];

const STATUSES: [string, TKey][] = [
  ["EXACT", "hwStatusExact"],
  ["PRICE_UNAVAILABLE", "hwStatusUnavailable"],
  ["DISCOVERY_ONLY", "hwStatusDiscovery"],
  ["NEEDS_HUMAN_REVIEW", "hwStatusReview"],
];

const WEIGHTS: [TKey, number][] = [
  ["hwWeightCpu", 25],
  ["hwWeightRam", 25],
  ["hwWeightDisk", 15],
  ["hwWeightClass", 15],
  ["hwWeightTraffic", 10],
  ["hwWeightDatacenter", 5],
  ["hwWeightBilling", 5],
];

function Bullets({ items }: { items: TKey[] }) {
  const { t } = useI18n();
  return (
    <ul className="hw-list">
      {items.map((k) => (
        <li key={k}>{t(k)}</li>
      ))}
    </ul>
  );
}

function PricingExample({ ex }: { ex: (typeof examples.pricing)[number] }) {
  const { t, pick } = useI18n();
  return (
    <div className="hw-example">
      <h3>
        {pick(ex.title.fa, ex.title.en)} <small className="muted">· {pick(ex.provider.fa, ex.provider.en)}</small>
      </h3>
      <p className="muted">{pick(ex.body.fa, ex.body.en)}</p>
      <div className="table-wrap">
        <table className="table compact">
          <thead>
            <tr>
              <th>{t("component")}</th>
              <th className="num-col">{t("quantity")}</th>
              <th className="num-col">{t("unitPrice")}</th>
              <th className="num-col">{t("subtotal")}</th>
            </tr>
          </thead>
          <tbody>
            {ex.lines.map((l) => (
              <tr key={l.code}>
                <td>{pick(l.fa, l.en)}</td>
                <td className="num-col">
                  <Num v={l.qty} />
                </td>
                <td className="num-col">{l.unit_price === "0" ? t("hwIncluded") : <Money v={l.unit_price} />}</td>
                <td className="num-col">{l.subtotal === "0" ? t("hwIncluded") : <Money v={l.subtotal} />}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th colSpan={3}>{t("hwMonthlyTotal")}</th>
              <td className="num-col strong">
                <Money v={ex.total} />
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

function Calc({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="hw-calc">
      <span className="muted">{label}</span>
      <strong>{children}</strong>
    </div>
  );
}

export function HowItWorksContent() {
  const { t } = useI18n();
  const d = examples.downsize;
  const pb = examples.payback;
  return (
    <div className="stack hw">
      <header className="stack">
        <h1>{t("hwTitle")}</h1>
        <p className="hw-lead">{t("hwLead")}</p>
      </header>

      <Card title={t("hwStepsTitle")}>
        <ol className="hw-steps">
          {STEPS.map(([title, body], i) => (
            <li key={title}>
              <span className="hw-step-n" aria-hidden>
                <Num v={String(i + 1)} />
              </span>
              <div>
                <strong>{t(title)}</strong>
                <p className="muted">{t(body)}</p>
              </div>
            </li>
          ))}
        </ol>
      </Card>

      <Card title={t("hwPricesTitle")}>
        <p>{t("hwPricesBody")}</p>
        <Bullets items={["hwPrices1", "hwPrices2", "hwPrices3", "hwPrices4"]} />
      </Card>

      <Card title={t("hwCostTitle")}>
        <p>{t("hwCostBody")}</p>
        {examples.pricing.map((ex) => (
          <PricingExample key={ex.id} ex={ex} />
        ))}
        <p className="alert alert-warn">{t("hwExampleNote")}</p>
        <Bullets items={["hwCostRule1", "hwCostRule2", "hwCostRule3", "hwCostRule4"]} />
      </Card>

      <Card title={t("hwUsageTitle")}>
        <p>{t("hwUsageBody")}</p>
        <Bullets items={["hwUsage1", "hwUsage2", "hwUsage3"]} />
      </Card>

      <Card title={t("hwSavingTitle")}>
        <p>{t("hwSavingBody")}</p>
        <h3>{t("hwDownsizeTitle")}</h3>
        <div className="hw-calcs">
          <Calc label={t("hwCalcObserved")}>
            <Pct v={d.ram_p95} /> · <Num v={d.ram_gb} /> GB
          </Calc>
          <Calc label={t("hwCalcNeeded")}>
            <span dir="ltr">
              <Num v={d.ram_gb} /> × <Pct v={d.ram_p95} /> × <Num v={d.headroom} /> = <Num v={d.required_ram_gb} /> GB
            </span>
          </Calc>
          <Calc label={t("hwCalcPlan")}>
            <span dir="ltr">{d.candidate_sku}</span>
          </Calc>
          <Calc label={t("hwCalcSaving")}>
            <span dir="ltr">
              <Money v={d.current} /> − <Money v={d.candidate} /> = <Money v={d.saving} />
            </span>{" "}
            (<Pct v={d.saving_percent} />)
          </Calc>
        </div>
        <p className="muted">{t("hwDownsizeNote")}</p>
        <h3>{t("hwOtherSavings")}</h3>
        <Bullets items={["hwSavingHourly", "hwSavingMove", "hwSavingCadence"]} />
        <p>{t("hwSavingRules")}</p>
      </Card>

      <Card title={t("hwCompareTitle")}>
        <p>{t("hwCompareBody")}</p>
        <Bullets items={["hwCompare1", "hwCompare2", "hwCompare3", "hwCompare4"]} />
        <h3>{t("hwScoreTitle")}</h3>
        <p className="muted">{t("hwScoreBody")}</p>
        <ul className="hw-weights">
          {WEIGHTS.map(([k, w]) => (
            <li key={k}>
              <span>{t(k)}</span>
              <span className="hw-bar" aria-hidden>
                <span style={{ width: `${w * 4}%` }} />
              </span>
              <Pct v={String(w)} />
            </li>
          ))}
        </ul>
        <h3>{t("hwPaybackTitle")}</h3>
        <div className="hw-calcs">
          <Calc label={t("hwCalcMoveCost")}>
            <span dir="ltr">
              <Num v={pb.days} /> × <Money v={pb.day_rate} /> = <Money v={pb.cost} />
            </span>
          </Calc>
          <Calc label={t("hwCalcPayback")}>
            <span dir="ltr">
              <Money v={pb.cost} /> ÷ <Money v={pb.saving} /> = <Num v={pb.months} />
            </span>{" "}
            {t("hwMonths")}
          </Calc>
        </div>
        <p className="muted">{t("hwPaybackNote")}</p>
      </Card>

      <Card title={t("hwStatusTitle")}>
        <dl className="hw-status">
          {STATUSES.map(([code, k]) => (
            <div key={code}>
              <dt>
                <code dir="ltr">{code}</code>
              </dt>
              <dd>{t(k)}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <Card title={t("hwAiTitle")}>
        <p>{t("hwAiBody")}</p>
        <Bullets items={["hwAi1", "hwAi2", "hwAi3"]} />
      </Card>

      <Card title={t("hwLimitsTitle")}>
        <Bullets items={["hwLimit1", "hwLimit2", "hwLimit3", "hwLimit4"]} />
      </Card>
    </div>
  );
}

/** The same explanation for people who haven't signed in, linked from the landing page. */
export function HowItWorksPublic() {
  const { t, lang, setLang } = useI18n();
  const { session } = useSession();
  return (
    <div className="hw-public">
      <header className="hw-public-bar">
        <Link to="/welcome" className="brand brand-link" aria-label={t("appName")}>
          <Lockup laid />
        </Link>
        <div className="row gap">
          <Button variant="ghost" onClick={() => setLang(lang === "fa" ? "en" : "fa")} aria-label={t("language")}>
            {lang === "fa" ? "EN" : "فا"}
          </Button>
          <Link className="btn btn-primary" to={session ? "/" : "/login"}>
            {session ? t("navOverview") : t("login")}
          </Link>
        </div>
      </header>
      <main className="hw-public-main">
        <HowItWorksContent />
      </main>
    </div>
  );
}
