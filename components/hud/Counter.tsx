"use client";
import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "@/lib/hud/useReducedMotion";

/** A glowing number that counts up only when its real value changes. */
export default function Counter({ value, format = n => n.toLocaleString("en-US"), duration = 1400 }: { value: number | null; format?: (n: number) => string; duration?: number }) {
  const [shown, setShown] = useState(0);
  const from = useRef(0);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (value === null) return;
    if (reduced) { setShown(value); from.current = value; return; }
    const start = performance.now(), origin = from.current;
    let frame = 0;
    const step = () => {
      const k = Math.min(1, (performance.now() - start) / duration), eased = 1 - Math.pow(1 - k, 3);
      const now = Math.round(origin + (value - origin) * eased);
      setShown(now); from.current = now;
      if (k < 1) frame = requestAnimationFrame(step); else from.current = value;
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value, duration, reduced]);
  // Screen readers get the final value, never the counting frames.
  return <span className="hud-big"><span aria-hidden="true">{value === null ? "—" : format(shown)}</span><span className="sr-only">{value === null ? "unavailable" : format(value)}</span></span>;
}
