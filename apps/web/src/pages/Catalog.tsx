import { useDeferredValue, useEffect, useMemo, useState, type CSSProperties } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { CatalogItem, ProviderInfo } from "../api/types";
import { useI18n, type TKey } from "../lib/i18n";
import { useProviders } from "../lib/hooks";
import { compareDecimal } from "../lib/money";
import { providerColor } from "../lib/viz";
import { Badge, Card, Date_, Drawer, ErrorBox, FreshnessBadge, Loading, Money, Num, StatusChip } from "../components/ui";
import { Initial, Rec, RecList, ServiceIcon } from "../components/records";

export function SyncStatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <Badge>—</Badge>;
  const bad = ["failed", "quarantined"].includes(status);
  const warn = status === "warning";
  return (
    <Badge tone={bad ? "bad" : warn ? "warn" : status === "success" || status === "ok" ? "good" : "info"}>
      {bad || warn ? "⚠ " : ""}
      {status.toUpperCase()}
    </Badge>
  );
}

function useProviderLabel() {
  const { lang } = useI18n();
  const providers = useProviders();
  return (id: string) => {
    const p = providers.data?.find((x) => x.id === id);
    return p ? (lang === "fa" ? p.name_fa || p.name_en : p.name_en) : id;
  };
}

function ProviderCards({ providers }: { providers: ProviderInfo[] }) {
  const { t, lang } = useI18n();
  return (
    <RecList label={t("providers")} grid>
      {providers.map((p) => {
        const st = p.last_sync?.status;
        const name = lang === "fa" ? p.name_fa || p.name_en : p.name_en;
        const live = p.adapter === "live_parser";
        return (
          <Rec
            key={p.id}
            accent={providerColor(p.id).css}
            tone={st === "failed" || st === "quarantined" ? "bad" : st === "warning" ? "warn" : undefined}
            icon={<Initial name={name} />}
            title={name}
            meta={
              <>
                <StatusChip tone={live ? "good" : "neutral"} label={live ? t("adapterLive") : t("adapterSeed")} />
                <span>
                  <Num v={p.catalog_items} /> {t("items")}
                </span>
              </>
            }
          >
            <div className="rec-facts">
              <span>
                {t("lastSync")}: {p.last_sync ? <SyncStatusBadge status={st} /> : <span className="muted">{t("never")}</span>}{" "}
                {p.last_sync && <Date_ v={p.last_sync.started_at} />}
              </span>
              <span>
                {t("strategy")}: <code>{p.engine_strategy ?? "—"}</code>
              </span>
            </div>
            {p.last_sync?.error && <p className="rec-note rec-note-bad">{p.last_sync.error}</p>}
            {p.adapter_note && <p className="rec-note">{p.adapter_note}</p>}
            {p.sources.length > 0 && (
              <ul className="rec-sources">
                {p.sources.map((s) => (
                  <li key={s.source_url}>
                    {s.source_url && (
                      <a href={s.source_url} target="_blank" rel="noreferrer noopener" dir="ltr" className="ellipsis">
                        {s.source_url.replace(/^https?:\/\//, "")}
                      </a>
                    )}
                    <FreshnessBadge f={s.freshness} />
                  </li>
                ))}
              </ul>
            )}
          </Rec>
        );
      })}
    </RecList>
  );
}

function PriceCell({ c }: { c: CatalogItem }) {
  const { t } = useI18n();
  return (
    <div className="stacked">
      {c.price_toman !== null && <Money v={c.price_toman} />}
      {c.hourly_price_toman !== null && <Money v={c.hourly_price_toman} suffix={t("perHour")} />}
      {c.daily_price_toman !== null && <Money v={c.daily_price_toman} suffix={t("perDay")} />}
      {c.price_toman === null && c.hourly_price_toman === null && c.daily_price_toman === null && <Money v={null} />}
    </div>
  );
}

function specParts(c: CatalogItem): string[] {
  const parts: string[] = [];
  if (c.cpu_cores) parts.push(`${c.cpu_cores} ${c.cpu_unit ?? "vCPU"}`);
  if (c.ram_gb) parts.push(`${c.ram_gb} GB RAM`);
  if (c.storage_gb) parts.push(`${c.storage_gb} GB ${c.storage_type ?? ""}`.trim());
  else if (c.storage_type) parts.push(c.storage_type);
  if (c.gpu_model) parts.push(`${c.gpu_count ?? ""}× ${c.gpu_model}`);
  if (c.included_traffic_gb) parts.push(`traffic ${c.included_traffic_gb} GB`);
  if (c.resource_class) parts.push(c.resource_class);
  if (c.tier_min || c.tier_max) parts.push(`tier ${c.tier_min ?? 0}–${c.tier_max ?? "∞"} ${c.tier_unit ?? ""}`.trim());
  if (c.datacenter) parts.push(c.datacenter);
  return parts;
}

function History({ item }: { item: CatalogItem }) {
  const { t } = useI18n();
  const q = useQuery({ queryKey: ["catalogHistory", item.id], queryFn: () => api.catalogHistory(item.id) });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorBox error={q.error} />;
  return (
    <div className="stack">
      <div className="rec-hero" style={{ "--prov": providerColor(item.provider_id).css } as CSSProperties}>
        <span className="rec-avatar" aria-hidden>
          <ServiceIcon type={item.service_type} />
        </span>
        <div>
          <strong dir="ltr">{item.sku ?? item.name}</strong>
          <div className="rec-meta" dir="ltr">
            {item.name}
          </div>
        </div>
      </div>
      {item.notes && <p className="small muted">{item.notes}</p>}
      <p className="small muted">{t("priceHistoryHint")}</p>
      <RecList label={t("history")} compact>
        {q.data?.map((v) => {
          const current = !v.valid_to;
          return (
            <Rec
              key={v.version_id ?? v.valid_from}
              selected={current}
              tone={v.availability === "sold_out" ? "bad" : undefined}
              accent={providerColor(item.provider_id).css}
              icon={<span aria-hidden>{current ? "●" : "○"}</span>}
              title={
                <>
                  <PriceCell c={v} />
                  {current && <StatusChip tone="good" label={t("current")} />}
                </>
              }
              meta={
                <>
                  <span>
                    {t("validRange")}: <Date_ v={v.valid_from} /> → {v.valid_to ? <Date_ v={v.valid_to} /> : "…"}
                  </span>
                  <span>
                    {t("retrieved")}: <Date_ v={v.source_retrieved_at} />
                  </span>
                  <span>
                    {t("providerPriceDate")}: <Date_ v={v.source_price_date} />
                  </span>
                </>
              }
              aside={
                <>
                  <StatusChip tone={v.availability === "available" ? "good" : "bad"} label={v.availability === "sold_out" ? t("soldOut") : t("available")} />
                  {v.source_url && (
                    <a className="btn btn-ghost" href={v.source_url} target="_blank" rel="noreferrer noopener" title={v.source_url}>
                      {t("source")} ↗
                    </a>
                  )}
                </>
              }
            />
          );
        })}
      </RecList>
    </div>
  );
}

type Sort = "default" | "priceAsc" | "priceDesc" | "newest" | "name";
const SORT_LABEL: Record<Sort, TKey> = {
  default: "sortDefault",
  priceAsc: "sortPriceAsc",
  priceDesc: "sortPriceDesc",
  newest: "sortNewest",
  name: "sortName",
};
const PAGE = 40;

function CatalogRow({ c, onOpen }: { c: CatalogItem; onOpen: () => void }) {
  const { t } = useI18n();
  const pname = useProviderLabel();
  const sold = c.availability === "sold_out";
  const spec = specParts(c);
  return (
    <Rec
      accent={providerColor(c.provider_id).css}
      tone={sold ? "bad" : undefined}
      icon={<ServiceIcon type={c.service_type} />}
      title={
        <button type="button" className="rec-open" onClick={onOpen} title={t("history")}>
          <bdi dir="ltr">{c.sku ?? c.name}</bdi>
          {c.sku && c.name !== c.sku && (
            <small className="muted" dir="ltr">
              {c.name}
            </small>
          )}
        </button>
      }
      meta={
        <>
          <span className="rec-prov">
            <span className="swatch" style={{ background: providerColor(c.provider_id).css }} aria-hidden />
            {pname(c.provider_id)}
          </span>
          <code>{c.service_type}</code>
          {spec.map((s) => (
            <span key={s} className="spec-chip" dir="ltr">
              {s}
            </span>
          ))}
        </>
      }
      aside={
        <>
          <div className="rec-price">
            <PriceCell c={c} />
            {c.unit && <small className="muted">{c.unit}</small>}
          </div>
          <div className="rec-flags">
            {sold ? <StatusChip tone="bad" label={t("soldOut")} /> : <StatusChip tone="good" label={t("available")} />}
            {c.exact_eligible ? <StatusChip tone="good" label="exact" /> : <StatusChip tone="warn" label={t("notExact")} />}
          </div>
        </>
      }
    >
      <div className="rec-facts">
        <span>
          {t("confidence")}: <strong>{c.confidence}</strong>
        </span>
        <span>
          {t("retrieved")}: <Date_ v={c.source_retrieved_at} />
        </span>
        <span>
          {t("providerPriceDate")}: <Date_ v={c.source_price_date} />
        </span>
        <button type="button" className="linkish" onClick={onOpen}>
          {t("versions")}: <Num v={c.version_count ?? 1} /> · {t("history")}
        </button>
        {c.source_url && (
          <a href={c.source_url} target="_blank" rel="noreferrer noopener" title={c.source_url}>
            {t("source")} ↗
          </a>
        )}
      </div>
    </Rec>
  );
}

export function CatalogPage() {
  const { t } = useI18n();
  const providers = useProviders();
  const pname = useProviderLabel();
  const [provider, setProvider] = useState("");
  const [service, setService] = useState("");
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const [sort, setSort] = useState<Sort>("default");
  const [limit, setLimit] = useState(PAGE);
  const [open, setOpen] = useState<CatalogItem | null>(null);

  const all = useQuery({ queryKey: ["catalog", {}], queryFn: () => api.catalog({}), staleTime: 60_000 });
  const filtered = useQuery({
    queryKey: ["catalog", { provider_id: provider, service_type: service, q }],
    queryFn: () => api.catalog({ provider_id: provider, service_type: service, q }),
    placeholderData: (prev) => prev,
  });
  const serviceTypes = useMemo(() => [...new Set((all.data ?? []).map((c) => c.service_type))].sort(), [all.data]);
  useEffect(() => setLimit(PAGE), [provider, service, q, sort]);

  const rows = useMemo(() => {
    const data = [...(filtered.data ?? [])];
    const key = (c: CatalogItem) => c.sku ?? c.name;
    if (sort === "priceAsc") data.sort((a, b) => compareDecimal(a.price_toman, b.price_toman));
    if (sort === "priceDesc") data.sort((a, b) => (a.price_toman === null ? 1 : b.price_toman === null ? -1 : compareDecimal(b.price_toman, a.price_toman)));
    if (sort === "newest") data.sort((a, b) => (b.source_retrieved_at ?? "").localeCompare(a.source_retrieved_at ?? ""));
    if (sort === "name") data.sort((a, b) => key(a).localeCompare(key(b)));
    return data;
  }, [filtered.data, sort]);
  const shown = rows.slice(0, limit);

  return (
    <div className="stack">
      <h1>{t("navCatalog")}</h1>
      <Card title={t("providers")}>{providers.isLoading ? <Loading /> : providers.error ? <ErrorBox error={providers.error} /> : <ProviderCards providers={providers.data ?? []} />}</Card>

      <Card
        title={t("navCatalog")}
        actions={
          <small className="muted">
            <Num v={rows.length} /> {t("rows")}
          </small>
        }
      >
        <div className="cat-filters">
          <div className="chip-row" role="radiogroup" aria-label={t("colProvider")}>
            {[{ id: "" }, ...(providers.data ?? [])].map((p) => (
              <button key={p.id || "all"} type="button" role="radio" aria-checked={provider === p.id} className={provider === p.id ? "filter-chip on" : "filter-chip"} onClick={() => setProvider(p.id)}>
                {p.id && <span className="swatch" style={{ background: providerColor(p.id).css }} aria-hidden />}
                {p.id ? pname(p.id) : t("all")}
              </button>
            ))}
          </div>
          <div className="row gap wrap">
            <select value={service} onChange={(e) => setService(e.target.value)} aria-label={t("serviceType")}>
              <option value="">
                {t("serviceType")}: {t("all")}
              </option>
              {serviceTypes.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label={t("sortBy")}>
              {(Object.keys(SORT_LABEL) as Sort[]).map((k) => (
                <option key={k} value={k}>
                  {t("sortBy")}: {t(SORT_LABEL[k])}
                </option>
              ))}
            </select>
            <input type="search" className="cat-search" placeholder={t("search")} aria-label={t("search")} value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        </div>
        <ErrorBox error={filtered.error} />
        {filtered.isLoading ? (
          <Loading />
        ) : (
          <>
            <RecList label={t("navCatalog")} compact>
              {shown.map((c) => (
                <CatalogRow key={c.id} c={c} onOpen={() => setOpen(c)} />
              ))}
            </RecList>
            {rows.length > shown.length && (
              <div className="row center cat-more">
                <button type="button" className="btn btn-secondary" onClick={() => setLimit(limit + PAGE)}>
                  {t("showMore")} (<Num v={shown.length} /> {t("shownOf")} <Num v={rows.length} />)
                </button>
              </div>
            )}
          </>
        )}
      </Card>
      <Drawer open={!!open} onClose={() => setOpen(null)} title={t("history")} wide>
        {open && <History item={open} />}
      </Drawer>
    </div>
  );
}
