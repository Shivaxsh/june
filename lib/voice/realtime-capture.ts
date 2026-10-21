// One continuous microphone graph. It produces silent speaker output and
// transfers only PCM packets to June's local voice connection.
export type EchoMode = 'system-audio' | 'browser-managed' | 'off' | 'unknown';

export class RealtimeCapture {
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private node: AudioWorkletNode | null = null;
  private cancelled = false;
  private cancelEchoUpgrade: (() => void) | null = null;
  private signal: AbortSignal | null = null;
  private abort = () => this.stop();
  constructor(private level: { current: number }) {}
  // Read actual settings, including changes after an optional upgrade timed out.
  // This describes browser processing, not measured acoustic echo removal.
  get echoMode(): EchoMode {
    try {
      const track = this.stream?.getAudioTracks()[0];
      if (!track || track.readyState === 'ended') return 'unknown';
      const mode: unknown = track.getSettings?.().echoCancellation;
      if (mode === 'all') return 'system-audio';
      if (mode === true || mode === 'remote-only') return 'browser-managed';
      if (mode === false) return 'off';
    } catch { /* Older browsers may not expose processing settings. */ }
    return 'unknown';
  }
  private async upgradeEchoCancellation(track: MediaStreamTrack) {
    try {
      const modes: unknown = track.getCapabilities?.().echoCancellation;
      if (!Array.isArray(modes) || !modes.includes('all') || this.cancelled) return;
    } catch { return; }
    await new Promise<void>(resolve => {
      // Detach the capture/resolve callback when finished, even if the browser's
      // constraint promise remains pending after timeout or Stop.
      let complete: (() => void) | null = () => {
        clearTimeout(timer); this.cancelEchoUpgrade = null; resolve();
      };
      const finish = () => { const callback = complete; complete = null; callback?.(); };
      const timer = setTimeout(finish, 750);
      this.cancelEchoUpgrade = finish;
      try {
        // W3C Media Capture 2025 adds string echo modes; TS 5.9 DOM still
        // types this constraint as boolean. Cast only this advertised request.
        // https://www.w3.org/TR/mediacapture-streams/#dom-echocancellationmodeenum
        // applyConstraints replaces the previous dictionary. Preserve capture
        // processing and any device-specific constraints during this upgrade.
        const constraints = { channelCount: 1, noiseSuppression: true, autoGainControl: true,
          ...track.getConstraints?.(), echoCancellation: { exact: 'all' } } as unknown as MediaTrackConstraints;
        // applyConstraints has no abort API. Bound our wait; consume either late
        // outcome without creating resources or retrying capture.
        void track.applyConstraints(constraints).then(finish, finish);
      } catch { finish(); }
    });
  }
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
      const track = stream.getAudioTracks()[0];
      if (track) await this.upgradeEchoCancellation(track);
      if (signal.aborted || this.cancelled) throw new Error('Microphone request cancelled.');
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
    this.cancelEchoUpgrade?.();
    this.stream?.getTracks().forEach(track => track.stop()); this.stream = null;
    this.source?.disconnect(); this.source = null;
    if (this.node) { this.node.port.onmessage = null; this.node.port.postMessage('stop'); this.node.disconnect(); this.node.port.close(); this.node = null; }
    if (this.context) { void this.context.close().catch(() => {}); this.context = null; }
    this.level.current = 0;
  }
}
