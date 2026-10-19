"use client";
import { useEffect, useId, useRef, useState } from "react";
import type { Mood } from "@/lib/orb/state";
import type { Level } from "@/lib/orb/audio-controller";
import { createOrbRenderer } from "@/lib/orb/renderer";

export default function Orb({ mood, label, level, still = false, activity, speechActive = false }: { mood: Mood; label: string; level: Level; still?: boolean; activity?: Level; speechActive?: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const meter = useRef<HTMLMeterElement>(null);
  const reading = useRef<HTMLSpanElement>(null);
  const renderer = useRef<ReturnType<typeof createOrbRenderer>>(null);
  const description = useId();
  const [available, setAvailable] = useState(true);
  const [systemStill, setSystemStill] = useState(false);
  const reduced = still || systemStill;
  const inputs = useRef({ mood, label, level, activity, speechActive, reduced });

  useEffect(() => {
    inputs.current = { mood, label, level, activity, speechActive, reduced };
    renderer.current?.invalidate();
  }, [mood, label, level, activity, speechActive, reduced]);
  useEffect(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const changed = () => setSystemStill(media.matches);
    changed(); media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, []);
  useEffect(() => {
    if (!canvas.current) return;
    let disposed = false;
    const instance = createOrbRenderer(canvas.current, () => {
      const input = inputs.current;
      return {
        mood: input.mood, level: input.level.current, activity: input.activity?.current || 0,
        speechActive: input.speechActive, reduced: input.reduced,
        preview: input.label.includes("visual preview"),
      };
    }, signal => {
      if (meter.current) meter.current.value = signal;
      if (reading.current) reading.current.textContent = `${Math.round(signal * 100)}%`;
    });
    renderer.current = instance;
    setAvailable(!!instance);
    // Canvas text uses the same locally hosted font as the artifact's labels.
    document.fonts?.load('600 12px "Bricolage Grotesque"').then(() => {
      if (!disposed) instance?.invalidate();
    }).catch(() => { /* The artifact's system-font fallback remains readable. */ });
    return () => { disposed = true; instance?.dispose(); renderer.current = null; };
  }, []);

  return <figure className="network-orb" data-mood={mood} data-motion={reduced ? "still" : "animated"} aria-describedby={description}>
    <div className="orb-canvas-stage"><canvas ref={canvas} aria-hidden="true" />{!available && <div className="orb-fallback" role="img" aria-label="June’s network illustration is unavailable">✦</div>}</div>
    <figcaption><span className="orb-state" role="status">{label}</span><span className="level-readout" hidden={speechActive}><span>Sound level</span><meter ref={meter} min="0" max="1" value="0" aria-label="Sound level" /><span ref={reading}>0%</span></span>{speechActive && <span className="motion-caption">Speech activity · amplitude unavailable</span>}{reduced && <span className="motion-caption">Still view · movement reduced</span>}<span id={description} className="orb-description">Illustrated modules · labels do not indicate enabled capabilities</span></figcaption>
  </figure>;
}
