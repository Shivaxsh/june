import type { AudioPhase } from "./state";

export type AudioState = { phase: AudioPhase; error: string };
export type Level = { current: number };

// Owns one source at a time. No audio is recorded or sent to a server.
export class AudioController {
  readonly level: Level;
  private notify: (state: AudioState) => void;
  private generation = 0;
  private disposed = false;
  private context: AudioContext | null = null;
  private source: AudioNode | null = null;
  private analyser: AnalyserNode | null = null;
  private media: HTMLAudioElement | null = null;
  private stream: MediaStream | null = null;
  private objectUrl: string | null = null;
  private frame = 0;
  private permissionTimer: ReturnType<typeof setTimeout> | undefined;

  constructor(notify: (state: AudioState) => void, level: Level = { current: 0 }) { this.notify = notify; this.level = level; }
  private emit(phase: AudioPhase, error = "") { if (!this.disposed) this.notify({ phase, error }); }

  stop() {
    this.generation++;
    clearTimeout(this.permissionTimer);
    cancelAnimationFrame(this.frame);
    if (this.media) {
      this.media.onended = null;
      this.media.onerror = null;
      this.media.pause();
      this.media.removeAttribute("src");
      this.media.load();
    }
    this.stream?.getTracks().forEach(track => track.stop());
    this.source?.disconnect();
    this.analyser?.disconnect();
    void this.context?.close().catch(() => {});
    if (this.objectUrl) URL.revokeObjectURL(this.objectUrl);
    this.media = null; this.stream = null; this.context = null;
    this.source = null; this.analyser = null; this.objectUrl = null;
    this.level.current = 0;
    this.emit("idle");
  }

  dispose() { this.disposed = true; this.stop(); }
  private fail(message: string) { this.stop(); this.emit("idle", message); }

  private prepare() {
    if (!window.AudioContext) throw new Error("This browser cannot visualise audio. Try a current browser; text chat still works.");
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    this.context = context; this.analyser = analyser;
    return { context, analyser };
  }

  private measure(token: number) {
    const analyser = this.analyser;
    if (!analyser) return;
    const samples = new Float32Array(analyser.fftSize);
    const tick = () => {
      if (token !== this.generation || this.disposed) return;
      analyser.getFloatTimeDomainData(samples);
      // RMS measures signal amplitude; smoothing removes abrupt frame jumps.
      const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
      const target = Math.min(1, rms * 5);
      this.level.current += (target - this.level.current) * 0.22;
      this.frame = requestAnimationFrame(tick);
    };
    this.frame = requestAnimationFrame(tick);
  }

  async play(file?: File) {
    if (this.disposed) return;
    // Resume the same source, preserving its playback position.
    if (this.media) {
      const token = this.generation;
      try {
        await this.context?.resume();
        if (token !== this.generation) return;
        await this.media?.play();
        if (token === this.generation) this.emit("playing");
      } catch { if (token === this.generation) this.fail("Playback could not resume. Press Play to try again."); }
      return;
    }
    this.stop();
    const token = this.generation;
    try {
      const { context, analyser } = this.prepare();
      const media = new Audio();
      this.media = media;
      media.preload = "auto";
      if (file) this.objectUrl = URL.createObjectURL(file);
      media.src = this.objectUrl || "/audio/june-tones.wav";
      this.source = context.createMediaElementSource(media);
      this.source.connect(analyser);
      analyser.connect(context.destination);
      media.onended = () => { if (token === this.generation) this.stop(); };
      media.onerror = () => { if (token === this.generation) this.fail("This audio could not play. Choose a supported audio file or try the built-in sample."); };
      await context.resume();
      if (token !== this.generation) return;
      await media.play();
      if (token !== this.generation) return;
      this.emit("playing");
      this.measure(token);
    } catch (error) {
      if (token === this.generation) this.fail(error instanceof Error && error.message.includes("browser") ? error.message : "Could not play audio. Try the built-in sample or choose another audio file.");
    }
  }

  pause() {
    if (!this.media) return;
    this.media.pause(); this.level.current = 0; this.emit("paused");
  }

  async microphone() {
    if (this.disposed) return;
    this.stop();
    const token = this.generation;
    if (!navigator.mediaDevices?.getUserMedia) {
      this.fail("Microphone access is unavailable here. Open June on localhost in a supported browser."); return;
    }
    this.emit("requesting");
    this.permissionTimer = setTimeout(() => {
      if (token === this.generation) this.fail("Microphone permission is still pending. Check the browser prompt, then press Start microphone again.");
    }, 30000);
    try {
      const { context, analyser } = this.prepare();
      // Resume on the user's click, before the permission dialog resolves.
      await context.resume();
      if (token !== this.generation) return;
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      if (token !== this.generation || this.disposed) { stream.getTracks().forEach(track => track.stop()); return; }
      clearTimeout(this.permissionTimer);
      this.stream = stream;
      this.source = context.createMediaStreamSource(stream);
      this.source.connect(analyser); // Deliberately no connection to speakers.
      stream.getAudioTracks().forEach(track => { track.onended = () => {
        if (token === this.generation) this.fail("The microphone disconnected. Check your device and start it again.");
      }; });
      this.emit("listening"); this.measure(token);
    } catch (error) {
      if (token !== this.generation) return;
      const name = error instanceof Error ? error.name : "";
      this.fail(name === "NotAllowedError" ? "Microphone permission was denied. Allow it in your browser settings to try again, or use the audio sample."
        : name === "NotFoundError" ? "No microphone was found. Connect one or use the audio sample."
        : "Could not start the microphone. Check browser permissions and whether another app is using it.");
    }
  }
}
