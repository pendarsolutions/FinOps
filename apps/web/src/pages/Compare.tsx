import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api/client";
import type { CompareResult, InventoryView } from "../api/types";
import { useI18n } from "../lib/i18n";
import { ConfirmedInventory } from "../components/Guard";
import { Badge, Button, Card, ErrorBox, Money, Num, Pct, StatusChip } from "../components/ui";
import { RankedBars } from "../components/viz";
import { visualShare } from "../lib/money";
import { ConstraintsList, VerdictBadge, show } from "./Opportunities";

function Matrix({ r }: { r: CompareResult }) {
  const { t } = useI18n();
  const dims: string[] = [];
  r.candidates.forEach((c) => c.differences.forEach((d) => !dims.includes(d.dimension) && dims.push(d.dimension)));
  const srcOf = (dim: string) => r.candidates.flatMap((c) => c.differences).find((d) => d.dimension === dim)?.source_value;
  const current = r.candidates[0]?.current;
  // index of the cheapest exact candidate (comparison only; no arithmetic on the amounts)
  let cheapest = -1;
  r.candidates.forEach((c, i) => {
    const v = c.candidate.monthly_total_toman;
    if (v === null || !c.exact) return;
    const best = cheapest >= 0 ? r.candidates[cheapest].candidate.monthly_total_toman : null;
    if (best === null || visualShare(v, best) < 1) cheapest = i;
  });

  return (
    <Card
      title={
        <>
          {r.resource_name}{" "}
          <small className="muted" dir="ltr">
            {show(r.source_specs.provider_id)} · {show(r.source_specs.sku ?? r.source_specs.service_type)}
          </small>
        </>
      }
    >
      {r.notes.length > 0 && (
        <ul className="plain small muted">
          {r.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
      {r.candidates.length === 0 ? (
        <p className="alert alert-warn">{t("noCandidates")}</p>
      ) : (
        <>
        <RankedBars
          caption={t("costCompareChart")}
          rows={[
            { key: "__current", label: <strong>{t("current")}</strong>, tipLabel: t("current"), value: current?.monthly_total_toman ?? null, emphasis: true },
            ...r.candidates.map((c, i) => ({
              key: String(i),
              label: <span dir="ltr">{c.candidate_label}</span>,
              tipLabel: c.candidate_label,
              sub: c.confidence === "NEEDS_HUMAN_REVIEW" ? t("needsHumanReview") : c.confidence,
              value: c.candidate.monthly_total_toman,
              trailing: i === cheapest ? <StatusChip tone="good" label={t("cheapest")} /> : undefined,
            })),
          ]}
        />
        <div className="table-wrap matrix-wrap">
          <table className="table matrix">
            <caption className="sr-only">
              {t("navCompare")}: {r.resource_name}
            </caption>
            <thead>
              <tr>
                <th scope="col">{t("dimension")}</th>
                <th scope="col" className="col-current">
                  {t("current")}
                </th>
                {r.candidates.map((c, i) => (
                  <th scope="col" key={i} className={i === cheapest ? "col-best" : undefined} dir="ltr">
                    {c.candidate_label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">{t("confidence")}</th>
                <td className="col-current">—</td>
                {r.candidates.map((c, i) => (
                  <td key={i}>
                    {c.confidence === "NEEDS_HUMAN_REVIEW" ? (
                      <Badge tone="warn">⚠ {t("needsHumanReview")}</Badge>
                    ) : (
                      <Badge tone={c.confidence === "high" ? "good" : c.confidence === "medium" ? "info" : "bad"}>{c.confidence}</Badge>
                    )}
                  </td>
                ))}
              </tr>
              <tr>
                <th scope="row">{t("fitScore")}</th>
                <td className="col-current">—</td>
                {r.candidates.map((c, i) => (
                  <td key={i} title={Object.entries(c.score_breakdown).map(([k, v]) => `${k}: ${v}`).join("\n")}>
                    <Num v={c.fit_score} max={4} />
                  </td>
                ))}
              </tr>
              <tr>
                <th scope="row">{t("cost")}</th>
                <td className="col-current">
                  <Money v={current?.monthly_total_toman ?? null} />
                </td>
                {r.candidates.map((c, i) => (
                  <td key={i} className={`num-col ${i === cheapest ? "col-best" : ""}`}>
                    <Money v={c.candidate.monthly_total_toman} />
                    {!c.exact && <Badge tone="warn">{t("notExact")}</Badge>}
                  </td>
                ))}
              </tr>
              <tr>
                <th scope="row">{t("saving")}</th>
                <td className="col-current">—</td>
                {r.candidates.map((c, i) => (
                  <td key={i}>
                    <Money v={c.monthly_saving_toman} /> <small>(<Pct v={c.monthly_saving_percent} />)</small>
                  </td>
                ))}
              </tr>
              {dims.map((dim) => (
                <tr key={dim}>
                  <th scope="row" dir="ltr">
                    {dim}
                  </th>
                  <td className="col-current" dir="ltr">
                    {show(srcOf(dim))}
                  </td>
                  {r.candidates.map((c, i) => {
                    const d = c.differences.find((x) => x.dimension === dim);
                    return (
                      <td key={i} className={d ? `v-${d.verdict}` : undefined} title={d?.note ?? undefined}>
                        {d ? (
                          <>
                            <span dir="ltr">{show(d.candidate_value)}</span> <VerdictBadge v={d.verdict} />
                            {d.note ? <div className="note">{d.note}</div> : null}
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr>
                <th scope="row">{t("assumptions")}</th>
                <td className="col-current" />
                {r.candidates.map((c, i) => (
                  <td key={i} className="small">
                    <details>
                      <summary>
                        {t("constraints")} / {t("assumptions")}
                      </summary>
                      <ConstraintsList items={c.constraints} />
                      <ul className="assumptions">
                        {c.assumptions.map((a, j) => (
                          <li key={j}>{a}</li>
                        ))}
                      </ul>
                    </details>
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
        </>
      )}
      {r.rejected.length > 0 && (
        <details className="rejected">
          <summary>
            {t("rejected")} ({r.rejected.length})
          </summary>
          <ul className="plain">
            {r.rejected.map((x, i) => (
              <li key={i}>
                <strong dir="ltr">{x.label}</strong>
                <ConstraintsList items={x.failed_constraints} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}

function CompareInner({ inv }: { inv: InventoryView }) {
  const { t } = useI18n();
  const [outside, setOutside] = useState(false);
  const [rid, setRid] = useState("");
  const m = useMutation({ mutationFn: () => api.compare(inv.id, outside, rid ? [rid] : undefined) });
  return (
    <div className="stack">
      <p className="muted">{t("compareIntro")}</p>
      <div className="row gap wrap">
        <label className="toggle">
          <input type="checkbox" checked={outside} onChange={(e) => setOutside(e.target.checked)} /> {t("allowOutsideIran")}
        </label>
        <label className="sr-only" htmlFor="cmp-res">
          {t("colResource")}
        </label>
        <select id="cmp-res" value={rid} onChange={(e) => setRid(e.target.value)}>
          <option value="">{t("allResources")}</option>
          {inv.resources.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
        <Button variant="primary" busy={m.isPending} onClick={() => m.mutate()}>
          {t("compare")}
        </Button>
      </div>
      <ErrorBox error={m.error} />
      {m.data && (
        <>
          <p className="muted small" dir="ltr">
            {t("catalogVersion")} {m.data.catalog_version} · allow_outside_iran={String(m.data.allow_outside_iran)}
          </p>
          {m.data.results.map((r) => (
            <Matrix key={r.resource_id} r={r} />
          ))}
        </>
      )}
    </div>
  );
}

export function ComparePage() {
  const { t } = useI18n();
  return (
    <div className="stack">
      <h1>{t("navCompare")}</h1>
      <ConfirmedInventory>{(inv) => <CompareInner key={inv.id} inv={inv} />}</ConfirmedInventory>
    </div>
  );
}
