import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const load = async path => {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  return import('data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText).toString('base64'));
};
const T = await load('../lib/timers.ts');
const read = path => readFile(new URL(path, import.meta.url), 'utf8');
const card = await read('../components/timers/TimerCard.tsx');
const panel = await read('../components/timers/TimersPanel.tsx');
const hook = await read('../components/timers/useTimers.ts');
const chat = await read('../components/Chat.tsx');
const voice = await read('../components/voice/useVoice.ts');

const timer = (extra = {}) => ({ id: 'tmr-12345678', label: 'tea', durationSeconds: 300, createdAt: 1_000_000, endsAt: 1_300_000, status: 'active', ...extra });

test('timer records are strictly validated', () => {
  assert.deepEqual(T.parseTimer(timer()), timer());
  assert.deepEqual(T.parseTimer(timer({ label: '' })).label, '');
  for (const bad of [{ status: 'running' }, { id: 'x' }, { durationSeconds: 0 }, { durationSeconds: 86401 }, { durationSeconds: 1.5 }, { label: 'x'.repeat(81) }, { endsAt: 'later' }])
    assert.equal(T.parseTimer(timer(bad)), null, JSON.stringify(bad));
  const state = T.parseTimers({ serverNow: 5, timers: [timer(), { junk: 1 }] });
  assert.equal(state.timers.length, 1);
  assert.equal(T.parseTimers({ timers: [] }), null);
});

test('countdown uses the server clock and never declares a timer done on its own', () => {
  assert.equal(T.remainingMs(timer(), 1_000_000, 50, 60_050), 240_000);
  assert.equal(T.formatClock(240_000), '4:00');
  assert.equal(T.formatClock(59_001), '1:00', 'counts up to the next whole second');
  assert.equal(T.formatClock(3_723_000), '1:02:03');
  assert.equal(T.formatClock(-5), '0:00');
  assert.equal(T.timerText(timer(), -10), 'Finishing…', 'still active on the server at 0:00');
  assert.equal(T.timerText(timer({ status: 'completed' }), -10), 'Done');
  assert.equal(T.timerText(timer({ status: 'cancelled' }), 100), 'Cancelled');
  assert.equal(T.timerText(timer(), 61_000), '1:01');
});

test('a fixed phrase names the label or the duration', () => {
  assert.equal(T.timerPhrase(timer()), 'Your tea timer is done.');
  assert.equal(T.timerPhrase(timer({ label: '' })), 'Your 5-minute timer is done.');
  assert.equal(T.timerPhrase(timer({ label: '', durationSeconds: 45 })), 'Your 45-second timer is done.');
  assert.equal(T.timerPhrase(timer({ label: '', durationSeconds: 7200 })), 'Your 2-hour timer is done.');
  assert.equal(T.timerPhrase(timer({ label: '', durationSeconds: 90 })), 'Your 1 minute 30 second timer is done.');
});

test('status merges never move backwards', () => {
  const active = timer(), done = timer({ status: 'completed' }), ack = timer({ status: 'acknowledged' }), cancelled = timer({ status: 'cancelled' });
  assert.equal(T.mergeTimer(done, active).status, 'completed');
  assert.equal(T.mergeTimer(active, done).status, 'completed');
  assert.equal(T.mergeTimer(ack, done).status, 'acknowledged');
  assert.equal(T.mergeTimer(cancelled, done).status, 'cancelled', 'the first final status stays');
  assert.deepEqual(T.mergeTimers([done], [active, timer({ id: 'tmr-22222222' })]).map(t => [t.id, t.status]), [['tmr-12345678', 'completed'], ['tmr-22222222', 'active']]);
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

test('create validates input and retries a dropped request once with the same requestId', async () => {
  await assert.rejects(T.createTimer({ durationSeconds: 0 }, recorder([]).http, () => 'r'), /1 second and 24 hours/);
  await assert.rejects(T.createTimer({ durationSeconds: 60, label: 'x'.repeat(81) }, recorder([]).http, () => 'r'), /80 characters/);
  const r = recorder([new TypeError('network'), { status: 200, body: { serverNow: 1, timer: timer() } }]);
  const reply = await T.createTimer({ durationSeconds: 300, label: ' tea ' }, r.http, () => '5f1c3e7a-0000-4000-8000-000000000001');
  assert.equal(r.calls.length, 2);
  assert.equal(r.calls[0].body, r.calls[1].body, 'same requestId on the retry');
  assert.deepEqual(JSON.parse(r.calls[0].body), { durationSeconds: 300, label: 'tea', requestId: '5f1c3e7a-0000-4000-8000-000000000001' });
  assert.equal(reply.timer.id, 'tmr-12345678');
  const twice = recorder([new TypeError('a'), new TypeError('b')]);
  await assert.rejects(T.createTimer({ durationSeconds: 60 }, twice.http, () => 'r'), /could not confirm/i);
  assert.equal(twice.calls.length, 2, 'never a third attempt');
});

test('cancel, acknowledge and claim post an empty body for that timer only', async () => {
  for (const [fn, path] of [[T.cancelTimer, 'cancel'], [T.acknowledgeTimer, 'acknowledge']]) {
    const r = recorder([{ status: 200, body: { serverNow: 2, timer: timer({ status: path === 'cancel' ? 'cancelled' : 'acknowledged' }) } }]);
    await fn(timer(), r.http);
    assert.deepEqual(r.calls[0], { url: `/api/timers/tmr-12345678/${path}`, method: 'POST', body: '{}' });
  }
  const c = recorder([{ status: 200, body: { serverNow: 3, timer: timer({ status: 'completed' }), announce: true } }]);
  assert.equal((await T.claimTimer(timer({ status: 'completed' }), c.http)).announce, true);
  const other = recorder([{ status: 200, body: { serverNow: 3, timer: timer({ id: 'tmr-99999999' }), announce: true } }]);
  await assert.rejects(T.claimTimer(timer(), other.http), /unexpected/i);
});

test('the UI never finishes a timer itself and polls only while one is active', () => {
  assert.match(hook, /timers\.some\(t => t\.status === "active"\)/);
  assert.match(hook, /setInterval\(\(\) => void refresh\(\), 1000\)/);
  assert.match(card, /timerText\(timer, /);
  assert.doesNotMatch(card + hook, /status: "completed"/, 'no client-side completion');
});

test('cards and panel offer Cancel, Hear again and Dismiss', () => {
  assert.match(card, /Cancel/);
  assert.match(card, /Hear again/);
  assert.match(card, /Dismiss/);
  assert.match(panel, /createTimer\(/);
  assert.match(panel, /<TimerCard /);
});

test('alerts are claimed at most once per tab and spoken only when June is idle, without stopping the mic', () => {
  // announce() must not take over: no manual takeover, no stopMedia, no recognition cancel.
  const announce = voice.slice(voice.indexOf('announce:'), voice.indexOf('\n', voice.indexOf('announce:')));
  assert.match(announce, /speech\.current\?\.replay\(text, getVoice\(\)\)/);
  assert.doesNotMatch(announce, /manual\.current|stopMedia|recognition\.current/);
  assert.match(chat, /claimTimer\(/);
  assert.match(chat, /claimed\.current\.has\(`timer:\$\{t\.id\}`\)/);
  assert.match(chat, /shouldAnnounce\(\{ announce: reply\.announce/);
  assert.match(chat, /const alertIdle = !busy && voice\.speech\.phase === "idle" && voice\.recognition\.phase === "idle" && \["off", "waiting"\]\.includes\(handsFree\.state\.phase\)/);
  assert.match(chat, /voice\.speakReplies/);
  assert.match(chat, /voice\.announce\(/);
});

test('chat shows a timer started from a reply and finds it again on reopen', () => {
  assert.match(chat, /parseTimer\(event\.timer\)/);
  assert.match(chat, /timerId: typeof t\.timerId === "string" \? t\.timerId : undefined/);
  assert.match(chat, /<TimerCard /);
  assert.match(chat, /\["timers", "Timers"\]/);
});

test('timer copy promises only what June does: spoken once if the page is open and voice is on, no OS notification', () => {
  assert.match(panel, /If this page is open and her voice is on, she says it once/);
  assert.match(panel, /There is no Mac notification\./);
  assert.doesNotMatch(panel, /always|notif(?:y|ies) you/i);
});

