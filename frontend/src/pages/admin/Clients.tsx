import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Client } from "../../api";
import { useFormat } from "../../app-context";
import { ErrorNote, useLoad } from "../../components";

export default function Clients() {
  const { t } = useTranslation();
  const f = useFormat();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const list = useLoad(() => api<Client[]>(`/api/admin/clients${query ? `?q=${encodeURIComponent(query)}` : ""}`), [query]);

  return (
    <main className="container">
      <div className="page-head">
        <h1>{t("clients_admin.title")}</h1>
        <input className="input" style={{ maxWidth: 300 }} maxLength={100} placeholder={t("clients_admin.search")} aria-label={t("clients_admin.search")} value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <ErrorNote code={list.error} />
      <section className="card table-wrap">
        {list.data?.length === 0 && <p className="muted">{t("common.none")}</p>}
        {!!list.data?.length && (
          <table>
            <thead><tr><th>{t("auth.full_name")}</th><th>{t("clients_admin.contacts")}</th><th className="num">{t("clients_admin.visits")}</th><th className="num">{t("clients_admin.spent")}</th><th>{t("clients_admin.last")}</th></tr></thead>
            <tbody>
              {list.data.map((c) => (
                <tr key={c.id}>
                  <td>{c.full_name}</td>
                  <td>{c.phone ?? ""}<div className="muted">{c.email}</div></td>
                  <td className="num">{c.visits}</td>
                  <td className="num">{f.money(c.total_spent)}</td>
                  <td>{c.last_visit ? f.dayMonth(f.localDate(c.last_visit)) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
