"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { allowScreen, getScreen, screenRequests, type ScreenState } from "@/lib/screen";

type Props = { onAnnounce: (text: string) => void };
const PERMISSION = "macOS hasn’t given “June Screen” permission. Open System Settings → Privacy & Security → Screen & System Audio Recording, switch on June Screen, then click Allow Screen again.";

/** Screen reading: off until turned on. When on, asking about the screen in chat reads it once; nothing is kept. */
export default function ScreenPanel({ onAnnounce }: Props) {
  const [screen, setScreen] = useState<ScreenState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  const requests = useRef(screenRequests());
  // A status read that finishes after a newer change (or read) is stale and must not undo what the person just did.
  const load = useCallback(async () => {
    const current = requests.current.read();
    try { const next = await getScreen(); if (alive.current && current()) { setScreen(next); setError(""); } }
    catch { if (alive.current && current()) setError("Screen reading is unavailable."); }
  }, []);
  useEffect(() => { alive.current = true; void load(); return () => { alive.current = false; }; }, [load]);

  async function toggle() {
    if (!screen) return;
    const change = requests.current.change();  // synchronous guard: a second click before re-render does nothing
    if (!change) return;
    setBusy(true); setError("");
    let recover = false;
    try {
      const next = await allowScreen(!screen.enabled);
      if (!alive.current || !change.current()) return;
      setScreen(next);
      onAnnounce(next.enabled ? "June can now read your screen when you ask." : "June will no longer read your screen.");
    } catch (failure) {
      const code = (failure as { code?: string }).code;
      if (alive.current) setError(code === "screen-permission" ? PERMISSION : failure instanceof Error ? failure.message : "June could not change that.");
      recover = code === "screen-permission";
    } finally {
      change.done(); if (alive.current) setBusy(false);
      // After the guard is released: a read started while it is held would be ignored. Shows the real setting, never a guessed one.
      if (recover && alive.current) void load();
    }
  }

  return <section className="timers-panel integrations-panel" aria-label="Screen">
    <div className="integration-group">
      <h3>Screen</h3>
      <p className="handsfree-note">When this is on, ask in chat, for example “what does the error on my screen mean?” or “summarise what’s on my screen”. June reads the text on your whole screen once, on this Mac, to answer that one question. No screenshot is saved, and the text isn’t kept. Text on the screen is treated as information, never as instructions.</p>
      {screen && !screen.installed && <p className="error-notice">The June Screen helper isn’t installed yet.</p>}
      {screen && screen.enabled && screen.problem && <><p className="error-notice" role="alert">{screen.problem === "screen-permission" ? PERMISSION : "June Screen didn’t answer just now."}</p>
        <div className="timer-buttons"><button type="button" className="quiet-button" disabled={busy}
          onClick={() => void load().then(() => onAnnounce("Checked the screen permission again."))}>Check again</button></div></>}
      {error && <p className="error-notice" role="alert">{error}</p>}
      {screen && <div className="plan-actions">
        <p className="plan-step-meta">{screen.enabled ? (screen.problem ? "Screen: on, but not working right now." : "Screen: on. June reads it only when you ask.") : "Screen: off. June can’t see your screen."}</p>
        <div className="timer-buttons"><button type="button" className="quiet-button" disabled={busy || !screen.installed} onClick={() => void toggle()}>
          {busy ? "Waiting for macOS…" : screen.enabled ? "Turn off screen reading" : "Allow Screen"}</button></div>
        {!screen.enabled && <p className="handsfree-note">The first time, macOS asks about “June Screen”. Allow it in System Settings, then click Allow Screen again.</p>}
      </div>}
    </div>
  </section>;
}
