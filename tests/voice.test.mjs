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
const { SentenceBuffer, spokenText, mergeTranscript } = await load('../lib/voice/sentences.ts');
const { VoiceRegistry, femaleVoices, voiceId, saved } = await load('../lib/voice/voices.ts');
const { SpeechController } = await load('../lib/voice/speech.ts');
const { RecognitionController } = await load('../lib/voice/recognition.ts');
const { resolveOrb } = await load('../lib/orb/state.ts');
const samantha = { name: 'Samantha', lang: 'en-US', voiceURI: 'sam', localService: true };
const veena = { name: 'Veena', lang: 'en-IN', voiceURI: 'veena', localService: true };

test('sentence chunks retain decimals, abbreviations and final fragments in order', () => {
  const buffer = new SentenceBuffer();
  assert.deepEqual(buffer.push('Dr. June likes 3.'), []);
  assert.deepEqual(buffer.push('14. She says '), ['Dr. June likes 3.14.']);
  assert.deepEqual(buffer.push('hello! Next '), ['She says hello!']);
  assert.deepEqual(buffer.finish(), ['Next']); assert.deepEqual(buffer.finish(), []);
});
test('an incomplete or complete fenced code block never becomes speech', () => {
  const buffer = new SentenceBuffer();
  assert.deepEqual(buffer.push('Hello. ```js\nconsole.log("Do not read. ");'), ['Hello.']);
  assert.deepEqual(buffer.push('\n```\nNow speak. Goodbye'), ['Now speak.']);
  assert.deepEqual(buffer.finish(), ['Goodbye']);
  assert.equal(spokenText('**Hi** [June](https://example.com) `welcome`'), 'Hi June welcome');
});
test('transcript merge preserves an existing draft and ignores empty speech', () => {
  assert.equal(mergeTranscript('Typed draft', ' hello '), 'Typed draft\nhello');
  assert.equal(mergeTranscript('', ' hello '), 'hello'); assert.equal(mergeTranscript('draft', '   '), 'draft');
});
test('voice filter rejects male, unknown and remote identities; default prefers Indian English', () => {
  assert.deepEqual(femaleVoices([samantha, { ...veena, localService: false }, { ...samantha, name: 'Unknown' }, { ...samantha, name: 'Rishi' }, veena]), [veena, samantha]);
});
test('delayed voices restore a saved female choice and persist changes; blocked storage is harmless', () => {
  let voices = []; const events = new Map(); const values = new Map([['june-voice-v1', voiceId(samantha)]]); let state;
  const synth = { getVoices: () => voices, addEventListener: (name, fn) => events.set(name, fn), removeEventListener: name => events.delete(name) };
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  const registry = new VoiceRegistry(synth, storage, s => state = s);
  try {
    assert.match(state.message, /Loading/); voices = [veena, samantha]; events.get('voiceschanged')();
    assert.equal(state.selected, voiceId(samantha)); registry.choose(voiceId(veena)); assert.equal(values.get('june-voice-v1'), voiceId(veena));
    assert.equal(saved({ getItem() { throw Error(); } }, 'x', 'fallback'), 'fallback');
  } finally { registry.dispose(); }
  assert.equal(events.size, 0);
});
function speechEnvironment() {
  const utterances = [], states = [];
  class Utterance { constructor(text) { this.text = text; } }
  const synth = { speak: u => utterances.push(u), cancel() {} };
  const controller = new SpeechController(synth, Utterance, state => states.push(state));
  return { controller, utterances, states };
}
test('speech starts with complete sentences, queues in order, flushes and stops late events', () => {
  const { controller, utterances, states } = speechEnvironment();
  try {
    controller.begin(1, samantha, true); controller.push(1, 'Hello. Next sentence. Tail');
    assert.equal(utterances.length, 1); assert.equal(utterances[0].text, 'Hello.'); assert.equal(utterances[0].voice, samantha);
    const staleStart = utterances[0].onstart; utterances[0].onstart(); assert.equal(states.at(-1).phase, 'speaking');
    controller.finish(1); utterances[0].onend(); assert.equal(utterances[1].text, 'Next sentence.');
    const staleEnd = utterances[0].onend; staleEnd(); assert.equal(utterances.length, 2);
    utterances[1].onend(); assert.equal(utterances[2].text, 'Tail');
    controller.stop(); staleStart(); controller.push(1, 'Late sentence. More');
    assert.equal(utterances.length, 3); assert.equal(states.at(-1).phase, 'idle'); assert.equal(controller.activity.current, 0);
  } finally { controller.dispose(); }
});
test('mute and missing voices prevent playback; replacement rejects old request chunks', () => {
  const { controller, utterances, states } = speechEnvironment();
  try {
    controller.begin(1, samantha, false); controller.push(1, 'Muted. Next'); assert.equal(utterances.length, 0);
    controller.begin(2, undefined, true); assert.match(states.at(-1).error, /No local female/);
    controller.begin(3, samantha, true); controller.push(2, 'Old. Next'); controller.push(3, 'New. Next');
    assert.equal(utterances.length, 1); assert.equal(utterances[0].text, 'New.');
    utterances[0].onstart(); utterances[0].onboundary({ charIndex: 0, charLength: 3 }); assert.equal(states.at(-1).approximate, false);
  } finally { controller.dispose(); }
});
function recognitionEnvironment() {
  const states = [], instances = [];
  const factory = () => { const instance = { start() {}, stop() { this.stops = (this.stops || 0) + 1; }, abort() { this.aborts = (this.aborts || 0) + 1; } }; instances.push(instance); return instance; };
  return { controller: new RecognitionController(factory, state => states.push(state)), states, instances };
}
test('release during delayed permission stops as soon as recognition starts; duplicate release is safe', () => {
  const { controller, states, instances } = recognitionEnvironment();
  try {
    controller.start('en-IN'); controller.finish(); instances[0].onstart(); controller.finish();
    assert.equal(instances[0].stops, 1); assert.equal(states.at(-1).phase, 'finishing');
    instances[0].onresult({ results: [{ 0: { transcript: 'hello June' }, isFinal: true }] }); instances[0].onend();
    assert.equal(states.at(-1).transcript, 'hello June'); assert.equal(states.at(-1).phase, 'idle');
    controller.edit('edited hello'); controller.cancel(); assert.equal(states.at(-1).transcript, 'edited hello');
  } finally { controller.dispose(); }
});
test('recognition interim/final replacements do not duplicate words; cancel ignores stale results', () => {
  const { controller, states, instances } = recognitionEnvironment();
  try {
    controller.start('en-US'); instances[0].onstart();
    instances[0].onresult({ results: [{ 0: { transcript: 'hel' }, isFinal: false }] });
    instances[0].onresult({ results: [{ 0: { transcript: 'hello' }, isFinal: true }, { 0: { transcript: 'June' }, isFinal: true }] });
    assert.equal(states.at(-1).transcript, 'hello June'); const late = instances[0].onresult; controller.cancel(true);
    late({ results: [{ 0: { transcript: 'stale' }, isFinal: true }] }); assert.equal(states.at(-1).transcript, '');
  } finally { controller.dispose(); }
});
test('unsupported recognition and permission denial produce actionable errors', () => {
  let state; const unsupported = new RecognitionController(undefined, s => state = s); unsupported.start('en-IN'); assert.match(state.error, /unavailable/); unsupported.dispose();
  const { controller, states, instances } = recognitionEnvironment();
  try { controller.start('en-IN'); instances[0].onerror({ error: 'not-allowed' }); assert.match(states.at(-1).error, /denied/); assert.equal(instances[0].aborts, 1); }
  finally { controller.dispose(); }
});
test('actual speech and listening take priority over generating text, with honest labels', () => {
  assert.equal(resolveOrb(true, false, 'auto', 'idle', { listening: false, speaking: true }).mood, 'speaking');
  assert.match(resolveOrb(true, false, 'auto', 'idle', { listening: false, speaking: true }).label, /approximation/);
  assert.equal(resolveOrb(false, false, 'speaking', 'idle', { listening: true, speaking: false }).label, 'Listening · speech recognition');
});
test('a complete sentence with trailing space starts without waiting for the next word', () => {
  const buffer = new SentenceBuffer(); assert.deepEqual(buffer.push('Hello. '), ['Hello.']);
  assert.deepEqual(buffer.push('Next'), []); assert.deepEqual(buffer.finish(), ['Next']);
});
test('recognition startup timeout aborts pending work and ignores a later start', () => {
  const originalSet = globalThis.setTimeout, originalClear = globalThis.clearTimeout; const callbacks = [];
  globalThis.setTimeout = fn => { callbacks.push(fn); return callbacks.length; }; globalThis.clearTimeout = () => {};
  const { controller, states, instances } = recognitionEnvironment();
  try {
    controller.start('en-IN'); const late = instances[0].onstart; callbacks[0]();
    assert.match(states.at(-1).error, /did not start/); assert.equal(instances[0].aborts, 1);
    late(); assert.equal(states.at(-1).phase, 'idle');
  } finally { controller.dispose(); globalThis.setTimeout = originalSet; globalThis.clearTimeout = originalClear; }
});
test('blocked speech startup ends with a readable recovery message', () => {
  const originalSet = globalThis.setTimeout, originalClear = globalThis.clearTimeout; const callbacks = [];
  globalThis.setTimeout = fn => { callbacks.push(fn); return callbacks.length; }; globalThis.clearTimeout = () => {};
  const { controller, states } = speechEnvironment();
  try {
    controller.replay('Hello June', samantha); callbacks[0]();
    assert.equal(states.at(-1).phase, 'idle'); assert.match(states.at(-1).error, /Preview voice or Hear reply/);
  } finally { controller.dispose(); globalThis.setTimeout = originalSet; globalThis.clearTimeout = originalClear; }
});
