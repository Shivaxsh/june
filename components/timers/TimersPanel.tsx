"use client";
import { useState } from "react";
import { createTimer, durationWords } from "@/lib/timers";
import TimerCard from "./TimerCard";
import type { Timers } from "./useTimers";

const PRESETS = [1, 5, 10, 25];
/** Systems → Timers: start one, see what's running or finished, and recent history. */
export default function TimersPanel({ timers, onHear, onAnnounce }: { timers: Timers; onHear(phrase: string): void; onAnnounce(text: string): void }) {
  const [minutes, setMinutes] = useState("5");
  const [seconds, setSeconds] = useState("0");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { state, receivedAt } = timers;
  const live = state?.timers.filter(t => t.status === "active" || t.status === "completed") ?? [];
  const past = state?.timers.filter(t => t.status === "cancelled" || t.status === "acknowledged").slice(0, 5) ?? [];
  async function start(total: number) {
    setBusy(true); setError("");
    try { const reply = await createTimer({ durationSeconds: total, label }); timers.upsert(reply.timer, reply.serverNow); setLabel(""); onAnnounce(`Timer started: ${reply.timer.label.trim() || `${durationWords(total)} timer`}.`); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "June could not start that timer."); }
    finally { setBusy(false); }
  }
  const total = (Number(minutes) || 0) * 60 + (Number(seconds) || 0);
  return <section className="timers-panel" aria-label="Timers">
    <span className="eyebrow">Timers · kept on this Mac</span>
    <h2>Set a <em>timer.</em></h2>
    <p>June keeps time on her local server, so a timer still finishes if this page is closed. If this page is open and her voice is on, she says it once when she is free to speak. Otherwise the finished card waits here, with Hear again. There is no Mac notification.</p>
    <form className="timer-form" onSubmit={event => { event.preventDefault(); void start(total); }}>
      <label>Minutes<input type="number" inputMode="numeric" min={0} max={1440} value={minutes} onChange={e => setMinutes(e.target.value)} /></label>
      <label>Seconds<input type="number" inputMode="numeric" min={0} max={59} value={seconds} onChange={e => setSeconds(e.target.value)} /></label>
      <label className="timer-name">Name (optional)<input type="text" maxLength={80} value={label} placeholder="tea, stretch, laundry…" onChange={e => setLabel(e.target.value)} /></label>
      <button type="submit" className="quiet-button" disabled={busy || total < 1 || total > 86400}>Start timer</button>
    </form>
    <div className="timer-presets" role="group" aria-label="Quick timers">{PRESETS.map(m => <button key={m} type="button" className="quiet-button" disabled={busy} onClick={() => void start(m * 60)}>{m} min</button>)}</div>
    {(error || timers.error) && <p className="error-notice" role="alert">{error || timers.error}</p>}
    {state && live.map(t => <TimerCard key={t.id} timer={t} serverNow={state.serverNow} receivedAt={receivedAt} onChange={timers.upsert} onHear={onHear} />)}
    {state && !live.length && <p className="handsfree-note">No timers running.</p>}
    {past.length > 0 && <ul className="hands-history" aria-label="Recent timers">{past.map(t => <li key={t.id}><span>{t.label || "Timer"}</span><span>{t.status === "cancelled" ? "Cancelled" : "Finished · dismissed"}</span><time dateTime={new Date(t.createdAt).toISOString()}>{new Date(t.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></li>)}</ul>}
  </section>;
}
