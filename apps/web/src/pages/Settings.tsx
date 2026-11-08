import { useTour } from "../components/Tour";
import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { useI18n } from "../lib/i18n";
import { usePlain } from "../lib/plain";
import { useSession } from "../lib/session";
import { Badge, Button, Card, Date_, ErrorBox, Field, Loading, Money } from "../components/ui";
import { normalizeDigits } from "../components/ReviewTable";
import { Rec, RecList } from "../components/records";
import { Icon } from "../components/Icon";

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
              {save.isSuccess && (
                <Badge tone="good">
                  <Icon name="check" small /> {t("saved")}
                </Badge>
              )}
              {!isAdmin && <small className="muted">{t("adminOnly")}</small>}
            </div>
          </form>
        )}
      </Card>

      {isAdmin && <MembersCard />}

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
                icon={<Icon name={a.action.includes("delete") ? "trash" : a.action.includes("confirm") ? "check" : "edit"} />}
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

function MembersCard() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const members = useQuery({ queryKey: ["members"], queryFn: api.members });
  const plain = usePlain();
  const empty = { email: "", password: "", name: "", role: "viewer" };
  const [form, setForm] = useState(empty);
  const add = useMutation({
    mutationFn: () => api.addMember(form),
    onSuccess: () => {
      setForm(empty);
      qc.invalidateQueries({ queryKey: ["members"] });
    },
  });
  return (
    <Card title={t("members")}>
      <ul>
        {members.data?.map((m) => (
          <li key={m.id}>
            <bdi dir="ltr">{m.email}</bdi> · <small className="muted">{plain.role(m.role)}</small>
          </li>
        ))}
      </ul>
      <form
        className="form-grid"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate();
        }}
      >
        <Field label={t("email")} htmlFor="m-email">
          <input id="m-email" type="email" dir="ltr" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        <Field label={t("password")} htmlFor="m-pass" hint={t("passwordHint")}>
          <input id="m-pass" type="password" dir="ltr" autoComplete="new-password" required minLength={10} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </Field>
        <Field label={t("role")} htmlFor="m-role">
          <select id="m-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            <option value="viewer">{plain.role("viewer")}</option>
            <option value="analyst">{plain.role("analyst")}</option>
            <option value="admin">{plain.role("admin")}</option>
          </select>
        </Field>
        <Button type="submit" variant="primary" busy={add.isPending}>
          {t("addMember")}
        </Button>
      </form>
      <ErrorBox error={add.error} />
    </Card>
  );
}
