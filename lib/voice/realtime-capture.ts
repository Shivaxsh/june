// One continuous microphone graph. It produces silent speaker output and
// transfers only PCM packets to June's local voice connection.
export class RealtimeCapture {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private node: AudioWorkletNode | null = null;
  private cancelled = false;
  private signal: AbortSignal | null = null;
  private abort = () => this.stop();
  constructor(private level: { current: number }) {}
  async start(signal: AbortSignal, packet: (data: ArrayBuffer) => void, failed: (message: string) => void) {
    if (typeof AudioContext === 'undefined' || typeof AudioWorkletNode === 'undefined' || !navigator.mediaDevices?.getUserMedia) throw new Error('Microphone streaming is unavailable in this browser. Try a current browser on June’s local page, or keep typing.');
    this.signal = signal; signal.addEventListener('abort', this.abort, { once: true });
    if (signal.aborted) { this.stop(); throw new Error('Microphone request cancelled.'); }
    const context = new AudioContext(); this.context = context;
    const resume = context.resume(); void resume.catch(() => {});
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      if (signal.aborted || this.cancelled) { stream.getTracks().forEach(track => track.stop()); throw new Error('Microphone request cancelled.'); }
      this.stream = stream;
      stream.getAudioTracks().forEach(track => track.addEventListener('ended', () => { if (!this.cancelled) failed('The microphone disconnected. Enable hands-free again.'); }, { once: true }));
      await resume; await context.audioWorklet.addModule('/audio/realtime-worklet.js');
      signal.throwIfAborted();
      if (this.cancelled || context.state !== 'running') throw new Error('Microphone audio could not start. Enable hands-free again.');
      this.node = new AudioWorkletNode(context, 'june-stream', { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] });
      this.node.port.onmessage = event => {
        if (this.cancelled) return;
        if (event.data.error) { failed('Microphone processing fell behind. Close busy tabs and enable hands-free again.'); return; }
        const pcm = event.data.pcm;
        if (!(pcm instanceof ArrayBuffer) || pcm.byteLength !== 640) { failed('The microphone stream was invalid. Try again.'); return; }
        const view = new DataView(pcm); let energy = 0;
        for (let i = 0; i < 640; i += 2) energy += (view.getInt16(i, true) / 32768) ** 2;
        this.level.current = Math.min(1, Math.sqrt(energy / 320) * 5);
        this.node?.port.postMessage('ack');
        packet(pcm);
      };
      this.source = context.createMediaStreamSource(stream); this.source.connect(this.node); this.node.connect(context.destination);
    } catch (error) { this.stop(); throw error; }
  }
  stop() {
    this.cancelled = true; this.signal?.removeEventListener('abort', this.abort);
    this.stream?.getTracks().forEach(track => track.stop()); this.stream = null;
    this.source?.disconnect(); this.source = null;
    if (this.node) { this.node.port.onmessage = null; this.node.port.postMessage('stop'); this.node.disconnect(); this.node.port.close(); this.node = null; }
    if (this.context) { void this.context.close().catch(() => {}); this.context = null; }
    this.level.current = 0;
  }
}
