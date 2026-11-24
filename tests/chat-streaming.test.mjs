import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const chat = await readFile(new URL('../components/Chat.tsx', import.meta.url), 'utf8');
const css = await readFile(new URL('../app/globals.css', import.meta.url), 'utf8');

test('streamed words are shown and spoken while the reply is still arriving', () => {
  const delta = chat.slice(chat.indexOf('if (event.type === "delta"'), chat.indexOf('} else if (event.type === "done"'));
  assert.match(delta, /reply \+= event\.text;\s*showProgress\(\);/);
  assert.match(chat, /requestAnimationFrame\(\(\) => \{ frame = 0; update\("pending"\); \}\)/, 'at most one render per frame');
  assert.match(chat, /if \(frame\) \{ cancelAnimationFrame\(frame\); frame = 0; \}/, 'a final state is never overwritten by a late frame');
  assert.match(chat, /\(!lead && \/\^\\s\*\[\\\[\{\]\/\.test\(reply\)\)/, 'raw JSON is never spoken; fenced code is stripped by the cleaner');
  assert.match(chat, /\(!complete && !lead && \/\^\\s\*```\\s\*json\\b\/i\.test\(reply\)\)\) return;/, 'a json-fence-first reply waits for validation');
});

test('a stopped reply keeps its words; a failed one is cleared', () => {
  assert.match(chat, /if \(!controller\.signal\.aborted\) reply="";/);
});

test('Systems shortcuts open the section they land on', () => {
  assert.match(chat, /querySelector\("details"\)\?\.setAttribute\("open", ""\)/);
  assert.match(chat, /"library:memory", "voice", "library:personality"/);
});

test('phones can scroll past the orb and reach the conversation first', () => {
  assert.match(css, /\.hud-orb canvas \{[^}]*touch-action: pan-y;/);
  const phone = css.slice(css.indexOf('@media (max-width: 760px)'));
  assert.match(phone, /\.hud-dialogue \{ order: 2;/);
  assert.doesNotMatch(css, /--hud-orb-h:[^;]*dvh/, 'svh keeps the hero steady while the address bar moves');
});

// Execute the real delta/done handler with a controlled voice queue. A rejected
// single-chunk document must never reach that queue, even before synthesis starts.
function speechHarness() {
  const speech = chat.slice(chat.indexOf('    let deltaCount = 0;'), chat.indexOf('    try {', chat.indexOf('    let deltaCount = 0;')));
  const branch = chat.slice(chat.indexOf('        if (event.type === "delta"'), chat.indexOf("        } else if (event.type === 'stage'")) + '\n}';
  const source = `
    let reply = "", firstToken = 0, complete = false;
    let citations = [], replyLimited = false, repetitionStopped = false, memoryIds = [], generalReply = false;
    let incomplete = false, savedTurnId = ""; const base = "", turnId = "t", unclosedFence = () => false, setResumable = () => {}, continuing = null, speechLead = () => "", setWriting = () => {}; let actionId, timerId, reminderId; const parseAction = () => null, actions = { upsert() {} }, parseTimer = () => null, timers = { upsert() {} }, parseReminder = () => null, reminders = { upsert() {}, upsertSeries() {} }, parseSeries = () => null, parsePlan = () => null, integrations = { upsert() {} }; let reminderSeriesId, planId;
    const id = 1, started = 0, automatic = false, libraryScope = {}, library = {temporary:true};
    const spokenTurn = {current:null}, input = {}, voiceSessionId = "";
    const voice = {push: (_id, text) => calls.push(text), stopVoice: () => {}};
    const spokenChatReply = text => text, showProgress = () => {};
    const console = {debug: () => {}};
    ${speech}
    return event => { for (const item of [event]) { ${branch} } if (complete) speakProgress(); };
  `;
  const calls = [];
  const validated = [];
  const validate = (_reply, event) => {
    validated.push(event);
    if (event.invalid) throw new Error('bad citation');
    return [];
  };
  const compiled = ts.transpile(source, {target:ts.ScriptTarget.ES2022});
  return {calls, validated, handle: new Function('calls', 'validatedDocumentReply', compiled)(calls, validate)};
}

test('a single-chunk document waits for successful citation validation before speech', () => {
  const h = speechHarness();
  h.handle({type:'delta', text:'Document evidence. A complete sentence.'});
  assert.deepEqual(h.calls, []);
  assert.throws(() => h.handle({type:'done', model:'fixture', invalid:true}), /bad citation/);
  assert.deepEqual(h.calls, []);
  const valid = speechHarness();
  valid.handle({type:'delta', text:'Validated document reply.'});
  valid.handle({type:'done', model:'fixture'});
  assert.equal(valid.validated.length, 1);
  assert.deepEqual(valid.calls, ['Validated document reply.']);
});

test('general streaming starts speech on its second nonempty delta', () => {
  const h = speechHarness();
  h.handle({type:'delta', text:'First sentence.'});
  h.handle({type:'delta', text:''});
  assert.deepEqual(h.calls, []);
  h.handle({type:'delta', text:' Second sentence.'});
  assert.deepEqual(h.calls, ['First sentence. Second sentence.']);
});

// What a listener actually hears: the handler's pushes through the real sentence buffer.
async function heard(chunks) {
  const source = await readFile(new URL('../lib/voice/sentences.ts', import.meta.url), 'utf8');
  const { SentenceBuffer } = await import('data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText).toString('base64'));
  const h = speechHarness();
  for (const text of chunks) h.handle({ type: 'delta', text });
  const buffer = new SentenceBuffer(); const out = [];
  for (const call of h.calls) out.push(...buffer.push(call));
  out.push(...buffer.finish());
  return out;
}

test('a reply that starts with code speaks the prose after the closing fence, never the code', async () => {
  const spoken = await heard(['```python\nx = 1\n', 'print(x)\n```\n', 'This sets x and prints it.', ' Run it with Python 3.']);
  assert.deepEqual(spoken, ['This sets x and prints it.', 'Run it with Python 3.']);
  assert.ok(spoken.every(s => !/x = 1|print\(/.test(s)));
});

test('code still open at the end of a stream is never spoken', async () => {
  assert.deepEqual(await heard(['Here is the start.', '\n```js\nfunction f() {\n', '  return 1;\n']), ['Here is the start.']);
});

test('raw JSON and json transport fences are never spoken progressively', async () => {
  assert.deepEqual(await heard(['{"answer": "Friday", ', '"citations": []}', ' more']), []);
  assert.deepEqual(await heard(['```json\n{"answer": "Friday"', ', "citations": []}\n```']), []);
});

test('prose after a closed json transport fence stays silent until done validates the reply', async () => {
  // Reported risk: envelope streamed across chunks, closed, then prose before done.
  const spoken = await heard(['```json\n{"answer": "Fri', 'day", "citations": []}\n', '```\n', 'Friday is the launch date.', ' It moved last week.']);
  assert.deepEqual(spoken, [], 'nothing is spoken before done validation');
  // A rejected envelope never speaks at all.
  const rejected = speechHarness();
  for (const text of ['```json\n{"answer": "Friday"}\n```\n', 'Friday is the launch date.', ' More.']) rejected.handle({ type: 'delta', text });
  assert.throws(() => rejected.handle({ type: 'done', model: 'fixture', invalid: true }), /bad citation/);
  assert.deepEqual(rejected.calls, []);
  // A json sample that passes validation is spoken once done completes: only its prose.
  const valid = speechHarness();
  for (const text of ['```json\n{"name": "Avery"}\n```\n', 'That is the config.', ' Save it as settings.json.']) valid.handle({ type: 'delta', text });
  assert.deepEqual(valid.calls, []);
  valid.handle({ type: 'done', model: 'fixture' });
  assert.equal(valid.calls.length, 1);
  assert.match(valid.calls[0], /That is the config\./);
});

test('python code-first prose still streams before done', async () => {
  assert.deepEqual(await heard(['```python\nx = 1\n```\n', 'This sets x.', ' Then it stops.']), ['This sets x.', 'Then it stops.']);
});
