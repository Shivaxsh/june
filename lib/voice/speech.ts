import type { SpeechState } from "./types";
import { EMPTY_SPEECH } from "./types";
import { SentenceBuffer, spokenText } from "./sentences";
export type SpeechDiagnostic = { event: string; at: number; token: number; queued: number; streaming: boolean; reason?: string; chars?: number; elapsedMs?: number; lastBoundary?: number };
export class SpeechController {
  readonly activity: { current: number };
  private synth: SpeechSynthesis;
  private Utterance: typeof SpeechSynthesisUtterance;
  private notify: (state: SpeechState) => void;
  private rate = .98;
  setRate(rate: number) { this.rate = [.98,.92,1.04].includes(rate) ? rate : .98; }
  private token = 0;
  private streamId: number | null = null;
  private buffer = new SentenceBuffer();
  private queue: string[] = [];
  private voice: SpeechSynthesisVoice | undefined;
  private utterance: SpeechSynthesisUtterance | null = null;
  private timers: ReturnType<typeof setTimeout>[] = [];
  private pulse: ReturnType<typeof setInterval> | undefined;
  private disposed = false;
  private handsFree = false;
  private inputHold = false;
  private pauseWait: { cancel(): void; promise: Promise<boolean | null> } | null = null;
  constructor(synth: SpeechSynthesis, Utterance: typeof SpeechSynthesisUtterance, notify: (state: SpeechState) => void, activity = { current: 0 }, private diagnose: (event: SpeechDiagnostic) => void = () => {}) { this.synth = synth; this.Utterance = Utterance; this.notify = notify; this.activity = activity; }
  private trace(event: string, detail: Partial<SpeechDiagnostic> = {}) { this.diagnose({ event, at: Date.now(), token: this.token, queued: this.queue.length, streaming: this.streamId !== null, ...detail }); }
  private emit(state: SpeechState) { if (!this.disposed) this.notify(state); }
  private clear() { this.timers.forEach(clearTimeout); this.timers = []; clearInterval(this.pulse); this.activity.current = 0; }
  stop(reason = 'stop') {
    if (this.utterance || this.streamId !== null || this.queue.length) this.trace('cancel', { reason });
    this.pauseWait?.cancel();
    const held = this.inputHold; this.inputHold = false;
    this.token++; this.streamId = null; this.queue = []; this.buffer = new SentenceBuffer(); this.handsFree = false; this.clear();
    if (this.utterance) this.utterance.onstart = this.utterance.onend = this.utterance.onerror = this.utterance.onboundary = null;
    this.utterance = null;
    try { this.synth.cancel(); } catch {}
    // Some engines remain globally paused after cancel(). A new turn must not
    // inherit that pause; old callbacks have already been detached.
    if (held) { try { this.synth.resume(); } catch {} }
    this.emit({ ...EMPTY_SPEECH });
  }
  pauseForInput() {
    if (this.inputHold) return this.pauseWait?.promise ?? Promise.resolve(true);
    this.inputHold = true; this.activity.current = 0;
    const token = this.token, utterance = this.utterance;
    let timer: ReturnType<typeof setTimeout> | undefined, complete = false;
    let resolve!: (value: boolean | null) => void;
    const promise = new Promise<boolean | null>(done => { resolve = done; });
    const finish = (value: boolean | null) => {
      if (complete) return;
      complete = true; clearTimeout(timer);
      if (utterance?.onpause === paused) utterance.onpause = null;
      this.pauseWait = null; resolve(value);
    };
    const paused = () => finish(token === this.token && this.inputHold && !this.disposed);
    // null means deliberate cancellation, not an unsupported pause engine.
    this.pauseWait = { cancel: () => finish(null), promise };
    if (utterance) utterance.onpause = paused;
    const deadline = Date.now() + 750;
    const check = () => {
      if (complete) return;
      if (token !== this.token || !this.inputHold || this.disposed) { finish(false); return; }
      if (this.synth.paused) { finish(true); return; }
      if (Date.now() >= deadline) {
        finish(false); this.fail('This browser could not pause voice for an interruption. Press Stop or try another browser.'); return;
      }
      timer = setTimeout(check, 25);
    };
    try { this.synth.pause(); check(); }
    catch { finish(false); this.fail('This browser could not pause voice for an interruption. Press Stop or try another browser.'); }
    return promise;
  }
  resumeAfterInput() {
    if (!this.inputHold) return;
    this.inputHold = false;
    try { this.synth.resume(); this.pump(); }
    catch { this.fail('Voice could not resume. Press Hear reply to retry.'); }
  }
  begin(id: number, voice: SpeechSynthesisVoice | undefined, enabled: boolean, handsFree = false) {
    this.stop('new-request'); if (!enabled) return;
    if (!voice) { this.emit({ ...EMPTY_SPEECH, error: "No local female voice is ready. Refresh voices or install one; your written reply will still appear." }); return; }
    this.handsFree = handsFree;
    this.streamId = id; this.voice = voice; this.emit({ ...EMPTY_SPEECH, phase: "waiting" });
  }
  push(id: number, delta: string) { if (id !== this.streamId) return; this.queue.push(...this.buffer.push(delta)); this.pump(); }
  finish(id: number, flushTail = true) {
    if (id !== this.streamId) return;
    this.queue.push(...this.buffer.finish(!flushTail));
    this.streamId = null; this.pump();
  }
  replay(text: string, voice: SpeechSynthesisVoice | undefined) {
    this.stop('replay');
    if (!voice) { this.emit({ ...EMPTY_SPEECH, error: "Choose an available local female English voice, then try playback." }); return; }
    const clean = spokenText(text);
    if (!clean) { this.emit({ ...EMPTY_SPEECH, error: "This reply contains no readable speech text." }); return; }
    this.voice = voice; this.queue = [clean]; this.pump();
  }
  private fail(message: string) { this.stop('playback-error'); this.emit({ ...EMPTY_SPEECH, error: message }); }
  private pump() {
    if (this.disposed || this.utterance || this.inputHold) return;
    const queued = this.queue.shift();
    const text = this.handsFree ? queued?.replace(/\bhey[\s,!.?—-]+june\b/gi, 'my wake phrase') : queued;
    if (!text) { if (this.streamId === null) this.emit({ ...EMPTY_SPEECH }); return; }
    const token = ++this.token;
    try {
      const utterance = new this.Utterance(text); this.utterance = utterance;
      utterance.voice = this.voice || null; utterance.lang = this.voice?.lang || "en-US";
      utterance.rate = this.rate; utterance.pitch = 1;
      let began = false, boundaries = false, index = 0, started = 0, lastBoundary = 0;
      const ownsPlayback = () => token === this.token && this.utterance === utterance;
      const words = [...text.matchAll(/\S+/g)];
      utterance.onstart = () => {
        if (!ownsPlayback()) return;
        began = true; this.clear();
        started = Date.now(); this.trace('start', { chars: text.length });
        this.emit({ phase: "speaking", error: "", caption: text, start: 0, end: 0, approximate: true });
        this.pulse = setInterval(() => {
          if (!ownsPlayback() || this.inputHold) return;
          // Speech activity animation only; this is not a measured waveform.
          this.activity.current = .35 + (index % 3) * .2;
          if (!boundaries) {
            const word = words[Math.min(index, words.length - 1)];
            if (word) this.emit({ phase: "speaking", error: "", caption: text, start: word.index ?? 0, end: (word.index ?? 0) + word[0].length, approximate: true });
          }
          index++;
        }, 370);
        this.timers.push(setTimeout(() => { if (ownsPlayback()) this.fail("Voice playback timed out. Try a shorter reply or preview another voice."); }, 90000));
      };
      utterance.onboundary = event => {
        if (!ownsPlayback() || !began || this.inputHold) return;
        boundaries = true; this.activity.current = .9;
        const start = Math.max(0, event.charIndex);
        const length = event.charLength || (text.slice(start).match(/^\S+/)?.[0].length ?? 0);
        lastBoundary = Math.min(text.length, start + length);
        this.emit({ phase: "speaking", error: "", caption: text, start, end: Math.min(text.length, start + length), approximate: false });
      };
      utterance.onend = () => {
        if (!ownsPlayback()) return;
        this.trace('end', { chars: text.length, elapsedMs: started ? Date.now()-started : 0, lastBoundary });
        this.clear(); this.utterance = null;
        // A sentence ending is not a reply ending. In particular, never open
        // hands-free follow-up capture while another sentence is queued or
        // the model is still streaming the rest of the same reply.
        const pending = this.inputHold || this.queue.length > 0 || this.streamId !== null;
        this.emit({ ...EMPTY_SPEECH, phase: pending ? 'waiting' : 'idle', caption: text, end: text.length, approximate: !boundaries });
        this.pump();
      };
      utterance.onerror = () => { if (ownsPlayback()) this.fail("The selected voice could not play. Preview another female voice or press Hear reply to retry."); };
      this.emit({ ...EMPTY_SPEECH, phase: "waiting" });
      this.synth.speak(utterance);
      this.timers.push(setTimeout(() => { if (ownsPlayback() && !began) this.fail("Voice playback did not start. Press Preview voice or Hear reply to activate it, or try another browser."); }, 12000));
    } catch { if (token === this.token) this.fail("Voice playback is unavailable. Try another browser; the reply remains readable."); }
  }
  dispose() { this.disposed = true; this.stop(); }
}
