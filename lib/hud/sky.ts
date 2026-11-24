/* The Observatory sky: June's knowledge constellation drawn as a night sky around the orb.
 * Pure geometry and timing only (no DOM), so it is deterministic and testable. Real data only:
 * the force layout from ./constellation decides each star's direction and relative distance. */
import type { GraphEdge, GraphNode } from "./constellation";

export type Point = { x: number; y: number };
export type Star = { i: number; id: string; type: GraphNode["type"]; label: string; angle: number; dist: number; mag: number; cites: number; seed: number };

/** Same geometry as the orb renderer (lib/orb/hud-renderer.ts): centre of the layer and its sphere radius. */
export function orbGeometry(W: number, H: number) {
  const R = Math.max(10, Math.min((H / 2 - 12) / 1.62, (W / 2 - 12) / 1.62));
  return { cx: W / 2, cy: H / 2, R };
}

/** Stars never sit on the orb: the clear zone covers the sphere and its brightest dust. */
export const CLEAR_ZONE = 1.42;
/** At most this many document names are always shown; the rest appear on hover. */
export const LABEL_BUDGET = 5;

/** Map the force layout onto polar sky coordinates: direction kept, distance normalised to 0..1. */
export function skyStars(nodes: GraphNode[], edges: GraphEdge[], recency: Map<string, number> = new Map()): Star[] {
  if (!nodes.length) return [];
  const mx = nodes.reduce((s, n) => s + n.x, 0) / nodes.length, my = nodes.reduce((s, n) => s + n.y, 0) / nodes.length;
  const dists = nodes.map(n => Math.hypot(n.x - mx, n.y - my));
  const far = Math.max(1e-6, ...dists);
  const cites = new Map<number, number>();
  for (const e of edges) if (e.type === "cite") for (const k of [e.a, e.b]) if (nodes[k].type === "doc") cites.set(k, (cites.get(k) ?? 0) + 1);
  return nodes.map((n, i) => {
    const seed = hash(n.type + n.id);
    // Documents are the bright named stars; memories medium; chats faint dust that brightens with recency.
    const mag = n.type === "doc" ? 1 : n.type === "mem" ? .62 : .22 + .38 * (recency.get(n.id) ?? 0);
    const angle = Math.atan2(n.y - my, n.x - mx) + (dists[i] < 1e-6 ? seed * 6.2832 : 0);
    return { i, id: n.id, type: n.type, label: n.label, angle, dist: dists[i] / far, mag, cites: cites.get(i) ?? 0, seed };
  });
}

/** Screen position of a star: an ellipse filling the layer, outside the orb's clear zone, rotated by `spin`. */
export function placeStar(star: Pick<Star, "angle" | "dist" | "seed">, W: number, H: number, spin = 0): Point {
  const { cx, cy, R } = orbGeometry(W, H);
  const inner = R * CLEAR_ZONE, ax = Math.max(inner + 8, W / 2 - 16), ay = Math.max(inner + 8, H / 2 - 12);
  // Spread by the layout distance with a little per-star jitter so rings never look mechanical.
  const t = Math.min(1, Math.max(0, .08 + .84 * Math.sqrt(star.dist) + (star.seed - .5) * .12));
  const a = star.angle + spin, rx = inner + (ax - inner) * t, ry = inner + (ay - inner) * t;
  return { x: cx + Math.cos(a) * rx, y: cy + Math.sin(a) * ry };
}

/** The whole sky turns once per local day: different by evening, imperceptible moment to moment. */
export function siderealAngle(date: Date) {
  return ((date.getHours() * 3600 + date.getMinutes() * 60 + date.getSeconds()) / 86400) * Math.PI * 2;
}

/** Which documents keep a permanent name: the most cited, at most LABEL_BUDGET. */
export function labelled(stars: Star[]) {
  return new Set(stars.filter(s => s.type === "doc").sort((a, b) => b.cites - a.cites || a.i - b.i).slice(0, LABEL_BUDGET).map(s => s.i));
}

/** Listening gravity: stars lean toward the orb with the voice level, falling off with distance, capped. */
export function gravity(p: Point, level: number, W: number, H: number, cap = 14): Point {
  if (!(level > 0)) return p;
  const { cx, cy, R } = orbGeometry(W, H), dx = cx - p.x, dy = cy - p.y, d = Math.max(R, Math.hypot(dx, dy));
  const pull = Math.min(cap, cap * Math.min(1, level) * (R * CLEAR_ZONE / d) ** 2);
  return { x: p.x + dx / d * pull, y: p.y + dy / d * pull };
}

/** Interruption shockwave: a ring expanding from the orb; stars near the ring jolt outward. t in 0..1. */
export function shock(p: Point, t: number, W: number, H: number): Point {
  if (!(t > 0 && t < 1)) return p;
  const { cx, cy, R } = orbGeometry(W, H), dx = p.x - cx, dy = p.y - cy, d = Math.hypot(dx, dy) || 1;
  const ring = R * (1 + t * 3.2), w = Math.max(0, 1 - Math.abs(d - ring) / (R * .35)) * (1 - t);
  return { x: p.x + dx / d * 10 * w, y: p.y + dy / d * 10 * w };
}

/** Citation comet: a curved path from a document star into the orb centre. t in 0..1, eased. */
export function comet(from: Point, W: number, H: number, t: number): Point {
  const { cx, cy } = orbGeometry(W, H), e = t < .5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
  const mx = (from.x + cx) / 2, my = (from.y + cy) / 2, nx = -(cy - from.y), ny = cx - from.x, l = Math.hypot(nx, ny) || 1;
  const bend = .22 * Math.hypot(cx - from.x, cy - from.y), qx = mx + nx / l * bend, qy = my + ny / l * bend;
  const u = 1 - e;
  return { x: u * u * from.x + 2 * u * e * qx + e * e * cx, y: u * u * from.y + 2 * u * e * qy + e * e * cy };
}

/** Launch ignition: stars light in creation order (documents, memories, then chats by last update). */
export function ignitionOrder(stars: Star[], updated: Map<string, number>) {
  const rank = { doc: 0, mem: 1, chat: 2 } as const;
  return [...stars].sort((a, b) => rank[a.type] - rank[b.type] || (a.type === "chat" ? (updated.get(a.id) ?? 0) - (updated.get(b.id) ?? 0) : a.i - b.i)).map(s => s.i);
}

/** 0..1 brightness of a star during ignition. */
export function ignition(position: number, total: number, elapsed: number, duration = 1500) {
  if (total <= 0) return 1;
  const start = (position / total) * duration * .8;
  return Math.min(1, Math.max(0, (elapsed - start) / 220));
}

/** Recency 0..1 for chats: newest is 1, oldest 0 (by last update time). */
export function recencyOf(conversations: { id: string; updated?: number }[]) {
  const times = conversations.map(c => c.updated ?? 0), lo = Math.min(...times), hi = Math.max(...times);
  return new Map(conversations.map(c => [c.id, hi > lo ? ((c.updated ?? 0) - lo) / (hi - lo) : 1]));
}

/** A stable 0..1 number per id (twinkle phase, jitter). */
export function hash(value: string) {
  let h = 2166136261;
  for (let i = 0; i < value.length; i++) h = Math.imul(h ^ value.charCodeAt(i), 16777619);
  return ((h >>> 0) % 100000) / 100000;
}
