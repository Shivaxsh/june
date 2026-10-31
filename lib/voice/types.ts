export type RecognitionPhase = "idle" | "requesting" | "listening" | "finishing";
export type RecognitionState = { phase: RecognitionPhase; transcript: string; error: string };
export type RecognitionResult = { isFinal: boolean; [index: number]: { transcript: string }; };
export type RecognitionEvent = { results: ArrayLike<RecognitionResult> };
export interface BrowserRecognition {
  lang: string; continuous: boolean; interimResults: boolean;
  onstart: (() => void) | null; onaudiostart: (() => void) | null;
  onend: (() => void) | null; onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  start(): void; stop(): void; abort(): void;
}
export type RecognitionFactory = () => BrowserRecognition;
// Frontend durations use monotonic receipt times for native playback events.
// Native fields are optional measurements reported by the helper itself.
export type SpeechTimings = { firstAudioMs?: number; playbackMs?: number; totalMs?: number; nativeFirstAudioMs?: number; nativePlaybackMs?: number };
export type SpeechState = { phase: "idle" | "waiting" | "speaking"; error: string; caption: string; start: number; end: number; approximate: boolean; timings?: SpeechTimings };
export type VoiceOption = { id: string; name: string; accent: string; lang: string };
export const EMPTY_SPEECH: SpeechState = { phase: "idle", error: "", caption: "", start: 0, end: 0, approximate: true };
