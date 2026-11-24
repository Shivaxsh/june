"use client";
import { useId, useRef, useState } from "react";
import { acknowledgeReminder, cancelReminder, describeRule, formatDue, isConflict, localClock, localDate, reminderPhrase, rescheduleReminder, skipReminder, snoozeOptionsBefore, snoozeReminder, type Reminder, type Series } from "@/lib/reminders";

/**
 * One reminder in its own zone. Only the server marks it due. Edits and snoozes are bound to the
 * revision shown: if it changed elsewhere the server refuses (409) and the card refreshes instead of retrying.
 */
export default function ReminderCard({ reminder, serverNow, onChange, onHear, onRefresh, compact = false, series }: {
  reminder: Reminder; serverNow: number; onChange(reminder: Reminder, serverNow: number): void; onHear?(phrase: string): void; onRefresh?(): void; compact?: boolean;
  /** The repeating reminder this occurrence belongs to, when it is one. */ series?: Series;
}) {
  // An occurrence of a repeating reminder: no Edit or Cancel (change the series instead); Snooze and Skip
  // only while the series is active, and never past its next regular time; Dismiss always.
  const occurrence = !!reminder.seriesId;
  const seriesActive = !occurrence || series?.status === "active";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  // The record the draft was opened from. Saving is bound to its revision: a newer copy arriving
  // while editing never rebinds the draft, so the server refuses (409) instead of being overwritten.
  const [base, setBase] = useState<Reminder | null>(null);
  const [date, setDate] = useState("");
  const [clock, setClock] = useState("");
  const [text, setText] = useState("");
  // State lands on the next render; the ref stops a fast second click from sending twice.
  const inFlight = useRef(false);
  const titleId = useId();
  const status = { active: "Scheduled", completed: "Due now", cancelled: "Cancelled", acknowledged: "Dismissed" }[reminder.status];
  const editable = !occurrence && (reminder.status === "active" || reminder.status === "completed");
  const snoozes = seriesActive ? snoozeOptionsBefore([5, 10, 30], serverNow, occurrence ? series?.nextScheduledAt ?? null : null) : [];
  const dismissable = reminder.status === "completed" || (occurrence && reminder.status === "active");
  async function run(change: () => Promise<{ reminder: Reminder; serverNow: number }>) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try { const reply = await change(); onChange(reply.reminder, reply.serverNow); setEditing(false); setBase(null); }
    catch (failure) {
      if (isConflict(failure)) { setError("This reminder changed somewhere else. June refreshed it; check it and try again."); setEditing(false); setBase(null); onRefresh?.(); }
      else setError(failure instanceof Error ? failure.message : "June could not reach Reminders.");
    }
    finally { inFlight.current = false; setBusy(false); }
  }
  function startEdit() {
    setBase(reminder);
    setDate(localDate(reminder.dueAt, reminder.timeZone)); setClock(localClock(reminder.dueAt, reminder.timeZone)); setText(reminder.text); setError(""); setEditing(true);
  }
  return <section className={`reminder-card is-${reminder.status}${compact ? " is-compact" : ""}`} role="group" aria-labelledby={titleId}>
    <div className="timer-head"><span className="hud-label">{status}</span><span className="reminder-due">{formatDue(reminder.dueAt, reminder.timeZone, serverNow)}</span></div>
    <p className="reminder-text" id={titleId}>{reminder.text}</p>
    {occurrence && <p className="reminder-series-note">{series ? `Repeats · ${describeRule(series)}` : "Repeating reminder"}{series && series.status !== "active" ? ` · ${series.status === "paused" ? "paused, silent" : "stopped"}` : ""}</p>}
    {reminder.dstAdjusted && <p className="reminder-series-note">Moved for daylight saving: that local time did not exist on this day.</p>}
    {editing && base ? <form className="reminder-edit" onSubmit={event => { event.preventDefault(); void run(() => rescheduleReminder(base, { localDate: date, localTime: clock, timeZone: base.timeZone, ...(text.trim() !== base.text ? { text } : {}) })); }}>
      {base && reminder.revision !== base.revision && <p className="error-notice" role="status">This reminder changed since you started editing. Saving will be refused; choose Keep as is to see the latest.</p>}
      <label>Date<input type="date" value={date} onChange={e => setDate(e.target.value)} /></label>
      <label>Time<input type="time" value={clock} onChange={e => setClock(e.target.value)} /></label>
      <label className="reminder-edit-text">Remind me to<input type="text" maxLength={200} value={text} onChange={e => setText(e.target.value)} /></label>
      <div className="timer-buttons"><button type="submit" className="quiet-button" disabled={busy || !text.trim() || !date || !clock}>Save changes</button>
        <button type="button" className="quiet-button" disabled={busy} onClick={() => { setEditing(false); setBase(null); }}>Keep as is</button></div>
      <p className="handsfree-note">Times are in {base.timeZone}.</p>
    </form> : <div className="timer-buttons">
      {reminder.status === "completed" && onHear && <button type="button" className="quiet-button" onClick={() => onHear(reminderPhrase(reminder))}>Hear again</button>}
      {reminder.status === "completed" && snoozes.length > 0 && <span className="reminder-snooze" role="group" aria-label="Snooze">{snoozes.map(minutes =>
        <button key={minutes} type="button" className="quiet-button" disabled={busy} onClick={() => void run(() => snoozeReminder(reminder, minutes * 60))}>Snooze {minutes} min</button>)}</span>}
      {occurrence && seriesActive && (reminder.status === "completed" || reminder.status === "active") && <button type="button" className="quiet-button" disabled={busy} onClick={() => void run(() => skipReminder(reminder))}>Skip this time</button>}
      {editable && <button type="button" className="quiet-button" disabled={busy} onClick={startEdit}>Edit</button>}
      {reminder.status === "active" && !occurrence && <button type="button" className="quiet-button" disabled={busy} onClick={() => void run(() => cancelReminder(reminder))}>Cancel</button>}
      {dismissable && <button type="button" className="quiet-button" disabled={busy} onClick={() => void run(() => acknowledgeReminder(reminder))}>Dismiss</button>}
    </div>}
    {error && <p className="error-notice" role="alert">{error}</p>}
  </section>;
}
