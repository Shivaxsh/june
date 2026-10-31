"use client";
import { useEffect, useId, useRef } from 'react';
import TimingReadout from './TimingReadout';
import type { HandsFreeControls } from './useHandsFree';

export const handsFreeLabels = {
  off: 'Hands-free is off', requesting: 'Requesting microphone access', connecting: 'Connecting to local audio', preparing: 'Preparing local wake phrase and speech detection',
  waiting: 'Waiting for “Hey June” · microphone on', listening: 'Listening to your question',
  transcribing: 'Transcribing on this Mac', generating: 'Generating June’s reply · speak to interrupt', speaking: 'June is speaking · speak to interrupt',
  followup: 'Listening for a follow-up · 30-second window',
};

const echoLabels = {
  'system-audio': 'System audio cancellation', 'browser-managed': 'Browser managed echo cancellation',
  off: 'Echo cancellation off', unknown: 'Echo cancellation unknown',
};

export default function HandsFreePanel({ controls, enabled, onStart }: { controls: HandsFreeControls; enabled: boolean; onStart(): void }) {
  const { state, active } = controls;
  const id = useId();
  const preparing = ['requesting', 'connecting', 'preparing'].includes(state.phase);
  const native = state.audioSource === 'native';
  const meter = useRef<HTMLMeterElement>(null);
  useEffect(() => {
    const interval = setInterval(() => { if (meter.current) meter.current.value = controls.level.current; }, 100);
    return () => clearInterval(interval);
  }, [controls.level]);
  return <section className={`handsfree-panel ${active ? 'handsfree-on' : ''}`} aria-label="Hands-free conversation">
    <div className="handsfree-heading"><div><span className="eyebrow">A conversation, without the buttons</span><h2>Just say <em>“Hey June.”</em></h2></div><span className={`mic-badge ${active ? 'mic-on' : ''}`}><span aria-hidden="true">●</span> {preparing ? (state.permission === 'requesting' ? 'Microphone permission requested' : 'Preparing microphone') : active ? 'Microphone on · local only' : 'Microphone off'}</span></div>
    <p>Say “Hey June” to start. During a reply, just start speaking to interrupt — no wake phrase needed. After each reply, you have 30 seconds to follow up.</p>
    <div className="handsfree-actions">{active ? <button className="quiet-button mic-active" onClick={() => controls.stop()}>Disable hands-free</button> : <button className="send-button" disabled={!enabled || controls.status.state !== 'ready'} onClick={onStart}>Enable hands-free <span aria-hidden="true">↗</span></button>}<label htmlFor={`${id}-pause`}>Pause before sending<select id={`${id}-pause`} aria-label="Pause before sending" value={controls.pause} disabled={active} onChange={event => controls.setPause(event.target.value)}><option value="short">Short · 0.8 seconds</option><option value="normal">Normal · 1.5 seconds</option><option value="patient">Patient · 2.5 seconds</option></select></label><button className="quiet-button" disabled={active} onClick={() => void controls.refresh()}>Refresh hands-free</button></div>
    <div className="handsfree-readout"><p role="status">{state.probing ? 'Checking microphone sound · June’s voice paused' : handsFreeLabels[state.phase]}</p>{active && <meter ref={meter} min="0" max="1" value="0" aria-label="Hands-free microphone level" />}</div>
    {active && <p className="handsfree-note">{native ? (preparing ? 'Preparing native Mac capture and playback' : 'Native Mac capture and playback · acoustic echo cancellation enabled') : `Browser reports: ${echoLabels[state.echoMode ?? 'unknown']}. Processing settings do not verify acoustic echo removal.`}</p>}
    <p className="handsfree-note">{controls.audioSource === 'browser' ? 'Select Native Mac audio to enable hands-free. Browser audio supports manual recording. ' : ''}{controls.status.message}{!enabled && ' Choose a local female voice, enable Speak replies and connect Local AI before starting.'}</p>
    {state.permission === 'denied' && <p className="handsfree-note">Allow microphone access for June in macOS System Settings, then refresh hands-free. Voice previews do not need microphone permission.</p>}
    {state.transcriptionMs > 0 && <p className="handsfree-note">Last local transcription: {(state.transcriptionMs / 1000).toFixed(1)} seconds · speech detection confidence {Math.round(state.vad * 100)}%</p>}
    <TimingReadout timings={state.timings} label="Voice turn timings" />
    {state.error && <div className="error-notice" role="alert">{state.error}</div>}
    <p className="handsfree-note">Questions send automatically in native hands-free mode. Stop or leaving this page releases the microphone. Choose browser audio explicitly to use Hold to talk and review your words before sending.</p>
    <p className="handsfree-note">Native audio uses echo-processed, sustained speech to detect an interruption and stop the old reply. Keep speaking naturally; transcription follows after you pause. Headphones or moving the microphone away from airflow can improve recognition.</p>
  </section>;
}
