import { useTour } from "../components/Tour";
import { Fragment, useEffect, useState, type FormEvent } from "react";
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

      <AccountCard />
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

/** Change your own password; every other device signed in as you is signed out. */
function AccountCard() {
  const { t } = useI18n();
  const { session, signIn } = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [done, setDone] = useState(false);
  const differ = again !== "" && next !== again;
  const change = useMutation({
    mutationFn: () => api.changePassword(current, next),
    onSuccess: (s) => {
      signIn(s);
      setCurrent("");
      setNext("");
      setAgain("");
      setDone(true);
    },
  });
  return (
    <Card title={t("yourAccount")}>
      <p className="muted">
        <bdi dir="ltr">{session?.user.email}</bdi>
      </p>
      <form
        className="form-grid"
        onSubmit={(e) => {
          e.preventDefault();
          setDone(false);
          if (!differ) change.mutate();
        }}
      >
        <Field label={t("currentPassword")} htmlFor="cur-pass">
          <input id="cur-pass" type="password" dir="ltr" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
        </Field>
        <Field label={t("newPassword")} htmlFor="new-pass" hint={t("passwordHint")}>
          <input id="new-pass" type="password" dir="ltr" autoComplete="new-password" required minLength={10} value={next} onChange={(e) => setNext(e.target.value)} />
        </Field>
        <Field label={t("repeatPassword")} htmlFor="new-pass-again">
          <input
            id="new-pass-again"
            type="password"
            dir="ltr"
            autoComplete="new-password"
            required
            aria-invalid={differ || undefined}
            aria-describedby={differ ? "pass-differ" : undefined}
            value={again}
            onChange={(e) => setAgain(e.target.value)}
          />
        </Field>
        <Button type="submit" busy={change.isPending} disabled={differ}>
          {t("changePassword")}
        </Button>
      </form>
      {differ && (
        <p id="pass-differ" className="alert alert-bad">
          {t("passwordsDiffer")}
        </p>
      )}
      {done && (
        <p className="alert alert-info" role="status">
          {t("passwordChanged")}
        </p>
      )}
      <ErrorBox error={change.error} />
    </Card>
  );
}

const RANK = ["viewer", "analyst", "admin", "owner"];

/** A random temporary password from the browser's cryptographic generator. */
function suggestPassword(): string {
  const alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join("");
}

function MembersCard() {
  const { t } = useI18n();
  const qc = useQueryClient();
  const { session } = useSession();
  const members = useQuery({ queryKey: ["members"], queryFn: api.members });
  const plain = usePlain();
  const empty = { email: "", password: "", name: "", role: "viewer" };
  const [form, setForm] = useState(empty);
  const [pwFor, setPwFor] = useState<string | null>(null);
  const [temp, setTemp] = useState("");
  const [notice, setNotice] = useState(false);
  const myRank = RANK.indexOf(session?.role ?? "viewer");
  const assignable = ["viewer", "analyst", "admin"].filter((r) => RANK.indexOf(r) <= myRank);
  const changed = () => {
    qc.invalidateQueries({ queryKey: ["members"] });
    qc.invalidateQueries({ queryKey: ["audit"] });
  };
  const add = useMutation({
    mutationFn: () => api.addMember(form),
    onSuccess: () => {
      setForm(empty);
      changed();
    },
  });
  const role = useMutation({ mutationFn: (a: { id: string; role: string }) => api.setMemberRole(a.id, a.role), onSuccess: changed });
  const remove = useMutation({ mutationFn: (id: string) => api.removeMember(id), onSuccess: changed });
  const setPassword = useMutation({
    mutationFn: (a: { id: string; password: string }) => api.setMemberPassword(a.id, a.password),
    onSuccess: () => {
      setPwFor(null);
      setTemp("");
      setNotice(true);
      changed();
    },
  });
  return (
    <Card title={t("members")}>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th scope="col">{t("email")}</th>
              <th scope="col">{t("role")}</th>
              <th scope="col">{t("memberActions")}</th>
            </tr>
          </thead>
          <tbody>
            {members.data?.map((m) => {
              const you = m.id === session?.user.id;
              const canManage = !you && myRank > RANK.indexOf(m.role);
              return (
                <Fragment key={m.id}>
                  <tr>
                    <td>
                      <bdi dir="ltr">{m.email}</bdi> {you ? <Badge>{t("memberYou")}</Badge> : null}
                    </td>
                    <td>
                      {canManage ? (
                        <select aria-label={`${t("role")}: ${m.email}`} value={m.role} onChange={(e) => role.mutate({ id: m.id, role: e.target.value })}>
                          {assignable.map((r) => (
                            <option key={r} value={r}>
                              {plain.role(r)}
                            </option>
                          ))}
                        </select>
                      ) : (
                        plain.role(m.role)
                      )}
                    </td>
                    <td>
                      {canManage ? (
                        <div className="row gap">
                          <Button
                            variant="ghost"
                            className="btn-sm"
                            aria-expanded={pwFor === m.id}
                            onClick={() => {
                              setNotice(false);
                              setTemp("");
                              setPwFor(pwFor === m.id ? null : m.id);
                            }}
                          >
                            <Icon name="key" /> {t("memberSetPassword")}
                          </Button>
                          <Button
                            variant="ghost"
                            className="btn-sm"
                            busy={remove.isPending && remove.variables === m.id}
                            onClick={() => {
                              if (window.confirm(t("memberRemoveConfirm").replace("{email}", m.email))) remove.mutate(m.id);
                            }}
                          >
                            <Icon name="trash" /> {t("memberRemove")}
                          </Button>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                  {pwFor === m.id && (
                    <tr>
                      <td colSpan={3}>
                        <form
                          className="row gap wrap"
                          onSubmit={(e) => {
                            e.preventDefault();
                            setPassword.mutate({ id: m.id, password: temp });
                          }}
                        >
                          <Field label={`${t("memberSetPassword")}: ${m.email}`} htmlFor={`temp-${m.id}`} hint={t("passwordHint")}>
                            <input id={`temp-${m.id}`} type="text" dir="ltr" autoComplete="off" spellCheck={false} required minLength={10} value={temp} onChange={(e) => setTemp(e.target.value)} />
                          </Field>
                          <Button variant="ghost" onClick={() => setTemp(suggestPassword())}>
                            {t("memberSuggestPassword")}
                          </Button>
                          <Button type="submit" busy={setPassword.isPending}>
                            {t("memberSetPasswordSave")}
                          </Button>
                        </form>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {notice && (
        <p className="alert alert-info" role="status">
          {t("memberPasswordSet")}
        </p>
      )}
      <ErrorBox error={role.error ?? remove.error ?? setPassword.error} />
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
