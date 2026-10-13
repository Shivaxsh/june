// Batch samples to avoid a main-thread message for every 128-sample audio block.
class JuneRecorder extends AudioWorkletProcessor {
  constructor() {
    super(); this.samples = new Float32Array(2048); this.used = 0; this.stopped = false;
    this.port.onmessage = event => { if (event.data === 'stop') { this.stopped = true; this.flush(); this.port.postMessage({ done: true }); } };
  }
  flush() {
    if (!this.used) return;
    const samples = this.samples.slice(0, this.used); this.port.postMessage({ samples }, [samples.buffer]); this.used = 0;
  }
  process(inputs, outputs) {
    // The graph is connected so processing runs, but its output is always silent.
    for (const channels of outputs) for (const channel of channels) channel.fill(0);
    if (this.stopped) return false;
    const channels = inputs[0]; if (!channels?.length) return true;
    for (let i = 0; i < channels[0].length; i++) {
      let mono = 0; for (const channel of channels) mono += channel[i];
      this.samples[this.used++] = mono / channels.length;
      if (this.used === this.samples.length) this.flush();
    }
    return true;
  }
}
registerProcessor('june-recorder', JuneRecorder);
