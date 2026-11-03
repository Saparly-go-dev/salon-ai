import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type Forecast, type ForecastPoint, type Kpis, type Overview } from "../../api";
import { useFormat } from "../../app-context";
import { ErrorNote, useLoad } from "../../components";

const AXIS = { fontSize: 12, fill: "var(--muted)" };
const LEVEL_MARK: Record<ForecastPoint["level"], string> = { high: "▲", normal: "●", low: "▼" };

function TableToggle({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <div className="stack">
      <div><button className="link-btn" aria-expanded={open} onClick={() => setOpen(!open)}>{t(open ? "dashboard.hide_table" : "dashboard.show_table")}</button></div>
      {open && <div className="table-wrap">{children}</div>}
    </div>
  );
}

function Kpi({ label, value, current, previous, upIsGood }: { label: string; value: string; current: number; previous: number; upIsGood: boolean }) {
  const { t } = useTranslation();
  const change = previous ? ((current - previous) / previous) * 100 : null;
  const good = change !== null && change !== 0 && change > 0 === upIsGood;
  return (
    <div className="card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {change !== null && (
        <div className="kpi-delta">
          <span className={change === 0 ? "" : good ? "delta-good" : "delta-bad"}>{change > 0 ? "+" : ""}{change.toFixed(1)}%</span> {t("dashboard.vs_prev")}
        </div>
      )}
    </div>
  );
}

function KpiRow({ kpis, previous }: { kpis: Kpis; previous: Kpis }) {
  const { t } = useTranslation();
  const f = useFormat();
  return (
    <section className="kpis">
      <Kpi label={t("dashboard.revenue")} value={f.money(kpis.revenue)} current={kpis.revenue} previous={previous.revenue} upIsGood />
      <Kpi label={t("dashboard.completed")} value={f.number(kpis.completed)} current={kpis.completed} previous={previous.completed} upIsGood />
      <Kpi label={t("dashboard.avg_ticket")} value={f.money(kpis.avg_ticket)} current={kpis.avg_ticket} previous={previous.avg_ticket} upIsGood />
      <Kpi label={t("dashboard.new_clients")} value={f.number(kpis.new_clients)} current={kpis.new_clients} previous={previous.new_clients} upIsGood />
      <Kpi label={t("dashboard.cancel_rate")} value={`${kpis.cancel_rate}%`} current={kpis.cancel_rate} previous={previous.cancel_rate} upIsGood={false} />
      <Kpi label={t("dashboard.no_show_rate")} value={`${kpis.no_show_rate}%`} current={kpis.no_show_rate} previous={previous.no_show_rate} upIsGood={false} />
    </section>
  );
}

function ForecastSection({ data }: { data: Extract<Forecast, { available: true }> }) {
  const { t } = useTranslation();
  const f = useFormat();
  const rows = [
    ...data.history.map((h) => ({ date: h.date, actual: h.appointments, predicted: null as number | null, band: null as [number, number] | null })),
    ...data.forecast.map((p) => ({ date: p.date, actual: null as number | null, predicted: p.appointments, band: [p.low, p.high] as [number, number] })),
  ];
  const { model, baseline, holdout_days } = data.metrics;
  const improvement = baseline.mae > 0 ? Math.round((1 - model.mae / baseline.mae) * 100) : 0;

  return (
    <>
      <section className="card stack">
        <div>
          <h2>{t("dashboard.forecast_title")}</h2>
          <p className="muted">{t("dashboard.forecast_sub")}</p>
        </div>
        <div className="legend">
          <span className="key"><i style={{ background: "var(--series-1)" }} />{t("dashboard.history")}</span>
          <span className="key"><i style={{ background: "var(--series-2)" }} />{t("dashboard.forecast")}</span>
          <span className="key"><i className="band" style={{ background: "var(--series-2)" }} />{t("dashboard.band")}</span>
        </div>
        <div className="chart">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="var(--grid)" vertical={false} />
              <XAxis dataKey="date" tick={AXIS} tickLine={false} axisLine={{ stroke: "var(--axis)" }} tickFormatter={f.dayMonth} minTickGap={36} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} width={36} allowDecimals={false} />
              <ReferenceLine x={data.forecast[0].date} stroke="var(--axis)" />
              <Tooltip
                content={({ active, payload }) => {
                  const row = payload?.[0]?.payload as (typeof rows)[number] | undefined;
                  if (!active || !row) return null;
                  return (
                    <div className="tooltip">
                      <b>{f.longDate(row.date)}</b>
                      {row.actual !== null && <div>{t("dashboard.history")}: {row.actual}</div>}
                      {row.predicted !== null && <div>{t("dashboard.forecast")}: {row.predicted}</div>}
                      {row.band && <div className="muted">{t("dashboard.band")}: {row.band[0]}–{row.band[1]}</div>}
                    </div>
                  );
                }}
              />
              <Area dataKey="band" stroke="none" fill="var(--series-2)" fillOpacity={0.12} isAnimationActive={false} connectNulls={false} activeDot={false} />
              <Line dataKey="actual" stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls={false} />
              <Line dataKey="predicted" stroke="var(--series-2)" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <TableToggle>
          <table>
            <thead><tr><th>{t("dashboard.date")}</th><th className="num">{t("dashboard.history")}</th><th className="num">{t("dashboard.forecast")}</th><th className="num">{t("dashboard.band")}</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.date}><td>{f.dayMonth(r.date)}</td><td className="num">{r.actual ?? ""}</td><td className="num">{r.predicted ?? ""}</td><td className="num">{r.band ? `${r.band[0]}–${r.band[1]}` : ""}</td></tr>
              ))}
            </tbody>
          </table>
        </TableToggle>
      </section>

      <section className="card stack">
        <h2>{t("dashboard.plan_title")}</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t("dashboard.date")}</th><th className="num">{t("dashboard.predicted")}</th><th className="num">{t("dashboard.booked")}</th><th className="num">{t("dashboard.exp_revenue")}</th><th>{t("dashboard.advice")}</th></tr></thead>
            <tbody>
              {data.forecast.slice(0, 7).map((p) => (
                <tr key={p.date}>
                  <td>{f.shortDay(p.date)}, {f.dayMonth(p.date)}</td>
                  <td className="num">{p.appointments.toFixed(0)}</td>
                  <td className="num">{p.booked}</td>
                  <td className="num">{f.money(p.revenue)}</td>
                  <td><span className="level"><i aria-hidden="true">{LEVEL_MARK[p.level]}</i>{t(`dashboard.level_${p.level}`)} ({p.load.toFixed(0)}%)</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card stack">
        <h2>{t("dashboard.model_title")}</h2>
        <p className="muted">{t("dashboard.model_text", { days: holdout_days })}</p>
        <div className="table-wrap">
          <table>
            <thead><tr><th /><th className="num">MAE</th><th className="num">RMSE</th><th className="num">wMAPE</th></tr></thead>
            <tbody>
              <tr><td>{t("dashboard.model")}</td><td className="num">{model.mae}</td><td className="num">{model.rmse}</td><td className="num">{model.wmape}%</td></tr>
              <tr><td>{t("dashboard.baseline")}</td><td className="num">{baseline.mae}</td><td className="num">{baseline.rmse}</td><td className="num">{baseline.wmape}%</td></tr>
            </tbody>
          </table>
        </div>
        <p><strong>{improvement > 0 ? t("dashboard.better", { pct: improvement }) : t("dashboard.worse")}</strong></p>
      </section>
    </>
  );
}

function Heatmap({ cells }: { cells: Overview["heatmap"] }) {
  const { t } = useTranslation();
  const short = t("weekdays_short", { returnObjects: true }) as string[];
  const seen = cells.map((c) => c.hour);
  const first = seen.length ? Math.min(...seen) : 9;
  const last = seen.length ? Math.max(...seen) : 18;
  const hours = Array.from({ length: last - first + 1 }, (_, i) => first + i);
  const counts = new Map(cells.map((c) => [`${c.weekday}-${c.hour}`, c.count]));
  const max = Math.max(1, ...cells.map((c) => c.count));
  const shade = (n: number) => (n === 0 ? 0 : Math.min(5, Math.ceil((n / max) * 5)));

  return (
    <>
    <div className="table-wrap">
      <div className="heatmap" style={{ gridTemplateColumns: `28px repeat(${hours.length}, 1fr)` }} role="img" aria-label={t("dashboard.heatmap_sub")}>
        <span />
        {hours.map((h) => <span className="heat-label" key={h}>{h}</span>)}
        {short.map((day, weekday) => (
          <div key={day} style={{ display: "contents" }}>
            <span className="heat-label">{day}</span>
            {hours.map((hour) => {
              const count = counts.get(`${weekday}-${hour}`) ?? 0;
              return <div key={hour} className="heat-cell" style={{ background: `var(--heat-${shade(count)})` }} title={`${day}, ${hour}:00: ${count}`} />;
            })}
          </div>
        ))}
      </div>
    </div>
    <div className="heat-scale">
      <span>{t("dashboard.fewer")}</span>
      {[1, 2, 3, 4, 5].map((n) => <i key={n} style={{ background: `var(--heat-${n})` }} />)}
      <span>{t("dashboard.more")}</span>
    </div>
    <TableToggle>
      <table>
        <thead><tr><th>{t("dashboard.day")}</th>{hours.map((h) => <th className="num" key={h}>{h}</th>)}</tr></thead>
        <tbody>
          {short.map((day, weekday) => (
            <tr key={day}><td>{day}</td>{hours.map((h) => <td className="num" key={h}>{counts.get(`${weekday}-${h}`) ?? 0}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </TableToggle>
    </>
  );
}

export default function Dashboard() {
  const { t } = useTranslation();
  const f = useFormat();
  const [days, setDays] = useState(30);
  const overview = useLoad(() => api<Overview>(`/api/admin/analytics/overview?days=${days}`), [days]);
  const forecast = useLoad(() => api<Forecast>("/api/admin/analytics/forecast"), []);
  const data = overview.data;

  return (
    <main className="container">
      <div className="page-head">
        <h1>{t("dashboard.title")}</h1>
        <div className="chips">
          {[7, 30, 90].map((n) => (
            <button key={n} className="chip" aria-pressed={days === n} onClick={() => setDays(n)}>{t("dashboard.days", { n })}</button>
          ))}
        </div>
      </div>
      <ErrorNote code={overview.error ?? forecast.error} />

      {data && <KpiRow kpis={data.kpis} previous={data.previous_kpis} />}
      {forecast.data?.available && <ForecastSection data={forecast.data} />}
      {forecast.data && !forecast.data.available && <p className="note note-info">{t("dashboard.not_enough", { n: forecast.data.min_history_days })}</p>}

      {data && (
        <>
          <section className="card stack">
            <h2>{t("dashboard.revenue_title")}</h2>
            <div className="chart chart-short">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.daily} margin={{ top: 8, right: 12, left: 0, bottom: 0 }} barCategoryGap={2}>
                  <CartesianGrid stroke="var(--grid)" vertical={false} />
                  <XAxis dataKey="date" tick={AXIS} tickLine={false} axisLine={{ stroke: "var(--axis)" }} tickFormatter={f.dayMonth} minTickGap={36} />
                  <YAxis tick={AXIS} tickLine={false} axisLine={false} width={48} />
                  <Tooltip
                    cursor={{ fill: "var(--grid)", fillOpacity: 0.5 }}
                    content={({ active, payload }) => {
                      const row = payload?.[0]?.payload as Overview["daily"][number] | undefined;
                      if (!active || !row) return null;
                      return (
                        <div className="tooltip">
                          <b>{f.longDate(row.date)}</b>
                          <div>{t("dashboard.revenue")}: {f.money(row.revenue)}</div>
                          <div>{t("dashboard.visits")}: {row.appointments}</div>
                        </div>
                      );
                    }}
                  />
                  <Bar dataKey="revenue" fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <TableToggle>
              <table>
                <thead><tr><th>{t("dashboard.date")}</th><th className="num">{t("dashboard.visits")}</th><th className="num">{t("dashboard.revenue")}</th></tr></thead>
                <tbody>{data.daily.map((d) => <tr key={d.date}><td>{f.dayMonth(d.date)}</td><td className="num">{d.appointments}</td><td className="num">{f.money(d.revenue)}</td></tr>)}</tbody>
              </table>
            </TableToggle>
          </section>

          <div className="grid-2">
            <section className="card stack">
              <h2>{t("dashboard.services_title")}</h2>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>{t("dashboard.service")}</th><th className="num">{t("dashboard.visits")}</th><th className="num">{t("dashboard.revenue")}</th></tr></thead>
                  <tbody>{data.top_services.map((s) => <tr key={s.id}><td>{f.loc(s.name)}</td><td className="num">{s.count}</td><td className="num">{f.money(s.revenue)}</td></tr>)}</tbody>
                </table>
              </div>
            </section>
            <section className="card stack">
              <h2>{t("dashboard.masters_title")}</h2>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>{t("dashboard.master")}</th><th className="num">{t("dashboard.visits")}</th><th>{t("dashboard.utilization")}</th><th className="num">%</th></tr></thead>
                  <tbody>
                    {data.masters.map((m) => (
                      <tr key={m.id}>
                        <td>{m.name}</td>
                        <td className="num">{m.appointments}</td>
                        <td style={{ verticalAlign: "middle" }}><div className="meter"><div style={{ width: `${Math.min(100, m.utilization)}%` }} /></div></td>
                        <td className="num">{m.utilization}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <section className="card stack">
            <div>
              <h2>{t("dashboard.heatmap_title")}</h2>
              <p className="muted">{t("dashboard.heatmap_sub")}</p>
            </div>
            <Heatmap cells={data.heatmap} />
          </section>
        </>
      )}
    </main>
  );
}
