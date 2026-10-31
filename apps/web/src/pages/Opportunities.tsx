import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ComponentLine, ConstraintResult, Difference, InventoryView, Recommendation } from "../api/types";
import { useI18n } from "../lib/i18n";
import { ConfirmedInventory } from "../components/Guard";
import { Badge, Button, Card, Drawer, ErrorBox, LinesTable, Loading, Money, Num, Pct, ToneBadge } from "../components/ui";
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

export function show(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function ConstraintsList({ items }: { items: ConstraintResult[] }) {
  return (
    <ul className="plain small">
      {items.map((c) => (
        <li key={c.constraint_id}>
          <Badge tone={c.passed ? "good" : "bad"}>{c.passed ? "✓" : "✗"}</Badge> <code dir="ltr">{c.constraint_id}</code> <span dir="ltr">{c.detail}</span>
        </li>
      ))}
    </ul>
  );
}

function DifferencesTable({ items }: { items: Difference[] }) {
  const { t } = useI18n();
  return (
    <div className="table-wrap">
      <table className="table compact">
        <thead>
          <tr>
            <th>{t("dimension")}</th>
            <th>{t("current")}</th>
            <th>{t("candidateLines")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((d) => (
            <tr key={d.dimension}>
              <td dir="ltr">{d.dimension}</td>
              <td dir="ltr">{show(d.source_value)}</td>
              <td dir="ltr">{show(d.candidate_value)}</td>
              <td>
                <VerdictBadge v={d.verdict} />
                {d.note ? <div className="note">{d.note}</div> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const STRUCTURED = new Set(["current", "candidate", "constraints", "differences"]);

function Evidence({ r }: { r: Recommendation }) {
  const { t } = useI18n();
  const e = r.evidence;
  const rest = Object.entries(e).filter(([k]) => !STRUCTURED.has(k));
  return (
    <div className="stack">
      {e.constraints && (
        <>
          <h4>{t("constraints")}</h4>
          <ConstraintsList items={e.constraints} />
        </>
      )}
      {e.differences && (
        <>
          <h4>{t("differences")}</h4>
          <DifferencesTable items={e.differences} />
        </>
      )}
      {e.current && (
        <>
          <h4>
            {t("currentLines")} — <Money v={e.current.monthly_total_toman ?? null} />
          </h4>
          <LinesTable lines={e.current.components as ComponentLine[]} />
        </>
      )}
      {e.candidate && (
        <>
          <h4>
            {t("candidateLines")} {e.candidate_label ? `(${e.candidate_label})` : ""} — <Money v={e.candidate.monthly_total_toman ?? null} />
          </h4>
          <LinesTable lines={e.candidate.components as ComponentLine[]} />
        </>
      )}
      {r.price_dates.length > 0 && (
        <>
          <h4>{t("priceDates")}</h4>
          <ul className="plain small" dir="ltr">
            {r.price_dates.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </>
      )}
      {rest.length > 0 && (
        <>
          <h4>{t("otherEvidence")}</h4>
          <dl className="kv small">
            {rest.map(([k, v]) => (
              <div key={k} className="kv-row">
                <dt dir="ltr">{k}</dt>
                <dd>
                  <code className="pre" dir="ltr">
                    {typeof v === "object" ? JSON.stringify(v, null, 1) : show(v)}
                  </code>
                </dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </div>
  );
}

function Plan({ id }: { id: string }) {
  const { t, pick } = useI18n();
  const q = useQuery({ queryKey: ["rec", id], queryFn: () => api.rec(id) });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  const r = q.data!;
  return (
    <div className="stack">
      <p>{pick(r.summary_fa, r.summary_en)}</p>
      <dl className="kv">
        <dt>{t("affectedResource")}</dt>
        <dd>{r.resource_name ?? "—"}</dd>
        <dt>{t("currentCost")}</dt>
        <dd>
          <Money v={r.current_cost_toman} />
        </dd>
        <dt>{t("candidateCost")}</dt>
        <dd>
          <Money v={r.candidate_cost_toman} />
        </dd>
        <dt>{t("savingMonth")}</dt>
        <dd>
          <Money v={r.monthly_saving_toman} /> (<Pct v={r.monthly_saving_percent} />)
        </dd>
        {r.one_time_migration_cost_toman !== null && (
          <>
            <dt>{t("migrationCost")}</dt>
            <dd>
              <Money v={r.one_time_migration_cost_toman} />
            </dd>
          </>
        )}
        {(r.payback_months !== null || r.payback_status) && (
          <>
            <dt>{t("payback")}</dt>
            <dd>
              <Num v={r.payback_months} /> <small className="muted">{r.payback_status}</small>
            </dd>
          </>
        )}
        <dt>{t("risk")}</dt>
        <dd>
          <ToneBadge kind="risk" value={r.risk_level} />
        </dd>
        <dt>{t("effort")}</dt>
        <dd>
          <ToneBadge kind="effort" value={r.effort_level} />
        </dd>
        <dt>{t("confidence")}</dt>
        <dd>
          <ToneBadge kind="confidence" value={r.confidence} />
        </dd>
        <dt>Rule</dt>
        <dd dir="ltr">
          {r.rule_id} · {r.recommendation_type} · {r.status}
        </dd>
      </dl>
      {r.missing_inputs.length > 0 && (
        <>
          <h4>{t("missingInputs")}</h4>
          <ul dir="ltr">
            {r.missing_inputs.map((m) => (
              <li key={m}>
                <code>{m}</code>
              </li>
            ))}
          </ul>
        </>
      )}
      <Evidence r={r} />
    </div>
  );
}

function OppCard({ r, counted, onPlan }: { r: Recommendation; counted: boolean; onPlan: () => void }) {
  const { t, pick } = useI18n();
  return (
    <article className="opp">
      <header className="row between wrap">
        <h3>{pick(r.title_fa, r.title_en)}</h3>
        {r.monthly_saving_toman !== null && <Money v={r.monthly_saving_toman} big suffix={t("perMonth")} />}
      </header>
      <div className="row gap wrap small">
        <span>
          {t("affectedResource")}: <strong>{r.resource_name ?? "—"}</strong>
        </span>
        {r.monthly_saving_percent && (
          <span>
            <Pct v={r.monthly_saving_percent} />
          </span>
        )}
        <span>
          {t("risk")} <ToneBadge kind="risk" value={r.risk_level} />
        </span>
        <span>
          {t("effort")} <ToneBadge kind="effort" value={r.effort_level} />
        </span>
        <span>
          {t("confidence")} <ToneBadge kind="confidence" value={r.confidence} />
        </span>
        {counted && <Badge tone="info">Σ</Badge>}
      </div>
      {r.current_cost_toman !== null && r.candidate_cost_toman !== null && (
        <BeforeAfter current={r.current_cost_toman} after={r.candidate_cost_toman} saving={r.monthly_saving_toman} />
      )}
      <p className="small">{pick(r.summary_fa, r.summary_en)}</p>
      <details>
        <summary>{t("evidence")}</summary>
        <Evidence r={r} />
      </details>
      <div className="row gap">
        <Button onClick={onPlan}>{t("viewPlan")}</Button>
      </div>
    </article>
  );
}

function OppsInner({ inv }: { inv: InventoryView }) {
  const { t, pick } = useI18n();
  const qc = useQueryClient();
  const [plan, setPlan] = useState<Recommendation | null>(null);
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
                  {t("actionable")}: <Num v={d.summary.actionable_count} /> · {t("cannotDetermine")}: <Num v={d.summary.cannot_determine_count} />
                </span>
              </div>
            </div>
            <p className="small">
              <strong>{t("method")}:</strong> {d.summary.method} <Badge tone="info">Σ</Badge>
            </p>
          </Card>

          {groups.actionable.length > 0 && (
            <Card title={t("savingsChart")}>
              <RankedBars
                caption={t("savingsChart")}
                rows={groups.actionable.map((r) => ({
                  key: r.id,
                  label: pick(r.title_fa, r.title_en),
                  tipLabel: `${pick(r.title_fa, r.title_en)} · ${r.resource_name ?? ""}`,
                  sub: r.resource_name,
                  value: r.monthly_saving_toman,
                  emphasis: counted.has(r.key),
                  trailing: counted.has(r.key) ? <Badge tone="info">Σ</Badge> : undefined,
                }))}
              />
              <p className="muted small">
                <Badge tone="info">Σ</Badge> {t("method")}: {d.summary.method}
              </p>
            </Card>
          )}

          <h2>{t("actionable")}</h2>
          {groups.actionable.map((r) => (
            <OppCard key={r.id} r={r} counted={counted.has(r.key)} onPlan={() => setPlan(r)} />
          ))}

          {groups.informational.length > 0 && (
            <>
              <h2>{t("informational")}</h2>
              {groups.informational.map((r) => (
                <OppCard key={r.id} r={r} counted={false} onPlan={() => setPlan(r)} />
              ))}
            </>
          )}

          {groups.cannot.length > 0 && (
            <Card title={t("cannotDetermine")} className="card-warn">
              <ul className="plain">
                {groups.cannot.map((r) => (
                  <li key={r.id} className="cannot">
                    <strong>{r.resource_name ?? "—"}</strong> — {pick(r.summary_fa, r.summary_en)}
                    <div className="chips" dir="ltr">
                      {r.missing_inputs.map((m) => (
                        <code key={m} className="chip">
                          {m}
                        </code>
                      ))}
                    </div>
                    <Button variant="ghost" onClick={() => setPlan(r)}>
                      {t("viewPlan")}
                    </Button>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <p className="muted small" dir="ltr">
            analysis {d.analysis_id} · quote {d.quote_id}
          </p>
        </>
      )}
      <Drawer open={!!plan} onClose={() => setPlan(null)} title={plan ? pick(plan.title_fa, plan.title_en) : ""} wide>
        {plan && <Plan id={plan.id} />}
      </Drawer>
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
