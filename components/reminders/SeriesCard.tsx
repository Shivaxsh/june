"use client";
import { useId, useRef, useState } from "react";
import { cancelSeries, describeRule, formatDue, isConflict, pauseSeries, resumeSeries, skipNextSeries, updateSeries, type Reminder, type Series } from "@/lib/reminders";

const DAYS = [[1, "Mon"], [2, "Tue"], [3, "Wed"], [4, "Thu"], [5, "Fri"], [6, "Sat"], [7, "Sun"]] as const;

/**
 * A repeating reminder. Its next time comes from the series itself (no future reminder exists yet).
 * Every action is bound to the revision shown (Skip next also to the date shown); a 409 refreshes.
 */
export default function SeriesCard({ series, serverNow, onChange, onRefresh, compact = false }: {
  series: Series; serverNow: number; onChange(series: Series, serverNow: number, reminder: Reminder | null): void; onRefresh?(): void; compact?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // The series the edit draft was opened from: a newer copy arriving meanwhile never rebinds it.
  const [base, setBase] = useState<Series | null>(null);
  const [text, setText] = useState("");
  const [clock, setClock] = useState("");
  const [rule, setRule] = useState<"daily" | "weekly">("daily");
  const [days, setDays] = useState<number[]>([]);
  const inFlight = useRef(false);
  const titleId = useId();
  const live = series.status !== "cancelled";
  async function run(change: () => Promise<{ series: Series; serverNow: number; reminder: Reminder | null }>) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try { const reply = await change(); onChange(reply.series, reply.serverNow, reply.reminder); setBase(null); }
    catch (failure) {
      if (isConflict(failure)) { setError("This repeating reminder changed somewhere else. June refreshed it; check it and try again."); setBase(null); onRefresh?.(); }
      else setError(failure instanceof Error ? failure.message : "June could not reach Reminders.");
    }
    finally { inFlight.current = false; setBusy(false); }
  }
  function startEdit() { setBase(series); setText(series.text); setClock(series.localTime); setRule(series.rule); setDays(series.weekdays); setError(""); }
  // Only what changed, measured against the base the draft was opened from.
  function changesFrom(edit: Series) {
    return {
      ...(text.trim() !== edit.text ? { text } : {}), ...(clock !== edit.localTime ? { localTime: clock } : {}),
      ...(rule !== edit.rule || (rule === "weekly" && days.join() !== edit.weekdays.join()) ? { rule, ...(rule === "weekly" ? { weekdays: days } : {}) } : {}),
    };
  }
  const status = { active: "Repeating", paused: "Paused", cancelled: "Stopped" }[series.status];
  return <section className={`reminder-card series-card is-series-${series.status}${compact ? " is-compact" : ""}`} role="group" aria-labelledby={titleId}>
    <div className="timer-head"><span className="hud-label">{status}</span><span className="reminder-due">{describeRule(series)}</span></div>
    <p className="reminder-text" id={titleId}>{series.text}</p>
    <p className="reminder-series-note">{series.status === "active" && series.nextScheduledAt !== null ? `Next: ${formatDue(series.nextScheduledAt, series.timeZone, serverNow)}`
      : series.status === "paused" ? "Paused: nothing will be said until you resume." : "No longer repeating."} · {series.timeZone}</p>
    {series.lastMissed && <p className="reminder-series-note">Missed {series.lastMissed.count === 1 ? "once" : `${series.lastMissed.count} times`} while June was off · last on {series.lastMissed.occurrenceDate}</p>}
    {base ? <form className="reminder-edit" onSubmit={event => { event.preventDefault(); void run(() => updateSeries(base, changesFrom(base))); }}>
      {series.revision !== base.revision && <p className="error-notice" role="status">This repeating reminder changed since you started editing. Saving will be refused; choose Keep as is to see the latest.</p>}
      <label className="reminder-edit-text">Remind me to<input type="text" maxLength={200} value={text} onChange={e => setText(e.target.value)} /></label>
      <label>Time<input type="time" value={clock} onChange={e => setClock(e.target.value)} /></label>
      <div className="reminder-repeat" role="group" aria-label="Repeat">{([["daily", "Daily"], ["weekly", "Weekly"]] as const).map(([value, label]) =>
        <button key={value} type="button" className="quiet-button" aria-pressed={rule === value} onClick={() => setRule(value)}>{label}</button>)}</div>
      {rule === "weekly" && <div className="reminder-days" role="group" aria-label="Days">{DAYS.map(([day, label]) =>
        <button key={day} type="button" className="quiet-button" aria-pressed={days.includes(day)} onClick={() => setDays(d => d.includes(day) ? d.filter(x => x !== day) : [...d, day].sort((a, b) => a - b))}>{label}</button>)}</div>}
      <div className="timer-buttons"><button type="submit" className="quiet-button" disabled={busy || !text.trim() || !clock || (rule === "weekly" && !days.length)}>Save changes</button>
        <button type="button" className="quiet-button" disabled={busy} onClick={() => setBase(null)}>Keep as is</button></div>
      <p className="handsfree-note">A reminder that is already due keeps its own text and time.</p>
    </form> : live && <div className="timer-buttons">
      <button type="button" className="quiet-button" disabled={busy} onClick={startEdit}>Edit</button>
      {series.status === "active" ? <button type="button" className="quiet-button" disabled={busy} onClick={() => void run(() => pauseSeries(series))}>Pause</button>
        : <button type="button" className="quiet-button" disabled={busy} onClick={() => void run(() => resumeSeries(series))}>Resume</button>}
      {series.status === "active" && series.nextOccurrenceDate && <button type="button" className="quiet-button" disabled={busy} onClick={() => void run(() => skipNextSeries(series))}>Skip next</button>}
      <button type="button" className="quiet-button" disabled={busy} onClick={() => void run(() => cancelSeries(series))}>Stop repeating</button>
    </div>}
    {error && <p className="error-notice" role="alert">{error}</p>}
  </section>;
}
