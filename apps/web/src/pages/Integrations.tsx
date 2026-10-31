import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useI18n } from "../lib/i18n";
import { useProviders } from "../lib/hooks";
import { useSession } from "../lib/session";
import { Badge, Button, Card, Date_, ErrorBox, Field, Loading, Num, StatusChip } from "../components/ui";
import { Initial, Rec, RecList, RecStat } from "../components/records";
import { providerColor } from "../lib/viz";
import { SyncStatusBadge } from "./Catalog";

export function IntegrationsPage() {
  const { t, lang } = useI18n();
  const { hasRole } = useSession();
  const isAdmin = hasRole("admin");
  const qc = useQueryClient();
  const providers = useProviders();
  const integ = useQuery({ queryKey: ["integrations"], queryFn: api.integrations });
  const runs = useQuery({ queryKey: ["syncRuns"], queryFn: api.syncRuns });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["syncRuns"] });
    qc.invalidateQueries({ queryKey: ["providers"] });
    qc.invalidateQueries({ queryKey: ["catalog"] });
    qc.invalidateQueries({ queryKey: ["integrations"] });
  };
  const sync = useMutation({ mutationFn: api.syncProvider, onSettled: refresh });
  const approve = useMutation({ mutationFn: api.approveRun, onSettled: refresh });

  const [cred, setCred] = useState({ provider_id: "", label: "", secret: "" });
  const addCred = useMutation({
    mutationFn: () => api.addCredential({ ...cred, read_only: true }),
    onSuccess: () => {
      setCred({ provider_id: "", label: "", secret: "" });
      qc.invalidateQueries({ queryKey: ["integrations"] });
    },
  });
  const delCred = useMutation({ mutationFn: api.deleteCredential, onSuccess: () => qc.invalidateQueries({ queryKey: ["integrations"] }) });
  const submitCred = (e: FormEvent) => {
    e.preventDefault();
    addCred.mutate();
  };
  const pname = (id: string) => {
    const p = providers.data?.find((x) => x.id === id);
    return p ? (lang === "fa" ? p.name_fa || p.name_en : p.name_en) : id;
  };

  return (
    <div className="stack">
      <h1>{t("navIntegrations")}</h1>
      <ErrorBox error={sync.error || approve.error} />
      <Card title={t("priceAdapters")}>
        {integ.isLoading ? (
          <Loading />
        ) : integ.error ? (
          <ErrorBox error={integ.error} />
        ) : (
          <RecList label={t("priceAdapters")}>
            {integ.data?.price_adapters.map((a) => {
              const last = providers.data?.find((p) => p.id === a.provider_id)?.last_sync;
              const live = a.status === "live_parser";
              return (
                <Rec
                  key={a.provider_id}
                  accent={providerColor(a.provider_id).css}
                  icon={<Initial name={pname(a.provider_id)} />}
                  title={pname(a.provider_id)}
                  meta={
                    <>
                      <StatusChip tone={live ? "good" : "neutral"} label={live ? t("adapterLive") : a.status === "seed_only" ? t("adapterSeed") : a.status} title={a.status} />
                      <span>
                        {t("lastSync")}:{" "}
                        {last ? (
                          <>
                            <SyncStatusBadge status={last.status} /> <Date_ v={last.started_at} />
                          </>
                        ) : (
                          t("never")
                        )}
                      </span>
                    </>
                  }
                  aside={
                    <Button
                      disabled={!isAdmin || !live}
                      title={!isAdmin ? t("adminOnly") : undefined}
                      busy={sync.isPending && sync.variables === a.provider_id}
                      onClick={() => sync.mutate(a.provider_id)}
                    >
                      ↻ {t("syncNow")}
                    </Button>
                  }
                >
                  {a.note && <p className="rec-note">{a.note}</p>}
                </Rec>
              );
            })}
          </RecList>
        )}
        {!isAdmin && <p className="muted small">{t("syncNow")}: {t("adminOnly")}</p>}
      </Card>

      <Card title={t("syncRuns")}>
        {runs.isLoading ? (
          <Loading />
        ) : runs.error ? (
          <ErrorBox error={runs.error} />
        ) : !runs.data?.length ? (
          <p className="muted">{t("noRuns")}</p>
        ) : (
          <RecList label={t("syncRuns")}>
            {runs.data.map((r) => {
              const bad = ["failed", "quarantined"].includes(r.status);
              const warns = Array.isArray(r.warnings) ? (r.warnings as unknown[]) : [];
              return (
                <Rec
                  key={r.id}
                  accent={providerColor(r.provider_id).css}
                  tone={bad ? "bad" : r.status === "warning" ? "warn" : undefined}
                  icon={<Initial name={pname(r.provider_id)} />}
                  title={
                    <>
                      {pname(r.provider_id)} <SyncStatusBadge status={r.status} />
                    </>
                  }
                  meta={
                    <>
                      {t("started")}: <Date_ v={r.started_at} />
                    </>
                  }
                  aside={
                    <>
                      <RecStat label={t("seen")}>
                        <Num v={r.items_seen} />
                      </RecStat>
                      <RecStat label={t("changed")}>
                        <Num v={r.items_changed} />
                      </RecStat>
                      {r.status === "quarantined" && r.has_pending_items && (
                        <Button
                          variant="primary"
                          disabled={!isAdmin}
                          title={!isAdmin ? t("adminOnly") : undefined}
                          busy={approve.isPending && approve.variables === r.id}
                          onClick={() => approve.mutate(r.id)}
                        >
                          {t("approve")}
                        </Button>
                      )}
                    </>
                  }
                >
                  {(r.error || warns.length > 0) && (
                    <>
                      {r.error && <p className="rec-note rec-note-bad">{r.error}</p>}
                      {warns.length > 0 && (
                        <details className="rec-details">
                          <summary>
                            {t("warnings")} ({warns.length})
                          </summary>
                          <ul dir="ltr">
                            {warns.map((w, i) => (
                              <li key={i}>{typeof w === "string" ? w : JSON.stringify(w)}</li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </>
                  )}
                </Rec>
              );
            })}
          </RecList>
        )}
      </Card>

      <Card title={t("inventoryConnectors")}>
        {integ.data && (
          <p>
            <Badge tone="warn">{integ.data.inventory_connectors.status}</Badge> {integ.data.inventory_connectors.note}
          </p>
        )}
        <h3>{t("credentials")}</h3>
        {integ.data?.credentials.length ? (
          <RecList label={t("credentials")} compact>
            {integ.data.credentials.map((c) => (
              <Rec
                key={c.id}
                accent={providerColor(c.provider_id).css}
                icon={<Initial name={pname(c.provider_id)} />}
                title={
                  <>
                    {pname(c.provider_id)} <span className="muted">· {c.label}</span>
                  </>
                }
                meta={
                  <>
                    <code dir="ltr">{c.secret_hint}</code>
                    <StatusChip tone="info" label={t("readOnly")} />
                    <Date_ v={c.created_at} />
                  </>
                }
                aside={
                  <Button variant="ghost" className="rec-danger" disabled={!isAdmin} busy={delCred.isPending && delCred.variables === c.id} onClick={() => delCred.mutate(c.id)}>
                    {t("delete")}
                  </Button>
                }
              />
            ))}
          </RecList>
        ) : (
          <p className="muted">—</p>
        )}
        <form className="form-grid" onSubmit={submitCred}>
          <Field label={t("colProvider")} htmlFor="cr-prov">
            <select id="cr-prov" required value={cred.provider_id} onChange={(e) => setCred({ ...cred, provider_id: e.target.value })}>
              <option value="">—</option>
              {providers.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {pname(p.id)}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("label")} htmlFor="cr-label">
            <input id="cr-label" required maxLength={200} value={cred.label} onChange={(e) => setCred({ ...cred, label: e.target.value })} />
          </Field>
          <Field label={t("secret")} htmlFor="cr-secret">
            <input id="cr-secret" type="password" dir="ltr" autoComplete="off" required minLength={8} value={cred.secret} onChange={(e) => setCred({ ...cred, secret: e.target.value })} />
          </Field>
          <label className="toggle">
            <input type="checkbox" checked readOnly disabled /> {t("readOnly")}
          </label>
          <Button type="submit" variant="primary" disabled={!isAdmin} title={!isAdmin ? t("adminOnly") : undefined} busy={addCred.isPending}>
            {t("addCredential")}
          </Button>
        </form>
        <ErrorBox error={addCred.error || delCred.error} />
      </Card>
    </div>
  );
}
