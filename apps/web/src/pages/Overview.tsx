import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { environmentColor, providerColor } from "../lib/viz";
import { PartMeter, RankedBars, ShareBar } from "../components/viz";
import { useI18n } from "../lib/i18n";
import { useProviderName } from "../lib/hooks";
import { useSession } from "../lib/session";
import { Badge, Button, Card, Date_, Empty, ErrorBox, FreshnessBadge, Loading, Money, Num, Pct, PriceUnavailableBadge, ToneBadge } from "../components/ui";
import { HandoffNote } from "./Opportunities";

export function EmptyWorkspace() {
  const { t } = useI18n();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { setActiveId } = useSession();
  const demo = useMutation({
    mutationFn: api.createDemo,
    onSuccess: (v) => {
      qc.setQueryData(["inventory", v.id], v);
      qc.invalidateQueries({ queryKey: ["inventories"] });
      setActiveId(v.id);
      nav("/infrastructure?tab=review");
    },
  });
  return (
    <Card>
      <Empty>
        <h2>{t("emptyTitle")}</h2>
        <p className="muted">{t("emptyBody")}</p>
        <div className="row gap wrap center">
          <Button variant="primary" busy={demo.isPending} onClick={() => demo.mutate()}>
            {t("loadDemo")}
          </Button>
          <Button onClick={() => nav("/infrastructure?tab=chat")}>{t("describeChat")}</Button>
          <Button onClick={() => nav("/infrastructure?tab=invoice")}>{t("uploadInvoice")}</Button>
          <Button onClick={() => nav("/infrastructure?tab=builder")}>{t("guidedBuilder")}</Button>
        </div>
        <ErrorBox error={demo.error} />
      </Empty>
    </Card>
  );
}

export function OverviewPage() {
  const { t, lang, pick } = useI18n();
  const { activeId, inventories, inventoriesLoading } = useSession();
  const pname = useProviderName();
  const qc = useQueryClient();
  const ov = useQuery({ queryKey: ["overview", activeId], queryFn: () => api.overview(activeId!), enabled: !!activeId });
  const run = useMutation({
    mutationFn: () => api.runRecs(activeId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["overview", activeId] });
      qc.invalidateQueries({ queryKey: ["recs", activeId] });
      qc.invalidateQueries({ queryKey: ["quotes", activeId] });
    },
  });

  if (inventoriesLoading) return <Loading />;
  if (!inventories?.length || !activeId)
    return (
      <>
        <h1>{t("navOverview")}</h1>
        <EmptyWorkspace />
      </>
    );
  if (ov.isLoading) return <Loading />;
  if (ov.error) return <ErrorBox error={ov.error} onRetry={() => ov.refetch()} />;
  const d = ov.data!;
  const confirmed = d.inventory.status === "confirmed";

  return (
    <div className="stack">
      <div className="row between wrap">
        <h1>
          {t("navOverview")} — {d.inventory.name}
        </h1>
        {confirmed && (
          <Button variant="primary" busy={run.isPending} onClick={() => run.mutate()}>
            {t("runAnalysis")}
          </Button>
        )}
      </div>
      <ErrorBox error={run.error} />
      {!confirmed && (
        <div className="alert alert-warn">
          {t("notConfirmed")} <Link to="/infrastructure?tab=review">{t("goReview")}</Link>
        </div>
      )}
      {confirmed && !d.quote && <div className="alert alert-info">{t("noAnalysis")}</div>}

      <div className="stats stats-hero">
        <div className="stat stat-hero">
          <span className="stat-label">{t("currentSpend")}</span>
          {d.quote ? (
            d.quote.total_toman !== null ? (
              <Money v={d.quote.total_toman} big suffix={t("perMonth")} />
            ) : (
              <>
                <PriceUnavailableBadge />
                <small>
                  {t("incompleteQuote")} <Money v={d.quote.priced_subtotal_toman} />
                </small>
              </>
            )
          ) : (
            <span className="muted">—</span>
          )}
        </div>
        <div className="stat">
          <span className="stat-label">{t("avoidableSpend")}</span>
          {d.summary ? <Money v={d.summary.avoidable_monthly_toman} big suffix={t("perMonth")} /> : <span className="muted">—</span>}
          {d.summary && d.quote?.total_toman ? (
            <PartMeter part={d.summary.avoidable_monthly_toman} whole={d.quote.total_toman} label={t("avoidableOfCurrent")} />
          ) : null}
        </div>
        <div className="stat">
          <span className="stat-label">{t("savingPct")}</span>
          <span className="money-big">
            <Pct v={d.summary?.potential_saving_percent} />
          </span>
          <small className="muted">{t("avoidableOfCurrent")}</small>
        </div>
      </div>
      {d.summary && <p className="muted small">{d.summary.method}</p>}

      <div className="grid2">
        <Card title={t("providerDist")}>
          {d.provider_distribution.length ? (
            <ShareBar
              caption={t("providerDist")}
              total={d.quote?.total_toman ?? d.quote?.priced_subtotal_toman}
              items={d.provider_distribution.map((r) => ({
                key: r.provider_id,
                label: pname(r.provider_id, lang),
                value: r.monthly_toman,
                color: providerColor(r.provider_id).css,
              }))}
            />
          ) : (
            <p className="muted">—</p>
          )}
        </Card>
        <Card title={t("envDist")}>
          {d.environment_distribution.length ? (
            <ShareBar
              caption={t("envDist")}
              total={d.quote?.total_toman ?? d.quote?.priced_subtotal_toman}
              items={d.environment_distribution.map((r) => ({
                key: r.environment,
                label: r.environment,
                value: r.monthly_toman,
                color: environmentColor(r.environment).css,
              }))}
            />
          ) : (
            <p className="muted">—</p>
          )}
        </Card>
      </div>

      {d.unavailable.length > 0 && (
        <Card title={t("unavailableList")}>
          <ul>
            {d.unavailable.map((u, i) => (
              <li key={i}>
                <PriceUnavailableBadge /> {u.component} — {u.reason}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title={t("topOpps")} actions={<Link to="/opportunities">{t("viewAll")}</Link>}>
        {d.top_opportunities.length ? (
          <RankedBars
            caption={t("savingsChart")}
            rows={d.top_opportunities.map((r) => ({
              key: r.id,
              label: pick(r.title_fa, r.title_en),
              tipLabel: `${pick(r.title_fa, r.title_en)} · ${r.resource_name ?? ""}`,
              sub: r.resource_name,
              value: r.monthly_saving_toman,
              trailing: (
                <span className="rank-badges">
                  <small className="muted">{t("risk")}</small>
                  <ToneBadge kind="risk" value={r.risk_level} />
                  <small className="muted">{t("confidence")}</small>
                  <ToneBadge kind="confidence" value={r.confidence} />
                </span>
              ),
            }))}
          />
        ) : (
          <p className="muted">{t("noOpps")}</p>
        )}
      </Card>

      <Card title={t("priceFreshness")} actions={<small className="muted" dir="ltr">{d.catalog_version}</small>}>
        <div className="table-wrap">
          <table className="table compact">
            <thead>
              <tr>
                <th>{t("colProvider")}</th>
                <th>{t("source")}</th>
                <th>{t("retrieved")}</th>
                <th>{t("providerPriceDate")}</th>
                <th>{t("ageDays")}</th>
                <th>{t("freshness")}</th>
              </tr>
            </thead>
            <tbody>
              {d.price_freshness.map((s) => (
                <tr key={s.provider_id + s.source_url}>
                  <td>{pname(s.provider_id, lang)}</td>
                  <td>
                    {s.source_url ? (
                      <a href={s.source_url} target="_blank" rel="noreferrer noopener" dir="ltr" className="ellipsis">
                        {s.source_url.replace(/^https?:\/\//, "")}
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    <Date_ v={s.retrieved_at} />
                  </td>
                  <td>
                    <Date_ v={s.provider_price_date} />
                  </td>
                  <td>
                    <Num v={s.age_days} />
                  </td>
                  <td>
                    <FreshnessBadge f={s.freshness} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {d.summary?.pendar_handoff && <HandoffNote h={d.summary.pendar_handoff} />}
      {d.quote && (
        <p className="muted small" dir="ltr">
          quote {d.quote.id} · {d.quote.catalog_version} · {d.quote.engine_version} <Badge>{d.quote.complete ? t("complete") : t("incomplete")}</Badge>
        </p>
      )}
    </div>
  );
}
