"use client";
import { useEffect, useRef, useState } from "react";
import VoicePanel from "./voice/VoicePanel";
import { useVoice } from "./voice/useVoice";
import { useAudio } from "./orb/useAudio";
import Orb from "./orb/Orb";
import { resolveOrb } from "@/lib/orb/state";
const topics = ["Web Speech API", "Speech to text", "Text to speech", "Sentence streaming", "Orb and captions", "Female voice selection"];
const explanations = [
  "Web Speech includes browser recognition and synthesis. June uses synthesis for its local female voice, but replaces the unreliable browser recognition service with direct recording and local Whisper. Typing works independently.",
  "Hold the button, say a short sentence, release it, then inspect and edit the words. June records in the browser and transcribes locally with Whisper base.en after you stop. The reviewed text is what your local model receives.",
  "Your model writes the answer; a speech engine gives it a voice. Preview a known female English system voice and listen to its actual accent. Installed voice quality varies.",
  "The model sends text in small pieces. June buffers complete sentences and queues them in order. The final unfinished sentence is flushed when generation succeeds. Stop voice discards the queue immediately.",
  "The orb follows actual listening and speech playback events. Word events drive caption highlighting when available. Timed movement is labelled as an approximation because system speech exposes no waveform to measure.",
  "Voice lists may be empty at first. June waits for voiceschanged, filters known female English identities from local services, restores your saved choice, and labels its actual accent. No unknown default voice is substituted.",
];
const snippets = [
  'const synth = window.speechSynthesis;\n// Browser recognition services can fail independently of the microphone.\n// June uses direct microphone recording plus local Whisper instead.',
  'const stream = await navigator.mediaDevices.getUserMedia({ audio: true });\n// AudioWorklet captures samples; OfflineAudioContext resamples to 16 kHz.\n// Release stops capture and POSTs a WAV to /api/speech/transcribe.\n// Local Whisper returns words for editing before Send.',
  'const utterance = new SpeechSynthesisUtterance(text);\nutterance.voice = selectedLocalFemaleVoice;\nutterance.rate = 0.98;\nutterance.pitch = 1;\nspeechSynthesis.speak(utterance);',
  'onText(delta) { queue.push(...sentences.push(delta)); }\nonComplete() { queue.push(...sentences.finish()); }\nonStop() { requestId++; queue.length = 0; synth.cancel(); }\n// Old callbacks check their request ID before doing anything.',
  'utterance.onstart = () => setSpeaking(true);\nutterance.onboundary = event => highlight(event.charIndex);\nutterance.onend = () => setSpeaking(false);\n// Approximate animation is never displayed as measured volume.',
  'synth.addEventListener("voiceschanged", refreshVoices);\nconst voices = synth.getVoices().filter(isKnownLocalFemaleEnglish);\n// Prefer en-IN; otherwise label the actual fallback accent.\n// Persist only the voice preference, not conversations.',
];
export default function PhaseThree() {
  const [topic, setTopic] = useState(0);
  const [review, setReview] = useState("");
  const [streamText, setStreamText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [still, setStill] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const counter = useRef(0);
  const audio = useAudio(); const voice = useVoice(audio.stop);
  const activity = { listening: voice.recognition.phase === "listening", speaking: voice.speech.phase === "speaking", requesting: voice.recognition.phase === "requesting", finishing: voice.recognition.phase === "finishing" };
  const orb = resolveOrb(false, false, "auto", audio.phase, activity);
  const stopDemo = () => { clearInterval(timer.current); counter.current++; setStreaming(false); };
  const stop = () => { stopDemo(); voice.cancel(); };
  useEffect(() => { const hide = () => { if (document.hidden) { clearInterval(timer.current); counter.current++; setStreaming(false); } }; document.addEventListener("visibilitychange", hide); return () => { clearInterval(timer.current); document.removeEventListener("visibilitychange", hide); }; }, []);
  function choose(index: number) { stop(); voice.clearTranscript(); setTopic(index); }
  function streamDemo() {
    stop(); const id = ++counter.current; voice.begin(id); setStreamText(""); setStreaming(true);
    const chunks = ["Hello. ", "I’m June. ", "This is demonstration text, ", "arriving in small pieces. ", "I read complete sentences ", "while the remaining text arrives. ", "Stop voice cancels the speaking queue."];
    let index = 0;
    timer.current = setInterval(() => {
      if (counter.current !== id) return;
      const chunk = chunks[index++]; setStreamText(previous => previous + chunk); voice.push(id, chunk);
      if (index === chunks.length) { clearInterval(timer.current); setStreaming(false); voice.finish(id); }
    }, 650);
  }
  return <div className="learn-page"><header className="masthead"><a className="wordmark" href="/">← june</a><span className="version">June v0.3.1 · Learning studio</span></header><main><p className="eyebrow">Phase 3 · Words, listening and a voice</p><h1>A little voice.<br />A little more <em>June.</em></h1><p className="learn-intro">Explore the six workbook topics. Speech processing, the model’s answer and spoken playback each have a different job.</p><nav className="topic-nav" aria-label="Phase 3 topics">{topics.map((name, i) => <button key={name} aria-current={topic === i ? "step" : undefined} onClick={() => choose(i)}><span>3.{i + 1}</span>{name}</button>)}</nav><section className="lesson-panel" aria-labelledby="voice-topic"><p className="eyebrow">Explore · 3.{topic + 1}</p><h2 id="voice-topic">{topics[topic]}</h2><p>{explanations[topic]}</p><div className="lesson-orb"><Orb mood={orb.mood} label={orb.label} level={voice.recognition.phase === "listening" ? voice.level : audio.level} activity={voice.activity} speechActive={voice.speech.phase === "speaking"} still={still} /><label className="motion-option"><input type="checkbox" checked={still} onChange={event => setStill(event.target.checked)} /> Still view</label></div><VoicePanel voice={voice} onUse={text => { setReview(text); voice.clearTranscript(); }} onActivate={stopDemo} />
    {review && <div className="speech-captions"><strong>Reviewed demonstration transcript</strong><p>{review}</p><small>This learning example does not send text to a model. Return to chat to send a real request.</small></div>}
    {topic === 3 && <div className="stream-example"><button className="quiet-button" disabled={streaming || !voice.choices.selected} onClick={streamDemo}>Stream demonstration text</button><button className="quiet-button" onClick={stop}>Stop demonstration</button><p>{streamText || "Demonstration text will appear here. This example does not call the model."}</p></div>}
    <pre><code>{snippets[topic]}</code></pre><p className="lesson-note">June uses local Whisper base.en for English recognition and a local system synthesis voice. Hosted speech services such as Deepgram, ElevenLabs and Cartesia are optional later integrations and may charge fees. No paid service is configured. Transcription starts when recording stops.</p><div className="lesson-footer"><span>{topic + 1} / 6 · In the same order as your workbook</span>{topic < 5 && <button className="quiet-button" onClick={() => choose(topic + 1)}>Next: {topics[topic + 1]} →</button>}</div></section><p className="learning-footer"><a href="/">← Back to June</a> · <a href="/learn/phase-2">Phase 2 studio</a> · Exploring does not mark learning topics complete.</p></main></div>;
}
