"use client";
import { useEffect, useId, useState } from "react";
import { acknowledgeTimer, cancelTimer, durationWords, remainingMs, timerPhrase, timerText, type Timer } from "@/lib/timers";

/** One timer on the server's clock. The card never ends a timer itself; at 0:00 it waits for the server. */
export default function TimerCard({ timer, serverNow, receivedAt, onChange, onHear, compact = false }: {
  timer: Timer; serverNow: number; receivedAt: number; onChange(timer: Timer, serverNow: number): void; onHear?(phrase: string): void; compact?: boolean;
}) {
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const titleId = useId();
  const active = timer.status === "active";
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [active]);
  const left = remainingMs(timer, serverNow, receivedAt, now);
  const name = timer.label.trim() || `${durationWords(timer.durationSeconds)} timer`;
  async function act(kind: "cancel" | "acknowledge") {
    setBusy(true); setError("");
    try { const reply = await (kind === "cancel" ? cancelTimer(timer) : acknowledgeTimer(timer)); onChange(reply.timer, reply.serverNow); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "June could not reach Timers."); }
    finally { setBusy(false); }
  }
  return <section className={`timer-card is-${timer.status}${compact ? " is-compact" : ""}`} role="group" aria-labelledby={titleId}>
    <div className="timer-head"><span className="hud-label" id={titleId}>{name}</span>
      <span className="timer-clock" aria-label={active ? `${timerText(timer, left)} left` : timerText(timer, left)}>{timerText(timer, left)}</span></div>
    {active && <div className="timer-buttons"><button type="button" className="quiet-button" disabled={busy} onClick={() => void act("cancel")}>Cancel</button></div>}
    {timer.status === "completed" && <div className="timer-buttons">
      {onHear && <button type="button" className="quiet-button" onClick={() => onHear(timerPhrase(timer))}>Hear again</button>}
      <button type="button" className="quiet-button" disabled={busy} onClick={() => void act("acknowledge")}>Dismiss</button>
    </div>}
    {error && <p className="error-notice" role="alert">{error}</p>}
  </section>;
}
