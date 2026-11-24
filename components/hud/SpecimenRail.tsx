"use client";
import { forwardRef, useEffect, useState } from "react";
import type { Level } from "@/lib/orb/audio-controller";
import { bitRows, pushBit } from "@/lib/hud/atlas";
import { useReducedMotion } from "@/lib/hud/useReducedMotion";
import Counter from "./Counter";

export type RailRow = { label: string; value: string; onOpen?: () => void; pressed?: boolean };

/** The Specimen plate's left data column: real readouts only, a live voice-activity bit box, and local/cloud split. */
const SpecimenRail = forwardRef<HTMLElement, {
  params: number | null; rows: RailRow[]; level: Level; micLive: boolean; timings: { label: string; value: string }[];
  parts: { name: string; onOpen: () => void }[];
}>(function SpecimenRail({ params, rows, level, micLive, timings, parts }, ref) {
  const reduced = useReducedMotion();
  const [bits, setBits] = useState("0".repeat(36));
  useEffect(() => {
    if (!micLive || reduced) return;
    const timer = window.setInterval(() => setBits(previous => pushBit(previous, level.current)), 120);
    return () => window.clearInterval(timer);
  }, [micLive, reduced, level]);
  return <aside ref={ref} className="june-rail" aria-label="June readouts">
    <p className="june-rail-title">June · local</p>
    <dl className="june-rail-rows">
      <div><dt>Params</dt><dd><Counter value={params} /></dd></div>
      {rows.map(row => <div key={row.label}><dt>{row.label}</dt><dd>{row.onOpen
        ? <button type="button" className="june-rail-link" aria-pressed={row.pressed} onClick={row.onOpen}>{row.value}</button> : row.value}</dd></div>)}
    </dl>
    <div className="june-rail-split">
      <div className="june-bits" aria-label={micLive ? "Live voice activity" : "Voice activity (microphone off)"}>
        {bitRows(bits).map((row, i) => <span key={i}>{row}</span>)}
      </div>
      <div className="june-share">
        <span className="june-share-big">100%</span><span className="june-share-label">local</span>
        <span className="sp-rule" aria-hidden="true" />
        <span className="june-share-big">0%</span><span className="june-share-label">cloud</span>
      </div>
    </div>
    <dl className="june-rail-rows is-white">{timings.map(t => <div key={t.label}><dt>{t.label}</dt><dd>{t.value}</dd></div>)}</dl>
    <nav className="june-parts" aria-label="Parts of June">{parts.map(p => <button key={p.name} type="button" onClick={p.onOpen}><span className="sp-x" aria-hidden="true">×</span>{p.name}</button>)}</nav>
  </aside>;
});
export default SpecimenRail;
