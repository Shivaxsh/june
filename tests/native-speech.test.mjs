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
const { NativeSpeechController, NativeVoiceRegistry, JUNE_VOICE } = await load('../lib/voice/native-speech.ts');
const june = JUNE_VOICE;
const nicky = { id: 'com.apple.ttsbundle.siri_nicky_en-US_compact', name: 'Nicky', lang: 'en-US', gender: 'female', localService: true };
const voice = { ...june, voiceURI: june.id, default: false };
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
    assert.equal(f.requests[0].body.voiceId, june.id);
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
    for (const request of f.requests) { assert.ok(request.body.text.length <= 600); assert.equal(request.body.rate, .92); assert.doesNotMatch(request.body.text, /secret/); }
    assert.equal(f.stops.length, 0); // output preview acquires playback only
  } finally { f.controller.dispose(); }
});
test('fixed June ignores old browser and Nicky preferences and cannot be switched', async () => {
  for (const preference of ['browser-voice-uri|Nicky|en-US', nicky.id, 'samantha']) {
    const values = new Map([['june-voice-v1', preference]]), states = [];
    const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
    const registry = new NativeVoiceRegistry(storage, state => states.push(state), async () => Response.json({ state: 'ready', voices: [nicky, june], message: 'Ready' }));
    try {
      await registry.refresh(); registry.choose(nicky.id);
      assert.equal(states.at(-1).selected, june.id); assert.equal(states.at(-1).state, 'ready');
      assert.deepEqual(states.at(-1).options.map(v => v.id), [june.id]);
      assert.equal(registry.get(june.id).localService, false); assert.equal(registry.get(nicky.id), undefined);
      assert.equal(values.get('june-voice-v1'), preference);
    } finally { registry.dispose(); }
  }
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

test('provider setup, outage, and malformed records retain June identity but revoke playback without fallback', async () => {
  const states = []; let result = { state: 'ready', voices: [june], message: 'Ready' };
  const registry = new NativeVoiceRegistry(undefined, state => states.push(state), async () => {
    if (result instanceof Error) throw result;
    return Response.json(result);
  });
  try {
    await registry.refresh(); assert.equal(registry.get(june.id).name, 'June');
    for (const unavailable of [
      { state: 'setup-required', voices: [june], message: 'Add your ElevenLabs key' },
      { state: 'error', voices: [june, nicky], message: 'Provider unavailable' },
      { state: 'quota-exhausted', voices: [june], message: 'Credits exhausted' },
      { state: 'ready', voices: [nicky], message: 'Local voice ready' },
      ...['id', 'name', 'lang', 'gender', 'localService', 'provider'].map(field => ({ state: 'ready', voices: [{ ...june, [field]: field === 'localService' ? true : 'other' }], message: 'Wrong identity' })),
      new Error('Provider offline'),
    ]) {
      result = unavailable; await registry.refresh();
      assert.notEqual(states.at(-1).state, 'ready'); assert.equal(states.at(-1).selected, '');
      assert.deepEqual(states.at(-1).options.map(v => [v.id, v.name]), [[june.id, 'June']]);
      assert.equal(registry.get(june.id), undefined); assert.equal(registry.get(nicky.id), undefined);
      const f = fixture();
      try { f.controller.replay('Remain readable.', registry.get(june.id)); await tick(); assert.equal(f.requests.length, 0); }
      finally { f.controller.dispose(); }
    }
    result = { state: 'ready', voices: [june], message: 'Ready again' }; await registry.refresh();
    assert.equal(registry.get(june.id).voiceURI, june.id);
  } finally { registry.dispose(); }
});

test('native output rejects direct legacy identities and mute submits no speech', async () => {
  const f = fixture();
  try {
    const legacy = { ...nicky, voiceURI: nicky.id };
    f.controller.replay('Do not switch.', legacy);
    f.controller.begin(1, legacy, true); f.controller.push(1, 'No fallback. '); f.controller.finish(1);
    f.controller.begin(2, voice, false); f.controller.push(2, 'Muted. '); f.controller.finish(2);
    await tick(); assert.equal(f.requests.length, 0);
  } finally { f.controller.dispose(); }
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
    if(path.endsWith('/voices'))return Response.json({state:'ready',voices:[june]});
    if(path.endsWith('/stop'))return Response.json({stopped:true});
    return new Response(new TextEncoder().encode('{"type":"start"}\n{"type":"end"}\n'));
  }
  const registry=new NativeVoiceRegistry(undefined,()=>{},browserFetch);
  const controller=new NativeSpeechController(()=>{},{current:0},browserFetch);
  try {
    await registry.refresh();assert.equal(registry.get(june.id)?.name,'June');
    controller.replay('Receiver check.',voice);await tick();controller.stop();await tick();
    assert.ok(calls>=3);
  } finally {registry.dispose();controller.dispose();}
});

test('cloud chunks stay within 600 characters without losing words or splitting surrogate pairs', async () => {
  for (const text of ['word '.repeat(290).trim(), 'x'.repeat(599) + '😀' + 'y'.repeat(601)]) {
    const f = fixture();
    try {
      f.controller.replay(text, voice); await tick();
      for (let index = 0; index < f.requests.length; index++) {
        const request = f.requests[index];
        assert.ok(request.body.text.length <= 600);
        assert.ok(!/[\uD800-\uDBFF]$/.test(request.body.text));
        assert.ok(!/^[\uDC00-\uDFFF]/.test(request.body.text));
        if (text.startsWith('word')) assert.match(request.body.text, /^(word ?)+$/);
        request.event({ type: 'end' }); await tick();
      }
      const joined = f.requests.map(request => request.body.text).join(text.startsWith('word') ? ' ' : '');
      assert.equal(joined, text);
      assert.ok(f.requests.length >= 3); assert.equal(f.states.at(-1).phase, 'idle');
    } finally { f.controller.dispose(); }
  }
});
