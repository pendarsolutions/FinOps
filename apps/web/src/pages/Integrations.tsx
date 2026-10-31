import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useI18n } from "../lib/i18n";
import { useProviders } from "../lib/hooks";
import { useSession } from "../lib/session";
import { Button, Card, Date_, ErrorBox, Loading, Num, StatusChip } from "../components/ui";
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

    </div>
  );
}
