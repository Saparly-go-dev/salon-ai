import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ApiError, api, errorCode, type NailResult } from "../api";
import { useApp, useFormat } from "../app-context";
import { AiOffNote, Banner, ErrorNote } from "../components";

const MAX_SIDE = 1568;

/** Фото с телефона часто больше лимита API, поэтому оно уменьшается ещё в браузере. */
async function prepareImage(file: File): Promise<Blob> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new ApiError("image_bad_type", 415);
  }
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new ApiError("image_bad_type", 415))), "image/jpeg", 0.9),
  );
}

export default function Nails() {
  const { t, i18n } = useTranslation();
  const { user, meta, ready } = useApp();
  const f = useFormat();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<NailResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!file) { setPreview(null); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  async function analyze() {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", await prepareImage(file), "photo.jpg");
      form.append("lang", i18n.language);
      setResult(await api<NailResult>("/api/ai/nails", { form }));
    } catch (e) {
      setError(errorCode(e));
    } finally {
      setBusy(false);
    }
  }

  const head = <Banner image="/images/nails-hand.jpg" title={t("nails.title")} lead={t("nails.lead")} />;
  if (!ready) return null;
  if (!meta.ai_enabled) return <main className="container narrow">{head}<AiOffNote /></main>;
  if (!user) {
    return (
      <main className="container narrow">
        {head}
        <div className="card stack">
          <p>{t("nails.login_needed")}</p>
          <div><Link className="btn btn-primary" to="/login" state={{ from: "/nails" }}>{t("nav.login")}</Link></div>
        </div>
      </main>
    );
  }

  const facts = result
    ? ([["shape", result.shape], ["length", result.length], ["finish", result.finish], ["colors", result.colors.join(", ")]] as const).filter(([, v]) => v)
    : [];

  return (
    <main className="container narrow">
      {head}
      <section className="card stack">
        {preview && <img className="photo-preview" src={preview} alt="" />}
        <div className="row">
          <label className="btn">
            {t(file ? "nails.change" : "nails.choose")}
            <input type="file" accept="image/*" hidden onChange={(e) => { setFile(e.target.files?.[0] ?? null); setResult(null); setError(null); }} />
          </label>
          {file && <button className="btn btn-primary" disabled={busy} onClick={analyze}>{t(busy ? "nails.analyzing" : "nails.analyze")}</button>}
        </div>
        <p className="muted">{t("nails.privacy")}</p>
        <ErrorNote code={error} />
      </section>

      {result && !result.is_nail_photo && (
        <section className="card stack">
          <h2>{t("nails.not_nails")}</h2>
          <p>{result.summary}</p>
        </section>
      )}

      {result?.is_nail_photo && (
        <>
          <section className="card stack">
            <div><span className="badge">{t(`nails.kind_${result.photo_kind}`)}</span></div>
            <p>{result.summary}</p>
            {facts.length > 0 && (
              <dl className="facts">
                {facts.map(([key, value]) => (
                  <div key={key}><dt>{t(`nails.${key}`)}</dt><dd>{value}</dd></div>
                ))}
              </dl>
            )}
            {result.design_details.length > 0 && (
              <div><h3>{t("nails.details")}</h3><ul className="plain-list">{result.design_details.map((d) => <li key={d}>{d}</li>)}</ul></div>
            )}
            {result.care_observations.length > 0 && (
              <div><h3>{t("nails.care")}</h3><ul className="plain-list">{result.care_observations.map((d) => <li key={d}>{d}</li>)}</ul></div>
            )}
            {result.see_doctor_note && <p className="note note-info"><strong>{t("nails.doctor")}:</strong> {result.see_doctor_note}</p>}
            <p className="muted">{t("nails.disclaimer")}</p>
          </section>

          {result.recommendations.length > 0 && (
            <section className="card">
              <h2>{t("nails.recommended")}</h2>
              {result.recommendations.map((r) => (
                <div className="service-row" key={r.service_id}>
                  <div className="service-info">
                    <strong>{f.loc(r.name)}</strong> · {f.money(r.price)}
                    <div className="muted">{r.reason}</div>
                  </div>
                  <Link className="btn btn-small" to={`/book?service=${r.service_id}`}>{t("nails.book")}</Link>
                </div>
              ))}
            </section>
          )}
        </>
      )}
    </main>
  );
}
