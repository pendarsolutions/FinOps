import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { InventoryView, QuoteView } from "../api/types";
import { useI18n } from "../lib/i18n";
import { useProviderName } from "../lib/hooks";
import { formatDecimal, visualShare } from "../lib/money";
import { providerColor } from "../lib/viz";
import { ConfirmedInventory } from "../components/Guard";
import { RankedBars, ShareBar } from "../components/viz";
import { Rec, RecList } from "../components/records";
import { Button, Card, Date_, ErrorBox, LineStatusBadge, Loading, Money, Num, PriceUnavailableBadge, SourceInfo, StatusChip, freshnessFor } from "../components/ui";

/** One grouped table: a summary row per resource (click to expand), component lines nested beneath. */
function BreakdownTable({ q }: { q: QuoteView }) {
  const { t, lang } = useI18n();
  const pname = useProviderName();
  const c = q.content;
  const [open, setOpen] = useState<Set<string>>(() => new Set(c.breakdowns.filter((b) => b.status !== "EXACT").map((b) => b.resource_id)));
  const toggle = (id: string) =>
    setOpen((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const allOpen = open.size === c.breakdowns.length;
  return (
    <Card
      title={t("breakdown")}
      actions={
        <Button variant="ghost" onClick={() => setOpen(allOpen ? new Set() : new Set(c.breakdowns.map((b) => b.resource_id)))}>
          {allOpen ? t("collapseAll") : t("expandAll")}
        </Button>
      }
    >
      <div className="table-wrap">
        <table className="table grouped">
          <thead>
            <tr>
              <th>{t("component")}</th>
              <th>{t("lineStatus")}</th>
              <th className="num-col">{t("quantity")}</th>
              <th className="num-col">{t("unitPrice")}</th>
              <th className="num-col">{t("subtotal")}</th>
              <th>{t("source")}</th>
            </tr>
          </thead>
          {c.breakdowns.map((b) => {
            const isOpen = open.has(b.resource_id);
            const lines = [...b.components, ...b.tax_lines];
            return (
              <tbody key={b.resource_id} className={isOpen ? "group open" : "group"}>
                <tr className="group-head" onClick={() => toggle(b.resource_id)}>
                  <th scope="rowgroup" colSpan={2}>
                    <button type="button" className="disclosure" aria-expanded={isOpen} onClick={(e) => (e.stopPropagation(), toggle(b.resource_id))}>
                      <span className="chev" aria-hidden>
                        ▸
                      </span>
                      <i className="swatch" style={{ background: providerColor(b.provider_id).css }} aria-hidden />
                      <strong>{b.resource_name}</strong>
                    </button>
                    <small className="muted">
                      {" "}
                      {pname(b.provider_id, lang)} · {lines.length} {t("componentsCount")}
                    </small>{" "}
                    {b.status === "EXACT" ? null : <StatusChip tone={b.status === "PRICE_UNAVAILABLE" ? "bad" : "warn"} label={b.status} />}
                  </th>
                  <td className="num-col">
                    ×<Num v={b.quantity} />
                  </td>
                  <td />
                  <td className="num-col strong">{b.monthly_total_toman !== null ? <Money v={b.monthly_total_toman} /> : <PriceUnavailableBadge />}</td>
                  <td />
                </tr>
                {isOpen &&
                  lines.map((l, i) => (
                    <tr key={`${l.code}-${i}`} className={`line line-${l.status}`}>
                      <td>
                        <div className="bidi">{l.description}</div>
                        <small className="muted code" dir="ltr">
                          {l.code}
                        </small>
                        {l.note ? <div className="note">{l.note}</div> : null}
                      </td>
                      <td>
                        <LineStatusBadge s={l.status} />
                      </td>
                      <td className="num-col">
                        <Num v={l.quantity} /> <small className="muted">{l.unit}</small>
                      </td>
                      <td className="num-col">{l.unit_price_toman !== null ? <Money v={l.unit_price_toman} /> : <span className="muted">—</span>}</td>
                      <td className="num-col">
                        {l.status === "unavailable" ? <PriceUnavailableBadge /> : l.subtotal_toman !== null ? <Money v={l.subtotal_toman} /> : <span className="muted">—</span>}
                      </td>
                      <td>
                        <SourceInfo url={l.source_url} retrieved={l.retrieved_at} priceDate={l.price_date} freshness={freshnessFor(c.price_sources, l.source_url)} compact />
                      </td>
                    </tr>
                  ))}
                {isOpen && b.unavailable.length > 0 && (
                  <tr className="line">
                    <td colSpan={6}>
                      {b.unavailable.map((u, i) => (
                        <div key={i} className="small">
                          <PriceUnavailableBadge /> {u.component}: {u.reason}
                        </div>
                      ))}
                      {b.monthly_total_toman === null && (
                        <div className="small">
                          {t("pricedSubtotal")}: <Money v={b.priced_subtotal_toman} />
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </tbody>
            );
          })}
          <tfoot>
            <tr>
              <th colSpan={4}>{t("total")}</th>
              <td className="num-col strong">{c.total_toman !== null ? <Money v={c.total_toman} /> : <PriceUnavailableBadge />}</td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  );
}

function QuoteDetail({ q }: { q: QuoteView }) {
  const { t, lang } = useI18n();
  const pname = useProviderName();
  const c = q.content;
  return (
    <div className="stack">
      <div className="stats">
        <div className="stat">
          <span className="stat-label">{t("total")}</span>
          <Money v={c.total_toman} big suffix={t("perMonth")} />
          {c.total_rial ? (
            <small className="muted">
              = {formatDecimal(c.total_rial, lang)} {t("rial")}
            </small>
          ) : null}
        </div>
        <div className="stat">
          <span className="stat-label">{t("pricedSubtotal")}</span>
          <Money v={c.priced_subtotal_toman} big />
        </div>
        {q.include_tax && (
          <div className="stat">
            <span className="stat-label">{t("tax")}</span>
            <Money v={c.total_tax_toman} big />
          </div>
        )}
      </div>
      <p className="muted small" dir="ltr">
        quote {q.id} · {t("catalogVersion")} {c.catalog_version} · {t("engineVersion")} {c.engine_version} · {t("policyVersion")} {c.policy_version} · hash {c.content_hash.slice(0, 12)}
      </p>

      {c.unavailable.length > 0 && (
        <Card title={t("unavailableList")} className="card-bad">
          <ul>
            {c.unavailable.map((u, i) => (
              <li key={i}>
                <PriceUnavailableBadge /> <strong>{u.component}</strong> — {u.reason} <small className="muted">({u.missing_field})</small>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid2">
        <Card title={t("costByResource")}>
          <RankedBars
            caption={t("costByResource")}
            rows={[...c.breakdowns]
              .sort((a, b) => visualShare(b.monthly_total_toman ?? b.priced_subtotal_toman, c.priced_subtotal_toman) - visualShare(a.monthly_total_toman ?? a.priced_subtotal_toman, c.priced_subtotal_toman))
              .map((b) => ({
                key: b.resource_id,
                label: b.resource_name,
                tipLabel: `${b.resource_name} · ${pname(b.provider_id, lang)}`,
                sub: (
                  <>
                    <i className="swatch" style={{ background: providerColor(b.provider_id).css }} aria-hidden /> {pname(b.provider_id, lang)} · ×
                    {formatDecimal(b.quantity, lang)}
                  </>
                ),
                value: b.monthly_total_toman,
                color: providerColor(b.provider_id).css,
              }))}
          />
        </Card>
        <Card title={t("costByProvider")}>
          <ShareBar
            caption={t("costByProvider")}
            total={c.priced_subtotal_toman}
            items={c.provider_totals.map((p) => ({
              key: p.provider_id,
              label: pname(p.provider_id, lang),
              value: p.monthly_total_toman ?? p.priced_subtotal_toman,
              color: providerColor(p.provider_id).css,
              sub: p.complete ? undefined : <StatusChip tone="bad" label={t("incomplete")} />,
            }))}
          />
        </Card>
      </div>

      <BreakdownTable q={q} />

      <Card title={t("assumptions")}>
        {c.assumptions.length ? (
          <ul className="assumptions">
            {c.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">—</p>
        )}
      </Card>

      <Card title={t("priceFreshness")}>
        <ul className="plain">
          {c.price_sources.map((s) => (
            <li key={s.provider_id + s.source_url} className="row gap wrap">
              <strong>{pname(s.provider_id, lang)}</strong>
              <SourceInfo url={s.source_url} retrieved={s.retrieved_at} priceDate={s.provider_price_date} freshness={s.freshness} />
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function CostsInner({ inv }: { inv: InventoryView }) {
  const { t } = useI18n();
  const qc = useQueryClient();
  const [includeTax, setIncludeTax] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const quotes = useQuery({ queryKey: ["quotes", inv.id], queryFn: () => api.quotes(inv.id) });
  useEffect(() => {
    if (!selected && quotes.data?.length) setSelected(quotes.data[0].id);
  }, [quotes.data, selected]);
  const detail = useQuery({ queryKey: ["quote", selected], queryFn: () => api.getQuote(selected!), enabled: !!selected });
  const run = useMutation({
    mutationFn: () => api.quote(inv.id, includeTax),
    onSuccess: (q) => {
      qc.setQueryData(["quote", q.id], q);
      qc.invalidateQueries({ queryKey: ["quotes", inv.id] });
      qc.invalidateQueries({ queryKey: ["overview", inv.id] });
      setSelected(q.id);
    },
  });

  return (
    <div className="stack">
      <div className="row gap wrap">
        <label className="toggle">
          <input type="checkbox" checked={includeTax} onChange={(e) => setIncludeTax(e.target.checked)} /> {t("includeTax")}
        </label>
        <Button variant="primary" busy={run.isPending} onClick={() => run.mutate()}>
          {t("calcQuote")}
        </Button>
      </div>
      <ErrorBox error={run.error} />
      {detail.isLoading ? <Loading /> : detail.error ? <ErrorBox error={detail.error} /> : detail.data ? <QuoteDetail q={detail.data} /> : <p className="muted">{t("noQuote")}</p>}

      <Card title={t("previousQuotes")}>
        {quotes.isLoading ? (
          <Loading />
        ) : (
          <RecList label={t("previousQuotes")}>
            {quotes.data?.map((q) => (
              <Rec
                key={q.id}
                selected={q.id === selected}
                tone={q.complete ? undefined : "bad"}
                icon={<span aria-hidden>Σ</span>}
                title={<Money v={q.total_toman} />}
                meta={
                  <>
                    <Date_ v={q.created_at} />
                    <span>
                      {t("includeTax")}: {q.include_tax ? t("yes") : t("no")}
                    </span>
                    <span>
                      {t("catalogVersion")}: <bdi dir="ltr">{q.catalog_version}</bdi>
                    </span>
                  </>
                }
                aside={
                  <>
                    <StatusChip tone={q.complete ? "good" : "bad"} label={q.complete ? t("complete") : t("incomplete")} />
                    <Button variant={q.id === selected ? "primary" : "secondary"} onClick={() => setSelected(q.id)} aria-pressed={q.id === selected}>
                      {t("open")}
                    </Button>
                  </>
                }
              />
            ))}
          </RecList>
        )}
      </Card>
    </div>
  );
}

export function CostsPage() {
  const { t } = useI18n();
  return (
    <div className="stack">
      <h1>{t("navCosts")}</h1>
      <ConfirmedInventory>{(inv) => <CostsInner key={inv.id} inv={inv} />}</ConfirmedInventory>
    </div>
  );
}
