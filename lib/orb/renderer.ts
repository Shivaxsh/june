import type { Mood } from "./state";

// Ported from docs/roadmap/building-june.html. Keep seed, topology and visual constants aligned.
export interface Cluster { name: string; col: number[]; dir: number[]; n: number }
export interface NetworkNode { p: number[]; c: number; size: number; hub: boolean; ph: number }
export interface OrbInput { expression?: "steady" | "calm" | "bright"; mood: Mood; level: number; activity: number; speechActive: boolean; preview: boolean; reduced: boolean }
export interface RendererHost {
  requestFrame(callback: (time: number) => void): number;
  cancelFrame(id: number): void;
  delay(callback: () => void, milliseconds: number): number;
  cancelDelay(id: number): void;
  pixelRatio(): number;
  hidden(): boolean;
  observeSize(callback: () => void): () => void;
  observeVisibility(callback: (visible: boolean) => void): () => void;
  onVisibility(callback: () => void): () => void;
}
export function createNetwork() {
  let seed = 7;
  const rnd = () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
  const gauss = () => (rnd() + rnd() + rnd() - 1.5) / 1.5;
  const norm = (v: number[]) => { const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; };

  /* Each cluster is one part of June */
  const CLUSTERS: Cluster[] = [
    {name:"Memory",          col:[59,167,240],  dir:[-.8,.35,.45],  n:95},
    {name:"Voice",           col:[242,140,40],  dir:[.25,.15,.95],  n:90},
    {name:"Personality",     col:[240,98,168],  dir:[.9,.1,-.2],    n:120},
    {name:"Knowledge · RAG", col:[155,123,234], dir:[-.35,-.25,-.9],n:80},
    {name:"Hands · MCP",     col:[52,209,184],  dir:[-.2,-.95,.2],  n:70},
    {name:"Ears",            col:[245,197,66],  dir:[.3,.9,-.1],    n:55}
  ];
  const nodes: NetworkNode[] = [];
  CLUSTERS.forEach((c, ci) => {
    c.dir = norm(c.dir);
    for (let i = 0; i < c.n; i++) {
      const p = norm([c.dir[0] + gauss() * .9, c.dir[1] + gauss() * .9, c.dir[2] + gauss() * .9]);
      const shell = i < 4 ? .78 + rnd() * .1 : .62 + Math.pow(rnd(), .5) * .4;
      const hub = i < 4;
      nodes.push({p:[p[0] * shell, p[1] * shell, p[2] * shell], c:ci, size: hub ? 3.6 + rnd() * 1.6 : .8 + Math.pow(rnd(), 3) * 2.4, hub, ph: rnd() * 6.28});
    }
  });
  /* Wire each node to its nearest neighbours in the same cluster, plus some bridges between clusters */
  const edges: number[][] = [], seen = new Set<string>();
  const d2 = (a: number[], b: number[]) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;
  const addEdge = (a: number, b: number) => { const k = a < b ? a + "-" + b : b + "-" + a; if (a !== b && !seen.has(k)) { seen.add(k); edges.push([a, b]); } };
  nodes.forEach((a, i) => {
    const near: number[][] = [];
    nodes.forEach((b, j) => { if (j !== i && b.c === a.c) near.push([d2(a.p, b.p), j]); });
    near.sort((x, y) => x[0] - y[0]);
    const k = a.hub ? 7 : 2;
    for (let m = 0; m < Math.min(k, near.length); m++) addEdge(i, near[m][1]);
  });
  for (let m = 0; m < 140; m++) {
    const i = Math.floor(rnd() * nodes.length);
    let best = -1, bd = 1e9;
    for (let s = 0; s < 40; s++) { const j = Math.floor(rnd() * nodes.length); if (nodes[j].c !== nodes[i].c) { const dd = d2(nodes[i].p, nodes[j].p); if (dd < bd) { bd = dd; best = j; } } }
    if (best >= 0) addEdge(i, best);
  }
  const hubs = nodes.map((n, i) => n.hub ? i : -1).filter(i => i >= 0);

  /* The wireframe core: an icosahedron */
  const P = (1 + Math.sqrt(5)) / 2;
  const icoV = [[-1,P,0],[1,P,0],[-1,-P,0],[1,-P,0],[0,-1,P],[0,1,P],[0,-1,-P],[0,1,-P],[P,0,-1],[P,0,1],[-P,0,-1],[-P,0,1]].map(norm);
  const icoE: number[][] = [];
  for (let i = 0; i < 12; i++) for (let j = i + 1; j < 12; j++) if (d2(icoV[i], icoV[j]) < 1.2) icoE.push([i, j]);

  /* Orbit rings */
  const ORBITS = [{r:1.28, tx:1.15, tz:.25, speed:.35}, {r:1.4, tx:-.5, tz:1.0, speed:-.22}, {r:1.18, tx:.2, tz:-.7, speed:.5}];

  return { clusters: CLUSTERS, nodes, edges, hubs, icoV, icoE, orbits: ORBITS };
}
interface MoodStyle { spin: number; breathe: number; fire: number; glow: number; ring: number; core: number[]; label: string }
export const MOODS: Record<Mood, MoodStyle> = {
  idle: {spin:.1, breathe:.015, fire:2, glow:.45, ring:0, core:[52,209,184], label:"Idle"},
  listening: {spin:.16, breathe:.03, fire:6, glow:.6, ring:1, core:[59,167,240], label:"Listening"},
  thinking: {spin:.75, breathe:.02, fire:28, glow:.75, ring:0, core:[155,123,234], label:"Thinking"},
  speaking: {spin:.22, breathe:.02, fire:12, glow:.85, ring:0, core:[245,197,66], label:"Speaking"},
};
// Connections are generated once, rather than searched for during animation or React renders.
const NETWORK = createNetwork();
const bounded = (value: number) => Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;

function browserHost(canvas: HTMLCanvasElement): RendererHost {
  return {
    requestFrame: callback => requestAnimationFrame(callback), cancelFrame: id => cancelAnimationFrame(id),
    delay: (callback, milliseconds) => window.setTimeout(callback, milliseconds), cancelDelay: id => window.clearTimeout(id),
    pixelRatio: () => window.devicePixelRatio || 1, hidden: () => document.hidden,
    observeSize(callback) {
      const observer = new ResizeObserver(callback); observer.observe(canvas); return () => observer.disconnect();
    },
    observeVisibility(callback) {
      if (!("IntersectionObserver" in window)) return () => {};
      const observer = new IntersectionObserver(entries => callback(entries[0]?.isIntersecting ?? true));
      observer.observe(canvas); return () => observer.disconnect();
    },
    onVisibility(callback) {
      document.addEventListener("visibilitychange", callback);
      return () => document.removeEventListener("visibilitychange", callback);
    },
  };
}

export function createOrbRenderer(canvas: HTMLCanvasElement, read: () => OrbInput, onLevel: (level: number) => void, host = browserHost(canvas)) {
  const context = canvas.getContext("2d");
  if (!context) return null;
  const ctx = context;
  const { clusters: CLUSTERS, nodes, edges, hubs, icoV, icoE, orbits: ORBITS } = NETWORK;
  const cur: MoodStyle = {...MOODS.idle, core:[...MOODS.idle.core]};
  let energy = 0, angle = 0, t = 0, W = 0, H = 0, last: number | null = null;
  let frame = 0, timer = 0, disposed = false, visible = true, dirty = true, lastMood: Mood | null = null;
  let fireAcc = 0;
  const signals: {e: number; p: number; v: number}[] = [];
  const proj: number[][] = new Array(nodes.length);
  const order = nodes.map((_, i) => i);
  const rgba = (c: number[], a: number) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

  function paint(dt: number, state: OrbInput) {
    const mood = state.mood;
    const target = MOODS[mood], ease = state.reduced ? 1 : Math.min(1, dt * 3);
    for (const k of ["spin","breathe","fire","glow","ring"] as const) cur[k] += (target[k] - cur[k]) * ease;
    for (let i = 0; i < 3; i++) cur.core[i] += (target.core[i] - cur.core[i]) * ease;
    // Real capture/playback uses measured amplitude. Browser speech has activity events, not amplitude.
    let eTarget = Math.max(bounded(state.level), state.speechActive ? bounded(state.activity) * .3 : 0);
    if (state.preview && mood === "speaking") eTarget = .35 + .65 * Math.abs(Math.sin(t * 11) * Math.sin(t * 2.7 + 1)) * (.7 + .3 * Math.sin(t * 23));
    if (state.preview && mood === "listening") eTarget = .2 + .2 * Math.abs(Math.sin(t * 3));
    energy = state.reduced ? 0 : energy + (eTarget - energy) * Math.min(1, dt * 12);
    if (!state.reduced) { t += dt; angle += dt * cur.spin; }
    ctx.clearRect(0, 0, W, H);
    // Preserve the reference geometry, fitting its full perspective orbit envelope into the viewport.
    // The largest 1.4-radius orbit projects to <1.58R; leave room for its moving marker.
    const side = Math.min(W, H);
    const cx = W / 2, cy = H / 2, R = Math.min(side * .36, Math.max(0, side / 2 - 12) / 1.58);
    const ca = Math.cos(angle), sa = Math.sin(angle), tilt = .28, ct = Math.cos(tilt), st = Math.sin(tilt);
    const expression = mood === "idle" ? state.expression === "calm" ? .8 : state.expression === "bright" ? 1.15 : 1 : 1;
    const scale = state.reduced ? 1 : 1 + Math.sin(t * 1.4 * expression) * cur.breathe * expression + energy * .07;
    const project = (x: number, y: number, z: number, out: number[]) => {
      const x1 = x * ca - z * sa, z1 = x * sa + z * ca;
      const y2 = y * ct - z1 * st, z2 = y * st + z1 * ct;
      const f = 3.2 / (3.2 - z2);
      out[0] = cx + x1 * R * f; out[1] = cy + y2 * R * f; out[2] = z2; out[3] = f;
      return out;
    };

    /* Glow behind the core */
    const core = cur.core;
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.1);
    g.addColorStop(0, rgba(core.map(Math.round), .22 + cur.glow * .18 * expression + energy * .15));
    g.addColorStop(.45, rgba(core.map(Math.round), .06));
    g.addColorStop(1, "rgba(5,7,13,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

    /* Orbit rings */
    const tmp = [0,0,0,0], tmp2 = [0,0,0,0];
    ORBITS.forEach((o, oi) => {
      const cX = Math.cos(o.tx), sX = Math.sin(o.tx), cZ = Math.cos(o.tz), sZ = Math.sin(o.tz);
      const pt = (a: number, out: number[]) => {
        let x = Math.cos(a) * o.r, y = 0, z = Math.sin(a) * o.r;
        let y1 = y * cX - z * sX, z1 = y * sX + z * cX;
        let x2 = x * cZ - y1 * sZ, y2 = x * sZ + y1 * cZ;
        return project(x2, y2, z1, out);
      };
      ctx.beginPath();
      for (let s = 0; s <= 96; s++) { pt(s / 96 * 6.2832, tmp); s ? ctx.lineTo(tmp[0], tmp[1]) : ctx.moveTo(tmp[0], tmp[1]); }
      ctx.strokeStyle = "rgba(170,185,210,.16)"; ctx.lineWidth = 1; ctx.stroke();
      if (oi === 0) {
        pt(t * o.speed, tmp);
        ctx.beginPath(); ctx.arc(tmp[0], tmp[1], 6 * tmp[3], 0, 6.2832);
        ctx.fillStyle = "rgba(196,190,60,.85)"; ctx.fill();
      }
    });

    /* Listening ripples */
    if (!state.reduced && cur.ring > .02) {
      for (let k = 0; k < 3; k++) {
        const p = ((t * .55 + k / 3) % 1);
        ctx.beginPath(); ctx.arc(cx, cy, R * (.3 + p * 1.1), 0, 6.2832);
        ctx.strokeStyle = rgba(core.map(Math.round), (1 - p) * .3 * cur.ring); ctx.lineWidth = 1.5; ctx.stroke();
      }
    }

    /* Project every node */
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i], s = scale * (state.reduced ? 1 : 1 + Math.sin(t * 1.7 + n.ph) * .012);
      proj[i] = project(n.p[0] * s, n.p[1] * s, n.p[2] * s, proj[i] || [0,0,0,0]);
    }

    /* Lines to the core from each cluster's hubs */
    hubs.forEach(i => {
      const p = proj[i];
      ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(p[0], p[1]);
      ctx.strokeStyle = rgba(CLUSTERS[nodes[i].c].col, .07 + (p[2] + 1) * .05); ctx.lineWidth = .8; ctx.stroke();
    });

    /* Connections */
    ctx.lineWidth = .7;
    for (let e = 0; e < edges.length; e++) {
      const [a, b] = edges[e], pa = proj[a], pb = proj[b];
      const depth = ((pa[2] + pb[2]) / 2 + 1.1) / 2.2;
      ctx.beginPath(); ctx.moveTo(pa[0], pa[1]); ctx.lineTo(pb[0], pb[1]);
      ctx.strokeStyle = rgba(CLUSTERS[nodes[a].c].col, .05 + depth * .22);
      ctx.stroke();
    }

    /* Wireframe core */
    const cr = .17 * (1 + energy * .25), cAng = t * .6;
    const cc = Math.cos(cAng), cs = Math.sin(cAng);
    const coreP = icoV.map(v => {
      const x = v[0] * cc - v[2] * cs, z = v[0] * cs + v[2] * cc, y = v[1];
      const y1 = y * Math.cos(cAng * .7) - z * Math.sin(cAng * .7), z1 = y * Math.sin(cAng * .7) + z * Math.cos(cAng * .7);
      return [cx + x * R * cr, cy + y1 * R * cr, z1];
    });
    ctx.lineWidth = 1;
    icoE.forEach(([a, b]) => {
      ctx.beginPath(); ctx.moveTo(coreP[a][0], coreP[a][1]); ctx.lineTo(coreP[b][0], coreP[b][1]);
      ctx.strokeStyle = rgba([225,240,245], .25 + ((coreP[a][2] + coreP[b][2]) / 2 + 1) * .2); ctx.stroke();
    });
    coreP.forEach(p => { ctx.beginPath(); ctx.arc(p[0], p[1], 1.4, 0, 6.2832); ctx.fillStyle = "rgba(235,248,250,.8)"; ctx.fill(); });

    /* Nodes, back to front */
    order.sort((a, b) => proj[a][2] - proj[b][2]);
    for (let k = 0; k < order.length; k++) {
      const i = order[k], n = nodes[i], p = proj[i];
      const depth = (p[2] + 1.1) / 2.2;
      const r = n.size * p[3] * (1 + (n.hub ? energy * .35 : energy * .15));
      const col = CLUSTERS[n.c].col;
      if (n.hub) {
        ctx.beginPath(); ctx.arc(p[0], p[1], r * 2.4, 0, 6.2832);
        ctx.fillStyle = rgba(col, .08 + depth * .1); ctx.fill();
      }
      ctx.beginPath(); ctx.arc(p[0], p[1], r, 0, 6.2832);
      ctx.fillStyle = rgba(col, .3 + depth * .7); ctx.fill();
    }

    /* Signals firing along connections */
    fireAcc += state.reduced ? 0 : dt * (cur.fire + energy * 25);
    while (fireAcc > 1) { fireAcc--; if (signals.length < 120) signals.push({e: Math.floor(Math.random() * edges.length), p: 0, v: .8 + Math.random() * 1.4}); }
    for (let s = signals.length - 1; s >= 0; s--) {
      const sg = signals[s]; sg.p += dt * sg.v;
      if (sg.p >= 1) { signals.splice(s, 1); continue; }
      const [a, b] = edges[sg.e], pa = proj[a], pb = proj[b];
      const x = pa[0] + (pb[0] - pa[0]) * sg.p, y = pa[1] + (pb[1] - pa[1]) * sg.p;
      const col = CLUSTERS[nodes[a].c].col;
      ctx.beginPath(); ctx.arc(x, y, 4, 0, 6.2832); ctx.fillStyle = rgba(col, .25); ctx.fill();
      ctx.beginPath(); ctx.arc(x, y, 1.6, 0, 6.2832); ctx.fillStyle = "rgba(255,255,255,.95)"; ctx.fill();
    }

    /* Cluster labels, shown when the cluster faces you */
    ctx.font = `600 ${Math.max(11, Math.round(R * .075))}px "Bricolage Grotesque", "Avenir Next", system-ui, sans-serif`;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    CLUSTERS.forEach(c => {
      const p = project(c.dir[0] * .8 * scale, c.dir[1] * .8 * scale, c.dir[2] * .8 * scale, tmp2);
      const a = Math.max(0, Math.min(1, (p[2] + .1) * 1.6));
      if (a <= 0) return;
      ctx.fillStyle = `rgba(5,7,13,${a * .55})`;
      const w = ctx.measureText(c.name).width + 12;
      ctx.fillRect(p[0] - w / 2, p[1] - 10, w, 20);
      ctx.fillStyle = `rgba(240,244,250,${a})`;
      ctx.fillText(c.name, p[0], p[1]);
    });
  }

  function cancel() {
    if (frame) host.cancelFrame(frame);
    if (timer) host.cancelDelay(timer);
    frame = timer = 0;
  }
  function schedule() {
    if (disposed || !visible || host.hidden() || frame || timer || !W || !H) return;
    if (read().reduced) timer = host.delay(() => { timer = 0; tick(0); }, 100);
    else frame = host.requestFrame(now => { frame = 0; tick(now); });
  }
  function tick(now: number) {
    if (disposed || !visible || host.hidden()) return;
    const state = read();
    onLevel(bounded(state.level));
    if (state.reduced) {
      if (dirty || lastMood !== state.mood) { paint(0, state); dirty = false; lastMood = state.mood; }
      last = null;
    } else if (last === null || now - last >= 1000 / 30 - .1) {
      const dt = last === null ? 0 : Math.min((now - last) / 1000, .05);
      last = now; paint(dt, state); dirty = false; lastMood = state.mood;
    }
    schedule();
  }
  function invalidate() {
    if (disposed) return;
    dirty = true;
    cancel(); last = null;
    if (read().reduced && visible && !host.hidden()) tick(0);
    else schedule();
  }
  function resize() {
    if (disposed) return;
    const bounds = canvas.getBoundingClientRect();
    W = bounds.width; H = bounds.height;
    const dpr = Math.min(Math.max(host.pixelRatio(), 1), 2);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    invalidate();
  }
  const releaseSize = host.observeSize(resize);
  const releaseIntersection = host.observeVisibility(value => { visible = value; invalidate(); });
  const releaseVisibility = host.onVisibility(invalidate);
  resize();
  return {
    invalidate,
    dispose() {
      if (disposed) return;
      disposed = true; cancel(); signals.length = 0;
      releaseSize(); releaseIntersection(); releaseVisibility();
    },
  };
}
