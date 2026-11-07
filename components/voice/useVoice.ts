"use client";
import { useEffect, useRef, useState } from "react";
import { LocalRecognitionController, transcribeLocally } from "@/lib/voice/local-recognition";
import { BrowserVoiceCapture } from "@/lib/voice/capture";
import { NativeSpeechController, NativeVoiceRegistry, JUNE_VOICE_OPTION, type NativeVoiceState, type NativePlaybackContext, type AudioEngine } from "@/lib/voice/native-speech";
import { fetchVoiceConfig, type VoiceConfig } from "@/lib/voice/realtime-client";
import { AUTO_KEY, saved, save } from "@/lib/voice/voices";
import { EMPTY_SPEECH, type RecognitionState, type SpeechState } from "@/lib/voice/types";

import {expressionRates, type Expression} from "@/lib/memory-types";

export function useVoice(stopMedia: () => void, onManual: () => void = () => {}) {
  const manual = useRef(onManual); manual.current = onManual;
  const registry = useRef<NativeVoiceRegistry | null>(null);
  const speech = useRef<NativeSpeechController | null>(null);
  const recognition = useRef<LocalRecognitionController | null>(null);
  const selected = useRef("");
  const engine = 'native' as AudioEngine;
  const [browserCapture, setBrowserCapture] = useState(false);
  const browserCaptureRef = useRef(false);
  const owner = useRef('');
  const [ownerId, setOwnerId] = useState('');
  const [audioStatus, setAudioStatus] = useState<VoiceConfig>({ state: 'checking', message: 'Checking June’s voice and native audio…' });
  const audioStatusRef = useRef(audioStatus);
  const mounted = useRef(false);
  const audioCheck = useRef(0);
  async function refreshAudio() {
    const check = ++audioCheck.current;
    try {
      const data = await fetchVoiceConfig(AbortSignal.timeout(12000));
      if (mounted.current && check === audioCheck.current) {
        audioStatusRef.current = data; setAudioStatus(data);
        if (data.providerState !== 'ready' || data.nativeReady !== true) speech.current?.stop('provider-unavailable');
      }
    } catch {
      if (mounted.current && check === audioCheck.current) {
        const status = { state: 'error', providerState: 'error' as const, message: 'June’s voice is unavailable. Refresh audio; replies remain readable.' };
        audioStatusRef.current = status; setAudioStatus(status); speech.current?.stop('provider-unavailable');
      }
    }
  }
  const enabled = useRef(true);
  const rate = useRef(.98);
  const storage = useRef<Storage | undefined>(undefined);
  const [choices, setChoices] = useState<NativeVoiceState>({ options: [{ ...JUNE_VOICE_OPTION }], selected: "", state: "checking", message: "Checking June’s local Heart voice…" });
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
  const [browserCaptureSupported, setBrowserCaptureSupported] = useState(false);
  const activity = useRef(0);
  useEffect(() => {
    mounted.current = true;
    owner.current = crypto.randomUUID(); setOwnerId(owner.current);
    try { storage.current = window.localStorage; } catch {}
    void refreshAudio();
    enabled.current = saved(storage.current, AUTO_KEY, "true") !== "false"; setSpeakReplies(enabled.current);
    const captureSupported = !!navigator.mediaDevices?.getUserMedia && !!window.AudioContext && !!window.AudioWorkletNode && !!window.OfflineAudioContext;
    void refreshSpeech();
    setBrowserCaptureSupported(captureSupported);
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
    const notify = (state: NativeVoiceState) => {
      selected.current = state.selected; setChoices(state);
      if (state.state !== 'ready') speech.current?.stop('provider-unavailable');
    };
    registry.current = new NativeVoiceRegistry(storage.current, notify);
    speech.current = new NativeSpeechController(setSpeechState, activity, fetch, owner.current);
    speech.current.setRate(rate.current);
    void registry.current.refresh();
    return () => { speech.current?.dispose(); registry.current?.dispose(); speech.current = null; registry.current = null; };
  }, []);
  useEffect(() => {
    if (audioStatus.state !== 'preparing') return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => { await refreshAudio(); if (!cancelled) timer = setTimeout(poll, 2000); };
    timer = setTimeout(poll, 2000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [audioStatus.state]);
  const outputReady = audioStatus.nativeReady === true && audioStatus.providerState === 'ready' && choices.state === 'ready';
  const support = {
    // Native hands-free requires both capture and June’s local output.
    recognition: outputReady && audioStatus.state === 'ready',
    speech: outputReady,
    checked: audioStatus.state !== 'checking' && choices.state !== 'checking',
  };
  const cancel = (reset = false) => { recognition.current?.cancel(reset); speech.current?.stop(); };
  const getVoice = () => audioStatusRef.current.nativeReady === true && audioStatusRef.current.providerState === 'ready'
    ? registry.current?.get(selected.current) : undefined;
  return {
    setExpression: (expression:Expression) => { rate.current = expressionRates[expression]; speech.current?.setRate(rate.current); },
    engine, ownerId, audioStatus, refreshAudio,
    browserCapture, browserCaptureSupported,
    setBrowserCapture: (value: boolean) => {
      manual.current(); recognition.current?.cancel(); speech.current?.stop('capture-mode-changed'); stopMedia();
      browserCaptureRef.current = value; setBrowserCapture(value);
    },
    choices: { ...choices, selected: outputReady ? choices.selected : '' }, speech: speechState, recognition: recognitionState, support, speakReplies, engineStatus, refreshSpeech, activity, level,
    cancel, stopVoice: (reason = 'stop-voice') => speech.current?.stop(reason), finishTalk: () => recognition.current?.finish(),
    pauseForInput: () => speech.current?.pauseForInput() ?? false,
    resumeAfterInput: () => speech.current?.resumeAfterInput(),
    startTalk: () => { if (!browserCaptureRef.current) return; manual.current(); speech.current?.stop(); stopMedia(); recognition.current?.start(); },
    setTranscript: (transcript: string) => recognition.current?.edit(transcript),
    clearTranscript: () => { recognition.current?.cancel(true); },
    refresh: () => { void registry.current?.refresh(); void refreshAudio(); },
    setSpeakReplies: (value: boolean) => { if (!value) manual.current(); enabled.current = value; setSpeakReplies(value); save(storage.current, AUTO_KEY, String(value)); if (!value) speech.current?.stop(); },
    preview: () => { manual.current(); recognition.current?.cancel(); stopMedia(); speech.current?.replay("Hi, I’m June. Let’s take the next step together.", getVoice()); },
    replay: (text: string) => { manual.current(); recognition.current?.cancel(); stopMedia(); speech.current?.replay(text, getVoice()); },
    begin: (id: number, handsFree = false, context?: NativePlaybackContext) => {
      recognition.current?.cancel(); stopMedia();
      speech.current?.begin(id, getVoice(), enabled.current, handsFree, context);
    },
    push: (id: number, text: string) => speech.current?.push(id, text),
    finish: (id: number, flushTail = true) => speech.current?.finish(id, flushTail),
  };
}
export type VoiceControls = ReturnType<typeof useVoice>;
