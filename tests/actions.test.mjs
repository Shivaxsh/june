import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const load = async path => {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  return import('data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText).toString('base64'));
};
const A = await load('../lib/actions.ts');
const read = path => readFile(new URL(path, import.meta.url), 'utf8');
const card = await read('../components/actions/ActionCard.tsx');
const panel = await read('../components/actions/HandsPanel.tsx');
const chat = await read('../components/Chat.tsx');

const record = (extra = {}) => ({ id: 'act-12345678', action: 'open-vscode', label: 'Open VS Code', detail: 'Opens Visual Studio Code (com.microsoft.VSCode) on this Mac. Nothing else runs.',
  fingerprint: 'fp-abcdef012345', createdAt: 1_000_000, expiresAt: 1_300_000, status: 'proposed', ...extra });

test('only the allowlisted action with immutable server fields is accepted', () => {
  assert.deepEqual(A.parseAction(record()), record());
  assert.equal(A.parseAction(record({ action: 'run-shell' })), null);
  assert.equal(A.parseAction(record({ status: 'done' })), null);
  assert.equal(A.parseAction(record({ id: 'x' })), null);
  assert.equal(A.parseAction(record({ fingerprint: '' })), null);
  assert.equal(A.parseAction(record({ expiresAt: 'soon' })), null);
  for (const key of ['command', 'argv', 'args', 'path', 'shell', 'cwd'])
    assert.equal(A.parseAction(record({ [key]: '/bin/sh -c rm' })), null, `${key} is never accepted from the server`);
  assert.equal(A.parseAction(null), null);
  assert.deepEqual(A.parseAction(record({ status: 'completed', result: { state: 'active', message: 'VS Code is in front.' } })).result, { state: 'active', message: 'VS Code is in front.' });
  assert.equal(A.parseAction(record({ status: 'completed', result: { state: 'success' } })), null);
});

test('the countdown uses the server clock, not the browser clock', () => {
  // Server says 1_000_000; we received it at local 50; now local is 60_050 → one minute later on the server.
  assert.equal(A.remainingMs(record(), 1_000_000, 50, 60_050), 240_000);
  assert.equal(A.formatRemaining(240_000), '4:00');
  assert.equal(A.formatRemaining(61_500), '1:01');
  assert.equal(A.formatRemaining(-1), '0:00');
});

test('result wording never claims success from an exit code', () => {
  assert.match(A.statusText(record({ status: 'completed', result: { state: 'active', message: '' } })), /VS Code is open and in front/);
  assert.match(A.statusText(record({ status: 'completed', result: { state: 'running', message: '' } })), /VS Code is running/);
  const unverified = A.statusText(record({ status: 'unverified', result: { state: 'unverified', message: '' } }));
  assert.match(unverified, /^Outcome unverified/);
  assert.doesNotMatch(unverified, /requested|launched|opened ·/i, 'a restart may have stopped before the Mac was asked');
  assert.match(A.statusText(record({ status: 'executing' })), /Opening or bringing VS Code forward/);
  assert.match(A.statusText(record({ status: 'cancelled' })), /Cancelled · nothing ran/);
  assert.match(A.statusText(record({ status: 'expired' })), /Expired · nothing ran/);
  assert.match(A.statusText(record({ status: 'failed', result: { state: 'failed', message: 'VS Code is not installed.' } })), /VS Code is not installed/);
  assert.doesNotMatch(Object.values(A.STATUS_WORDS).join(' '), /success/i);
});

const recorder = responses => {
  const calls = [];
  const http = async (url, init = {}) => {
    calls.push({ url, method: init.method || 'GET', body: init.body });
    const next = responses.shift();
    if (next instanceof Error) throw next;
    return { ok: next.status < 400, status: next.status, json: async () => next.body };
  };
  return { calls, http };
};

test('approve sends the exact fingerprint once; a network failure reconciles with GET, never a second POST', async () => {
  const done = record({ status: 'completed', result: { state: 'running', message: '' } });
  const ok = recorder([{ status: 200, body: { serverNow: 1_000_100, action: done } }]);
  const result = await A.approveAction(record(), ok.http);
  assert.deepEqual(ok.calls, [{ url: '/api/actions/act-12345678/approve', method: 'POST', body: JSON.stringify({ fingerprint: 'fp-abcdef012345' }) }]);
  assert.equal(result.action.status, 'completed');

  const lost = recorder([new TypeError('network'), { status: 200, body: { serverNow: 1_000_200, available: true, actions: [record({ status: 'executing' })] } }]);
  const reconciled = await A.approveAction(record(), lost.http);
  assert.deepEqual(lost.calls.map(c => c.method + ' ' + c.url), ['POST /api/actions/act-12345678/approve', 'GET /api/actions']);
  assert.equal(reconciled.action.status, 'executing');
  assert.equal(reconciled.reconciled, true);

  const stale = recorder([{ status: 409, body: { message: 'This action expired.' } }]);
  await assert.rejects(A.approveAction(record(), stale.http), /This action expired\./);
  assert.equal(stale.calls.length, 1);
});

test('a response for a different action or an invalid record is rejected', async () => {
  const other = recorder([{ status: 200, body: { serverNow: 1, action: record({ id: 'act-99999999' }) } }]);
  await assert.rejects(A.approveAction(record(), other.http), /unexpected/i);
  const bad = recorder([{ status: 200, body: { serverNow: 1, action: record({ argv: ['x'] }) } }]);
  await assert.rejects(A.cancelAction(record(), bad.http), /unexpected/i);
});

test('propose names only the allowlisted action; state parsing drops unsafe records', async () => {
  const p = recorder([{ status: 200, body: { serverNow: 5, action: record() } }]);
  await A.proposeAction(p.http);
  assert.deepEqual(p.calls[0], { url: '/api/actions/propose', method: 'POST', body: JSON.stringify({ action: 'open-vscode' }) });
  const state = A.parseState({ serverNow: 9, available: true, actions: [record(), record({ id: 'act-87654321', command: 'rm' }), { nonsense: true }] });
  assert.equal(state.actions.length, 1);
  assert.equal(A.parseState({ actions: [] }), null);
});

test('Approve needs a trusted click on the visible button: no autofocus, no speech, no automatic retry', () => {
  assert.match(card, /if \(!event\.nativeEvent\.isTrusted\) return;/);
  assert.doesNotMatch(card, /autoFocus/);
  assert.match(card, /approveAction\(/);
  // Only the card approves; chat, voice and hands-free code never call it.
  for (const [name, source] of [['Chat', chat], ['HandsPanel', panel]]) assert.doesNotMatch(source, /approveAction/, name);
  assert.match(card, /disabled=\{!!busy \|\| expired\}/);
  assert.match(card, /Cancel/);
  assert.match(card, /\{record\.detail\}/, 'the exact server wording is shown');
});

test('Chat shows a proposed action from done and looks up saved actions on reopen without re-proposing', () => {
  assert.match(chat, /parseAction\(event\.actionProposal\)/);
  assert.match(chat, /<ActionCard /);
  assert.match(chat, /actionId: typeof t\.actionId === "string" \? t\.actionId : undefined/);
  assert.doesNotMatch(chat, /proposeAction/, 'chat never proposes on its own');
  assert.match(chat, /\["hands", "Hands"\]/);
  assert.match(chat, /<HandsPanel /);
});

test('state merges are monotonic: a late proposed or executing reply never overwrites a newer outcome', () => {
  const proposed = record(), executing = record({ status: 'executing' }), done = record({ status: 'completed', result: { state: 'running', message: '' } });
  assert.equal(A.mergeAction(done, executing).status, 'completed');
  assert.equal(A.mergeAction(executing, proposed).status, 'executing');
  assert.equal(A.mergeAction(proposed, executing).status, 'executing');
  assert.equal(A.mergeAction(executing, done).status, 'completed');
  assert.equal(A.mergeAction(record({ status: 'cancelled' }), done).status, 'cancelled', 'an outcome is final; the first one seen stays');
  assert.equal(A.mergeAction(undefined, proposed).status, 'proposed');
  const merged = A.mergeActions([done, record({ id: 'act-22222222', status: 'executing' })], [executing, record({ id: 'act-22222222', status: 'failed', result: { state: 'failed', message: 'x' } }), record({ id: 'act-33333333' })]);
  assert.deepEqual(merged.map(a => [a.id, a.status]), [['act-12345678', 'completed'], ['act-22222222', 'failed'], ['act-33333333', 'proposed']]);
});

test('frontend review fixes: unique card ids, generic unavailability, monotonic hook', async () => {
  const hook = await read('../components/actions/useActions.ts');
  assert.match(card, /const titleId = useId\(\);/);
  assert.match(panel, /Mac actions are unavailable right now/);
  assert.doesNotMatch(panel + chat, /VS ?Code (?:was )?not found/i);
  assert.match(hook, /mergeActions\(/);
  assert.match(hook, /mergeAction\(/);
});

test('outcome wording reports what macOS observed, never a fresh launch', () => {
  const active = record({ status: 'completed', result: { state: 'active', message: '' } });
  const running = record({ status: 'completed', result: { state: 'running', message: '' } });
  assert.equal(A.statusText(active), 'VS Code is open and in front');
  assert.equal(A.statusText(running), 'VS Code is running · it may be behind another window');
  // History is a past observation, not a live claim.
  assert.equal(A.statusText(active, { past: true }), 'Seen open and in front after approval');
  assert.equal(A.statusText(running, { past: true }), 'Seen running after approval');
  const all = [...Object.values(A.STATUS_WORDS), A.statusText(active, { past: true }), A.statusText(running, { past: true })].join(' ');
  assert.doesNotMatch(all, /\b(?:opened|launched|started)\b/i, 'VS Code may already have been open: no launch claim');
});

test('observed app state is a timed snapshot with plain wording', () => {
  assert.deepEqual(A.parseState({ serverNow: 10, available: true, actions: [], appState: 'running', observedAt: 4 }).appState, 'running');
  assert.equal(A.parseState({ serverNow: 10, available: true, actions: [], appState: 'launched', observedAt: 4 }).appState, undefined, 'unknown states are dropped');
  assert.equal(A.parseState({ serverNow: 10, available: true, actions: [], appState: 'active', observedAt: 'x' }).observedAt, undefined);
  assert.equal(A.APP_STATE_WORDS.active, 'Active · in front');
  assert.equal(A.APP_STATE_WORDS.running, 'Already running');
  assert.equal(A.APP_STATE_WORDS['not-running'], 'Not running');
  assert.equal(A.APP_STATE_WORDS.unverified, 'Could not verify');
  // Age uses the server clock: observed 12 s before the server spoke, 3 s of local time since.
  assert.equal(A.observedAgo(100_000, 112_000, 0, 3_000), 'checked 15 s ago');
  assert.equal(A.observedAgo(100_000, 100_400, 0, 0), 'checked just now');
  assert.equal(A.observedAgo(undefined, 1, 0, 0), '');
});

test('the card shows an in-flight line and blocks duplicate approve clicks before React re-renders', () => {
  assert.match(card, /Opening or bringing VS Code forward…/);
  assert.match(card, /if \(inFlight\.current\) return;\s*inFlight\.current = true;/);
  assert.match(card, /inFlight\.current = false;/);
});

test('Hands shows the observed snapshot with an explicit Refresh status', () => {
  assert.match(panel, /Refresh status/);
  assert.match(panel, /APP_STATE_WORDS\[/);
  assert.match(panel, /observedAgo\(/);
  assert.match(panel, /a snapshot, not live monitoring/);
  assert.match(panel, /statusText\(a, \{ past: true \}\)/);
});

test('an approval keeps the last observed snapshot instead of erasing it', async () => {
  const hook = await read('../components/actions/useActions.ts');
  assert.match(hook, /return \{ \.\.\.previous, serverNow, available:/);
  assert.match(panel, /comes forward if it is already running/);
});

test('direct open: preference flag, mode and the idempotent run request', async () => {
  assert.equal(A.parseState({ serverNow: 1, available: true, actions: [] }).openVSCodeWithoutApproval, false, 'default is review');
  assert.equal(A.parseState({ serverNow: 1, available: true, actions: [], openVSCodeWithoutApproval: true }).openVSCodeWithoutApproval, true);
  assert.equal(A.parseAction(record({ mode: 'direct', status: 'completed', result: { state: 'active', message: '' } })).mode, 'direct');
  assert.equal(A.parseAction(record({ mode: 'auto' })), null);
  const direct = record({ mode: 'direct', status: 'completed', result: { state: 'running', message: '' } });
  assert.equal(A.statusText(direct, { past: true }), 'Seen running after opening · no review (your setting)');
  assert.doesNotMatch(A.statusText(direct, { past: true }), /\b(?:opened|launched|started)\b/i);

  const pref = recorder([{ status: 200, body: { serverNow: 2, available: true, actions: [], openVSCodeWithoutApproval: true } }]);
  assert.equal((await A.setOpenWithoutApproval(true, pref.http)).openVSCodeWithoutApproval, true);
  assert.deepEqual(pref.calls[0], { url: '/api/actions/preferences', method: 'POST', body: JSON.stringify({ openVSCodeWithoutApproval: true }) });

  const run = recorder([new TypeError('network'), { status: 200, body: { serverNow: 3, action: direct } }]);
  const reply = await A.runOpenVSCode(run.http, () => '5f1c3e7a-0000-4000-8000-000000000002');
  assert.equal(run.calls.length, 2);
  assert.equal(run.calls[0].body, run.calls[1].body, 'a retry reuses the requestId, so it cannot open twice');
  assert.deepEqual(JSON.parse(run.calls[0].body), { action: 'open-vscode', requestId: '5f1c3e7a-0000-4000-8000-000000000002' });
  assert.equal(reply.action.mode, 'direct');
  const off = recorder([{ status: 409, body: { message: 'Turn on opening without approval first.' } }]);
  await assert.rejects(A.runOpenVSCode(off.http, () => 'r'), /Turn on opening/);
});

test('Hands frames the setting as a remembered approval for this one action', () => {
  assert.match(panel, /Remember approval for opening VS Code/);
  assert.match(panel, /Review every time/);
  assert.match(panel, /role="switch"/);
  // Trust is granted only by a genuine Approve with Remember ticked; the switch can only forget it.
  assert.match(panel, /setOpenWithoutApproval\(false\)/);
  assert.doesNotMatch(panel, /setOpenWithoutApproval\(true\)|setOpenWithoutApproval\(!direct\)/);
  assert.match(panel, /disabled=\{saving \|\| !direct\}/);
  assert.match(panel, /no files, folders or arguments/);
  assert.match(panel, /runOpenVSCode\(/);
  assert.match(panel, /if \(!event\.nativeEvent\.isTrusted\) return;/);
  assert.match(panel, /if \(running\.current\) return;/);
  assert.match(panel, /direct \? .*Open VS Code/s);
  assert.doesNotMatch(chat, /runOpenVSCode|setOpenWithoutApproval/, 'chat never opens or changes the setting itself');
});

test('the VS Code approval card offers Remember (checked by default) and sends it with the fingerprint', async () => {
  assert.match(card, /Remember this approval for opening VS Code/);
  assert.match(card, /useState\(true\)/);
  assert.match(card, /approveAction\(record, undefined, remember\)/);
  const r = recorder([{ status: 200, body: { serverNow: 1, action: record({ status: 'completed', result: { state: 'running', message: '' } }) } }]);
  await A.approveAction(record(), r.http, true);
  assert.deepEqual(JSON.parse(r.calls[0].body), { fingerprint: 'fp-abcdef012345', remember: true });
  const plain = recorder([{ status: 200, body: { serverNow: 1, action: record({ status: 'completed', result: { state: 'running', message: '' } }) } }]);
  await A.approveAction(record(), plain.http);
  assert.deepEqual(JSON.parse(plain.calls[0].body), { fingerprint: 'fp-abcdef012345' }, 'callers that do not choose send no remember key');
});

test('remembered trust appears only after the server confirms it: refresh after a successful approve, never optimistic', () => {
  const body = card.slice(card.indexOf('async function decide'), card.indexOf('finally', card.indexOf('async function decide')));
  assert.ok(body.indexOf('await (kind === "approve"') < body.indexOf('onRefresh?.()'), 'refresh only after the approve reply');
  assert.match(body, /if \(kind === "approve" && rememberable && remember\) onRefresh\?\.\(\);/);
  for (const source of [card, panel]) assert.doesNotMatch(source, /openVSCodeWithoutApproval: true/, 'the UI never sets trust locally');
});

test('the HUD Hands cluster reflects remembered approval instead of always saying approval required', () => {
  assert.match(chat, /actions\.state\.openVSCodeWithoutApproval \? "Open VS Code · approval remembered" : "Open VS Code · your approval required"/);
});
