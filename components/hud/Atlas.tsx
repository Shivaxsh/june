"use client";
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import type { Level } from "@/lib/orb/audio-controller";
import type { buildConstellation, GraphLinks } from "@/lib/hud/constellation";
import { at, cellNumber, cells, chatGlyph, drawn, fan, frameFrom, lean, memoryMark, docApex, spread, type Frame, type Point } from "@/lib/hud/atlas";
import { recencyOf } from "@/lib/hud/sky";
import { useReducedMotion } from "@/lib/hud/useReducedMotion";
import type { ConstellationState } from "./Constellation";

type Graph = ReturnType<typeof buildConstellation> & { links?: GraphLinks | null };
export type AtlasNumbers = { params: number | null; chats: number | null; memories: number | null; docs: number; answerMs: number | null; firstAudioMs: number | null };
const CYAN = "95,200,210", WHITE = "242,244,245", FONT = '"Avenir Next", "Helvetica Neue", Arial, sans-serif';
const SIGNAL_MS = 1100, SHOCK_MS = 700, MARK_MS = 1200, DRAW_MS = 1600, BUNDLE = 5;
/** Tags are deliberately tiny (user request): document name, citation count, memory tag. */
const TAG_PX = 8.5, COUNT_PX = 6.5, MEM_PX = 6.5;
const CELL_CAPTIONS = ["Billion params", "Chats", "Memories", "Documents", "Answer · s", "First audio · s"];

/** Specimen atlas: June's real documents, chats and memories as a neural-network plate around the unchanged orb. */
export default function Atlas({ graph, conversations, memoryIds, numbers, state, cited, citedKey, activeChat, level, listening, thinking, shockSeq, hitArea, orbBox, railBox, onOpenChat, onCometArrive }: {
  graph: Graph; conversations: { id: string; updated?: number }[]; memoryIds: string[]; numbers: AtlasNumbers;
  state: ConstellationState; cited: string[]; citedKey: string; activeChat: string | null;
  level: Level; listening: boolean; thinking: boolean; shockSeq: number;
  hitArea: RefObject<HTMLElement | null>; orbBox: RefObject<HTMLElement | null>; railBox: RefObject<HTMLElement | null>;
  onOpenChat: (id: string) => void; onCometArrive: (documentId: string) => void;
}) {
  const reduced = useReducedMotion();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = useState<{ label: string; x: number; y: number; w: number } | null>(null);
  const recency = useMemo(() => recencyOf(conversations), [conversations]);
  // Real data only: documents with the chats that cited them, chats, memories.
  const data = useMemo(() => {
    const docs = graph.nodes.map((n, i) => ({ n, i })).filter(d => d.n.type === "doc").slice(0, 8);
    const chats = graph.nodes.filter(n => n.type === "chat");
    const mems = graph.nodes.filter(n => n.type === "mem");
    // Every stored citation counts, not only those of the chats drawn as glyphs: one entry per citing conversation.
    const citing = new Map<string, Set<string>>();
    for (const c of graph.links?.citations ?? []) citing.set(c.documentId, (citing.get(c.documentId) ?? new Set()).add(c.conversation));
    return { docs: docs.map(d => ({ id: d.n.id, label: d.n.label.toUpperCase(), chats: [...(citing.get(d.n.id) ?? [])] })), chats, mems };
  }, [graph]);
  const frame = useRef<Frame | null>(null), railRight = useRef(0);
  const tags = useRef<{ x: number; y: number; w: number; h: number; label: string }[]>([]);
  const glyphs = useRef<{ x: number; y: number; id: string; label: string }[]>([]);
  const signals = useRef<{ doc: number; docId: string; started: number; done: boolean }[]>([]);
  const flashes = useRef(new Map<number, number>()), marks = useRef<{ i: number; started: number }[]>([]);
  const shockAt = useRef(0), born = useRef(0), spin = useRef(0);
  const live = useRef({ state, cited, activeChat, listening, thinking, reduced, numbers, onCometArrive });
  live.current = { state, cited, activeChat, listening, thinking, reduced, numbers, onCometArrive };

  useEffect(() => { if (graph.nodes.length && !born.current) born.current = performance.now(); }, [graph.nodes.length]);

  // Signal: each newly cited document sends a cyan pulse down its fan into the orb.
  const lastKey = useRef("");
  useEffect(() => {
    if (!citedKey || citedKey === lastKey.current) return;
    lastKey.current = citedKey;
    const now = performance.now();
    cited.forEach((id, k) => {
      const doc = data.docs.findIndex(d => d.id === id);
      if (doc < 0 || reduced) { onCometArrive(id); if (doc >= 0) flashes.current.set(doc, now); return; }
      signals.current.push({ doc, docId: id, started: now + k * 180, done: false });
    });
  }, [citedKey, cited, data, reduced, onCometArrive]);

  // Memory ignition: a memory that did not exist on the previous render draws its crosshair in.
  const known = useRef<Set<string> | null>(null);
  useEffect(() => {
    const previous = known.current; known.current = new Set(memoryIds);
    if (!previous || reduced) return;
    data.mems.forEach((m, i) => { if (!previous.has(m.id)) marks.current.push({ i, started: performance.now() }); });
  }, [memoryIds, data, reduced]);

  const lastShock = useRef(shockSeq);
  useEffect(() => { if (shockSeq !== lastShock.current) { lastShock.current = shockSeq; if (!reduced) shockAt.current = performance.now(); } }, [shockSeq, reduced]);

  useEffect(() => {
    const element = canvas.current; if (!element) return;
    const g = element.getContext("2d"); if (!g) return;
    let raf = 0, last = 0, lastSpin = 0, visible = true;
    const measure = () => {
      const box = element.getBoundingClientRect(), orb = orbBox.current?.getBoundingClientRect(), rail = railBox.current?.getBoundingClientRect();
      if (!orb || !box.width) { frame.current = null; return; }
      frame.current = frameFrom(box.width, box.height, { left: orb.left - box.left, top: orb.top - box.top, width: orb.width, height: orb.height });
      railRight.current = rail && rail.width ? rail.right - box.left : 0;
    };
    const tag = (x: number, y: number, text: string, fill: string, ink: string, size = TAG_PX) => {
      g.font = `600 ${size}px ${FONT}`; const w = g.measureText(text).width + 7, h = size + 4;
      g.fillStyle = fill; g.fillRect(x, y - h / 2, w, h); g.fillStyle = ink; g.fillText(text, x + 3.5, y + size * .36); return { w, h };
    };
    // Tag apexes: on the orb's left arc, clear of the rail, never stacked on each other.
    const apexesFor = (f: Frame) => data.docs.map((d, i) => {
      g.font = `600 ${TAG_PX}px ${FONT}`; const tw = g.measureText(d.label).width + 7, a = docApex(i, data.docs.length, f, railRight.current);
      return { x: Math.max(a.x, railRight.current + 18 + tw + 18), y: a.y };
    });
    const draw = (now: number) => {
      const W = element.clientWidth, H = element.clientHeight; if (!W || !H) return;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      if (element.width !== Math.round(W * dpr) || element.height !== Math.round(H * dpr)) { element.width = Math.round(W * dpr); element.height = Math.round(H * dpr); measure(); }
      if (!frame.current) measure();
      const f = frame.current; g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H); if (!f) return;
      const L = live.current, still = L.reduced, age = born.current ? now - born.current : DRAW_MS;
      const lvl = L.listening && !still ? Math.min(1, Math.max(0, level.current)) : 0;
      if (L.thinking && !still) spin.current += Math.min(.05, (now - lastSpin) / 1000) * .22; lastSpin = now;

      // Faint orbit arcs (ornament).
      g.lineWidth = 1; g.strokeStyle = `rgba(${WHITE},.06)`;
      for (const k of [1.7, 2.35]) { g.beginPath(); g.arc(f.cx, f.cy, f.R * k, Math.PI * .9, Math.PI * 2.35); g.stroke(); }

      // Document fans: converging hairlines from each cyan tag into the orb rim.
      tags.current = []; let strandIndex = 0; const totalStrands = data.docs.reduce((s, d) => s + Math.max(1, d.chats.length), 0);
      const apexes = spread(apexesFor(f), 28, 24, H - 24);
      data.docs.forEach((d, i) => {
        g.font = `600 ${TAG_PX}px ${FONT}`; const tw = g.measureText(d.label).width + 7;
        const apex = apexes[i];
        const strands = fan(apex, d.chats, f, d.id);
        const hot = L.state === "cited" && L.cited.includes(d.id);
        for (const s of strands) {
          const t = still ? 1 : drawn(strandIndex++, totalStrands, age, DRAW_MS); if (t <= 0) continue;
          const steps = Math.max(2, Math.round(28 * t));
          for (let b = 0; b < BUNDLE; b++) {
            const off = (b - (BUNDLE - 1) / 2) * (2.2 + 2.4 * s.seed);
            g.strokeStyle = `rgba(${hot ? CYAN : WHITE},${(hot ? .5 : .16 + .14 * s.seed) * (b === 0 ? 1.6 : 1)})`; g.lineWidth = hot && b === 0 ? 1 : .55;
            g.beginPath();
            for (let k = 0; k <= steps; k++) {
              const u = k / 28, p = lean(at(s, u), u, lvl, f), w = Math.sin(Math.PI * u) * off;  // ends meet; the middle fans out
              const q = at(s, Math.min(1, u + .01)), dx = q.x - p.x, dy = q.y - p.y, l = Math.hypot(dx, dy) || 1;
              const x = p.x - dy / l * w, y = p.y + dx / l * w; if (k) g.lineTo(x, y); else g.moveTo(x, y);
            }
            g.stroke();
          }
        }
        const flash = flashes.current.get(i), lit = flash !== undefined && now - flash < 900;
        // The name is plain teal text (no box), so it reads clearly on black; it flashes white when its pulse lands.
        g.font = `600 ${TAG_PX}px ${FONT}`; g.fillStyle = lit ? `rgb(${WHITE})` : `rgb(${CYAN})`;
        g.fillText(d.label, apex.x - tw - 14 + 3.5, apex.y + TAG_PX * .36);
        const box = { w: tw, h: TAG_PX + 4 };
        tag(apex.x - 11, apex.y, String(d.chats.length), `rgba(${WHITE},.92)`, "#000", COUNT_PX);
        g.fillStyle = `rgb(${CYAN})`; g.fillRect(apex.x - 1, apex.y - 1, 2, 2);
        tags.current.push({ x: apex.x - tw - 14, y: apex.y - box.h / 2 - 3, w: box.w + 14, h: box.h + 6, label: `${d.label} · cited in ${d.chats.length} chat${d.chats.length === 1 ? "" : "s"}` });
      });

      // Phones keep only the tags and fans: the orb fills the width there.
      const roomy = W >= 640;
      // Chats: square glyphs, brighter when recent; the open chat is cyan.
      glyphs.current = [];
      if (roomy) data.chats.forEach((c, i) => {
        const p = chatGlyph(i, c.id, f, railRight.current), a = (.22 + .55 * (recency.get(c.id) ?? 0)) * (still ? 1 : Math.min(1, age / DRAW_MS));
        const on = c.id === L.activeChat;
        g.strokeStyle = on ? `rgb(${CYAN})` : `rgba(${WHITE},${a})`; g.lineWidth = 1; g.strokeRect(p.x - 3, p.y - 3, 6, 6);
        if (on) { g.fillStyle = `rgb(${CYAN})`; g.fillRect(p.x - 1.5, p.y - 1.5, 3, 3); }
        glyphs.current.push({ x: p.x, y: p.y, id: c.id, label: `Chat · ${c.label}` });
      });

      // Memories: cyan crosshairs (a new one draws itself in, with its tag).
      marks.current = marks.current.filter(m => now - m.started < MARK_MS);
      data.mems.forEach((m, i) => {
        const p = memoryMark(i, data.mems.length, f), mark = marks.current.find(x => x.i === i);
        const t = mark ? (now - mark.started) / MARK_MS : 1, s = 2.6;
        g.strokeStyle = `rgb(${CYAN})`; g.lineWidth = .9; g.beginPath();
        const a1 = Math.min(1, t * 2), a2 = Math.max(0, Math.min(1, t * 2 - 1));
        g.moveTo(p.x - s, p.y - s); g.lineTo(p.x - s + 2 * s * a1, p.y - s + 2 * s * a1);
        if (a2 > 0) { g.moveTo(p.x + s, p.y - s); g.lineTo(p.x + s - 2 * s * a2, p.y - s + 2 * s * a2); }
        g.stroke();
        if (mark) tag(p.x + 6, p.y, `MEM – ${String(i + 1).padStart(2, "0")}`, `rgba(${CYAN},${Math.min(1, t * 3)})`, "#03161a", MEM_PX);
      });

      // Cells tangent to the orb, each holding a real number.
      const n = L.numbers, values = [cellNumber(n.params, "params"), cellNumber(n.chats, "count"), cellNumber(n.memories, "count"), cellNumber(n.docs, "count"), cellNumber(n.answerMs, "seconds"), cellNumber(n.firstAudioMs, "seconds")];
      if (roomy) cells(f, still ? 0 : spin.current).forEach((c, k) => {
        g.strokeStyle = `rgba(${WHITE},.34)`; g.lineWidth = 1; g.beginPath(); g.arc(c.x, c.y, c.r, 0, Math.PI * 2); g.stroke();
        if (L.thinking && !still) { const a = now / 600 + k; g.strokeStyle = `rgba(${CYAN},.75)`; g.lineWidth = 1.4; g.beginPath(); g.arc(c.x, c.y, c.r, a, a + .9); g.stroke(); }
        // Readable numbers: bright white value, solid cyan caption (they were blending into the black).
        g.textAlign = "center"; g.fillStyle = `rgba(${WHITE},.92)`; g.font = `300 ${Math.round(c.r * .46)}px ${FONT}`; g.fillText(values[k], c.x, c.y + c.r * .12);
        g.fillStyle = `rgb(${CYAN})`; g.font = `600 ${Math.max(9, Math.round(c.r * .14))}px ${FONT}`; g.fillText(CELL_CAPTIONS[k].toUpperCase(), c.x, c.y + c.r * .42); g.textAlign = "start";
      });

      // Interruption: a hairline ring expands from the rim.
      const shockT = still || !shockAt.current ? 0 : (now - shockAt.current) / SHOCK_MS;
      if (shockT > 0 && shockT < 1) { g.strokeStyle = `rgba(${CYAN},${.5 * (1 - shockT)})`; g.lineWidth = 1; g.beginPath(); g.arc(f.cx, f.cy, f.R * (1 + shockT * 1.6), 0, Math.PI * 2); g.stroke(); }

      // Signal: a cyan pulse races down a cited document's fan, then into the orb.
      signals.current = signals.current.filter(s => !s.done);
      for (const s of signals.current) {
        const t = (now - s.started) / SIGNAL_MS; if (t < 0) continue;
        if (t >= 1) { s.done = true; flashes.current.set(s.doc, now); L.onCometArrive(s.docId); continue; }
        const d = data.docs[s.doc], apex = apexes[s.doc];
        const strand = fan(apex, d.chats, f, d.id)[0], u = Math.min(1, t / .8);
        const p = u < 1 ? at(strand, u) : { x: strand.p3.x + (f.cx - strand.p3.x) * ((t - .8) / .2), y: strand.p3.y + (f.cy - strand.p3.y) * ((t - .8) / .2) };
        for (let k = 6; k >= 0; k--) { const q = at(strand, Math.max(0, u - k * .025)); g.fillStyle = `rgba(${CYAN},${.12 * (7 - k)})`; g.fillRect(q.x - 1.5, q.y - 1.5, 3, 3); }
        g.fillStyle = `rgb(${WHITE})`; g.beginPath(); g.arc(p.x, p.y, 2.6, 0, Math.PI * 2); g.fill();
      }
    };
    const busy = (now: number) => signals.current.length > 0 || marks.current.length > 0 || (shockAt.current > 0 && now - shockAt.current < SHOCK_MS) || (born.current > 0 && now - born.current < DRAW_MS) || live.current.listening || [...flashes.current.values()].some(t => now - t < 900);
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      if (!visible || document.hidden) return;
      const interval = busy(now) ? 16 : live.current.thinking ? 80 : 50;
      if (now - last < interval) return; last = now; draw(now);
    };
    measure();
    if (live.current.reduced) draw(performance.now()); else raf = requestAnimationFrame(loop);
    const resize = new ResizeObserver(() => { measure(); draw(performance.now()); }); resize.observe(element); if (orbBox.current) resize.observe(orbBox.current);
    const io = "IntersectionObserver" in window ? new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? true; }) : null; io?.observe(element);
    return () => { cancelAnimationFrame(raf); resize.disconnect(); io?.disconnect(); };
  }, [data, recency, level, reduced, orbBox, railBox, state, cited, activeChat, thinking]);

  // Hover and click arrive through the hero (the atlas has no pointer events of its own); the orb keeps its own.
  useEffect(() => {
    const area = hitArea.current, element = canvas.current; if (!area || !element) return;
    const pick = (event: PointerEvent | MouseEvent) => {
      const box = element.getBoundingClientRect(), x = event.clientX - box.left, y = event.clientY - box.top, f = frame.current;
      if (!f || Math.hypot(x - f.cx, y - f.cy) < f.R * 1.05) return null;
      const t = tags.current.find(t => x >= t.x && x <= t.x + t.w && y >= t.y && y <= t.y + t.h);
      if (t) return { label: t.label, x, y, w: box.width, chat: null as string | null };
      let best: { id: string; label: string } | null = null, bestD = 9;
      for (const p of glyphs.current) { const d = Math.hypot(p.x - x, p.y - y); if (d < bestD) { bestD = d; best = p; } }
      return best ? { label: best.label, x, y, w: box.width, chat: best.id } : null;
    };
    const move = (event: PointerEvent) => { const found = pick(event); setHover(found ? { label: found.label, x: found.x, y: found.y, w: found.w } : null); area.style.cursor = found?.chat ? "pointer" : ""; };
    const leave = () => { setHover(null); area.style.cursor = ""; };
    const click = (event: MouseEvent) => { const found = pick(event); if (found?.chat) { event.stopPropagation(); onOpenChat(found.chat); } };
    area.addEventListener("pointermove", move); area.addEventListener("pointerleave", leave); area.addEventListener("click", click, true);
    return () => { area.removeEventListener("pointermove", move); area.removeEventListener("pointerleave", leave); area.removeEventListener("click", click, true); };
  }, [hitArea, onOpenChat]);

  return <div className="june-atlas" aria-hidden="true">
    <canvas ref={canvas} />
    {hover && <span className="sp-tip" style={hover.x > hover.w / 2 ? { right: hover.w - hover.x + 12, top: hover.y - 10 } : { left: hover.x + 12, top: hover.y - 10 }}>{hover.label}</span>}
  </div>;
}

export type { Point };
