"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import type { Plan, Capability } from "@/lib/integrations";
import { getTransactions, panelSession, respond, type Transaction, type TransactionsState } from "@/lib/transactions";
import PlanCard from "../integrations/PlanCard";
import TransactionCard from "./TransactionCard";

type Props = {
  plans: Plan[]; capabilities: Capability[]; serverNow: number; receivedAt: number;
  onPlan: (plan: Plan, serverNow: number) => void; onRefreshPlans: () => void; onAnnounce: (text: string) => void;
};

/** Systems → Shopping & bookings (simulated). Requests started here use a private panel session, so they never write
 * normal chat history. Approval is always the plan card with its exact reviewed quote. */
export default function TransactionsPanel({ plans, capabilities, serverNow, receivedAt, onPlan, onRefreshPlans, onAnnounce }: Props) {
  const [state, setState] = useState<TransactionsState | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const alive = useRef(true), inFlight = useRef(false), seq = useRef(0);
  const session = useRef<string | null>(null);
  const load = useCallback(async () => {
    const token = ++seq.current;
    try { const next = await getTransactions(); if (alive.current && token === seq.current) { setState(next); setError(""); } }
    catch { if (alive.current && token === seq.current) setError("Shopping & bookings are unavailable right now."); }
  }, []);
  useEffect(() => {
    alive.current = true; void load();
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => { alive.current = false; clearInterval(tick); };
  }, [load]);
  // When a purchase's plan finishes, re-read the receipts (read-only).
  const finished = plans.filter(p => !["proposed", "approved", "running"].includes(p.status) && state?.transactions.some(t => t.planId === p.id)).map(p => p.id + p.status).join();
  useEffect(() => { if (finished) void load(); }, [finished, load]);

  /** `conversationId`: a booking's own id when choosing one of its offers (it may have started in chat); new free-text
   * requests use the private panel session. Neither writes normal chat history. */
  async function send(input: { text?: string; select?: { offerId: string } }, conversationId?: string) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      session.current ??= panelSession(typeof window === "undefined" ? null : window.localStorage);
      const reply = await respond({ conversationId: conversationId ?? session.current, ...input });
      if (reply.plan) onPlan(reply.plan, reply.serverNow);
      onAnnounce(reply.reply);
      if (input.text) setDraft("");
      seq.current++;  // anything loaded before this change is out of date
      await load();
    } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : "June could not update that booking."); }
    finally { inFlight.current = false; if (alive.current) setBusy(false); }
  }

  const caps = new Map(capabilities.map(c => [c.id, c]));
  const card = (t: Transaction) => {
    const plan = t.planId ? plans.find(p => p.id === t.planId) : undefined;
    return <TransactionCard key={t.id} transaction={t} busy={busy} now={now} onChoose={offerId => void send({ select: { offerId } }, t.conversationId)}
      planCard={plan ? <PlanCard plan={plan} capabilities={caps} serverNow={serverNow} receivedAt={receivedAt} onChange={onPlan} onRefresh={onRefreshPlans} onAnnounce={onAnnounce} /> : undefined} />;
  };
  const recent = state?.transactions.slice(0, 5) ?? [];
  const preferences = Object.entries(state?.preferences ?? {});
  return <section className="timers-panel integrations-panel" aria-label="Shopping and bookings">
    <div className="integration-group">
      <h3>Shopping & bookings <span className="plan-step-meta">· simulated</span></h3>
      <p className="handsfree-note">Practice runs only: no real shop, cinema or restaurant is contacted and nothing is charged. Ask in chat or here, for example “2 movie tickets in Noida tomorrow evening”, “order 2 kg rice” or “a table for 4 at 8 pm”. June asks only what’s missing, shows the exact quote, and books only after you approve that exact quote.</p>
      <form className="timer-buttons" onSubmit={event => { event.preventDefault(); if (draft.trim()) void send({ text: draft }); }}>
        <input type="text" maxLength={300} aria-label="Ask June to shop or book (simulated)" value={draft} onChange={event => setDraft(event.target.value)} />
        <button type="submit" className="quiet-button" disabled={busy || !draft.trim()}>{busy ? "Working…" : "Ask"}</button>
      </form>
      {error && <p className="error-notice" role="alert">{error}</p>}
      {state && !recent.length && <p className="plan-step-meta">No simulated bookings yet.</p>}
      {recent.map(card)}
      {preferences.length > 0 && <details><summary>Preferences you asked June to remember ({preferences.length})</summary>
        <ul className="command-list">{preferences.map(([k, v]) => <li key={k}><span className="plan-step-meta">{k}</span> {v}</li>)}</ul></details>}
    </div>
  </section>;
}
