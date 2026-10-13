import { validateWav } from './pcm';
import type { RecognitionState } from './types';
export interface VoiceCapture {
  start(signal: AbortSignal, onLimit: () => void): Promise<void>;
  finish(): Promise<ArrayBuffer>;
  cancel(): void;
}
export type Transcription = { text: string; durationMs: number };
export type Transcriber = (clip: ArrayBuffer, signal: AbortSignal) => Promise<Transcription>;
function captureError(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === 'NotAllowedError') return 'Microphone permission was denied. Allow microphone access in your browser settings, then try again.';
    if (error.name === 'NotFoundError') return 'No microphone was found. Connect a microphone and try again.';
    if (error.name === 'NotReadableError') return 'The microphone is unavailable. Close other recording apps and try again.';
  }
  return error instanceof Error ? error.message : 'June could not record speech. Check your microphone and try again.';
}
// Request tokens protect the draft from late permission and transcription results.
export class LocalRecognitionController {
  private token = 0; private phase: RecognitionState['phase'] = 'idle';
  private transcript = ''; private disposed = false;
  private capture: VoiceCapture | null = null; private abort: AbortController | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  constructor(private factory: () => VoiceCapture, private transcribe: Transcriber, private notify: (state: RecognitionState) => void) {}
  private emit(phase: RecognitionState['phase'], error = '') { this.phase = phase; if (!this.disposed) this.notify({ phase, transcript: this.transcript, error }); }
  cancel(reset = false) {
    this.token++; clearTimeout(this.timer); this.abort?.abort(); this.abort = null;
    this.capture?.cancel(); this.capture = null;
    if (reset) this.transcript = ''; this.emit('idle');
  }
  edit(text: string) { if (this.phase === 'idle') { this.transcript = text; this.emit('idle'); } }
  start() {
    if (this.disposed || this.phase !== 'idle') return;
    this.cancel(); const token = this.token; const abort = new AbortController(); this.abort = abort;
    this.emit('requesting');
    try { this.capture = this.factory(); } catch (error) { this.emit('idle', captureError(error)); return; }
    const capture = this.capture;
    this.timer = setTimeout(() => { if (token === this.token) { this.cancel(); this.emit('idle', 'Microphone access is still pending. Answer the browser prompt, then start listening again.'); } }, 15000);
    void capture.start(abort.signal, () => this.finish()).then(() => {
      if (token !== this.token || this.disposed) { capture.cancel(); return; }
      clearTimeout(this.timer); this.emit('listening');
    }).catch(error => {
      if (token !== this.token || this.disposed) return;
      clearTimeout(this.timer); capture.cancel(); this.capture = null; this.abort = null; this.emit('idle', captureError(error));
    });
  }
  finish() {
    if (this.phase === 'requesting') { this.cancel(); this.emit('idle', 'Recording stopped before microphone access was ready. Start listening again when access is allowed.'); return; }
    if (this.phase !== 'listening' || !this.capture || !this.abort) return;
    const token = this.token, capture = this.capture, abort = this.abort;
    this.emit('finishing');
    void (async () => {
      try {
        const clip = await capture.finish(); if (token !== this.token) return;
        this.capture = null; validateWav(new Uint8Array(clip));
        const result = await this.transcribe(clip, abort.signal); if (token !== this.token || abort.signal.aborted) return;
        if (!result.text.trim()) throw new Error('No words were recognised. Try a clear, short sentence.');
        this.transcript = result.text.trim(); this.emit('idle');
      } catch (error) {
        if (token === this.token && !abort.signal.aborted) this.emit('idle', captureError(error));
      } finally {
        capture.cancel(); if (token === this.token) { this.capture = null; this.abort = null; }
      }
    })();
  }
  dispose() { this.cancel(); this.disposed = true; }
}
export async function transcribeLocally(clip: ArrayBuffer, signal: AbortSignal): Promise<Transcription> {
  let response: Response;
  try {
    response = await fetch('/api/speech/transcribe', { method: 'POST', headers: { 'Content-Type': 'audio/wav' }, body: clip, signal: AbortSignal.any([signal, AbortSignal.timeout(125000)]) });
  } catch (error) {
    signal.throwIfAborted();
    if (error instanceof DOMException && error.name === 'TimeoutError') throw new Error('Local transcription took too long. Try a shorter recording.');
    throw new Error('June’s speech server could not connect. Restart June, then refresh speech and try again.');
  }
  const result = await response.json().catch(() => { throw new Error('June’s speech server returned unreadable data. Restart June, then refresh speech.'); });
  if (!response.ok) throw new Error(result?.error?.message || 'Local transcription failed. Refresh speech and retry.');
  if (typeof result.text !== 'string' || typeof result.durationMs !== 'number') throw new Error('The local speech server returned an invalid transcript.');
  return result;
}
