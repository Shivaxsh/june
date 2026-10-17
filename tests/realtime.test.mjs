import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
async function load(path) {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  const code = path.endsWith('.ts') ? ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText : source;
  return import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
}
const { StreamingResampler } = await load('../public/audio/pcm-stream.js');
const { HandsFreeController } = await load('../lib/voice/realtime-client.ts');

test('resampling preserves packet boundaries and rate over consecutive blocks', () => {
  for (const rate of [16000, 44100, 48000]) {
    const output = [], resampler = new StreamingResampler(rate, pcm => output.push(pcm));
    for (let i = 0; i < rate; i += 128) resampler.push(Float32Array.from({ length: Math.min(128, rate - i) }, (_, j) => .2 * Math.sin(2 * Math.PI * 440 * (i + j) / rate)));
    assert.equal(output.length, 50); assert.ok(output.every(pcm => pcm.byteLength === 640));
    const samples = output.flatMap(p => Array.from(new Int16Array(p)));
    const rms = Math.sqrt(samples.reduce((sum, x) => sum + (x / 32768) ** 2, 0) / samples.length);
    assert.ok(rms > .12 && rms < .16, String(rms));
  }
});

test('downsampling filters above-Nyquist audio instead of aliasing it into speech', () => {
  const output = [], resampler = new StreamingResampler(48000, pcm => output.push(pcm));
  resampler.push(Float32Array.from({ length: 48000 }, (_, i) => .5 * Math.sin(2 * Math.PI * 12000 * i / 48000)));
  const samples = output.flatMap(p => Array.from(new Int16Array(p))).slice(100);
  const rms = Math.sqrt(samples.reduce((sum, x) => sum + (x / 32768) ** 2, 0) / samples.length);
  assert.ok(rms < .025, String(rms));
});

function fixture() {
  const states = [], transcripts = [], wakes = [], cancels = [];
  const input = { stopped: false, async start(_signal, send) { this.send = send; }, stop() { this.stopped = true; } };
  const ws = { readyState: 0, bufferedAmount: 0, sent: [], send(data) { this.sent.push(data); }, close() { this.readyState = 3; } };
  const controller = new HandsFreeController(() => input, () => ws, async () => ({ state: 'ready', websocketUrl: 'ws://127.0.0.1:8001/ws/voice' }), s => states.push(s), {
    transcript: (text, turn) => transcripts.push({ text, turn }), wake: turn => wakes.push(turn), cancel: () => cancels.push(true),
  });
  const event = data => ws.onmessage?.({ data: JSON.stringify({ session: 'session-one', ...data }) });
  return { controller, ws, input, states, transcripts, wakes, cancels, event };
}

test('voice transcripts send once and stale sessions/turns cannot interrupt or send', async () => {
  const f = fixture(); await f.controller.start('normal'); f.ws.readyState = 1; f.ws.onopen();
  f.event({ type: 'ready', turn: 0 }); f.event({ type: 'wake', turn: 1 });
  f.event({ type: 'transcript', text: 'hello', turn: 1, durationMs: 12 });
  f.event({ type: 'transcript', text: 'duplicate', turn: 1, durationMs: 12 });
  f.event({ type: 'wake', turn: 2 }); f.event({ type: 'transcript', text: 'old', turn: 1 });
  f.event({ session: 'different', type: 'wake', turn: 3 });
  assert.deepEqual(f.transcripts, [{ text: 'hello', turn: 1 }]); assert.deepEqual(f.wakes, [1, 2]);
  f.controller.stop(); assert.equal(f.input.stopped, true); assert.equal(f.ws.readyState, 3);
});

test('socket congestion releases microphone and reports the error', async () => {
  const f = fixture(); await f.controller.start('normal'); f.ws.readyState = 1; f.ws.onopen(); f.event({ type: 'ready', turn: 0 });
  f.ws.bufferedAmount = 64001; f.input.send(new ArrayBuffer(640));
  assert.equal(f.input.stopped, true); assert.match(f.states.at(-1).error, /behind|busy/i);
});

test('cancellation during delayed microphone permission prevents a late socket', async () => {
  const f = fixture(); let release;
  f.input.start = async () => await new Promise(resolve => { release = resolve; });
  const start = f.controller.start('normal'); f.controller.stop(); release(); await start;
  assert.equal(f.input.stopped, true); assert.equal(f.ws.onopen, undefined);
});

const { RealtimeCapture } = await load('../lib/voice/realtime-capture.ts');
test('unsupported capture gives an actionable message without requesting permission', async () => {
  const capture = new RealtimeCapture({ current: 0 });
  await assert.rejects(capture.start(new AbortController().signal, () => {}, () => {}), /unavailable.*browser/i);
});
test('microphone denial closes its context; a permission grant after cancel immediately stops tracks', async () => {
  const originalContext = Object.getOwnPropertyDescriptor(globalThis, 'AudioContext');
  const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  const originalNode = Object.getOwnPropertyDescriptor(globalThis, 'AudioWorkletNode');
  const contexts = [];
  class Context {
    constructor() { this.closed = false; contexts.push(this); }
    resume() { return Promise.resolve(); }
    close() { this.closed = true; return Promise.resolve(); }
  }
  const restore = (name, value) => value ? Object.defineProperty(globalThis, name, value) : delete globalThis[name];
  Object.defineProperty(globalThis, 'AudioContext', { value: Context, configurable: true });
  Object.defineProperty(globalThis, 'AudioWorkletNode', { value: function () {}, configurable: true });
  try {
    Object.defineProperty(globalThis, 'navigator', { value: { mediaDevices: { getUserMedia: async () => { throw new DOMException('Denied', 'NotAllowedError'); } } }, configurable: true });
    const denied = new RealtimeCapture({ current: 0 });
    await assert.rejects(denied.start(new AbortController().signal, () => {}, () => {}), { name: 'NotAllowedError' });
    assert.equal(contexts[0].closed, true);
    let grant, stopped = false;
    navigator.mediaDevices.getUserMedia = () => new Promise(resolve => { grant = resolve; });
    const late = new RealtimeCapture({ current: 0 }), abort = new AbortController();
    const pending = late.start(abort.signal, () => {}, () => {});
    abort.abort(); grant({ getTracks: () => [{ stop() { stopped = true; } }] });
    await assert.rejects(pending, /cancelled/);
    assert.equal(stopped, true); assert.equal(contexts[1].closed, true);
  } finally { restore('AudioContext', originalContext); restore('navigator', originalNavigator); restore('AudioWorkletNode', originalNode); }
});

test('connection failures and server errors disarm the input; old callbacks stay inert', async () => {
  const f = fixture(); await f.controller.start('normal'); f.ws.readyState = 1; f.ws.onopen(); f.event({ type:'ready' });
  const late = f.ws.onmessage;
  f.ws.onclose();
  assert.equal(f.input.stopped, true); assert.equal(f.states.at(-1).phase, 'off');
  late({ data: JSON.stringify({ type:'wake', session:'session-one', turn:1 }) });
  assert.deepEqual(f.wakes, []);
});

test('playback feedback is deduplicated and scoped to the current session turn', async () => {
  const f = fixture(); await f.controller.start('normal'); f.ws.readyState = 1; f.ws.onopen(); f.event({ type:'ready' });
  f.event({ type:'wake', turn:1 });
  f.controller.activity('speaking'); f.controller.activity('speaking');
  f.controller.activity('complete'); f.controller.activity('complete');
  const activity = f.ws.sent.filter(value => typeof value === 'string').map(value => JSON.parse(value)).filter(value => value.type === 'activity');
  assert.deepEqual(activity.map(value => [value.phase, value.turn, value.session]), [['speaking', 1, 'session-one'], ['complete', 1, 'session-one']]);
  f.controller.stop();
});

test('worklet bounds packets when the main thread stops acknowledging audio', async () => {
  const source = (await readFile(new URL('../public/audio/realtime-worklet.js', import.meta.url), 'utf8')).replace(/^import[^\n]+\n/, '');
  let Worklet;
  class Processor { constructor() { this.port = { messages: [], postMessage(value) { this.messages.push(value); } }; } }
  Function('AudioWorkletProcessor', 'sampleRate', 'registerProcessor', 'StreamingResampler', source)(Processor, 16000, (_name, value) => Worklet = value, StreamingResampler);
  const worklet = new Worklet();
  const output = [new Float32Array(128)];
  for (let i = 0; i < 400; i++) worklet.process([[new Float32Array(128)]], [output]);
  assert.equal(worklet.port.messages.filter(value => value.pcm).length, 100);
  assert.equal(worklet.port.messages.filter(value => value.error).length, 1);
  assert.equal(worklet.process([], [output]), false);
  assert.equal(output[0].every(value => value === 0), true);
});

test('natural interruption and pause probes are scoped; stale resume cannot revive cancelled playback', async () => {
  const f = fixture(); let held = false, pauses = 0, resumes = 0;
  f.controller.callbacks.pause = () => { held = true; pauses++; return true; };
  f.controller.callbacks.resume = () => { held = false; resumes++; };
  await f.controller.start('normal'); f.ws.readyState = 1; f.ws.onopen(); f.event({ type:'ready' }); f.event({ type:'wake', turn:1 });
  f.event({ type:'probe', turn:1, probe:1 }); f.event({ type:'probe', turn:1, probe:1 });
  assert.equal(pauses, 1); assert.equal(held, true); assert.equal(f.states.at(-1).probing, true);
  assert.ok(f.ws.sent.some(x => typeof x==='string' && JSON.parse(x).type==='probe-paused'));
  f.event({ type:'resume', turn:1, probe:1 }); assert.equal(resumes, 1); assert.equal(held, false);
  f.event({ type:'probe', turn:1, probe:2 }); f.event({ type:'interrupt', turn:2 });
  f.event({ type:'resume', turn:1, probe:2 }); f.event({ type:'interrupt', turn:2 });
  assert.equal(resumes, 1); assert.deepEqual(f.wakes, [1,2]);
  f.event({ type:'transcript', turn:2, text:'Wait, a different question.' });
  f.event({ type:'transcript', turn:1, text:'old' }); assert.equal(f.transcripts.length, 1);
  f.controller.stop();
});

test('deliberately cancelled native pause leaves text generation running; late acknowledgements are ignored', async () => {
  const f = fixture(); let finish;
  f.controller.callbacks.pause = () => new Promise(resolve => { finish=resolve; });
  await f.controller.start('normal'); f.ws.readyState=1; f.ws.onopen(); f.event({type:'ready'}); f.event({type:'wake',turn:1});
  f.event({type:'probe',turn:1,probe:1}); finish(null); await Promise.resolve();
  assert.equal(f.controller.active,true); assert.equal(f.cancels.length,0);
  assert.ok(f.ws.sent.some(x=>typeof x==='string' && JSON.parse(x).type==='probe-cancelled'));
  f.event({type:'probe',turn:1,probe:2}); f.event({type:'interrupt',turn:2}); finish(true); await Promise.resolve();
  assert.equal(f.ws.sent.filter(x=>typeof x==='string' && JSON.parse(x).type==='probe-paused').length,0);
  f.controller.stop();
});
