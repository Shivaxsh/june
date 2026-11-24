"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getJobs, liveQuestions, teachAnswer, type JobQuestion } from "@/lib/mail";

type Props = { active: boolean; onAnnounce: (text: string) => void };

/** A recruiter question June is waiting on while she holds a Naukri application open. She also says it out loud and
 * sends a notification; answering here saves it (she reuses it for similar questions) and she types it into Naukri. */
export default function JobQuestionCard({ active, onAnnounce }: Props) {
  const [questions, setQuestions] = useState<JobQuestion[]>([]);
  const [now, setNow] = useState(() => Date.now());
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const alive = useRef(true);
  const live = useRef(liveQuestions());
  const load = useCallback(async () => {
    const token = live.current.begin();
    try {
      const state = await getJobs();
      if (!alive.current) return;
      const view = live.current.accept(token, state.questions, Date.now());
      if (!view) return;  // started before an answer was sent: out of date
      setQuestions(view.visible);
      for (const q of view.announce) onAnnounce(`June needs your answer: ${q.question}`);
    } catch { /* the Email & jobs panel shows connection problems */ }
  }, [onAnnounce]);
  useEffect(() => {
    alive.current = true; void load();
    // While an application runs, check often; otherwise occasionally (a question can also wait from an earlier run).
    const poll = setInterval(() => void load(), active ? 2000 : 15000);
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => { alive.current = false; clearInterval(poll); clearInterval(tick); };
  }, [active, load]);
  async function answer(q: JobQuestion, value: string) {
    if (!live.current.answer(q, Date.now())) return;  // synchronous: a second tap while sending does nothing
    setBusy(q.key); setError("");
    setQuestions(list => list.filter(x => !(x.key === q.key && x.job === q.job && x.waitingUntil === q.waitingUntil)));
    try {
      await teachAnswer(q.question, value);
      live.current.settle(q);
      onAnnounce("Thanks. June is typing that into Naukri and will remember it for similar questions.");
    } catch (failure) {
      live.current.failed(q);
      if (alive.current) setError(failure instanceof Error ? failure.message : "June could not save that answer.");
      void load();
    } finally { if (alive.current) setBusy(""); }
  }
  const shown = questions.filter(q => q.waitingUntil !== null && q.waitingUntil > now);
  if (!shown.length) return null;
  // A region, not an alert: June announces each question once; the ticking countdown is not read out.
  return <section className="job-question-card hud-panel" role="region" aria-label="June needs your answer">
    {shown.map(q => {  // one card row per waiting instance
      const left = Math.max(0, Math.round(((q.waitingUntil ?? now) - now) / 1000));
      return <div key={`${q.key}|${q.job}|${q.waitingUntil}`} className="integration-group">
        <p className="plan-step-meta">June needs your answer{q.title ? ` · ${q.title}` : ""} <span aria-hidden="true">waiting {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}</span></p>
        <p><strong>{q.question}</strong></p>
        {q.options.length > 0
          ? <div className="timer-buttons">{q.options.map(option => <button key={option} type="button" className="quiet-button" disabled={!!busy} onClick={() => void answer(q, option)}>{option}</button>)}</div>
          : <form className="timer-buttons" onSubmit={event => { event.preventDefault(); void answer(q, draft[q.key] ?? ""); }}>
              <input type="text" maxLength={300} aria-label={`Your answer to: ${q.question}`} value={draft[q.key] ?? ""}
                onChange={event => { const value = event.target.value; setDraft(d => ({ ...d, [q.key]: value })); }} />
              <button type="submit" className="quiet-button" disabled={!!busy || !(draft[q.key] ?? "").trim()}>Send answer</button>
            </form>}
        <p className="handsfree-note">June keeps the application open while she waits, types your answer into Naukri, and remembers it for similar questions.</p>
      </div>;
    })}
    {error && <p className="error-notice" role="alert">{error}</p>}
  </section>;
}
