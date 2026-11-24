import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const dataUrl = source => 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
const read = path => readFile(new URL(path, import.meta.url), 'utf8');
const compile = source => ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const integrationsUrl = dataUrl(compile(await read('../lib/integrations.ts')));
const transactionsUrl = dataUrl(compile(await read('../lib/transactions.ts')).replaceAll('"./integrations"', JSON.stringify(integrationsUrl)));
const lib = await import(dataUrl(compile(await read('../lib/commerce-voice.ts')).replaceAll('"./integrations"', JSON.stringify(integrationsUrl)).replaceAll('"./transactions"', JSON.stringify(transactionsUrl))));
function http(replies) {
  const calls = [];
  const fn = async (url, init = {}) => { calls.push({ url, body: init.body ? JSON.parse(init.body) : undefined }); return { ok: true, status: 200, json: async () => replies.shift() }; };
  return { fn, calls };
}
const review = { transactionId: 'tx-1', planId: 'a'.repeat(32), revision: 1, fingerprint: 'fp-0000001', text: 'Simulated order from Sim Mart: two kilos of rice, five hundred twenty rupees in total, delivered today.' };

test('the client approval phrases are exactly the backend’s', async () => {
  const backend = await read('../backend/june/commerce.py');
  const source = backend.match(/APPROVAL=re\.compile\(r'([^']+)'/)[1];
  assert.equal(lib.APPROVAL_SOURCE, source, 'keep lib/commerce-voice.ts APPROVAL_SOURCE in sync with backend june/commerce.py');
});

test('only explicit go-aheads approve; bare yes asks again; corrections, quotes and questions never approve', () => {
  for (const t of ['I approve', 'Go ahead.', 'yes, book it', 'Hey June, place the order', 'confirm the booking', 'book it!'])
    assert.equal(lib.classifyReply(t), 'approve', t);
  for (const t of ['yes', 'Okay', 'sure', 'yeah.', 'do it']) assert.equal(lib.classifyReply(t), 'ambiguous', t);
  for (const t of ["don't go ahead", 'go ahead? wait', 'make it 3 then go ahead', 'no, cheaper', 'he said go ahead', '"I approve"',
                   'go ahead and book it for tomorrow instead', 'I approve but change the time', 'cancel', 'what is the total', ''])
    assert.equal(lib.classifyReply(t), 'other', t);
  assert.equal(lib.classifyReply(lib.CLARIFY), 'other', 'June’s own clarification can never approve if echoed');
  assert.equal(lib.classifyReply(review.text), 'other', 'nor can the review itself');
  assert.doesNotMatch(lib.CLARIFY, new RegExp(lib.APPROVAL_SOURCE.replace(/^\(\?:/, '\\b(?:'), 'i'), 'the clarification contains no accepted phrase');
});

test('arming waits for the exact spoken review to finish, and any change disarms', () => {
  const consent = new lib.VoiceConsent();
  consent.expect(review, 'session-1', 'req-uuid-1');
  assert.equal(consent.completed('req-uuid-other'), null, 'another playback finishing never arms');
  consent.expect(review, 'session-1', 'req-uuid-1');
  const due = consent.completed('req-uuid-1');
  assert.equal(due.requestId, 'req-uuid-1'); assert.equal(consent.completed('req-uuid-1'), null, 'once only');
  consent.setArmed(due, 'token-12345678', 5000);
  const again = consent.route('yes', 'session-1', 1000);
  assert.equal(again.kind, 'reread'); assert.equal(again.review.text, review.text, 'June re-reads the exact review');
  assert.equal(consent.armed, null, 'the old token is dropped (the server disarmed it); re-reading re-arms a fresh one');
  consent.setArmed(due, 'token-12345678', 5000);
  assert.equal(consent.route('go ahead', 'session-2', 1000).kind, 'pass', 'another hands-free session never approves'); assert.equal(consent.armed, null);
  consent.setArmed(due, 'token-12345678', 5000);
  assert.equal(consent.route('I approve', 'session-1', 6000).kind, 'pass', 'expired'); assert.equal(consent.armed, null);
  consent.setArmed(due, 'token-12345678', 5000);
  assert.equal(consent.route('make it 3 people', 'session-1', 1000).kind, 'pass'); assert.equal(consent.armed, null, 'a correction voids the review');
  consent.setArmed(due, 'token-12345678', 5000);
  const ok = consent.route('I approve', 'session-1', 1000);
  assert.equal(ok.kind, 'approve'); assert.equal(ok.armed.reviewToken, 'token-12345678'); assert.equal(consent.armed, null, 'one use');
  assert.equal(consent.route('I approve', 'session-1', 1000).kind, 'pass', 'a repeated go-ahead does nothing');
  consent.setArmed(due, 'token-12345678', 5000); consent.expect({ ...review, revision: 2 }, 'session-1', 'req-uuid-2');
  assert.equal(consent.armed, null, 'a new review disarms the old one before it is spoken');
});

test('arm and voice-approve send only ids and the bound quote; the server decides', async () => {
  const plan = { id: review.planId, revision: 1, fingerprint: 'fp-0000001', status: 'approved', title: 'Simulated purchase', createdAt: 1, expiresAt: 2, rememberable: false,
    steps: [{ id: 's1', capability: 'commerce.commit', label: 'Simulated purchase', preview: 'Sim Mart', status: 'pending' }] };
  const a = http([{ version: 1, serverNow: 5, reviewToken: 'token-12345678', expiresAt: 65000 }, { version: 1, serverNow: 6, plan }]);
  const armed = await lib.arm({ ...review, sessionId: 'session-1', requestId: 'req-uuid-1' }, a.fn);
  const consent = new lib.VoiceConsent(); consent.setArmed({ ...review, sessionId: 'session-1', requestId: 'req-uuid-1' }, armed.reviewToken, armed.expiresAt);
  const approved = await lib.voiceApprove(consent.armed, 7, a.fn, () => 'approve-req-1');
  assert.equal(approved.plan.status, 'approved');
  assert.deepEqual(a.calls.map(c => [c.url, c.body]), [
    ['/api/transactions/tx-1/arm', { planId: review.planId, revision: 1, fingerprint: 'fp-0000001', sessionId: 'session-1', requestId: 'req-uuid-1' }],
    [`/api/plans/${review.planId}/voice-approve`, { requestId: 'approve-req-1', revision: 1, fingerprint: 'fp-0000001', reviewToken: 'token-12345678', sessionId: 'session-1', turnId: 7 }]]);
  assert.ok(!a.calls.some(c => 'text' in (c.body ?? {}) || 'voice' in (c.body ?? {})), 'no transcript or voice flag from the client');
  await assert.rejects(lib.voiceApprove(consent.armed ?? { ...review, sessionId: 's', reviewToken: 'token-12345678', expiresAt: 1 }, 0, http([]).fn));
  await assert.rejects(lib.arm({ ...review, sessionId: '', requestId: 'r' }, http([]).fn));
});

test('Chat arms only after the exact hands-free reply finished, routes replies before the model, and disarms on change', async () => {
  const chat = await read('../components/Chat.tsx');
  assert.match(chat, /const speakingRequest = voice\.requestId\(\);/);
  assert.match(chat, /const kind = automatic && speakingRequest && proposedPlan \? reviewKind\(t, proposedPlan\) : null;\s*if \(kind && proposedPlan\)\s*consent\.current\.expect\(\{ transactionId: t\.id, planId: proposedPlan\.id, revision: proposedPlan\.revision, fingerprint: proposedPlan\.fingerprint, text: base \+ reply, kind \}/, 'only a hands-free reply carrying this transaction’s own exact review');
  assert.match(chat, /const finished = voice\.speech\.completedRequest;\n\s*const due = finished \? consent\.current\.completed\(finished\) : null;/, 'arming waits for native playback of that reply to end');
  assert.match(chat, /const decision = consent\.current\.route\(content, handsFree\.sessionId\(\), Date\.now\(\)\);\n\s*if \(decision\.kind === "pass"\) \{ void send\(/, 'replies are routed before reaching the model');
  assert.match(chat, /if \(automatic\) consent\.current\.disarm\(\);/);
  assert.match(chat, /useEffect\(\(\) => \{ if \(!handsFree\.active\) consent\.current\.disarm\(\); \}, \[handsFree\.active\]\);/);
  assert.match(chat, /Tap Approve on the card to book it\./, 'if arming fails, the card stays the way to approve');
  assert.match(chat, /function speakTurn\(turn: number, text: string\) \{[\s\S]{0,200}voice\.begin\(id, true, \{ voiceSessionId: handsFree\.sessionId\(\), turnId: turn \}\);/, 'consent replies are spoken in the turn’s own native context');
  assert.match(chat, /const requestId = speakTurn\(turn, `\$\{CLARIFY\} \$\{decision\.review\.text\}`\);\n\s*consent\.current\.expect\(decision\.review, handsFree\.sessionId\(\), requestId\);/, 'an ambiguous reply re-reads and re-arms');
  assert.match(chat, /const outcome = await waitForOutcome\(armed\.transactionId, id => getTransaction\(id\), \{ kind: armed\.kind \}\);[\s\S]{0,120}speakTurn\(turn, outcomeSpeech\(outcome, armed\.kind\)\);/, 'June speaks the verified receipt');
  assert.equal(chat.match(/voice\.announce\(/g).length, 1, 'the alert queue stays the only announcer');
});

test('June waits (bounded, read-only) for the simulated outcome and speaks only a verified receipt as done', async () => {
  const base = { id: 'tx-1', conversationId: 'panel-x', domain: 'retail', simulated: true, slots: {}, missing: [], offers: [], quote: null, planId: null, lastReply: '' };
  const receipt = { id: 'r1', transactionId: 'tx-1', status: 'confirmed', simulated: true, totalMinor: 52000, currency: 'INR', createdAt: 5, detail: 'Simulated order SIM-1042' };
  let reads = 0, clock = 0;
  const states = [{ ...base, status: 'executing', receipt: null }, { ...base, status: 'executing', receipt: null }, { ...base, status: 'completed', receipt }];
  const done = await lib.waitForOutcome('tx-1', async () => ({ transaction: states[Math.min(reads++, 2)] }), { sleep: async ms => { clock += ms; }, now: () => clock });
  assert.equal(done.status, 'completed'); assert.equal(reads, 3);
  assert.equal(lib.outcomeSpeech(done), 'Done. Simulated receipt: Simulated order SIM-1042, ₹520. Nothing real was charged.');
  assert.match(lib.outcomeSpeech({ ...done, domain: 'dining', receipt: { ...receipt, totalMinor: 0 } }), /no charge/);
  clock = 0; reads = 0;
  const stuck = await lib.waitForOutcome('tx-1', async () => { reads++; return { transaction: states[0] }; }, { timeoutMs: 5000, intervalMs: 1000, sleep: async ms => { clock += ms; }, now: () => clock });
  assert.equal(stuck.status, 'executing'); assert.ok(reads <= 7, 'bounded');
  assert.match(lib.outcomeSpeech(stuck), /couldn’t confirm the outcome yet\. I won’t place it again/);
  assert.match(lib.outcomeSpeech(null), /won’t place it again/);
  assert.match(lib.outcomeSpeech({ ...base, status: 'expired', receipt: null }), /expired/);
});

test('a lost approval response after the server committed is reconciled read-only: never "nothing was booked", never a second approval', async () => {
  assert.equal(typeof lib.approvalFailureSpeech, 'function');
  const { IntegrationError } = await import(integrationsUrl);
  const base = { id: 'tx-1', conversationId: 'panel-x', domain: 'retail', simulated: true, slots: {}, missing: [], offers: [], quote: null, planId: null, lastReply: '' };
  const receipt = { id: 'r1', transactionId: 'tx-1', status: 'confirmed', simulated: true, totalMinor: 52000, currency: 'INR', createdAt: 5, detail: 'Simulated order SIM-1042' };
  const committed = { ...base, status: 'completed', receipt };
  const lost = new TypeError('Failed to fetch');                           // the response never arrived
  assert.equal(lib.approvalFailureSpeech(lost, committed), lib.outcomeSpeech(committed), 'the verified receipt is spoken');
  assert.equal(lib.approvalFailureSpeech(new IntegrationError('Server error', 503, 'unavailable'), committed), lib.outcomeSpeech(committed));
  for (const unclear of [null, { ...base, status: 'executing', receipt: null }, { ...base, status: 'unknown', receipt: null }]) {
    const said = lib.approvalFailureSpeech(lost, unclear);
    assert.doesNotMatch(said, /Nothing was booked/, 'a transport failure never claims nothing happened');
    assert.match(said, /won’t try it again/);
  }
  const refused = new IntegrationError('That was not an explicit go-ahead for this quote.', 409, 'voice-approval');
  assert.match(lib.approvalFailureSpeech(refused, { ...base, status: 'awaiting-approval', receipt: null }), /explicit go-ahead.*Nothing was booked\./, 'a definite refusal before any commit');
  assert.doesNotMatch(lib.approvalFailureSpeech(refused, null), /Nothing was booked/, 'even a refusal is not called "nothing booked" without reading the booking');
  assert.equal(lib.approvalFailureSpeech(refused, committed), lib.outcomeSpeech(committed), 'if it did complete (e.g. by tap), say so');

  const chat = await read('../components/Chat.tsx');
  const handler = chat.slice(chat.indexOf('void voiceApprove(armed, turn)'), chat.indexOf('},', chat.indexOf('void voiceApprove(armed, turn)') + 600) + 2);
  assert.match(handler, /\.catch\(async failure => \{[\s\S]*waitForOutcome\(armed\.transactionId, id => getTransaction\(id\), isDefiniteRejection\(failure\) \? \{ kind: armed\.kind, timeoutMs: 0 \} : \{ kind: armed\.kind \}\)[\s\S]*speakTurn\(turn, approvalFailureSpeech\(failure, outcome, armed\.kind\)\)/, 'the catch reconciles read-only before speaking');
  assert.doesNotMatch(handler, /Nothing was booked/, 'no unconditional claim in Chat');
  assert.equal(chat.match(/voiceApprove\(/g).length, 1, 'no second approval attempt anywhere');
});

test('a spoken cancel review of a confirmed order arms, waits for the cancellation (not the old receipt), and is spoken honestly', async () => {
  assert.equal(typeof lib.reviewKind, 'function');
  const base = { id: 'tx-1', conversationId: 'panel-x', domain: 'retail', simulated: true, slots: {}, missing: [], offers: [], quote: null, lastReply: '' };
  const receipt = { id: 'sim-1', transactionId: 'tx-1', status: 'confirmed', simulated: true, totalMinor: 62900, currency: 'INR', createdAt: 5, detail: 'Simulation: purchase confirmed' };
  const pid = 'b'.repeat(32);
  const plan = cap => ({ id: pid, status: 'proposed', steps: [{ capability: cap }] });
  const ordered = { ...base, status: 'completed', receipt, planId: pid };
  // Exactly two kinds of review arm: an awaiting quote's commit, and a confirmed order's cancel. Nothing else.
  assert.equal(lib.reviewKind({ ...base, status: 'quoted', receipt: null, planId: pid }, plan('commerce.commit')), 'commit');
  assert.equal(lib.reviewKind({ ...base, status: 'awaiting-approval', receipt: null, planId: pid }, plan('commerce.commit')), 'commit');
  assert.equal(lib.reviewKind(ordered, plan('commerce.cancel')), 'cancel');
  assert.equal(lib.reviewKind(ordered, plan('commerce.commit')), null, 'a completed order never re-arms a commit');
  assert.equal(lib.reviewKind({ ...ordered, planId: 'c'.repeat(32) }, plan('commerce.cancel')), null, 'only the transaction’s own plan');
  assert.equal(lib.reviewKind({ ...ordered, receipt: { ...receipt, status: 'cancelled' } }, plan('commerce.cancel')), null, 'already cancelled');
  assert.equal(lib.reviewKind({ ...ordered, status: 'unknown' }, plan('commerce.cancel')), null);
  assert.equal(lib.reviewKind({ ...base, status: 'quoted', receipt: null, planId: pid }, plan('commerce.cancel')), null);
  assert.equal(lib.reviewKind(ordered, { ...plan('commerce.cancel'), status: 'completed' }), null, 'only a proposed plan');

  // Waiting for a cancel: the still-completed order is not its outcome.
  const cancelled = { ...ordered, status: 'cancelled', receipt: { ...receipt, status: 'cancelled' } };
  let clock = 0, reads = 0;
  const states = [ordered, ordered, cancelled];
  const done = await lib.waitForOutcome('tx-1', async () => ({ transaction: states[Math.min(reads++, 2)] }), { kind: 'cancel', sleep: async ms => { clock += ms; }, now: () => clock });
  assert.equal(done.status, 'cancelled');
  assert.match(lib.outcomeSpeech(done, 'cancel'), /cancelled.*₹629.*Nothing real was charged/i);
  assert.doesNotMatch(lib.outcomeSpeech(ordered, 'cancel'), /^Done/, 'the old order receipt is never spoken as the cancel outcome');
  assert.match(lib.outcomeSpeech(ordered, 'cancel'), /couldn’t confirm the cancellation.*won’t send it again/);
  // A lost cancel response, or a definite refusal, is spoken honestly.
  const { IntegrationError } = await import(integrationsUrl);
  assert.equal(lib.approvalFailureSpeech(new TypeError('Failed to fetch'), cancelled, 'cancel'), lib.outcomeSpeech(cancelled, 'cancel'));
  assert.match(lib.approvalFailureSpeech(new TypeError('Failed to fetch'), ordered, 'cancel'), /couldn’t confirm the cancellation/);
  assert.match(lib.approvalFailureSpeech(new IntegrationError('That was not an explicit go-ahead for this quote.', 409, 'voice-approval'), ordered, 'cancel'), /explicit go-ahead.*Nothing was cancelled\./);
  // Commit behaviour is unchanged by default.
  assert.equal(lib.outcomeSpeech(ordered), lib.outcomeSpeech(ordered, 'commit'));

  // The review the consent holds carries its kind through arming and an ambiguous re-read.
  const consent = new lib.VoiceConsent();
  consent.expect({ transactionId: 'tx-1', planId: pid, revision: 1, fingerprint: 'fp-0000001', text: 'Cancel it?', kind: 'cancel' }, 'hf-1', 'req-1');
  const due = consent.completed('req-1'); consent.setArmed(due, 'token-12345678', 10_000);
  assert.equal(consent.armed.kind, 'cancel');
  assert.equal(consent.route('yes', 'hf-1', 1).review.kind, 'cancel');

  const chat = await read('../components/Chat.tsx');
  assert.match(chat, /const kind = automatic && speakingRequest && proposedPlan \? reviewKind\(t, proposedPlan\) : null;/, 'Chat gates arming through reviewKind only');
  assert.doesNotMatch(chat, /t\.status === "quoted" \|\| t\.status === "awaiting-approval"/, 'no separate status gate left in Chat');
  assert.match(chat, /waitForOutcome\(armed\.transactionId, id => getTransaction\(id\), \{ kind: armed\.kind \}\)[\s\S]{0,140}outcomeSpeech\(outcome, armed\.kind\)/);
  assert.match(chat, /approvalFailureSpeech\(failure, outcome, armed\.kind\)/);
});

test('natural spoken go-aheads approve; near-approvals with conditions, quotes or negation still never do', () => {
  for (const t of ['Yes, go ahead.', 'Okay, go ahead', 'ok go ahead', 'Go ahead please.', 'Go ahead and book it.', 'go ahead and place the order',
                   'I approve it', 'I approve the booking', 'Yes, please book it', 'Book it, please.', 'confirm the reservation', 'June: go ahead', 'Hey June, yes, go ahead.', 'Yeah, go ahead.', 'yeah go ahead', 'Yeah, book it.'])
    assert.equal(lib.classifyReply(t), 'approve', t);
  for (const t of ['Yes, go ahead but make it 3', 'go ahead and book it for tomorrow instead', 'Okay, go ahead?', 'she said "yes, go ahead"',
                   "No, don't go ahead", 'Yes, go ahead later', 'go ahead with a cheaper one', 'Go ahead, June.', 'yes go ahead and change the time'])
    assert.notEqual(lib.classifyReply(t), 'approve', t);
  for (const t of ['yes', 'okay', 'ok', 'sure', 'yeah', 'Yeah.']) assert.equal(lib.classifyReply(t), 'ambiguous', t);
  for (const t of ['Yeah, go ahead but cheaper', 'yeah no wait', 'Yeah, go ahead?']) assert.notEqual(lib.classifyReply(t), 'approve', t);
});
