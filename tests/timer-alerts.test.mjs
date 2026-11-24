import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const source = await readFile(new URL('../lib/timer-alerts.ts', import.meta.url), 'utf8');
const Q = await import('data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText).toString('base64'));
const chat = await readFile(new URL('../components/Chat.tsx', import.meta.url), 'utf8');
const t = (id, status) => ({ id, label: id, durationSeconds: 60, createdAt: 0, endsAt: 1, status });
const alert = id => ({ id, phrase: `Your ${id} timer is done.` });

test('only a timer that is still completed can be queued, and only once', () => {
  let q = Q.enqueueAlert([], alert('tea'), [t('tea', 'completed')]);
  assert.deepEqual(q, [alert('tea')]);
  assert.deepEqual(Q.enqueueAlert(q, alert('tea'), [t('tea', 'completed')]), q, 'no duplicate');
  assert.deepEqual(Q.enqueueAlert([], alert('tea'), [t('tea', 'acknowledged')]), [], 'a stale claim reply cannot resurrect a dismissed alert');
  assert.deepEqual(Q.enqueueAlert([], alert('tea'), []), []);
});

test('complete → queue → dismiss before June is idle: the alert is dropped, never spoken', () => {
  const queue = [alert('tea')];
  const busy = Q.takeAlert(queue, [t('tea', 'completed')], { idle: false, gate: null });
  assert.equal(busy.play, null);
  assert.deepEqual(busy.queue, queue, 'kept while June is busy');
  const dismissed = Q.takeAlert(busy.queue, [t('tea', 'acknowledged')], { idle: true, gate: null });
  assert.equal(dismissed.play, null);
  assert.deepEqual(dismissed.queue, []);
  assert.equal(Q.takeAlert([alert('tea')], [t('tea', 'cancelled')], { idle: true, gate: null }).play, null);
});

test('several completions play one at a time and never cut off the alert being spoken', () => {
  const timers = [t('tea', 'completed'), t('pasta', 'completed')];
  let queue = [alert('tea'), alert('pasta')];
  let step = Q.takeAlert(queue, timers, { idle: true, gate: null });
  assert.deepEqual(step.play, alert('tea'));
  let gate = Q.openGate(0);
  // Speech has not started yet: June still looks idle, but the gate holds the next alert.
  step = Q.takeAlert(step.queue, timers, { idle: true, gate: Q.updateGate(gate, 'idle', 100) });
  assert.equal(step.play, null);
  gate = Q.updateGate(gate, 'speaking', 200);
  assert.ok(gate && gate.heard);
  assert.equal(Q.takeAlert(step.queue, timers, { idle: false, gate }).play, null, 'never over the current alert');
  gate = Q.updateGate(gate, 'idle', 3000);
  assert.equal(gate, null, 'released once the first alert finished');
  assert.deepEqual(Q.takeAlert(step.queue, timers, { idle: true, gate }).play, alert('pasta'));
});

test('an alert that never starts speaking releases the gate after a timeout', () => {
  const gate = Q.openGate(0);
  assert.ok(Q.updateGate(gate, 'idle', Q.ALERT_START_TIMEOUT_MS - 1));
  assert.equal(Q.updateGate(gate, 'idle', Q.ALERT_START_TIMEOUT_MS), null);
});

test('Chat claims only when June can speak, checks state before queueing and playing, and stays visual when muted', () => {
  assert.match(chat, /if \(!alertsReady\) return;/, 'claim only when idle with a ready, unmuted voice');
  assert.match(chat, /enqueueAlert\(queue, \{ id: `timer:\$\{reply\.timer\.id\}`, phrase: timerPhrase\(reply\.timer\) \}, alertItemsRef\.current\)/);
  assert.match(chat, /takeAlert\(timerAlerts, alertItems, \{ idle: alertsReady, gate \}\)/);
  assert.match(chat, /alertGate\.current = openGate\(Date\.now\(\)\);/);
  assert.match(chat, /voice\.announce\(play\.phrase\)/);
});

test('a timer this page saw running announces once when June is free, even after a long reply', () => {
  const done = { ...t('tea', 'completed'), completedAt: 1_000_000 };
  // Witnessed active, finished while Qwen was busy for 150 s, claimed when idle.
  assert.equal(Q.shouldAnnounce({ announce: true, timer: done, serverNow: 1_150_000, witnessedActive: true }), true);
  // Loaded already completed long ago: stays visual.
  assert.equal(Q.shouldAnnounce({ announce: true, timer: done, serverNow: 1_150_000, witnessedActive: false }), false);
  // Loaded already completed but only just: still fresh.
  assert.equal(Q.shouldAnnounce({ announce: true, timer: done, serverNow: 1_060_000, witnessedActive: false }), true);
  // Server says another tab already announced: never.
  assert.equal(Q.shouldAnnounce({ announce: false, timer: done, serverNow: 1_000_100, witnessedActive: true }), false);
  // No completion time reported: treat as fresh.
  assert.equal(Q.shouldAnnounce({ announce: true, timer: t('tea', 'completed'), serverNow: 9e9, witnessedActive: false }), true);
});

test('Chat records timers seen running in this session and uses them for the freshness decision', () => {
  assert.match(chat, /if \(t\.status === "active"\) seenActive\.current\.add\(`timer:\$\{t\.id\}`\);/);
  assert.match(chat, /shouldAnnounce\(\{ announce: reply\.announce, timer: reply\.timer, serverNow: reply\.serverNow, witnessedActive: seenActive\.current\.has\(`timer:\$\{reply\.timer\.id\}`\) \}\)/);
});

test('no claim or alert until a voice is ready: idle alone is not enough', () => {
  assert.equal(Q.alertReady({ idle: true, speakReplies: true, voiceSelected: '' }), false, 'provider still preparing on load');
  assert.equal(Q.alertReady({ idle: true, speakReplies: false, voiceSelected: 'heart' }), false, 'muted stays visual');
  assert.equal(Q.alertReady({ idle: false, speakReplies: true, voiceSelected: 'heart' }), false);
  assert.equal(Q.alertReady({ idle: true, speakReplies: true, voiceSelected: 'heart' }), true);
});

test('a completed timer is claimed once only after the voice becomes ready', () => {
  // Simulates the claim effect: it runs on every change, but may only claim when ready.
  const claimed = new Set(); const claims = [];
  const run = ready => { if (!ready) return; for (const id of ['tea']) { if (claimed.has(id)) continue; claimed.add(id); claims.push(id); } };
  run(Q.alertReady({ idle: true, speakReplies: true, voiceSelected: '' }));
  assert.deepEqual(claims, [], 'speech idle but no voice: no claim spent');
  run(Q.alertReady({ idle: true, speakReplies: true, voiceSelected: 'heart' }));
  run(Q.alertReady({ idle: true, speakReplies: true, voiceSelected: 'heart' }));
  assert.deepEqual(claims, ['tea'], 'voice ready: exactly one claim');
  // Chat gates both claim and playback on the same readiness, and re-runs when the voice arrives.
  assert.match(chat, /const alertsReady = alertReady\(\{ idle: alertIdle, speakReplies: voice\.speakReplies, voiceSelected: voice\.alertOutputWarm \? voice\.choices\.selected : "" \}\);/);
  assert.match(chat, /if \(!alertsReady\) return;/);
  assert.match(chat, /\}, \[timers\.state, reminders\.state, alertsReady\]\);/);
  assert.match(chat, /\{ idle: alertsReady, gate \}/);
});
