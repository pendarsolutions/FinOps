import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ComponentLine, ConstraintResult, Dec, Difference, InventoryView, Recommendation } from "../api/types";
import { Link } from "react-router-dom";
import { useI18n } from "../lib/i18n";
import { formatDecimal, localizeDigits } from "../lib/money";
import { recTitle, usePlain } from "../lib/plain";
import { ConfirmedInventory } from "../components/Guard";
import { Badge, Button, Card, ErrorBox, LinesTable, Loading, Money, Num, Pct, ToneBadge } from "../components/ui";
import { BeforeAfter, RankedBars } from "../components/viz";

const VERDICT: Record<string, { mark: string; key: "vBetter" | "vWorse" | "vSame" | "vDifferent" | "vUnknown" }> = {
  better: { mark: "▲", key: "vBetter" },
  worse: { mark: "▼", key: "vWorse" },
  same: { mark: "=", key: "vSame" },
  different: { mark: "≠", key: "vDifferent" },
  unknown: { mark: "?", key: "vUnknown" },
};

/** Verdict = shape mark + word + tone (never color alone). */
export function VerdictBadge({ v }: { v: string }) {
  const { t } = useI18n();
  const meta = VERDICT[v] ?? VERDICT.unknown;
  return (
    <span className={`verdict verdict-${v}`}>
      <span aria-hidden>{meta.mark}</span> {t(meta.key)}
    </span>
  );
}

/** A 0–1 match score as a whole percentage. Display only. */
export function FitPercent({ v }: { v: Dec | null }) {
  const { lang } = useI18n();
  if (v === null) return <>—</>;
  const pct = Math.round(Number(v) * 100);
  return <span className="num">{lang === "fa" ? `${localizeDigits(String(pct), lang)}٪` : `${pct}%`}</span>;
}

export function ConstraintsList({ items }: { items: ConstraintResult[] }) {
  const { t } = useI18n();
  const p = usePlain();
  return (
    <ul className="plain small">
      {items.map((c) => {
        // A check that passed only because nothing is known isn't a real pass.
        const unknown = c.passed && c.detail === "cpu class: unknown";
        return (
          <li key={c.constraint_id}>
            <Badge tone={unknown ? "warn" : c.passed ? "good" : "bad"}>{unknown ? "?" : c.passed ? "✓" : "✗"}</Badge>{" "}
            {unknown ? t("cpuTypeUnknown") : p.check(c)}
            {!c.passed && c.constraint_id === "HC-PRICEABLE" ? <div className="note">{p.note(c.detail)}</div> : null}
          </li>
        );
      })}
    </ul>
  );
}

/** Shown as a before/after row on the card. */
const SPEC_ROWS = ["cpu_cores", "ram_gb", "storage_gb", "included_traffic_gb", "datacenter"];
/** Already visible in the price lines, so they aren't repeated as differences. */
const COST_ROWS = new Set(["traffic_cost_toman", "ipv4_cost_toman"]);

function WhatChanges({ items }: { items: Difference[] }) {
  const { t } = useI18n();
  const p = usePlain();
  const rows = items.filter((d) => SPEC_ROWS.includes(d.dimension) && d.candidate_value !== null && d.verdict !== "unknown");
  if (!rows.length) return null;
  return (
    <div className="table-wrap">
      <table className="table compact">
        <thead>
          <tr>
            <th />
            <th>{t("nowLabel")}</th>
            <th>{t("afterMove")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.dimension}>
              <th scope="row">{p.dimension(d.dimension)}</th>
              <td>{p.value(d.dimension, d.source_value)}</td>
              <td>
                {p.value(d.dimension, d.candidate_value)} {d.verdict === "better" || d.verdict === "worse" ? <VerdictBadge v={d.verdict} /> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** What the price list doesn't say, as questions to ask the new provider. */
function AskFirst({ items }: { items: Difference[] }) {
  const { t, pick } = useI18n();
  const p = usePlain();
  const questions: string[] = [];
  for (const d of items) {
    if (d.verdict !== "unknown" || COST_ROWS.has(d.dimension)) continue;
    if (d.dimension === "cpu_class") questions.push(pick("پردازنده اختصاصی است یا اشتراکی؟", "Is the CPU dedicated or shared?"));
    else if (d.dimension === "storage_type") questions.push(pick("نوع دیسک چیست (مثلاً SSD یا NVMe)؟", "What type of disk is it (SSD or NVMe, for example)?"));
    else if (d.dimension === "datacenter") questions.push(pick("سرور در کدام دیتاسنتر است؟", "Which datacenter is the server in?"));
    else if (Array.isArray(d.candidate_value)) d.candidate_value.forEach((x) => questions.push(p.note(String(x))));
    else questions.push(p.dimension(d.dimension));
  }
  if (!questions.length) return null;
  return (
    <div className="opp-ask">
      <strong>{t("askFirst")}</strong>
      <ul>
        {questions.map((q) => (
          <li key={q}>{q}</li>
        ))}
      </ul>
    </div>
  );
}

function Migration({ r }: { r: Recommendation }) {
  const { t, lang, pick } = useI18n();
  const days = formatDecimal(r.evidence.migration_effort_days_per_instance as string | undefined, lang);
  return (
    <p className="small">
      {pick(`انتقال حدود ${days} روز کار مهندس می‌برد.`, `Moving takes about ${days} engineer days.`)}{" "}
      {r.one_time_migration_cost_toman !== null ? (
        <>
          {t("migrationCost")}: <Money v={r.one_time_migration_cost_toman} /> · {t("payback")}: <Num v={r.payback_months} max={1} />
        </>
      ) : (
        <>
          {pick("برای دیدن هزینه انتقال و زمان جبران آن، ", "To see what the move costs and when it pays off, ")}
          <Link to="/settings">{t("enterDayRate")}</Link>.
        </>
      )}
    </p>
  );
}

const INPUTS: Record<string, [string, string]> = {
  p95_cpu_percent: ["مصرف پردازنده در ۹۵٪ مواقع (٪)", "CPU use 95% of the time (%)"],
  p95_ram_percent: ["مصرف حافظه در ۹۵٪ مواقع (٪)", "Memory use 95% of the time (%)"],
  observation_days: ["روزهای اندازه‌گیری", "Days measured"],
  required_cpu_cores: ["پردازنده لازم (هسته)", "CPU needed (cores)"],
  required_ram_gb: ["حافظه لازم (گیگابایت)", "Memory needed (GB)"],
  required_storage_gb: ["دیسک لازم (گیگابایت)", "Disk needed (GB)"],
  active_hours_per_month: ["ساعت کار در ماه", "Hours used per month"],
};

/** The working behind a suggestion: both price lists, the checks it passed and how the prices were dated. */
function Working({ r }: { r: Recommendation }) {
  const { t, lang, pick } = useI18n();
  const e = r.evidence;
  const inputs = Object.entries((e.inputs ?? {}) as Record<string, unknown>).filter(([k]) => INPUTS[k]);
  return (
    <div className="stack">
      {e.current && (
        <>
          <h4>
            {t("currentLines")}: <Money v={e.current.monthly_total_toman ?? null} />
          </h4>
          <LinesTable lines={e.current.components as ComponentLine[]} />
        </>
      )}
      {e.candidate && (
        <>
          <h4>
            {t("afterChange")} {e.candidate_label ? `(${e.candidate_label})` : ""}: <Money v={e.candidate.monthly_total_toman ?? null} />
          </h4>
          <LinesTable lines={e.candidate.components as ComponentLine[]} />
        </>
      )}
      {inputs.length > 0 && (
        <dl className="kv">
          {inputs.map(([k, v]) => (
            <div key={k} className="kv-row">
              <dt>{pick(...INPUTS[k])}</dt>
              <dd>
                <Num v={String(v)} max={2} />
              </dd>
            </div>
          ))}
        </dl>
      )}
      {e.constraints && (
        <>
          <h4>{t("constraints")}</h4>
          <ConstraintsList items={e.constraints} />
        </>
      )}
      {e.fit_score && (
        <p className="small">
          <strong>{t("fitScore")}:</strong> <FitPercent v={e.fit_score} />. {t("fitExplain")}
        </p>
      )}
      {r.price_dates.length > 0 && (
        <p className="small muted">
          {t("priceDates")}: {localizeDigits([...new Set(r.price_dates.map((d) => d.slice(d.lastIndexOf(" ") + 1)))].join("، "), lang)}
        </p>
      )}
    </div>
  );
}

function OppCard({ r }: { r: Recommendation }) {
  const { t, lang, pick } = useI18n();
  const isMove = r.rule_id === "REC-003";
  const differences = r.evidence.differences ?? [];
  return (
    <article className="opp">
      <header className="row between wrap">
        <div>
          <h3>{recTitle(r, lang)}</h3>
          <small className="muted">
            {t("colServer")}: <strong>{r.resource_name ?? "—"}</strong>
          </small>
        </div>
        {r.monthly_saving_toman !== null && (
          <div className="opp-saving">
            <small className="muted">{t("youSave")}</small>
            <Money v={r.monthly_saving_toman} big suffix={t("perMonth")} />
            {r.monthly_saving_percent && (
              <small className="muted">
                <Pct v={r.monthly_saving_percent} /> {t("ofThisServer")}
              </small>
            )}
          </div>
        )}
      </header>
      {r.current_cost_toman !== null && r.candidate_cost_toman !== null && (
        <BeforeAfter current={r.current_cost_toman} after={r.candidate_cost_toman} saving={r.monthly_saving_toman} />
      )}
      {!isMove && <p className="small">{pick(r.summary_fa, r.summary_en)}</p>}
      {isMove && <WhatChanges items={differences} />}
      {isMove && <AskFirst items={differences} />}
      {isMove && <Migration r={r} />}
      <div className="row gap wrap small">
        <span>
          {t("risk")} <ToneBadge kind="risk" value={r.risk_level} />
        </span>
        <span>
          {t("effort")} <ToneBadge kind="effort" value={r.effort_level} />
        </span>
        {r.confidence !== "n/a" && (
          <span>
            {t("confidence")} <ToneBadge kind="confidence" value={r.confidence} />
          </span>
        )}
      </div>
      {r.evidence.current && (
        <details>
          <summary>{t("howCalculated")}</summary>
          <Working r={r} />
        </details>
      )}
    </article>
  );
}

/** One line per thing still needed, saying who has to do what. */
function Needed({ r }: { r: Recommendation }) {
  const { t, lang, pick, fieldLabel } = useI18n();
  const dayRate = r.missing_inputs.includes("organization.engineer_day_rate_toman");
  const days = r.missing_inputs.map((m) => /^metrics\.observation_days>=(\d+)$/.exec(m)?.[1]).find(Boolean);
  const metrics = r.missing_inputs.some((m) => m.startsWith("metrics."));
  let body;
  if (dayRate) {
    body = (
      <>
        {pick("برای محاسبه هزینه انتقال و زمان جبران آن، ", "To work out what a move costs and when it pays off, ")}
        <Link to="/settings">{t("enterDayRate")}</Link>.
      </>
    );
  } else if (metrics) {
    const n = days ? formatDecimal(days, lang) : null;
    body = n
      ? pick(`برای پیشنهاد سرور کوچک‌تر، مصرف این سرور باید دست‌کم ${n} روز اندازه‌گیری شود. سرور را متصل نگه دارید.`,
             `To suggest a smaller server, its usage must be measured for at least ${n} days. Keep the server connected.`)
      : pick("برای پیشنهاد سرور کوچک‌تر، مصرف پردازنده و حافظه این سرور لازم است. سرور را متصل نگه دارید.",
             "To suggest a smaller server, its CPU and memory usage is needed. Keep the server connected.");
  } else {
    body = (
      <>
        {pick(r.summary_fa, r.summary_en)}
        {r.missing_inputs.length > 0 && (
          <div className="small muted">
            {t("missing")}: {r.missing_inputs.map(fieldLabel).join("، ")}
          </div>
        )}
      </>
    );
  }
  return (
    <li className="cannot">
      <strong>{r.resource_name ?? "—"}</strong>: {body}
    </li>
  );
}

function OppsInner({ inv }: { inv: InventoryView }) {
  const { t, lang } = useI18n();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["recs", inv.id], queryFn: () => api.recs(inv.id) });
  const run = useMutation({
    mutationFn: () => api.runRecs(inv.id),
    onSuccess: (d) => {
      qc.setQueryData(["recs", inv.id], d);
      qc.invalidateQueries({ queryKey: ["overview", inv.id] });
      qc.invalidateQueries({ queryKey: ["quotes", inv.id] });
    },
  });
  const d = q.data;
  const counted = new Set(d?.summary?.counted_recommendation_keys ?? []);
  const groups = {
    actionable: d?.recommendations.filter((r) => r.result_status === "actionable") ?? [],
    informational: d?.recommendations.filter((r) => r.result_status === "informational") ?? [],
    cannot: d?.recommendations.filter((r) => r.result_status === "cannot_determine") ?? [],
  };

  return (
    <div className="stack">
      <div className="row gap">
        <Button variant="primary" busy={run.isPending} onClick={() => run.mutate()}>
          {t("runAnalysis")}
        </Button>
      </div>
      <ErrorBox error={run.error || q.error} />
      {q.isLoading ? (
        <Loading />
      ) : !d?.summary ? (
        <p className="muted">{t("noOpps")}</p>
      ) : (
        <>
          <Card title={t("summary")}>
            <div className="stats">
              <div className="stat">
                <span className="stat-label">{t("avoidableSpend")}</span>
                <Money v={d.summary.avoidable_monthly_toman} big suffix={t("perMonth")} />
              </div>
              <div className="stat">
                <span className="stat-label">{t("savingPct")}</span>
                <span className="money-big">
                  <Pct v={d.summary.potential_saving_percent} />
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">{t("counts")}</span>
                <span>
                  {t("actionable")}: <Num v={d.summary.actionable_count} /> · {t("needMoreData")}: <Num v={d.summary.cannot_determine_count} />
                </span>
              </div>
            </div>
            <p className="small muted">{t("savingMethod")}</p>
          </Card>

          {groups.actionable.length > 1 && (
            <Card title={t("savingsChart")}>
              <RankedBars
                caption={t("savingsChart")}
                rows={groups.actionable.map((r) => ({
                  key: r.id,
                  label: recTitle(r, lang),
                  tipLabel: `${recTitle(r, lang)} · ${r.resource_name ?? ""}`,
                  sub: r.resource_name,
                  value: r.monthly_saving_toman,
                  emphasis: counted.has(r.key),
                }))}
              />
            </Card>
          )}

          {groups.actionable.length > 0 && <h2>{t("actionable")}</h2>}
          {groups.actionable.map((r) => (
            <OppCard key={r.id} r={r} />
          ))}

          {groups.informational.length > 0 && (
            <>
              <h2>{t("informational")}</h2>
              {groups.informational.map((r) => (
                <OppCard key={r.id} r={r} />
              ))}
            </>
          )}

          {groups.cannot.length > 0 && (
            <Card title={t("needMoreData")} className="card-warn">
              <ul className="plain">
                {groups.cannot.map((r) => (
                  <Needed key={r.id} r={r} />
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

export function OpportunitiesPage() {
  const { t } = useI18n();
  return (
    <div className="stack">
      <h1>{t("navOpportunities")}</h1>
      <ConfirmedInventory>{(inv) => <OppsInner key={inv.id} inv={inv} />}</ConfirmedInventory>
    </div>
  );
}
