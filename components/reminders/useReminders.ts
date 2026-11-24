"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getReminders, mergeReminder, mergeReminders, mergeSeries, mergeSeriesList, nextReminderCheck, type Reminder, type ReminderState, type Series } from "@/lib/reminders";

/** Reminders as the server reports them. Checks again just after the nearest due time, not every second for days. */
export function useReminders() {
  const [state, setState] = useState<ReminderState | null>(null);
  const [receivedAt, setReceivedAt] = useState(0);
  const [error, setError] = useState("");
  const fetching = useRef(false);
  const refresh = useCallback(async () => {
    if (fetching.current) return;
    fetching.current = true;
    try {
      const next = await getReminders(), at = Date.now();
      setState(previous => ({ ...next, reminders: mergeReminders(previous?.reminders ?? [], next.reminders), series: mergeSeriesList(previous?.series ?? [], next.series) }));
      setReceivedAt(at); setError("");
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Reminders are unavailable."); }
    finally { fetching.current = false; }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!state) return;
    const delay = nextReminderCheck(state.reminders, state.serverNow, receivedAt, Date.now());
    if (delay === null) return;
    const timer = setTimeout(() => void refresh(), delay);
    return () => clearTimeout(timer);
  }, [state, receivedAt, refresh]);
  // Coming back to the page re-reads reminders that may have come due meanwhile.
  useEffect(() => {
    const again = () => { if (!document.hidden) void refresh(); };
    window.addEventListener("focus", again); document.addEventListener("visibilitychange", again);
    return () => { window.removeEventListener("focus", again); document.removeEventListener("visibilitychange", again); };
  }, [refresh]);
  const upsert = useCallback((reminder: Reminder, serverNow: number) => {
    setState(previous => {
      const known = previous?.reminders.find(r => r.id === reminder.id);
      return { timeZone: previous?.timeZone ?? reminder.timeZone, serverNow, series: previous?.series ?? [], reminders: [mergeReminder(known, reminder), ...(previous?.reminders ?? []).filter(r => r.id !== reminder.id)] };
    });
    setReceivedAt(Date.now());
  }, []);
  /** A repeating reminder from a reply: merged by revision, and by schedule at an equal revision. */
  const upsertSeries = useCallback((series: Series, serverNow: number) => {
    setState(previous => {
      const known = previous?.series.find(x => x.id === series.id);
      return { timeZone: previous?.timeZone ?? series.timeZone, serverNow, reminders: previous?.reminders ?? [], series: [mergeSeries(known, series), ...(previous?.series ?? []).filter(x => x.id !== series.id)] };
    });
    setReceivedAt(Date.now());
  }, []);
  return { state, receivedAt, error, refresh, upsert, upsertSeries };
}
export type Reminders = ReturnType<typeof useReminders>;
