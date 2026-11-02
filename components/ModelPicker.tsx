"use client";

import { useEffect, useRef, useState } from "react";

type Model = { id: string; label: string; description: string; sizeBytes: number };
type Catalog = { active: string; models: Model[] };

export default function ModelPicker({ activeModel, disabled, changing, onChanging, onChanged }: {
  activeModel?: string; disabled: boolean; changing: boolean;
  onChanging: (value: boolean) => void; onChanged: () => void;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const request = useRef<AbortController | null>(null);
  const channel = useRef<BroadcastChannel | null>(null);
  const changed = useRef(onChanged); changed.current = onChanged;

  async function refresh() {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setLoading(true); setError("");
    try {
      const response = await fetch("/api/models", { cache: "no-store", signal: controller.signal });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || "Cannot load installed models.");
      if (typeof data.active !== "string" || !Array.isArray(data.models)
        || !data.models.every((m: Model) => typeof m.id === "string" && typeof m.label === "string" && typeof m.description === "string")) {
        throw new Error("June returned an invalid model list. Try Refresh models.");
      }
      if (controller.signal.aborted) return;
      setCatalog(data); setSelected(data.active);
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Cannot load installed models.");
    } finally { if (!controller.signal.aborted) setLoading(false); }
  }

  useEffect(() => { void refresh(); return () => request.current?.abort(); }, [activeModel]);
  useEffect(() => {
    if (!("BroadcastChannel" in window)) return;
    const connection = new BroadcastChannel("june-model-selection"); channel.current = connection;
    connection.onmessage = () => { changed.current(); void refresh(); };
    return () => { connection.close(); channel.current = null; };
  }, []);

  async function apply() {
    if (disabled || changing || !selected || selected === catalog?.active) return;
    onChanging(true); setError(""); setNotice("");
    // Selection stays application-owned; no model download or arbitrary URL is accepted.
    try {
      const response = await fetch("/api/models", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model: selected }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || "Model change failed. Refresh to check the active model.");
      setCatalog(previous => previous ? { ...previous, active: data.active } : previous);
      setNotice(data.message); changed.current(); channel.current?.postMessage({ model: data.active });
    } catch (e) { setError(e instanceof Error ? e.message : "Model change failed. Refresh to check the active model."); }
    finally { onChanging(false); }
  }

  const choice = catalog?.models.find(model => model.id === selected);
  return <details className="model-picker">
    <summary>Local model <span>{changing ? "Switching…" : "Choose speed or accuracy"}</span></summary>
    <div className="model-picker-body">
      <label htmlFor="local-model">Installed model</label>
      <div className="model-picker-actions">
        <select id="local-model" value={selected} disabled={disabled || changing || loading || !catalog?.models.length}
          aria-describedby="model-choice-note" onChange={event => { setSelected(event.target.value); setNotice(""); }}>
          {!catalog && <option value="">Loading models…</option>}
          {catalog && !catalog.models.some(model => model.id === catalog.active) && <option value={catalog.active} disabled>{catalog.active} · missing</option>}
          {catalog?.models.map(model => <option key={model.id} value={model.id}>{model.label}{model.id === catalog.active ? " · active" : ""}</option>)}
        </select>
        <button className="quiet-button" onClick={() => void apply()} disabled={disabled || changing || loading || !choice || selected === catalog?.active}>{changing ? "Switching…" : "Use this model"}</button>
        <button className="quiet-button" onClick={() => void refresh()} disabled={changing || loading}>Refresh models</button>
      </div>
      <p id="model-choice-note">{choice?.description || "Only models already installed on this Mac appear here."}</p>
      <p className="model-picker-hint">Stop voice, hands-free and replies before switching. This choice applies to all June tabs and is saved on this Mac. Chats, approved memories and Nicky stay unchanged. For a fresh comparison, start a New chat.</p>
      {error && <p className="error-message" role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
    </div>
  </details>;
}
