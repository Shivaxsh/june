"use client";
import { useEffect, useRef, useState } from "react";
import { LocalRecognitionController, transcribeLocally } from "@/lib/voice/local-recognition";
import { BrowserVoiceCapture } from "@/lib/voice/capture";
import { SpeechController } from "@/lib/voice/speech";
import { VoiceRegistry, AUTO_KEY, saved, save, type VoiceState } from "@/lib/voice/voices";
import { EMPTY_SPEECH, type RecognitionState, type SpeechState } from "@/lib/voice/types";

export function useVoice(stopMedia: () => void, onManual: () => void = () => {}) {
  const manual = useRef(onManual); manual.current = onManual;
  const registry = useRef<VoiceRegistry | null>(null);
  const speech = useRef<SpeechController | null>(null);
  const recognition = useRef<LocalRecognitionController | null>(null);
  const selected = useRef("");
  const enabled = useRef(true);
  const storage = useRef<Storage | undefined>(undefined);
  const [choices, setChoices] = useState<VoiceState>({ options: [], selected: "", message: "Loading browser voices…" });
  const [speechState, setSpeechState] = useState<SpeechState>({ ...EMPTY_SPEECH });
  const [recognitionState, setRecognitionState] = useState<RecognitionState>({ phase: "idle", transcript: "", error: "" });
  const [speakReplies, setSpeakReplies] = useState(true);
  const level = useRef(0);
  const [engineStatus, setEngineStatus] = useState({ state: "checking", message: "Checking local speech…" });
  async function refreshSpeech() {
    try {
      const response = await fetch("/api/speech/status", { cache: "no-store", signal: AbortSignal.timeout(5000) });
      const result = await response.json();
      if (!response.ok || !["ready", "runtime-missing", "model-missing", "error"].includes(result.state) || typeof result.message !== "string") throw new Error();
      setEngineStatus(result);
    } catch { setEngineStatus({ state: "error", message: "June’s speech server is unavailable. Restart June, then refresh speech." }); }
  }
  const [support, setSupport] = useState({ recognition: false, speech: false, checked: false });
  const activity = useRef(0);
  useEffect(() => {
    try { storage.current = window.localStorage; } catch {}
    enabled.current = saved(storage.current, AUTO_KEY, "true") !== "false"; setSpeakReplies(enabled.current);
    const captureSupported = !!navigator.mediaDevices?.getUserMedia && !!window.AudioContext && !!window.AudioWorkletNode && !!window.OfflineAudioContext;
    void refreshSpeech();
    const synth = window.speechSynthesis;
    const supportedSpeech = !!synth && !!window.SpeechSynthesisUtterance;
    setSupport({ recognition: captureSupported, speech: supportedSpeech, checked: true });
    recognition.current = new LocalRecognitionController(() => new BrowserVoiceCapture(level), transcribeLocally, setRecognitionState);
    if (supportedSpeech) {
      registry.current = new VoiceRegistry(synth, storage.current, state => { selected.current = state.selected; setChoices(state); });
      speech.current = new SpeechController(synth, window.SpeechSynthesisUtterance, setSpeechState, activity);
    } else setChoices({ options: [], selected: "", message: "Speech playback is unavailable in this browser. Replies remain readable." });
    const stop = () => { recognition.current?.cancel(); speech.current?.stop(); };
    const hide = () => { if (document.hidden) stop(); };
    window.addEventListener("pagehide", stop); document.addEventListener("visibilitychange", hide);
    return () => {
      recognition.current?.dispose(); speech.current?.dispose(); registry.current?.dispose();
      recognition.current = null; speech.current = null; registry.current = null;
      window.removeEventListener("pagehide", stop); document.removeEventListener("visibilitychange", hide);
    };
  }, []);
  const cancel = (reset = false) => { recognition.current?.cancel(reset); speech.current?.stop(); };
  const getVoice = () => registry.current?.get(selected.current);
  return {
    choices, speech: speechState, recognition: recognitionState, support, speakReplies, engineStatus, refreshSpeech, activity, level,
    cancel, stopVoice: () => speech.current?.stop(), finishTalk: () => recognition.current?.finish(),
    pauseForInput: () => speech.current?.pauseForInput() ?? false,
    resumeAfterInput: () => speech.current?.resumeAfterInput(),
    startTalk: () => { manual.current(); speech.current?.stop(); stopMedia(); recognition.current?.start(); },
    setTranscript: (transcript: string) => recognition.current?.edit(transcript),
    clearTranscript: () => { recognition.current?.cancel(true); },
    chooseVoice: (id: string) => { manual.current(); recognition.current?.cancel(); speech.current?.stop(); registry.current?.choose(id); },
    refresh: () => registry.current?.refresh(),
    setSpeakReplies: (value: boolean) => { if (!value) manual.current(); enabled.current = value; setSpeakReplies(value); save(storage.current, AUTO_KEY, String(value)); if (!value) speech.current?.stop(); },
    preview: () => { manual.current(); recognition.current?.cancel(); stopMedia(); speech.current?.replay("Hi Shivansh, I’m June. Let’s take the next step together.", getVoice()); },
    replay: (text: string) => { manual.current(); recognition.current?.cancel(); stopMedia(); speech.current?.replay(text, getVoice()); },
    begin: (id: number, handsFree = false) => { recognition.current?.cancel(); stopMedia(); speech.current?.begin(id, getVoice(), enabled.current, handsFree); },
    push: (id: number, text: string) => speech.current?.push(id, text),
    finish: (id: number, flushTail = true) => speech.current?.finish(id, flushTail),
  };
}
export type VoiceControls = ReturnType<typeof useVoice>;
