import { useTour } from "../components/Tour";
import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useI18n } from "../lib/i18n";
import { useSession } from "../lib/session";
import { Badge, Button, Card, Date_, ErrorBox, Field, Loading, Money } from "../components/ui";
import { normalizeDigits } from "../components/ReviewTable";
import { Rec, RecList } from "../components/records";

export function SettingsPage() {
  const { t, lang, setLang } = useI18n();
  const { hasRole, session } = useSession();
  const isAdmin = hasRole("admin");
  const tour = useTour();
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const audit = useQuery({ queryKey: ["audit"], queryFn: () => api.auditLogs(100), enabled: isAdmin });
  const [rate, setRate] = useState("");
  useEffect(() => setRate(settings.data?.settings.engineer_day_rate_toman ?? ""), [settings.data]);
  const valid = rate === "" || /^\d+$/.test(rate);
  const save = useMutation({
    mutationFn: () => api.putSettings({ engineer_day_rate_toman: rate === "" ? null : rate }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      qc.invalidateQueries({ queryKey: ["audit"] });
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };

  return (
    <div className="stack">
      <h1>{t("navSettings")}</h1>
      <Card title={t("language")}>
        <div className="row gap" role="radiogroup" aria-label={t("language")}>
          <Button variant={lang === "fa" ? "primary" : "secondary"} role="radio" aria-checked={lang === "fa"} onClick={() => setLang("fa")}>
            فارسی
          </Button>
          <Button variant={lang === "en" ? "primary" : "secondary"} role="radio" aria-checked={lang === "en"} onClick={() => setLang("en")}>
            English
          </Button>
        </div>
      </Card>

      <Card title={t("tourHelp")}>
        <Button onClick={() => tour.start()}>{t("tourRestart")}</Button>
      </Card>

      <Card title={`${t("organization")}: ${session?.organization.name ?? ""}`}>
        {settings.isLoading ? (
          <Loading />
        ) : settings.error ? (
          <ErrorBox error={settings.error} />
        ) : (
          <form className="stack" onSubmit={submit}>
            <Field label={t("dayRate")} htmlFor="day-rate" hint={t("dayRateHelp")}>
              <input
                id="day-rate"
                inputMode="numeric"
                dir="ltr"
                value={rate}
                aria-invalid={!valid || undefined}
                placeholder={t("digitsOnly")}
                disabled={!isAdmin}
                onChange={(e) => setRate(normalizeDigits(e.target.value))}
              />
            </Field>
            {rate && valid && (
              <p className="small">
                = <Money v={rate} />
              </p>
            )}
            {!valid && (
              <p className="alert alert-bad" role="alert">
                {t("digitsOnly")}
              </p>
            )}
            {settings.data?.settings.engineer_day_rate_label && (
              <p className="small">
                <Badge tone="warn">{settings.data.settings.engineer_day_rate_label}</Badge>
              </p>
            )}
            <ErrorBox error={save.error} />
            <div className="row gap">
              <Button type="submit" variant="primary" disabled={!isAdmin || !valid} busy={save.isPending}>
                {t("save")}
              </Button>
              {save.isSuccess && <Badge tone="good">✓ {t("saved")}</Badge>}
              {!isAdmin && <small className="muted">{t("adminOnly")}</small>}
            </div>
          </form>
        )}
      </Card>

      <Card title={t("auditLog")}>
        {!isAdmin ? (
          <p className="muted">{t("errForbidden")} ({t("adminOnly")})</p>
        ) : audit.isLoading ? (
          <Loading />
        ) : audit.error ? (
          <ErrorBox error={audit.error} />
        ) : (
          <RecList label={t("auditLog")} compact dense>
            {audit.data?.map((a) => (
              <Rec
                key={a.id}
                icon={<span aria-hidden>{a.action.includes("delete") ? "✕" : a.action.includes("confirm") ? "✓" : "•"}</span>}
                tone={a.action.includes("delete") ? "bad" : undefined}
                title={<code dir="ltr">{a.action}</code>}
                meta={
                  <>
                    <Date_ v={a.created_at} />
                    <bdi dir="ltr">
                      {a.entity_type} {a.entity_id?.slice(0, 8)}
                    </bdi>
                  </>
                }
              >
                {a.detail ? (
                  <details className="rec-details">
                    <summary>{t("detail")}</summary>
                    <code dir="ltr" className="wrap-any">
                      {JSON.stringify(a.detail)}
                    </code>
                  </details>
                ) : null}
              </Rec>
            ))}
          </RecList>
        )}
      </Card>
    </div>
  );
}
