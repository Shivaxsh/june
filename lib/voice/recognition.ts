import type { BrowserRecognition, RecognitionFactory, RecognitionState } from "./types";
const errors: Record<string, string> = {
  "not-allowed": "Speech permission was denied. Allow the microphone in your browser settings, or keep typing.",
  "service-not-allowed": "This browser cannot access its speech service. Try a browser with speech recognition, or keep typing.",
  "audio-capture": "No usable microphone was found. Check your microphone and browser permissions.",
  "no-speech": "No speech was recognised. Hold the button and try a short sentence.",
  network: "The browser’s speech service could not connect. Check your connection, try a browser with working recognition, or keep typing.",
  "language-not-supported": "This recognition language is unavailable. Try another English option.",
};
export class RecognitionController {
  private factory: RecognitionFactory | undefined;
  private notify: (state: RecognitionState) => void;
  private instance: BrowserRecognition | null = null;
  private generation = 0;
  private transcript = "";
  private started = false;
  private released = false;
  private stopping = false;
  private disposed = false;
  private timers: ReturnType<typeof setTimeout>[] = [];
  constructor(factory: RecognitionFactory | undefined, notify: (state: RecognitionState) => void) { this.factory = factory; this.notify = notify; }
  private emit(phase: RecognitionState["phase"], error = "") { if (!this.disposed) this.notify({ phase, transcript: this.transcript, error }); }
  private clear() { this.timers.forEach(clearTimeout); this.timers = []; }
  cancel(reset = false) {
    this.generation++; this.clear();
    const old = this.instance; this.instance = null;
    if (old) { old.onstart = old.onaudiostart = old.onend = old.onresult = old.onerror = null; try { old.abort(); } catch {} }
    if (reset) this.transcript = "";
    this.emit("idle");
  }
  private fail(message: string) { this.cancel(); this.emit("idle", message); }
  start(lang: string) {
    if (this.disposed || this.instance) return;
    this.cancel(true);
    if (!this.factory) { this.emit("idle", "Speech recognition is unavailable in this browser. Try a supported browser or keep typing."); return; }
    const token = this.generation;
    this.started = false; this.released = false; this.stopping = false;
    try {
      const recognition = this.factory(); this.instance = recognition;
      recognition.lang = lang; recognition.continuous = true; recognition.interimResults = true;
      recognition.onstart = () => {
        if (token !== this.generation) return;
        this.started = true; this.clear();
        if (this.released) { this.finish(); return; }
        this.emit("listening");
        this.timers.push(setTimeout(() => { if (token === this.generation) this.finish(); }, 30000));
      };
      recognition.onaudiostart = () => { if (token === this.generation && !this.released) this.emit("listening"); };
      recognition.onresult = event => {
        if (token !== this.generation) return;
        this.transcript = Array.from(event.results).map(result => result[0]?.transcript || "").join(" ").replace(/\s+/g, " ").trim();
        this.emit(this.released ? "finishing" : "listening");
      };
      recognition.onend = () => {
        if (token !== this.generation) return;
        this.clear(); this.instance = null; this.generation++;
        this.emit("idle", this.transcript ? "" : "No speech was recognised. Try again or keep typing.");
      };
      recognition.onerror = event => { if (token === this.generation) this.fail(errors[event.error] || "Speech recognition stopped. Try again or keep typing."); };
      this.emit("requesting"); recognition.start();
      this.timers.push(setTimeout(() => { if (token === this.generation && !this.started) this.fail("Speech recognition did not start. Check the browser permission prompt, then try again."); }, 10000));
    } catch { if (token === this.generation) this.fail("Speech recognition could not start. Try again or use typed input."); }
  }
  finish() {
    if (!this.instance) return;
    this.released = true; this.emit("finishing");
    // Some browsers are still waiting for permission when the pointer is released.
    // onstart will stop capture immediately once it becomes active.
    if (!this.started || this.stopping) return;
    this.stopping = true;
    this.clear(); const token = this.generation;
    try { this.instance.stop(); } catch { this.fail("Could not finish recognition. Your recognised words remain available."); return; }
    this.timers.push(setTimeout(() => { if (token === this.generation) { this.cancel(); this.emit("idle", this.transcript ? "" : "Recognition ended without a transcript. Try again or keep typing."); } }, 4000));
  }
  edit(transcript: string) { if (!this.instance) { this.transcript = transcript; this.emit("idle"); } }
  dispose() { this.disposed = true; this.cancel(true); }
}
