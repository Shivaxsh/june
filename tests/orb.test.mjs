import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const load = async path => {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
  return import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'));
};
const { resolveOrb } = await load('../lib/orb/state.ts');
const { AudioController } = await load('../lib/orb/audio-controller.ts');

test('real generation takes priority; ending it resolves the remaining activity honestly', () => {
  assert.deepEqual(resolveOrb(true, false, 'speaking', 'listening'), { mood: 'thinking', label: 'Generating reply' });
  assert.equal(resolveOrb(false, false, 'auto', 'listening').label, 'Listening · sound visualisation only');
  assert.equal(resolveOrb(false, false, 'auto', 'playing').label, 'Audio playback');
  assert.equal(resolveOrb(false, false, 'auto', 'idle').mood, 'idle');
  assert.match(resolveOrb(true, true, 'auto', 'idle').label, /simulated/);
  for (const mood of ['idle', 'listening', 'thinking', 'speaking']) assert.match(resolveOrb(false, false, mood, 'idle').label, /preview/);
});

// Fake media devices exercise ownership/race conditions without accessing a microphone.
function environment() {
  const descriptors = new Map();
  const set = (key, value) => { descriptors.set(key, Object.getOwnPropertyDescriptor(globalThis, key)); Object.defineProperty(globalThis, key, { configurable: true, writable: true, value }); };
  const contexts = [], elements = [], frames = new Map(), revoked = [];
  let pendingResolve, pendingReject;
  const permission = new Promise((resolve, reject) => { pendingResolve = resolve; pendingReject = reject; });
  let stopped = 0;
  const track = { stop() { stopped++; }, onended: null };
  const stream = { getTracks: () => [track], getAudioTracks: () => [track] };
  const node = () => ({ links: [], connect(target) { this.links.push(target); }, disconnect() { this.links = []; } });
  class Context {
    destination = {}; closed = false;
    constructor() { contexts.push(this); }
    createAnalyser() { this.analyser = { ...node(), fftSize: 1024, getFloatTimeDomainData(samples) { samples.fill(.1); } }; return this.analyser; }
    createMediaElementSource() { this.source = node(); return this.source; }
    createMediaStreamSource() { this.source = node(); return this.source; }
    async resume() {}
    async close() { this.closed = true; }
  }
  class Media {
    paused = true; src = ''; onended = null; onerror = null;
    constructor() { elements.push(this); }
    async play() { this.paused = false; }
    pause() { this.paused = true; }
    removeAttribute() { this.src = ''; }
    load() {}
  }
  set('window', { AudioContext: Context }); set('AudioContext', Context); set('Audio', Media);
  set('navigator', { mediaDevices: { getUserMedia: () => permission } });
  let nextFrame = 0;
  set('requestAnimationFrame', cb => { frames.set(++nextFrame, cb); return nextFrame; });
  set('cancelAnimationFrame', id => frames.delete(id));
  const oldCreate = URL.createObjectURL, oldRevoke = URL.revokeObjectURL;
  URL.createObjectURL = () => 'blob:local-test'; URL.revokeObjectURL = url => revoked.push(url);
  return { contexts, elements, frames, revoked, stream, resolve: () => pendingResolve(stream), reject: () => pendingReject(new DOMException('Denied', 'NotAllowedError')), get stopped() { return stopped; }, restore() {
    for (const [key, descriptor] of descriptors) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
    URL.createObjectURL = oldCreate; URL.revokeObjectURL = oldRevoke;
  } };
}
const settle = () => new Promise(resolve => setImmediate(resolve));

test('late microphone permission after Stop cannot reactivate capture', async () => {
  const env = environment(); const states = []; const controller = new AudioController(s => states.push(s));
  try {
    const starting = controller.microphone(); await settle(); controller.stop(); env.resolve(); await starting;
    assert.equal(env.stopped, 1); assert.equal(states.at(-1).phase, 'idle'); assert.equal(env.frames.size, 0);
    assert.equal(env.contexts[0].closed, true);
  } finally { controller.dispose(); env.restore(); }
});
test('a late permission rejection cannot replace a newer playback state', async () => {
  const env = environment(); const states = []; const controller = new AudioController(s => states.push(s));
  try {
    const starting = controller.microphone(); await settle(); await controller.play(); env.reject(); await starting;
    assert.equal(states.at(-1).phase, 'playing'); assert.equal(states.at(-1).error, '');
  } finally { controller.dispose(); env.restore(); }
});
test('microphone measures real samples without a speaker connection and dispose stops tracks', async () => {
  const env = environment(); const states = []; const controller = new AudioController(s => states.push(s));
  try {
    const starting = controller.microphone(); await settle(); env.resolve(); await starting;
    assert.equal(states.at(-1).phase, 'listening'); assert.deepEqual(env.contexts[0].analyser.links, []);
    const callback = env.frames.values().next().value; env.frames.clear(); callback();
    assert.ok(controller.level.current > 0);
    controller.dispose(); assert.equal(env.stopped, 1); assert.equal(env.frames.size, 0); assert.equal(controller.level.current, 0);
  } finally { controller.dispose(); env.restore(); }
});
test('file playback pause/resume retains source; Stop releases URL, graph and media', async () => {
  const env = environment(); const states = []; const controller = new AudioController(s => states.push(s));
  try {
    await controller.play({ name: 'example.wav' }); controller.pause(); assert.equal(states.at(-1).phase, 'paused');
    await controller.play(); assert.equal(env.elements.length, 1); assert.equal(states.at(-1).phase, 'playing');
    controller.stop(); assert.deepEqual(env.revoked, ['blob:local-test']); assert.equal(env.elements[0].paused, true);
    assert.equal(env.contexts[0].closed, true); assert.equal(states.at(-1).phase, 'idle'); assert.equal(env.frames.size, 0);
  } finally { controller.dispose(); env.restore(); }
});
test('permission denial gives an actionable idle error', async () => {
  const env = environment(); const states = []; const controller = new AudioController(s => states.push(s));
  try { const pending = controller.microphone(); await settle(); env.reject(); await pending; assert.equal(states.at(-1).phase, 'idle'); assert.match(states.at(-1).error, /denied/); }
  finally { controller.dispose(); env.restore(); }
});
test('unanswered permission times out; a later grant releases the device', async () => {
  const env = environment(); const states = []; const controller = new AudioController(s => states.push(s));
  const originalSet = globalThis.setTimeout, originalClear = globalThis.clearTimeout;
  let expire;
  globalThis.setTimeout = callback => { expire = callback; return 1; };
  globalThis.clearTimeout = () => {};
  try {
    const starting = controller.microphone(); await settle(); expire();
    assert.equal(states.at(-1).phase, 'idle'); assert.match(states.at(-1).error, /pending/);
    env.resolve(); await starting; assert.equal(env.stopped, 1); assert.equal(env.frames.size, 0);
  } finally { controller.dispose(); globalThis.setTimeout = originalSet; globalThis.clearTimeout = originalClear; env.restore(); }
});
