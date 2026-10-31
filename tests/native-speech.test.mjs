import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const modules = new Map();
async function moduleUrl(url) {
  if (modules.has(url.href)) return modules.get(url.href);
  const source = await readFile(url, 'utf8');
  let { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
  for (const match of [...outputText.matchAll(/from ["'](\.[^"']+)["']/g)]) {
    const dependency = await moduleUrl(new URL(match[1] + '.ts', url));
    outputText = outputText.replace(match[0], `from ${JSON.stringify(dependency)}`);
  }
  const result = 'data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'); modules.set(url.href, result); return result;
}
const load = async path => import(await moduleUrl(new URL(path, import.meta.url)));
const { NativeSpeechController, NativeVoiceRegistry } = await load('../lib/voice/native-speech.ts');
const nicky = { id: 'com.apple.ttsbundle.siri_nicky_en-US_compact', name: 'Nicky', lang: 'en-US', gender: 'female', localService: true };
const voice = { ...nicky, voiceURI: nicky.id, default: false };
const tick = async () => { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); };
function fixture(now) {
  const requests = [], stops = [], states = [];
  const http = async (path, options) => {
    const body = JSON.parse(options.body);
    if (path.endsWith('/stop')) { stops.push(body); return new Response('{}'); }
    let output;
    const stream = new ReadableStream({ start(controller) { output = controller; } });
    const request = { body, signal: options.signal, event(value) { try { output.enqueue(new TextEncoder().encode(JSON.stringify(value) + '\n')); } catch {} }, close() { try { output.close(); } catch {} } };
    requests.push(request);
    return new Response(stream);
  };
  const controller = new NativeSpeechController(state => states.push(state), { current: 0 }, http, undefined, now);
  return { controller, requests, stops, states };
}
test('native playback waits for real start, prefetches at most two and preserves waiting until the whole reply ends', async () => {
  const f = fixture();
  try {
    f.controller.begin(1, voice, true, true, { voiceSessionId: '123e4567-e89b-42d3-a456-426614174001', turnId: 3 }); f.controller.push(1, 'First. Second. Third. Tail');
    await tick(); assert.equal(f.requests.length, 2); assert.equal(f.states.at(-1).phase, 'waiting');
    assert.equal(f.requests[0].body.voiceId, nicky.id);
    assert.equal(f.requests[0].body.voiceSessionId, '123e4567-e89b-42d3-a456-426614174001'); assert.equal(f.requests[0].body.turnId, 3);
    assert.equal(f.requests[0].body.ownerId, f.controller.ownerId);
    assert.match(f.requests[0].body.requestId, /^[0-9a-f-]{36}$/i);
    assert.notEqual(f.requests[0].body.segmentId, f.requests[1].body.segmentId);
    f.requests[0].event({ type: 'start', approximate: true }); await tick(); assert.equal(f.states.at(-1).phase, 'speaking');
    assert.equal(f.controller.activity.current, 0);
    f.requests[0].event({ type: 'boundary', charIndex: 0, charLength: 5, level: .6, approximate: true }); await tick();
    assert.equal(f.controller.activity.current, .6); assert.equal(f.states.at(-1).end, 5); assert.equal(f.states.at(-1).approximate, true);
    f.requests[0].event({ type: 'end', approximate: true }); await tick();
    assert.equal(f.requests.length, 3); assert.equal(f.states.at(-1).phase, 'waiting');
    f.controller.finish(1); f.requests[1].event({ type: 'end' }); await tick();
    assert.equal(f.requests.length, 4);
    f.requests[2].event({ type: 'end' }); f.requests[3].event({ type: 'end' }); await tick();
    assert.equal(f.states.at(-1).phase, 'idle');
  } finally { f.controller.dispose(); }
});
test('native stop aborts HTTP and queued work; late old events never replace a new epoch', async () => {
  const f = fixture();
  try {
    f.controller.begin(1, voice, true); f.controller.push(1, 'Old. Another. Queued. Tail'); await tick();
    const old = f.requests[0];
    f.controller.replay('New reply.', voice); await tick();
    const current = f.requests.at(-1);
    assert.equal(old.signal.aborted, true);
    assert.deepEqual(f.stops[0], { ownerId: f.controller.ownerId, requestId: old.body.requestId });
    assert.notEqual(current.body.requestId, old.body.requestId);
    current.event({ type: 'start' }); await tick();
    old.event({ type: 'error', message: 'Late failure' }); old.event({ type: 'end' }); await tick();
    assert.equal(f.states.at(-1).caption, 'New reply.'); assert.equal(f.states.at(-1).phase, 'speaking');
    f.controller.stop(); assert.equal(current.signal.aborted, true); assert.equal(f.states.at(-1).phase, 'idle');
    f.controller.push(1, 'Late. Text'); await tick(); assert.equal(f.requests.length, 3);
  } finally { f.controller.dispose(); }
});
test('native playback errors and truncated event streams clear the queue without automatic retry', async () => {
  const f = fixture();
  try {
    f.controller.begin(1, voice, true); f.controller.push(1, 'First. Second. Third. Tail'); await tick();
    f.requests[0].close(); await tick();
    assert.equal(f.states.at(-1).phase, 'idle'); assert.match(f.states.at(-1).error, /ended|stream/i);
    assert.equal(f.requests[1].signal.aborted, true); assert.equal(f.requests.length, 2);
  } finally { f.controller.dispose(); }
});
test('native segments respect text cap and supported expression rates without reading fenced code', async () => {
  const f = fixture();
  try {
    f.controller.setRate(.92);
    f.controller.replay('Hello. ```js\nsecret()\n``` ' + 'word '.repeat(700), voice); await tick();
    assert.equal(f.requests.length, 2);
    for (const request of f.requests) { assert.ok(request.body.text.length <= 2000); assert.equal(request.body.rate, .92); assert.doesNotMatch(request.body.text, /secret/); }
    assert.equal(f.stops.length, 0); // output preview acquires playback only
  } finally { f.controller.dispose(); }
});
test('native voice registry migrates browser Nicky preference by name and language without overwriting it', async () => {
  const preference = 'browser-voice-uri|Nicky|en-US', values = new Map([['june-voice-v1', preference]]), states = [];
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  const registry = new NativeVoiceRegistry(storage, state => states.push(state), async () => Response.json({ state: 'ready', voices: [{ ...nicky, id: 'samantha', name: 'Samantha' }, nicky], message: 'Ready' }));
  try {
    await registry.refresh(); assert.equal(states.at(-1).selected, nicky.id);
    assert.equal(registry.get(nicky.id).voiceURI, nicky.id); assert.equal(values.get('june-voice-v1'), preference);
  } finally { registry.dispose(); }
});

test('prefetch waits for preceding response headers and late headers cannot revive a revoked request', async () => {
  const pending = [], states = [];
  const http = (path, options) => {
    if (path.endsWith('/stop')) return Promise.resolve(Response.json({}));
    return new Promise(resolve => pending.push({ body: JSON.parse(options.body), signal: options.signal, accept: () => resolve(new Response(new ReadableStream())) }));
  };
  const controller = new NativeSpeechController(state => states.push(state), { current: 0 }, http);
  try {
    controller.begin(1, voice, true); controller.push(1, 'First. Second. Third. Tail'); await tick();
    assert.equal(pending.length, 1);
    pending[0].accept(); await tick(); assert.equal(pending.length, 2);
    const old = pending[1]; controller.replay('Replacement.', voice); await tick();
    assert.equal(pending.length, 3); assert.equal(old.signal.aborted, true);
    old.accept(); await tick(); assert.equal(pending.length, 3);
    assert.equal(states.at(-1).phase, 'waiting');
  } finally { controller.dispose(); }
});

test('voice refresh errors clear stale selections and never overwrite a saved native preference', async () => {
  const values = new Map([['june-voice-v1', nicky.id]]), states = []; let available = true;
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  const registry = new NativeVoiceRegistry(storage, state => states.push(state), async () => available
    ? Response.json({ state: 'ready', voices: [nicky, { ...nicky, id: 'male', name: 'Rishi', gender: 'male' }], message: 'Ready' })
    : Response.json({ state: 'missing', voices: [], message: 'Install June Audio' }));
  try {
    await registry.refresh(); assert.equal(states.at(-1).options.length, 1); assert.equal(states.at(-1).selected, nicky.id);
    available = false; await registry.refresh(); assert.equal(states.at(-1).selected, ''); assert.equal(states.at(-1).options.length, 0);
    assert.equal(values.get('june-voice-v1'), nicky.id);
  } finally { registry.dispose(); }
});

test('hands-free playback without a live capture session cannot submit unbound native speech', async () => {
  const f = fixture();
  try {
    f.controller.begin(1, voice, true, true); f.controller.push(1, 'Unbound. Reply'); await tick();
    assert.equal(f.requests.length, 0); assert.match(f.states.at(-1).error, /session/i);
  } finally { f.controller.dispose(); }
});

test('native timings follow real events, survive boundaries and stream completion, and reject stale event IDs', async () => {
  let now = 100;
  const f = fixture(() => now);
  try {
    f.controller.begin(1, voice, true); now = 140; f.controller.push(1, 'One sentence. '); await tick();
    assert.equal(f.states.at(-1).timings, undefined);
    const first = f.requests[0];
    now = 200; first.event({ type: 'start', firstAudioMs: 31 }); await tick();
    assert.deepEqual(f.states.at(-1).timings, { firstAudioMs: 100, playbackMs: 0, nativeFirstAudioMs: 31 });
    now = 250; first.event({ type: 'boundary', charIndex: 0, charLength: 3 }); await tick();
    assert.equal(f.states.at(-1).timings.firstAudioMs, 100); assert.equal(f.states.at(-1).timings.playbackMs, 50);
    now = 300; first.event({ type: 'end', playbackMs: 80 }); await tick();
    const completed = { firstAudioMs: 100, playbackMs: 100, totalMs: 200, nativeFirstAudioMs: 31, nativePlaybackMs: 80 };
    assert.equal(f.states.at(-1).phase, 'waiting'); assert.deepEqual(f.states.at(-1).timings, completed);
    f.controller.finish(1); assert.equal(f.states.at(-1).phase, 'idle'); assert.deepEqual(f.states.at(-1).timings, completed);
    now = 350; f.controller.replay('Replacement.', voice); await tick();
    assert.equal(f.states.at(-1).timings, undefined);
    const second = f.requests.at(-1);
    now = 400; second.event({ type: 'start', requestId: first.body.requestId, firstAudioMs: 999 }); await tick();
    assert.equal(f.states.at(-1).phase, 'waiting'); assert.equal(f.states.at(-1).timings, undefined);
    now = 500; second.event({ type: 'start', ...second.body, firstAudioMs: -1 }); await tick();
    assert.deepEqual(f.states.at(-1).timings, { firstAudioMs: 150, playbackMs: 0 });
    now = 550; second.event({ type: 'end', segmentId: first.body.segmentId, playbackMs: 999 }); await tick();
    assert.equal(f.states.at(-1).phase, 'speaking'); assert.equal(f.states.at(-1).timings.playbackMs, 0);
    now = 600; second.event({ type: 'end', playbackMs: 90 }); await tick();
    assert.equal(f.states.at(-1).timings.totalMs, 250); assert.equal(f.states.at(-1).timings.playbackMs, 100);
    f.controller.stop(); assert.equal(f.states.at(-1).timings, undefined);
  } finally { f.controller.dispose(); }
});

test('reply timing keeps the first audio origin across prefetched segments and measures each observed end', async () => {
  let now = 0;
  const f = fixture(() => now);
  try {
    f.controller.begin(1, voice, true); now = 10; f.controller.push(1, 'First. Second. '); f.controller.finish(1); await tick();
    now = 100; f.requests[0].event({ type: 'start', firstAudioMs: 20 }); await tick();
    now = 200; f.requests[0].event({ type: 'end', playbackMs: 95 }); await tick();
    const afterFirst = f.states.at(-1);
    assert.equal(afterFirst.phase, 'waiting'); assert.equal(afterFirst.timings.firstAudioMs, 100);
    now = 240; f.requests[1].event({ type: 'start', firstAudioMs: 35 }); await tick();
    assert.equal(f.states.at(-1).timings.firstAudioMs, 100); assert.equal(f.states.at(-1).timings.nativeFirstAudioMs, 20);
    now = 400; f.requests[1].event({ type: 'end', playbackMs: 155 }); await tick();
    assert.equal(f.states.at(-1).phase, 'idle');
    assert.deepEqual(f.states.at(-1).timings, { firstAudioMs: 100, playbackMs: 300, totalMs: 400, nativeFirstAudioMs: 20, nativePlaybackMs: 155 });
    assert.equal(afterFirst.timings.totalMs, 200); // earlier state snapshots stay immutable
  } finally { f.controller.dispose(); }
});

test('delayed earlier segment events cannot replace prefetched playback captions or RMS', async () => {
  const f = fixture();
  try {
    f.controller.begin(1, voice, true); f.controller.push(1, 'First. Second. '); f.controller.finish(1); await tick();
    assert.equal(f.requests.length, 2);
    const [first, second] = f.requests;
    second.event({ type: 'start' });
    second.event({ type: 'boundary', charIndex: 1, charLength: 3, level: .6 }); await tick();
    const speaking = f.states.at(-1);
    assert.equal(speaking.caption, 'Second.'); assert.equal(speaking.phase, 'speaking');
    first.event({ type: 'start' });
    first.event({ type: 'boundary', charIndex: 0, charLength: 5, level: .1 }); await tick();
    assert.equal(f.states.at(-1), speaking); assert.equal(f.controller.activity.current, .6);
    first.event({ type: 'end' }); await tick();
    assert.equal(f.states.at(-1), speaking); assert.equal(f.controller.activity.current, .6);
    assert.equal(f.stops.length, 0); assert.equal(second.signal.aborted, false);
    second.event({ type: 'boundary', charIndex: 4, charLength: 2, level: .8 }); await tick();
    assert.equal(f.states.at(-1).caption, 'Second.'); assert.equal(f.states.at(-1).phase, 'speaking');
    assert.equal(f.states.at(-1).start, 4); assert.equal(f.controller.activity.current, .8);
    second.event({ type: 'end' }); await tick();
    assert.equal(f.states.at(-1).phase, 'idle'); assert.equal(f.controller.activity.current, 0);
  } finally { f.controller.dispose(); }
});

test('completed newer playback cannot be revived by an older start and a new request resets ordering', async () => {
  const f = fixture();
  try {
    f.controller.begin(1, voice, true); f.controller.push(1, 'First. Second. '); f.controller.finish(1); await tick();
    const [first, second] = f.requests;
    second.event({ type: 'start' }); second.event({ type: 'end' }); await tick();
    const waiting = f.states.at(-1);
    assert.equal(waiting.phase, 'waiting');
    first.event({ type: 'start' });
    first.event({ type: 'boundary', charIndex: 0, charLength: 5, level: .9 }); await tick();
    assert.equal(f.states.at(-1), waiting); assert.equal(f.controller.activity.current, 0);
    first.event({ type: 'end' }); await tick();
    assert.equal(f.states.at(-1).phase, 'idle');
    f.controller.replay('Replacement.', voice); await tick();
    f.requests[2].event({ type: 'start' }); await tick();
    assert.equal(f.states.at(-1).phase, 'speaking'); assert.equal(f.states.at(-1).caption, 'Replacement.');
    f.requests[2].event({ type: 'end' }); await tick();
    assert.equal(f.states.at(-1).phase, 'idle');
  } finally { f.controller.dispose(); }
});

test('native HTTP clients preserve the Window receiver required by browser fetch', async () => {
  let calls=0;
  async function browserFetch(path) {
    assert.equal(this,globalThis); calls++;
    if(path.endsWith('/voices'))return Response.json({state:'ready',voices:[nicky]});
    if(path.endsWith('/stop'))return Response.json({stopped:true});
    return new Response(new TextEncoder().encode('{"type":"start"}\n{"type":"end"}\n'));
  }
  const registry=new NativeVoiceRegistry(undefined,()=>{},browserFetch);
  const controller=new NativeSpeechController(()=>{},{current:0},browserFetch);
  try {
    await registry.refresh();assert.equal(registry.get(nicky.id)?.name,'Nicky');
    controller.replay('Receiver check.',voice);await tick();controller.stop();await tick();
    assert.ok(calls>=3);
  } finally {registry.dispose();controller.dispose();}
});
