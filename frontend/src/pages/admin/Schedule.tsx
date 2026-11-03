import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, errorCode, type Appointment, type Master, type Status } from "../../api";
import { addDays, useApp, useFormat } from "../../app-context";
import { ErrorNote, useLoad } from "../../components";

export default function Schedule() {
  const { t } = useTranslation();
  const f = useFormat();
  const { user } = useApp();
  const isAdmin = user?.role === "admin";
  const [date, setDate] = useState(f.today());
  const [masterId, setMasterId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const masters = useLoad(() => (isAdmin ? api<Master[]>("/api/admin/masters") : Promise.resolve([])), [isAdmin]);
  const list = useLoad(
    () => api<Appointment[]>(`/api/admin/appointments?on=${date}${masterId ? `&master_id=${masterId}` : ""}`),
    [date, masterId],
  );

  async function setStatus(id: number, status: Status) {
    setError(null);
    try {
      await api(`/api/admin/appointments/${id}`, { method: "PATCH", body: { status } });
      list.reload();
    } catch (e) {
      setError(errorCode(e));
    }
  }

  return (
    <main className="container">
      <div className="page-head">
        <h1>{t("schedule.title")}</h1>
        {isAdmin && <Link className="btn btn-primary" to="/book">{t("schedule.new")}</Link>}
      </div>
      <div className="row">
        <button className="btn btn-small" aria-label="-1" onClick={() => setDate(addDays(date, -1))}>←</button>
        <input className="input" style={{ width: "auto" }} type="date" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} />
        <button className="btn btn-small" aria-label="+1" onClick={() => setDate(addDays(date, 1))}>→</button>
        <strong>{f.longDate(date)}</strong>
        {isAdmin && (
          <select className="input" style={{ width: "auto" }} value={masterId ?? ""} onChange={(e) => setMasterId(Number(e.target.value) || null)}>
            <option value="">{t("schedule.all_masters")}</option>
            {(masters.data ?? []).map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
          </select>
        )}
      </div>
      <ErrorNote code={error ?? list.error} />
      <section className="card table-wrap">
        {list.data?.length === 0 && <p className="muted">{t("schedule.empty")}</p>}
        {!!list.data?.length && (
          <table>
            <thead>
              <tr><th>{t("schedule.time")}</th><th>{t("schedule.client")}</th><th>{t("schedule.service")}</th><th>{t("schedule.master")}</th><th>{t("schedule.status")}</th><th>{t("schedule.actions")}</th></tr>
            </thead>
            <tbody>
              {list.data.map((a) => (
                <tr key={a.id}>
                  <td className="num">{f.time(a.starts_at)}–{f.time(a.ends_at)}</td>
                  <td>{a.client_name}{a.client_phone && <div className="muted">{a.client_phone}</div>}</td>
                  <td>
                    {f.loc(a.service_name)}
                    {a.source === "chat" && <div className="muted">{t("schedule.source_chat")}</div>}
                    {a.notes && <div className="muted">{a.notes}</div>}
                  </td>
                  <td>{a.master_name}</td>
                  <td><span className={`badge badge-${a.status}`}>{t(`status.${a.status}`)}</span></td>
                  <td>
                    {a.status === "booked" && (
                      <div className="row">
                        <button className="btn btn-small" onClick={() => setStatus(a.id, "completed")}>{t("schedule.complete")}</button>
                        <button className="btn btn-small" onClick={() => setStatus(a.id, "no_show")}>{t("schedule.no_show")}</button>
                        <button className="btn btn-small" onClick={() => setStatus(a.id, "cancelled")}>{t("schedule.cancel")}</button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
