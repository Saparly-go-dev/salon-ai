import { useEffect, useState, type DependencyList } from "react";
import { useTranslation } from "react-i18next";
import { errorCode } from "./api";
import { PHOTO_CREDITS } from "./photos";

export function ErrorNote({ code }: { code: string | null }) {
  const { t } = useTranslation();
  if (!code) return null;
  return <p className="note note-error" role="alert">{t(`errors.${code}`, { defaultValue: t("errors.generic") })}</p>;
}

export function Banner({ image, title, lead }: { image: string; title: string; lead?: string }) {
  return (
    <div className="banner" style={{ backgroundImage: `url(${image})` }}>
      <div className="banner-text">
        <h1>{title}</h1>
        {lead && <p>{lead}</p>}
      </div>
    </div>
  );
}

export function Footer() {
  const { t } = useTranslation();
  return (
    <footer className="footer">
      <details>
        <summary>{t("photo_credits")}</summary>
        <ul>
          {PHOTO_CREDITS.map((c) => (
            <li key={c.file}><a href={c.url} target="_blank" rel="noreferrer">{c.title}</a>, {c.author}, {c.license}</li>
          ))}
        </ul>
      </details>
    </footer>
  );
}

export function AiOffNote() {
  const { t } = useTranslation();
  return (
    <div className="note note-info">
      <strong>{t("ai.off_title")}</strong>
      <p>{t("ai.off_text")}</p>
    </div>
  );
}

/** Загрузка данных при монтировании и смене зависимостей. Устаревшие ответы отбрасываются. */
export function useLoad<T>(load: () => Promise<T>, deps: DependencyList) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let stale = false;
    setError(null);
    load()
      .then((value) => { if (!stale) setData(value); })
      .catch((e) => { if (!stale) setError(errorCode(e)); });
    return () => { stale = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version]);

  return { data, error, reload: () => setVersion((v) => v + 1), setData };
}
