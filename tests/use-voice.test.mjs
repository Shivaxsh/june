import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

// Drive the hook's effects and rerenders deterministically without a microphone
// or DOM. Dependencies use their real controllers and mocked HTTP responses.
const modules = new Map();
const dataUrl = source => 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
const react = dataUrl(`export const useRef = value => globalThis.voiceHooks.ref(value);
export const useState = value => globalThis.voiceHooks.state(value);
export const useEffect = (effect, deps) => globalThis.voiceHooks.effect(effect, deps);`);
async function moduleUrl(url) {
  if (modules.has(url.href)) return modules.get(url.href);
  let { outputText } = ts.transpileModule(await readFile(url, 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
  for (const match of [...outputText.matchAll(/from ["']([^"']+)["']/g)]) {
    const path = match[1];
    const dependency = path === 'react' ? react : await moduleUrl(path.startsWith('@/')
      ? new URL('../' + path.slice(2) + '.ts', import.meta.url) : new URL(path + '.ts', url));
    outputText = outputText.replace(match[0], `from ${JSON.stringify(dependency)}`);
  }
  const result = dataUrl(outputText); modules.set(url.href, result); return result;
}
const { useVoice } = await import(await moduleUrl(new URL('../components/voice/useVoice.ts', import.meta.url)));
const june = { id: 'kokoro-af-heart', name: 'June', lang: 'en-US', gender: 'female', localService: true, provider: 'kokoro' };
const tick = async () => { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); };
function fixture(speak = 'true') {
  const slots = [], pending = [], cleanups = [], requests = [];
  let cursor = 0;
  const values = new Map([['june-audio-engine-v1', 'browser'], ['june-voice-v1', 'browser-uri|Nicky|en-US'], ['june-speak-replies-v1', speak]]);
  const api = { status: 'ready', provider: 'ready', voices: 'ready', playbackError: false, statusFailures: 0, voiceListFailures: 0 };
  const descriptors = Object.fromEntries(['window', 'document', 'navigator', 'fetch', 'voiceHooks'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  const setGlobal = (key, value) => Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  setGlobal('voiceHooks', {
    ref(value) { const index = cursor++; return slots[index] ??= { current: value }; },
    state(value) { const index = cursor++; if (!(index in slots)) slots[index] = value; return [slots[index], next => { slots[index] = next; }]; },
    effect(effect, deps) {
      const index = cursor++, previous = slots[index];
      if (!previous || deps.some((value, i) => value !== previous[i])) { slots[index] = deps; pending.push(() => { cleanups[index]?.(); cleanups[index] = effect(); }); }
    },
  });
  setGlobal('window', {
    localStorage: { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) },
    addEventListener() {}, removeEventListener() {},
    get speechSynthesis() { throw new Error('Browser synthesis must never be accessed'); },
    get SpeechSynthesisUtterance() { throw new Error('Browser synthesis must never be accessed'); },
  });
  setGlobal('document', { addEventListener() {}, removeEventListener() {} });
  setGlobal('navigator', { mediaDevices: {} });
  setGlobal('fetch', async (path, options) => {
    if (path === '/api/voice/voices') {
      if (api.voiceListFailures > 0) { api.voiceListFailures--; throw new TypeError('Connection closed during restart'); }
      return Response.json({ state: api.voices, voices: [june], message: api.voices });
    }
    if (path === '/api/voice/status') {
      if (api.statusFailures > 0) { api.statusFailures--; throw new TypeError('Connection closed during restart'); }
      return Response.json({ state: api.status, nativeReady: true, provider: 'kokoro', providerState: api.provider, voiceId: june.id, whisperWarm: false, modelWarm: false, voiceWarm: false, ...(api.outputError ? { outputError: api.outputError } : {}), message: api.status });
    }
    if (path === '/api/speech/status') return Response.json({ state: 'ready', message: 'Local transcription ready' });
    requests.push({ path, body: JSON.parse(options.body) });
    if (path.endsWith('/stop')) return Response.json({ stopped: true });
    return new Response(api.playbackError ? '{"type":"error","message":"Provider offline"}\n' : '{"type":"start"}\n{"type":"end"}\n');
  });
  const render = () => { cursor = 0; const result = useVoice(() => {}); pending.splice(0).forEach(effect => effect()); return result; };
  return { api, requests, values, render, close() {
    cleanups.forEach(cleanup => cleanup?.());
    for (const [key, descriptor] of Object.entries(descriptors)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
  } };
}

test('old browser engine and Nicky preferences cannot change June output; saved mute survives mount', async () => {
  const f = fixture('false');
  try {
    f.render(); await tick(); let voice = f.render();
    assert.equal(voice.engine, 'native'); assert.equal(voice.browserCapture, false);
    assert.equal(voice.choices.selected, june.id); assert.equal(voice.support.speech, true);
    assert.equal(voice.speakReplies, false);
    voice.begin(1); voice.push(1, 'Muted reply. '); voice.finish(1); await tick();
    assert.equal(f.requests.length, 0);
    voice.setSpeakReplies(true); voice = f.render();
    voice.begin(2); voice.push(2, 'June reply. '); voice.finish(2); await tick();
    assert.equal(f.requests.filter(r => r.path.endsWith('/speak')).length, 1);
    assert.equal(f.requests.find(r => r.path.endsWith('/speak')).body.voiceId, june.id);
    assert.equal(f.values.get('june-audio-engine-v1'), 'browser');
    assert.equal(f.values.get('june-voice-v1'), 'browser-uri|Nicky|en-US');
    voice.setSpeakReplies(false); assert.equal(f.values.get('june-speak-replies-v1'), 'false');
  } finally { f.close(); }
});

test('voice-list and provider status must both be ready for playback and native hands-free', async () => {
  const f = fixture();
  try {
    f.render(); await tick(); assert.equal(f.render().support.speech, true);
    for (const [status, provider, voices] of [
      ['setup-required', 'setup-required', 'setup-required'],
      ['error', 'error', 'ready'], ['ready', 'error', 'ready'], ['ready', 'ready', 'setup-required'],
    ]) {
      Object.assign(f.api, { status, provider, voices }); f.render().refresh(); await tick();
      const voice = f.render();
      assert.equal(voice.support.speech, false); assert.equal(voice.support.recognition, false);
      // Chat replay and the learning studio's streamed preview use selected.
      assert.equal(voice.choices.selected, '');
      voice.setTranscript('Text remains editable without a provider key.');
      assert.equal(f.render().recognition.transcript, 'Text remains editable without a provider key.');
      assert.equal(voice.choices.options[0].name, 'June');
      const before = f.requests.filter(r => r.path.endsWith('/speak')).length;
      voice.preview(); voice.replay('Readable reply.'); voice.begin(3); voice.push(3, 'No fallback. '); voice.finish(3); await tick();
      assert.equal(f.requests.filter(r => r.path.endsWith('/speak')).length, before);
    }
    Object.assign(f.api, { status: 'ready', provider: 'ready', voices: 'ready' });
    f.render().refresh(); await tick(); assert.equal(f.render().support.speech, true);
    f.api.playbackError = true; f.render().preview(); await tick();
    assert.equal(f.render().speech.error, 'Provider offline');
    assert.equal(f.requests.filter(r => r.path.endsWith('/speak')).length, 1);
  } finally { f.close(); }
});


test('preview and replay work during model warm-up while native hands-free waits for ready', async () => {
  const f = fixture();
  try {
    f.api.status = 'preparing';
    f.render(); await tick(); let voice = f.render();
    assert.equal(voice.audioStatus.state, 'preparing');
    assert.equal(voice.support.speech, true); assert.equal(voice.support.recognition, false);
    assert.equal(voice.choices.selected, june.id);
    voice.preview(); await tick();
    const stopsBeforeRefresh = f.requests.filter(r => r.path.endsWith('/stop')).length;
    await voice.refreshAudio(); await tick();
    assert.equal(f.requests.filter(r => r.path.endsWith('/stop')).length, stopsBeforeRefresh);
    voice = f.render(); voice.replay('Already written reply.'); await tick();
    const speech = f.requests.filter(r => r.path.endsWith('/speak'));
    assert.equal(speech.length, 2); assert.ok(speech.every(r => r.body.voiceId === june.id));
    assert.equal(speech[1].body.text, 'Already written reply.');
    assert.equal(f.render().speech.error, '');
    f.api.status = 'ready'; await voice.refreshAudio(); await tick();
    assert.equal(f.render().support.recognition, true);
  } finally { f.close(); }
});

test('a transient restart recovers Heart controls without reloading or using the microphone', async () => {
  const f = fixture();
  try {
    f.api.statusFailures = 1;
    f.api.voiceListFailures = 1;
    f.render(); await tick();
    assert.equal(f.render().support.speech, false);
    await new Promise(resolve => setTimeout(resolve, 900)); await tick();
    assert.equal(f.render().choices.selected, june.id);
    assert.equal(f.render().support.speech, true);
    assert.deepEqual(f.requests, []);
  } finally { f.close(); }
});

test('a failed audio status is re-checked with backoff, and recovery reloads the voice list without speaking or opening the mic', async () => {
  const timers = [], realSet = globalThis.setTimeout, realClear = globalThis.clearTimeout;
  globalThis.setTimeout = (fn, ms) => { const t = { fn, ms, cleared: false, fired: false }; timers.push(t); return t; };
  globalThis.clearTimeout = t => { if (t && typeof t === 'object') t.cleared = true; };
  const f = fixture();
  const due = ms => timers.filter(t => !t.cleared && !t.fired && t.ms === ms);
  const fire = async ms => { const [t] = due(ms); assert.ok(t, `a ${ms} ms check is scheduled`); t.fired = true; t.fn(); await tick(); f.render(); await tick(); return f.render(); };
  try {
    Object.assign(f.api, { status: 'error', provider: 'error', voices: 'error' });
    f.render(); await tick(); let voice = f.render(); await tick(); voice = f.render();
    assert.equal(voice.choices.selected, '', 'no voice while audio is down');
    assert.equal(voice.audioRecovery.phase, 'unavailable');
    assert.match(voice.audioRecovery.message, /unavailable/i);
    assert.equal(due(2000).length, 1, 'exactly one pending check, not a loop per render');
    voice = await fire(2000);
    assert.equal(due(4000).length, 1, 'still failing: backs off');
    assert.equal(due(2000).length, 0);
    Object.assign(f.api, { status: 'ready', provider: 'ready', voices: 'ready' });
    voice = await fire(4000); await tick(); voice = f.render();
    assert.equal(voice.audioStatus.state, 'ready');
    assert.equal(voice.choices.selected, june.id, 'voice list reloaded without a page reload');
    assert.equal(voice.audioRecovery.phase, 'ready');
    assert.equal(voice.audioRecovery.message, '');
    assert.deepEqual(timers.filter(t => !t.cleared && !t.fired && t.ms >= 2000 && t.ms <= 60000).map(t => t.ms), [30000], 'once ready only the slow health check remains');
    assert.equal(f.requests.filter(r => r.path.endsWith('/speak')).length, 0, 'nothing is spoken on recovery');
  } finally { f.close(); globalThis.setTimeout = realSet; globalThis.clearTimeout = realClear; }
});

test('an output failure withdraws the voice (no claims, no speech) until it clears; voiceWarm false alone does not', async () => {
  const f = fixture();
  try {
    f.render(); await tick(); let voice = f.render();
    assert.equal(voice.choices.selected, june.id, 'healthy with voiceWarm false (prewarm off)');
    assert.equal(voice.support.speech, true);
    f.api.outputError = 'Audio output was interrupted. Reconnecting when June is idle.';
    await voice.refreshAudio(); await tick(); f.render(); voice = f.render();
    assert.equal(voice.choices.selected, '', 'timer claims and hands-free see no ready voice');
    assert.equal(voice.support.speech, false);
    assert.equal(voice.audioRecovery.phase, 'unavailable');
    assert.match(voice.audioRecovery.message, /output stopped working/);
    delete f.api.outputError;
    await voice.refreshAudio(); await tick(); voice = f.render();
    assert.equal(voice.choices.selected, june.id);
    assert.equal(voice.support.speech, true);
    assert.equal(f.requests.filter(r => r.path.endsWith('/speak')).length, 0, 'recovery never speaks');
  } finally { f.close(); }
});

test('a ready page keeps one slow health check, detects a dead helper, backs off, and recovers on its own', async () => {
  const timers = [], realSet = globalThis.setTimeout, realClear = globalThis.clearTimeout;
  globalThis.setTimeout = (fn, ms) => { const t = { fn, ms, cleared: false, fired: false }; timers.push(t); return t; };
  globalThis.clearTimeout = t => { if (t && typeof t === 'object') t.cleared = true; };
  const f = fixture();
  const due = ms => timers.filter(t => !t.cleared && !t.fired && t.ms === ms);
  const fire = async ms => { const [t] = due(ms); assert.ok(t, `a ${ms} ms check is scheduled`); t.fired = true; t.fn(); await tick(); f.render(); await tick(); f.render(); return f.render(); };
  try {
    f.render(); await tick(); f.render(); let voice = f.render();
    assert.equal(voice.audioRecovery.phase, 'ready');
    assert.equal(due(30000).length, 1, 'one health check while ready');
    voice = await fire(30000);
    assert.equal(due(30000).length, 1, 'still healthy: the next health check, still only one');
    f.api.outputError = 'Audio output was interrupted.';   // the JuneAudio worker died
    voice = await fire(30000);
    assert.equal(voice.audioRecovery.phase, 'unavailable');
    assert.equal(voice.choices.selected, '');
    assert.equal(due(2000).length, 1, 'failure budget starts fresh at 2 s');
    voice = await fire(2000);
    assert.equal(due(4000).length, 1);
    delete f.api.outputError;
    voice = await fire(4000);
    assert.equal(voice.audioRecovery.phase, 'ready');
    assert.equal(voice.choices.selected, june.id, 'voice back without a page or app restart');
    assert.equal(due(30000).length, 1, 'back to one health check');
    assert.equal(timers.filter(t => !t.cleared && !t.fired && t.ms >= 2000 && t.ms <= 60000).length, 1, 'a single loop throughout');
    assert.equal(f.requests.filter(r => r.path.endsWith('/speak')).length, 0, 'never speaks');
  } finally { f.close(); globalThis.setTimeout = realSet; globalThis.clearTimeout = realClear; }
});
