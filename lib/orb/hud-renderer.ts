import type { Mood } from "./state";
import { createNetwork, type RendererHost } from "./renderer";

/*
 * Orb v2: June's existing network (the exact createNetwork geometry) plus
 * seeded detail layers: dendrite branches, neural dust, light highways,
 * comet orbits, a core reactor, cascading signals, lightning, a waveform halo
 * and shockwaves. Every animated quantity is driven by real state (mood and
 * measured level); nothing here invents audio. No text is drawn on the orb.
 */

export interface HudOrbInput { mood: Mood; level: number; focus: number; reduced: boolean }
export type OrbHit = { kind: "cluster"; cluster: number } | { kind: "core" } | { kind: "space" };
type V3 = [number, number, number];
type P4 = [number, number, number, number];
interface Segment { a: V3; c: V3; b: V3; d: number; cl: number; ph: number; tip: boolean }
interface Dust { r: number; a: number; y: number; ph: number; sz: number; sp: number; u: number }
interface Highway { a: number; b: number; ca: number; cb: number; c: V3 }
interface Signal { e: number; p: number; v: number; rev: boolean; hops: number; tr: [number, number][] }
interface Shock { core: boolean; x: number; y: number; t: number }
interface Bolt { to: number; t: number; seed: number }
interface Style { spin: number; breathe: number; fire: number; glow: number; ring: number }

export const CORE_COLOR = [52, 209, 184];
const STYLE: Record<Mood, Style> = {
  idle: { spin: .1, breathe: .015, fire: 2, glow: .45, ring: 0 },
  listening: { spin: .16, breathe: .03, fire: 6, glow: .55, ring: 1 },
  thinking: { spin: .45, breathe: .02, fire: 18, glow: .6, ring: 0 },
  speaking: { spin: .18, breathe: .02, fire: 10, glow: .6, ring: 0 },
};
/** The cluster each mood exercises: Ears, Knowledge, Voice. */
export const ACTIVE_CLUSTER: Record<Mood, number> = { idle: -1, listening: 5, thinking: 3, speaking: 1 };

function seeded(start: number) {
  let seed = start;
  return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
}
const norm = (v: number[]): V3 => { const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; };
const cross = (a: number[], b: number[]): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];

export const NETWORK = createNetwork();

/** Deterministic detail layers built once from the unchanged network. */
export function createDetail(network = NETWORK) {
  const rnd = seeded(31), N = network.nodes;
  const segs: Segment[] = [];
  const grow = (p: V3, dir: V3, len: number, d: number, maxD: number, cl: number) => {
    let b: V3 = [p[0] + dir[0] * len, p[1] + dir[1] * len, p[2] + dir[2] * len];
    const bl = Math.hypot(b[0], b[1], b[2]); if (bl > 1.24) b = [b[0] * 1.24 / bl, b[1] * 1.24 / bl, b[2] * 1.24 / bl];
    const perp = norm(cross(dir, [rnd() - .5, rnd() - .5, rnd() - .5]));
    const bend = (rnd() - .5) * len * .55;
    const c: V3 = [(p[0] + b[0]) / 2 + perp[0] * bend, (p[1] + b[1]) / 2 + perp[1] * bend, (p[2] + b[2]) / 2 + perp[2] * bend];
    segs.push({ a: p, c, b, d, cl, ph: rnd() * 6.28, tip: d === maxD });
    if (d < maxD) {
      const k = rnd() < .28 ? 3 : 2;
      for (let j = 0; j < k; j++) {
        const side = norm(cross(dir, [rnd() - .5, rnd() - .5, rnd() - .5])); const ang = Math.tan(.44 + rnd() * .27);
        grow(b, norm([dir[0] + side[0] * ang, dir[1] + side[1] * ang, dir[2] + side[2] * ang]), len * (.62 + rnd() * .16), d + 1, maxD, cl);
      }
    }
  };
  network.hubs.forEach(h => { const n = N[h]; grow(n.p as V3, norm([n.p[0] + (rnd() - .5) * .3, n.p[1] + (rnd() - .5) * .3, n.p[2] + (rnd() - .5) * .3]), .2, 0, 3, n.c); });
  network.clusters.forEach((_, ci) => {
    N.map((n, i) => [n, i] as const).filter(([n]) => n.c === ci && !n.hub).sort((a, b) => b[0].size - a[0].size).slice(0, 3)
      .forEach(([n]) => grow(n.p as V3, norm(n.p), .14, 1, 3, ci));
  });
  const dust: Dust[] = [];
  for (let i = 0; i < 460; i++) { const r = 1.15 + Math.pow(rnd(), .7) * 1.75; dust.push({ r, a: rnd() * 6.2832, y: (rnd() - .5) * .22 * r, ph: rnd() * 6.28, sz: rnd() < .1 ? 1.9 : rnd() < .5 ? 1.2 : .8, sp: .4 + rnd() * .8, u: rnd() }); }
  const hub = (c: number) => network.hubs[c * 4];
  const highways: Highway[] = [[5, 3], [3, 0], [3, 1], [2, 1], [0, 2], [4, 5]].map(([a, b]) => {
    const pa = N[hub(a)].p, pb = N[hub(b)].p;
    let m: number[] = [(pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, (pa[2] + pb[2]) / 2];
    if (Math.hypot(m[0], m[1], m[2]) < .2) m = cross(pa, pb);
    const mn = norm(m);
    return { a: hub(a), b: hub(b), ca: a, cb: b, c: [mn[0] * 1.18, mn[1] * 1.18, mn[2] * 1.18] };
  });
  const phi = (1 + Math.sqrt(5)) / 2, ip = 1 / phi, dv: number[][] = [];
  for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) dv.push([x, y, z]);
  for (const a of [-1, 1]) for (const b of [-1, 1]) { dv.push([0, a * ip, b * phi]); dv.push([a * ip, b * phi, 0]); dv.push([a * phi, 0, b * ip]); }
  const dodV = dv.map(norm), dodE: [number, number][] = [];
  const dist = (i: number, j: number) => Math.hypot(dodV[i][0] - dodV[j][0], dodV[i][1] - dodV[j][1], dodV[i][2] - dodV[j][2]);
  let shortest = 9; for (let i = 0; i < 20; i++) for (let j = i + 1; j < 20; j++) shortest = Math.min(shortest, dist(i, j));
  for (let i = 0; i < 20; i++) for (let j = i + 1; j < 20; j++) if (dist(i, j) < shortest * 1.01) dodE.push([i, j]);
  const adjacency: number[][] = N.map(() => []);
  network.edges.forEach((e, k) => { adjacency[e[0]].push(k); adjacency[e[1]].push(k); });
  return { segs, dust, highways, dodV, dodE, adjacency };
}
const DETAIL = createDetail();

export interface OrbStats { strokes: number; tier: number; texts: number }

export function createHudOrbRenderer(canvas: HTMLCanvasElement, read: () => HudOrbInput, host: RendererHost, random: () => number = Math.random) {
  const context = canvas.getContext("2d");
  if (!context) return null;
  const g = context;
  const net = NETWORK, det = DETAIL, N = net.nodes, CL = net.clusters;
  const cur: Style = { ...STYLE.idle };
  let W = 0, H = 0, cx = 0, cy = 0, R = 0, frame = 0, timer = 0, last: number | null = null;
  let disposed = false, visible = true, dirty = true;
  let t = 0, boot = 0, yaw = .35, pitch = 0, vy = 0, vp = 0, energy = 0, prevEnergy = 0, lastShock = 0;
  let active = -1, spawnAcc = 0, cursorAcc = 0, boltClock = 0, nextRipple = 5, ema = 8, govClock = 0, tier = 0, firstPaint = true;
  let ripple: { c: number; t0: number } | null = null;
  let mouse: { x: number; y: number } | null = null, dragging = false;
  const grow = [0, 0, 0, 0, 0, 0];
  const bloom = new Float32Array(N.length);
  const signals: Signal[] = [], shocks: Shock[] = [], bolts: Bolt[] = [];
  const P: P4[] = N.map(() => [0, 0, 0, 0]);
  const order = N.map((_, i) => i);
  const buckets: number[][] = Array.from({ length: 24 }, () => []);
  const stats: OrbStats = { strokes: 0, tier: 0, texts: 0 };
  const rgba = (c: number[], a: number) => `rgba(${c[0]},${c[1]},${c[2]},${Math.max(0, Math.min(1, a))})`;
  const stroke = () => { g.stroke(); stats.strokes++; };

  function paint(dt: number, state: HudOrbInput) {
    stats.strokes = 0;
    const mood = state.mood, target = STYLE[mood], ease = state.reduced ? 1 : Math.min(1, dt * 3);
    for (const k of ["spin", "breathe", "fire", "glow", "ring"] as const) cur[k] += (target[k] - cur[k]) * ease;
    if (state.reduced) { boot = 9; grow.fill(1); } else { t += dt; boot += dt; }
    const level = Number.isFinite(state.level) ? Math.max(0, Math.min(1, state.level)) : 0;
    energy = state.reduced ? 0 : energy + (level - energy) * Math.min(1, dt * 12);
    if (!state.reduced && mood === "speaking" && energy - prevEnergy > .06 && t - lastShock > .32) { shocks.push({ core: true, x: 0, y: 0, t: 0 }); lastShock = t; }
    prevEnergy = energy;
    const act = ACTIVE_CLUSTER[mood];
    if (act !== active) { if (act >= 0 && !state.reduced && !firstPaint) grow[act] = 0; active = act; }
    firstPaint = false;
    const focus = state.focus >= 0 && state.focus < 6 ? state.focus : -1;
    if (boot > .9) for (let c = 0; c < 6; c++) grow[c] = Math.min(1, grow[c] + dt * .75);
    if (!dragging && !state.reduced) { yaw += dt * (cur.spin * .55 + vy); vy *= Math.pow(.2, dt); pitch += vp * dt; vp *= Math.pow(.05, dt); pitch *= Math.pow(.6, dt); }
    pitch = Math.max(-.32, Math.min(.32, pitch));
    cx = W / 2; cy = H / 2; R = Math.max(10, Math.min((H / 2 - 12) / 1.62, (W / 2 - 12) / 1.62));
    const ca = Math.cos(yaw), sa = Math.sin(yaw), tilt = .28 + pitch, ct = Math.cos(tilt), st = Math.sin(tilt);
    const breath = 1 + Math.sin(t * 1.4) * cur.breathe + energy * .06;
    const bootS = boot >= .9 ? 1 : 1 - Math.pow(1 - boot / .9, 3);
    const proj = (x: number, y: number, z: number, out: P4) => { const x1 = x * ca - z * sa, z1 = x * sa + z * ca; const y2 = y * ct - z1 * st, z2 = y * st + z1 * ct; const f = 3.2 / (3.2 - z2); out[0] = cx + x1 * R * f; out[1] = cy + y2 * R * f; out[2] = z2; out[3] = f; return out; };
    const inside = (x: number, y: number, r: number) => x - r >= 0 && y - r >= 0 && x + r <= W && y + r <= H;
    const dimFor = (c: number) => focus < 0 ? 1 : c === focus ? 1.7 : .22;
    const core = CORE_COLOR;
    g.clearRect(0, 0, W, H);

    /* glow */
    const gl = g.createRadialGradient(cx, cy, 0, cx, cy, R * 1.5);
    gl.addColorStop(0, rgba(core, .2 + cur.glow * .16 + energy * .16)); gl.addColorStop(.35, rgba(core, .06)); gl.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = gl; g.fillRect(0, 0, W, H);

    /* neural dust: a flattened galaxy disc on a weak perspective */
    const dustN = tier >= 1 ? 160 : det.dust.length;
    const flowing = mood === "listening" || mood === "thinking", flowSpeed = mood === "thinking" ? .22 : .1;
    for (let i = 0; i < dustN; i++) {
      const d = det.dust[i]; let r = d.r, al = 1;
      if (flowing) { const u = (d.u + t * flowSpeed * d.sp) % 1; r = 1.15 + (1 - u) * (d.r - 1); al = Math.min(1, u * 4) * Math.min(1, (1 - u) * 6); }
      else if (mood === "speaking") r = d.r * (1 + energy * .08);
      const a = d.a + t * .06 * d.sp / r + yaw * .35;
      const x = Math.cos(a) * r, z = Math.sin(a) * r;
      const y2 = d.y * ct - z * st, z2 = d.y * st + z * ct, f = 6 / (6 - z2);
      const sx = cx + x * R * f, sy = cy + y2 * R * f;
      if (sx < 1 || sy < 1 || sx + d.sz > W - 1 || sy + d.sz > H - 1) continue;
      const twinkle = .45 + .55 * Math.abs(Math.sin(t * .9 * d.sp + d.ph));
      g.fillStyle = rgba([150, 230, 215], (.12 + .35 * (z2 + 3) / 6) * twinkle * bootS * al); g.fillRect(sx, sy, d.sz, d.sz);
    }

    /* orbit rings with ticks, comet tails and mood markers */
    const tmp: P4 = [0, 0, 0, 0];
    const sweep = Math.max(0, Math.min(1, (boot - .5) / .7));
    net.orbits.forEach((o, oi) => {
      if (sweep <= 0) return;
      const cX = Math.cos(o.tx), sX = Math.sin(o.tx), cZ = Math.cos(o.tz), sZ = Math.sin(o.tz);
      const pt = (a: number, out: P4) => { const x = Math.cos(a) * o.r, z = Math.sin(a) * o.r; const y1 = -z * sX, z1 = z * cX; return proj(x * cZ - y1 * sZ, x * sZ + y1 * cZ, z1, out); };
      const steps = Math.max(2, Math.round(120 * sweep));
      g.beginPath(); for (let s = 0; s <= steps; s++) { pt(s / 120 * 6.2832, tmp); if (s) g.lineTo(tmp[0], tmp[1]); else g.moveTo(tmp[0], tmp[1]); }
      g.strokeStyle = "rgba(170,185,210,.17)"; g.lineWidth = 1; stroke();
      g.beginPath(); for (let s = 0; s < steps; s += 4) { pt(s / 120 * 6.2832, tmp); const dx = tmp[0] - cx, dy = tmp[1] - cy, l = Math.hypot(dx, dy) || 1, k = s % 20 === 0 ? 5 : 2.5; const ex = tmp[0] + dx / l * k, ey = tmp[1] + dy / l * k; if (!inside(ex, ey, 0)) continue; g.moveTo(tmp[0], tmp[1]); g.lineTo(ex, ey); }
      g.strokeStyle = "rgba(170,200,215,.22)"; stroke();
      if (sweep < 1) return;
      const markers: number[][] = [];
      if (oi === 0) markers.push([196, 190, 60]);
      if (oi === 1 && mood === "listening") markers.push([59, 167, 240]);
      if (oi === 2 && mood === "thinking") markers.push([170, 140, 255]);
      if (oi === 2 && mood === "speaking") markers.push([245, 197, 66]);
      const trail = tier >= 3 ? 1 : 14;
      markers.forEach((mc, mi) => { for (let k = trail - 1; k >= 0; k--) { pt(t * o.speed * (oi === 0 ? 1 : 1.6) - k * .045 * Math.sign(o.speed) + mi * 3.1, tmp); const fr = 1 - k / trail, rr = (k ? 4 : 6) * tmp[3] * fr; if (!inside(tmp[0], tmp[1], rr)) continue; g.beginPath(); g.arc(tmp[0], tmp[1], rr, 0, 6.2832); g.fillStyle = rgba(mc, k ? .35 * fr : .9); g.fill(); } });
    });

    /* inward listening ripples */
    if (cur.ring > .02 && !state.reduced) for (let k = 0; k < 3; k++) { const p = 1 - ((t * .55 + k / 3) % 1), rr = R * (.3 + p * 1.05); if (!inside(cx, cy, rr)) continue; g.beginPath(); g.arc(cx, cy, rr, 0, 6.2832); g.strokeStyle = rgba(core, p * .32 * cur.ring); g.lineWidth = 1.4; stroke(); }

    /* project nodes, then apply cursor gravity and shockwave push in screen space */
    for (let i = 0; i < N.length; i++) { const n = N[i], s = breath * bootS * (1 + (state.reduced ? 0 : Math.sin(t * 1.7 + n.ph) * .012)); proj(n.p[0] * s, n.p[1] * s, n.p[2] * s, P[i]); }
    for (let i = 0; i < N.length; i++) {
      const p = P[i];
      if (mouse && !dragging) { const dx = mouse.x - p[0], dy = mouse.y - p[1], d = Math.hypot(dx, dy); if (d < 110 && d > 1) { const k = (1 - d / 110) * .16; p[0] += dx * k; p[1] += dy * k; } }
      for (const s of shocks) { const sx = s.core ? cx : s.x, sy = s.core ? cy : s.y, rr = s.core ? R * (.15 + s.t * 1.6) : R * s.t * 1.3; const dx = p[0] - sx, dy = p[1] - sy, d = Math.hypot(dx, dy) || 1; const w = Math.max(0, 1 - Math.abs(d - rr) / (R * .13)) * (1 - s.t); if (w > 0) { p[0] += dx / d * 8 * w; p[1] += dy / d * 8 * w; if (w > .6) bloom[i] = Math.max(bloom[i], .5 * w); } }
      p[0] = Math.max(1, Math.min(W - 1, p[0])); p[1] = Math.max(1, Math.min(H - 1, p[1]));
    }

    /* light highways between the parts of June */
    const hot: Record<Mood, number[]> = { idle: [], listening: [0, 5], thinking: [0, 1], speaking: [2, 3] };
    if (bootS > .95) det.highways.forEach((h, hi) => {
      const A = P[h.a], B = P[h.b], C = proj(h.c[0] * breath, h.c[1] * breath, h.c[2] * breath, [0, 0, 0, 0]);
      if (!inside(C[0], C[1], 0)) return;
      const on = hot[mood].includes(hi) || focus === h.ca || focus === h.cb;
      g.beginPath(); g.moveTo(A[0], A[1]); g.quadraticCurveTo(C[0], C[1], B[0], B[1]);
      g.strokeStyle = rgba(CL[h.ca].col, on ? .16 : .06); g.lineWidth = on ? 1.4 : 1; stroke();
      if (!state.reduced) { g.setLineDash(on ? [3, 16] : [2, 26]); g.lineDashOffset = -t * (on ? 90 : 30); }
      g.strokeStyle = on ? "rgba(235,250,255,.85)" : rgba(CL[h.cb].col, .35); g.lineWidth = on ? 2 : 1.2; stroke(); g.setLineDash([]);
    });

    /* hub to core lines, then edges batched by cluster and depth */
    const edgeA = Math.max(0, Math.min(1, (boot - .35) / .5));
    g.lineWidth = .8; g.beginPath();
    for (const i of net.hubs) { g.moveTo(cx, cy); g.lineTo(P[i][0], P[i][1]); }
    g.strokeStyle = rgba(core, .09 * edgeA); stroke();
    buckets.forEach(b => { b.length = 0; });
    for (let e = 0; e < net.edges.length; e++) { const [a, b] = net.edges[e]; const d = Math.max(0, Math.min(3, Math.floor(((P[a][2] + P[b][2]) / 2 + 1.1) / 2.2 * 4))); buckets[N[a].c * 4 + d].push(e); }
    g.lineWidth = .7;
    for (let c = 0; c < 6; c++) for (let d = 0; d < 4; d++) {
      const list = buckets[c * 4 + d]; if (!list.length) continue;
      g.beginPath(); for (const e of list) { const [a, b] = net.edges[e]; g.moveTo(P[a][0], P[a][1]); g.lineTo(P[b][0], P[b][1]); }
      g.strokeStyle = rgba(CL[c].col, Math.min(.6, (.05 + (d + .5) / 4 * .22) * dimFor(c)) * edgeA); stroke();
    }

    /* dendrite branches */
    const maxD = tier >= 2 ? 2 : 3, A3: P4 = [0, 0, 0, 0], B3: P4 = [0, 0, 0, 0], C3: P4 = [0, 0, 0, 0];
    const tips: [number, number, number, number, number][] = [];
    for (let c = 0; c < 6; c++) for (let d = 0; d <= maxD; d++) {
      g.beginPath(); let any = false;
      for (const s of det.segs) {
        if (s.cl !== c || s.d !== d) continue;
        const f = Math.max(0, Math.min(1, grow[c] * 4 - d)); if (f <= 0) continue;
        const sw = state.reduced ? 0 : Math.sin(t * .8 + s.ph) * .025 * (1 + energy);
        proj(s.a[0] * breath, s.a[1] * breath, s.a[2] * breath, A3); proj((s.c[0] + sw) * breath, (s.c[1] - sw) * breath, s.c[2] * breath, C3); proj(s.b[0] * breath, s.b[1] * breath, s.b[2] * breath, B3);
        if (!inside(A3[0], A3[1], 0) || !inside(B3[0], B3[1], 0) || !inside(C3[0], C3[1], 0)) continue;
        const q1x = A3[0] + (C3[0] - A3[0]) * f, q1y = A3[1] + (C3[1] - A3[1]) * f;
        const q2x = q1x + (C3[0] + (B3[0] - C3[0]) * f - q1x) * f, q2y = q1y + (C3[1] + (B3[1] - C3[1]) * f - q1y) * f;
        g.moveTo(A3[0], A3[1]); g.quadraticCurveTo(q1x, q1y, q2x, q2y); any = true;
        if (s.tip && f >= 1) tips.push([B3[0], B3[1], c, s.ph, B3[2]]);
      }
      if (!any) continue;
      g.strokeStyle = rgba(CL[c].col, Math.min(.85, (.42 - d * .08) * dimFor(c))); g.lineWidth = Math.max(.5, 1.3 - d * .25); stroke();
    }
    for (const [x, y, c, ph, z] of tips) {
      const on = c === focus || c === act, r = on ? 1.6 + Math.abs(Math.sin(t * 6 + ph)) * 1.2 : 1.1;
      if (!inside(x, y, r * 2.4)) continue;
      if (on && tier < 4) { g.beginPath(); g.arc(x, y, r * 2.4, 0, 6.2832); g.fillStyle = rgba(CL[c].col, .18); g.fill(); }
      g.beginPath(); g.arc(x, y, r, 0, 6.2832); g.fillStyle = rgba(CL[c].col, (.35 + .4 * (z + 1) / 2) * Math.min(1, dimFor(c))); g.fill();
    }

    /* core reactor: plasma, counter-rotating dodecahedron, icosahedron */
    const cr = .17 * (1 + energy * .25);
    if (tier < 4) for (let k = 0; k < 3; k++) {
      const jx = Math.sin(t * (1.3 + k) + k) * R * .02, jy = Math.cos(t * (1.1 + k * .7)) * R * .02, pr = R * cr * (1.3 - k * .25);
      const pg = g.createRadialGradient(cx + jx, cy + jy, 0, cx + jx, cy + jy, pr); pg.addColorStop(0, rgba(core, .32 + energy * .3)); pg.addColorStop(1, rgba(core, 0));
      g.fillStyle = pg; g.beginPath(); g.arc(cx + jx, cy + jy, pr, 0, 6.2832); g.fill();
    }
    const dA = -t * .35, dc = Math.cos(dA), ds = Math.sin(dA), dr = cr * 1.55, c5 = Math.cos(.5), s5 = Math.sin(.5);
    g.beginPath();
    for (const [a, b] of det.dodE) for (const [k, v] of [[0, det.dodV[a]], [1, det.dodV[b]]] as const) { const x = v[0] * dc - v[2] * ds, z = v[0] * ds + v[2] * dc; const px = cx + x * R * dr, py = cy + (v[1] * c5 - z * s5) * R * dr; if (k) g.lineTo(px, py); else g.moveTo(px, py); }
    g.strokeStyle = rgba(core, .22 * bootS); g.lineWidth = .8; stroke();
    const cA = t * .6, cc = Math.cos(cA), cs = Math.sin(cA), c7 = Math.cos(cA * .7), s7 = Math.sin(cA * .7);
    const iP = net.icoV.map(v => { const x = v[0] * cc - v[2] * cs, z = v[0] * cs + v[2] * cc; return [cx + x * R * cr * bootS, cy + (v[1] * c7 - z * s7) * R * cr * bootS, v[1] * s7 + z * c7]; });
    g.lineWidth = 1; g.beginPath(); for (const [a, b] of net.icoE) { g.moveTo(iP[a][0], iP[a][1]); g.lineTo(iP[b][0], iP[b][1]); }
    g.strokeStyle = "rgba(225,240,245,.45)"; stroke();
    for (const p of iP) { g.beginPath(); g.arc(p[0], p[1], 1.4, 0, 6.2832); g.fillStyle = "rgba(235,248,250,.8)"; g.fill(); }

    /* waveform halo, driven only by the measured level */
    if ((mood === "speaking" || mood === "listening") && energy > .02) {
      const bars = 132, hr = R * 1.1, col = mood === "speaking" ? [245, 197, 66] : [90, 180, 250];
      g.beginPath();
      for (let i = 0; i < bars; i++) { const a = i / bars * 6.2832 - 1.5708, mi = Math.min(i, bars - i), n = .5 + .5 * Math.sin(mi * .41 + t * 9) * Math.sin(mi * .17 - t * 5.3), len = R * (.012 + .13 * energy * n); const x1 = cx + Math.cos(a) * (hr + len), y1 = cy + Math.sin(a) * (hr + len); if (!inside(x1, y1, 0)) continue; g.moveTo(cx + Math.cos(a) * hr, cy + Math.sin(a) * hr); g.lineTo(x1, y1); }
      g.strokeStyle = rgba(col, .6); g.lineWidth = 1.8; stroke();
    }

    /* idle dream ripple */
    if (!state.reduced && mood === "idle" && t > nextRipple && boot > 2) { ripple = { c: Math.floor(random() * 6), t0: t }; nextRipple = t + 8 + random() * 4; }
    if (ripple) { const age = t - ripple.t0; if (age > 1.6) ripple = null; else { const hp = N[net.hubs[ripple.c * 4]].p; N.forEach((n, i) => { if (n.c !== ripple!.c) return; const d = Math.hypot(n.p[0] - hp[0], n.p[1] - hp[1], n.p[2] - hp[2]); if (Math.abs(age * .8 - d) < .07) bloom[i] = Math.max(bloom[i], .8); }); } }

    /* nodes, back to front, with depth of field and bloom */
    order.sort((a, b) => P[a][2] - P[b][2]);
    for (const i of order) {
      const n = N[i], p = P[i], d = (p[2] + 1.1) / 2.2, col = CL[n.c].col, dim = dimFor(n.c), bl = bloom[i];
      let r = n.size * p[3] * (R / 150) * .62 * (1 + (n.hub ? energy * .35 : energy * .15)) * (1 + bl * .9);
      let a = (.3 + d * .7) * Math.min(1, dim);
      if (d < .4) { r *= 1 + (.4 - d) * 1.6; a *= .55; }
      if (mouse && !dragging) { const dd = Math.hypot(p[0] - mouse.x, p[1] - mouse.y); if (dd < 70) { a = Math.min(1, a + (1 - dd / 70) * .5); r *= 1 + (1 - dd / 70) * .5; } }
      const halo = n.hub ? 2.6 : 2.2;
      if (!inside(p[0], p[1], r * halo)) continue;
      if ((n.hub || bl > .05) && tier < 4) { g.globalCompositeOperation = "lighter"; g.beginPath(); g.arc(p[0], p[1], r * halo, 0, 6.2832); g.fillStyle = rgba(col, (.06 + d * .08 + bl * .25) * Math.min(1, dim)); g.fill(); g.globalCompositeOperation = "source-over"; }
      g.beginPath(); g.arc(p[0], p[1], Math.max(.5, r), 0, 6.2832); g.fillStyle = rgba(bl > .3 ? [255, 255, 255] : col, a + bl * .4); g.fill();
      bloom[i] = Math.max(0, bl - dt * 1.6);
    }

    /* shockwaves */
    for (let s = shocks.length - 1; s >= 0; s--) {
      const sh = shocks[s]; sh.t += dt * (sh.core ? .9 : 1.1);
      if (sh.t >= 1 || state.reduced) { shocks.splice(s, 1); continue; }
      const sx = sh.core ? cx : sh.x, sy = sh.core ? cy : sh.y, rr = sh.core ? R * (.15 + sh.t * 1.6) : R * sh.t * 1.3;
      if (!inside(sx, sy, rr)) continue;
      g.beginPath(); g.arc(sx, sy, rr, 0, 6.2832); g.strokeStyle = sh.core ? rgba(core, (1 - sh.t) * .55) : rgba([168, 247, 234], (1 - sh.t) * .6); g.lineWidth = 1.4 + (1 - sh.t) * 1.5; stroke();
    }

    /* lightning into the working cluster while thinking */
    if (!state.reduced && mood === "thinking" && bootS >= 1) {
      boltClock -= dt;
      if (boltClock <= 0) {
        boltClock = .16 + random() * .14;
        const tc = focus >= 0 ? focus : 3;
        const pool = N.map((n, i) => n.c === tc && (n.hub || n.size > 1.6) ? i : -1).filter(i => i >= 0);
        const to = pool[Math.floor(random() * pool.length)]; bolts.push({ to, t: 0, seed: random() * 1000 }); bloom[to] = 1;
      }
    }
    for (let b = bolts.length - 1; b >= 0; b--) {
      const bo = bolts[b]; bo.t += dt; if (bo.t > .22 || state.reduced) { bolts.splice(b, 1); continue; }
      const T = P[bo.to], pts: [number, number][] = [[cx, cy]]; let sd = bo.seed;
      const jitter = () => { sd = (sd * 9301 + 49297) % 233280; return sd / 233280 - .5; };
      for (let k = 1; k < 9; k++) { const f = k / 9, x = cx + (T[0] - cx) * f, y = cy + (T[1] - cy) * f, nx = -(T[1] - cy), ny = T[0] - cx, nl = Math.hypot(nx, ny) || 1, j = jitter() * R * .12 * Math.sin(f * Math.PI); pts.push([x + nx / nl * j, y + ny / nl * j]); }
      pts.push([T[0], T[1]]);
      if (!pts.every(q => inside(q[0], q[1], 0))) continue;
      const al = 1 - bo.t / .22; g.globalCompositeOperation = "lighter";
      for (const [w, a2, col] of [[4, .16, [150, 120, 255]], [1.2, .95, [235, 230, 255]]] as const) {
        if (w > 2 && tier >= 4) continue;
        g.beginPath(); pts.forEach((q, k) => k ? g.lineTo(q[0], q[1]) : g.moveTo(q[0], q[1]));
        g.strokeStyle = rgba(col as unknown as number[], a2 * al); g.lineWidth = w; stroke();
      }
      g.globalCompositeOperation = "source-over";
    }

    /* signal comets that cascade across the network */
    if (!state.reduced) {
      spawnAcc += dt * (cur.fire + energy * 25) * (bootS >= 1 ? 1 : 0);
      while (spawnAcc > 1) {
        spawnAcc--; if (signals.length >= 150) continue;
        let e: number;
        if (focus >= 0 && random() < .55) { const hs = net.hubs.filter(i => N[i].c === focus), h = hs[Math.floor(random() * hs.length)]; e = det.adjacency[h][Math.floor(random() * det.adjacency[h].length)]; }
        else e = Math.floor(random() * net.edges.length);
        signals.push({ e, p: 0, v: .8 + random() * 1.4, rev: random() < .5, hops: 0, tr: [] });
      }
      if (mouse && !dragging && bootS >= 1) {
        cursorAcc += dt;
        if (cursorAcc > .12) { cursorAcc = 0; let best = -1, bd = 1e9; for (let s = 0; s < 40; s++) { const i = Math.floor(random() * N.length), d = Math.hypot(P[i][0] - mouse.x, P[i][1] - mouse.y); if (d < bd) { bd = d; best = i; } } if (best >= 0 && bd < 140 && det.adjacency[best].length) { const e = det.adjacency[best][0]; signals.push({ e, p: 0, v: 1.6, rev: net.edges[e][1] === best, hops: 2, tr: [] }); } }
      }
    }
    const cascade = mood === "thinking" ? .85 : .5;
    for (let s = signals.length - 1; s >= 0; s--) {
      const sg = signals[s]; sg.p += dt * sg.v;
      let [a, b] = net.edges[sg.e]; if (sg.rev) [a, b] = [b, a];
      if (sg.p >= 1) {
        bloom[b] = Math.max(bloom[b], .9);
        if (sg.hops < 4 && random() < cascade && det.adjacency[b].length > 1) { let e2 = sg.e; for (let k = 0; k < 4 && e2 === sg.e; k++) e2 = det.adjacency[b][Math.floor(random() * det.adjacency[b].length)]; sg.e = e2; sg.rev = net.edges[e2][1] === b; sg.p = 0; sg.hops++; [a, b] = net.edges[sg.e]; if (sg.rev) [a, b] = [b, a]; }
        else { signals.splice(s, 1); continue; }
      }
      const x = P[a][0] + (P[b][0] - P[a][0]) * sg.p, y = P[a][1] + (P[b][1] - P[a][1]) * sg.p, col = CL[N[a].c].col;
      if (tier < 3) { sg.tr.push([x, y]); if (sg.tr.length > 7) sg.tr.shift(); for (let k = 1; k < sg.tr.length; k++) { g.beginPath(); g.moveTo(sg.tr[k - 1][0], sg.tr[k - 1][1]); g.lineTo(sg.tr[k][0], sg.tr[k][1]); g.strokeStyle = rgba(col, k / sg.tr.length * .55); g.lineWidth = k / sg.tr.length * 2; stroke(); } }
      if (!inside(x, y, 4)) continue;
      g.beginPath(); g.arc(x, y, 4, 0, 6.2832); g.fillStyle = rgba(col, .25); g.fill();
      g.beginPath(); g.arc(x, y, 1.6, 0, 6.2832); g.fillStyle = "rgba(255,255,255,.95)"; g.fill();
    }

    /* no text on the orb: a focused cluster gets a light-only target lock */
    if (focus >= 0 && boot > 1.4) {
      const c = CL[focus], p = proj(c.dir[0] * .8 * breath, c.dir[1] * .8 * breath, c.dir[2] * .8 * breath, tmp);
      const s = R * .16, L = R * .05, x0 = p[0] - s, x1 = p[0] + s, y0 = p[1] - s, y1 = p[1] + s;
      if (inside(x0, y0, 0) && inside(x1, y1, 0) && p[2] > -.2) {
        g.beginPath(); g.moveTo(x0, y0 + L); g.lineTo(x0, y0); g.lineTo(x0 + L, y0); g.moveTo(x1 - L, y0); g.lineTo(x1, y0); g.lineTo(x1, y0 + L); g.moveTo(x0, y1 - L); g.lineTo(x0, y1); g.lineTo(x0 + L, y1); g.moveTo(x1 - L, y1); g.lineTo(x1, y1); g.lineTo(x1, y1 - L);
        g.strokeStyle = rgba(c.col, .55 + .35 * Math.sin(t * 4)); g.lineWidth = 1.3; stroke();
      }
    }
    stats.tier = tier;
  }

  /* performance governor: drop or restore detail tiers by measured paint time */
  function govern(ms: number, dt: number) {
    ema = ema * .9 + ms * .1; govClock += dt;
    if (govClock > 1.5) { govClock = 0; if (ema > 14 && tier < 4) tier++; else if (ema < 8 && tier > 0) tier--; }
  }
  function cancel() { if (frame) host.cancelFrame(frame); if (timer) host.cancelDelay(timer); frame = timer = 0; }
  function schedule() {
    if (disposed || !visible || host.hidden() || frame || timer || !W || !H) return;
    if (read().reduced) timer = host.delay(() => { timer = 0; tick(0); }, 100);
    else frame = host.requestFrame(now => { frame = 0; tick(now); });
  }
  function tick(now: number) {
    if (disposed || !visible || host.hidden()) return;
    const state = read();
    if (state.reduced) { if (dirty) { paint(0, state); dirty = false; } last = null; }
    else if (last === null || now - last >= 1000 / 30 - .1) {
      const dt = last === null ? 0 : Math.min((now - last) / 1000, .05); last = now;
      const start = typeof performance !== "undefined" ? performance.now() : 0;
      paint(dt, state); dirty = false;
      govern(typeof performance !== "undefined" ? performance.now() - start : 0, dt);
    }
    schedule();
  }
  function invalidate() { if (disposed) return; dirty = true; cancel(); last = null; if (read().reduced && visible && !host.hidden()) tick(0); else schedule(); }
  function resize() {
    if (disposed) return;
    const bounds = canvas.getBoundingClientRect(); W = bounds.width; H = bounds.height;
    const dpr = Math.min(Math.max(host.pixelRatio(), 1), W > 1200 ? 1.5 : 2);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    g.setTransform(dpr, 0, 0, dpr, 0, 0); invalidate();
  }
  function hit(x: number, y: number): OrbHit {
    if (Math.hypot(x - cx, y - cy) < R * .22) return { kind: "core" };
    let best = -1, bd = 24;
    P.forEach((p, i) => { if (p[2] < -.3) return; const d = Math.hypot(p[0] - x, p[1] - y); if (d < bd) { bd = d; best = N[i].c; } });
    return best >= 0 ? { kind: "cluster", cluster: best } : { kind: "space" };
  }
  const releaseSize = host.observeSize(resize);
  const releaseIntersection = host.observeVisibility(value => { visible = value; invalidate(); });
  const releaseVisibility = host.onVisibility(invalidate);
  resize();
  let lx = 0, ly = 0, sx = 0, sy = 0, moved = false, pressed = false;
  return {
    invalidate, stats, hit,
    pointerMove(x: number, y: number, clientX: number, clientY: number): OrbHit {
      if (dragging) { const dx = clientX - lx, dy = clientY - ly; yaw += dx * .008; pitch = Math.max(-.32, Math.min(.32, pitch + dy * .004)); vy = dx * .3; vp = dy * .12; lx = clientX; ly = clientY; if (Math.abs(clientX - sx) + Math.abs(clientY - sy) > 5) moved = true; invalidate(); return { kind: "space" }; }
      mouse = { x, y }; return hit(x, y);
    },
    /** With reduced motion a press is still tracked so clicks select, but it never rotates the network. */
    pointerDown(clientX: number, clientY: number) { pressed = true; moved = false; lx = sx = clientX; ly = sy = clientY; dragging = !read().reduced; },
    /** A click (not a drag): the core says hello, a cluster regrows, empty space gets a shockwave. */
    pointerUp(x: number, y: number): OrbHit | null {
      const was = pressed; pressed = dragging = false;
      if (!was || moved) return null;
      const result = hit(x, y);
      if (read().reduced) { invalidate(); return result; }
      if (result.kind === "core") { shocks.push({ core: true, x: 0, y: 0, t: 0 }); grow.fill(0); bloom.fill(.7); }
      else if (result.kind === "cluster") grow[result.cluster] = 0;
      else shocks.push({ core: false, x, y, t: 0 });
      invalidate(); return result;
    },
    pointerLeave() { mouse = null; dragging = pressed = false; },
    rotate(dx: number, dy: number) { yaw += dx; pitch = Math.max(-.32, Math.min(.32, pitch + dy)); invalidate(); },
    dispose() { if (disposed) return; disposed = true; cancel(); signals.length = shocks.length = bolts.length = 0; releaseSize(); releaseIntersection(); releaseVisibility(); },
  };
}
export type HudOrbRenderer = NonNullable<ReturnType<typeof createHudOrbRenderer>>;
