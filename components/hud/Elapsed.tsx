"use client";
import { useEffect, useState } from "react";
import { elapsedText } from "@/lib/wait-status";

/** Seconds since a request started, ticking once a second; hidden from screen readers to avoid chatter. */
export default function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { setNow(Date.now()); const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, [since]);
  const text = since ? elapsedText(now - since) : "";
  return text ? <span className="hud-elapsed" aria-hidden="true"> · {text}</span> : null;
}
