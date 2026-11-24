"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { proposePlan, type Intent, type Plan, type PlanInput } from "@/lib/integrations";
import { addCommand, getCommands, removeCommand, setGithub, type CommandKind, type CommandState } from "@/lib/commands";

type Props = { plans: Plan[]; onPlan: (plan: Plan, serverNow: number) => void; onAnnounce: (text: string) => void };

/** Project commands: fixed git recipes for projects saved in Hands, and commands the person typed here. */
export default function CommandsPanel({ plans, onPlan, onAnnounce }: Props) {
  const [state, setState] = useState<CommandState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [draft, setDraft] = useState({ projectId: "", name: "", command: "", safe: false, kind: "run" as CommandKind });
  const [last, setLast] = useState<{ id: string; label: string } | null>(null);
  const inFlight = useRef(false);
  const alive = useRef(true);

  const load = useCallback(async () => {
    try { const next = await getCommands(); if (alive.current) { setState(next); setError(""); } }
    catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : "Project commands are unavailable."); }
  }, []);
  useEffect(() => { alive.current = true; void load(); return () => { alive.current = false; }; }, [load]);

  async function guarded(work: () => Promise<void>) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError("");
    try { await work(); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "June could not do that."); }
    finally { inFlight.current = false; if (alive.current) setBusy(false); }
  }
  const plan = (intent: Intent, label: string, input: PlanInput) => guarded(async () => {
    const reply = await proposePlan(intent, undefined, undefined, input);
    onPlan(reply.plan, reply.serverNow); setLast({ id: reply.plan.id, label });
    onAnnounce(reply.plan.status === "proposed" ? `${label} is ready for your review.` : `${label}: ${reply.plan.status}.`);
    void load();
  });
  const change = (work: () => Promise<CommandState>, said: string) => guarded(async () => { const next = await work(); if (alive.current) setState(next); onAnnounce(said); });

  const shown = last ? plans.find(p => p.id === last.id) : undefined;
  const note = !last || !shown ? "" : shown.status === "proposed" ? `${last.label}: review the card under “Waiting for review” above.`
    : shown.status === "approved" || shown.status === "running" ? `${last.label}: working… this can take a few minutes.`
    : shown.steps.map(step => step.result?.message).filter(Boolean).join(" ") || `${last.label}: ${shown.status}.`;
  const projects = state?.projects ?? [];
  const projectId = draft.projectId || projects[0]?.id || "";

  return <div className="integration-group" aria-label="Project commands">
    <h3>Project commands</h3>
    <p className="handsfree-note">For projects saved in Hands. Each command shows a card first. Commit and push is reviewed every time, with the exact files, branch and address. June never force-pushes and never uses administrator rights.</p>
    {state && projects.length === 0 && <p className="handsfree-note">No project is saved yet. Add your project folder in Systems → Hands first.</p>}
    {state && <div className="plan-actions">
      <p className="plan-step-meta">{state.githubAllowed ? "GitHub: allowed. Pull and push contact github.com only when you approve a card." : "GitHub: not allowed. Pull and push are off until you allow June to contact github.com."}</p>
      <div className="timer-buttons"><button type="button" className="quiet-button" disabled={busy}
        onClick={() => void change(() => setGithub(!state.githubAllowed), state.githubAllowed ? "June will no longer contact GitHub." : "June may contact GitHub when you approve a pull or push.")}>{state.githubAllowed ? "Stop GitHub access" : "Allow GitHub"}</button></div>
    </div>}
    {projects.map(project => <div key={project.id} className="plan-actions">
      <p className="plan-step-meta">{project.name}</p>
      <div className="timer-buttons">
        <button type="button" className="quiet-button" disabled={busy} onClick={() => void plan("project-recipe", `Run tests in ${project.name}`, { name: project.name, recipe: "test" })}>Run tests</button>
        <button type="button" className="quiet-button" disabled={busy} onClick={() => void plan("project-recipe", `Build ${project.name}`, { name: project.name, recipe: "build" })}>Build</button>
        <button type="button" className="quiet-button" disabled={busy || !state?.githubAllowed} onClick={() => void plan("project-pull", `Pull ${project.name}`, { name: project.name })}>Pull from GitHub</button>
      </div>
      <label className="command-field">Commit message
        <input type="text" value={message} maxLength={200} placeholder="What changed?" onChange={event => setMessage(event.target.value)} /></label>
      <div className="timer-buttons"><button type="button" className="quiet-button" disabled={busy || !state?.githubAllowed || !message.trim()}
        onClick={() => void plan("project-push", `Commit and push ${project.name}`, { name: project.name, message: message.trim() })}>Review commit and push</button></div>
    </div>)}
    {note && <p className="quick-result" role="status">{note}</p>}

    {state && state.commands.length > 0 && <ul className="command-list">{state.commands.map(command => <li key={command.id}>
      <div><strong>{command.name}</strong> <span className="plan-step-meta">{command.project} · {command.kind === "server" ? (command.running ? "running" : "keeps running") : "runs once"} · {command.safe ? "can be remembered" : "asks every time"}</span>
        <code>{command.command}</code></div>
      <div className="timer-buttons">
        {command.kind === "server" && command.running
          ? <button type="button" className="quiet-button" disabled={busy} onClick={() => void plan("project-stop", `Stop ${command.name}`, { id: command.id })}>Stop</button>
          : <button type="button" className="quiet-button" disabled={busy} onClick={() => void plan("project-command", `Run ${command.name}`, { id: command.id })}>{command.kind === "server" ? "Start" : "Run"}</button>}
        <button type="button" className="quiet-button" disabled={busy} onClick={() => void change(() => removeCommand(command.id), `${command.name} removed.`)}>Remove</button>
      </div>
    </li>)}</ul>}

    {projects.length > 0 && <form className="command-form" onSubmit={event => { event.preventDefault();
      void change(async () => { const next = await addCommand({ ...draft, projectId }); setDraft({ projectId, name: "", command: "", safe: false, kind: "run" }); return next; }, "Command saved."); }}>
      <p className="plan-step-meta">Save your own command</p>
      <p className="handsfree-note">Type it exactly as you would in Terminal. June runs this text in the project folder after you review it; she never writes or changes it. Then say “run” followed by its name.</p>
      {projects.length > 1 && <label className="command-field">Project
        <select value={projectId} onChange={event => setDraft(d => ({ ...d, projectId: event.target.value }))}>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>}
      <label className="command-field">Name (what you will say)
        <input type="text" value={draft.name} maxLength={40} placeholder="dev server" onChange={event => setDraft(d => ({ ...d, name: event.target.value }))} /></label>
      <label className="command-field">Command
        <input type="text" value={draft.command} maxLength={500} placeholder="npm run dev" spellCheck={false} autoCapitalize="off" autoCorrect="off" onChange={event => setDraft(d => ({ ...d, command: event.target.value }))} /></label>
      <label className="command-check"><input type="checkbox" checked={draft.kind === "server"} onChange={event => setDraft(d => ({ ...d, kind: event.target.checked ? "server" : "run" }))} /> It keeps running (a dev server)</label>
      <label className="command-check"><input type="checkbox" checked={draft.safe} onChange={event => setDraft(d => ({ ...d, safe: event.target.checked }))} /> Safe to run without asking, once I tick “Don’t ask again”</label>
      <div className="timer-buttons"><button type="submit" className="quiet-button" disabled={busy || !draft.name.trim() || !draft.command.trim()}>Save command</button></div>
    </form>}
    {error && <p className="error-notice" role="alert">{error}</p>}
  </div>;
}
