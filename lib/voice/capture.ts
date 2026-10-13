import { encodeWav, MAX_RECORD_SECONDS } from './pcm';
import type { VoiceCapture } from './local-recognition';
export class BrowserVoiceCapture implements VoiceCapture {
  private context: AudioContext | null = null; private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null; private node: AudioWorkletNode | null = null;
  private chunks: Float32Array[] = []; private count = 0; private rate = 48000;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private flush: (() => void) | undefined; private cancelled = false;
  private signal: AbortSignal | null = null;
  private onAbort = () => this.cancel();
  constructor(private level: { current: number }) {}
  async start(signal: AbortSignal, onLimit: () => void) {
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext || !window.AudioWorkletNode || !window.OfflineAudioContext) throw new Error('Audio recording is unavailable in this browser. Open June’s local address in a current browser; typing still works.');
    this.signal = signal; signal.addEventListener('abort', this.onAbort, { once: true });
    // Create/resume during the deliberate user gesture, before awaiting permission.
    const context = new AudioContext(); this.context = context; this.rate = context.sampleRate;
    const resume = context.resume();
    // Handle rejection immediately while permission is pending. Awaiting the
    // original promise below still reports the error and releases the device.
    void resume.catch(() => {});
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      if (signal.aborted || this.cancelled) { stream.getTracks().forEach(track => track.stop()); signal.throwIfAborted(); throw new Error('Recording cancelled.'); }
      this.stream = stream;
      for (const track of stream.getAudioTracks()) track.addEventListener('ended', onLimit, { once: true });
      await resume; await context.audioWorklet.addModule('/audio/recorder-worklet.js'); signal.throwIfAborted();
      if (context.state !== 'running') throw new Error('Microphone audio could not start. Click Start listening again.');
      this.node = new AudioWorkletNode(context, 'june-recorder', { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] });
      this.node.port.onmessage = event => {
        if (this.cancelled) return;
        if (event.data.done) { this.flush?.(); return; }
        const samples: Float32Array = event.data.samples;
        const remaining = Math.max(0, this.rate * MAX_RECORD_SECONDS - this.count);
        const clipped = samples.length > remaining ? samples.slice(0, remaining) : samples;
        if (clipped.length) {
          this.chunks.push(clipped); this.count += clipped.length;
          let sum = 0; for (const value of clipped) sum += value * value;
          this.level.current = Math.min(1, Math.sqrt(sum / clipped.length) * 5);
        }
        if (this.count >= this.rate * MAX_RECORD_SECONDS) onLimit();
      };
      this.source = context.createMediaStreamSource(stream); this.source.connect(this.node); this.node.connect(context.destination);
      this.timer = setTimeout(onLimit, MAX_RECORD_SECONDS * 1000);
    } catch (error) { this.cancel(); throw error; }
  }
  async finish(): Promise<ArrayBuffer> {
    clearTimeout(this.timer);
    const node = this.node;
    if (!node || this.cancelled) throw new Error('No recording was captured. Start listening and try again.');
    await new Promise<void>(resolve => {
      const timeout = setTimeout(resolve, 300);
      this.flush = () => { clearTimeout(timeout); resolve(); }; node.port.postMessage('stop');
    });
    const samples = new Float32Array(this.count); let offset = 0;
    for (const chunk of this.chunks) { samples.set(chunk, offset); offset += chunk.length; }
    const rate = this.rate; this.release(); this.chunks = []; this.count = 0;
    if (samples.length < rate * .5) throw new Error('Recording is too short. Hold to talk for at least half a second.');
    if (this.cancelled) throw new Error('Recording cancelled.');
    // OfflineAudioContext applies proper audio resampling before WAV encoding.
    const offline = new OfflineAudioContext(1, Math.floor(samples.length * 16000 / rate), 16000);
    const buffer = offline.createBuffer(1, samples.length, rate); buffer.copyToChannel(samples, 0);
    const source = offline.createBufferSource(); source.buffer = buffer; source.connect(offline.destination); source.start();
    const rendered = await offline.startRendering(); if (this.cancelled) throw new Error('Recording cancelled.');
    return encodeWav(rendered.getChannelData(0));
  }
  private release() {
    clearTimeout(this.timer); this.signal?.removeEventListener('abort', this.onAbort);
    this.stream?.getTracks().forEach(track => track.stop()); this.stream = null;
    this.source?.disconnect(); this.source = null;
    if (this.node) { this.node.port.onmessage = null; this.node.disconnect(); this.node.port.close(); } this.node = null;
    if (this.context) void this.context.close().catch(() => {}); this.context = null; this.level.current = 0;
  }
  cancel() { this.cancelled = true; this.flush?.(); this.flush = undefined; this.release(); this.chunks = []; this.count = 0; }
}
