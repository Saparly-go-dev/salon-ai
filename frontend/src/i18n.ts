import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en";
import ru from "./locales/ru";
import tk from "./locales/tk";

export const LANGUAGES = [
  { code: "tk", label: "TM" },
  { code: "ru", label: "RU" },
  { code: "en", label: "EN" },
] as const;

export type Lang = (typeof LANGUAGES)[number]["code"];

const STORAGE_KEY = "salon.lang";

function initialLanguage(): Lang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "tk" || stored === "ru" || stored === "en") return stored;
  } catch {
    // Хранилище браузера может быть недоступно
  }
  const browser = navigator.language.slice(0, 2);
  return browser === "tk" || browser === "en" ? browser : "ru";
}

export function setLanguage(lang: Lang) {
  i18n.changeLanguage(lang);
  document.documentElement.lang = lang;
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // Выбор языка просто не сохранится
  }
}

i18n.use(initReactI18next).init({
  resources: { tk: { translation: tk }, ru: { translation: ru }, en: { translation: en } },
  lng: initialLanguage(),
  fallbackLng: "ru",
  interpolation: { escapeValue: false },
});
document.documentElement.lang = i18n.language;

export default i18n;
