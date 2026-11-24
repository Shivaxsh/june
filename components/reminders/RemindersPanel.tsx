"use client";
import { useEffect, useState } from "react";
import { createReminder, createSeries, nextHourDefault, type Reminder } from "@/lib/reminders";
import ReminderCard from "./ReminderCard";
import SeriesCard from "./SeriesCard";
import type { Reminders } from "./useReminders";

const DAYS = [[1, "Mon"], [2, "Tue"], [3, "Wed"], [4, "Thu"], [5, "Fri"], [6, "Sat"], [7, "Sun"]] as const;
const OUTCOME_WORDS: Record<string, string> = { missed: "Missed", skipped: "Skipped", paused: "Paused" };
const pastLabel = (r: Reminder) => r.outcome ? OUTCOME_WORDS[r.outcome] : r.status === "cancelled" ? "Cancelled" : "Done · dismissed";

/** Systems → Reminders: once, daily or on chosen weekdays, in June's time zone. */
export default function RemindersPanel({ reminders, onHear, onAnnounce }: { reminders: Reminders; onHear(phrase: string): void; onAnnounce(text: string): void }) {
  const { state } = reminders;
  const zone = state?.timeZone ?? "Asia/Kolkata";
  const [date, setDate] = useState("");
  const [clock, setClock] = useState("");
  const [text, setText] = useState("");
  const [repeat, setRepeat] = useState<"once" | "daily" | "weekly">("once");
  const [days, setDays] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Defaults come from the server's clock and zone once known: the next whole hour (date and time together).
  useEffect(() => { if (state && !date) { const next = nextHourDefault(state.serverNow, zone); setDate(next.date); setClock(next.time); } }, [state, zone, date]);
  const seriesById = new Map((state?.series ?? []).map(s => [s.id, s]));
  const live = state?.reminders.filter(r => r.status === "completed" || r.status === "active").sort((a, b) => a.dueAt - b.dueAt) ?? [];
  const repeating = state?.series.filter(s => s.status !== "cancelled") ?? [];
  const past = state?.reminders.filter(r => r.status === "cancelled" || r.status === "acknowledged").slice(0, 6) ?? [];
  async function save() {
    setBusy(true); setError("");
    try {
      if (repeat === "once") {
        const reply = await createReminder({ text, localDate: date, localTime: clock, timeZone: zone });
        reminders.upsert(reply.reminder, reply.serverNow); onAnnounce(`Reminder saved: ${reply.reminder.text}.`);
      } else {
        const reply = await createSeries({ text, rule: repeat, ...(repeat === "weekly" ? { weekdays: days } : {}), localTime: clock, startDate: date, timeZone: zone });
        reminders.upsertSeries(reply.series, reply.serverNow); onAnnounce(`Repeating reminder saved: ${reply.series.text}.`);
      }
      setText("");
    }
    catch (failure) { setError(failure instanceof Error ? failure.message : "June could not save that reminder."); }
    finally { setBusy(false); }
  }
  return <section className="timers-panel reminders-panel" aria-label="Reminders">
    <span className="eyebrow">Reminders · kept on this Mac</span>
    <h2>Remind me <em>later.</em></h2>
    <p>June keeps reminders on her local server: once (up to 30 days ahead), every day, or on the days you choose. If this page is open and her voice is on, she says each one once when she is free to speak. Otherwise it waits here. There is no Mac notification.</p>
    <form className="timer-form reminder-form" onSubmit={event => { event.preventDefault(); void save(); }}>
      <div className="reminder-repeat" role="group" aria-label="Repeat">{([["once", "Once"], ["daily", "Daily"], ["weekly", "Weekly"]] as const).map(([value, label]) =>
        <button key={value} type="button" className="quiet-button" aria-pressed={repeat === value} onClick={() => setRepeat(value)}>{label}</button>)}</div>
      {repeat === "weekly" && <div className="reminder-days" role="group" aria-label="Days">{DAYS.map(([day, label]) =>
        <button key={day} type="button" className="quiet-button" aria-pressed={days.includes(day)} onClick={() => setDays(d => d.includes(day) ? d.filter(x => x !== day) : [...d, day].sort((a, b) => a - b))}>{label}</button>)}</div>}
      <label>{repeat === "once" ? "Date" : "Starts"}<input type="date" value={date} onChange={e => setDate(e.target.value)} /></label>
      <label>Time<input type="time" value={clock} onChange={e => setClock(e.target.value)} /></label>
      <label className="timer-name">Remind me to<input type="text" maxLength={200} value={text} placeholder="call Mom, take the pasta off…" onChange={e => setText(e.target.value)} /></label>
      <button type="submit" className="quiet-button" disabled={busy || !text.trim() || !date || !clock || (repeat === "weekly" && !days.length)}>Save reminder</button>
    </form>
    <p className="handsfree-note">Times are in {zone}.</p>
    {(error || reminders.error) && <p className="error-notice" role="alert">{error || reminders.error}</p>}
    {state && live.map(r => <ReminderCard key={r.id} reminder={r} series={r.seriesId ? seriesById.get(r.seriesId) : undefined} serverNow={state.serverNow} onChange={reminders.upsert} onHear={onHear} onRefresh={() => void reminders.refresh()} />)}
    {state && repeating.map(s => <SeriesCard key={s.id} series={s} serverNow={state.serverNow} onChange={(next, now, reminder) => { reminders.upsertSeries(next, now); if (reminder) reminders.upsert(reminder, now); }} onRefresh={() => void reminders.refresh()} />)}
    {state && !live.length && !repeating.length && <p className="handsfree-note">No reminders scheduled.</p>}
    {past.length > 0 && <ul className="hands-history" aria-label="Recent reminders">{past.map(r => <li key={r.id}><span>{r.text}</span><span>{pastLabel(r)}</span><time dateTime={new Date(r.dueAt).toISOString()}>{new Date(r.dueAt).toLocaleDateString([], { day: "numeric", month: "short" })}</time></li>)}</ul>}
  </section>;
}
