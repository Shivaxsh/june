import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const dataUrl = source => 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
const read = path => readFile(new URL(path, import.meta.url), 'utf8');
const compile = source => ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const libUrl = dataUrl(compile(await read('../lib/integrations.ts')));
const integrations = await import(libUrl);
const mail = await import(dataUrl(compile(await read('../lib/mail.ts')).replaceAll('"./integrations"', JSON.stringify(libUrl))));
function http(replies) {
  const calls = [];
  const fn = async (url, init = {}) => { calls.push({ url, method: init.method ?? 'GET', body: init.body ? JSON.parse(init.body) : undefined }); const next = replies.shift(); return { ok: true, status: 200, json: async () => next.body }; };
  return { fn, calls };
}
const mailState = (o = {}) => ({ version: 1, serverNow: 1, enabled: true, installed: true, accounts: ['Gmail'], unread: 2, recent: [{ name: 'Rahul', subject: 'Standup', date: '2026-11-18T09:00:00Z', unread: true }], ...o });
const job = (o = {}) => ({ id: '181125000123', title: 'React Developer', company: 'Acme', location: 'Bengaluru', experience: '3-5 Yrs', salary: '', score: 82, reason: 'React match', status: 'found', detail: '', at: 5, ...o });
const jobsState = (o = {}) => ({ version: 1, serverNow: 1, enabled: true, installed: true, dailyLimit: 10, appliedToday: 0, stopped: false, jobs: [job()], ...o });

test('email state is checked strictly and only allow/deny is sent', async () => {
  const a = http([{ body: mailState() }, { body: mailState({ enabled: false, accounts: [], unread: null, recent: [] }) }]);
  assert.equal((await mail.getMail(a.fn)).recent[0].subject, 'Standup');
  await mail.allowMail(false, a.fn);
  assert.deepEqual(a.calls.map(c => [c.url, c.body]), [['/api/mail', undefined], ['/api/mail/enable', { allowed: false }]]);
  for (const bad of [mailState({ enabled: 'yes' }), mailState({ unread: -1 }), mailState({ recent: [{ name: 'x' }] }), mailState({ accounts: [5] })])
    await assert.rejects(mail.getMail(http([{ body: bad }]).fn));
});

test('jobs are parsed strictly, and applying is always a reviewed plan of one to five job ids', async () => {
  const got = await mail.getJobs(http([{ body: jobsState() }]).fn);
  assert.equal(got.jobs[0].score, 82);
  for (const bad of [jobsState({ jobs: [job({ id: '../x' })] }), jobsState({ jobs: [job({ status: 'hired' })] }), jobsState({ jobs: [job({ score: 120 })] }), jobsState({ dailyLimit: '10' })])
    await assert.rejects(mail.getJobs(http([{ body: bad }]).fn));
  const plan = { id: 'plan-0001', revision: 1, fingerprint: 'fp-0000001', status: 'proposed', title: 'x', createdAt: 1, expiresAt: 2, rememberable: false,
    steps: [{ id: 'step-1', capability: 'jobs.apply', label: 'Apply: React Developer at Acme', preview: 'p', status: 'pending' }] };
  const a = http([{ body: { version: 1, serverNow: 5, plan } }]);
  await integrations.proposePlan('job-apply', a.fn, () => 'req-00000060', { ids: ['181125000123'] });
  assert.deepEqual(a.calls[0].body.input, { ids: ['181125000123'] });
  for (const input of [{ ids: [] }, { ids: ['1', '2', '3', '4', '5', '6'] }, { ids: ['abc'] }, { ids: ['181125000123', '181125000123'] }, { ids: ['181125000123'], url: 'x' }])
    await assert.rejects(integrations.proposePlan('job-apply', http([]).fn, () => 'r', input), e => e.code === 'invalid-input', JSON.stringify(input));
  await assert.rejects(mail.jobSettings({ dailyLimit: 99 }, http([]).fn), e => e.code === 'invalid-input');
  await assert.rejects(mail.skipJob('../x', http([]).fn), e => e.code === 'invalid-input');
});

test('the panel explains consent, risk and honesty, and the bridges allow only known endpoints', async () => {
  const panel = await read('../components/integrations/MailJobsPanel.tsx');
  assert.match(panel, /% title keywords/); assert.doesNotMatch(panel, /% fit/, 'the score is title keyword coverage, not suitability');
  assert.match(panel, /isn’t a judgement of fit: read the full role and your resume before approving/);
  for (const words of [/sent only if you approve that exact email/, /never as instructions/, /Allow JavaScript from Apple Events/, /only when Naukri’s own page confirms/,
                       /account could be restricted/, /Choose up to 5 jobs/, /Stop applying/])
    assert.match(panel, words);
  const mailBridge = await read('../app/api/mail/[[...path]]/route.ts');
  assert.match(mailBridge, /route === "enable"/); assert.doesNotMatch(mailBridge, /send/);
  const jobsBridge = await read('../app/api/jobs/[[...path]]/route.ts');
  assert.match(jobsBridge, /\\d\{8,16\}\\\/\(\?:skip\|check\)/); assert.doesNotMatch(jobsBridge, /apply/, 'applying goes through plans only');
  assert.match(await read('../components/Chat.tsx'), /<MailJobsPanel plans=\{integrations\.plans\}/);
});

test('a permission that stopped working is shown as a problem, never as plain “allowed”', async () => {
  assert.equal((await mail.getMail(http([{ body: mailState() }]).fn)).problem, null, 'absent means not reported');
  assert.equal((await mail.getMail(http([{ body: mailState({ problem: 'disk-access', recent: [] }) }]).fn)).problem, 'disk-access');
  assert.equal((await mail.getJobs(http([{ body: jobsState({ problem: 'javascript-off' }) }]).fn)).problem, 'javascript-off');
  for (const bad of [mailState({ problem: 'hacked' }), mailState({ problem: 3 })]) await assert.rejects(mail.getMail(http([{ body: bad }]).fn));
  await assert.rejects(mail.getJobs(http([{ body: jobsState({ problem: 'disk-access' }) }]).fn), 'jobs have their own problem words');
  const panel = await read('../components/integrations/MailJobsPanel.tsx');
  assert.match(panel, /allowed, but not working right now/);
  assert.match(panel, /Refresh Mail status/); assert.match(panel, /guarded\("refresh", async \(\) => \{ const next = await getMail\(\)/, 'a repaired permission clears without reloading or toggling consent'); assert.match(panel, /needs Full Disk Access again/); assert.match(panel, /Allow JavaScript from Apple Events” is off/);
});

test('sent-email receipts are strict, read-only to re-check, and never offer a resend', async () => {
  const receipt = (o = {}) => ({ id: 'a'.repeat(32), to: ['me@home.in'], subject: 'Test from June', status: 'pending', at: 5, ...o });
  assert.deepEqual((await mail.getMail(http([{ body: mailState() }]).fn)).receipts, [], 'absent means none');
  const got = await mail.getMail(http([{ body: mailState({ receipts: [receipt(), receipt({ id: 'b'.repeat(32), status: 'verified' })] }) }]).fn);
  assert.deepEqual(got.receipts.map(r => r.status), ['pending', 'verified']);
  for (const bad of [receipt({ id: 'x' }), receipt({ status: 'sent' }), receipt({ to: [] }), receipt({ to: ['not an address'] }), receipt({ subject: '' }), receipt({ at: 'now' }), receipt({ body: undefined, to: 'me@home.in' })])
    await assert.rejects(mail.getMail(http([{ body: mailState({ receipts: [bad] }) }]).fn), JSON.stringify(bad));
  await assert.rejects(mail.getMail(http([{ body: mailState({ receipts: Array.from({ length: 21 }, () => receipt()) }) }]).fn));
  const a = http([{ body: mailState({ receipts: [receipt({ status: 'verified' })] }) }]);
  await mail.checkReceipt('a'.repeat(32), a.fn);
  assert.deepEqual([a.calls[0].url, a.calls[0].method, a.calls[0].body], [`/api/mail/receipts/${'a'.repeat(32)}/check`, 'POST', {}]);
  await assert.rejects(mail.checkReceipt('../x', http([]).fn), e => e.code === 'invalid-input');
  const panel = await read('../components/integrations/MailJobsPanel.tsx');
  for (const words of [/Send outcome not confirmed yet/, /Verified in Sent/, /"not-sent": "Not sent"/, /Check Sent again/, /never sends the email again/]) assert.match(panel, words);
  assert.match(panel, /Email send checks/); assert.doesNotMatch(panel, /Emails June sent/, 'a pending or not-sent row is not an email June sent');
  assert.match(panel, /disabled=\{!!busy \|\| !mail\.enabled \|\| !!mail\.problem\}/, 'no check without working Mail access');
  assert.doesNotMatch(panel, /[Rr]esend|Send again/, 'no way to send twice from the panel');
  const bridge = await read('../app/api/mail/[[...path]]/route.ts');
  assert.match(bridge, /receipts\\\/\[a-f0-9\]\{32\}\\\/check/);
});

test('the screen setting is parsed strictly and only allow/deny is ever sent', async () => {
  const screen = await import(dataUrl(compile(await read('../lib/screen.ts')).replaceAll('"./integrations"', JSON.stringify(libUrl))));
  const state = (o = {}) => ({ version: 1, serverNow: 1, enabled: false, installed: true, problem: null, ...o });
  const a = http([{ body: state() }, { body: state({ enabled: true }) }]);
  assert.equal((await screen.getScreen(a.fn)).enabled, false);
  assert.equal((await screen.allowScreen(true, a.fn)).enabled, true);
  assert.deepEqual(a.calls.map(c => [c.url, c.body]), [['/api/screen', undefined], ['/api/screen/enable', { allowed: true }]]);
  for (const bad of [state({ enabled: 'yes' }), state({ problem: 'hacked' }), state({ installed: undefined })])
    await assert.rejects(screen.getScreen(http([{ body: bad }]).fn));
});

test('screen panel requests: one change at a time, and stale replies never win', async () => {
  const screen = await import(dataUrl(compile(await read('../lib/screen.ts')).replaceAll('"./integrations"', JSON.stringify(libUrl))));
  const r = screen.screenRequests();
  const firstRead = r.read();
  const change = r.change();
  assert.ok(change);
  assert.equal(r.change(), null, 'a double click while the first change runs does nothing');
  assert.equal(firstRead(), false, 'a status read started before the change is stale');
  assert.equal(change.current(), true);
  const duringChange = r.read();
  assert.equal(duringChange(), false, 'a read started mid-change may hold the old setting: ignored');
  assert.equal(change.current(), true, 'and it does not discard the change reply');
  change.done();
  const afterwards = r.read(); assert.equal(afterwards(), true); assert.equal(change.current(), false);
  const again = r.change(); assert.ok(again, 'after it finishes, the next change may start'); again.done();
});

test('a refused change reloads the real screen setting only after releasing its guard', async () => {
  const screen = await import(dataUrl(compile(await read('../lib/screen.ts')).replaceAll('"./integrations"', JSON.stringify(libUrl))));
  const r = screen.screenRequests();
  const change = r.change();
  assert.equal(r.read()(), false, 'a recovery read while the guard is held would be ignored');
  change.done();
  assert.equal(r.read()(), true, 'the same read after releasing the guard is current');
  const panel = await read('../components/integrations/ScreenPanel.tsx');
  const released = panel.indexOf('change.done()'), recovery = panel.indexOf('void load()', panel.indexOf('async function toggle'));
  assert.ok(released > 0 && recovery > released, 'the panel releases the guard before its recovery read');
  assert.ok(!/catch[^}]*void load\(\)/.test(panel), 'no recovery read inside the catch, where the guard is still held');
});

test('checking a job again is read-only on the server, needs a valid id, and returns its message', async () => {
  const a = http([{ body: { ...jobsState({ jobs: [job({ status: 'applied' })] }), message: 'Naukri shows React Developer at Acme as applied.' } }]);
  const got = await mail.checkJob('181125000123', a.fn);
  assert.equal(got.jobs.jobs[0].status, 'applied'); assert.match(got.message, /Naukri shows/);
  assert.deepEqual(a.calls.map(c => [c.url, c.body]), [['/api/jobs/181125000123/check', {}]]);
  await assert.rejects(mail.checkJob('../x', http([]).fn));
  await assert.rejects(mail.checkJob('181125000123', http([{ body: { ...jobsState(), message: 5 } }]).fn));
});

test('recruiter questions and taught answers are parsed strictly; teaching sends only the question and answer', async () => {
  const q = { key: 'will you sign a 2 year bond', question: 'Will you sign a 2 year bond?', options: ['Yes', 'No'], job: '181125000123' };
  const a = http([{ body: jobsState({ questions: [q], answers: [], standing: true }) }, { body: jobsState({ questions: [], answers: [{ key: q.key, question: q.question, answer: 'No' }], standing: true }) }, { body: jobsState() }]);
  const got = await mail.getJobs(a.fn);
  assert.equal(got.questions[0].options[1], 'No'); assert.equal(got.standing, true);
  assert.equal((await mail.teachAnswer(q.question, ' No ', a.fn)).answers[0].answer, 'No');
  await mail.forgetAnswer(q.key, a.fn);
  assert.deepEqual(a.calls.map(c => [c.url, c.body]), [['/api/jobs', undefined], ['/api/jobs/answers', { question: q.question, answer: 'No' }], ['/api/jobs/answers/forget', { key: q.key }]]);
  for (const bad of [jobsState({ questions: [{ ...q, job: '../x' }] }), jobsState({ answers: [{ key: 'k', question: 'q', answer: 5 }] }), jobsState({ standing: 'yes' })])
    await assert.rejects(mail.getJobs(http([{ body: bad }]).fn));
  await assert.rejects(mail.teachAnswer(q.question, '   ', http([]).fn));
  await assert.rejects(mail.teachAnswer(q.question, 'x'.repeat(301), http([]).fn));
  const panel = await read('../components/integrations/MailJobsPanel.tsx');
  assert.match(panel, /answers them from your saved answers and submits/); assert.match(panel, /log-in, captcha, OTP, test/);
});

test('job check messages may name long jobs, and taught answers are single-line', async () => {
  const long = 'Naukri shows ' + 'Very Long Title '.repeat(20) + 'at ' + 'Company '.repeat(20) + 'as applied. I’ve recorded it.';
  assert.ok(long.length > 400);
  const got = await mail.checkJob('181125000123', http([{ body: { ...jobsState(), message: long } }]).fn);
  assert.equal(got.message, long);
  await assert.rejects(mail.checkJob('181125000123', http([{ body: { ...jobsState(), message: 'x'.repeat(1001) } }]).fn));
  for (const bad of ['line one\nline two', 'tab\there', 'cr\r'])
    await assert.rejects(mail.teachAnswer('Q?', bad, http([]).fn), JSON.stringify(bad));
});

test('the recruiter-question page script is bound to the reviewed job and never takes raw text', async () => {
  const swift = await read('../native/JuneBrowser.swift');
  const template = swift.match(/let chatTemplate = #"""\n([\s\S]*?)\n"""#/)[1];
  assert.match(template, /\[1\] === 'JOB_ID';\n\s*if \(!sameJob\(\)\) return out\(\{ok: false, reason: 'different-job'\}\);/, 'checked inside the same script as any typing or clicking');
  assert.match(template, /const MODE = MODE_VALUE, VALUE = VALUE_VALUE, EXPECTED = EXPECTED_VALUE;/);
  assert.match(template, /if \(question !== EXPECTED\) return out\(\{ok: true, answered: false, reason: 'question-changed', question\}\);/, 'no entry into a different question');
  assert.match(template, /setTimeout\(\(\) => \{\n\s*if \(!sameJob\(\)\) \{ window\.__juneLastSave = \{question: EXPECTED, saved: false, reason: 'different-job'\}; return; \}/, 'the delayed Save rechecks the exact job first');
  assert.match(template, /location\.protocol === 'https:' && location\.hostname\.replace\(\/\^www\\\.\/, ''\) === 'naukri\.com'/);
  assert.match(template, /entered = \(\) => box\.isConnected && !!findDrawer\(\)\?\.contains\(box\)/, 'the box must still be the live one');
  assert.match(template, /if \(questionIn\(d\) !== EXPECTED\) \{ window\.__juneLastSave = \{question: EXPECTED, saved: false, reason: 'question-changed'\}; return; \}/, 'Save re-checks the question');
  assert.match(template, /if \(!entered\(\)\) \{ window\.__juneLastSave = \{question: EXPECTED, saved: false, reason: 'answer-changed'\}; return; \}/, 'and the entered answer');
  assert.match(template, /if \(MODE === 'read'\) return out\(\{ok: true, open: true, applied, question, kind, options, lastSave: window\.__juneLastSave \|\| null\}\);/);
  for (const placeholder of ['JOB_ID', 'MODE_VALUE', 'VALUE_VALUE', 'EXPECTED_VALUE'])
    assert.ok(template.split(placeholder).length >= 2, placeholder);
  assert.match(swift, /func fill\(_ template:String, _ values:\[String:String\]\) -> String\? \{\n\s*guard let pattern = try\? NSRegularExpression\(pattern:"JOB_ID\|MODE_VALUE\|EXPECTED_VALUE\|VALUE_VALUE"\)/, 'placeholders are filled in one pass');
  assert.doesNotMatch(template, /\beval\(|new Function|innerHTML\s*=/, 'no code or markup from values');
  assert.match(template, /!e\.querySelector\('\[class\*="chip"\]/, 'only innermost chips are options');
  const navigation = new RegExp(template.match(/const navigation = \/(.+)\/i;/)[1], 'i');
  for (const label of ['Skip this question', 'skip', 'SKIP THIS QUESTION']) assert.ok(navigation.test(label), label);
  for (const label of ["I'll do it later", 'Yes', 'No', 'Skip to resume upload', 'Skip the test round']) assert.ok(!navigation.test(label), `${label} stays an answer`);
  assert.match(template, /&& !navigation\.test\(t\(e\.innerText\)\)\);/, 'navigation chips are never options');
  assert.match(template, /input\[type=radio\]'\)\]\.filter\(i => !navigation\.test\(labelOf\(i\)\)\)/, 'nor radio choices');
  assert.match(template, /input\[type=checkbox\]'\)\]\.filter\(i => !navigation\.test\(labelOf\(i\)\)\)/, 'nor checkbox choices');
  assert.match(swift, /case "read":\n\s*guard value\.isEmpty, expected == nil else \{ return nil \}/, 'read takes no value or expected question');
  assert.match(swift, /case "text", "option":\n\s*guard validAnswer\(value\), let expected, validQuestion\(expected\)/, 'entry needs a one-line answer and the exact question');
  assert.match(swift, /guard keys == readKeys \|\| keys == readKeys\.union\(\["expectedQuestion"\]\)/, 'no other fields are accepted');
});

test('a live recruiter question carries its job and waiting time, and the chat card answers it', async () => {
  const q = { key: 'will you sign a 2 year bond', question: 'Will you sign a 2 year bond?', options: ['Yes', 'No'], job: '181125000123', title: 'Developer at Acme', waitingUntil: 5000 };
  const got = await mail.getJobs(http([{ body: jobsState({ questions: [q] }) }]).fn);
  assert.equal(got.questions[0].title, 'Developer at Acme'); assert.equal(got.questions[0].waitingUntil, 5000);
  const old = await mail.getJobs(http([{ body: jobsState({ questions: [{ key: q.key, question: q.question, options: [], job: q.job }] }) }]).fn);
  assert.equal(old.questions[0].waitingUntil, null, 'older replies without the new fields still parse');
  for (const bad of [{ ...q, waitingUntil: 'soon' }, { ...q, title: 5 }])
    await assert.rejects(mail.getJobs(http([{ body: jobsState({ questions: [bad] }) }]).fn));
  const card = await read('../components/integrations/JobQuestionCard.tsx');
  assert.match(card, /teachAnswer\(q\.question, value\)/, 'answering saves it through the same teach endpoint');
  assert.match(card, /q\.waitingUntil !== null && q\.waitingUntil > now/, 'only questions June is still waiting on are shown');
  const chat = await read('../components/Chat.tsx');
  assert.match(chat, /<JobQuestionCard active=\{integrations\.plans\.some\(p => \(p\.status === "approved" \|\| p\.status === "running"\) && p\.steps\.some\(s => s\.capability === "jobs\.apply"\)\)\}/);
});

test('live questions: a refresh from before an answer never brings it back, a re-ask shows again, a new ask is announced again', async () => {
  const { liveQuestions } = mail;
  assert.equal(typeof liveQuestions, 'function', 'the card keeps its live-question rules in lib/mail.ts');
  const q = (key, until = 100000) => ({ key, question: key + '?', options: ['Yes', 'No'], job: '181125000123', title: 'Dev', waitingUntil: until });
  const live = liveQuestions({ hold: 10000 });
  const first = live.begin();
  let view = live.accept(first, [q('bond')], 1000);
  assert.deepEqual(view.visible.map(x => x.key), ['bond']); assert.deepEqual(view.announce.map(x => x.key), ['bond']);
  const stale = live.begin();            // a refresh starts…
  assert.equal(live.answer(q('bond'), 2000), true, 'the answer is taken');
  assert.equal(live.answer(q('bond'), 2001), false, 'a second tap while it is being sent is ignored');
  live.settle(q('bond'));
  assert.equal(live.accept(stale, [q('bond')], 2500), null, '…and finishes after the answer: ignored');
  view = live.accept(live.begin(), [q('bond')], 3000);
  assert.deepEqual(view.visible, [], 'still listed while June picks it up: stays hidden');
  view = live.accept(live.begin(), [q('bond')], 13000);
  assert.deepEqual(view.visible.map(x => x.key), ['bond'], 'still waiting long after: June asked again, show it');
  view = live.accept(live.begin(), [], 14000);
  assert.deepEqual(view.visible, []);
  view = live.accept(live.begin(), [q('bond', 200000)], 15000);
  assert.deepEqual(view.announce.map(x => x.key), ['bond'], 'asked again later (another application): announced again');
  assert.deepEqual(live.accept(live.begin(), [q('old', 500)], 16000).visible, [], 'past its waiting time: not shown');
});

test('the live-question card is a labelled region, not an alert that re-reads every second', async () => {
  const card = await read('../components/integrations/JobQuestionCard.tsx');
  assert.doesNotMatch(card, /role="alert" aria-label="June needs your answer"/, 'the countdown would be re-announced every second');
  assert.match(card, /<section className="job-question-card hud-panel" role="region" aria-label="June needs your answer">/);
  assert.match(card, /aria-hidden="true">waiting/, 'the ticking countdown is not read out');
  assert.match(card, /liveQuestions\(/, 'the card uses the tested rules');
});

test('live questions: a stale refresh stays stale after the answered question disappears', async () => {
  const q = (key, job = '181125000123', until = 100000) => ({ key, question: key + '?', options: ['Yes', 'No'], job, title: 'Dev', waitingUntil: until });
  const live = mail.liveQuestions({ hold: 10000 });
  live.accept(live.begin(), [q('bond')], 1000);
  const old = live.begin();                         // token 1: an old refresh starts
  live.answer(q('bond'), 2000); live.settle(q('bond'));
  assert.deepEqual(live.accept(live.begin(), [], 3000).visible, [], 'a newer refresh: nothing waiting any more');
  assert.equal(live.accept(old, [q('bond')], 3500), null, 'the old refresh still loses: the barrier is permanent');
});

test('live questions: each wait is its own instance (job + waiting time), so a new wait is announced and shown', async () => {
  const q = (key, job, until) => ({ key, question: key + '?', options: ['Yes', 'No'], job, title: 'Dev', waitingUntil: until });
  const live = mail.liveQuestions({ hold: 10000 });
  let view = live.accept(live.begin(), [q('bond', '181125000123', 100000)], 1000);
  assert.equal(view.announce.length, 1);
  live.answer(q('bond', '181125000123', 100000), 2000); live.settle(q('bond', '181125000123', 100000));
  view = live.accept(live.begin(), [q('bond', '181125000456', 200000)], 3000);   // same question, another job, no empty poll between
  assert.deepEqual(view.visible.map(x => x.job), ['181125000456'], 'answering one wait does not hide a different wait');
  assert.deepEqual(view.announce.map(x => x.job), ['181125000456'], 'and the new wait is announced');
  view = live.accept(live.begin(), [q('bond', '181125000456', 300000)], 4000);   // same job, re-asked with a new waiting time
  assert.deepEqual(view.announce.map(x => x.waitingUntil), [300000], 'a fresh wait for the same job is announced again');
});

test('live questions: refreshes finishing out of order never roll the card back', async () => {
  const q = (key, until = 100000) => ({ key, question: key + '?', options: ['Yes', 'No'], job: '181125000123', title: 'Dev', waitingUntil: until });
  const live = mail.liveQuestions({ hold: 10000 });
  const older = live.begin(), newer = live.begin();
  assert.deepEqual(live.accept(newer, [q('new')], 1000).visible.map(x => x.key), ['new']);
  assert.equal(live.accept(older, [q('old')], 1100), null, 'the older refresh finished later: ignored, no regression or re-announcement');
  assert.deepEqual(live.accept(live.begin(), [q('new')], 1200).announce, [], 'the newer question was already announced once');
});

test('a finished job application from anywhere (chat, other tab, reload) refreshes the jobs list once', async () => {
  const { finishedApplications } = mail;
  assert.equal(typeof finishedApplications, 'function');
  const plan = (id, status, capability = 'jobs.apply') => ({ id, status, steps: [{ capability }] });
  const seen = new Set();
  assert.equal(finishedApplications(seen, [plan('a', 'completed'), plan('m', 'completed', 'mail.send')], true), false, 'already finished when the panel opened: the first load covers it');
  assert.equal(finishedApplications(seen, [plan('a', 'completed'), plan('b', 'running')]), false, 'still running');
  assert.equal(finishedApplications(seen, [plan('a', 'completed'), plan('b', 'completed')]), true, 'a chat-created application just finished');
  assert.equal(finishedApplications(seen, [plan('a', 'completed'), plan('b', 'completed')]), false, 'only once');
  assert.equal(finishedApplications(seen, [plan('c', 'unknown')]), true, 'any outcome counts (unknown, failed, cancelled)');
  assert.equal(finishedApplications(seen, [plan('d', 'expired')]), false, 'an expired card never ran');
  assert.equal(finishedApplications(seen, [plan('e', 'completed', 'mail.send')]), false, 'other cards do not refetch jobs');
});

test('jobs replies: only the newest request may update the list', async () => {
  const replies = mail.newestReplies();
  const older = replies.begin(), newer = replies.begin();
  assert.equal(replies.take(newer), true);
  assert.equal(replies.take(older), false, 'an older reply arriving later is dropped');
  const panel = await read('../components/integrations/MailJobsPanel.tsx');
  assert.match(panel, /finishedApplications\(seenApplications\.current!?, plans/, 'every finished application refreshes jobs, not just the panel’s own card');
  assert.match(panel, /const refreshJobs = useCallback\(\(\) => updateJobs\(getJobs\(\)\)/, 'a finished application refetches jobs only, never Mail');
  assert.doesNotMatch(panel, /setJobs\(next/, 'every jobs update goes through the newest-reply guard');
});
