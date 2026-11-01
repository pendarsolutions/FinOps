import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { ServerDetail, ServerView } from "../api/types";
import { useI18n, type TKey } from "../lib/i18n";
import { useProviderName, useProviders } from "../lib/hooks";
import { useSession } from "../lib/session";
import { Badge, Button, Card, Date_, Drawer, Empty, ErrorBox, Field, LinesTable, Loading, Money, Num, Pct, PriceUnavailableBadge, StatusChip, type Tone } from "../components/ui";
import { Initial, Rec, RecList, RecStat } from "../components/records";
import { providerColor } from "../lib/viz";

const STATUS: Record<ServerView["status"], { tone: Tone; key: TKey }> = {
  online: { tone: "good", key: "srvOnline" },
  pending: { tone: "neutral", key: "srvPending" },
  unreachable: { tone: "bad", key: "srvUnreachable" },
  host_key_changed: { tone: "bad", key: "srvKeyChanged" },
};

function CopyBox({ text }: { text: string }) {
  const { t } = useI18n();
  const [done, setDone] = useState(false);
  return (
    <div className="stack">
      <code dir="ltr" className="wrap-any command-box">
        {text}
      </code>
      <div className="row gap">
        <Button
          onClick={() => {
            navigator.clipboard?.writeText(text);
            setDone(true);
          }}
        >
          {done ? `✓ ${t("copied")}` : t("copy")}
        </Button>
      </div>
    </div>
  );
}

function AddServer({ onDone }: { onDone: (s: ServerView) => void }) {
  const { t } = useI18n();
  const enroll = useQuery({ queryKey: ["enrollCommand"], queryFn: api.enrollCommand });
  const empty = { name: "", host: "", port: "22" };
  const [form, setForm] = useState(empty);
  const add = useMutation({
    mutationFn: () => api.addServer({ name: form.name, host: form.host, port: Number(form.port) }),
    onSuccess: (s) => {
      setForm(empty);
      onDone(s);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    add.mutate();
  };
  return (
    <Card title={t("addServer")}>
      <p>{t("enrollStep")}</p>
      {enroll.isLoading ? <Loading /> : enroll.error ? <ErrorBox error={enroll.error} /> : enroll.data && <CopyBox text={enroll.data.command} />}
      <p className="muted">{t("enrollThen")}</p>
      <form className="form-grid" onSubmit={submit}>
        <Field label={t("serverName")} htmlFor="srv-name">
          <input id="srv-name" required maxLength={200} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <Field label={t("serverHost")} htmlFor="srv-host">
          <input id="srv-host" dir="ltr" required maxLength={255} value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} />
        </Field>
        <Field label={t("serverPort")} htmlFor="srv-port">
          <input id="srv-port" dir="ltr" type="number" min={1} max={65535} required value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} />
        </Field>
        <Button type="submit" variant="primary" busy={add.isPending}>
          {t("addServer")}
        </Button>
      </form>
      <ErrorBox error={add.error} />
    </Card>
  );
}

function UsageGrid({ s }: { s: ServerView }) {
  const { t } = useI18n();
  const u = s.usage;
  return (
    <div className="stats">
      <div className="stat">
        <span className="stat-label">{t("srvCpu")}</span>
        {u.p95_cpu_percent != null ? <Pct v={u.p95_cpu_percent} /> : "—"}
      </div>
      <div className="stat">
        <span className="stat-label">{t("srvRam")}</span>
        {u.p95_ram_percent != null ? <Pct v={u.p95_ram_percent} /> : "—"}
      </div>
      <div className="stat">
        <span className="stat-label">{t("srvDisk")}</span>
        {u.disk_used_gb != null ? <><Num v={u.disk_used_gb} /> GB</> : "—"}
      </div>
      <div className="stat">
        <span className="stat-label">{t("srvDownload")}</span>
        {u.monthly_download_gb != null ? <><Num v={u.monthly_download_gb} /> GB</> : "—"}
      </div>
      <div className="stat">
        <span className="stat-label">{t("srvUpload")}</span>
        {u.monthly_upload_gb != null ? <><Num v={u.monthly_upload_gb} /> GB</> : "—"}
      </div>
      <div className="stat">
        <span className="stat-label">{t("srvObserved")}</span>
        <Num v={String(u.observation_days ?? 0)} />
      </div>
    </div>
  );
}

function ServerDrawer({ id, onClose, canEdit }: { id: string; onClose: () => void; canEdit: boolean }) {
  const { t, lang, pick } = useI18n();
  const pname = useProviderName();
  const providers = useProviders();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["server", id], queryFn: () => api.server(id) });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["server", id] });
    qc.invalidateQueries({ queryKey: ["servers"] });
  };
  const patch = useMutation({ mutationFn: (b: Record<string, unknown>) => api.patchServer(id, b), onSuccess: refresh });
  const check = useMutation({ mutationFn: () => api.checkServer(id), onSuccess: refresh });
  const trust = useMutation({ mutationFn: () => api.trustServer(id), onSuccess: refresh });
  const [removal, setRemoval] = useState<string | null>(null);
  const remove = useMutation({
    mutationFn: () => api.deleteServer(id),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["servers"] });
      setRemoval(r.removal_command);
    },
  });
  const [traffic, setTraffic] = useState({ download: "", upload: "" });
  const d: ServerDetail | undefined = q.data;
  const providerId = d?.provider_id ?? null;
  const rows = useQuery({
    queryKey: ["catalog", providerId],
    queryFn: () => api.catalog({ provider_id: providerId! }),
    enabled: !!providerId,
  });
  const plans = rows.data?.filter((i) => i.service_type === "compute_vm" && i.sku) ?? [];
  const classes = [...new Set(rows.data?.filter((i) => i.service_type === "compute_component").map((i) => i.resource_class).filter(Boolean))] as string[];
  const storageTypes = [...new Set(rows.data?.filter((i) => i.service_type === "storage_component").map((i) => i.storage_type).filter(Boolean))] as string[];

  return (
    <Drawer open onClose={onClose} wide title={d?.name ?? ""}>
      {removal ? (
        <div className="stack">
          <p>{t("removeHelp")}</p>
          <CopyBox text={removal} />
        </div>
      ) : q.isLoading || !d ? (
        <Loading />
      ) : (
        <div className="stack">
          <p dir="ltr" className="muted">
            {d.host}:{d.port} {d.os ? `· ${d.os}` : ""} {d.cpu_cores ? `· ${d.cpu_cores} CPU` : ""}
          </p>
          {d.last_error && <p className="alert alert-bad">{d.last_error}</p>}
          {d.status === "host_key_changed" && (
            <div className="stack">
              <p className="alert alert-bad">{t("srvKeyChangedHelp")}</p>
              <div className="row gap">
                <Button disabled={!canEdit} busy={trust.isPending} onClick={() => trust.mutate()}>
                  {t("srvTrust")}
                </Button>
              </div>
            </div>
          )}
          <UsageGrid s={d} />
          {d.usage.traffic_projected && <small className="muted">{t("srvDownload")}: {t("srvProjected")}</small>}

          <Card title={t("srvPlan")}>
            <div className="form-grid">
              <Field label={t("colProvider")} htmlFor="s-prov">
                <select id="s-prov" disabled={!canEdit} value={d.provider_id ?? ""} onChange={(e) => patch.mutate({ provider_id: e.target.value || null, sku: null })}>
                  <option value="">—</option>
                  {providers.data?.map((p) => (
                    <option key={p.id} value={p.id}>
                      {pname(p.id, lang)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t("srvEnv")} htmlFor="s-env">
                <select id="s-env" disabled={!canEdit} value={d.environment ?? ""} onChange={(e) => patch.mutate({ environment: e.target.value || null })}>
                  <option value="">—</option>
                  <option value="production">production</option>
                  <option value="staging">staging</option>
                  <option value="development">development</option>
                  <option value="test">test</option>
                </select>
              </Field>
              <Field label={t("srvRenewal")} htmlFor="s-renew">
                <input id="s-renew" type="date" dir="ltr" disabled={!canEdit} value={d.renewal_date ?? ""} onChange={(e) => patch.mutate({ renewal_date: e.target.value || null })} />
              </Field>
            </div>
            {d.provider_id && (
              <div className="form-grid">
                {plans.length > 0 && (
                  <Field label={t("srvPlan")} htmlFor="s-plan">
                    <select id="s-plan" dir="ltr" disabled={!canEdit} value={d.sku ?? ""} onChange={(e) => patch.mutate({ sku: e.target.value || null })}>
                      <option value="">—</option>
                      {plans.map((p) => (
                        <option key={p.id} value={p.sku ?? ""}>
                          {p.sku}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                {classes.length > 0 && (
                  <Field label={t("srvClass")} htmlFor="s-class">
                    <select id="s-class" dir="ltr" disabled={!canEdit} value={d.resource_class ?? ""} onChange={(e) => patch.mutate({ resource_class: e.target.value || null })}>
                      <option value="">—</option>
                      {classes.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
                {storageTypes.length > 0 && (
                  <Field label={t("srvStorage")} htmlFor="s-storage">
                    <select id="s-storage" dir="ltr" disabled={!canEdit} value={d.storage_type ?? ""} onChange={(e) => patch.mutate({ storage_type: e.target.value || null })}>
                      <option value="">—</option>
                      {storageTypes.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </Field>
                )}
              </div>
            )}
            <h3>{t("srvSuggest")}</h3>
            <p className="muted small">{t("srvSuggestHelp")}</p>
            {d.suggestions.length ? (
              <RecList label={t("srvSuggest")} compact dense>
                {d.suggestions.map((p) => (
                  <Rec
                    key={`${p.provider_id}:${p.sku}`}
                    accent={providerColor(p.provider_id).css}
                    icon={<Initial name={pname(p.provider_id, lang)} />}
                    title={
                      <>
                        {pname(p.provider_id, lang)} <code dir="ltr">{p.sku}</code>
                      </>
                    }
                    meta={p.datacenter ?? undefined}
                    aside={
                      <>
                        <Money v={p.price_toman} />
                        <Button disabled={!canEdit || (d.provider_id === p.provider_id && d.sku === p.sku)} onClick={() => patch.mutate({ provider_id: p.provider_id, sku: p.sku })}>
                          {t("srvSetPlan")}
                        </Button>
                      </>
                    }
                  />
                ))}
              </RecList>
            ) : (
              <p className="muted">—</p>
            )}
            <ErrorBox error={patch.error} />
          </Card>

          {d.breakdown && (
            <Card title={t("srvMonthlyTotal")}>
              {d.monthly_total_toman != null ? <Money v={d.monthly_total_toman} big /> : <PriceUnavailableBadge />}
              <LinesTable lines={d.breakdown.components} />
              {d.breakdown.unavailable.length > 0 && (
                <form
                  className="form-grid"
                  onSubmit={(e) => {
                    e.preventDefault();
                    patch.mutate({ download_gb_override: traffic.download || null, upload_gb_override: traffic.upload || null });
                  }}
                >
                  <Field label={`${t("srvTrafficOverride")} · ${t("srvDownload")}`} htmlFor="s-down">
                    <input id="s-down" dir="ltr" inputMode="decimal" value={traffic.download} onChange={(e) => setTraffic({ ...traffic, download: e.target.value })} />
                  </Field>
                  <Field label={t("srvUpload")} htmlFor="s-up">
                    <input id="s-up" dir="ltr" inputMode="decimal" value={traffic.upload} onChange={(e) => setTraffic({ ...traffic, upload: e.target.value })} />
                  </Field>
                  <Button type="submit" disabled={!canEdit}>
                    {t("save")}
                  </Button>
                </form>
              )}
              {d.breakdown.assumptions.length > 0 && (
                <ul className="assumptions">
                  {d.breakdown.assumptions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              )}
              <small className="muted">{t("srvListPrice")}</small>
            </Card>
          )}

          {d.recommendations.length > 0 && (
            <Card title={t("navOpportunities")}>
              <ul>
                {d.recommendations.map((r) => (
                  <li key={r.key}>
                    <strong>{pick(r.title_fa, r.title_en)}</strong>
                    {r.monthly_saving_toman != null && (
                      <>
                        {" "}
                        · <Money v={r.monthly_saving_toman} />
                      </>
                    )}
                    <div className="small muted">{pick(r.summary_fa, r.summary_en)}</div>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <div className="row gap wrap">
            <Button disabled={!canEdit} busy={check.isPending} onClick={() => check.mutate()}>
              ↻ {t("checkNow")}
            </Button>
            <Button variant="ghost" className="rec-danger" disabled={!canEdit} busy={remove.isPending} onClick={() => remove.mutate()}>
              {t("removeServer")}
            </Button>
          </div>
          <ErrorBox error={check.error || trust.error || remove.error} />
        </div>
      )}
    </Drawer>
  );
}

export function ServersPage() {
  const { t, lang } = useI18n();
  const { hasRole, setActiveId } = useSession();
  const isAdmin = hasRole("admin");
  const nav = useNavigate();
  const pname = useProviderName();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["servers"], queryFn: api.servers, refetchInterval: 60_000 });
  const [open, setOpen] = useState<string | null>(null);
  const toInv = useMutation({
    mutationFn: api.serversToInventory,
    onSuccess: async (r) => {
      await qc.invalidateQueries({ queryKey: ["inventories"] });
      setActiveId(r.id);
      nav("/infrastructure");
    },
  });
  const d = q.data;

  return (
    <div className="stack">
      <h1>{t("navServers")}</h1>
      <p className="muted">{t("serversIntro")}</p>
      {q.isLoading ? (
        <Loading />
      ) : q.error ? (
        <ErrorBox error={q.error} onRetry={() => q.refetch()} />
      ) : (
        d && (
          <>
            {d.servers.length > 0 && (
              <div className="stats">
                <div className="stat">
                  <span className="stat-label">{t("srvMonthlyTotal")}</span>
                  <Money v={d.summary.monthly_total_toman} big />
                </div>
                <div className="stat">
                  <span className="stat-label">{t("srvAvoidable")}</span>
                  <Money v={d.summary.avoidable_monthly_toman} big />
                </div>
                <div className="stat">
                  <span className="stat-label">{t("srvOnlineCount")}</span>
                  <span>
                    <Num v={String(d.summary.online)} /> / <Num v={String(d.summary.total)} />
                  </span>
                </div>
                <div className="stat">
                  <span className="stat-label">{t("srvNotPriced")}</span>
                  <Num v={String(d.summary.not_priced)} />
                </div>
              </div>
            )}
            {d.summary.not_priced > 0 && <p className="alert alert-warn">{t("srvNotPriced")}: <Num v={String(d.summary.not_priced)} /> · {t("srvNotConfirmed")}</p>}
            <Card>
              {d.servers.length === 0 ? (
                <Empty>{t("srvNoServers")}</Empty>
              ) : (
                <RecList label={t("navServers")}>
                  {d.servers.map((s) => {
                    const st = STATUS[s.status];
                    return (
                      <Rec
                        key={s.id}
                        accent={s.provider_id ? providerColor(s.provider_id).css : undefined}
                        tone={st.tone === "bad" ? "bad" : undefined}
                        icon={<Initial name={s.name} />}
                        title={
                          <button type="button" className="linklike" onClick={() => setOpen(s.id)}>
                            {s.name}
                          </button>
                        }
                        meta={
                          <>
                            <StatusChip tone={st.tone} label={t(st.key)} />
                            <span>{s.provider_id ? `${pname(s.provider_id, lang)}${s.sku ? ` · ${s.sku}` : ""}` : t("srvNotConfirmed")}</span>
                            {s.last_seen_at && (
                              <span>
                                {t("srvLastSeen")}: <Date_ v={s.last_seen_at} />
                              </span>
                            )}
                            {s.renewal_date && (
                              <span>
                                {t("srvRenewsIn")}: <Date_ v={s.renewal_date} />
                              </span>
                            )}
                          </>
                        }
                        aside={
                          <>
                            <RecStat label={t("srvCpu")}>{s.usage.p95_cpu_percent != null ? <Pct v={s.usage.p95_cpu_percent} /> : "—"}</RecStat>
                            <RecStat label={t("srvRam")}>{s.usage.p95_ram_percent != null ? <Pct v={s.usage.p95_ram_percent} /> : "—"}</RecStat>
                            <RecStat label={t("srvMonthlyTotal")}>
                              {s.monthly_total_toman != null ? <Money v={s.monthly_total_toman} /> : s.priced ? <PriceUnavailableBadge /> : <Badge>—</Badge>}
                            </RecStat>
                          </>
                        }
                      />
                    );
                  })}
                </RecList>
              )}
              {d.servers.some((s) => s.provider_id) && (
                <div className="row gap">
                  <Button busy={toInv.isPending} onClick={() => toInv.mutate()}>
                    {t("srvToInventory")}
                  </Button>
                </div>
              )}
              <ErrorBox error={toInv.error} />
            </Card>
            {isAdmin && <AddServer onDone={(s) => {
              qc.invalidateQueries({ queryKey: ["servers"] });
              setOpen(s.id);
            }} />}
          </>
        )
      )}
      {open && <ServerDrawer key={open} id={open} canEdit={isAdmin} onClose={() => setOpen(null)} />}
    </div>
  );
}
