"use client";
import { useEffect, useId, useRef, useState } from "react";
import { approveAction, cancelAction, formatRemaining, getActions, remainingMs, statusText, type ActionRecord } from "@/lib/actions";

/**
 * One proposed Mac action, shown exactly as the server described it.
 * It runs only after a real click on Approve: never from speech, never on its own,
 * and a dropped connection is reconciled by reading the state back, not by approving again.
 */
export default function ActionCard({ record, serverNow, receivedAt, onChange, onAnnounce, onRefresh }: {
  record: ActionRecord; serverNow: number; receivedAt: number;
  onChange(record: ActionRecord, serverNow: number): void; onAnnounce?(text: string): void;
  /** Re-read Hands after a remembered approval so the setting shows at once. */ onRefresh?(): void;
}) {
  // The person asked for this to be remembered by default; it applies to this one fixed action only.
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState<"" | "approve" | "cancel">("");
  // State updates land on the next render; a ref stops a fast double click from sending twice.
  const inFlight = useRef(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const proposed = record.status === "proposed";
  useEffect(() => {
    if (!proposed) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [proposed]);
  // While macOS reports back, read the server's state; never act again.
  useEffect(() => {
    if (record.status !== "executing") return;
    let stop = false, tries = 0;
    const timer = setInterval(() => {
      if (stop || ++tries > 20) { clearInterval(timer); return; }
      void getActions().then(state => {
        const current = state.actions.find(a => a.id === record.id);
        if (!stop && current && current.status !== "executing") { onChange(current, state.serverNow); onAnnounce?.(statusText(current)); }
      }).catch(() => {});
    }, 1500);
    return () => { stop = true; clearInterval(timer); };
  }, [record.status, record.id]);
  const left = remainingMs(record, serverNow, receivedAt, now);
  const expired = proposed && left <= 0;

  async function decide(kind: "approve" | "cancel") {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(kind); setError("");
    try {
      const rememberable = record.action === "open-vscode" || record.action === "open-project";
      const reply = await (kind === "approve" ? approveAction(record, undefined, remember) : cancelAction(record));
      if (kind === "approve" && rememberable && remember) onRefresh?.();
      onChange(reply.action, reply.serverNow);
      onAnnounce?.(statusText(reply.action));
      if (reply.reconciled) setError("The connection dropped. This is the status June reports now; nothing was sent twice.");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "June could not reach Hands. Nothing was approved.");
    } finally { inFlight.current = false; setBusy(""); }
  }

  // The same record can show in chat and in Hands at once; each card needs its own id.
  const titleId = useId();
  return <section className={`action-card is-${expired ? "expired" : record.status}`} role="group" aria-labelledby={titleId}>
    <div className="action-head">
      <span className="hud-label">{proposed && !expired ? "Proposed action · needs your approval" : "Action"}</span>
      {proposed && !expired && <span className="action-timer" aria-label={`Expires in ${formatRemaining(left)}`}>{formatRemaining(left)}</span>}
    </div>
    <h3 id={titleId}>{record.label}</h3>
    <p className="action-detail">{record.detail}</p>
    {proposed && !expired && <label className="action-remember">
      <input type="checkbox" checked={remember} disabled={!!busy} onChange={event => setRemember(event.target.checked)} />
      <span>{record.action === "open-project" ? "Remember approval for this exact project folder" : "Remember this approval for opening VS Code"}<small>{record.action === "open-project" ? "Only this saved folder in VS Code. Other folders need their own approval. Forget or remove it in Hands." : "Next time June opens it (or brings it forward) without a new card. Only this app, no files, folders or arguments. You can switch it off in Hands."}</small></span>
    </label>}
    {proposed && !expired ? <div className="action-buttons">
      {/* A real pointer or keyboard activation only: scripts and speech cannot approve. */}
      <button type="button" className="action-approve" disabled={!!busy || expired} onClick={event => { if (!event.nativeEvent.isTrusted) return; void decide("approve"); }}>Approve</button>
      <button type="button" className="quiet-button" disabled={!!busy} onClick={() => void decide("cancel")}>Cancel</button>
      {busy === "approve" && <p className="action-status action-pending" role="status">Opening or bringing VS Code forward…</p>}
    </div> : <p className="action-status" role="status">{expired ? "Expired · nothing ran. Ask again if you still want it." : statusText(record)}</p>}
    {error && <p className="error-notice" role="alert">{error}</p>}
    {proposed && !expired && <p className="action-note">Only a click approves. Voice can ask; it can never approve.</p>}
  </section>;
}
