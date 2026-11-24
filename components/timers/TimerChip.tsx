"use client";
import { useEffect, useState } from "react";
import { remainingMs, timerText, type Timer } from "@/lib/timers";

/** The nearest running timer in the HUD, on the server's clock. */
export default function TimerChip({ timer, serverNow, receivedAt, onOpen }: { timer: Timer; serverNow: number; receivedAt: number; onOpen(): void }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const tick = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(tick); }, []);
  const text = timerText(timer, remainingMs(timer, serverNow, receivedAt, now));
  return <button type="button" className="hud-chip hud-timer-chip" onClick={onOpen} aria-label={`${timer.label || "Timer"}: ${text}. Open Timers`}>
    <span aria-hidden="true">◷</span>{timer.label ? <span className="hud-timer-label">{timer.label}</span> : null}<span className="timer-clock">{text}</span></button>;
}
