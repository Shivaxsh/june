import type { SpeechState } from "./types";
import { EMPTY_SPEECH } from "./types";
import { SentenceBuffer, spokenText } from "./sentences";
export class SpeechController {
  readonly activity: { current: number };
  private synth: SpeechSynthesis;
  private Utterance: typeof SpeechSynthesisUtterance;
  private notify: (state: SpeechState) => void;
  private token = 0;
  private streamId: number | null = null;
  private buffer = new SentenceBuffer();
  private queue: string[] = [];
  private voice: SpeechSynthesisVoice | undefined;
  private utterance: SpeechSynthesisUtterance | null = null;
  private timers: ReturnType<typeof setTimeout>[] = [];
  private pulse: ReturnType<typeof setInterval> | undefined;
  private disposed = false;
  constructor(synth: SpeechSynthesis, Utterance: typeof SpeechSynthesisUtterance, notify: (state: SpeechState) => void, activity = { current: 0 }) { this.synth = synth; this.Utterance = Utterance; this.notify = notify; this.activity = activity; }
  private emit(state: SpeechState) { if (!this.disposed) this.notify(state); }
  private clear() { this.timers.forEach(clearTimeout); this.timers = []; clearInterval(this.pulse); this.activity.current = 0; }
  stop() {
    this.token++; this.streamId = null; this.queue = []; this.buffer = new SentenceBuffer(); this.clear();
    if (this.utterance) this.utterance.onstart = this.utterance.onend = this.utterance.onerror = this.utterance.onboundary = null;
    this.utterance = null;
    try { this.synth.cancel(); } catch {}
    this.emit({ ...EMPTY_SPEECH });
  }
  begin(id: number, voice: SpeechSynthesisVoice | undefined, enabled: boolean) {
    this.stop(); if (!enabled) return;
    if (!voice) { this.emit({ ...EMPTY_SPEECH, error: "No local female voice is ready. Refresh voices or install one; your written reply will still appear." }); return; }
    this.streamId = id; this.voice = voice; this.emit({ ...EMPTY_SPEECH, phase: "waiting" });
  }
  push(id: number, delta: string) { if (id !== this.streamId) return; this.queue.push(...this.buffer.push(delta)); this.pump(); }
  finish(id: number) {
    if (id !== this.streamId) return;
    this.queue.push(...this.buffer.finish()); this.streamId = null; this.pump();
  }
  replay(text: string, voice: SpeechSynthesisVoice | undefined) {
    this.stop();
    if (!voice) { this.emit({ ...EMPTY_SPEECH, error: "Choose an available local female English voice, then try playback." }); return; }
    const clean = spokenText(text);
    if (!clean) { this.emit({ ...EMPTY_SPEECH, error: "This reply contains no readable speech text." }); return; }
    this.voice = voice; this.queue = [clean]; this.pump();
  }
  private fail(message: string) { this.stop(); this.emit({ ...EMPTY_SPEECH, error: message }); }
  private pump() {
    if (this.disposed || this.utterance) return;
    const text = this.queue.shift();
    if (!text) { if (this.streamId === null) this.emit({ ...EMPTY_SPEECH }); return; }
    const token = ++this.token;
    try {
      const utterance = new this.Utterance(text); this.utterance = utterance;
      utterance.voice = this.voice || null; utterance.lang = this.voice?.lang || "en-US";
      utterance.rate = .98; utterance.pitch = 1;
      let began = false, boundaries = false, index = 0;
      const words = [...text.matchAll(/\S+/g)];
      utterance.onstart = () => {
        if (token !== this.token) return;
        began = true; this.clear();
        this.emit({ phase: "speaking", error: "", caption: text, start: 0, end: 0, approximate: true });
        this.pulse = setInterval(() => {
          if (token !== this.token) return;
          // Speech activity animation only; this is not a measured waveform.
          this.activity.current = .35 + (index % 3) * .2;
          if (!boundaries) {
            const word = words[Math.min(index, words.length - 1)];
            if (word) this.emit({ phase: "speaking", error: "", caption: text, start: word.index ?? 0, end: (word.index ?? 0) + word[0].length, approximate: true });
          }
          index++;
        }, 370);
        this.timers.push(setTimeout(() => { if (token === this.token) this.fail("Voice playback timed out. Try a shorter reply or preview another voice."); }, 90000));
      };
      utterance.onboundary = event => {
        if (token !== this.token || !began) return;
        boundaries = true; this.activity.current = .9;
        const start = Math.max(0, event.charIndex);
        const length = event.charLength || (text.slice(start).match(/^\S+/)?.[0].length ?? 0);
        this.emit({ phase: "speaking", error: "", caption: text, start, end: Math.min(text.length, start + length), approximate: false });
      };
      utterance.onend = () => {
        if (token !== this.token) return;
        this.clear(); this.utterance = null; this.emit({ ...EMPTY_SPEECH, caption: text, end: text.length, approximate: !boundaries }); this.pump();
      };
      utterance.onerror = () => { if (token === this.token) this.fail("The selected voice could not play. Preview another female voice or press Hear reply to retry."); };
      this.emit({ ...EMPTY_SPEECH, phase: "waiting" });
      this.synth.speak(utterance);
      this.timers.push(setTimeout(() => { if (token === this.token && !began) this.fail("Voice playback did not start. Press Preview voice or Hear reply to activate it, or try another browser."); }, 12000));
    } catch { if (token === this.token) this.fail("Voice playback is unavailable. Try another browser; the reply remains readable."); }
  }
  dispose() { this.disposed = true; this.stop(); }
}
