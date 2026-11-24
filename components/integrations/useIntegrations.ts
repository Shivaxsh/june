"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getApps, getCapabilities, getConnections, getPlans, isActive, mergePlan, mergePlans, type AppEntry, type Capability, type Connection, type Plan } from "@/lib/integrations";

const ACTIVE_POLL_MS = 1500;
const IDLE_POLL_MS = 15000;

/** Capabilities, connections and recent plans, each from the server; plans merge monotonically. */
export function useIntegrations() {
  const [capabilities, setCapabilities] = useState<Capability[] | null>(null);
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [apps, setApps] = useState<AppEntry[] | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [serverNow, setServerNow] = useState(0);
  const [receivedAt, setReceivedAt] = useState(0);
  const [error, setError] = useState("");
  const alive = useRef(false);
  const plansRef = useRef<Plan[]>([]);
  plansRef.current = plans;

  const refreshPlans = useCallback(async () => {
    try {
      const reply = await getPlans();
      if (!alive.current) return;
      setPlans(previous => mergePlans(previous, reply.plans));
      setServerNow(reply.serverNow); setReceivedAt(Date.now()); setError("");
    } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : "Integrations are unavailable."); }
  }, []);

  const refresh = useCallback(async () => {
    // Each list stands alone: one failing endpoint never hides the others.
    const [caps, conns, list] = await Promise.allSettled([getCapabilities(), getConnections(), getApps(), refreshPlans()]);
    if (!alive.current) return;
    if (caps.status === "fulfilled") setCapabilities(caps.value.capabilities);
    if (conns.status === "fulfilled") setConnections(conns.value.connections);
    if (list.status === "fulfilled") setApps(list.value.apps);
    const failed = [caps, conns].find(r => r.status === "rejected") as PromiseRejectedResult | undefined;
    if (failed) setError(failed.reason instanceof Error ? failed.reason.message : "Integrations are unavailable.");
  }, [refreshPlans]);

  useEffect(() => {
    alive.current = true;
    void refresh();
    // A running plan is followed closely; otherwise a visible page checks occasionally.
    let ticks = 0, inFlight = false;
    const timer = setInterval(() => {
      ticks++;
      const due = plansRef.current.some(isActive) || (ticks % (IDLE_POLL_MS / ACTIVE_POLL_MS) === 0 && !document.hidden);
      if (!due || inFlight) return;
      inFlight = true;
      void refreshPlans().finally(() => { inFlight = false; });
    }, ACTIVE_POLL_MS);
    const focus = () => void refresh();
    window.addEventListener("focus", focus);
    return () => { alive.current = false; clearInterval(timer); window.removeEventListener("focus", focus); };
  }, [refresh, refreshPlans]);

  /** A plan from a propose/approve/cancel reply: merged, never moved backwards. */
  const upsert = useCallback((plan: Plan, now: number) => {
    setPlans(previous => [mergePlan(previous.find(p => p.id === plan.id), plan), ...previous.filter(p => p.id !== plan.id)].slice(0, 20));
    setServerNow(now); setReceivedAt(Date.now());
  }, []);

  /** A whole plan list from a reply (for example after forgetting approvals), merged monotonically. */
  const replacePlans = useCallback((next: Plan[], now: number) => {
    setPlans(previous => mergePlans(previous, next));
    setServerNow(now); setReceivedAt(Date.now());
  }, []);

  return { capabilities, connections, apps, plans, serverNow, receivedAt, error, refresh, refreshPlans, upsert, replacePlans };
}
export type Integrations = ReturnType<typeof useIntegrations>;
