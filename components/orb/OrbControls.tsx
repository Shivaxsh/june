"use client";
import type { Preview } from "@/lib/orb/state";
export default function OrbControls({ preview, onPreview, still, onStill, disabled = false }: { preview: Preview; onPreview: (value: Preview) => void; still: boolean; onStill: (value: boolean) => void; disabled?: boolean }) {
  return <div className="orb-controls"><fieldset disabled={disabled}><legend>Explore the moods <span>· visual previews</span></legend><div className="mood-buttons">{(["auto", "idle", "listening", "thinking", "speaking"] as Preview[]).map(value => <button key={value} type="button" aria-pressed={preview === value} onClick={() => onPreview(value)}>{value === "auto" ? "Auto" : value[0].toUpperCase() + value.slice(1)}</button>)}</div></fieldset><label className="motion-option"><input type="checkbox" checked={still} onChange={event => onStill(event.target.checked)} /> Still view</label></div>;
}
