import { readJsonLines } from '../ndjson';
import { SentenceBuffer, spokenText } from './sentences';
import { EMPTY_SPEECH, type SpeechState, type SpeechTimings } from './types';
import { accent, femaleVoices, saved, save, VOICE_KEY, type VoiceState } from './voices';

export type NativeVoice = { id: string; name: string; lang: string; gender: string; localService: true };
export type NativePlaybackContext = { voiceSessionId: string; turnId: number };
export type AudioEngine = 'native' | 'browser';
export const AUDIO_ENGINE_KEY = 'june-audio-engine-v1';
type Segment = { id: string; ordinal: number; text: string; abort: AbortController; accepted: boolean; started: boolean; timer?: ReturnType<typeof setTimeout> };

// Keep the browser controller's public surface, while the Mac helper owns all
// audio. Neither preview nor streamed playback acquires browser microphone input.
export class NativeSpeechController {
  private request = '';
  private requestAt: number | undefined;
  private firstPlaybackAt: number | undefined;
  private timings: SpeechTimings = {};
  private context: NativePlaybackContext | undefined;
  private streamId: number | null = null;
  private buffer = new SentenceBuffer();
  private queue: string[] = [];
  private segments = new Map<string, Segment>();
  private nextOrdinal = 0;
  private latestStartedOrdinal = -1;
  private playing = '';
  private voiceId = '';
  private rate = .98;
  private handsFree = false;
  private disposed = false;
  constructor(private notify: (state: SpeechState) => void, readonly activity = { current: 0 }, private http: typeof fetch = fetch, readonly ownerId = crypto.randomUUID(), private now: () => number = () => performance.now()) {}
  private emit(state: SpeechState) {
    if (!this.disposed) this.notify({ ...state, ...(Object.keys(this.timings).length ? { timings: { ...this.timings } } : {}) });
  }
  setRate(rate: number) { this.rate = [.98, .92, 1.04].includes(rate) ? rate : .98; }
  stop(_reason = 'stop') {
    const requestId = this.request; this.request = ''; this.streamId = null;
    if (requestId) console.debug('[June timing]', JSON.stringify({ event: 'speech-stop-request', at: Date.now(), requestId, ...this.context }));
    this.requestAt = this.firstPlaybackAt = undefined; this.timings = {};
    this.context = undefined;
    this.nextOrdinal = 0; this.latestStartedOrdinal = -1;
    this.queue = []; this.buffer = new SentenceBuffer(); this.playing = ''; this.activity.current = 0;
    for (const segment of this.segments.values()) { clearTimeout(segment.timer); segment.abort.abort(); }
    this.segments.clear();
    if (requestId) void this.http.call(globalThis, '/api/voice/stop', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, keepalive: true,
      body: JSON.stringify({ ownerId: this.ownerId, requestId }),
    }).catch(() => {});
    this.emit({ ...EMPTY_SPEECH });
  }
  // Native interruption verification runs beside the helper's AEC. A browser
  // probe must never claim that an HTTP stop is a resumable native pause.
  pauseForInput() { return false; }
  resumeAfterInput() {}
  begin(id: number, voice: SpeechSynthesisVoice | undefined, enabled: boolean, handsFree = false, context?: NativePlaybackContext) {
    this.stop('new-request');
    if (!enabled) return;
    if (handsFree && (!context?.voiceSessionId || !Number.isSafeInteger(context.turnId) || context.turnId < 1)) { this.fail('The native capture session ended. Enable hands-free again before speaking.'); return; }
    if (!voice) { this.fail('No local female voice is ready. Refresh voices; your reply remains readable.'); return; }
    this.requestAt = this.now(); this.request = crypto.randomUUID(); this.streamId = id; this.voiceId = voice.voiceURI; this.handsFree = handsFree; this.context = context ? { ...context } : undefined;
    this.emit({ ...EMPTY_SPEECH, phase: 'waiting' });
  }
  push(id: number, text: string) { if (id !== this.streamId) return; this.enqueue(this.buffer.push(text)); this.pump(); }
  finish(id: number, flushTail = true) {
    if (id !== this.streamId) return;
    this.enqueue(this.buffer.finish(!flushTail)); this.streamId = null; this.pump();
  }
  replay(text: string, voice: SpeechSynthesisVoice | undefined) {
    this.stop('replay');
    if (!voice) { this.fail('Choose an available local female English voice, then try playback.'); return; }
    const clean = spokenText(text);
    if (!clean) { this.fail('This reply contains no readable speech text.'); return; }
    this.requestAt = this.now(); this.request = crypto.randomUUID(); this.voiceId = voice.voiceURI; this.handsFree = false;
    this.enqueue([clean]); this.pump();
  }
  private enqueue(units: string[]) {
    for (let text of units) {
      if (this.handsFree) text = text.replace(/\bhey[\s,!.?—-]+june\b/gi, 'my wake phrase');
      // The server's 2000-character ceiling also applies to replay and long
      // punctuation-free output. Prefer a word boundary; never lose the tail.
      while (text.length > 2000) {
        let end = text.lastIndexOf(' ', 2000);
        if (end < 1) end = 2000;
        if (/[\uD800-\uDBFF]/.test(text[end - 1])) end--;
        this.queue.push(text.slice(0, end)); text = text.slice(end).trimStart();
      }
      if (text.trim()) this.queue.push(text.trim());
    }
  }
  private fail(message: string) { this.stop('playback-error'); this.emit({ ...EMPTY_SPEECH, error: message }); }
  private pump() {
    if (this.disposed || !this.request) return;
    // At most two submitted segments, and no prefetch before the preceding
    // request's headers are accepted. Native playback serializes the segments.
    if (this.queue.length && this.segments.size < 2 && [...this.segments.values()].every(segment => segment.accepted)) {
      const segment: Segment = { id: crypto.randomUUID(), ordinal: this.nextOrdinal++, text: this.queue.shift()!, abort: new AbortController(), accepted: false, started: false };
      this.segments.set(segment.id, segment);
      if (!this.playing) this.emit({ ...EMPTY_SPEECH, phase: 'waiting' });
      void this.play(segment, this.request);
    } else if (!this.segments.size && !this.queue.length) {
      this.activity.current = 0;
      this.emit({ ...EMPTY_SPEECH, phase: this.streamId === null ? 'idle' : 'waiting' });
    }
  }
  private async play(segment: Segment, requestId: string) {
    const owns = () => !this.disposed && this.request === requestId && this.segments.get(segment.id) === segment;
    segment.timer = setTimeout(() => { if (owns()) this.fail('Native voice playback timed out. Press Hear reply to retry.'); }, 120000);
    let terminal = false;
    try {
      const response = await this.http.call(globalThis, '/api/voice/speak', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: segment.abort.signal,
        body: JSON.stringify({ ownerId: this.ownerId, requestId, segmentId: segment.id, text: segment.text, voiceId: this.voiceId, rate: this.rate, ...this.context }),
      });
      if (!owns()) { await response.body?.cancel().catch(() => {}); return; }
      if (!response.ok || !response.body) throw new Error('Native voice could not accept playback. Refresh audio, then press Hear reply.');
      segment.accepted = true; this.pump();
      for await (const value of readJsonLines(response.body)) {
        if (!owns()) return;
        if (!value || typeof value !== 'object') throw new Error('Native voice sent an invalid playback event.');
        const event = value as { type?: string; charIndex?: number; charLength?: number; level?: number; message?: string; ownerId?: string; requestId?: string; segmentId?: string; firstAudioMs?: number; playbackMs?: number };
        if ((event.ownerId !== undefined && event.ownerId !== this.ownerId) || (event.requestId !== undefined && event.requestId !== requestId) || (event.segmentId !== undefined && event.segmentId !== segment.id)) continue;
        if (event.type === 'error') throw new Error(event.message || 'Native voice playback failed. Press Hear reply to retry.');
        if (event.type === 'cancelled') { terminal = true; this.stop('native-cancelled'); return; }
        // Independent HTTP streams can deliver an older start after newer
        // playback, even after that newer segment ended. Keep its ordinal until
        // the request stops; older terminal events still release their slots.
        if (event.type === 'start' && segment.ordinal >= this.latestStartedOrdinal) {
          this.latestStartedOrdinal = segment.ordinal;
          if (this.firstPlaybackAt === undefined) {
            this.firstPlaybackAt = this.now();
            if (this.requestAt !== undefined) this.timings.firstAudioMs = Math.max(0, this.firstPlaybackAt - this.requestAt);
            if (typeof event.firstAudioMs === 'number' && Number.isFinite(event.firstAudioMs) && event.firstAudioMs >= 0) this.timings.nativeFirstAudioMs = event.firstAudioMs;
            console.debug('[June timing]', JSON.stringify({ event: 'first-playback', at: Date.now(), requestId, ...this.context, durationMs: this.timings.firstAudioMs }));
          }
          segment.started = true; this.playing = segment.id; this.activity.current = 0;
        }
        if ((event.type === 'start' || event.type === 'boundary') && segment.started && this.playing === segment.id) {
          if (this.firstPlaybackAt !== undefined) this.timings.playbackMs = Math.max(0, this.now() - this.firstPlaybackAt);
          const start = typeof event.charIndex === 'number' && Number.isFinite(event.charIndex) ? Math.min(segment.text.length, Math.max(0, Math.floor(event.charIndex))) : 0;
          const length = typeof event.charLength === 'number' && Number.isFinite(event.charLength) ? Math.max(0, Math.floor(event.charLength)) : 0;
          if (typeof event.level === 'number' && Number.isFinite(event.level)) this.activity.current = Math.min(1, Math.max(0, event.level));
          this.emit({ phase: 'speaking', error: '', caption: segment.text, start, end: Math.min(segment.text.length, start + length), approximate: true });
        }
        if (event.type === 'end') {
          const endedAt = this.now();
          if (this.firstPlaybackAt !== undefined) this.timings.playbackMs = Math.max(0, endedAt - this.firstPlaybackAt);
          if (this.requestAt !== undefined) this.timings.totalMs = Math.max(0, endedAt - this.requestAt);
          if (typeof event.playbackMs === 'number' && Number.isFinite(event.playbackMs) && event.playbackMs >= 0) this.timings.nativePlaybackMs = event.playbackMs;
          console.debug('[June timing]', JSON.stringify({ event: 'segment-end', at: Date.now(), requestId, segmentId: segment.id, ...this.context, durationMs: event.playbackMs }));
          terminal = true; clearTimeout(segment.timer); this.segments.delete(segment.id);
          if (this.playing === segment.id) { this.playing = ''; this.activity.current = 0; }
          if (!this.playing) this.emit({ ...EMPTY_SPEECH, phase: this.queue.length || this.segments.size || this.streamId !== null ? 'waiting' : 'idle' });
          this.pump(); return;
        }
        if (!['accepted', 'start', 'boundary', 'end'].includes(event.type || '')) throw new Error('Native voice sent an invalid playback event.');
      }
      if (!terminal && owns()) throw new Error('The native playback stream ended before playback completed. Press Hear reply to retry.');
    } catch (error) {
      if (owns()) this.fail(error instanceof Error ? error.message : 'Native voice playback failed. Press Hear reply to retry.');
    } finally { clearTimeout(segment.timer); }
  }
  dispose() { this.stop('dispose'); this.disposed = true; }
}

function browserShape(voice: NativeVoice): SpeechSynthesisVoice {
  return { name: voice.name, lang: voice.lang, localService: true, default: false, voiceURI: voice.id };
}
export class NativeVoiceRegistry {
  private choices: SpeechSynthesisVoice[] = [];
  private selected = '';
  private abort: AbortController | null = null;
  private disposed = false;
  constructor(private storage: Storage | undefined, private notify: (state: VoiceState) => void, private http: typeof fetch = fetch) {}
  refresh = async () => {
    this.abort?.abort(); const abort = new AbortController(); this.abort = abort;
    try {
      const response = await this.http.call(globalThis, '/api/voice/voices', { cache: 'no-store', signal: AbortSignal.any([abort.signal, AbortSignal.timeout(10000)]) });
      const data = await response.json();
      if (!response.ok || !['ready', 'missing', 'error'].includes(data?.state) || !Array.isArray(data.voices)) throw new Error('Native voices are unavailable. Refresh audio or explicitly choose browser audio.');
      if (abort.signal.aborted || this.disposed) return;
      this.choices = data.state === 'ready' ? (data.voices as NativeVoice[])
        .filter(voice => voice && typeof voice.id === 'string' && typeof voice.name === 'string' && typeof voice.lang === 'string' && voice.localService === true && /^en(?:[-_]|$)/i.test(voice.lang))
        .filter(voice => /^female$/i.test(voice.gender) || (!/^male$/i.test(voice.gender) && femaleVoices([browserShape(voice)]).length > 0))
        .map(browserShape) : [];
      const preference = saved(this.storage, VOICE_KEY, '');
      const [uri, name, lang] = preference.split('|');
      const sameLang = (value: string) => value.replaceAll('_', '-').toLowerCase() === lang?.replaceAll('_', '-').toLowerCase();
      const remembered = this.choices.find(voice => voice.voiceURI === uri)
        || this.choices.find(voice => voice.name.toLowerCase() === name?.toLowerCase() && sameLang(voice.lang));
      const selected = remembered || this.get(this.selected) || this.choices[0]; this.selected = selected?.voiceURI || '';
      this.publish(selected ? `${selected.name} · ${accent(selected.lang)} · native Mac voice` : data.message || 'No local female English voice is ready.');
    } catch (error) {
      if (!abort.signal.aborted && !this.disposed) { this.choices = []; this.selected = ''; this.publish(error instanceof Error ? error.message : 'Could not load native voices.'); }
    }
  };
  private publish(message: string) { this.notify({ options: this.choices.map(voice => ({ id: voice.voiceURI, name: voice.name, lang: voice.lang, accent: accent(voice.lang) })), selected: this.selected, message }); }
  get(id: string) { return this.choices.find(voice => voice.voiceURI === id); }
  choose(id: string) {
    const voice = this.get(id); if (!voice) return;
    this.selected = id; save(this.storage, VOICE_KEY, `${voice.voiceURI}|${voice.name}|${voice.lang}`);
    this.publish(`${voice.name} · ${accent(voice.lang)} · native Mac voice`);
  }
  dispose() { this.disposed = true; this.abort?.abort(); }
}
