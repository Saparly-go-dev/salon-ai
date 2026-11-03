import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, type Master, type Service } from "../api";
import { useFormat } from "../app-context";
import { ErrorNote, useLoad } from "../components";
import { CATEGORY_PHOTOS } from "../photos";

const CATEGORY_ORDER = ["hair", "nails", "face", "brows", "makeup"];

const AVATAR_COLORS = ["#fde4ef", "#efe4fb", "#ffe6d5", "#f8b4d2", "#dcd3f8"];

function initials(name: string) {
  return name.split(" ").map((part) => part[0]).slice(0, 2).join("");
}

export default function Home() {
  const { t } = useTranslation();
  const f = useFormat();
  const services = useLoad(() => api<Service[]>("/api/services"), []);
  const masters = useLoad(() => api<Master[]>("/api/masters"), []);
  const present = new Set((services.data ?? []).map((s) => s.category));
  const categories = [...CATEGORY_ORDER.filter((c) => present.has(c)), ...[...present].filter((c) => !CATEGORY_ORDER.includes(c))];

  return (
    <main className="container">
      <section className="hero">
        <div className="hero-text">
          <h1>{t("home.title")}</h1>
          <p className="lead">{t("home.lead")}</p>
          <div className="row">
            <Link className="btn btn-primary" to="/book">{t("home.cta_book")}</Link>
            <Link className="btn" to="/assistant">{t("home.cta_chat")}</Link>
          </div>
        </div>
        <img className="hero-photo" src="/images/salon.jpg" alt="" />
      </section>

      <section className="grid-3">
        <Link to="/assistant" className="card stack feature">
          <div className="feature-icon" style={{ background: "var(--accent-wash)" }} aria-hidden="true">💬</div>
          <h3>{t("home.ai_chat_title")}</h3>
          <p className="muted">{t("home.ai_chat_text")}</p>
        </Link>
        <Link to="/nails" className="card stack feature">
          <div className="feature-icon" style={{ background: "var(--lilac)" }} aria-hidden="true">💅</div>
          <h3>{t("home.ai_nails_title")}</h3>
          <p className="muted">{t("home.ai_nails_text")}</p>
        </Link>
        <div className="card stack">
          <div className="feature-icon" style={{ background: "var(--peach)" }} aria-hidden="true">📈</div>
          <h3>{t("home.ai_forecast_title")}</h3>
          <p className="muted">{t("home.ai_forecast_text")}</p>
        </div>
      </section>

      <section className="stack">
        <h2>{t("home.services")}</h2>
        <ErrorNote code={services.error} />
        <div className="service-columns">
          {categories.map((category) => (
            <div className="card" key={category}>
              {CATEGORY_PHOTOS[category] && <img className="card-photo" src={CATEGORY_PHOTOS[category]} alt="" loading="lazy" />}
              <h3>{t(`categories.${category}`, { defaultValue: category })}</h3>
              {services.data!.filter((s) => s.category === category).map((s) => (
                <div className="service-row" key={s.id}>
                  <div className="service-info">
                    <div>{f.loc(s.name)}</div>
                    <div className="muted">{s.duration_minutes} {t("common.min")}</div>
                  </div>
                  <div className="service-end">
                    <strong>{f.money(s.price)}</strong>
                    <Link className="btn btn-small" to={`/book?service=${s.id}`}>{t("home.book_this")}</Link>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </section>

      <section className="stack">
        <h2>{t("home.masters")}</h2>
        <div className="grid-3">
          {(masters.data ?? []).map((m, i) => (
            <div className="card master-card" key={m.id}>
              <div className="avatar" style={{ background: AVATAR_COLORS[i % AVATAR_COLORS.length] }} aria-hidden="true">{initials(m.full_name)}</div>
              <div>
                <strong>{m.full_name}</strong>
                <div className="muted">{f.loc(m.title)}</div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
