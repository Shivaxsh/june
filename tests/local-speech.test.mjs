import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const cache = new Map();
async function moduleUrl(url) {
  if (cache.has(url.href)) return cache.get(url.href);
  let { outputText } = ts.transpileModule(await readFile(url, 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
  for (const match of [...outputText.matchAll(/from ["'](\.[^"']+)["']/g)]) {
    outputText = outputText.replace(match[0], `from ${JSON.stringify(await moduleUrl(new URL(match[1] + '.ts', url)))}`);
  }
  const result = 'data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'); cache.set(url.href, result); return result;
}
const load = async path => import(await moduleUrl(new URL(path, import.meta.url)));
let pcm;
try { pcm = await load('../lib/voice/pcm.ts'); } catch {}
test('WAV encoding clips to signed PCM and produces a valid 16k mono header', () => {
  assert.equal(typeof pcm?.encodeWav, 'function', 'PCM encoder has not been implemented');
  const data = pcm.encodeWav(new Float32Array([-2, -1, 0, .5, 1, 2])); const view = new DataView(data);
  assert.equal(new TextDecoder().decode(new Uint8Array(data, 0, 4)), 'RIFF');
  assert.equal(view.getUint32(24, true), 16000); assert.equal(view.getUint16(22, true), 1);
  assert.deepEqual(Array.from({ length: 6 }, (_, i) => view.getInt16(44 + i * 2, true)), [-32768, -32768, 0, 16384, 32767, 32767]);
});
test('WAV validation rejects malformed, silent, short, stereo and oversized input', () => {
  assert.equal(typeof pcm?.validateWav, 'function', 'WAV validation has not been implemented');
  assert.throws(() => pcm.validateWav(new Uint8Array(45)), /WAV/);
  assert.throws(() => pcm.validateWav(new Uint8Array(pcm.encodeWav(new Float32Array(16000)))), /speech|quiet|silence/i);
  assert.throws(() => pcm.validateWav(new Uint8Array(pcm.encodeWav(new Float32Array(100).fill(.2)))), /short/i);
  const valid = new Uint8Array(pcm.encodeWav(new Float32Array(16000).fill(.2)));
  assert.equal(pcm.validateWav(valid).durationMs, 1000);
  const stereo = valid.slice(); new DataView(stereo.buffer).setUint16(22, 2, true);
  assert.throws(() => pcm.validateWav(stereo), /mono|format/i);
  assert.throws(() => pcm.validateWav(new Uint8Array(1048577)), /large/i);
  const wrongRate = valid.slice(); new DataView(wrongRate.buffer).setUint32(24, 44100, true);
  assert.throws(() => pcm.validateWav(wrongRate), /16|format/i);
  const truncated = valid.slice(0, -2); assert.throws(() => pcm.validateWav(truncated), /WAV|size/i);
});
let local;
try { local = await load('../lib/voice/local-recognition.ts'); } catch {}
const tick = () => new Promise(resolve => setImmediate(resolve));
function environment(transcribe = async () => ({ text: 'Hello June.', durationMs: 23 })) {
  let begin, ended = 0; const states = [];
  const clip = pcm?.encodeWav(new Float32Array(16000).fill(.2));
  const capture = { start: () => new Promise(resolve => { begin = resolve; }), finish: async () => clip, cancel: () => { ended++; } };
  const controller = new local.LocalRecognitionController(() => capture, transcribe, state => states.push(state));
  return { controller, states, release: () => begin(), ended: () => ended };
}
test('direct capture works without a browser speech recognition service', async () => {
  assert.equal(typeof local?.LocalRecognitionController, 'function', 'Local recogniser has not been implemented');
  const env = environment(); env.controller.start(); assert.equal(env.states.at(-1).phase, 'requesting');
  env.release(); await tick(); assert.equal(env.states.at(-1).phase, 'listening');
  env.controller.finish(); await tick(); assert.equal(env.states.at(-1).transcript, 'Hello June.'); assert.equal(env.states.at(-1).phase, 'idle');
  env.controller.edit('Edited words'); env.controller.start(); env.controller.cancel();
  env.release(); await tick(); assert.equal(env.states.at(-1).transcript, 'Edited words'); assert.ok(env.ended() > 0); env.controller.dispose();
});
test('cancelled transcription cannot overwrite a newer edited transcript', async () => {
  assert.equal(typeof local?.LocalRecognitionController, 'function');
  let resolve; let signal;
  const env = environment((_clip, abort) => { signal = abort; return new Promise(r => { resolve = r; }); });
  env.controller.start(); env.release(); await tick(); env.controller.finish(); await tick();
  assert.equal(env.states.at(-1).phase, 'finishing'); env.controller.cancel(); assert.equal(signal.aborted, true);
  env.controller.edit('Keep this'); resolve({ text: 'stale result', durationMs: 5 }); await tick();
  assert.equal(env.states.at(-1).transcript, 'Keep this'); env.controller.dispose();
});
test('permission denial preserves the existing transcript and returns idle', async () => {
  assert.equal(typeof local?.LocalRecognitionController, 'function');
  const states = []; const controller = new local.LocalRecognitionController(() => ({ start: async () => { throw new DOMException('denied', 'NotAllowedError'); }, cancel() {} }), async () => {}, state => states.push(state));
  controller.edit('Existing'); controller.start(); await tick();
  assert.match(states.at(-1).error, /permission|allow/i); assert.equal(states.at(-1).phase, 'idle'); assert.equal(states.at(-1).transcript, 'Existing'); controller.dispose();
});
let server;
try { server = await load('../lib/server/speech.ts'); } catch {}
test('speech routes reject foreign origins and oversized streaming bodies', async () => {
  assert.equal(typeof server?.localRequest, 'function', 'Speech request validation is missing');
  assert.equal(server.localRequest(new Request('http://localhost:3001', { headers: { host: '127.0.0.1:3001', origin: 'http://127.0.0.1:3001' } })), true);
  assert.equal(server.localRequest(new Request('http://localhost:3001', { headers: { host: '127.0.0.1:3001', origin: 'https://evil.example' } })), false);
  assert.equal(server.localRequest(new Request('http://localhost:3001', { headers: { host: 'evil.example' } })), false);
  const request = new Request('http://localhost', { method: 'POST', body: new Uint8Array(1048577) });
  await assert.rejects(server.readAudio(request), /large/i);
});
test('missing speech installation reports setup instructions and does not accept a job', async () => {
  const old = process.env.JUNE_SPEECH_HOME; process.env.JUNE_SPEECH_HOME = '/tmp/june-no-such-test-runtime';
  try {
    const status = await server.speechStatus(); assert.equal(status.state, 'runtime-missing'); assert.match(status.message, /speech:setup/);
    const clip = new Uint8Array(pcm.encodeWav(new Float32Array(16000).fill(.2)));
    await assert.rejects(server.transcribe(clip, new AbortController().signal), /setup/i);
  } finally { if (old === undefined) delete process.env.JUNE_SPEECH_HOME; else process.env.JUNE_SPEECH_HOME = old; }
});
test('early release, duplicate finish, cancellation and repeated recording do not leave active capture', async () => {
  const env = environment();
  env.controller.start(); env.controller.finish(); env.release(); await tick(); assert.equal(env.states.at(-1).phase, 'idle');
  for (let i = 0; i < 10; i++) {
    env.controller.start(); env.release(); await tick(); env.controller.finish(); env.controller.finish(); await tick();
    assert.equal(env.states.at(-1).transcript, 'Hello June.'); assert.equal(env.states.at(-1).phase, 'idle');
  }
  env.controller.cancel(true); assert.equal(env.states.at(-1).transcript, ''); env.controller.dispose();
});
test('quiet recordings never reach the local model and retain edited words', async () => {
  let calls = 0; const states = [];
  const capture = { start: async () => {}, finish: async () => pcm.encodeWav(new Float32Array(16000)), cancel() {} };
  const controller = new local.LocalRecognitionController(() => capture, async () => { calls++; return { text: 'hallucination', durationMs: 0 }; }, state => states.push(state));
  controller.edit('Keep edited words'); controller.start(); await tick(); controller.finish(); await tick();
  assert.equal(calls, 0); assert.match(states.at(-1).error, /quiet/i); assert.equal(states.at(-1).transcript, 'Keep edited words'); controller.dispose();
});
test('real local engine transcribes speech and cancellation releases its job', async t => {
  const { readFile, readdir } = await import('node:fs/promises'); const { homedir, tmpdir } = await import('node:os'); const { join } = await import('node:path');
  if ((await server.speechStatus()).state !== 'ready') { t.skip('Run speech:setup for the real-engine check.'); return; }
  const raw = new Uint8Array(await readFile(join(homedir(), 'Library/Application Support/June/speech/whisper.cpp/samples/jfk.wav')));
  // The upstream fixture has extra metadata chunks. Canonicalise its PCM payload
  // into the narrow recording format this app sends, retaining the actual speech.
  const dv = new DataView(raw.buffer); let offset = 12, samples;
  while (offset + 8 <= raw.length) {
    const size = dv.getUint32(offset + 4, true), name = new TextDecoder().decode(raw.subarray(offset, offset + 4));
    if (name === 'data') { samples = new Float32Array(size / 2); for (let i = 0; i < samples.length; i++) samples[i] = dv.getInt16(offset + 8 + i * 2, true) / 32768; break; }
    offset += 8 + size + size % 2;
  }
  assert.ok(samples); const clip = new Uint8Array(pcm.encodeWav(samples));
  const before = (await readdir(tmpdir())).filter(name => name.startsWith('june-speech-'));
  const abort = new AbortController(); const job = server.transcribe(clip, abort.signal);
  await assert.rejects(server.transcribe(clip, new AbortController().signal), error => error.code === 'busy');
  setTimeout(() => abort.abort(), 150); await assert.rejects(job, /cancel|abort/i);
  const result = await server.transcribe(clip, new AbortController().signal);
  assert.match(result.text, /ask not what your country can do for you/i); assert.equal(result.engine, 'whisper.cpp'); assert.ok(result.durationMs > 0);
  assert.deepEqual((await readdir(tmpdir())).filter(name => name.startsWith('june-speech-')), before);
});
test('permission timeout releases capture and ignores a late grant', async () => {
  const originalSet = globalThis.setTimeout, originalClear = globalThis.clearTimeout; let timeout;
  globalThis.setTimeout = callback => { timeout = callback; return 1; }; globalThis.clearTimeout = () => {};
  const env = environment();
  try {
    env.controller.start(); timeout(); assert.match(env.states.at(-1).error, /pending/); env.release(); await tick();
    assert.equal(env.states.at(-1).phase, 'idle'); assert.ok(env.ended() > 0);
  } finally { env.controller.dispose(); globalThis.setTimeout = originalSet; globalThis.clearTimeout = originalClear; }
});
test('empty and failing transcription preserve the reviewed transcript', async () => {
  for (const transcribe of [async () => ({ text: ' ', durationMs: 0 }), async () => { throw Error('Engine unavailable; refresh speech.'); }]) {
    const env = environment(transcribe); env.controller.edit('Keep this draft'); env.controller.start(); env.release(); await tick(); env.controller.finish(); await tick();
    assert.equal(env.states.at(-1).phase, 'idle'); assert.equal(env.states.at(-1).transcript, 'Keep this draft'); assert.ok(env.states.at(-1).error); env.controller.dispose();
  }
});
test('audio worklet mixes channels, flushes its final samples and never echoes microphone input', async () => {
  const vm = await import('node:vm'); let Processor; const messages = [];
  class Base { port = { postMessage: message => messages.push(message), onmessage: null }; }
  const context = vm.createContext({ AudioWorkletProcessor: Base, Float32Array, registerProcessor: (_name, value) => { Processor = value; } });
  vm.runInContext(await readFile(new URL('../public/audio/recorder-worklet.js', import.meta.url), 'utf8'), context);
  const node = new Processor(); const output = new Float32Array(3).fill(.9);
  assert.equal(node.process([[new Float32Array([.2, .4, .6]), new Float32Array([.4, .6, .8])]], [[output]]), true);
  assert.deepEqual([...output], [0, 0, 0]); node.port.onmessage({ data: 'stop' });
  assert.equal(messages[0].samples.length, 3); assert.ok(Math.abs(messages[0].samples[0] - .3) < .0001);
  assert.equal(messages[1].done, true); assert.equal(node.process([], [[output]]), false);
});
const { BrowserVoiceCapture } = await load('../lib/voice/capture.ts');
test('direct recorder releases tracks from a late permission grant and closes its context', async () => {
  const oldWindow = Object.getOwnPropertyDescriptor(globalThis, 'window'), oldNavigator = Object.getOwnPropertyDescriptor(globalThis, 'navigator');
  let resolve; let stopped = 0, closed = 0; const permission = new Promise(r => { resolve = r; });
  const stream = { getTracks: () => [{ stop() { stopped++; } }] };
  class Context { sampleRate = 48000; resume = async () => {}; close = async () => { closed++; }; }
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { AudioContext: Context, AudioWorkletNode() {}, OfflineAudioContext() {} } });
  Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { mediaDevices: { getUserMedia: () => permission } } });
  const oldContext = Object.getOwnPropertyDescriptor(globalThis, 'AudioContext'); Object.defineProperty(globalThis, 'AudioContext', { configurable: true, value: Context });
  try {
    const level = { current: .5 }, capture = new BrowserVoiceCapture(level), abort = new AbortController();
    const job = capture.start(abort.signal, () => {}); abort.abort(); resolve(stream); await assert.rejects(job, /abort/i);
    assert.equal(stopped, 1); assert.equal(closed, 1); assert.equal(level.current, 0);
  } finally {
    for (const [key, descriptor] of [['window',oldWindow],['navigator',oldNavigator],['AudioContext',oldContext]]) {
      if (descriptor) Object.defineProperty(globalThis,key,descriptor); else delete globalThis[key];
    }
  }
});
test('a stopped local speech server gives actionable recovery instead of a generic fetch error', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch'); };
  try { await assert.rejects(local.transcribeLocally(new ArrayBuffer(44), new AbortController().signal), /restart June|refresh speech/i); }
  finally { globalThis.fetch = original; }
});
test('speech setup reads the same ignored configuration file as the app server', async () => {
  const { mkdtemp, writeFile, rm } = await import('node:fs/promises'); const { tmpdir } = await import('node:os'); const { join } = await import('node:path'); const { spawnSync } = await import('node:child_process');
  const directory = await mkdtemp(join(tmpdir(), 'june-config-test-'));
  try {
    await writeFile(join(directory, '.env.local'), 'JUNE_SPEECH_HOME=/tmp/june-custom-speech-test\n');
    const url = new URL('../scripts/speech.mjs', import.meta.url).href;
    const result = spawnSync(process.execPath, ['--input-type=module', '-e', `import { root } from ${JSON.stringify(url)}; process.stdout.write(root);`], { cwd: directory, encoding: 'utf8' });
    assert.equal(result.status, 0); assert.equal(result.stdout, '/tmp/june-custom-speech-test');
  } finally { await rm(directory, { recursive: true, force: true }); }
});
test('engine failure and forced timeout remove temporary audio and free the process lock', async t => {
  if ((await server.speechStatus()).state !== 'ready') { t.skip('Run speech:setup for process lifecycle checks.'); return; }
  const { mkdtemp, mkdir, writeFile, readFile, symlink, rm, readdir } = await import('node:fs/promises');
  const { tmpdir, homedir } = await import('node:os'); const { join } = await import('node:path');
  const directory = await mkdtemp(join(tmpdir(),'june-engine-test-')); const previous = process.env.JUNE_SPEECH_HOME;
  const actual = join(homedir(),'Library/Application Support/June/speech'); const realSet = globalThis.setTimeout;
  try {
    await mkdir(join(directory,'whisper.cpp/build/bin'),{recursive:true});
    await symlink(join(actual,'ggml-base.en.bin'),join(directory,'ggml-base.en.bin'));
    await writeFile(join(directory,'ready.json'),await readFile(join(actual,'ready.json')));
    const executable = join(directory,'whisper.cpp/build/bin/whisper-cli');
    const clip = new Uint8Array(pcm.encodeWav(new Float32Array(16000).fill(.2)));
    const before = (await readdir(tmpdir())).filter(name=>name.startsWith('june-speech-'));
    process.env.JUNE_SPEECH_HOME = directory;
    await writeFile(executable,`#!${process.execPath}\nprocess.exit(1);\n`,{mode:0o700});
    await assert.rejects(server.transcribe(clip,new AbortController().signal),error=>error.code==='engine-failed');
    await writeFile(executable,`#!${process.execPath}\nconst fs=require('node:fs');fs.writeFileSync(${JSON.stringify(join(directory,'pid'))},String(process.pid));process.on('SIGTERM',()=>{});setInterval(()=>{},1000);\n`,{mode:0o700});
    // Compress only this component's watchdog delays; the child is a real process
    // that ignores SIGTERM, so escalation and cleanup are exercised end to end.
    globalThis.setTimeout = (fn,ms,...args) => realSet(fn,ms===120000?300:ms===1000?50:ms,...args);
    await assert.rejects(server.transcribe(clip,new AbortController().signal),error=>error.code==='timeout');
    globalThis.setTimeout = realSet;
    const pid = Number(await readFile(join(directory,'pid'),'utf8')); assert.throws(()=>process.kill(pid,0),error=>error.code==='ESRCH');
    assert.deepEqual((await readdir(tmpdir())).filter(name=>name.startsWith('june-speech-')),before);
    await writeFile(executable,`#!${process.execPath}\nprocess.exit(1);\n`,{mode:0o700});
    await assert.rejects(server.transcribe(clip,new AbortController().signal),error=>error.code==='engine-failed');
  } finally {
    globalThis.setTimeout = realSet; if(previous===undefined) delete process.env.JUNE_SPEECH_HOME; else process.env.JUNE_SPEECH_HOME=previous;
    await rm(directory,{recursive:true,force:true});
  }
});
test('a rejected audio start is handled while microphone permission is still pending', async () => {
  const originals = new Map(['window','navigator','AudioContext'].map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]));
  let resolve; const permission = new Promise(r=>{resolve=r;}); let stopped=0;
  class Context { sampleRate=48000; resume=()=>Promise.reject(new Error('Audio start blocked')); close=async()=>{}; }
  Object.defineProperty(globalThis,'window',{configurable:true,value:{AudioContext:Context,AudioWorkletNode(){},OfflineAudioContext(){}}});
  Object.defineProperty(globalThis,'AudioContext',{configurable:true,value:Context});
  Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{getUserMedia:()=>permission}}});
  try {
    const capture=new BrowserVoiceCapture({current:0}); const task=capture.start(new AbortController().signal,()=>{});
    const rejected=assert.rejects(task,/Audio start blocked/);
    await tick(); resolve({getTracks:()=>[{stop(){stopped++;}}],getAudioTracks:()=>[]}); await rejected;
    assert.equal(stopped,1);
  } finally { for(const [key,descriptor] of originals) {if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key];} }
});
