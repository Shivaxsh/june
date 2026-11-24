"use client";
import { onSustainedHide } from '../../lib/visibility';
import { alertOutputWarm, audioPhase, nextCheckDelay, outputUsable, recoveryMessage, shouldReloadVoices, type AudioPhase } from "@/lib/voice/audio-recovery";
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
  const audioRetry = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  async function refreshAudio(retry = true) {
    clearTimeout(audioRetry.current);
    const check = ++audioCheck.current;
    try {
      const data = await fetchVoiceConfig(AbortSignal.timeout(12000));
      if (mounted.current && check === audioCheck.current) {
        audioStatusRef.current = data; setAudioStatus(data);
        if (!outputUsable(data)) speech.current?.stop('provider-unavailable');
      }
    } catch {
      if (mounted.current && check === audioCheck.current) {
        if (retry) {
          audioRetry.current = setTimeout(() => {
            if (!mounted.current || check !== audioCheck.current) return;
            if (!selected.current) void registry.current?.refresh();
            void refreshAudio(false);
          }, 750);
          return;
        }
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
    const releaseHide = onSustainedHide(stop);
    window.addEventListener("pagehide", stop);
    return () => {
      mounted.current = false; audioCheck.current++; clearTimeout(audioRetry.current); recognition.current?.dispose();
      recognition.current = null;
      window.removeEventListener("pagehide", stop); releaseHide();
    };
  }, []);
  useEffect(() => {
    const notify = (state: NativeVoiceState) => {
      selected.current = state.selected; voicesReady.current = state.state === 'ready'; setChoices(state);
      if (state.state !== 'ready') speech.current?.stop('provider-unavailable');
    };
    registry.current = new NativeVoiceRegistry(storage.current, notify);
    speech.current = new NativeSpeechController(setSpeechState, activity, fetch, owner.current);
    speech.current.setRate(rate.current);
    void registry.current.refresh();
    return () => { speech.current?.dispose(); registry.current?.dispose(); speech.current = null; registry.current = null; };
  }, []);
  const recoveryAttempt = useRef(0);
  const voicesReady = useRef(false);
  const recoveryPhase = useRef<AudioPhase | undefined>(undefined);
  const [audioRecovery, setAudioRecovery] = useState<{ phase: AudioPhase; message: string }>({ phase: "preparing", message: "" });
  // Audio recovery: while audio is preparing or unavailable, one bounded, slowing status check at a
  // time; when it comes back, reload the voice list so no page reload is needed. Never opens the
  // microphone or replays speech; a broken Mac audio service still needs the person to restart it.
  useEffect(() => {
    const phase = audioPhase(audioStatus);
    const before = recoveryPhase.current; recoveryPhase.current = phase;
    if (phase !== before) recoveryAttempt.current = 0;
    // Reload only a list that failed: reloading a ready one would briefly disable speech.
    if (shouldReloadVoices(before, phase) && !voicesReady.current) void registry.current?.refresh();
    const delay = nextCheckDelay(phase, recoveryAttempt.current);
    setAudioRecovery({ phase, message: recoveryMessage({ phase, gaveUp: delay === null, delayMs: delay ?? 0, outputError: !!audioStatus.outputError }) });
    // Hidden pages skip the healthy check; becoming visible checks at once (below).
    if (delay === null || (phase === "ready" && document.hidden)) return;
    const timer = setTimeout(() => { recoveryAttempt.current++; lastCheck.current = Date.now(); void refreshAudio(false); }, delay);
    return () => clearTimeout(timer);
  }, [audioStatus]);
  // Event-driven checks: returning to the page, a device change, or a playback error re-checks status
  // at once (debounced). They only read status: no speech is replayed and the microphone stays off.
  const lastCheck = useRef(0);
  useEffect(() => {
    const check = () => {
      if (document.hidden) return;
      const now = Date.now();
      if (now - lastCheck.current < 2000) return;
      lastCheck.current = now; void refreshAudio(false);
    };
    const whenVisible = () => { if (!document.hidden) check(); };
    window.addEventListener("focus", check);
    document.addEventListener("visibilitychange", whenVisible);
    navigator.mediaDevices?.addEventListener?.("devicechange", check);
    return () => {
      window.removeEventListener("focus", check);
      document.removeEventListener("visibilitychange", whenVisible);
      navigator.mediaDevices?.removeEventListener?.("devicechange", check);
    };
  }, []);
  useEffect(() => { if (speechState.error) void refreshAudio(false); }, [speechState.error]);
  // A reported output failure withdraws the voice: no speech, no hands-free, and timer claims wait.
  const outputReady = outputUsable(audioStatus) && choices.state === 'ready';
  const support = {
    // Native hands-free requires both capture and June’s local output.
    recognition: outputReady && audioStatus.state === 'ready',
    speech: outputReady,
    checked: audioStatus.state !== 'checking' && choices.state !== 'checking',
  };
  const cancel = (reset = false) => { recognition.current?.cancel(reset); speech.current?.stop(); };
  const getVoice = () => outputUsable(audioStatusRef.current)
    ? registry.current?.get(selected.current) : undefined;
  return {
    setExpression: (expression:Expression) => { rate.current = expressionRates[expression]; speech.current?.setRate(rate.current); },
    engine, ownerId, audioStatus, refreshAudio,
    browserCapture, browserCaptureSupported,
    setBrowserCapture: (value: boolean) => {
      manual.current(); recognition.current?.cancel(); speech.current?.stop('capture-mode-changed'); stopMedia();
      browserCaptureRef.current = value; setBrowserCapture(value);
    },
    choices: { ...choices, selected: outputReady ? choices.selected : '' }, audioRecovery,
    /** True when a timer's one spoken announcement may be spent: selected voice and prepared output. */
    alertOutputWarm: outputReady && alertOutputWarm(audioStatus), speech: speechState, recognition: recognitionState, support, speakReplies, engineStatus, refreshSpeech, activity, level,
    cancel, stopVoice: (reason = 'stop-voice') => speech.current?.stop(reason), finishTalk: () => recognition.current?.finish(),
    pauseForInput: () => speech.current?.pauseForInput() ?? false,
    resumeAfterInput: () => speech.current?.resumeAfterInput(),
    startTalk: () => { if (!browserCaptureRef.current) return; manual.current(); speech.current?.stop(); stopMedia(); recognition.current?.start(); },
    setTranscript: (transcript: string) => recognition.current?.edit(transcript),
    clearTranscript: () => { recognition.current?.cancel(true); },
    // A manual refresh also restarts the automatic recovery budget.
    refresh: () => { recoveryAttempt.current = 0; void registry.current?.refresh(); void refreshAudio(); },
    setSpeakReplies: (value: boolean) => { if (!value) manual.current(); enabled.current = value; setSpeakReplies(value); save(storage.current, AUTO_KEY, String(value)); if (!value) speech.current?.stop(); },
    preview: () => { manual.current(); recognition.current?.cancel(); stopMedia(); speech.current?.replay("Hi, I’m June. Let’s take the next step together.", getVoice()); },
    // A queued notice (a finished timer): speaks only; never takes over, stops the microphone or cancels a reply.
    announce: (text: string) => { if (enabled.current) speech.current?.replay(text, getVoice()); },
    replay: (text: string) => { manual.current(); recognition.current?.cancel(); stopMedia(); speech.current?.replay(text, getVoice()); },
    begin: (id: number, handsFree = false, context?: NativePlaybackContext) => {
      recognition.current?.cancel(); stopMedia();
      speech.current?.begin(id, getVoice(), enabled.current, handsFree, context);
    },
    push: (id: number, text: string) => speech.current?.push(id, text),
    finish: (id: number, flushTail = true) => speech.current?.finish(id, flushTail),
    /** The native request now being spoken ('' when none): the id the backend sees for this playback. */
    requestId: () => speech.current?.currentRequest() ?? '',
  };
}
export type VoiceControls = ReturnType<typeof useVoice>;
