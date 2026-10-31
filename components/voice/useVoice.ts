"use client";
import { useEffect, useRef, useState } from "react";
import { LocalRecognitionController, transcribeLocally } from "@/lib/voice/local-recognition";
import { BrowserVoiceCapture } from "@/lib/voice/capture";
import { NativeSpeechController, NativeVoiceRegistry, AUDIO_ENGINE_KEY, type AudioEngine, type NativePlaybackContext } from "@/lib/voice/native-speech";
import { fetchVoiceConfig, type VoiceConfig } from "@/lib/voice/realtime-client";
import { SpeechController } from "@/lib/voice/speech";
import { VoiceRegistry, AUTO_KEY, saved, save, type VoiceState } from "@/lib/voice/voices";
import { EMPTY_SPEECH, type RecognitionState, type SpeechState } from "@/lib/voice/types";

import {expressionRates, type Expression} from "@/lib/memory-types";

export function useVoice(stopMedia: () => void, onManual: () => void = () => {}) {
  const manual = useRef(onManual); manual.current = onManual;
  const registry = useRef<VoiceRegistry | NativeVoiceRegistry | null>(null);
  const speech = useRef<SpeechController | NativeSpeechController | null>(null);
  const recognition = useRef<LocalRecognitionController | null>(null);
  const selected = useRef("");
  const [engine, setEngine] = useState<AudioEngine>('native');
  const engineRef = useRef<AudioEngine>('native'); engineRef.current = engine;
  const owner = useRef('');
  const [ownerId, setOwnerId] = useState('');
  const [audioStatus, setAudioStatus] = useState<VoiceConfig>({ state: 'checking', message: 'Checking native Mac audio…' });
  const mounted = useRef(false);
  const audioCheck = useRef(0);
  async function refreshAudio() {
    const check = ++audioCheck.current;
    try {
      const data = await fetchVoiceConfig(AbortSignal.timeout(12000));
      if (mounted.current && check === audioCheck.current) setAudioStatus(data);
    } catch { if (mounted.current && check === audioCheck.current) setAudioStatus({ state: 'error', message: 'Native Mac audio is unavailable. Refresh audio or choose browser audio explicitly.' }); }
  }
  const enabled = useRef(true);
  const rate = useRef(.98);
  const storage = useRef<Storage | undefined>(undefined);
  const [choices, setChoices] = useState<VoiceState>({ options: [], selected: "", message: "Loading native Mac voices…" });
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
  const [browserSupport, setBrowserSupport] = useState({ recognition: false, speech: false, checked: false });
  const activity = useRef(0);
  useEffect(() => {
    mounted.current = true;
    owner.current = crypto.randomUUID(); setOwnerId(owner.current);
    try { storage.current = window.localStorage; } catch {}
    const preference = saved(storage.current, AUDIO_ENGINE_KEY, 'native');
    if (preference === 'browser') setEngine('browser');
    void refreshAudio();
    enabled.current = saved(storage.current, AUTO_KEY, "true") !== "false"; setSpeakReplies(enabled.current);
    const captureSupported = !!navigator.mediaDevices?.getUserMedia && !!window.AudioContext && !!window.AudioWorkletNode && !!window.OfflineAudioContext;
    void refreshSpeech();
    const synth = window.speechSynthesis;
    const supportedSpeech = !!synth && !!window.SpeechSynthesisUtterance;
    setBrowserSupport({ recognition: captureSupported, speech: supportedSpeech, checked: true });
    recognition.current = new LocalRecognitionController(() => new BrowserVoiceCapture(level), transcribeLocally, setRecognitionState);
    const stop = () => { recognition.current?.cancel(); speech.current?.stop('page-hidden-or-unloaded'); };
    const hide = () => { if (document.hidden) stop(); };
    window.addEventListener("pagehide", stop); document.addEventListener("visibilitychange", hide);
    return () => {
      mounted.current = false; audioCheck.current++; recognition.current?.dispose();
      recognition.current = null;
      window.removeEventListener("pagehide", stop); document.removeEventListener("visibilitychange", hide);
    };
  }, []);
  useEffect(() => {
    recognition.current?.cancel(); selected.current = '';
    setChoices({ options: [], selected: '', message: engine === 'native' ? 'Loading native Mac voices…' : 'Loading browser voices…' });
    const notify = (state: VoiceState) => { selected.current = state.selected; setChoices(state); };
    if (engine === 'native') {
      registry.current = new NativeVoiceRegistry(storage.current, notify);
      speech.current = new NativeSpeechController(setSpeechState, activity, fetch, owner.current);
      void registry.current.refresh();
    } else if (window.speechSynthesis && window.SpeechSynthesisUtterance) {
      registry.current = new VoiceRegistry(window.speechSynthesis, storage.current, notify);
      speech.current = new SpeechController(window.speechSynthesis, window.SpeechSynthesisUtterance, setSpeechState, activity,
        event => console.debug('[June voice]', JSON.stringify(event)));
    } else { selected.current = ''; setChoices({ options: [], selected: '', message: 'Speech playback is unavailable in this browser. Replies remain readable.' }); }
    speech.current?.setRate(rate.current);
    return () => { speech.current?.dispose(); registry.current?.dispose(); speech.current = null; registry.current = null; };
  }, [engine]);
  useEffect(() => {
    if (audioStatus.state !== 'preparing') return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => { await refreshAudio(); if (!cancelled) timer = setTimeout(poll, 2000); };
    timer = setTimeout(poll, 2000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [audioStatus.state]);
  const support = engine === 'native'
    ? { recognition: audioStatus.nativeReady === true, speech: audioStatus.nativeReady === true, checked: audioStatus.state !== 'checking' }
    : browserSupport;
  const cancel = (reset = false) => { recognition.current?.cancel(reset); speech.current?.stop(); };
  const getVoice = () => registry.current?.get(selected.current);
  return {
    setExpression: (expression:Expression) => { rate.current = expressionRates[expression]; speech.current?.setRate(rate.current); },
    engine, ownerId, audioStatus, refreshAudio,
    chooseEngine: (value: AudioEngine) => {
      if (value !== 'native' && value !== 'browser') return;
      manual.current(); recognition.current?.cancel(); speech.current?.stop('audio-engine-changed'); stopMedia();
      save(storage.current, AUDIO_ENGINE_KEY, value); setEngine(value);
    },
    choices, speech: speechState, recognition: recognitionState, support, speakReplies, engineStatus, refreshSpeech, activity, level,
    cancel, stopVoice: (reason = 'stop-voice') => speech.current?.stop(reason), finishTalk: () => recognition.current?.finish(),
    pauseForInput: () => speech.current?.pauseForInput() ?? false,
    resumeAfterInput: () => speech.current?.resumeAfterInput(),
    startTalk: () => { if (engineRef.current !== 'browser') return; manual.current(); speech.current?.stop(); stopMedia(); recognition.current?.start(); },
    setTranscript: (transcript: string) => recognition.current?.edit(transcript),
    clearTranscript: () => { recognition.current?.cancel(true); },
    chooseVoice: (id: string) => { manual.current(); recognition.current?.cancel(); speech.current?.stop(); registry.current?.choose(id); },
    refresh: () => { void registry.current?.refresh(); void refreshAudio(); },
    setSpeakReplies: (value: boolean) => { if (!value) manual.current(); enabled.current = value; setSpeakReplies(value); save(storage.current, AUTO_KEY, String(value)); if (!value) speech.current?.stop(); },
    preview: () => { manual.current(); recognition.current?.cancel(); stopMedia(); speech.current?.replay("Hi, I’m June. Let’s take the next step together.", getVoice()); },
    replay: (text: string) => { manual.current(); recognition.current?.cancel(); stopMedia(); speech.current?.replay(text, getVoice()); },
    begin: (id: number, handsFree = false, context?: NativePlaybackContext) => {
      recognition.current?.cancel(); stopMedia();
      if (speech.current instanceof NativeSpeechController) speech.current.begin(id, getVoice(), enabled.current, handsFree, context);
      else speech.current?.begin(id, getVoice(), enabled.current, handsFree);
    },
    push: (id: number, text: string) => speech.current?.push(id, text),
    finish: (id: number, flushTail = true) => speech.current?.finish(id, flushTail),
  };
}
export type VoiceControls = ReturnType<typeof useVoice>;
