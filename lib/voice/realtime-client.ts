import type { EchoMode } from './realtime-capture';

export type HandsFreePhase = 'off' | 'requesting' | 'connecting' | 'preparing' | 'waiting' | 'listening' | 'transcribing' | 'generating' | 'speaking' | 'followup';
export type NativePermission = 'not-determined' | 'requesting' | 'granted' | 'denied' | 'restricted' | string;
export type VoiceConfig = { state: string; websocketUrl?: string; message?: string; audioEngine?: string; nativeReady?: boolean; permission?: NativePermission; whisperWarm?: boolean; modelWarm?: boolean };
export type AudioSourceOptions = { audioSource: 'native' | 'browser'; ownerId?: string; voiceId?: string };
export type HandsFreeState = { phase: HandsFreePhase; error: string; turn: number; vad: number; transcriptionMs: number; probing?: boolean; echoMode?: EchoMode; sessionId?: string; audioSource?: 'native' | 'browser'; permission?: NativePermission; level?: number; timings?: Record<string, number> };
type Input = { readonly echoMode?: EchoMode; start(signal: AbortSignal, packet: (data: ArrayBuffer) => void, fail: (message: string) => void): Promise<void>; stop(): void };

export async function fetchVoiceConfig(signal: AbortSignal, http: typeof fetch = fetch): Promise<VoiceConfig> {
  const response = await http('/api/voice/status', { cache: 'no-store', signal });
  const data = await response.json();
  if (!response.ok || typeof data?.state !== 'string' || typeof data?.message !== 'string') throw Error('Hands-free status is unavailable. Restart June, then refresh.');
  return data as VoiceConfig;
}
type Config = VoiceConfig;
type Callbacks = { wake(turn: number): void; transcript(text: string, turn: number): void; cancel(): void; pause?(): boolean | Promise<boolean | null>; resume?(): void };
const phases = ['requesting', 'preparing', 'waiting', 'listening', 'transcribing', 'generating', 'speaking', 'followup'];

export class HandsFreeController {
  private token = 0;
  private input: Input | null = null;
  private source: 'native' | 'browser' = 'browser';
  private socket: WebSocket | null = null;
  private abort: AbortController | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private heartbeat: ReturnType<typeof setInterval> | undefined;
  private session = '';
  private accepted = 0;
  private lastActivity = '';
  private incoming = 0;
  private probe = 0;
  private lastProbe = 0;
  private state: HandsFreeState = { phase: 'off', error: '', turn: 0, vad: 0, transcriptionMs: 0, echoMode: 'unknown' };
  constructor(private factory: () => Input, private connect: (url: string) => WebSocket,
    private config: (signal: AbortSignal) => Promise<Config>, private notify: (state: HandsFreeState) => void, private callbacks: Callbacks) {}
  private emit(change: Partial<HandsFreeState>) {
    const newTurn = change.turn !== undefined && change.turn > this.state.turn;
    this.state = { ...this.state, ...(newTurn ? { timings: {}, transcriptionMs: 0 } : {}), ...change, echoMode: this.input?.echoMode ?? 'unknown' };
    this.notify(this.state);
  }
  get sessionId() { return this.session; }
  get active() { return this.state.phase !== 'off'; }
  stop(message = '') {
    const wasActive = this.active;
    this.token++; clearTimeout(this.timer); clearInterval(this.heartbeat);
    this.abort?.abort(); this.abort = null;
    this.input?.stop(); this.input = null;
    if (this.socket) { this.socket.onopen = this.socket.onmessage = this.socket.onerror = this.socket.onclose = null; this.socket.close(); this.socket = null; }
    this.session = ''; this.accepted = 0; this.lastActivity = ''; this.probe = this.lastProbe = 0;
    this.emit({ phase: 'off', error: message, turn: 0, vad: 0, probing: false, level: 0, sessionId: '' });
    if (wasActive) this.callbacks.cancel();
  }
  async start(pause: string, options: AudioSourceOptions = { audioSource: 'browser' }) {
    if (this.active) return;
    const token = ++this.token;
    this.source = options.audioSource;
    this.emit({ phase: 'requesting', error: '', turn: 0, transcriptionMs: 0, audioSource: this.source, level: 0, timings: {}, permission: undefined });
    const abort = new AbortController(); this.abort = abort;
    this.timer = setTimeout(() => this.stop('Microphone or voice setup is still pending. Answer the permission prompt, then try again.'), 45000);
    try {
      // Native capture belongs to the Mac helper. Even constructing a browser
      // input here can acquire audio resources, so branch before the factory.
      const input = this.source === 'browser' ? this.factory() : null; this.input = input;
      const [config] = await Promise.all([this.config(abort.signal), input?.start(abort.signal, data => this.packet(data), message => this.stop(message))]);
      if (token !== this.token) { input?.stop(); return; }
      if (this.source === 'native') {
        if (!config.nativeReady || !options.ownerId || !options.voiceId) throw new Error(config.message || 'Native audio is not ready. Refresh audio or choose browser audio explicitly.');
        this.emit({ permission: config.permission });
      }
      if (config.state !== 'ready' || !config.websocketUrl) throw new Error(config.message || 'Local hands-free is not ready. Run its setup, then refresh.');
      const url = new URL(config.websocketUrl);
      if (url.protocol !== 'ws:' || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) || url.pathname !== '/ws/voice' || url.username || url.password || url.search || url.hash) throw new Error('Hands-free must connect to June’s local server.');
      const socket = this.connect(url.href); this.socket = socket;
      this.emit({ phase: 'connecting' });
      socket.onopen = () => { if (token === this.token) socket.send(JSON.stringify({ type: 'start', pause, ...(this.source === 'native' ? options : {}) })); };
      socket.onmessage = event => {
        if (token !== this.token) return;
        this.incoming = Date.now();
        try { this.receive(JSON.parse(event.data)); } catch { this.stop('The voice connection sent an invalid update. Enable hands-free again.'); }
      };
      socket.onerror = () => { if (token === this.token) this.stop('The local voice connection failed. Restart June and enable hands-free again.'); };
      socket.onclose = () => { if (token === this.token) this.stop('The local voice connection closed. Enable hands-free again when June is ready.'); };
    } catch (error) {
      if (token !== this.token) return;
      const message = error instanceof DOMException && error.name === 'NotAllowedError'
        ? 'Microphone permission was denied. Allow access in browser settings, then try again.'
        : error instanceof Error ? error.message : 'Could not start the microphone. Check your device and try again.';
      this.stop(message);
    }
  }
  private packet(data: ArrayBuffer) {
    if (!this.session || this.socket?.readyState !== 1) return;
    if (this.socket.bufferedAmount > 64000) { this.stop('The microphone connection fell behind. Close busy apps and try again.'); return; }
    this.socket.send(data);
  }
  private receive(value: unknown) {
    if (!value || typeof value !== 'object') throw Error();
    const event = value as { type?: string; session?: string; turn?: number; phase?: HandsFreePhase; text?: string; durationMs?: number; message?: string; fatal?: boolean; vad?: number; probe?: number; level?: number; permission?: NativePermission; stage?: string };
    if (!this.session && event.type === 'state' && (event.phase === 'requesting' || event.phase === 'preparing')) {
      this.emit({ phase: event.phase, ...(typeof event.permission === 'string' ? { permission: event.permission } : {}) }); return;
    }
    if (event.type === 'error' && event.fatal && !this.session) { this.stop(event.message || 'Hands-free is unavailable.'); return; }
    if (event.type === 'ready' && typeof event.session === 'string' && !this.session) {
      this.session = event.session; clearTimeout(this.timer); this.incoming = Date.now();
      this.heartbeat = setInterval(() => {
        if (Date.now() - this.incoming > 15000) { this.stop('The local voice server stopped responding. Restart June and enable hands-free again.'); return; }
        this.send({ type: 'ping' });
      }, 5000);
      this.emit({ phase: 'waiting', sessionId: this.session, ...(typeof event.permission === 'string' ? { permission: event.permission } : {}) }); return;
    }
    if (!this.session || event.session !== this.session) return;
    if (event.type === 'pong') return;
    if (event.type === 'metrics') {
      const change: Partial<HandsFreeState> = {};
      if (typeof event.vad === 'number' && Number.isFinite(event.vad)) change.vad = Math.min(1, Math.max(0, event.vad));
      if (typeof event.level === 'number' && Number.isFinite(event.level)) change.level = Math.min(1, Math.max(0, event.level));
      this.emit(change); return;
    }
    if (event.type === 'timing') {
      if (event.turn !== undefined && event.turn !== this.state.turn) return;
      if (typeof event.stage === 'string' && /^[a-z][a-z0-9_-]{0,39}$/i.test(event.stage) && typeof event.durationMs === 'number' && Number.isFinite(event.durationMs) && event.durationMs >= 0) {
        console.debug('[June timing]', JSON.stringify({ event: 'input-stage', at: Date.now(), session: this.session, turn: event.turn, stage: event.stage, durationMs: event.durationMs }));
        this.emit({ timings: { ...this.state.timings, [event.stage]: event.durationMs } });
      }
      return;
    }
    if (event.type === 'error') {
      if (event.fatal) this.stop(event.message || 'The voice session failed.');
      else this.emit({ error: event.message || 'That question could not be transcribed. Try again.' });
      return;
    }
    if (!Number.isSafeInteger(event.turn) || event.turn! < this.state.turn || event.turn! < 0) return;
    if (event.type === 'probe' && event.turn === this.state.turn && Number.isSafeInteger(event.probe) && event.probe! > this.lastProbe) {
      this.probe = this.lastProbe = event.probe!;
      const token = this.token, session = this.session;
      const acknowledge = (paused: boolean | null) => {
        if (token !== this.token || session !== this.session || event.turn !== this.state.turn || event.probe !== this.probe) return;
        if (paused === null) {
          this.probe = 0; this.emit({ probing: false });
          this.send({ type: 'probe-cancelled', turn: event.turn, probe: event.probe }); return;
        }
        if (!paused) { this.stop('Voice could not pause for your interruption. Try another browser or press Stop.'); return; }
        this.emit({ probing: true });
        this.send({ type: 'probe-paused', turn: event.turn, probe: event.probe });
      };
      const result = this.callbacks.pause?.() ?? false;
      if (typeof result === 'boolean') acknowledge(result);
      else void result.then(acknowledge, () => acknowledge(false));
    } else if (event.type === 'resume' && event.turn === this.state.turn && this.probe > 0 && event.probe === this.probe) {
      this.probe = 0; this.emit({ probing: false }); this.callbacks.resume?.();
    } else if ((event.type === 'wake' || event.type === 'interrupt') && event.turn! > this.state.turn) {
      console.debug('[June voice]', JSON.stringify({event:event.type,at:Date.now(),turn:event.turn,previousPhase:this.state.phase}));
      this.probe = 0;
      this.emit({ turn: event.turn, phase: 'listening', error: '', probing: false }); this.callbacks.wake(event.turn!);
    } else if (event.type === 'state' && event.phase && phases.includes(event.phase)) {
      this.emit({ turn: event.turn, phase: event.phase, ...(typeof event.permission === 'string' ? { permission: event.permission } : {}) });
    } else if (event.type === 'transcript' && event.turn === this.state.turn && event.turn! > this.accepted && typeof event.text === 'string' && event.text.trim()) {
      this.accepted = event.turn!;
      this.emit({ transcriptionMs: event.durationMs || 0, error: '' });
      this.callbacks.transcript(event.text.trim(), event.turn!);
    }
  }
  private send(value: Record<string, unknown>) {
    if (this.session && this.socket?.readyState === 1) this.socket.send(JSON.stringify({ ...value, session: this.session }));
  }
  activity(phase: 'generating' | 'speaking' | 'complete' | 'failed', text = '') {
    const reference = phase === 'speaking' ? text.slice(0, 4000) : '';
    const key = `${this.state.turn}:${phase}:${reference}`;
    if (!this.session || this.state.turn === 0 || this.lastActivity === key) return;
    this.lastActivity = key; this.send({ type: 'activity', turn: this.state.turn, phase, text: reference });
  }
}
