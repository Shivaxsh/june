"use client";
import { useEffect, useMemo, useState } from "react";
import { buildConstellation, type GraphInput, type GraphLinks } from "@/lib/hud/constellation";
import { GRAPH_RGB, rgb } from "@/lib/hud/palette";
export type ConstellationState = "idle" | "searching" | "cited";

/** June's knowledge graph: real documents, memories and chats with their stored links. Built once for the sky and legend. */
export function useConstellation({ documents, memories, conversations, revision }: Omit<GraphInput, "links"> & { revision: string }) {
  const [links, setLinks] = useState<GraphLinks | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/library/graph", { cache: "no-store", signal: controller.signal })
      .then(response => response.ok ? response.json() : null)
      .then(value => { if (value && Array.isArray(value.citations) && Array.isArray(value.memories)) setLinks(value as GraphLinks); })
      .catch(() => {});
    return () => controller.abort();
  }, [revision]);
  // The graph plus the full stored links (the graph itself only links the chats it draws).
  return useMemo(() => ({ ...buildConstellation({ documents, memories, conversations, links }), links }), [documents, memories, conversations, links]);
}

/** The sky's legend: an unframed key to what the stars are, at the left edge of the Observatory. */
export default function Constellation({ graph, state, onOpenChats }: { graph: ReturnType<typeof buildConstellation>; state: ConstellationState; onOpenChats: () => void }) {
  return <section className="hud-constellation" aria-label="Knowledge constellation" data-live={state !== "idle" ? "" : undefined}>
    <div className="hud-panel-head"><span className="hud-label">Constellation</span><span className="hud-label hud-accent">{state}</span></div>
    {!graph.nodes.length && <p className="hud-empty">Import a document or approve a memory and it appears in the sky.</p>}
    <ul className="hud-legend">
      {([["doc", "Documents", "documents"], ["mem", "Memories", "memories"], ["chat", "Chats", "chats"], ["cite", "Citations", "citations"]] as const).map(([type, label, key]) => {
        const shown = graph.counts[key], total = graph.totals[key];
        const count = <span>{shown < total ? `${shown} of ${total}` : total}</span>;
        const swatch = <span className="hud-swatch" style={{ background: rgb(GRAPH_RGB[type]) }} />;
        // Chat stars are pointer targets in the sky; the legend row gives keyboards the same way in.
        return <li key={type}>{type === "chat"
          ? <button type="button" className="hud-legend-button" onClick={onOpenChats} aria-label={`Chats: ${total}. Open saved chats`}>{swatch}<span>{label}</span>{count}</button>
          : <>{swatch}<span>{label}</span>{count}</>}</li>;
      })}
    </ul>
  </section>;
}
