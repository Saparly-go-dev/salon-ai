import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { api, errorCode, type Appointment, type Client, type Master, type Service, type Slot } from "../api";
import { addDays, useApp, useFormat } from "../app-context";
import { Banner, ErrorNote, useLoad } from "../components";
import { CATEGORY_PHOTOS } from "../photos";

export default function Book() {
  const { t } = useTranslation();
  const f = useFormat();
  const { user } = useApp();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const isAdmin = user?.role === "admin";

  const [serviceId, setServiceId] = useState<number | null>(Number(params.get("service")) || null);
  const [masterId, setMasterId] = useState<number | null>(null);
  const [date, setDate] = useState(f.today());
  const [slot, setSlot] = useState<Slot | null>(null);
  const [notes, setNotes] = useState("");
  const [clientId, setClientId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<Appointment | null>(null);

  const services = useLoad(() => api<Service[]>("/api/services"), []);
  const masters = useLoad(
    () => (serviceId ? api<Master[]>(`/api/masters?service_id=${serviceId}`) : Promise.resolve([])),
    [serviceId],
  );
  const slots = useLoad(
    () => {
      if (!serviceId) return Promise.resolve<Slot[]>([]);
      const master = masterId ? `&master_id=${masterId}` : "";
      return api<Slot[]>(`/api/availability?service_id=${serviceId}&on=${date}${master}`);
    },
    [serviceId, masterId, date],
  );
  const clients = useLoad(() => (isAdmin ? api<Client[]>("/api/admin/clients") : Promise.resolve([])), [isAdmin]);

  useEffect(() => setSlot(null), [serviceId, masterId, date]);

  const service = services.data?.find((s) => s.id === serviceId) ?? null;
  const days = useMemo(() => Array.from({ length: 14 }, (_, i) => addDays(f.today(), i)), []); // eslint-disable-line react-hooks/exhaustive-deps

  // При выборе "любого мастера" одно и то же время показывается один раз
  const uniqueSlots = useMemo(() => {
    const seen = new Set<string>();
    return (slots.data ?? []).filter((s) => !seen.has(s.starts_at) && !!seen.add(s.starts_at));
  }, [slots.data]);

  async function confirm() {
    if (!user) {
      navigate("/login", { state: { from: location.pathname + location.search } });
      return;
    }
    if (!slot || !service) return;
    setBusy(true);
    setError(null);
    try {
      const appointment = await api<Appointment>("/api/appointments", {
        body: {
          service_id: service.id,
          master_id: slot.master_id,
          starts_at: slot.starts_at,
          notes: notes || null,
          client_id: isAdmin ? clientId : null,
        },
      });
      setDone(appointment);
    } catch (e) {
      setError(errorCode(e));
      setSlot(null);
      slots.reload();
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <main className="container narrow">
        <div className="card stack">
          <h1>{t("book.success")}</h1>
          <p>{f.loc(done.service_name)}, {done.master_name}</p>
          <p><strong>{f.dateTime(done.starts_at)}</strong>, {f.money(done.price)}</p>
          <div className="row">
            {!isAdmin && <Link className="btn btn-primary" to="/me">{t("book.to_mine")}</Link>}
            <button className="btn" onClick={() => { setDone(null); setSlot(null); setNotes(""); slots.reload(); }}>{t("book.another")}</button>
          </div>
        </div>
      </main>
    );
  }

  const categories = [...new Set((services.data ?? []).map((s) => s.category))];

  return (
    <main className="container narrow">
      <Banner image={(service && CATEGORY_PHOTOS[service.category]) || "/images/salon.jpg"} title={t("book.title")} />
      <ErrorNote code={services.error ?? slots.error} />

      <section className="card stack">
        <h2>{t("book.service")}</h2>
        <label className="field">
          <span className="muted">{t("book.pick_service")}</span>
          <select className="input" value={serviceId ?? ""} onChange={(e) => { setServiceId(Number(e.target.value) || null); setMasterId(null); }}>
            <option value="">{t("book.pick_service")}</option>
            {categories.map((c) => (
              <optgroup key={c} label={t(`categories.${c}`, { defaultValue: c })}>
                {services.data!.filter((s) => s.category === c).map((s) => (
                  <option key={s.id} value={s.id}>{f.loc(s.name)} · {s.duration_minutes} {t("common.min")} · {f.money(s.price)}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
      </section>

      {service && (
        <>
          <section className="card stack">
            <h2>{t("book.master")}</h2>
            <div className="chips">
              <button className="chip" aria-pressed={masterId === null} onClick={() => setMasterId(null)}>{t("book.any_master")}</button>
              {(masters.data ?? []).map((m) => (
                <button key={m.id} className="chip" aria-pressed={masterId === m.id} onClick={() => setMasterId(m.id)}>{m.full_name}</button>
              ))}
            </div>
          </section>

          <section className="card stack">
            <h2>{t("book.date")}</h2>
            <div className="chips">
              {days.map((d) => (
                <button key={d} className="chip day-chip" aria-pressed={date === d} onClick={() => setDate(d)}>
                  {f.shortDay(d)}<small>{f.dayMonth(d)}</small>
                </button>
              ))}
            </div>
            <h2>{t("book.time")}</h2>
            {slots.data && uniqueSlots.length === 0 && <p className="muted">{t("book.no_slots")}</p>}
            <div className="chips">
              {uniqueSlots.map((s) => (
                <button key={s.starts_at} className="chip" aria-pressed={slot?.starts_at === s.starts_at} onClick={() => setSlot(s)}>
                  {f.time(s.starts_at)}
                </button>
              ))}
            </div>
          </section>

          {slot && (
            <section className="card stack">
              <h2>{t("book.summary")}</h2>
              <p>
                {f.loc(service.name)}, {slot.master_name}<br />
                <strong>{f.dateTime(slot.starts_at)}</strong>, {service.duration_minutes} {t("common.min")}, {f.money(service.price)}
              </p>
              {isAdmin && (
                <label className="field">
                  <span>{t("book.client")}</span>
                  <select className="input" value={clientId ?? ""} onChange={(e) => setClientId(Number(e.target.value) || null)}>
                    <option value="">{t("book.pick_client")}</option>
                    {(clients.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.full_name} · {c.phone ?? c.email}</option>)}
                  </select>
                </label>
              )}
              <label className="field">
                <span>{t("book.notes")}</span>
                <textarea className="input" rows={2} maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} />
              </label>
              <button className="btn btn-primary" disabled={busy || (isAdmin && !clientId)} onClick={confirm}>
                {t(user ? "book.confirm" : "book.login_to_confirm")}
              </button>
            </section>
          )}
          <ErrorNote code={error} />
        </>
      )}
    </main>
  );
}
