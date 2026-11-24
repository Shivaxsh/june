"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getGoals, getSettings, type AssistantSettings, type Goal } from "@/lib/daily";

/** Daily-assistant settings and goals from the server. A newer revision always wins. */
export function useDaily() {
  const [settings, setSettings] = useState<AssistantSettings | null>(null);
  const [goals, setGoals] = useState<Goal[] | null>(null);
  const [error, setError] = useState("");
  const alive = useRef(false);

  const refresh = useCallback(async () => {
    const [s, g] = await Promise.allSettled([getSettings(), getGoals()]);
    if (!alive.current) return;
    if (s.status === "fulfilled") setSettings(previous => previous && previous.revision > s.value.settings.revision ? previous : s.value.settings);
    if (g.status === "fulfilled") setGoals(previous => {
      const known = new Map((previous ?? []).map(goal => [goal.id, goal]));
      return g.value.goals.map(goal => { const old = known.get(goal.id); return old && old.revision > goal.revision ? old : goal; });
    });
    const failed = [s, g].find(r => r.status === "rejected") as PromiseRejectedResult | undefined;
    setError(failed ? (failed.reason instanceof Error ? failed.reason.message : "The daily assistant is unavailable.") : "");
  }, []);

  useEffect(() => {
    alive.current = true; void refresh();
    const focus = () => void refresh();
    window.addEventListener("focus", focus);
    return () => { alive.current = false; window.removeEventListener("focus", focus); };
  }, [refresh]);

  const putSettings = useCallback((next: AssistantSettings) => setSettings(previous => previous && previous.revision > next.revision ? previous : next), []);
  const putGoal = useCallback((goal: Goal) => setGoals(previous => {
    const list = previous ?? [];
    const old = list.find(g => g.id === goal.id);
    if (old && old.revision > goal.revision) return list;
    return old ? list.map(g => g.id === goal.id ? goal : g) : [goal, ...list];
  }), []);
  const dropGoal = useCallback((id: string) => setGoals(previous => (previous ?? []).filter(g => g.id !== id)), []);

  return { settings, goals, error, refresh, putSettings, putGoal, dropGoal };
}
export type Daily = ReturnType<typeof useDaily>;
