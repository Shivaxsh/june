"use client";
import { useEffect, useId, useRef } from "react";
import TimingReadout from "./TimingReadout";
import type { VoiceControls } from "./useVoice";
export default function VoicePanel({ voice, busy = false, onUse, onActivate }: { voice: VoiceControls; busy?: boolean; onUse: (text: string) => void; onActivate: () => void }) {
  const id = useId();
  const phase = voice.recognition.phase;
  const active = phase !== "idle";
  const blocked = !voice.browserCapture || busy || !voice.browserCaptureSupported || voice.engineStatus.state !== "ready";
  const transcribing = phase === "finishing";
  const meter = useRef<HTMLMeterElement>(null);
  const reading = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const update = () => { if (meter.current) meter.current.value = voice.level.current; if (reading.current) reading.current.textContent = `${Math.round(voice.level.current * 100)}%`; };
    const timer = setInterval(update, 100); update(); return () => clearInterval(timer);
  }, [voice.level]);
  const status = { idle: "Ready for a voice request", requesting: "Requesting microphone…", listening: "Listening · release to transcribe", finishing: "Transcribing on this Mac…" }[phase];
  const start = () => { onActivate(); voice.startTalk(); };
  return <section className="voice-panel" aria-label="June voice controls">
    <div className="voice-heading"><strong>A conversation you can hear</strong><label className="motion-option"><input type="checkbox" checked={voice.speakReplies} onChange={event => voice.setSpeakReplies(event.target.checked)} /> Speak replies</label></div>
    <div className="voice-settings"><p><strong>June</strong> · ElevenLabs · English · native playback</p><button className="quiet-button" disabled={busy || !voice.support.speech} onClick={() => { onActivate(); voice.preview(); }}>Preview voice</button><button className="quiet-button" disabled={busy} onClick={voice.refresh}>Refresh audio</button><button className="quiet-button" disabled={voice.speech.phase === "idle"} onClick={() => voice.stopVoice()}>Stop voice</button></div>
    <p className="voice-description" role="status">{voice.choices.message}</p>
    <p className="voice-description" role="status">{voice.audioStatus.providerMessage || voice.audioStatus.message}</p>
    <p className="recognition-notice">June’s voice uses ElevenLabs cloud speech and consumes credits. Reply text, including personal replies, is sent online to ElevenLabs for speech. Raw microphone audio stays on this Mac for local transcription.</p>
    <p className="voice-description">{quotaNotice(voice.audioStatus.quota)} The account allowance may exceed the separately restricted API-key limit.</p>
    <label className="motion-option"><input type="checkbox" checked={voice.browserCapture} disabled={busy || active || !voice.browserCaptureSupported} onChange={event => { onActivate(); voice.setBrowserCapture(event.target.checked); }} /> Use browser microphone for manual recording only</label>
    <p className="voice-description">Native hands-free uses this Mac’s microphone. Manual browser recording is capture only; June’s replies always use her ElevenLabs voice through native playback.</p>
    <p className="recognition-notice">Local English transcription · Whisper base.en. Your recording is processed only on this Mac, then deleted. Stop listening to transcribe; review the words before sending. Maximum 30 seconds.</p>
    <div className="talk-controls"><button className={`talk-button ${phase === "listening" ? "is-listening" : ""}`} disabled={blocked || transcribing} onPointerDown={event => {
      if (event.button !== 0) return; event.currentTarget.setPointerCapture(event.pointerId); start();
    }} onPointerUp={voice.finishTalk} onPointerCancel={() => voice.cancel()} onLostPointerCapture={voice.finishTalk} onKeyDown={event => {
      if ([" ", "Enter"].includes(event.key)) { event.preventDefault(); if (!event.repeat) start(); }
    }} onKeyUp={event => { if ([" ", "Enter"].includes(event.key)) { event.preventDefault(); voice.finishTalk(); } }} onBlur={voice.finishTalk}>Hold to talk</button>
      <button className="quiet-button" disabled={blocked || transcribing} onClick={() => { if (active) voice.finishTalk(); else start(); }}>{transcribing ? "Transcribing…" : active ? "Stop listening" : "Start listening"}</button>
      {active && <button className="quiet-button" onClick={() => voice.cancel()}>{transcribing ? "Cancel transcription" : "Cancel listening"}</button>}

    </div>
    <p className="voice-status" role="status">{!voice.support.checked ? "Checking audio recording support…" : !voice.browserCapture ? "Use native hands-free above, or enable manual browser recording here." : !voice.browserCaptureSupported ? "Microphone recording is unavailable here. Open June’s local address in a current browser, or keep typing." : voice.engineStatus.state !== "ready" ? voice.engineStatus.message : voice.recognition.transcript && !active ? "Transcript ready · review your words" : status}</p>
    <div className="speech-engine"><p>{voice.engineStatus.message}</p><button className="quiet-button" disabled={active || busy} onClick={() => void voice.refreshSpeech()}>Refresh speech</button></div>
    {phase === "listening" && <div className="recording-meter"><span>Microphone level</span><meter ref={meter} min="0" max="1" value="0" aria-label="Recording level" /><span ref={reading}>0%</span></div>}
    {(voice.recognition.transcript || active) && <div className="transcript-review"><label htmlFor={`${id}-transcript`}>Review your words</label><textarea id={`${id}-transcript`} rows={3} value={voice.recognition.transcript} disabled={active} onChange={event => voice.setTranscript(event.target.value)} /><div><button className="quiet-button" disabled={active || busy || !voice.recognition.transcript.trim()} onClick={() => onUse(voice.recognition.transcript)}>Use transcript</button><button className="quiet-button" disabled={active} onClick={voice.clearTranscript}>Clear transcript</button></div><p>Use transcript adds these words to your message. Send when you’re ready.</p></div>}
    {voice.speech.phase === "speaking" && <div className="speech-captions" aria-label="Spoken reply captions"><p>{voice.speech.caption.slice(0, voice.speech.start)}<mark>{voice.speech.caption.slice(voice.speech.start, voice.speech.end)}</mark>{voice.speech.caption.slice(voice.speech.end)}</p><small>Caption timing is approximate for native audio · orb follows measured playback audio</small></div>}
    <TimingReadout timings={voice.speech.timings} label="Observed playback timings" />
    {voice.speech.timings?.firstAudioMs !== undefined && <p className="handsfree-note">Request timings are observed in this page. Playback elapsed includes gaps between speech segments.</p>}
    {(voice.recognition.error || voice.speech.error) && <div className="error-notice" role="alert">{voice.recognition.error && <p>{voice.recognition.error}</p>}{voice.speech.error && <p>{voice.speech.error}</p>}</div>}
  </section>;
}

function quotaNotice(quota: VoiceControls['audioStatus']['quota']) {
  const credits = (value: number | null | undefined) => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value.toLocaleString('en-US') : undefined;
  const remaining = credits(quota?.remaining), limit = credits(quota?.limit), used = credits(quota?.used);
  const parts = [remaining !== undefined ? `${remaining} credits remaining` : '', limit !== undefined ? `${limit} credit limit` : '', used !== undefined ? `${used} credits used` : ''].filter(Boolean);
  if (quota?.resetAt != null) {
    const reset = new Date(typeof quota.resetAt === 'number' && quota.resetAt < 1e12 ? quota.resetAt * 1000 : quota.resetAt);
    if (Number.isFinite(reset.getTime())) parts.push(`resets ${reset.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}`);
  }
  return parts.length ? `ElevenLabs: ${parts.join(' · ')}.` : 'ElevenLabs credit balance is unavailable. Cloud speech still uses credits.';
}
