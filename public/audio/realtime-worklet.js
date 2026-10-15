import { StreamingResampler } from './pcm-stream.js';
class JuneStream extends AudioWorkletProcessor {
  constructor() {
    super(); this.stopped = false; this.inflight = 0;
    this.resampler = new StreamingResampler(sampleRate, pcm => {
      if (this.stopped) return;
      if (this.inflight >= 100) { this.stopped = true; this.port.postMessage({ error: 'backpressure' }); return; }
      this.inflight++; this.port.postMessage({ pcm }, [pcm]);
    });
    this.port.onmessage = event => { if (event.data === 'stop') this.stopped = true; else if (event.data === 'ack') this.inflight = Math.max(0, this.inflight - 1); };
  }
  process(inputs, outputs) {
    for (const channels of outputs) for (const channel of channels) channel.fill(0);
    if (this.stopped) return false;
    const channels = inputs[0]; if (!channels?.length) return true;
    const mono = new Float32Array(channels[0].length);
    for (let i = 0; i < mono.length; i++) {
      for (const channel of channels) mono[i] += channel[i] / channels.length;
    }
    this.resampler.push(mono); return true;
  }
}
registerProcessor('june-stream', JuneStream);
