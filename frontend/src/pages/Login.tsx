import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation } from "react-router-dom";
import { api, errorCode, type User } from "../api";
import { useApp } from "../app-context";
import { ErrorNote } from "../components";

export default function Login() {
  const { t } = useTranslation();
  const { user, signIn } = useApp();
  const location = useLocation();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({ email: "", password: "", full_name: "", phone: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from: string | undefined = location.state?.from;
  const homeFor = (u: User) => from ?? (u.role === "admin" ? "/admin" : u.role === "master" ? "/admin/schedule" : "/");
  if (user) return <Navigate to={homeFor(user)} replace />;

  const update = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = mode === "login"
        ? { email: form.email, password: form.password }
        : { ...form, phone: form.phone || null };
      const result = await api<{ access_token: string; user: User }>(`/api/auth/${mode}`, { body });
      signIn(result.access_token, result.user);
    } catch (err) {
      setError(errorCode(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="container tiny">
      <form className="card stack" onSubmit={submit}>
        <img className="card-photo" style={{ marginBottom: 0 }} src="/images/makeup.jpg" alt="" />
        <h1>{t(mode === "login" ? "auth.login_title" : "auth.register_title")}</h1>
        {mode === "register" && (
          <label className="field">
            <span>{t("auth.full_name")}</span>
            <input className="input" required minLength={2} autoComplete="name" value={form.full_name} onChange={update("full_name")} />
          </label>
        )}
        <label className="field">
          <span>{t("auth.email")}</span>
          <input className="input" type="email" required autoComplete="email" value={form.email} onChange={update("email")} />
        </label>
        <label className="field">
          <span>{t("auth.password")}</span>
          <input className="input" type="password" required minLength={mode === "register" ? 8 : undefined} autoComplete={mode === "login" ? "current-password" : "new-password"} value={form.password} onChange={update("password")} />
          {mode === "register" && <small className="muted">{t("auth.password_hint")}</small>}
        </label>
        {mode === "register" && (
          <label className="field">
            <span>{t("auth.phone")}</span>
            <input className="input" type="tel" autoComplete="tel" value={form.phone} onChange={update("phone")} />
          </label>
        )}
        <ErrorNote code={error} />
        <button className="btn btn-primary" disabled={busy}>{t(mode === "login" ? "auth.login" : "auth.register")}</button>
        <button type="button" className="link-btn" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }}>
          {t(mode === "login" ? "auth.to_register" : "auth.to_login")}
        </button>
      </form>
    </main>
  );
}
