"use client";
import { useEffect, useRef, useState } from "react";
import { RecognitionController } from "@/lib/voice/recognition";
import { SpeechController } from "@/lib/voice/speech";
import { VoiceRegistry, AUTO_KEY, LANGUAGE_KEY, saved, save, type VoiceState } from "@/lib/voice/voices";
import { EMPTY_SPEECH, type BrowserRecognition, type RecognitionState, type SpeechState } from "@/lib/voice/types";

export function useVoice(stopMedia: () => void) {
  const registry = useRef<VoiceRegistry | null>(null);
  const speech = useRef<SpeechController | null>(null);
  const recognition = useRef<RecognitionController | null>(null);
  const selected = useRef("");
  const enabled = useRef(true);
  const storage = useRef<Storage | undefined>(undefined);
  const [choices, setChoices] = useState<VoiceState>({ options: [], selected: "", message: "Loading browser voices…" });
  const [speechState, setSpeechState] = useState<SpeechState>({ ...EMPTY_SPEECH });
  const [recognitionState, setRecognitionState] = useState<RecognitionState>({ phase: "idle", transcript: "", error: "" });
  const [speakReplies, setSpeakReplies] = useState(true);
  const [language, setLanguage] = useState("en-IN");
  const [support, setSupport] = useState({ recognition: false, speech: false, checked: false });
  const activity = useRef(0);
  useEffect(() => {
    try { storage.current = window.localStorage; } catch {}
    enabled.current = saved(storage.current, AUTO_KEY, "true") !== "false"; setSpeakReplies(enabled.current);
    const remembered = saved(storage.current, LANGUAGE_KEY, "en-IN");
    if (["en-IN", "en-US", "en-GB"].includes(remembered)) setLanguage(remembered);
    const browser = window as Window & { SpeechRecognition?: new () => BrowserRecognition; webkitSpeechRecognition?: new () => BrowserRecognition };
    const Recognition = browser.SpeechRecognition || browser.webkitSpeechRecognition;
    const synth = window.speechSynthesis;
    const supportedSpeech = !!synth && !!window.SpeechSynthesisUtterance;
    setSupport({ recognition: !!Recognition, speech: supportedSpeech, checked: true });
    recognition.current = new RecognitionController(Recognition ? () => new Recognition() : undefined, setRecognitionState);
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
    choices, speech: speechState, recognition: recognitionState, support, speakReplies, language, activity,
    cancel, stopVoice: () => speech.current?.stop(), finishTalk: () => recognition.current?.finish(),
    startTalk: () => { speech.current?.stop(); stopMedia(); recognition.current?.start(language); },
    setTranscript: (transcript: string) => recognition.current?.edit(transcript),
    clearTranscript: () => { recognition.current?.cancel(true); },
    chooseVoice: (id: string) => { speech.current?.stop(); registry.current?.choose(id); },
    refresh: () => registry.current?.refresh(),
    setLanguage: (lang: string) => { recognition.current?.cancel(); setLanguage(lang); save(storage.current, LANGUAGE_KEY, lang); },
    setSpeakReplies: (value: boolean) => { enabled.current = value; setSpeakReplies(value); save(storage.current, AUTO_KEY, String(value)); if (!value) speech.current?.stop(); },
    preview: () => { recognition.current?.cancel(); stopMedia(); speech.current?.replay("Hi Shivansh, I’m June. Let’s take the next step together.", getVoice()); },
    replay: (text: string) => { recognition.current?.cancel(); stopMedia(); speech.current?.replay(text, getVoice()); },
    begin: (id: number) => { recognition.current?.cancel(); stopMedia(); speech.current?.begin(id, getVoice(), enabled.current); },
    push: (id: number, text: string) => speech.current?.push(id, text),
    finish: (id: number) => speech.current?.finish(id),
  };
}
export type VoiceControls = ReturnType<typeof useVoice>;
