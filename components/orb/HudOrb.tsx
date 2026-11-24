"use client";
import { useEffect, useRef, useState } from "react";
import type { Mood } from "@/lib/orb/state";
import type { Level } from "@/lib/orb/audio-controller";
import type { RendererHost } from "@/lib/orb/renderer";
import { createHudOrbRenderer, type HudOrbRenderer } from "@/lib/orb/hud-renderer";
import { CLUSTER_RGB, rgb } from "@/lib/hud/palette";

export type ClusterInfo = { name: string; value: string; hint: string };

function browserHost(canvas: HTMLCanvasElement): RendererHost {
  return {
    requestFrame: callback => requestAnimationFrame(callback), cancelFrame: id => cancelAnimationFrame(id),
    delay: (callback, milliseconds) => window.setTimeout(callback, milliseconds), cancelDelay: id => window.clearTimeout(id),
    pixelRatio: () => window.devicePixelRatio || 1, hidden: () => document.hidden,
    observeSize(callback) { const observer = new ResizeObserver(callback); observer.observe(canvas); return () => observer.disconnect(); },
    observeVisibility(callback) {
      if (!("IntersectionObserver" in window)) return () => {};
      const observer = new IntersectionObserver(entries => callback(entries[0]?.isIntersecting ?? true));
      observer.observe(canvas); return () => observer.disconnect();
    },
    onVisibility(callback) { document.addEventListener("visibilitychange", callback); return () => document.removeEventListener("visibilitychange", callback); },
  };
}

/** June's interactive network: the full-width hero layer of the HUD. */
export default function HudOrb({ mood, level, focus, still = false, info, address = "", onCluster, onCore }: {
  mood: Mood; level: Level; focus: number; still?: boolean; info: ClusterInfo[]; address?: string;
  onCluster: (cluster: number) => void; onCore: () => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const renderer = useRef<HudOrbRenderer | null>(null);
  const [systemStill, setSystemStill] = useState(false);
  const [hover, setHover] = useState<{ cluster: number; x: number; y: number } | null>(null);
  const [toast, setToast] = useState("");
  const [available, setAvailable] = useState(true);
  const reduced = still || systemStill;
  const inputs = useRef({ mood, level, focus, reduced });
  const toastTimer = useRef(0);

  useEffect(() => { inputs.current = { mood, level, focus: hover?.cluster ?? focus, reduced }; renderer.current?.invalidate(); }, [mood, level, focus, reduced, hover]);
  useEffect(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const changed = () => setSystemStill(media.matches);
    changed(); media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  useEffect(() => {
    if (!canvas.current) return;
    const instance = createHudOrbRenderer(canvas.current, () => {
      const input = inputs.current;
      return { mood: input.mood, level: input.level.current, focus: input.focus, reduced: input.reduced };
    }, browserHost(canvas.current));
    renderer.current = instance; setAvailable(!!instance);
    return () => { instance?.dispose(); renderer.current = null; window.clearTimeout(toastTimer.current); };
  }, []);

  const flash = (message: string) => { window.clearTimeout(toastTimer.current); setToast(message); toastTimer.current = window.setTimeout(() => setToast(""), 1700); };
  const local = (event: React.PointerEvent<HTMLCanvasElement>) => { const box = event.currentTarget.getBoundingClientRect(); return { x: event.clientX - box.left, y: event.clientY - box.top, width: box.width }; };
  // The callout is 230px wide (globals.css .hud-callout); keep it inside the stage, even on a phone.
  const calloutX = (x: number, width: number) => Math.max(8, Math.min(x + 26, width - 238));
  const hello = address ? `Hello, ${address}` : "Hello";
  const select = (cluster: number) => {
    if (cluster === 6) { flash(hello); onCore(); }
    else if (cluster >= 0 && info[cluster]) { flash(`Opening ${info[cluster].name}`); onCluster(cluster); }
  };

  const callout = hover && hover.cluster >= 0 ? hover.cluster === 6
    ? { name: "Core", value: `Reactor · ${mood}`, hint: "Click for a hello", color: "rgb(235,248,250)" }
    : { ...info[hover.cluster], color: rgb(CLUSTER_RGB[hover.cluster]) } : null;

  return <div className="hud-orb">
    <canvas ref={canvas} tabIndex={0} role="img" className={hover ? "is-pointing" : ""}
      aria-label="June’s network. Drag or use the arrow keys to turn it; press Enter to say hello, or open the part that is highlighted."
      onPointerMove={event => {
        const point = local(event);
        const result = renderer.current?.pointerMove(point.x, point.y, event.clientX, event.clientY);
        if (!result || event.pointerType === "touch") return;
        const cluster = result.kind === "cluster" ? result.cluster : result.kind === "core" ? 6 : -1;
        if (cluster !== (hover?.cluster ?? -1)) setHover(cluster >= 0 ? { cluster, x: calloutX(point.x, point.width), y: Math.max(8, point.y - 70) } : null);
      }}
      onPointerDown={event => { event.currentTarget.setPointerCapture(event.pointerId); renderer.current?.pointerDown(event.clientX, event.clientY); }}
      onPointerUp={event => {
        const point = local(event); const result = renderer.current?.pointerUp(point.x, point.y);
        const cluster = result?.kind === "core" ? 6 : result?.kind === "cluster" ? result.cluster : -1;
        if (cluster < 0) { if (event.pointerType === "touch") setHover(null); return; }
        // Touch has no hover: the first tap previews the part, a second tap on it opens it.
        if (event.pointerType === "touch" && hover?.cluster !== cluster) { setHover({ cluster, x: calloutX(point.x, point.width), y: Math.max(8, point.y - 70) }); return; }
        select(cluster);
      }}
      onPointerLeave={event => { renderer.current?.pointerLeave(); if (event.pointerType !== "touch") setHover(null); }}
      // A vertical swipe becomes page scrolling (touch-action: pan-y) and cancels the press.
      onPointerCancel={() => renderer.current?.pointerLeave()}
      onKeyDown={event => {
        const step = ({ ArrowLeft: [-.25, 0], ArrowRight: [.25, 0], ArrowUp: [0, -.12], ArrowDown: [0, .12] } as Record<string, number[]>)[event.key];
        if (step) { event.preventDefault(); renderer.current?.rotate(step[0], step[1]); }
        else if ((event.key === "Enter" || event.key === " ") && !event.repeat) { event.preventDefault(); select(hover?.cluster ?? (focus >= 0 ? focus : 6)); }
      }} />
    {!available && <div className="orb-fallback" role="img" aria-label="June’s network illustration is unavailable">✦</div>}
    {callout && hover && <div className="hud-callout hud-lock" aria-hidden="true" style={{ left: hover.x, top: hover.y }}>
      <div className="hud-callout-head"><span className="hud-swatch" style={{ background: callout.color, boxShadow: `0 0 10px ${callout.color}` }} /><span className="hud-label">{callout.name}</span></div>
      <div className="hud-callout-value">{callout.value}</div>
      <div className="hud-callout-hint">{callout.hint}</div>
    </div>}
    {toast && <div className="hud-toast" aria-hidden="true">{toast}</div>}
  </div>;
}
