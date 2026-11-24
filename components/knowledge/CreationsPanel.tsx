"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getCreations, KIND_WORDS, openCreation, type CreationState } from "@/lib/creations";

/** Documents June wrote. `refreshKey` changes after each reply, so a new file appears without a reload. */
export default function CreationsPanel({ refreshKey, onAnnounce }: { refreshKey: number; onAnnounce: (text: string) => void }) {
  const [state, setState] = useState<CreationState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  const load = useCallback(async () => {
    try { const next = await getCreations(); if (alive.current) { setState(next); setError(""); } }
    catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : "June’s documents are unavailable."); }
  }, []);
  useEffect(() => { alive.current = true; void load(); return () => { alive.current = false; }; }, [load, refreshKey]);
  async function act(id: string, how: "open" | "reveal", title: string) {
    if (busy) return;
    setBusy(true); setError("");
    try { const next = await openCreation(id, how); if (alive.current) setState(next); onAnnounce(how === "open" ? `Opened ${title}.` : `Showing ${title} in Finder.`); }
    catch (failure) { if (alive.current) { setError(failure instanceof Error ? failure.message : "June could not open that file."); void load(); } }
    finally { if (alive.current) setBusy(false); }
  }
  return <section className="timers-panel integrations-panel" aria-label="Documents June made">
    <div className="integration-group">
      <h3>Documents and websites June made</h3>
      <p className="handsfree-note">Ask in chat or by voice: “create a presentation about solar power with 6 slides”, “write a Word document about my project plan”, “make a PDF about healthy breakfasts”. It takes one to two minutes. Files are saved in Documents → {state?.folder ?? "June Documents"} and are drafts from June’s local model, so check the facts.</p>
      <p className="handsfree-note">Websites: “make a website about my bakery”, then “open it” to preview it and “publish it” to put it on GitHub Pages. Publishing is reviewed every time. Sites are saved in Documents → June Websites.</p>
      <p className="handsfree-note">June chooses a design for each one to fit the subject: colours, fonts, shapes and layout. Ask for a look (“make a dark presentation about…”, “in green”, “playful”), or after she makes one say “make it in a different style” or “redo it in dark”.</p>
      <p className="handsfree-note">To use your own look, put a file named template.docx or template.pptx in a “Templates” folder inside that folder.</p>
      {state && state.creations.length === 0 && <p className="plan-step-meta">Nothing yet.</p>}
      {state && state.creations.length > 0 && <ul className="command-list">{state.creations.map(item => <li key={item.id}>
        <div><strong>{item.title}</strong> <span className="plan-step-meta">{KIND_WORDS[item.kind]}{item.design ? ` · ${item.design}` : ""} · {new Date(item.createdAt).toLocaleString([], { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}{item.exists ? "" : " · moved or deleted"}</span>
          <code>{item.fileName}</code>
          {item.url && <a className="creation-link" href={item.url} target="_blank" rel="noreferrer noopener">{item.url.replace("https://", "")}</a>}</div>
        {item.exists && <div className="timer-buttons">
          <button type="button" className="quiet-button" disabled={busy} onClick={() => void act(item.id, "open", item.title)}>{item.kind === "site" ? "Preview" : "Open"}</button>
          <button type="button" className="quiet-button" disabled={busy} onClick={() => void act(item.id, "reveal", item.title)}>Show in Finder</button>
        </div>}
      </li>)}</ul>}
      {error && <p className="error-notice" role="alert">{error}</p>}
    </div>
  </section>;
}
