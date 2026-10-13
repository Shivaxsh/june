"use client";
import { useEffect, useRef, useState } from "react";
import type { Mood } from "@/lib/orb/state";
import type { Level } from "@/lib/orb/audio-controller";

const palette = ["#8ee9d0", "#86bceb", "#c4a9e4", "#efd099", "#79c8a1"];
const accents: Record<Mood, string> = { idle: "#8ee9d0", listening: "#86bceb", thinking: "#c4a9e4", speaking: "#efd099" };

// Deterministic points make resizing and remounting stable. Each group has its own colour.
const points = Array.from({ length: 110 }, (_, i) => {
  const y = 1 - (i / 109) * 2;
  const radius = Math.sqrt(1 - y * y);
  const angle = i * 2.399963;
  return { x: Math.cos(angle) * radius, y, z: Math.sin(angle) * radius, group: Math.floor((angle % (Math.PI * 2)) / (Math.PI * 2) * 5) };
});

export default function Orb({ mood, label, level, still = false, activity, speechActive = false }: { mood: Mood; label: string; level: Level; still?: boolean; activity?: Level; speechActive?: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const meter = useRef<HTMLMeterElement>(null);
  const reading = useRef<HTMLSpanElement>(null);
  const currentMood = useRef(mood);
  const [available, setAvailable] = useState(true);
  const [systemStill, setSystemStill] = useState(false);
  const reduced = still || systemStill;
  useEffect(() => { currentMood.current = mood; }, [mood]);
  useEffect(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const changed = () => setSystemStill(media.matches);
    changed(); media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  useEffect(() => {
    const element = canvas.current;
    const ctx = element?.getContext("2d");
    if (!element || !ctx) { setAvailable(false); return; }
    let frame = 0, previous = 0, elapsed = 0, width = 320;
    let lastMood: Mood | null = null;
    let needsDraw = true;
    const resize = () => {
      width = element.getBoundingClientRect().width || 320;
      const ratio = Math.min(devicePixelRatio || 1, 1.75);
      element.width = Math.round(width * ratio); element.height = Math.round(width * ratio);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0); needsDraw = true;
    };
    const observer = new ResizeObserver(resize); observer.observe(element); resize();
    const draw = (time: number) => {
      frame = requestAnimationFrame(draw);
      if (time - previous < (reduced ? 100 : 1000 / 30)) return;
      const dt = previous ? Math.min(60, time - previous) : 0;
      previous = time;
      const signal = Math.max(0, Math.min(1, level.current));
      const expression = Math.max(signal, (activity?.current || 0) * .3);
      if (meter.current) meter.current.value = signal;
      if (reading.current) reading.current.textContent = `${Math.round(signal * 100)}%`;
      if (reduced && !needsDraw && lastMood === currentMood.current) return;
      needsDraw = false; lastMood = currentMood.current;
      elapsed += reduced ? 0 : dt / 1000;
      const t = elapsed;
      const mood = currentMood.current;
      const accent = accents[mood];
      const mid = width / 2;
      const radius = width * .31;
      const breath = reduced ? 1 : 1 + Math.sin(t * (mood === "thinking" ? 2.6 : 1)) * .024 + expression * .12;
      const spin = reduced ? .35 : t * (mood === "thinking" ? .20 : .07) + .35;
      ctx.clearRect(0, 0, width, width);
      const halo = ctx.createRadialGradient(mid, mid, 0, mid, mid, width * .47);
      halo.addColorStop(0, accent + "28"); halo.addColorStop(.5, accent + "09"); halo.addColorStop(1, accent + "00");
      ctx.fillStyle = halo; ctx.fillRect(0, 0, width, width);
      // Orbit rings are flattened circles; different angles suggest depth.
      for (let ring = 0; ring < 3; ring++) {
        ctx.save(); ctx.translate(mid, mid); ctx.rotate(ring * 1.04 + (reduced ? 0 : t * .015));
        ctx.strokeStyle = accent + (ring === 0 ? "50" : "22"); ctx.lineWidth = .7;
        ctx.beginPath(); ctx.ellipse(0, 0, radius * 1.24, radius * (.33 + ring * .16), 0, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
      }
      const projected = points.map((p, i) => {
        const x = p.x * Math.cos(spin) - p.z * Math.sin(spin);
        const z = p.x * Math.sin(spin) + p.z * Math.cos(spin);
        const perspective = 1 + z * .14;
        const drift = reduced ? 0 : Math.sin(t * .65 + i) * .015;
        return { x: mid + x * radius * breath * perspective, y: mid + (p.y + drift) * radius * breath * perspective, z, group: p.group };
      });
      for (let i = 0; i < projected.length; i++) {
        const a = projected[i];
        for (let j = i + 1; j < projected.length; j++) {
          const b = projected[j];
          const distance = Math.hypot(a.x - b.x, a.y - b.y);
          if (distance > radius * .34 || Math.abs(a.z - b.z) > .65) continue;
          ctx.globalAlpha = (.08 + (1 - distance / (radius * .34)) * .26) * (a.z > 0 ? 1 : .5);
          ctx.strokeStyle = palette[a.group]; ctx.lineWidth = .7;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
          if (!reduced && (i * 7 + j) % 37 === 0) {
            const travel = (t * (mood === "thinking" ? .8 : .3) + i * .1) % 1;
            ctx.globalAlpha = .85; ctx.fillStyle = accent;
            ctx.beginPath(); ctx.arc(a.x + (b.x - a.x) * travel, a.y + (b.y - a.y) * travel, 1.35, 0, Math.PI * 2); ctx.fill();
          }
        }
      }
      ctx.globalAlpha = 1;
      const coreRadius = radius * (.33 + (reduced ? 0 : expression * .14));
      const core = ctx.createRadialGradient(mid, mid, 0, mid, mid, coreRadius);
      core.addColorStop(0, "#f1fff5"); core.addColorStop(.12, accent + "dc"); core.addColorStop(.4, accent + "30"); core.addColorStop(1, accent + "00");
      ctx.fillStyle = core; ctx.beginPath(); ctx.arc(mid, mid, coreRadius, 0, Math.PI * 2); ctx.fill();
      for (const p of [...projected].sort((a, b) => a.z - b.z)) {
        ctx.globalAlpha = .35 + (p.z + 1) * .32; ctx.fillStyle = palette[p.group];
        ctx.beginPath(); ctx.arc(p.x, p.y, 1.25 + (p.z + 1) * .65, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;
      if (mood === "listening" || mood === "speaking") {
        // A restrained outer arc differentiates audio states even without motion.
        ctx.strokeStyle = accent + "aa"; ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.arc(mid, mid, radius * 1.37, mood === "listening" ? 3.5 : .4, mood === "listening" ? 5.9 : 2.8); ctx.stroke();
      }
    };
    const visibility = () => { cancelAnimationFrame(frame); previous = 0; if (!document.hidden) frame = requestAnimationFrame(draw); };
    document.addEventListener("visibilitychange", visibility); visibility();
    return () => { cancelAnimationFrame(frame); observer.disconnect(); document.removeEventListener("visibilitychange", visibility); };
  }, [level, reduced, activity]);
  return <figure className="network-orb" data-mood={mood} data-motion={reduced ? "still" : "animated"}>
    <canvas ref={canvas} aria-hidden="true" />
    {!available && <div className="orb-fallback">✦</div>}
    <figcaption><span className="orb-state" role="status">{label}</span><span className="level-readout" hidden={speechActive}><span>Sound level</span><meter ref={meter} min="0" max="1" value="0" aria-label="Sound level" /><span ref={reading}>0%</span></span>{speechActive && <span className="motion-caption">Speech activity · amplitude unavailable</span>}{reduced && <span className="motion-caption">Still view · movement reduced</span>}</figcaption>
  </figure>;
}
