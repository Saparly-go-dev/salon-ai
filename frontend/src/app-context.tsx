import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { api, getToken, setToken, type Localized, type Meta, type User } from "./api";

type AppState = {
  user: User | null;
  meta: Meta;
  ready: boolean;
  signIn: (token: string, user: User) => void;
  signOut: () => void;
};

const AppContext = createContext<AppState | null>(null);
const DEFAULT_META: Meta = { timezone: "Asia/Ashgabat", currency: "TMT", ai_enabled: false };

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [meta, setMeta] = useState<Meta>(DEFAULT_META);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const loadUser = getToken()
      ? api<User>("/api/auth/me").then(setUser).catch(() => setToken(null))
      : Promise.resolve();
    const loadMeta = api<Meta>("/api/meta").then(setMeta).catch(() => undefined);
    Promise.all([loadUser, loadMeta]).finally(() => setReady(true));
  }, []);

  const signIn = useCallback((token: string, nextUser: User) => {
    setToken(token);
    setUser(nextUser);
  }, []);
  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, meta, ready, signIn, signOut }), [user, meta, ready, signIn, signOut]);
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp must be used inside AppProvider");
  return value;
}

/** Даты и суммы показываются по часовому поясу салона, а не браузера. */
export function useFormat() {
  const { t, i18n } = useTranslation();
  const { meta } = useApp();
  const months = t("months", { returnObjects: true }) as string[];
  const weekdays = t("weekdays", { returnObjects: true }) as string[];
  const short = t("weekdays_short", { returnObjects: true }) as string[];

  const parts = (iso: string) => {
    const values = new Intl.DateTimeFormat("en-CA", {
      timeZone: meta.timezone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    }).formatToParts(new Date(iso));
    const get = (type: string) => values.find((p) => p.type === type)?.value ?? "";
    return { date: `${get("year")}-${get("month")}-${get("day")}`, time: `${get("hour")}:${get("minute")}` };
  };
  const weekdayIndex = (date: string) => (new Date(`${date}T12:00:00Z`).getUTCDay() + 6) % 7;
  const dayMonth = (date: string) => `${Number(date.slice(8, 10))} ${months[Number(date.slice(5, 7)) - 1]}`;

  return {
    loc: (value: Localized) => value[i18n.language] || value.ru || Object.values(value)[0] || "",
    time: (iso: string) => parts(iso).time,
    localDate: (iso: string) => parts(iso).date,
    dayMonth,
    longDate: (date: string) => `${weekdays[weekdayIndex(date)]}, ${dayMonth(date)}`,
    shortDay: (date: string) => short[weekdayIndex(date)],
    dateTime: (iso: string) => {
      const p = parts(iso);
      return `${short[weekdayIndex(p.date)]}, ${dayMonth(p.date)}, ${p.time}`;
    },
    money: (value: number) => `${Math.round(value).toLocaleString("ru-RU").replace(/ /g, " ")} ${meta.currency}`,
    number: (value: number) => Math.round(value).toLocaleString("ru-RU").replace(/ /g, " "),
    today: () => parts(new Date().toISOString()).date,
  };
}

export function addDays(date: string, days: number): string {
  const value = new Date(`${date}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}
