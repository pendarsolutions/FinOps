import { useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { CatalogItem, InventoryView, ResourceDraft, ServiceType } from "../api/types";
import { useI18n } from "../lib/i18n";
import { useInventoryMutation, useProviderName, useProviders } from "../lib/hooks";
import { providerColor } from "../lib/viz";
import { Rec, RecList, ServiceIcon } from "./records";
import { ENVIRONMENTS, SERVICE_TYPES, normalizeDigits } from "./ReviewTable";
import { Badge, Button, Card, Empty, ErrorBox, Field, Money, Num, SourceInfo } from "./ui";

type Item = Partial<ResourceDraft> & { name: string; service_type: ServiceType; unknown_fields: string[] };

const DEC_FIELDS = [
  "quantity",
  "cpu_cores",
  "ram_gb",
  "storage_gb",
  "expected_monthly_download_gb",
  "expected_monthly_upload_gb",
  "active_hours_per_month",
] as const;
type DecField = (typeof DEC_FIELDS)[number];

const COMPONENT_CLASS_TYPE: Record<string, string | null> = { compute_vm: "compute_component", dbaas: "dbaas_compute_component", paas: null, object_storage: null };
const COMPONENT_STORAGE_TYPE: Record<string, string | null> = { compute_vm: "storage_component", dbaas: "dbaas_storage_component", paas: null, object_storage: "object_storage" };

function uniq(xs: (string | null)[]): string[] {
  return [...new Set(xs.filter((x): x is string => !!x))].sort();
}

const empty = (): Item => ({ name: "", service_type: "compute_vm", quantity: "1", billing_mode: "monthly", unknown_fields: [] });

export function Builder({ onCreated }: { onCreated: (v: InventoryView) => void }) {
  const { t, lang, fieldLabel } = useI18n();
  const providers = useProviders();
  const pName = useProviderName();
  const provName = (id: string | null | undefined) => pName(id, lang);
  const [invName, setInvName] = useState(lang === "fa" ? "زیرساخت من" : "My infrastructure");
  const [cart, setCart] = useState<Item[]>([]);
  const [it, setIt] = useState<Item>(empty);
  const [formErr, setFormErr] = useState<string | null>(null);

  const provider = providers.data?.find((p) => p.id === it.provider_id);
  const component = provider?.engine_strategy === "component";
  const catalog = useQuery({ queryKey: ["catalog", { provider_id: it.provider_id }], queryFn: () => api.catalog({ provider_id: it.provider_id! }), enabled: !!it.provider_id });

  const skuRows = useMemo(() => (catalog.data ?? []).filter((c) => c.service_type === it.service_type && c.sku), [catalog.data, it.service_type]);
  const classOpts = useMemo(() => uniq((catalog.data ?? []).filter((c) => c.service_type === COMPONENT_CLASS_TYPE[it.service_type]).map((c) => c.resource_class)), [catalog.data, it.service_type]);
  const storageOpts = useMemo(() => uniq((catalog.data ?? []).filter((c) => c.service_type === COMPONENT_STORAGE_TYPE[it.service_type]).map((c) => c.storage_type)), [catalog.data, it.service_type]);
  const picked: CatalogItem | undefined = skuRows.find((c) => c.sku === it.sku);

  const set = <K extends keyof Item>(k: K, v: Item[K]) => setIt((x) => ({ ...x, [k]: v }));
  const isUnknown = (f: string) => it.unknown_fields.includes(f);
  const toggleUnknown = (f: string) =>
    setIt((x) => ({
      ...x,
      [f]: null,
      unknown_fields: x.unknown_fields.includes(f) ? x.unknown_fields.filter((y) => y !== f) : [...x.unknown_fields, f],
    }));

  const dec = (f: DecField, label: ReactNode, allowUnknown = true) => (
    <Field label={label} htmlFor={`b-${f}`}>
      <div className="row gap-s">
        <input
          id={`b-${f}`}
          inputMode="decimal"
          dir="ltr"
          disabled={isUnknown(f)}
          value={(it[f] as string | null | undefined) ?? ""}
          onChange={(e) => set(f, normalizeDigits(e.target.value) || null)}
        />
        {allowUnknown && (
          <label className="dontknow">
            <input type="checkbox" checked={isUnknown(f)} onChange={() => toggleUnknown(f)} /> {t("dontKnow")}
          </label>
        )}
      </div>
    </Field>
  );

  const addToCart = () => {
    for (const f of DEC_FIELDS) {
      const v = it[f];
      if (v && !/^\d+(\.\d+)?$/.test(v)) {
        setFormErr(`${fieldLabel(f)}: ${t("digitsOnly")}`);
        return;
      }
    }
    if (!it.provider_id) {
      setFormErr(`${fieldLabel("provider_id")}: ${t("missing")}`);
      return;
    }
    setFormErr(null);
    const name = it.name.trim() || `${it.provider_id}-${it.sku ?? it.service_type}-${cart.length + 1}`;
    const clean: Item = { ...it, name };
    if (!component) {
      clean.resource_class = null;
    }
    setCart((c) => [...c, clean]);
    setIt({ ...empty(), provider_id: it.provider_id, environment: it.environment });
  };

  const create = useInventoryMutation(() => api.createInventory(invName, cart), (v) => {
    setCart([]);
    onCreated(v);
  });

  const pickSku = (sku: string) => {
    const row = skuRows.find((c) => c.sku === sku);
    setIt((x) => ({
      ...x,
      sku: sku || null,
      cpu_cores: row?.cpu_cores ?? x.cpu_cores ?? null,
      ram_gb: row?.ram_gb ?? x.ram_gb ?? null,
      storage_gb: row?.storage_gb ?? x.storage_gb ?? null,
      storage_type: row?.storage_type ?? x.storage_type ?? null,
      datacenter: row?.datacenter ?? x.datacenter ?? null,
    }));
  };

  return (
    <div className="grid-builder">
      <Card title={t("guidedBuilder")}>
        <div className="form-grid">
          <Field label={t("colProvider")} htmlFor="b-prov">
            <select id="b-prov" value={it.provider_id ?? ""} onChange={(e) => setIt({ ...it, provider_id: e.target.value || null, sku: null, resource_class: null, storage_type: null })}>
              <option value="">—</option>
              {providers.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {lang === "fa" ? p.name_fa || p.name_en : p.name_en} ({p.engine_strategy})
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("serviceType")} htmlFor="b-svc">
            <select id="b-svc" value={it.service_type} onChange={(e) => setIt({ ...it, service_type: e.target.value as ServiceType, sku: null, storage_type: null })}>
              {SERVICE_TYPES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("resourceName")} htmlFor="b-name">
            <input id="b-name" value={it.name} onChange={(e) => set("name", e.target.value)} />
          </Field>
        </div>

        {it.provider_id && component && (
          <>
            <p className="muted small">{t("componentPricing")}</p>
            <div className="form-grid">
              {COMPONENT_CLASS_TYPE[it.service_type] && (
                <Field label={t("resourceClass")} htmlFor="b-class">
                  <select id="b-class" value={it.resource_class ?? ""} onChange={(e) => set("resource_class", e.target.value || null)}>
                    <option value="">—</option>
                    {classOpts.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
              {it.service_type !== "object_storage" && dec("cpu_cores", t("cpuCores"))}
              {it.service_type !== "object_storage" && dec("ram_gb", t("ramGb"))}
              {dec("storage_gb", t("diskGb"))}
              {storageOpts.length > 0 && (
                <Field label={t("storageType")} htmlFor="b-st">
                  <select id="b-st" value={it.storage_type ?? ""} onChange={(e) => set("storage_type", e.target.value || null)}>
                    <option value="">—</option>
                    {storageOpts.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
            </div>
          </>
        )}

        {it.provider_id && !component && (
          <>
            <Field label={t("sku")} htmlFor="b-sku">
              <select id="b-sku" value={it.sku ?? ""} onChange={(e) => pickSku(e.target.value)}>
                <option value="">{catalog.isLoading ? t("loading") : t("chooseSku")}</option>
                {skuRows.map((c) => (
                  <option key={c.id} value={c.sku!} disabled={c.availability !== "available"}>
                    {c.sku} — {c.cpu_cores ?? "?"} vCPU / {c.ram_gb ?? "?"} GB / {c.storage_gb ?? "?"} GB
                    {c.availability !== "available" ? ` (${t("soldOut")})` : ""}
                  </option>
                ))}
              </select>
            </Field>
            {picked && (
              <div className="picked">
                <div className="row gap wrap">
                  <strong dir="ltr">{picked.name}</strong>
                  {picked.price_toman !== null ? (
                    <Money v={picked.price_toman} suffix={picked.unit ?? undefined} />
                  ) : picked.hourly_price_toman !== null ? (
                    <Money v={picked.hourly_price_toman} suffix={t("perHour")} />
                  ) : (
                    <Money v={picked.daily_price_toman} suffix={t("perDay")} />
                  )}
                  <Badge tone={picked.exact_eligible ? "good" : "warn"}>{picked.exact_eligible ? t("exactEligible") : t("notExact")}</Badge>
                  {picked.included_traffic_gb && (
                    <small className="muted">
                      traffic <Num v={picked.included_traffic_gb} /> GB
                    </small>
                  )}
                </div>
                <SourceInfo url={picked.source_url} retrieved={picked.source_retrieved_at} priceDate={picked.source_price_date} />
              </div>
            )}
            <div className="form-grid">{dec("storage_gb", t("diskGb"))}</div>
          </>
        )}

        <div className="form-grid">
          <Field label={t("region")} htmlFor="b-region">
            <input id="b-region" value={it.region ?? ""} onChange={(e) => set("region", e.target.value || null)} />
          </Field>
          <Field label={t("datacenter")} htmlFor="b-dc">
            <input id="b-dc" value={it.datacenter ?? ""} onChange={(e) => set("datacenter", e.target.value || null)} />
          </Field>
          {dec("quantity", t("quantity"), false)}
          {dec("expected_monthly_download_gb", t("download"))}
          {dec("expected_monthly_upload_gb", t("uploadGb"))}
          <Field label={t("publicIpv4")} htmlFor="b-ip">
            <select
              id="b-ip"
              value={isUnknown("requires_public_ipv4") ? "unknown" : it.requires_public_ipv4 === undefined || it.requires_public_ipv4 === null ? "" : String(it.requires_public_ipv4)}
              onChange={(e) => {
                const v = e.target.value;
                setIt((x) => ({
                  ...x,
                  requires_public_ipv4: v === "true" ? true : v === "false" ? false : null,
                  unknown_fields: v === "unknown" ? [...new Set([...x.unknown_fields, "requires_public_ipv4"])] : x.unknown_fields.filter((f) => f !== "requires_public_ipv4"),
                }));
              }}
            >
              <option value="">—</option>
              <option value="true">{t("yes")}</option>
              <option value="false">{t("no")}</option>
              <option value="unknown">{t("dontKnow")}</option>
            </select>
          </Field>
          <Field label={t("colEnv")} htmlFor="b-env">
            <select
              id="b-env"
              value={isUnknown("environment") ? "unknown" : it.environment ?? ""}
              onChange={(e) => {
                const v = e.target.value;
                setIt((x) => ({
                  ...x,
                  environment: v && v !== "unknown" ? v : null,
                  unknown_fields: v === "unknown" ? [...new Set([...x.unknown_fields, "environment"])] : x.unknown_fields.filter((f) => f !== "environment"),
                }));
              }}
            >
              <option value="">—</option>
              {ENVIRONMENTS.map((e) => (
                <option key={e} value={e}>
                  {e}
                </option>
              ))}
              <option value="unknown">{t("dontKnow")}</option>
            </select>
          </Field>
          <Field label={t("billingMode")} htmlFor="b-bill">
            <select id="b-bill" value={it.billing_mode ?? "monthly"} onChange={(e) => set("billing_mode", e.target.value as "monthly" | "hourly")}>
              <option value="monthly">{t("monthly")}</option>
              <option value="hourly">{t("hourly")}</option>
            </select>
          </Field>
          {dec("active_hours_per_month", t("runtimeHours"))}
        </div>
        {formErr && (
          <div className="alert alert-bad" role="alert">
            {formErr}
          </div>
        )}
        <Button variant="primary" onClick={addToCart} disabled={!it.provider_id}>
          + {t("addToCart")}
        </Button>
      </Card>

      <Card title={`${t("cart")} (${cart.length})`}>
        {cart.length === 0 ? (
          <Empty>{t("cartEmpty")}</Empty>
        ) : (
          <RecList label={t("cart")} compact>
            {cart.map((c, i) => (
              <Rec
                key={i}
                accent={providerColor(c.provider_id).css}
                icon={<ServiceIcon type={c.service_type} />}
                title={
                  <>
                    {c.name} <span className="rec-qty">×{c.quantity ?? "?"}</span>
                  </>
                }
                meta={
                  <>
                    <span>{provName(c.provider_id)}</span>
                    <bdi dir="ltr">{c.sku ?? c.resource_class ?? c.service_type}</bdi>
                  </>
                }
                aside={
                  <Button variant="ghost" className="rec-danger" aria-label={t("delete")} onClick={() => setCart(cart.filter((_, j) => j !== i))}>
                    ✕
                  </Button>
                }
              >
                {c.unknown_fields.length > 0 && (
                  <p className="rec-note">
                    {t("dontKnow")}: {c.unknown_fields.map(fieldLabel).join("، ")}
                  </p>
                )}
              </Rec>
            ))}
          </RecList>
        )}
        <Field label={t("inventoryName")} htmlFor="b-invname">
          <input id="b-invname" value={invName} onChange={(e) => setInvName(e.target.value)} />
        </Field>
        <ErrorBox error={create.error} />
        <Button variant="primary" disabled={!cart.length || !invName.trim()} busy={create.isPending} onClick={() => create.mutate(undefined)}>
          {t("createInventory")}
        </Button>
      </Card>
    </div>
  );
}
