"use client";
import { useId, useRef, useState } from "react";
import type { AudioControls } from "./useAudio";

export default function AudioPanel({ audio, onActivate, disableCapture = false }: { audio: AudioControls; onActivate: () => void; disableCapture?: boolean }) {
  const id = useId();
  const [file, setFile] = useState<File>();
  const input = useRef<HTMLInputElement>(null);
  const phaseText = { idle: "Audio off", playing: "Audio playing", paused: "Audio paused", requesting: "Waiting for microphone permission…", listening: "Microphone active · sound only" }[audio.phase];
  return <div className="audio-panel">
    <div className="audio-panel-heading"><strong>Let June move with sound</strong><span role="status">{phaseText}</span></div>
    <p>Play a sample, choose a file, or use your microphone. Sound stays in this browser; words are not transcribed.</p>
    <div className="audio-source"><span>{file ? file.name : "June tones · original 18-second sample"}</span>
      <label className="quiet-button file-button" htmlFor={id}>Choose audio file<input ref={input} id={id} type="file" accept="audio/*" onChange={event => {
        const selected = event.target.files?.[0]; if (selected) { audio.stop(); setFile(selected); onActivate(); }
      }} /></label>
      {file && <button className="quiet-button" onClick={() => { audio.stop(); setFile(undefined); if (input.current) input.current.value = ""; }}>Use sample</button>}
    </div>
    <div className="audio-buttons">
      <button className="quiet-button" disabled={audio.phase === "playing"} onClick={() => { onActivate(); void audio.play(file); }}>{audio.phase === "paused" ? "Resume audio" : "Play audio"}</button>
      <button className="quiet-button" disabled={audio.phase !== "playing"} onClick={audio.pause}>Pause audio</button>
      <button className="quiet-button" disabled={audio.phase === "idle"} onClick={audio.stop}>Stop audio</button>
      {audio.phase === "listening" || audio.phase === "requesting"
        ? <button className="quiet-button mic-active" onClick={audio.stop}>{audio.phase === "requesting" ? "Cancel microphone" : "Stop microphone"}</button>
        : <button className="quiet-button" disabled={disableCapture} onClick={() => { onActivate(); void audio.microphone(); }}>Start microphone</button>}
    </div>
    {audio.error && <p className="error-notice" role="alert">{audio.error}</p>}
  </div>;
}
