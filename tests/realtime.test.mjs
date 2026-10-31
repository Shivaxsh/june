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

// Mock only browser boundaries: all capture lifecycle/constraint logic runs for real.
function captureFixture(t, { capabilities = { echoCancellation: [true, false] }, settings = { echoCancellation: true }, apply, media } = {}) {
  const requests = [], constraints = [], contexts = [], nodes = [], modules = [], packets = [], failures = [];
  const track = new EventTarget();
  Object.assign(track, {
    readyState: 'live', stopped: 0,
    stop() { this.stopped++; this.readyState = 'ended'; },
    getCapabilities() { return typeof capabilities === 'function' ? capabilities() : capabilities; },
    getSettings() { return typeof settings === 'function' ? settings() : settings; },
    applyConstraints(value) { constraints.push(value); return apply ? apply(value, settings) : Promise.resolve(); },
  });
  const stream = { getTracks: () => [track], getAudioTracks: () => [track] };
  class Context {
    constructor() {
      this.state = 'running'; this.closed = false; contexts.push(this);
      this.audioWorklet = { addModule: async path => { modules.push(path); } };
    }
    resume() { return Promise.resolve(); }
    close() { this.closed = true; this.state = 'closed'; return Promise.resolve(); }
    createMediaStreamSource() { return { connect() {}, disconnect() {} }; }
  }
  class Worklet {
    constructor() {
      nodes.push(this); this.disconnected = false;
      this.port = { onmessage: null, closed: false, postMessage() {}, close() { this.closed = true; } };
    }
    connect() {}
    disconnect() { this.disconnected = true; }
  }
  const capture = new RealtimeCapture({ current: 0 });
  const globals = { AudioContext: Context, AudioWorkletNode: Worklet,
    navigator: { mediaDevices: { getUserMedia: async value => { requests.push(value); return media ? media() : stream; } } } };
  const originals = Object.fromEntries(Object.keys(globals).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries(globals)) Object.defineProperty(globalThis, key, { value, configurable: true });
  t.after(() => {
    capture.stop();
    for (const [key, descriptor] of Object.entries(originals)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key];
    }
  });
  const start = (signal = new AbortController().signal) => capture.start(signal, data => packets.push(data), message => failures.push(message));
  return { capture, track, requests, constraints, contexts, nodes, modules, packets, failures, start };
}
const flushCapture = () => new Promise(resolve => setImmediate(resolve));

test('capture upgrades only advertised all and reports the actual system-audio setting', async t => {
  const f = captureFixture(t, { capabilities: { echoCancellation: [true, false, 'all', 'remote-only'] },
    apply: async (_value, settings) => { settings.echoCancellation = 'all'; } });
  await f.start();
  assert.equal(f.requests.length, 1);
  assert.equal(f.requests[0].audio.echoCancellation, true);
  assert.equal(f.requests[0].audio.noiseSuppression, true);
  assert.equal(f.requests[0].audio.autoGainControl, true);
  assert.deepEqual(f.constraints, [{ channelCount: 1, noiseSuppression: true, autoGainControl: true, echoCancellation: { exact: 'all' } }]);
  assert.equal(f.capture.echoMode, 'system-audio');
  assert.equal(f.nodes.length, 1);
  f.capture.stop();
  assert.equal(f.track.readyState, 'ended');
  assert.equal(f.contexts[0].closed, true);
  assert.equal(f.nodes[0].port.closed, true);
  assert.equal(f.capture.echoMode, 'unknown');
});

for (const [name, capabilities, settings, want] of [
  ['boolean capabilities', { echoCancellation: [true, false] }, { echoCancellation: true }, 'browser-managed'],
  ['remote-only capability', { echoCancellation: [true, 'remote-only'] }, { echoCancellation: 'remote-only' }, 'browser-managed'],
  ['disabled processing', { echoCancellation: [false] }, { echoCancellation: false }, 'off'],
  ['missing capabilities and settings', {}, {}, 'unknown'],
  ['throwing capabilities', () => { throw Error('unavailable'); }, { echoCancellation: true }, 'browser-managed'],
  ['malformed capability string', { echoCancellation: 'all' }, { echoCancellation: 'unrecognized' }, 'unknown'],
  ['throwing settings', {}, () => { throw Error('unavailable'); }, 'unknown'],
]) test(`capture keeps boolean request for ${name} and reports settings honestly`, async t => {
  const f = captureFixture(t, { capabilities, settings });
  await f.start();
  assert.equal(f.requests.length, 1);
  assert.equal(f.requests[0].audio.echoCancellation, true);
  assert.deepEqual(f.constraints, []);
  assert.equal(f.capture.echoMode, want);
  assert.equal(f.nodes.length, 1);
});

test('successful optional constraint does not imply a reported system-audio setting', async t => {
  const f = captureFixture(t, { capabilities: { echoCancellation: [true, 'all'] } });
  await f.start();
  assert.deepEqual(f.constraints, [{ channelCount: 1, noiseSuppression: true, autoGainControl: true, echoCancellation: { exact: 'all' } }]);
  assert.equal(f.capture.echoMode, 'browser-managed');
});

test('AEC upgrade preserves the complete track constraint set under replacement semantics', async t => {
  const initial = { channelCount: { exact: 1 }, noiseSuppression: { ideal: true }, autoGainControl: true, sampleRate: { ideal: 48000 } };
  let current = initial;
  const f = captureFixture(t, { capabilities: { echoCancellation: [true, 'all'] },
    apply: async value => { current = value; } });
  f.track.getConstraints = () => current;
  await f.start();
  assert.deepEqual(current, { ...initial, echoCancellation: { exact: 'all' } });
});

for (const synchronous of [false, true]) test(`optional constraint ${synchronous ? 'throw' : 'rejection'} keeps the original capture without permission retry`, async t => {
  const f = captureFixture(t, { capabilities: { echoCancellation: [true, 'all'] }, apply() {
    const error = new DOMException('Cannot satisfy all', 'OverconstrainedError');
    if (synchronous) throw error;
    return Promise.reject(error);
  } });
  await f.start();
  assert.equal(f.constraints.length, 1);
  assert.equal(f.requests.length, 1);
  assert.equal(f.capture.echoMode, 'browser-managed');
  assert.equal(f.track.readyState, 'live');
  assert.equal(f.nodes.length, 1);
  assert.deepEqual(f.failures, []);
});

test('optional upgrade waits at most 750ms; late settings remain observable without another graph', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let finish;
  const settings = { echoCancellation: true };
  const f = captureFixture(t, { capabilities: { echoCancellation: [true, 'all'] }, settings,
    apply: () => new Promise(resolve => { finish = resolve; }) });
  const pending = f.start(); void pending.catch(() => {});
  await flushCapture();
  assert.equal(f.constraints.length, 1);
  t.mock.timers.tick(749); await flushCapture();
  assert.equal(f.nodes.length, 0);
  t.mock.timers.tick(1); await pending;
  assert.equal(f.nodes.length, 1);
  assert.equal(f.capture.echoMode, 'browser-managed');
  settings.echoCancellation = 'all'; finish(); await flushCapture();
  assert.equal(f.capture.echoMode, 'system-audio');
  assert.equal(f.nodes.length, 1);
  assert.equal(f.requests.length, 1);
});

for (const action of ['stop', 'abort']) for (const outcome of ['resolve', 'reject']) test(`${action} releases a delayed optional upgrade immediately and late ${outcome} cannot restart it`, async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let finish, settled = false;
  const f = captureFixture(t, { capabilities: { echoCancellation: [true, 'all'] },
    apply: (_value, settings) => new Promise((resolve, reject) => {
      finish = () => {
        if (outcome === 'reject') reject(Error('late optional rejection'));
        else { settings.echoCancellation = 'all'; resolve(); }
      };
    }) });
  const abort = new AbortController();
  const pending = f.start(abort.signal);
  void pending.then(() => { settled = true; }, () => { settled = true; });
  await flushCapture();
  assert.equal(f.constraints.length, 1);
  if (action === 'stop') f.capture.stop(); else abort.abort();
  await flushCapture(); assert.equal(settled, true);
  await assert.rejects(pending, /cancel|start/i);
  assert.equal(f.track.readyState, 'ended');
  assert.equal(f.contexts[0].closed, true);
  assert.equal(f.capture.echoMode, 'unknown');
  t.mock.timers.tick(750); finish(); await flushCapture();
  assert.equal(f.capture.echoMode, 'unknown');
  assert.equal(f.nodes.length, 0);
  assert.equal(f.modules.length, 0);
  assert.deepEqual(f.packets, []);
  assert.deepEqual(f.failures, []);
});

test('capture denial never retries permission or applies optional constraints', async t => {
  const f = captureFixture(t, { media: async () => { throw new DOMException('Denied', 'NotAllowedError'); } });
  await assert.rejects(f.start(), { name: 'NotAllowedError' });
  assert.equal(f.requests.length, 1);
  assert.deepEqual(f.constraints, []);
  assert.equal(f.contexts[0].closed, true);
  assert.equal(f.capture.echoMode, 'unknown');
});

test('controller publishes optional capture mode, refreshes settings, and clears stale mode on stop/restart', async () => {
  const f = fixture();
  try {
    f.input.echoMode = 'system-audio';
    await f.controller.start('normal');
    assert.equal(f.states.at(-1).echoMode, 'system-audio');
    f.ws.readyState = 1; f.ws.onopen(); f.event({ type: 'ready' });
    f.input.echoMode = 'off'; f.event({ type: 'metrics', vad: .2 });
    assert.equal(f.states.at(-1).echoMode, 'off');
    f.controller.stop();
    assert.equal(f.states.at(-1).echoMode, 'unknown');
    delete f.input.echoMode;
    await f.controller.start('normal');
    assert.equal(f.states.at(-1).echoMode, 'unknown');
  } finally { f.controller.stop(); }
});

test('repeated controller start shares the pending microphone and opens only one connection', async () => {
  const f = fixture(); let release, starts = 0, connects = 0;
  f.input.start = () => { starts++; return new Promise(resolve => { release = resolve; }); };
  f.controller.connect = () => { connects++; return f.ws; };
  try {
    const pending = f.controller.start('normal');
    await f.controller.start('normal');
    assert.equal(starts, 1); assert.equal(connects, 0);
    release(); await pending;
    await f.controller.start('normal');
    assert.equal(starts, 1); assert.equal(connects, 1);
  } finally { f.controller.stop(); }
});

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
test('resampling is independent of chunk sizes at six device sample rates',()=>{
  for(const rate of [16000,22050,24000,44100,48000,96000]) {
    const input=Float32Array.from({length:rate},(_,i)=>.4*Math.sin(2*Math.PI*440*i/rate));
    let reference;
    for(const chunk of [7,128,511]) {
      const packets=[],resampler=new StreamingResampler(rate,pcm=>packets.push(new Uint8Array(pcm)));
      for(let offset=0;offset<input.length;offset+=chunk)resampler.push(input.subarray(offset,offset+chunk));
      assert.equal(packets.length,50,`${rate} Hz, chunk ${chunk}`);
      const bytes=Buffer.concat(packets);
      if(reference)assert.deepEqual(bytes,reference);else reference=bytes;
    }
  }
});
test('nonfinite input becomes silence and clipping remains bounded',()=>{
  const packets=[],resampler=new StreamingResampler(48000,pcm=>packets.push(new Int16Array(pcm)));
  resampler.push(Float32Array.from({length:48000},(_,i)=>i%2?NaN:Infinity));
  assert.ok(packets.length>0);assert.ok(packets.every(p=>p.every(x=>x===0)));
});

test('native session never creates browser capture and forwards owner, voice, mic level and timings', async () => {
  const sent = [], states = [];
  const ws = { readyState: 1, send: data => sent.push(JSON.parse(data)), close() {} };
  const controller = new HandsFreeController(() => { throw Error('Browser microphone must not be requested'); }, () => ws,
    async () => ({ state: 'ready', websocketUrl: 'ws://127.0.0.1:8001/ws/voice', nativeReady: true, audioEngine: 'mac-native', permission: 'not-determined' }), state => states.push(state),
    { wake() {}, transcript() {}, cancel() {} });
  try {
    await controller.start('short', { audioSource: 'native', ownerId: '123e4567-e89b-42d3-a456-426614174000', voiceId: 'com.apple.ttsbundle.siri_nicky_en-US_compact' });
    assert.equal(states.at(-1).phase, 'connecting'); ws.onopen();
    assert.deepEqual(sent[0], { type: 'start', pause: 'short', audioSource: 'native', ownerId: '123e4567-e89b-42d3-a456-426614174000', voiceId: 'com.apple.ttsbundle.siri_nicky_en-US_compact' });
    const event = data => ws.onmessage({ data: JSON.stringify({ session: 'native-session', ...data }) });
    event({ type: 'ready', session: 'native-session' });
    assert.equal(states.at(-1).sessionId, 'native-session'); assert.equal(controller.sessionId, 'native-session');
    event({ type: 'state', turn: 0, phase: 'requesting', permission: 'requesting' });
    assert.equal(states.at(-1).phase, 'requesting');
    event({ type: 'state', turn: 0, phase: 'preparing', permission: 'granted' });
    assert.equal(states.at(-1).phase, 'preparing');
    event({ type: 'metrics', level: .42, vad: .7 });
    assert.equal(states.at(-1).level, .42);
    event({ type: 'timing', turn: 0, stage: 'whisper', durationMs: 123 });
    assert.equal(states.at(-1).timings.whisper, 123);
  } finally { controller.stop(); }
});

test('native microphone preparation can arrive before ready and never acquires browser capture', async () => {
  const states = [], ws = { readyState: 1, send() {}, close() {} };
  const controller = new HandsFreeController(() => { throw Error('must not capture'); }, () => ws,
    async () => ({ state: 'ready', nativeReady: true, websocketUrl: 'ws://127.0.0.1:8001/ws/voice' }), state => states.push(state), { wake() {}, transcript() {}, cancel() {} });
  try {
    await controller.start('short', { audioSource: 'native', ownerId: '123e4567-e89b-42d3-a456-426614174000', voiceId: 'nicky' }); ws.onopen();
    ws.onmessage({ data: JSON.stringify({ type: 'state', phase: 'requesting', permission: 'requesting' }) });
    assert.equal(states.at(-1).phase, 'requesting'); assert.equal(states.at(-1).permission, 'requesting');
    ws.onmessage({ data: JSON.stringify({ type: 'ready', session: '123e4567-e89b-42d3-a456-426614174001' }) });
    assert.equal(controller.sessionId, '123e4567-e89b-42d3-a456-426614174001');
  } finally { controller.stop(); }
});

test('voice status adapter validates readiness while preserving native permission and warming fields', async () => {
  const { fetchVoiceConfig } = await load('../lib/voice/realtime-client.ts');
  const data = { state: 'ready', message: 'Native ready', audioEngine: 'mac-native', nativeReady: true, permission: 'not-determined', whisperWarm: false, modelWarm: true };
  assert.deepEqual(await fetchVoiceConfig(new AbortController().signal, async () => Response.json(data)), data);
  await assert.rejects(() => fetchVoiceConfig(new AbortController().signal, async () => Response.json({ state: 3 })), /status|unavailable/i);
});

test('hands-free timings are scoped to the current session and turn rather than mixed with earlier questions', async () => {
  const f = fixture();
  try {
    await f.controller.start('short'); f.ws.readyState = 1; f.ws.onopen(); f.event({ type: 'ready', turn: 0 }); f.event({ type: 'wake', turn: 1 });
    f.event({ type: 'timing', turn: 1, stage: 'endDetection', durationMs: 800 });
    f.event({ type: 'timing', turn: 1, stage: 'transcription', durationMs: 230 });
    assert.deepEqual(f.states.at(-1).timings, { endDetection: 800, transcription: 230 });
    f.event({ type: 'wake', turn: 2 }); assert.deepEqual(f.states.at(-1).timings, {});
    f.event({ type: 'timing', turn: 1, stage: 'transcription', durationMs: 999 });
    f.event({ type: 'timing', session: 'old-session', turn: 2, stage: 'endDetection', durationMs: 999 });
    f.event({ type: 'timing', turn: 2, stage: 'transcription', durationMs: -1 });
    assert.deepEqual(f.states.at(-1).timings, {});
    f.event({ type: 'timing', turn: 2, stage: 'endDetection', durationMs: 0 });
    assert.deepEqual(f.states.at(-1).timings, { endDetection: 0 });
  } finally { f.controller.stop(); }
});
