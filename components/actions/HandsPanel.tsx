"use client";
import { useEffect, useRef, useState } from "react";
import { APP_STATE_WORDS, observedAgo, proposeAction, runOpenVSCode, setOpenWithoutApproval, statusText } from "@/lib/actions";
import ActionCard from "./ActionCard";
import ProjectsPanel from "./ProjectsPanel";
import type { Actions } from "./useActions";

/** Systems → Hands: what June may do on this Mac, pending proposals, and what already happened. */
export default function HandsPanel({ actions, onAnnounce }: { actions: Actions; onAnnounce(text: string): void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { state, receivedAt } = actions;
  const [refreshing, setRefreshing] = useState(false);
  // The age label advances on its own; the state itself changes only when June checks again.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 5000); return () => clearInterval(timer); }, []);
  async function refresh() { setRefreshing(true); try { await actions.refresh(); setNow(Date.now()); } finally { setRefreshing(false); } }
  const pending = state?.actions.filter(a => a.status === "proposed") ?? [];
  const history = state?.actions.filter(a => a.status !== "proposed").slice(0, 8) ?? [];
  const direct = state?.openVSCodeWithoutApproval === true;
  // One click opens once: the ref blocks a second click before React re-renders.
  const running = useRef(false);
  const [opening, setOpening] = useState(false);
  async function openNow() {
    if (running.current) return;
    running.current = true; setOpening(true); setError("");
    try { const reply = await runOpenVSCode(); actions.upsert(reply.action, reply.serverNow); onAnnounce(statusText(reply.action)); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "June could not open VS Code."); }
    finally { running.current = false; setOpening(false); }
  }
  const [saving, setSaving] = useState(false);
  // The switch can only forget: trust is granted by a genuine Approve with Remember ticked.
  async function forget() {
    setSaving(true); setError("");
    try { const next = await setOpenWithoutApproval(false); actions.replace(next); onAnnounce("June will ask you to review opening VS Code each time."); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "June could not change that setting."); }
    finally { setSaving(false); }
  }
  async function propose() {
    setBusy(true); setError("");
    try { const reply = await proposeAction(); actions.upsert(reply.action, reply.serverNow); onAnnounce("June proposed opening VS Code. Review it, then approve or cancel."); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "June could not propose that action."); }
    finally { setBusy(false); }
  }
  return <section className="hands-panel" aria-label="Hands">
    <span className="eyebrow">Hands · VS Code and saved projects</span>
    <h2>June can open <em>VS Code.</em></h2>
    <p>{direct
      ? "You approved this once and asked June to remember it: when you or June ask, VS Code opens, or comes forward if it is already running, without a new card. Any other action would still need its own review."
      : "She proposes it, you see exactly what will happen, and it runs only after you click Approve: VS Code opens, or comes forward if it is already running. A proposal expires after 5 minutes. Saved project folders have their own review below."}</p>
    {state?.available && <div className="hands-mode">
      <button type="button" role="switch" aria-checked={direct} className={`hands-switch${direct ? " is-on" : ""}`} disabled={saving || !direct}
        onClick={event => { if (!event.nativeEvent.isTrusted) return; void forget(); }}>
        <span className="hands-switch-track" aria-hidden="true"><span /></span>{direct ? "Remember approval for opening VS Code" : "Review every time"}</button>
      <span className="hands-observed-note">{direct
        ? "Remembered: Visual Studio Code (com.microsoft.VSCode) only, with no files, folders or arguments. Switch off to review each time."
        : "Each request shows a card to approve or cancel. To stop being asked, tick “Remember this approval” on the next VS Code card: no files, folders or arguments, only this app."}</span>
    </div>}
    {state && <div className="hands-observed" role="group" aria-label="Visual Studio Code on this Mac">
      <span className="hud-label">VS Code on this Mac</span>
      <strong className={`hands-app is-${state.appState ?? "unknown"}`}>{state.appState ? APP_STATE_WORDS[state.appState] : "Status not reported"}</strong>
      <span className="hands-observed-note">{[observedAgo(state.observedAt, state.serverNow, receivedAt, now), "a snapshot, not live monitoring"].filter(Boolean).join(" · ")}</span>
      <button type="button" className="quiet-button" disabled={refreshing} onClick={() => void refresh()}>{refreshing ? "Checking…" : "Refresh status"}</button>
    </div>}
    {actions.error ? <p className="error-notice" role="alert">{actions.error} <button type="button" className="quiet-button" onClick={() => void actions.refresh()}>Retry</button></p>
      : !state ? <p className="handsfree-note">Checking Hands…</p>
      : !state.available ? <p className="handsfree-note">Mac actions are unavailable right now. June’s local action helper or Visual Studio Code may be missing; nothing can be proposed until it is ready.</p>
      : <div className="hands-actions">{direct
          ? <button type="button" className="action-approve" disabled={opening} onClick={event => { if (!event.nativeEvent.isTrusted) return; void openNow(); }}>{opening ? "Opening or bringing VS Code forward…" : "Open VS Code"}</button>
          : <button type="button" className="quiet-button" disabled={busy || pending.length > 0} onClick={() => void propose()}>Ask June to open VS Code</button>}
          {!direct && pending.length > 0 && <span className="handsfree-note">A proposal is waiting below.</span>}</div>}
    <ProjectsPanel actions={actions} onAnnounce={onAnnounce} />
    {error && <p className="error-notice" role="alert">{error}</p>}
    {state && pending.map(record => <ActionCard key={record.id} record={record} serverNow={state.serverNow} receivedAt={receivedAt} onChange={actions.upsert} onAnnounce={onAnnounce} onRefresh={() => void actions.refresh()} />)}
    {history.length > 0 && <ul className="hands-history" aria-label="Recent actions">
      {history.map(a => <li key={a.id}><span>{a.label}</span><span>{statusText(a, { past: true })}</span><time dateTime={new Date(a.createdAt).toISOString()}>{new Date(a.createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time></li>)}
    </ul>}
  </section>;
}
