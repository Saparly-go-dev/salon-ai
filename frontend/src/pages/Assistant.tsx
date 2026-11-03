import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api, errorCode, type ChatResponse, type ChatTurn } from "../api";
import { useApp } from "../app-context";
import { AiOffNote, Banner, ErrorNote } from "../components";

export default function Assistant() {
  const { t, i18n } = useTranslation();
  const { user, meta, ready } = useApp();
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [booked, setBooked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!user || !meta.ai_enabled) return;
    api<ChatResponse>("/api/ai/chat/latest")
      .then((r) => { setConversationId(r.conversation_id); setTurns(r.messages); })
      .catch((e) => setError(errorCode(e)));
  }, [user, meta.ai_enabled]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [turns, busy]);

  async function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    setBooked(false);
    setText("");
    setTurns((current) => [...current, { role: "user", text: trimmed }]);
    try {
      const response = await api<ChatResponse>("/api/ai/chat", {
        body: { message: trimmed, lang: i18n.language, conversation_id: conversationId },
      });
      setConversationId(response.conversation_id);
      setTurns(response.messages);
      setBooked(response.booked);
    } catch (e) {
      setError(errorCode(e));
    } finally {
      setBusy(false);
    }
  }

  function startNew() {
    setConversationId(null);
    setTurns([]);
    setBooked(false);
    setError(null);
  }

  const head = (
    <>
      <Banner image="/images/face.jpg" title={t("chat.title")} lead={t("chat.lead")} />
      {user && meta.ai_enabled && turns.length > 0 && <div><button className="btn btn-small" onClick={startNew}>{t("chat.new")}</button></div>}
    </>
  );

  if (!ready) return null;
  if (!meta.ai_enabled) return <main className="container narrow">{head}<AiOffNote /></main>;
  if (!user) {
    return (
      <main className="container narrow">
        {head}
        <div className="card stack">
          <p>{t("chat.login_needed")}</p>
          <div><Link className="btn btn-primary" to="/login" state={{ from: "/assistant" }}>{t("nav.login")}</Link></div>
        </div>
      </main>
    );
  }

  const submit = (e: FormEvent) => { e.preventDefault(); send(text); };

  return (
    <main className="container narrow">
      {head}
      <section className="card stack">
        <div className="chat" ref={logRef} aria-live="polite">
          {turns.length === 0 && <div className="bubble bubble-assistant">{t("chat.greeting")}</div>}
          {turns.map((turn, i) => <div key={i} className={`bubble bubble-${turn.role}`}>{turn.text}</div>)}
          {busy && <div className="bubble bubble-assistant muted">{t("chat.thinking")}</div>}
        </div>
        {turns.length === 0 && (
          <div className="chips">
            {(["s1", "s2", "s3"] as const).map((k) => (
              <button key={k} className="chip" onClick={() => send(t(`chat.${k}`))}>{t(`chat.${k}`)}</button>
            ))}
          </div>
        )}
        {booked && <p className="note note-good">{t("chat.booked")} <Link to="/me">{t("chat.to_mine")}</Link></p>}
        <ErrorNote code={error} />
        <form className="chat-form" onSubmit={submit}>
          <input className="input" maxLength={2000} value={text} placeholder={t("chat.placeholder")} aria-label={t("chat.placeholder")} onChange={(e) => setText(e.target.value)} />
          <button className="btn btn-primary" disabled={busy || !text.trim()}>{t("chat.send")}</button>
        </form>
      </section>
    </main>
  );
}
