import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useI18n } from "../lib/i18n";
import { useSession } from "../lib/session";
import { Button, ErrorBox, Field } from "../components/ui";
import { Lockup } from "../components/Brand";

export function LoginPage({ mode }: { mode: "login" | "register" }) {
  const { t, lang, setLang } = useI18n();
  const { session, signIn } = useSession();
  const nav = useNavigate();
  const loc = useLocation();
  const from = (loc.state as { from?: string } | null)?.from ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [org, setOrg] = useState("");
  const status = useQuery({ queryKey: ["authStatus"], queryFn: api.authStatus });
  const closed = mode === "register" && status.data?.registration_open === false;
  const setup = status.data?.setup_needed === true;

  const m = useMutation({
    mutationFn: () =>
      mode === "login" ? api.login(email, password) : api.register({ email, password, name, organization_name: org }),
    onSuccess: (s) => {
      signIn(s);
      nav(from, { replace: true });
    },
  });

  if (session) return <Navigate to={from} replace />;
  if (setup && mode === "login") return <Navigate to="/register" replace />;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    m.mutate();
  };

  return (
    <div className="auth-page">
      <form className="card auth-card stack" onSubmit={submit}>
        <div className="row between">
          <span className="brand">
            <Lockup laid />
          </span>
          <Button variant="ghost" onClick={() => setLang(lang === "fa" ? "en" : "fa")} aria-label={t("language")}>
            {lang === "fa" ? "EN" : "فا"}
          </Button>
        </div>
        <p className="muted">{t("tagline")}</p>
        <h1>{setup ? t("setupTitle") : mode === "login" ? t("login") : t("register")}</h1>
        {setup && <p>{t("setupLead")}</p>}
        <Field label={t("email")} htmlFor="email">
          <input id="email" type="email" dir="ltr" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label={t("password")} htmlFor="password" hint={mode === "register" ? t("passwordHint") : undefined}>
          <input
            id="password"
            type="password"
            dir="ltr"
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            required
            minLength={mode === "register" ? 10 : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        {mode === "register" && (
          <>
            <Field label={t("yourName")} htmlFor="name">
              <input id="name" value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label={t("orgName")} htmlFor="org">
              <input id="org" required value={org} onChange={(e) => setOrg(e.target.value)} />
            </Field>
          </>
        )}
        {mode === "login" && <Link to="/forgot-password">{t("forgotPassword")}</Link>}
        <ErrorBox error={m.error} />
        {closed && <p className="alert alert-bad">{t("registrationClosed")}</p>}
        <Button type="submit" variant="primary" busy={m.isPending} disabled={closed}>
          {setup ? t("setupSubmit") : mode === "login" ? t("login") : t("register")}
        </Button>
        {/* where sign-up is closed, people are added by an admin, so there's nothing to link to */}
        {mode === "login" && status.data?.registration_open && <Link to="/register">{t("noAccount")}</Link>}
        {mode === "register" && !setup && <Link to="/login">{t("haveAccount")}</Link>}
        {mode === "login" && status.data?.demo_user && <small className="muted" dir="ltr">{t("demoHint")}</small>}
      </form>
    </div>
  );
}
