import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api, errorCode, type Hours, type Master, type Service } from "../../api";
import { useFormat } from "../../app-context";
import { ErrorNote, useLoad } from "../../components";

const LANGS = ["tk", "ru", "en"] as const;
const EMPTY = { full_name: "", email: "", password: "", title: { tk: "", ru: "", en: "" }, is_active: true, service_ids: [] as number[], hours: [] as Hours[] };
type Draft = typeof EMPTY & { id?: number };

export default function Masters() {
  const { t } = useTranslation();
  const f = useFormat();
  const list = useLoad(() => api<Master[]>("/api/admin/masters"), []);
  const services = useLoad(() => api<Service[]>("/api/admin/services"), []);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const weekdays = t("weekdays", { returnObjects: true }) as string[];

  function edit(m: Master) {
    setError(null);
    setDraft({
      ...EMPTY,
      ...m,
      title: { ...EMPTY.title, ...m.title },
      hours: m.hours.map((h) => ({ ...h, start_time: h.start_time.slice(0, 5), end_time: h.end_time.slice(0, 5) })),
    });
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!draft) return;
    const { id, email, password, full_name, title, is_active, service_ids, hours } = draft;
    try {
      if (id) {
        await api(`/api/admin/masters/${id}`, { method: "PUT", body: { full_name, title, is_active, service_ids, hours } });
      } else {
        await api("/api/admin/masters", { body: { email, password, full_name, title, service_ids, hours } });
      }
      setDraft(null);
      list.reload();
    } catch (err) {
      setError(errorCode(err));
    }
  }

  function toggleDay(weekday: number, on: boolean) {
    if (!draft) return;
    const rest = draft.hours.filter((h) => h.weekday !== weekday);
    setDraft({ ...draft, hours: on ? [...rest, { weekday, start_time: "09:00", end_time: "19:00" }] : rest });
  }

  function changeHours(weekday: number, key: "start_time" | "end_time", value: string) {
    if (!draft) return;
    setDraft({ ...draft, hours: draft.hours.map((h) => (h.weekday === weekday ? { ...h, [key]: value } : h)) });
  }

  return (
    <main className="container">
      <div className="page-head">
        <h1>{t("masters_admin.title")}</h1>
        <button className="btn btn-primary" onClick={() => { setError(null); setDraft({ ...EMPTY }); }}>{t("masters_admin.new")}</button>
      </div>
      <ErrorNote code={list.error} />
      <section className="card table-wrap">
        <table>
          <thead><tr><th>{t("masters_admin.full_name")}</th><th>{t("masters_admin.specialty")}</th><th className="num">{t("masters_admin.services")}</th><th /><th /></tr></thead>
          <tbody>
            {(list.data ?? []).map((m) => (
              <tr key={m.id}>
                <td>{m.full_name}</td>
                <td>{f.loc(m.title)}</td>
                <td className="num">{m.service_ids.length}</td>
                <td>{!m.is_active && <span className="badge">{t("masters_admin.inactive")}</span>}</td>
                <td><button className="btn btn-small" onClick={() => edit(m)}>{t("common.edit")}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {draft && (
        <div className="modal-back">
          <form className="modal" onSubmit={save}>
            <h2>{draft.id ? draft.full_name : t("masters_admin.new")}</h2>
            <label className="field">
              <span>{t("masters_admin.full_name")}</span>
              <input className="input" required minLength={2} value={draft.full_name} onChange={(e) => setDraft({ ...draft, full_name: e.target.value })} />
            </label>
            {!draft.id && (
              <div className="form-grid">
                <label className="field">
                  <span>{t("masters_admin.email")}</span>
                  <input className="input" type="email" required autoComplete="off" value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })} />
                </label>
                <label className="field">
                  <span>{t("masters_admin.password")}</span>
                  <input className="input" type="password" required minLength={8} autoComplete="new-password" value={draft.password} onChange={(e) => setDraft({ ...draft, password: e.target.value })} />
                </label>
              </div>
            )}
            <div className="form-grid">
              {LANGS.map((l) => (
                <label className="field" key={l}>
                  <span>{t("masters_admin.specialty")} ({t(`common.lang_${l}`)})</span>
                  <input className="input" value={draft.title[l]} onChange={(e) => setDraft({ ...draft, title: { ...draft.title, [l]: e.target.value } })} />
                </label>
              ))}
            </div>
            <div className="stack">
              <h3>{t("masters_admin.services")}</h3>
              <div className="check-grid">
                {(services.data ?? []).map((s) => (
                  <label className="check" key={s.id}>
                    <input
                      type="checkbox"
                      checked={draft.service_ids.includes(s.id)}
                      onChange={(e) => setDraft({ ...draft, service_ids: e.target.checked ? [...draft.service_ids, s.id] : draft.service_ids.filter((id) => id !== s.id) })}
                    />
                    {f.loc(s.name)}
                  </label>
                ))}
              </div>
            </div>
            <div className="stack">
              <h3>{t("masters_admin.hours")}</h3>
              {weekdays.map((name, weekday) => {
                const hours = draft.hours.find((h) => h.weekday === weekday);
                return (
                  <div className="hours-row" key={weekday}>
                    <label className="check">
                      <input type="checkbox" checked={!!hours} onChange={(e) => toggleDay(weekday, e.target.checked)} />
                      {name}
                    </label>
                    {hours ? (
                      <>
                        <input className="input" type="time" required aria-label={`${name} start`} value={hours.start_time} onChange={(e) => changeHours(weekday, "start_time", e.target.value)} />
                        <input className="input" type="time" required aria-label={`${name} end`} value={hours.end_time} onChange={(e) => changeHours(weekday, "end_time", e.target.value)} />
                      </>
                    ) : (
                      <span className="muted" style={{ gridColumn: "span 2" }}>{t("masters_admin.day_off")}</span>
                    )}
                  </div>
                );
              })}
            </div>
            {draft.id && (
              <label className="check">
                <input type="checkbox" checked={draft.is_active} onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} />
                {t("masters_admin.active")}
              </label>
            )}
            <ErrorNote code={error} />
            <div className="row">
              <button className="btn btn-primary">{t("common.save")}</button>
              <button type="button" className="btn" onClick={() => setDraft(null)}>{t("common.cancel")}</button>
            </div>
          </form>
        </div>
      )}
    </main>
  );
}
