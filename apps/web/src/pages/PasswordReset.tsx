import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useI18n } from "../lib/i18n";
import { Button, ErrorBox, Field, Loading } from "../components/ui";
import { Lockup } from "../components/Brand";

/** Run on the server when nobody can sign in (docs/installation.md). */
export const RESET_COMMAND = "sudo finops-agent reset-password --email you@example.ir";

/** The sign-in card's frame, shared by the two pages below. */
function AuthFrame({ title, children }: { title: string; children: ReactNode }) {
  const { t, lang, setLang } = useI18n();
  return (
    <div className="auth-page">
      <div className="card auth-card stack">
        <div className="row between">
          <span className="brand">
            <Lockup laid />
          </span>
          <Button variant="ghost" onClick={() => setLang(lang === "fa" ? "en" : "fa")} aria-label={t("language")}>
            {lang === "fa" ? "EN" : "فا"}
          </Button>
        </div>
        <h1>{title}</h1>
        {children}
      </div>
    </div>
  );
}

/** Asks for an emailed link, or, where this installation can't send email, says who can reset it. */
export function ForgotPasswordPage() {
  const { t } = useI18n();
  const status = useQuery({ queryKey: ["authStatus"], queryFn: api.authStatus });
  const [email, setEmail] = useState("");
  const send = useMutation({ mutationFn: () => api.forgotPassword(email) });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    send.mutate();
  };

  let body: ReactNode;
  if (status.isLoading) body = <Loading />;
  else if (!status.data?.password_reset_email)
    body = (
      <>
        <p>{t("forgotNoEmail")}</p>
        <code dir="ltr" className="wrap-any command-box">
          {RESET_COMMAND}
        </code>
      </>
    );
  else if (send.isSuccess)
    body = (
      <p className="alert alert-info" role="status">
        {t("forgotSent")}
      </p>
    );
  else
    body = (
      <form className="stack" onSubmit={submit}>
        <p className="muted">{t("forgotIntro")}</p>
        <Field label={t("email")} htmlFor="email">
          <input id="email" type="email" dir="ltr" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <ErrorBox error={send.error} />
        <Button type="submit" variant="primary" busy={send.isPending}>
          {t("forgotSend")}
        </Button>
      </form>
    );

  return (
    <AuthFrame title={t("forgotTitle")}>
      {body}
      <Link to="/login">{t("backToLogin")}</Link>
    </AuthFrame>
  );
}

/** Opened from the emailed link; the token is in the address's fragment, which never reaches a server. */
export function ResetPasswordPage() {
  const { t } = useI18n();
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get("token") ?? "");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const differ = again !== "" && password !== again;
  const reset = useMutation({ mutationFn: () => api.resetPassword(token, password) });

  // keep the one-time token out of the browser history once it's read
  useEffect(() => {
    if (window.location.hash) window.history.replaceState(null, "", window.location.pathname);
  }, []);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!differ) reset.mutate();
  };

  let body: ReactNode;
  if (!token)
    body = (
      <>
        <p className="alert alert-warn">{t("resetNoToken")}</p>
        <Link to="/forgot-password">{t("forgotPassword")}</Link>
      </>
    );
  else if (reset.isSuccess)
    body = (
      <p className="alert alert-info" role="status">
        {t("resetDone")}
      </p>
    );
  else
    body = (
      <form className="stack" onSubmit={submit}>
        <Field label={t("newPassword")} htmlFor="new-password" hint={t("passwordHint")}>
          <input id="new-password" type="password" dir="ltr" autoComplete="new-password" required minLength={10} value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Field label={t("repeatPassword")} htmlFor="new-password-again">
          <input
            id="new-password-again"
            type="password"
            dir="ltr"
            autoComplete="new-password"
            required
            aria-invalid={differ || undefined}
            aria-describedby={differ ? "reset-differ" : undefined}
            value={again}
            onChange={(e) => setAgain(e.target.value)}
          />
        </Field>
        {differ && (
          <p id="reset-differ" className="alert alert-bad">
            {t("passwordsDiffer")}
          </p>
        )}
        <ErrorBox error={reset.error} />
        <Button type="submit" variant="primary" busy={reset.isPending} disabled={differ}>
          {t("resetSave")}
        </Button>
      </form>
    );

  return (
    <AuthFrame title={t("resetTitle")}>
      {body}
      <Link to="/login">{t("backToLogin")}</Link>
    </AuthFrame>
  );
}
