// Opt-in check of June Browser's recruiter-question script against a local MOCK of Naukri's question box
// (tests/fixtures/naukri/recruiter-questions.html). It never contacts naukri.com: Chrome is started headless
// with www.naukri.com mapped to a local HTTPS server and a throwaway certificate. It proves the script's logic
// only; Naukri's real markup can differ. Usage: node scripts/check-naukri-chat.mjs
import {execFileSync, spawn} from 'node:child_process';
import fs from 'node:fs';
import https from 'node:https';
import os from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'june-naukri-chat-'));
execFileSync('/usr/bin/openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', path.join(work, 'k.pem'), '-out', path.join(work, 'c.pem'), '-days', '1', '-subj', '/CN=www.naukri.com'], {stdio: 'ignore'});
const page = fs.readFileSync(path.join(root, 'tests/fixtures/naukri/recruiter-questions.html'));
const server = https.createServer({key: fs.readFileSync(path.join(work, 'k.pem')), cert: fs.readFileSync(path.join(work, 'c.pem'))}, (q, r) => { r.writeHead(200, {'content-type': 'text/html'}); r.end(page); });
await new Promise(r => server.listen(0, '127.0.0.1', r));
const port = 9400 + Math.floor(Math.random() * 400);
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', ['--headless=new', `--remote-debugging-port=${port}`, '--mute-audio', '--ignore-certificate-errors',
  `--host-resolver-rules=MAP www.naukri.com:443 127.0.0.1:${server.address().port}`, `--user-data-dir=${path.join(work, 'profile')}`, 'about:blank'], {stdio: 'ignore'});
const sleep = ms => new Promise(r => setTimeout(r, ms));
try {
  let list;
  for (let i = 0; i < 40 && !list; i++) { await sleep(250); list = await fetch(`http://127.0.0.1:${port}/json`).then(r => r.json()).catch(() => null); }
  const swift = fs.readFileSync(path.join(root, 'native/JuneBrowser.swift'), 'utf8');
  const template = swift.match(/let chatTemplate = #"""\n([\s\S]*?)\n"""#/)[1];
  // The same one-pass fill as JuneBrowser's chatJS: text put in for one placeholder is never read as another.
  const js = (id, mode, value, expected = null) => {
    const values = {JOB_ID: id, MODE_VALUE: JSON.stringify(mode), VALUE_VALUE: JSON.stringify(value), EXPECTED_VALUE: expected === null ? 'null' : JSON.stringify(expected)};
    return template.replace(/JOB_ID|MODE_VALUE|EXPECTED_VALUE|VALUE_VALUE/g, k => values[k]);
  };
  const ws = new WebSocket(list.find(t => t.type === 'page').webSocketDebuggerUrl);
  let n = 0; const wait = {}; ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && wait[m.id]) { wait[m.id](m.result); delete wait[m.id]; } };
  await new Promise(r => ws.onopen = r);
  const send = (method, params = {}) => new Promise(r => { const id = ++n; wait[id] = r; ws.send(JSON.stringify({id, method, params})); });
  const run = async code => JSON.parse((await send('Runtime.evaluate', {expression: code, returnByValue: true})).result.value);
  await send('Page.navigate', {url: 'https://www.naukri.com/job-listings-frontend-engineer-acme-noida-1-to-3-years-181125000123'}); await sleep(1200);
  const ID = '181125000123';
  assert.deepEqual(await run(js('181125000999', 'read', '')), {ok: false, reason: 'different-job'}, 'bound to the reviewed job');
  const NOTICE = 'What is your notice period?';
  const answers = async () => run('JSON.stringify(window.__answers)');
  // Race 1: the question changes between June reading it and entering the answer: nothing is entered.
  assert.equal((await run(js(ID, 'read', ''))).question, NOTICE);
  await run('window.__interject("Sneaky new question VALUE_VALUE JOB_ID?"), "1"');
  assert.deepEqual(await run(js(ID, 'text', 'Immediate joiner', NOTICE)), {ok: true, answered: false, reason: 'question-changed', question: 'Sneaky new question VALUE_VALUE JOB_ID?'});
  assert.equal(await run('JSON.stringify(document.querySelector(".textArea").innerText)'), '', 'nothing typed into the changed question');
  // A question whose text looks like a placeholder stays literal text (one-pass fill).
  const filled = js(ID, 'text', 'v', 'Q VALUE_VALUE JOB_ID?');
  assert.ok(filled.includes('EXPECTED = "Q VALUE_VALUE JOB_ID?"') && filled.includes('VALUE = "v"'), 'placeholders inside values are not filled again');
  await run('window.__uninterject(), "1"');
  // Race 2: the question changes after entry but before Save: Save is not clicked, and the next read says so.
  assert.deepEqual(await run(js(ID, 'text', 'Immediate joiner', NOTICE)), {ok: true, answered: true});
  await run('window.__interject("Another question?"), "1"');
  await new Promise(r => setTimeout(r, 900));
  const skipped = await run(js(ID, 'read', ''));
  assert.deepEqual(skipped.lastSave, {question: NOTICE, saved: false, reason: 'question-changed'});
  assert.deepEqual(await answers(), [], 'Save was not clicked for a changed question');
  await run('window.__uninterject(), "1"');
  // Race 3: the page moves to a different job (same question, no reload) after entry, before Save: no Save there.
  const HERE = '/job-listings-frontend-engineer-acme-noida-1-to-3-years-181125000123';
  assert.deepEqual(await run(js(ID, 'text', 'Immediate joiner', NOTICE)), {ok: true, answered: true});
  await run('history.pushState({}, "", "/job-listings-other-role-acme-noida-1-to-3-years-181125000999"), "1"');
  await sleep(900);
  assert.deepEqual(await run(js(ID, 'read', '')), {ok: false, reason: 'different-job'}, 'reads are bound to the job too');
  await run(`history.pushState({}, "", "${HERE}"), "1"`);
  assert.deepEqual((await run(js(ID, 'read', ''))).lastSave, {question: NOTICE, saved: false, reason: 'different-job'});
  assert.deepEqual(await answers(), [], 'nothing was saved on the other job');
  // Race 4: the page replaces the answer box (as React may) after entry, before Save: the new box is not ours, so no Save.
  assert.deepEqual(await run(js(ID, 'text', 'Immediate joiner', NOTICE)), {ok: true, answered: true});
  await run('(() => { const old = document.querySelector(".textArea"); const fresh = old.cloneNode(false); old.replaceWith(fresh); return "1"; })()');
  await sleep(900);
  assert.deepEqual((await run(js(ID, 'read', ''))).lastSave, {question: NOTICE, saved: false, reason: 'answer-changed'});
  assert.deepEqual(await answers(), []);
  const expected = {'What is your notice period?': ['text', [], 'Immediate joiner'], 'Are you willing to relocate to Gurugram?': ['radio', ['Yes', 'No'], 'Yes'],
                    'Do you have your own laptop?': ['chips', ['Yes', 'No'], 'Yes'],
                    // Naukri's navigation chip next to a text box is not an answer: this is a text question, and Skip is never clicked.
                    'Have you used AI coding tools? Which ones?': ['text', [], 'Yes - GPT and Claude'],
                    // A "Skip this question" choice among radio answers is navigation too: never an option, never clicked.
                    'Are you okay working from our Noida (Noida Extension) office?': ['radio', ['yes', 'no'], 'yes']};
  for (const [question, [kind, options, answer]] of Object.entries(expected)) {
    const seen = await run(js(ID, 'read', ''));
    assert.equal(seen.question, question); assert.equal(seen.kind, kind); assert.deepEqual(seen.options, options, 'only real options, never a wrapper');
    if (kind !== 'text') assert.deepEqual(await run(js(ID, 'option', 'Maybe', question)), {ok: true, answered: false, reason: 'no-such-option'});
    assert.equal((await run(js(ID, kind === 'text' ? 'text' : 'option', answer, question))).answered, true);
    await sleep(900);
    const after = await run(js(ID, 'read', ''));
    assert.ok(after.open === false || after.lastSave?.saved !== false || kind === 'chips', JSON.stringify(after.lastSave));
  }
  const end = await run(js(ID, 'read', ''));
  assert.equal(end.open, false); assert.equal(end.applied, true);
  assert.deepEqual(await run('JSON.stringify(window.__answers)'), ['Immediate joiner', 'Yes', 'Yes', 'Yes - GPT and Claude', 'yes'], 'the text answer was saved and Skip was never clicked');
  console.log('June Browser recruiter-question script: mock check passed (text, radio, chips, wrong job, unknown option, changed question before entry and before Save, other job before Save, replaced box before Save, placeholder-like text, text box beside a Skip chip, Skip among radio answers).');
  ws.close();
} finally {
  const exited = new Promise(r => chrome.once('exit', r));
  chrome.kill(); server.close();
  await Promise.race([exited, sleep(3000)]);
  fs.rmSync(work, {recursive: true, force: true, maxRetries: 5, retryDelay: 200});
}
