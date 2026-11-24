"use client";
import { useEffect, useId, useRef, useState } from "react";
import { approvePlan, cancelPlan, countsLine, isConflict, PLAN_WORDS, remainingMs, RISK_WORDS, stepWords, type Capability, type Plan } from "@/lib/integrations";

const clock = (ms: number) => { const s = Math.max(0, Math.floor(ms / 1000)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };

/**
 * One plan. While it waits for review, the card shows and binds the exact copy first
 * shown (its revision and fingerprint): a newer copy arriving meanwhile never changes
 * what Approve sends. Outcomes come from the server's checked results; an unknown
 * outcome is said plainly and is never retried from here.
 */
export default function PlanCard({ plan, capabilities, serverNow, receivedAt, onChange, onRefresh, onAnnounce }: {
  plan: Plan; capabilities: Map<string, Capability>; serverNow: number; receivedAt: number;
  onChange(plan: Plan, serverNow: number): void; onRefresh(): void; onAnnounce(text: string): void;
}) {
  const [reviewed, setReviewed] = useState<Plan | null>(plan.status === "proposed" ? plan : null);
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const [stopAsked, setStopAsked] = useState(false);
  const inFlight = useRef(false);
  const titleId = useId();

  // A plan that becomes reviewable later (for example after a refresh) is bound then, once.
  useEffect(() => { if (!reviewed && plan.status === "proposed") setReviewed(plan); }, [plan, reviewed]);
  useEffect(() => {
    if (plan.status !== "proposed") return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [plan.status]);

  const shown = plan.status === "proposed" && reviewed ? reviewed : plan;
  const changed = !!reviewed && plan.status === "proposed" && (plan.revision !== reviewed.revision || plan.fingerprint !== reviewed.fingerprint);
  const left = remainingMs(plan, serverNow, receivedAt, now);
  const expired = plan.status === "proposed" && left <= 0;
  const outward = shown.steps.some(step => { const risk = capabilities.get(step.capability)?.risk; return risk === "outward" || risk === "financial" || risk === undefined; });
  const canRemember = shown.rememberable && !outward;
  // One approval covers this whole narrow class, so the wording says so.
  const musicClass = shown.steps.every(step => step.capability === "music.control" || step.capability === "music.library");

  // Approval binds the copy reviewed. Stopping binds the same immutable revision and
  // fingerprint, so it can never act on a different plan.
  const bound = reviewed ?? plan;
  const active = plan.status === "approved" || plan.status === "running";
  const stopping = active && (plan.cancelRequested === true || stopAsked);

  async function decide(kind: "approve" | "cancel") {
    if (inFlight.current || (kind === "approve" && !reviewed)) return;
    inFlight.current = true; setBusy(true); setError("");
    try {
      const reply = kind === "approve" ? await approvePlan(reviewed!, canRemember && remember) : await cancelPlan(bound);
      onChange(reply.plan, reply.serverNow);
      if (reply.plan.status !== "proposed") setReviewed(null);
      if (kind === "cancel" && (reply.plan.status === "approved" || reply.plan.status === "running")) setStopAsked(true);
      onAnnounce(reply.reconciled ? `Connection dropped; June read the plan back: ${PLAN_WORDS[reply.plan.status]}.` : `${shown.title}: ${PLAN_WORDS[reply.plan.status]}.`);
    } catch (failure) {
      if (isConflict(failure)) { setError("This plan changed or was already decided elsewhere. June refreshed it; review it again."); setReviewed(null); onRefresh(); }
      else setError(failure instanceof Error ? failure.message : "June could not reach Integrations. Check Plans before trying again.");
    } finally { inFlight.current = false; setBusy(false); }
  }

  const pending = plan.status === "proposed";
  return <section className={`plan-card is-${plan.status}`} role="group" aria-labelledby={titleId}>
    <div className="timer-head">
      <span className="hud-label">{PLAN_WORDS[plan.status]}</span>
      {pending && <span className="plan-expiry">{expired ? "Expired" : `Expires in ${clock(left)}`}</span>}
    </div>
    <p className="plan-title" id={titleId}>{shown.title}</p>
    {changed && <p className="error-notice" role="status">This plan changed since it was shown. Approving will be refused; refresh to review the new version.</p>}
    <ol className="plan-steps">
      {shown.steps.map(step => {
        const capability = capabilities.get(step.capability);
        const live = plan.steps.find(s => s.id === step.id) ?? step;
        return <li key={step.id} className={`plan-step is-${live.status}`}>
          <div className="plan-step-head"><strong>{step.label}</strong><span>{stepWords(live)}</span></div>
          <p className="plan-step-meta">{capability ? `${capability.label} · ${RISK_WORDS[capability.risk]}` : `${step.capability} · not in this Mac's catalog`}</p>
          {/* Exactly what approval covers; shown in full, never summarised. */}
          <pre className="plan-preview" tabIndex={0} aria-label={`What ${step.label} will do`}>{step.preview}</pre>
          {live.result && <p className={`plan-result${live.result.verified ? " is-verified" : ""}`}>{live.result.verified ? "Checked: " : "Not confirmed: "}{live.result.message}</p>}
        </li>;
      })}
    </ol>
    {countsLine(plan) && <p className="plan-step-meta" role="status">{countsLine(plan)}</p>}
    {plan.status === "unknown" && <p className="handsfree-note">June could not confirm whether this happened. Check the result yourself before asking again; nothing will be retried automatically.</p>}
    {plan.steps.some(s => s.reason === "blocked-by-unknown" && s.capability === "jobs.apply") && <p className="handsfree-note">Jobs marked “Not started” never ran. Say “apply to the rest” and June prepares a new card for just those, for you to review; nothing runs by itself.</p>}
    {plan.status === "partial" && <p className="handsfree-note">Some steps finished and some did not. Steps that did not start will not run.</p>}
    {pending && reviewed && !expired && <div className="plan-actions">
      {canRemember && <label className="plan-remember"><input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} disabled={busy} />{musicClass ? "Don't ask again for music controls and playing from my library" : "Don't ask again for this exact request"}</label>}
      {!canRemember && outward && <p className="handsfree-note">Sends, publishing and payments need your review every time.</p>}
      <div className="timer-buttons">
        <button type="button" className="quiet-button" disabled={busy || changed} onClick={() => void decide("approve")}>Approve</button>
        <button type="button" className="quiet-button" disabled={busy} onClick={() => void decide("cancel")}>Cancel</button>
      </div>
    </div>}
    {active && (stopping
      ? <p className="handsfree-note" role="status">Stop requested. A step already running may still finish; later steps will not start.</p>
      : <div className="plan-actions">
          <p className="handsfree-note">A step already running may still finish; cancelling stops the steps that have not started.</p>
          <div className="timer-buttons"><button type="button" className="quiet-button" disabled={busy} onClick={() => void decide("cancel")}>Cancel remaining steps</button></div>
        </div>)}
    {error && <p className="error-notice" role="alert">{error}</p>}
  </section>;
}
