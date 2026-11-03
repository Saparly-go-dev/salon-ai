import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, errorCode, type Appointment } from "../api";
import { useFormat } from "../app-context";
import { Banner, ErrorNote, useLoad } from "../components";

export default function MyAppointments() {
  const { t } = useTranslation();
  const f = useFormat();
  const list = useLoad(() => api<Appointment[]>("/api/appointments/mine"), []);
  const [error, setError] = useState<string | null>(null);

  async function cancel(id: number) {
    if (!window.confirm(t("mine.cancel_confirm"))) return;
    setError(null);
    try {
      await api(`/api/appointments/${id}/cancel`, { method: "POST" });
      list.reload();
    } catch (e) {
      setError(errorCode(e));
    }
  }

  const now = Date.now();
  const all = list.data ?? [];
  const upcoming = all.filter((a) => a.status === "booked" && new Date(a.starts_at).getTime() > now).reverse();
  const past = all.filter((a) => !upcoming.includes(a));

  const row = (a: Appointment, canCancel: boolean) => (
    <div className="service-row" key={a.id}>
      <div className="service-info">
        <div><strong>{f.loc(a.service_name)}</strong></div>
        <div className="muted">{f.dateTime(a.starts_at)} · {a.master_name} · {f.money(a.price)}</div>
      </div>
      {canCancel
        ? <button className="btn btn-small" onClick={() => cancel(a.id)}>{t("mine.cancel")}</button>
        : <span className="badge">{t(`status.${a.status}`)}</span>}
    </div>
  );

  return (
    <main className="container narrow">
      <Banner image="/images/nails.jpg" title={t("mine.title")} />
      <ErrorNote code={error ?? list.error} />
      {list.data && all.length === 0 && (
        <div className="card stack">
          <p>{t("mine.empty")}</p>
          <div><Link className="btn btn-primary" to="/book">{t("mine.book_now")}</Link></div>
        </div>
      )}
      {upcoming.length > 0 && (
        <section className="card">
          <h2>{t("mine.upcoming")}</h2>
          {upcoming.map((a) => row(a, true))}
        </section>
      )}
      {past.length > 0 && (
        <section className="card">
          <h2>{t("mine.past")}</h2>
          {past.map((a) => row(a, false))}
        </section>
      )}
    </main>
  );
}
