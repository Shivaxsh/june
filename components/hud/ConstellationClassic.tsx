"use client";
import { useEffect, useRef, useState } from "react";
import type { buildConstellation } from "@/lib/hud/constellation";
import { GRAPH_RGB, LABEL_RGB, LINE_RGB, rgb, rgba } from "@/lib/hud/palette";
import { useReducedMotion } from "@/lib/hud/useReducedMotion";
import type { ConstellationState } from "./Constellation";

/** June's knowledge constellation (classic HUD): real documents, memories and chats with their links, in a boxed panel. */
export default function ConstellationClassic({ graph, state, cited, activeChat, onOpenChat, onOpenChats }: {
  graph: ReturnType<typeof buildConstellation>; state: ConstellationState; cited: string[]; activeChat: string | null;
  onOpenChat: (id: string) => void; onOpenChats: () => void;
}) {
  const reduced = useReducedMotion();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = useState<{ label: string; x: number; y: number; w: number } | null>(null);
  const positions = useRef<{ x: number; y: number; r: number; i: number }[]>([]);

  useEffect(() => {
    const element = canvas.current; if (!element) return;
    const context = element.getContext("2d"); if (!context) return;
    let frame = 0, last = 0;
    const draw = (time: number) => {
      const w = element.clientWidth, h = element.clientHeight; if (!w || !h) return;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      if (element.width !== Math.round(w * dpr)) { element.width = Math.round(w * dpr); element.height = Math.round(h * dpr); }
      context.setTransform(dpr, 0, 0, dpr, 0, 0); context.clearRect(0, 0, w, h);
      const nodes = graph.nodes;
      if (!nodes.length) return;
      const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y);
      const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
      const s = Math.min((w - 100) / Math.max(1, maxX - minX), (h - 40) / Math.max(1, maxY - minY), 3);
      const X = (x: number) => 20 + (x - minX) * s + (w - 100 - (maxX - minX) * s) / 2, Y = (y: number) => 20 + (y - minY) * s + (h - 40 - (maxY - minY) * s) / 2;
      const pulse = reduced ? 1 : .5 + .5 * Math.sin(time / 1000 * 6);
      for (const e of graph.edges) {
        const A = nodes[e.a], B = nodes[e.b];
        const hot = state === "cited" && ((B.type === "doc" && cited.includes(B.id) && A.id === activeChat) || (A.type === "doc" && cited.includes(A.id) && B.id === activeChat));
        context.strokeStyle = hot ? rgba(GRAPH_RGB.cite, .6 + .3 * pulse) : e.type === "cite" ? rgba(GRAPH_RGB.cite, .16) : rgba(LINE_RGB, .12);
        context.lineWidth = hot ? 1.6 : .8; context.beginPath(); context.moveTo(X(A.x), Y(A.y)); context.lineTo(X(B.x), Y(B.y)); context.stroke();
      }
      positions.current = [];
      const labels: [number, number, number, number][] = [];
      context.font = '11px "JetBrains Mono", ui-monospace, monospace';
      nodes.forEach((n, i) => {
        const c = GRAPH_RGB[n.type]; let r = n.type === "doc" ? 6 : n.type === "chat" ? 3.6 : 3, a = .85;
        if (n.type === "doc" && state === "searching") { r += 2.2 * pulse; a = .6 + .4 * pulse; }
        if (n.type === "doc" && state === "cited" && cited.includes(n.id)) r += 3 + 2 * pulse;
        if (n.type === "chat" && n.id === activeChat) r += 1.5;
        const x = X(n.x), y = Y(n.y); positions.current.push({ x, y, r, i });
        context.fillStyle = rgba(c, a * .22); context.beginPath(); context.arc(x, y, r * 2.6, 0, 6.2832); context.fill();
        context.fillStyle = rgba(c, a); context.beginPath(); context.arc(x, y, r, 0, 6.2832); context.fill();
        if (n.type === "doc") {
          // Only draw a name where it fits without colliding; hover still reveals every name.
          const width = context.measureText(n.label).width, box: [number, number, number, number] = [x + r + 5, y - 8, x + r + 7 + width, y + 6];
          const fits = box[2] <= w - 2 && !labels.some(b => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1]);
          if (fits) { labels.push(box); context.fillStyle = rgba(LABEL_RGB, .85); context.fillText(n.label, x + r + 6, y + 3); }
        }
      });
    };
    const animate = state !== "idle" && !reduced;
    const loop = (time: number) => { frame = requestAnimationFrame(loop); if (document.hidden || time - last < 66) return; last = time; draw(time); };
    if (animate) frame = requestAnimationFrame(loop); else draw(0);
    const resize = new ResizeObserver(() => { if (!animate) draw(0); });
    resize.observe(element);
    return () => { cancelAnimationFrame(frame); resize.disconnect(); };
  }, [graph, state, cited, activeChat, reduced]);

  const pick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const box = event.currentTarget.getBoundingClientRect(), x = event.clientX - box.left, y = event.clientY - box.top;
    let best: { i: number; d: number } | null = null;
    for (const p of positions.current) { const d = Math.hypot(p.x - x, p.y - y); if (d < Math.max(8, p.r * 2) && (!best || d < best.d)) best = { i: p.i, d }; }
    return best ? { node: graph.nodes[best.i], x, y } : null;
  };

  return <section className="hud-panel hud-constellation" aria-label="Knowledge constellation">
    <div className="hud-panel-head"><span className="hud-label">Constellation</span><span className="hud-label hud-accent">{state}</span></div>
    <div className="hud-constellation-stage">
      <canvas ref={canvas} aria-hidden="true"
        onPointerMove={event => { const found = pick(event); setHover(found ? { label: found.node.type === "doc" ? found.node.label : found.node.type === "chat" ? `Chat · ${found.node.label}` : "Approved memory", x: found.x, y: found.y, w: event.currentTarget.clientWidth } : null); event.currentTarget.style.cursor = found?.node.type === "chat" ? "pointer" : "default"; }}
        onPointerLeave={() => setHover(null)} onPointerCancel={() => setHover(null)}
        onClick={event => { const found = pick(event); if (found?.node.type === "chat") onOpenChat(found.node.id); }} />
      {hover && <span className="hud-graph-tip" style={hover.x > hover.w / 2 ? { right: hover.w - hover.x + 12, top: hover.y - 10 } : { left: hover.x + 12, top: hover.y - 10 }}>{hover.label}</span>}
      {!graph.nodes.length && <p className="hud-empty">Import a document or approve a memory and it appears here.</p>}
    </div>
    <ul className="hud-legend">
      {([["doc", "Documents", "documents"], ["mem", "Memories", "memories"], ["chat", "Chats", "chats"], ["cite", "Citations", "citations"]] as const).map(([type, label, key]) => {
        const shown = graph.counts[key], total = graph.totals[key];
        const count = <span>{shown < total ? `${shown} of ${total}` : total}</span>;
        const swatch = <span className="hud-swatch" style={{ background: rgb(GRAPH_RGB[type]) }} />;
        // Chat nodes are mouse targets on the canvas; the legend row gives keyboards the same way in.
        return <li key={type}>{type === "chat"
          ? <button type="button" className="hud-legend-button" onClick={onOpenChats} aria-label={`Chats: ${total}. Open saved chats`}>{swatch}<span>{label}</span>{count}</button>
          : <>{swatch}<span>{label}</span>{count}</>}</li>;
      })}
    </ul>
  </section>;
}
