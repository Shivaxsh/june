"use client";
import { useId } from "react";
import type { VoiceControls } from "./useVoice";
export default function VoicePanel({ voice, busy = false, onUse, onActivate }: { voice: VoiceControls; busy?: boolean; onUse: (text: string) => void; onActivate: () => void }) {
  const id = useId();
  const phase = voice.recognition.phase;
  const active = phase !== "idle";
  const blocked = busy || !voice.support.recognition;
  const status = { idle: "Ready for a voice request", requesting: "Requesting speech access…", listening: "Listening · release to review", finishing: "Finishing your transcript…" }[phase];
  const start = () => { onActivate(); voice.startTalk(); };
  return <section className="voice-panel" aria-label="June voice controls">
    <div className="voice-heading"><strong>A conversation you can hear</strong><label className="motion-option"><input type="checkbox" checked={voice.speakReplies} disabled={!voice.support.speech} onChange={event => voice.setSpeakReplies(event.target.checked)} /> Speak replies</label></div>
    <div className="voice-settings"><label htmlFor={`${id}-voice`}>June’s voice<select id={`${id}-voice`} value={voice.choices.selected} disabled={!voice.choices.options.length} onChange={event => voice.chooseVoice(event.target.value)}>{!voice.choices.options.length && <option value="">No local female voice ready</option>}{voice.choices.options.map(option => <option key={option.id} value={option.id}>{option.name} · {option.accent}</option>)}</select></label><button className="quiet-button" disabled={busy || !voice.choices.selected} onClick={() => { onActivate(); voice.preview(); }}>Preview voice</button><button className="quiet-button" disabled={!voice.support.speech} onClick={voice.refresh}>Refresh voices</button><button className="quiet-button" disabled={voice.speech.phase === "idle"} onClick={voice.stopVoice}>Stop voice</button></div>
    <p className="voice-description">{voice.choices.message}</p>
    <p className="recognition-notice">Browser speech recognition may send your microphone audio to its online speech service. Hold to talk starts it deliberately. Review the words before sending them to June.</p>
    <div className="talk-controls"><button className={`talk-button ${phase === "listening" ? "is-listening" : ""}`} disabled={blocked} onPointerDown={event => {
      if (event.button !== 0) return; event.currentTarget.setPointerCapture(event.pointerId); start();
    }} onPointerUp={voice.finishTalk} onPointerCancel={() => voice.cancel()} onLostPointerCapture={voice.finishTalk} onKeyDown={event => {
      if ([" ", "Enter"].includes(event.key)) { event.preventDefault(); if (!event.repeat) start(); }
    }} onKeyUp={event => { if ([" ", "Enter"].includes(event.key)) { event.preventDefault(); voice.finishTalk(); } }} onBlur={voice.finishTalk}>Hold to talk</button>
      <button className="quiet-button" disabled={blocked} onClick={() => { if (active) voice.finishTalk(); else start(); }}>{active ? "Finish listening" : "Start listening"}</button>
      {active && <button className="quiet-button" onClick={() => voice.cancel()}>Cancel listening</button>}
      <label className="recognition-language" htmlFor={`${id}-language`}>Recognition language<select id={`${id}-language`} value={voice.language} disabled={active || busy} onChange={event => voice.setLanguage(event.target.value)}><option value="en-IN">Indian English</option><option value="en-US">American English</option><option value="en-GB">British English</option></select></label>
    </div>
    <p className="voice-status" role="status">{!voice.support.checked ? "Checking browser speech support…" : !voice.support.recognition ? "Speech recognition is unavailable here. Open June in a supported browser, or keep typing." : status}</p>
    {(voice.recognition.transcript || active) && <div className="transcript-review"><label htmlFor={`${id}-transcript`}>Review your words</label><textarea id={`${id}-transcript`} rows={3} value={voice.recognition.transcript} disabled={active} onChange={event => voice.setTranscript(event.target.value)} /><div><button className="quiet-button" disabled={active || busy || !voice.recognition.transcript.trim()} onClick={() => onUse(voice.recognition.transcript)}>Use transcript</button><button className="quiet-button" disabled={active} onClick={voice.clearTranscript}>Clear transcript</button></div><p>Use transcript adds these words to your message. Send when you’re ready.</p></div>}
    {voice.speech.phase === "speaking" && <div className="speech-captions" aria-label="Spoken reply captions"><p>{voice.speech.caption.slice(0, voice.speech.start)}<mark>{voice.speech.caption.slice(voice.speech.start, voice.speech.end)}</mark>{voice.speech.caption.slice(voice.speech.end)}</p><small>{voice.speech.approximate ? "Caption timing is approximate" : "Caption timing follows browser word events"} · orb movement is a visual approximation</small></div>}
    {(voice.recognition.error || voice.speech.error) && <div className="error-notice" role="alert">{voice.recognition.error && <p>{voice.recognition.error}</p>}{voice.speech.error && <p>{voice.speech.error}</p>}</div>}
  </section>;
}
