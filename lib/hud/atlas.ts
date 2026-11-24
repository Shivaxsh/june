/* The Specimen atlas: June's real knowledge drawn as a neural-network plate around the (unchanged) orb.
 * Pure geometry and timing; deterministic and testable. Document tags sit in the left field with converging fans of
 * hairline strands into the orb rim (one strand per chat that cited the document), chats are square glyphs, memories
 * are crosshairs, and six cells tangent to the orb hold real numbers. */
import { hash } from "./sky";

export type Point = { x: number; y: number };
/** The canvas size and the orb's real centre and sphere radius inside it (the orb box may be off-centre). */
export type Frame = { W: number; H: number; cx: number; cy: number; R: number };

/** Same sphere radius as lib/orb/hud-renderer.ts, for an orb box of width w and height h at (left, top). */
export function frameFrom(W: number, H: number, box: { left: number; top: number; width: number; height: number }): Frame {
  const R = Math.max(10, Math.min((box.height / 2 - 12) / 1.62, (box.width / 2 - 12) / 1.62));
  return { W, H, cx: box.left + box.width / 2, cy: box.top + box.height / 2, R };
}

const rad = (deg: number) => deg * Math.PI / 180;
/** The orb's network visibly reaches about 1.6 sphere radii; nothing in the atlas is drawn inside that. */
export const REACH = 1.6;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Where document i of n puts its tag (the fan's apex): an arc on the orb's left, kept clear of the left rail. */
export function docApex(i: number, n: number, f: Frame, railRight = 0): Point {
  const t = n <= 1 ? .5 : i / (n - 1);
  const angle = rad(150 + t * 88);                          // 150° (lower left) … 238° (upper left); y grows down
  const r = f.R * (REACH + .55 + (i % 2) * .4);
  const x = clamp(f.cx + Math.cos(angle) * r, railRight + 24, f.W - 24), y = clamp(f.cy + Math.sin(angle) * r, 28, f.H - 28);
  return { x, y };
}

/** Keep tag apexes at least `gap` apart vertically (sorted by height), always inside [top, bottom]: when there is not
 * room for the full gap, the gap shrinks evenly. The input order is preserved. */
export function spread(points: Point[], gap: number, top: number, bottom: number): Point[] {
  const n = points.length, step = n > 1 ? Math.min(gap, (bottom - top) / (n - 1)) : gap;
  const order = points.map((p, i) => ({ p: { ...p }, i })).sort((a, b) => a.p.y - b.p.y);
  order.forEach((o, k) => { o.p.y = Math.max(clamp(o.p.y, top, bottom), k ? order[k - 1].p.y + step : top); });
  order.forEach((o, k) => { o.p.y = Math.min(o.p.y, bottom - (n - 1 - k) * step); });
  const out: Point[] = []; for (const o of order) out[o.i] = o.p; return out;
}

/** A point on the orb rim at `angle`. */
export function rim(f: Frame, angle: number, inset = .98): Point {
  return { x: f.cx + Math.cos(angle) * f.R * inset, y: f.cy + Math.sin(angle) * f.R * inset };
}

export type Strand = { p0: Point; p1: Point; p2: Point; p3: Point; seed: number };

/** A converging fan: one hairline per citing chat (at least one), from the tag apex into the facing side of the rim. */
export function fan(apex: Point, chats: string[], f: Frame, docId: string): Strand[] {
  const ids = chats.length ? chats : [docId];
  const facing = Math.atan2(apex.y - f.cy, apex.x - f.cx);
  return ids.map((id, k) => {
    const s = hash(docId + ":" + id), spread = (s - .5) * 1.5 + (ids.length > 1 ? (k / (ids.length - 1) - .5) * .9 : 0);
    const end = rim(f, facing + spread);
    const dx = end.x - apex.x, dy = end.y - apex.y, d = Math.hypot(dx, dy) || 1, nx = -dy / d, ny = dx / d;
    const bend = (hash(id + docId) - .5) * d * .45;
    const out = { x: (end.x - f.cx) / f.R, y: (end.y - f.cy) / f.R };   // leaves the rim outward, like the reference
    return {
      p0: apex,
      p1: { x: apex.x + dx * .3 + nx * bend, y: apex.y + dy * .3 + ny * bend },
      p2: { x: end.x + out.x * f.R * .55 + nx * bend * .4, y: end.y + out.y * f.R * .55 + ny * bend * .4 },
      p3: end, seed: s,
    };
  });
}

/** Point at t on a strand (cubic bézier). */
export function at(s: Strand, t: number): Point {
  const u = 1 - t, a = u * u * u, b = 3 * u * u * t, c = 3 * u * t * t, d = t * t * t;
  return { x: a * s.p0.x + b * s.p1.x + c * s.p2.x + d * s.p3.x, y: a * s.p0.y + b * s.p1.y + c * s.p2.y + d * s.p3.y };
}

/** Listening gravity: a strand's middle leans toward the orb with the voice level (ends stay fixed), capped. */
export function lean(p: Point, t: number, level: number, f: Frame, cap = 16): Point {
  if (!(level > 0)) return p;
  const dx = f.cx - p.x, dy = f.cy - p.y, d = Math.hypot(dx, dy) || 1, w = Math.sin(Math.PI * t);
  const pull = Math.min(cap, cap * Math.min(1, level)) * w;
  return { x: p.x + dx / d * pull, y: p.y + dy / d * pull };
}

/** Six cells tangent to the orb's visible reach (right side and lower left, away from the document fans). */
export const CELL_ANGLES = [-54, -27, 0, 27, 54, 125];
export function cells(f: Frame, spin = 0) {
  return CELL_ANGLES.map((deg, k) => {
    const r = f.R * (k % 2 ? .26 : .32), a = rad(deg) + spin, d = f.R * REACH + r + 4;
    const x = clamp(f.cx + Math.cos(a) * d, r + 4, f.W - r - 4), y = clamp(f.cy + Math.sin(a) * d, r + 4, f.H - r - 4);
    return { x, y, r };
  });
}

/** Chats as square glyphs scattered across the field left of the orb (between the rail and the orb's reach). */
export function chatGlyph(i: number, id: string, f: Frame, railRight = 0): Point {
  const left = railRight + 28, right = Math.max(left + 40, f.cx - f.R * REACH - 12);
  const x = left + (right - left) * hash("cx:" + id), y = 18 + (f.H - 36) * hash("cy:" + id + i);
  return { x, y };
}

/** Memories as crosshairs on the upper-left field, between the fans and the cells. */
export function memoryMark(i: number, n: number, f: Frame): Point {
  const t = n <= 1 ? .5 : i / (n - 1), angle = rad(232 + t * 50), r = f.R * (REACH + .25 + (i % 3) * .2);
  return { x: clamp(f.cx + Math.cos(angle) * r, 10, f.W - 10), y: clamp(f.cy + Math.sin(angle) * r, 10, f.H - 10) };
}

/** Launch: strands draw themselves in order over `duration`; returns how much of strand k (0..1) is drawn. */
export function drawn(k: number, total: number, elapsed: number, duration = 1600) {
  if (total <= 0) return 1;
  const start = (k / total) * duration * .6;
  return clamp((elapsed - start) / (duration * .4), 0, 1);
}

/** Live voice-activity bits for the rail's binary box: newest last, 1 when the level is above the speech threshold. */
export function pushBit(bits: string, level: number, size = 36, threshold = .12) {
  return (bits + (level > threshold ? "1" : "0")).slice(-size).padStart(size, "0");
}
export function bitRows(bits: string, width = 6) {
  const rows: string[] = [];
  for (let i = 0; i < bits.length; i += width) rows.push(bits.slice(i, i + width));
  return rows;
}

/** A compact number for a cell: 4022468096 → "4.0224", 97 → "97", seconds → "0.42". */
export function cellNumber(value: number | null | undefined, kind: "params" | "count" | "seconds") {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  if (kind === "params") return (value / 1e9).toFixed(4);
  if (kind === "seconds") return (value / 1000).toFixed(2);
  return String(Math.round(value));
}
