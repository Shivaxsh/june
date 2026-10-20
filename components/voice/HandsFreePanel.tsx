"use client";
import { useEffect, useRef } from 'react';
import type { HandsFreeControls } from './useHandsFree';

export const handsFreeLabels = {
  off: 'Hands-free is off', requesting: 'Requesting microphone access', connecting: 'Preparing local wake phrase and speech detection',
  waiting: 'Waiting for “Hey June” · microphone on', listening: 'Listening to your question',
  transcribing: 'Transcribing on this Mac', generating: 'Generating June’s reply · speak to interrupt', speaking: 'June is speaking · speak to interrupt',
  followup: 'Listening for a follow-up · 30-second window',
};

export default function HandsFreePanel({ controls, enabled, onStart }: { controls: HandsFreeControls; enabled: boolean; onStart(): void }) {
  const { state, active } = controls;
  const meter = useRef<HTMLMeterElement>(null);
  useEffect(() => {
    const interval = setInterval(() => { if (meter.current) meter.current.value = controls.level.current; }, 100);
    return () => clearInterval(interval);
  }, [controls.level]);
  return <section className={`handsfree-panel ${active ? 'handsfree-on' : ''}`} aria-label="Hands-free conversation">
    <div className="handsfree-heading"><div><span className="eyebrow">A conversation, without the buttons</span><h2>Just say <em>“Hey June.”</em></h2></div><span className={`mic-badge ${active ? 'mic-on' : ''}`}><span aria-hidden="true">●</span> {state.phase === 'requesting' ? 'Microphone requested · starting' : active ? 'Microphone on · local only' : 'Microphone off'}</span></div>
    <p>Say “Hey June” to start. During a reply, just start speaking to interrupt — no wake phrase needed. After each reply, you have 30 seconds to follow up.</p>
    <div className="handsfree-actions">{active ? <button className="quiet-button mic-active" onClick={() => controls.stop()}>Disable hands-free</button> : <button className="send-button" disabled={!enabled || controls.status.state !== 'ready'} onClick={onStart}>Enable hands-free <span aria-hidden="true">↗</span></button>}<label>Pause before sending<select aria-label="Pause before sending" value={controls.pause} disabled={active} onChange={event => controls.setPause(event.target.value)}><option value="short">Short · 0.8 seconds</option><option value="normal">Normal · 1.5 seconds</option><option value="patient">Patient · 2.5 seconds</option></select></label><button className="quiet-button" disabled={active} onClick={() => void controls.refresh()}>Refresh hands-free</button></div>
    <div className="handsfree-readout"><p role="status">{state.probing ? 'Checking microphone sound · June’s voice paused' : handsFreeLabels[state.phase]}</p>{active && <meter ref={meter} min="0" max="1" value="0" aria-label="Hands-free microphone level" />}</div>
    <p className="handsfree-note">{controls.status.message}{!enabled && ' Choose a local female voice, enable Speak replies and connect Local AI before starting.'}</p>
    {state.transcriptionMs > 0 && <p className="handsfree-note">Last local transcription: {(state.transcriptionMs / 1000).toFixed(1)} seconds · speech detection confidence {Math.round(state.vad * 100)}%</p>}
    {state.error && <div className="error-notice" role="alert">{state.error}</div>}
    <p className="handsfree-note">Questions send automatically in this mode. Stop or leaving this page releases the microphone. The usual Hold to talk control still lets you review first.</p>
    <p className="handsfree-note">June checks for words while her voice keeps playing, so fans and speaker echo do not pause her on sound detection alone. Verified speech stops the old reply. Local verification can take a moment; keep speaking naturally. Headphones or moving the microphone away from airflow can improve recognition.</p>
  </section>;
}
