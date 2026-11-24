"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getTimers, mergeTimer, mergeTimers, type Timer, type TimerState } from "@/lib/timers";

/** Timers as the server reports them. Polls once a second only while a timer is running. */
export function useTimers() {
  const [state, setState] = useState<TimerState | null>(null);
  const [receivedAt, setReceivedAt] = useState(0);
  const [error, setError] = useState("");
  const fetching = useRef(false);
  const refresh = useCallback(async () => {
    if (fetching.current) return;
    fetching.current = true;
    try {
      const next = await getTimers(), at = Date.now();
      setState(previous => ({ ...next, timers: mergeTimers(previous?.timers ?? [], next.timers) }));
      setReceivedAt(at); setError("");
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Timers are unavailable."); }
    finally { fetching.current = false; }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const running = !!state?.timers.some(t => t.status === "active");
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => void refresh(), 1000);
    return () => clearInterval(timer);
  }, [running, refresh]);
  const upsert = useCallback((timer: Timer, serverNow: number) => {
    setState(previous => {
      const known = previous?.timers.find(t => t.id === timer.id);
      return { serverNow, timers: [mergeTimer(known, timer), ...(previous?.timers ?? []).filter(t => t.id !== timer.id)] };
    });
    setReceivedAt(Date.now());
  }, []);
  return { state, receivedAt, error, refresh, upsert };
}
export type Timers = ReturnType<typeof useTimers>;
