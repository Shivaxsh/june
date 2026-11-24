"use client";
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import type { Level } from "@/lib/orb/audio-controller";
import type { buildConstellation } from "@/lib/hud/constellation";
import { GRAPH_RGB, LABEL_RGB, LINE_RGB, rgba } from "@/lib/hud/palette";
import { CLEAR_ZONE, comet, gravity, ignition, ignitionOrder, labelled, orbGeometry, placeStar, recencyOf, shock, siderealAngle, skyStars, type Point } from "@/lib/hud/sky";
import { useReducedMotion } from "@/lib/hud/useReducedMotion";
import type { ConstellationState } from "./Constellation";

type Graph = ReturnType<typeof buildConstellation>;
type Comet = { star: number; doc: string; started: number; arrived: boolean };
type Bloom = { star: number; started: number };
const COMET_MS = 950, SHOCK_MS = 650, BLOOM_MS = 1300, IGNITE_MS = 1500;

/** Where a permanent star name goes: right of the star, flipped left at the edge, never under the side
 * instruments of the wide layout (it still shows on hover). null = leave it unlabelled. */
export function labelX(x: number, width: number, W: number) {
  const right = x + 9, left = x - 9 - width;
  let at = right + width <= W - 6 ? right : left >= 6 ? left : null;
  if (at !== null && W > 1100 && (at < 250 || at + width > W - 270)) at = null;
  return at;
}

/** The Observatory sky: June's documents, memories and chats as a night sky around the orb (which it never covers). */
export default function Sky({ graph, conversations, memoryIds, state, cited, citedKey, activeChat, level, listening, thinking, shockSeq, hitArea, onOpenChat, onCometArrive }: {
  graph: Graph; conversations: { id: string; updated?: number }[]; memoryIds: string[];
  state: ConstellationState; cited: string[]; citedKey: string; activeChat: string | null;
  level: Level; listening: boolean; thinking: boolean; shockSeq: number; hitArea: RefObject<HTMLElement | null>;
  onOpenChat: (id: string) => void; onCometArrive: (documentId: string) => void;
}) {
  const reduced = useReducedMotion();
  const canvas = useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = useState<{ label: string; x: number; y: number; w: number } | null>(null);
  const hovered = useRef<number>(-1);
  const updated = useMemo(() => new Map(conversations.map(c => [c.id, c.updated ?? 0])), [conversations]);
  const stars = useMemo(() => skyStars(graph.nodes, graph.edges, recencyOf(conversations)), [graph, conversations]);
  const named = useMemo(() => labelled(stars), [stars]);
  // Event animations live in refs so the draw loop reads them without re-subscribing.
  const comets = useRef<Comet[]>([]), blooms = useRef<Bloom[]>([]), shockAt = useRef(0), born = useRef(0);
  const order = useMemo(() => { const o = ignitionOrder(stars, updated), at = new Map<number, number>(); o.forEach((s, k) => at.set(s, k)); return at; }, [stars, updated]);
  const placed = useRef<Point[]>([]);
  const live = useRef({ state, cited, activeChat, listening, thinking, reduced, onCometArrive });
  live.current = { state, cited, activeChat, listening, thinking, reduced, onCometArrive };

  // Launch ignition: once per page load, when the sky first has stars.
  useEffect(() => { if (stars.length && !born.current) born.current = performance.now(); }, [stars.length]);

  // Citation comet: each newly cited document sends a comet into the orb.
  const lastKey = useRef("");
  useEffect(() => {
    if (!citedKey || citedKey === lastKey.current) return;
    lastKey.current = citedKey;
    const now = performance.now();
    for (const doc of cited) {
      const star = stars.find(s => s.type === "doc" && s.id === doc);
      if (!star) { onCometArrive(doc); continue; }
      if (reduced) onCometArrive(doc);
      else comets.current.push({ star: star.i, doc, started: now + comets.current.length * 160, arrived: false });
    }
  }, [citedKey, cited, stars, reduced, onCometArrive]);

  // Memory ignition: a memory that did not exist on the previous render forms out of drifting dust.
  const knownMemories = useRef<Set<string> | null>(null);
  useEffect(() => {
    const previous = knownMemories.current; knownMemories.current = new Set(memoryIds);
    if (!previous || reduced) return;
    for (const id of memoryIds) if (!previous.has(id)) {
      const star = stars.find(s => s.type === "mem" && s.id === id);
      if (star) blooms.current.push({ star: star.i, started: performance.now() });
    }
  }, [memoryIds, stars, reduced]);

  // Interruption shockwave.
  const lastShock = useRef(shockSeq);
  useEffect(() => { if (shockSeq !== lastShock.current) { lastShock.current = shockSeq; if (!reduced) shockAt.current = performance.now(); } }, [shockSeq, reduced]);

  useEffect(() => {
    const element = canvas.current; if (!element) return;
    const context = element.getContext("2d"); if (!context) return;
    let frame = 0, last = 0, visible = true, spin = siderealAngle(new Date()), spinAt = 0;
    const draw = (now: number) => {
      const W = element.clientWidth, H = element.clientHeight; if (!W || !H) return;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      if (element.width !== Math.round(W * dpr) || element.height !== Math.round(H * dpr)) { element.width = Math.round(W * dpr); element.height = Math.round(H * dpr); }
      context.setTransform(dpr, 0, 0, dpr, 0, 0); context.clearRect(0, 0, W, H);
      const { cx, cy, R } = orbGeometry(W, H), L = live.current, still = L.reduced;
      if (!still && now - spinAt > 10000) { spin = siderealAngle(new Date()); spinAt = now; }
      const lvl = L.listening && !still ? Math.min(1, Math.max(0, level.current)) : 0;
      const shockT = still || !shockAt.current ? 0 : (now - shockAt.current) / SHOCK_MS;
      const pts = stars.map(s => { let p = placeStar(s, W, H, still ? 0 : spin); if (lvl) p = gravity(p, lvl, W, H); if (shockT > 0 && shockT < 1) p = shock(p, shockT, W, H); return p; });
      placed.current = pts;
      const age = born.current ? now - born.current : IGNITE_MS;
      const glow = (i: number) => still ? 1 : ignition(order.get(i) ?? 0, stars.length, age, IGNITE_MS);

      // Star-chart lines: citations faint, the hovered star's links bright.
      for (const e of graph.edges) {
        const A = pts[e.a], B = pts[e.b]; if (!A || !B) continue;
        const hot = hovered.current === e.a || hovered.current === e.b;
        const cite = e.type === "cite" && L.state === "cited" && ((L.cited.includes(stars[e.a].id) && stars[e.b].id === L.activeChat) || (L.cited.includes(stars[e.b].id) && stars[e.a].id === L.activeChat));
        const a = (hot ? .42 : cite ? .3 : e.type === "cite" ? .07 : .035) * Math.min(glow(e.a), glow(e.b));
        if (a < .01) continue;
        context.strokeStyle = rgba(e.type === "cite" ? GRAPH_RGB.cite : LINE_RGB, a); context.lineWidth = hot || cite ? 1 : .6;
        context.beginPath(); context.moveTo(A.x, A.y); context.lineTo(B.x, B.y); context.stroke();
      }

      context.font = '10px "JetBrains Mono", ui-monospace, monospace';
      stars.forEach((s, k) => {
        const p = pts[k], c = GRAPH_RGB[s.type], g = glow(k); if (g <= 0) return;
        const twinkle = still ? 1 : .78 + .22 * Math.sin(now / 1000 * (1.1 + s.seed) + s.seed * 40);
        const searching = s.type === "doc" && L.state === "searching" && !still ? .7 + .3 * Math.sin(now / 160 + s.seed * 9) : 1;
        const isCited = s.type === "doc" && L.state === "cited" && L.cited.includes(s.id);
        const a = Math.min(1, s.mag * twinkle * searching * g * (isCited ? 1.25 : 1) * (hovered.current === k ? 1.4 : 1));
        const r = s.type === "doc" ? 2.4 : s.type === "mem" ? 1.7 : 1 + s.mag;
        context.fillStyle = rgba(c, a * .16); context.beginPath(); context.arc(p.x, p.y, r * (s.type === "chat" ? 2.2 : 3.6), 0, 6.2832); context.fill();
        context.fillStyle = rgba(c, a); context.beginPath(); context.arc(p.x, p.y, r, 0, 6.2832); context.fill();
        if (s.type === "doc") {
          // A four-point diffraction glint marks the named stars.
          const len = 7 + 5 * a; context.strokeStyle = rgba(c, a * .5); context.lineWidth = .7; context.beginPath();
          context.moveTo(p.x - len, p.y); context.lineTo(p.x + len, p.y); context.moveTo(p.x, p.y - len); context.lineTo(p.x, p.y + len); context.stroke();
          if (named.has(k) && hovered.current !== k && W >= 600) {
            const tw = context.measureText(s.label).width, lx = labelX(p.x, tw, W);
            if (lx !== null) { context.fillStyle = rgba(LABEL_RGB, .5 * g); context.fillText(s.label, lx, Math.max(12, p.y - 7)); }
          }
        }
      });

      // Memory ignition: dust converging into a new star, then a brief bloom.
      blooms.current = blooms.current.filter(b => now - b.started < BLOOM_MS);
      for (const b of blooms.current) {
        const p = pts[b.star]; if (!p) continue; const t = (now - b.started) / BLOOM_MS, c = GRAPH_RGB.mem;
        for (let d = 0; d < 10; d++) { const ang = d / 10 * 6.2832 + t * 2, rr = 46 * (1 - Math.min(1, t * 1.4)); context.fillStyle = rgba(c, .7 * (1 - t)); context.fillRect(p.x + Math.cos(ang) * rr, p.y + Math.sin(ang) * rr, 1.4, 1.4); }
        if (t > .55) { const k = (t - .55) / .45; context.fillStyle = rgba(c, .35 * (1 - k)); context.beginPath(); context.arc(p.x, p.y, 4 + 18 * k, 0, 6.2832); context.fill(); }
      }

      // Interruption shockwave ring.
      if (shockT > 0 && shockT < 1) { context.strokeStyle = rgba(LINE_RGB, .28 * (1 - shockT)); context.lineWidth = 1.2; context.beginPath(); context.arc(cx, cy, R * (1 + shockT * 3.2), 0, 6.2832); context.stroke(); }

      // Citation comets: head and fading tail, arriving at the orb centre.
      comets.current = comets.current.filter(m => !m.arrived);
      for (const m of comets.current) {
        const from = pts[m.star]; if (!from) continue;
        const t = (now - m.started) / COMET_MS; if (t < 0) continue;
        if (t >= 1) { m.arrived = true; L.onCometArrive(m.doc); continue; }
        const c = GRAPH_RGB.cite;
        for (let k = 14; k >= 0; k--) { const q = comet(from, W, H, Math.max(0, t - k * .018)); context.fillStyle = rgba(c, (1 - k / 15) * .55); context.beginPath(); context.arc(q.x, q.y, 2.4 * (1 - k / 18), 0, 6.2832); context.fill(); }
        const head = comet(from, W, H, t); context.fillStyle = rgba([255, 245, 220], .95); context.beginPath(); context.arc(head.x, head.y, 2.2, 0, 6.2832); context.fill();
      }
    };
    const busy = (now: number) => comets.current.length > 0 || blooms.current.length > 0 || (shockAt.current > 0 && now - shockAt.current < SHOCK_MS) || (born.current > 0 && now - born.current < IGNITE_MS) || live.current.listening;
    const loop = (now: number) => {
      frame = requestAnimationFrame(loop);
      if (!visible || document.hidden) return;
      const L = live.current, interval = busy(now) ? 16 : L.thinking ? 80 : 50;  // twinkle at 20 fps; leave CPU to the model while it thinks
      if (now - last < interval) return; last = now; draw(now);
    };
    if (live.current.reduced) draw(performance.now()); else frame = requestAnimationFrame(loop);
    const resize = new ResizeObserver(() => draw(performance.now())); resize.observe(element);
    const io = "IntersectionObserver" in window ? new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? true; }) : null; io?.observe(element);
    return () => { cancelAnimationFrame(frame); resize.disconnect(); io?.disconnect(); };
  }, [graph, stars, named, order, level, reduced, state, cited, activeChat]);

  // Hover and click come from the orb layer (the sky sits above it with no pointer events of its own).
  useEffect(() => {
    const area = hitArea.current, element = canvas.current; if (!area || !element) return;
    const pick = (event: PointerEvent | MouseEvent) => {
      const box = element.getBoundingClientRect(), x = event.clientX - box.left, y = event.clientY - box.top;
      const { cx, cy, R } = orbGeometry(box.width, box.height);
      if (Math.hypot(x - cx, y - cy) < R * CLEAR_ZONE) return null;  // the orb keeps its own interactions
      let best = -1, bestD = 12;
      placed.current.forEach((p, k) => { const d = Math.hypot(p.x - x, p.y - y); if (d < bestD) { best = k; bestD = d; } });
      return best < 0 ? null : { star: stars[best], k: best, x, y, w: box.width };
    };
    const move = (event: PointerEvent) => {
      const found = pick(event); hovered.current = found ? found.k : -1;
      if (!found) { setHover(null); return; }
      const s = found.star;
      const label = s.type === "doc" ? `${s.label}${s.cites ? ` · cited ${s.cites}×` : ""}` : s.type === "chat" ? `Chat · ${s.label}` : "Approved memory";
      setHover({ label, x: found.x, y: found.y, w: found.w });
      (event.target as HTMLElement).style.cursor = s.type === "chat" ? "pointer" : "";
    };
    const leave = () => { hovered.current = -1; setHover(null); };
    const click = (event: MouseEvent) => { const found = pick(event); if (found?.star.type === "chat") { event.stopPropagation(); onOpenChat(found.star.id); } };
    area.addEventListener("pointermove", move); area.addEventListener("pointerleave", leave); area.addEventListener("click", click, true);
    return () => { area.removeEventListener("pointermove", move); area.removeEventListener("pointerleave", leave); area.removeEventListener("click", click, true); };
  }, [hitArea, stars, onOpenChat]);

  return <div className="hud-sky" aria-hidden="true">
    <canvas ref={canvas} />
    {hover && <span className="hud-graph-tip" style={hover.x > hover.w / 2 ? { right: hover.w - hover.x + 12, top: hover.y - 10 } : { left: hover.x + 12, top: hover.y - 10 }}>{hover.label}</span>}
  </div>;
}
