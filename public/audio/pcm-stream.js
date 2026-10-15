// Stateful low-pass filtering + fractional resampling. Worklet and tests share
// exactly this implementation; samples are never rounded per incoming block.
export class StreamingResampler {
  constructor(rate, emit) {
    this.rate = rate; this.emit = emit; this.step = rate / 16000;
    this.cursor = 0; this.next = 0; this.previous = 0;
    this.packet = new Int16Array(320); this.used = 0;
    this.history = new Float64Array(63); this.position = 0;
    this.taps = new Float64Array(63);
    const cutoff = Math.min(.45, 7200 / rate); let total = 0;
    for (let i = 0; i < 63; i++) {
      const x = i - 31;
      const sinc = x === 0 ? 2 * cutoff : Math.sin(2 * Math.PI * cutoff * x) / (Math.PI * x);
      this.taps[i] = sinc * (.54 - .46 * Math.cos(2 * Math.PI * i / 62)); total += this.taps[i];
    }
    for (let i = 0; i < 63; i++) this.taps[i] /= total;
  }
  push(samples) {
    for (let value of samples) {
      value = Number.isFinite(value) ? value : 0;
      this.history[this.position] = value;
      let filtered = 0;
      for (let i = 0; i < 63; i++) filtered += this.taps[i] * this.history[(this.position - i + 63) % 63];
      this.position = (this.position + 1) % 63;
      while (this.next <= this.cursor + 1e-7) {
        const fraction = Math.max(0, Math.min(1, this.next - this.cursor + 1));
        const sample = Math.max(-1, Math.min(1, this.previous + fraction * (filtered - this.previous)));
        this.packet[this.used++] = Math.round(sample * (sample < 0 ? 32768 : 32767));
        if (this.used === 320) {
          // Explicit little endian, independent of the host typed-array layout.
          const buffer = new ArrayBuffer(640), view = new DataView(buffer);
          for (let j = 0; j < 320; j++) view.setInt16(j * 2, this.packet[j], true);
          this.emit(buffer); this.used = 0;
        }
        this.next += this.step;
      }
      this.previous = filtered; this.cursor++;
    }
  }
}
