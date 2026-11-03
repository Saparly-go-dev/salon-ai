import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api, errorCode, type Service } from "../../api";
import { useFormat } from "../../app-context";
import { ErrorNote, useLoad } from "../../components";

const CATEGORIES = ["hair", "nails", "face", "brows", "makeup"];
const LANGS = ["tk", "ru", "en"];
const EMPTY = { category: "hair", name: { tk: "", ru: "", en: "" }, description: { tk: "", ru: "", en: "" }, duration_minutes: 60, price: 100, is_active: true };
type Draft = typeof EMPTY & { id?: number };

export default function Services() {
  const { t } = useTranslation();
  const f = useFormat();
  const list = useLoad(() => api<Service[]>("/api/admin/services"), []);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);

  function edit(s: Service) {
    setError(null);
    setDraft({ ...EMPTY, ...s, name: { ...EMPTY.name, ...s.name }, description: { ...EMPTY.description, ...s.description } });
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!draft) return;
    const { id, ...body } = draft;
    try {
      await api(id ? `/api/admin/services/${id}` : "/api/admin/services", { method: id ? "PUT" : "POST", body });
      setDraft(null);
      list.reload();
    } catch (err) {
      setError(errorCode(err));
    }
  }

  return (
    <main className="container">
      <div className="page-head">
        <h1>{t("services_admin.title")}</h1>
        <button className="btn btn-primary" onClick={() => { setError(null); setDraft({ ...EMPTY }); }}>{t("services_admin.new")}</button>
      </div>
      <ErrorNote code={list.error} />
      <section className="card table-wrap">
        <table>
          <thead><tr><th>{t("common.name")}</th><th>{t("services_admin.category")}</th><th className="num">{t("services_admin.duration")}</th><th className="num">{t("services_admin.price")}</th><th /><th /></tr></thead>
          <tbody>
            {(list.data ?? []).map((s) => (
              <tr key={s.id}>
                <td>{f.loc(s.name)}</td>
                <td>{t(`categories.${s.category}`, { defaultValue: s.category })}</td>
                <td className="num">{s.duration_minutes}</td>
                <td className="num">{f.money(s.price)}</td>
                <td>{!s.is_active && <span className="badge">{t("services_admin.inactive")}</span>}</td>
                <td><button className="btn btn-small" onClick={() => edit(s)}>{t("common.edit")}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {draft && (
        <div className="modal-back">
          <form className="modal" onSubmit={save}>
            <h2>{draft.id ? t("common.edit") : t("services_admin.new")}</h2>
            <div className="form-grid">
              {LANGS.map((l) => (
                <label className="field" key={l}>
                  <span>{t("common.name")} ({t(`common.lang_${l}`)})</span>
                  <input className="input" required value={draft.name[l as "ru"]} onChange={(e) => setDraft({ ...draft, name: { ...draft.name, [l]: e.target.value } })} />
                </label>
              ))}
            </div>
            <div className="form-grid">
              {LANGS.map((l) => (
                <label className="field" key={l}>
                  <span>{t("common.description")} ({t(`common.lang_${l}`)})</span>
                  <textarea className="input" rows={2} value={draft.description[l as "ru"]} onChange={(e) => setDraft({ ...draft, description: { ...draft.description, [l]: e.target.value } })} />
                </label>
              ))}
            </div>
            <div className="form-grid">
              <label className="field">
                <span>{t("services_admin.category")}</span>
                <select className="input" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{t(`categories.${c}`)}</option>)}
                </select>
              </label>
              <label className="field">
                <span>{t("services_admin.duration")}</span>
                <input className="input" type="number" min={5} max={600} step={5} required value={draft.duration_minutes} onChange={(e) => setDraft({ ...draft, duration_minutes: Number(e.target.value) })} />
              </label>
              <label className="field">
                <span>{t("services_admin.price")}</span>
                <input className="input" type="number" min={0} step="0.01" required value={draft.price} onChange={(e) => setDraft({ ...draft, price: Number(e.target.value) })} />
              </label>
            </div>
            <label className="check">
              <input type="checkbox" checked={draft.is_active} onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} />
              {t("services_admin.active")}
            </label>
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
