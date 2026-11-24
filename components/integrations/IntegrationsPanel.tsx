"use client";
import { useMemo, useRef, useState } from "react";
import { CONNECTION_WORDS, forgetApprovals, proposePlan, RISK_WORDS, type Capability, type Intent, type PlanInput } from "@/lib/integrations";
import PlanCard from "./PlanCard";
import type { Integrations } from "./useIntegrations";

const checked = (at: number | null) => at === null ? "" : ` · checked ${new Date(at).toLocaleString([], { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}`;

/**
 * Systems → Integrations. What June can do, which outside services are actually
 * connected (as the server last verified), and plans waiting for review. Nothing here
 * connects an account or runs anything without an exact, reviewed plan.
 */
export default function IntegrationsPanel({ integrations, onAnnounce, onForgotten }: { integrations: Integrations; onAnnounce(text: string): void; onForgotten?(): void }) {
  const { capabilities, connections, plans, serverNow, receivedAt, error } = integrations;
  const [busy, setBusy] = useState(false);
  const [requestError, setRequestError] = useState("");
  const [confirmForget, setConfirmForget] = useState(false);
  const inFlight = useRef(false);
  const reviewRef = useRef<HTMLDivElement>(null);
  const byId = useMemo(() => new Map((capabilities ?? []).map(c => [c.id, c] as [string, Capability])), [capabilities]);
  const reviewing = plans.filter(p => p.status === "proposed");
  const active = plans.filter(p => p.status === "approved" || p.status === "running");
  const history = plans.filter(p => p.status !== "proposed" && p.status !== "approved" && p.status !== "running");
  const openVSCode = (capabilities ?? []).find(c => /(?:^|[.:])open-vscode$/.test(c.id));
  const openApp = byId.get("app.open");

  const [quickRun, setQuickRun] = useState<{ id: string; label: string } | null>(null);
  async function request(input?: PlanInput, name = "VS Code") {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setRequestError("");
    try {
      const reply = input ? await proposePlan("open-app", undefined, undefined, input) : await proposePlan("open-vscode");
      integrations.upsert(reply.plan, reply.serverNow);
      if (input) void integrations.refresh();
      // The review card appears higher up; bring it into view so it is not missed.
      requestAnimationFrame(() => reviewRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
      onAnnounce(reply.plan.status === "proposed" ? `A plan to open ${name} is ready for your review.` : `Open ${name}: ${reply.plan.status}.`);
    } catch (failure) { setRequestError(failure instanceof Error ? failure.message : "June could not reach Integrations."); }
    finally { inFlight.current = false; setBusy(false); }
  }

  async function quick(intent: Intent, label: string, input?: PlanInput) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setRequestError("");
    try {
      const reply = await proposePlan(intent, undefined, undefined, input);
      integrations.upsert(reply.plan, reply.serverNow);
      setQuickRun({ id: reply.plan.id, label });
      requestAnimationFrame(() => reviewRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
      onAnnounce(reply.plan.status === "proposed" ? `${label} is ready for your review.` : `${label}: ${reply.plan.status}.`);
    } catch (failure) { setRequestError(failure instanceof Error ? failure.message : "June could not reach Integrations."); }
    finally { inFlight.current = false; setBusy(false); }
  }
  const off = (id: string) => busy || byId.get(id)?.available === false;
  // A remembered action runs without a card, so its checked result is shown here instead of nowhere.
  const quickPlan = quickRun ? plans.find(p => p.id === quickRun.id) : undefined;
  const quickNote = !quickRun || !quickPlan ? "" : quickPlan.status === "proposed" ? `${quickRun.label}: review the card above.`
    : quickPlan.status === "approved" || quickPlan.status === "running" ? `${quickRun.label}: working…`
    : quickPlan.steps.map(step => step.result?.message).filter(Boolean).join(" ") || `${quickRun.label}: ${quickPlan.status}.`;

  async function forget() {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setRequestError("");
    try {
      const reply = await forgetApprovals();
      integrations.replacePlans(reply.plans, reply.serverNow);
      setConfirmForget(false); onForgotten?.();
      onAnnounce("Remembered approvals forgotten. June will ask for review again, and approved plans that had not started were cancelled.");
    } catch (failure) { setRequestError(failure instanceof Error ? failure.message : "June could not reach Integrations."); }
    finally { inFlight.current = false; setBusy(false); }
  }

  return <section className="timers-panel integrations-panel" aria-label="Integrations">
    <span className="eyebrow">Integrations · reviewed before anything runs</span>
    <h2>Connect <em>carefully.</em></h2>
    <p>June prepares a plan, shows exactly what each step will do, and waits for your approval. Sending, publishing and payments are reviewed every time. Accounts are connected only with your explicit permission.</p>

    <div className="integration-request">
      <button type="button" className="quiet-button" disabled={busy || openVSCode?.available === false} onClick={() => void request()}>Open VS Code</button>
      <span className="handsfree-note">{openVSCode?.available === false ? openVSCode.unavailableReason : "Prepares a plan to open or bring VS Code forward."}</span>
    </div>
    {integrations.apps && integrations.apps.length > 0 && <div className="integration-group" aria-label="Apps">
      <h3>Apps June can open</h3>
      <p className="handsfree-note">Say or type “open Chrome and Figma”. Tick “Don&apos;t ask again” on an app&apos;s card to let June open it by voice.</p>
      <ul className="app-list">{integrations.apps.map(app => <li key={app.id}>
        <button type="button" className="quiet-button" disabled={busy || openApp?.available === false} onClick={() => void request({ apps: [app.id] }, app.label)}>Open {app.label}</button>
        <span className="plan-step-meta">{app.remembered ? "Opens without asking" : "Asks first"}</span>
      </li>)}</ul>
      {openApp?.available === false && <p className="handsfree-note">{openApp.unavailableReason}</p>}
    </div>}
    <div className="integration-group" aria-label="Quick actions">
      <h3>Quick actions</h3>
      <p className="handsfree-note">Each one shows a card first. Tick “Don&apos;t ask again” on a card to run it straight away next time.</p>
      <p className="plan-step-meta">Developer</p>
      <div className="timer-buttons">
        <button type="button" className="quiet-button" disabled={off("app.open")} onClick={() => void quick("coding-session", "Start coding session")}>Start coding session</button>
        <button type="button" className="quiet-button" disabled={off("quick.keep-awake")} onClick={() => void quick("keep-awake", "Keep Mac awake", { minutes: 60 })}>Keep Mac awake 1 hour</button>
        <button type="button" className="quiet-button" disabled={off("quick.allow-sleep")} onClick={() => void quick("allow-sleep", "Let Mac sleep")}>Let Mac sleep</button>
      </div>
      <p className="handsfree-note">By voice or text, for a project saved in Hands: “git status of June”, “open June on GitHub”, “free port 3000” (always reviewed).</p>
      <p className="plan-step-meta">Designer</p>
      <div className="timer-buttons">
        <button type="button" className="quiet-button" disabled={off("app.open")} onClick={() => void quick("design-workspace", "Open design workspace")}>Open design workspace</button>
        <button type="button" className="quiet-button" disabled={off("quick.appearance")} onClick={() => void quick("appearance", "Switch light / dark", { mode: "toggle" })}>Switch light / dark</button>
        <button type="button" className="quiet-button" disabled={off("app.open")} onClick={() => void quick("open-app", "Take a screenshot", { apps: ["screenshot"] })}>Take a screenshot</button>
        <button type="button" className="quiet-button" disabled={off("app.open")} onClick={() => void quick("open-app", "Colour picker", { apps: ["color-meter"] })}>Colour picker</button>
        <button type="button" className="quiet-button" disabled={off("quick.convert-images")} onClick={() => void quick("convert-images", "Convert images", { format: "png" })}>Convert images to PNG</button>
      </div>
      {quickNote && <p className="quick-result" role="status">{quickNote}</p>}
      <p className="handsfree-note">Images: put them in a folder named “June Images” in your home folder. Copies go to “June Images/converted”; originals are never changed. You can also say “resize my images to 1200 pixels”.</p>
    </div>
    {requestError && <p className="error-notice" role="alert">{requestError}</p>}
    {error && <p className="error-notice" role="alert">{error} <button type="button" className="quiet-button" onClick={() => void integrations.refresh()}>Retry</button></p>}

    {reviewing.length > 0 && <div ref={reviewRef} className="integration-group" aria-label="Plans waiting for review">
      <h3>Waiting for review</h3>
      {reviewing.map(plan => <PlanCard key={plan.id} plan={plan} capabilities={byId} serverNow={serverNow} receivedAt={receivedAt}
        onChange={integrations.upsert} onRefresh={() => void integrations.refreshPlans()} onAnnounce={onAnnounce} />)}
    </div>}

    {active.length > 0 && <div className="integration-group" aria-label="Plans in progress">
      <h3>In progress</h3>
      {active.map(plan => <PlanCard key={plan.id} plan={plan} capabilities={byId} serverNow={serverNow} receivedAt={receivedAt}
        onChange={integrations.upsert} onRefresh={() => void integrations.refreshPlans()} onAnnounce={onAnnounce} />)}
    </div>}

    {history.length > 0 && <details className="integration-group">
      <summary>Recent plans ({history.length})</summary>
      {history.map(plan => <PlanCard key={plan.id} plan={plan} capabilities={byId} serverNow={serverNow} receivedAt={receivedAt}
        onChange={integrations.upsert} onRefresh={() => void integrations.refreshPlans()} onAnnounce={onAnnounce} />)}
    </details>}

    <div className="integration-group" aria-label="Connections">
      <h3>Connections</h3>
      {connections === null ? <p className="handsfree-note">Checking connections…</p> : connections.length === 0 ? <p className="handsfree-note">No connections are set up.</p> :
        <ul className="integration-list">{connections.map(c => <li key={c.id} className={`connection is-${c.state}`}>
          <div className="plan-step-head"><strong>{c.label}</strong><span>{CONNECTION_WORDS[c.state]}</span></div>
          <p>{c.message}{checked(c.checkedAt)}</p>
          <p className="plan-step-meta">{!c.hosts.length ? "No online access enabled" : c.state === "connected" ? `Talks to: ${c.hosts.join(", ")}` : c.enabled ? `Allowed to contact: ${c.hosts.join(", ")} · not checked yet` : `Would contact: ${c.hosts.join(", ")} · not enabled`}{c.scopes.length ? ` · Allowed: ${c.scopes.join(", ")}` : ""}</p>
        </li>)}</ul>}
    </div>

    <div className="integration-group" aria-label="Remembered approvals">
      <h3>Remembered approvals</h3>
      {confirmForget
        ? <div className="plan-actions">
            <p className="handsfree-note">June will ask for review again for every action, including Hands&apos; open-without-review setting. Approved plans that have not started will be cancelled; a step already running may still finish.</p>
            <div className="timer-buttons">
              <button type="button" className="quiet-button" disabled={busy} onClick={() => void forget()}>Forget them now</button>
              <button type="button" className="quiet-button" disabled={busy} onClick={() => setConfirmForget(false)}>Keep them</button>
            </div>
          </div>
        : <div className="integration-request">
            <button type="button" className="quiet-button" disabled={busy} onClick={() => setConfirmForget(true)}>Forget remembered approvals</button>
            <span className="handsfree-note">Only exact, local, reversible requests can be remembered.</span>
          </div>}
    </div>

    <details className="integration-group">
      <summary>What June can do ({capabilities?.filter(c => c.available).length ?? 0} available{capabilities ? ` of ${capabilities.length}` : ""})</summary>
      {capabilities === null ? <p className="handsfree-note">Checking capabilities…</p> :
        <ul className="integration-list">{[...capabilities].sort((a, b) => Number(b.available) - Number(a.available)).map(c => <li key={c.id} className={c.available ? "capability is-available" : "capability is-unavailable"}>
          <div className="plan-step-head"><strong>{c.label}</strong><span>{c.available ? RISK_WORDS[c.risk] : "Not available"}</span></div>
          <p className="plan-step-meta">{c.available ? (c.rememberable ? "You can choose not to be asked again for an exact request." : "Reviewed every time.") : c.unavailableReason}</p>
        </li>)}</ul>}
    </details>
  </section>;
}
