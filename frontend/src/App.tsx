import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { Role } from "./api";
import { useApp } from "./app-context";
import { Footer } from "./components";
import { LANGUAGES, setLanguage } from "./i18n";
import Assistant from "./pages/Assistant";
import Book from "./pages/Book";
import Home from "./pages/Home";
import Login from "./pages/Login";
import MyAppointments from "./pages/MyAppointments";
import Nails from "./pages/Nails";
import Clients from "./pages/admin/Clients";
import Dashboard from "./pages/admin/Dashboard";
import Masters from "./pages/admin/Masters";
import Schedule from "./pages/admin/Schedule";
import Services from "./pages/admin/Services";

function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, ready } = useApp();
  const location = useLocation();
  if (!ready) return null;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname + location.search }} replace />;
  if (!roles.includes(user.role)) return <Navigate to="/" replace />;
  return children;
}

function Header() {
  const { t, i18n } = useTranslation();
  const { user, signOut } = useApp();
  const navigate = useNavigate();

  const staffLinks =
    user?.role === "admin"
      ? [
          ["/admin", t("admin_nav.dashboard")],
          ["/admin/schedule", t("admin_nav.schedule")],
          ["/admin/services", t("admin_nav.services")],
          ["/admin/masters", t("admin_nav.masters")],
          ["/admin/clients", t("admin_nav.clients")],
          ["/book", t("nav.book")],
        ]
      : user?.role === "master"
        ? [["/admin/schedule", t("admin_nav.schedule")]]
        : null;
  const links = staffLinks ?? [
    ["/book", t("nav.book")],
    ["/assistant", t("nav.assistant")],
    ["/nails", t("nav.nails")],
    ...(user ? [["/me", t("nav.mine")]] : []),
  ];

  return (
    <header className="header">
      <div className="header-inner">
        <Link to="/" className="logo">{t("brand")}</Link>
        <nav className="nav">
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/admin"}>{label}</NavLink>
          ))}
        </nav>
        <div className="header-tools">
          <div className="lang" role="group" aria-label="Language">
            {LANGUAGES.map((l) => (
              <button key={l.code} aria-pressed={i18n.language === l.code} onClick={() => setLanguage(l.code)}>{l.label}</button>
            ))}
          </div>
          {user ? (
            <button className="btn btn-small" onClick={() => { signOut(); navigate("/"); }}>{t("nav.logout")}</button>
          ) : (
            <Link className="btn btn-small" to="/login">{t("nav.login")}</Link>
          )}
        </div>
      </div>
    </header>
  );
}

export default function App() {
  return (
    <>
      <Header />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/book" element={<Book />} />
        <Route path="/login" element={<Login />} />
        <Route path="/assistant" element={<Assistant />} />
        <Route path="/nails" element={<Nails />} />
        <Route path="/me" element={<RequireRole roles={["client", "master", "admin"]}><MyAppointments /></RequireRole>} />
        <Route path="/admin" element={<RequireRole roles={["admin"]}><Dashboard /></RequireRole>} />
        <Route path="/admin/schedule" element={<RequireRole roles={["admin", "master"]}><Schedule /></RequireRole>} />
        <Route path="/admin/services" element={<RequireRole roles={["admin"]}><Services /></RequireRole>} />
        <Route path="/admin/masters" element={<RequireRole roles={["admin"]}><Masters /></RequireRole>} />
        <Route path="/admin/clients" element={<RequireRole roles={["admin"]}><Clients /></RequireRole>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <Footer />
    </>
  );
}
