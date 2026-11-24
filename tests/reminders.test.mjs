import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const load = async path => {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  return import('data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText).toString('base64'));
};
const R = await load('../lib/reminders.ts');
const Q = await load('../lib/timer-alerts.ts');
const read = path => readFile(new URL(path, import.meta.url), 'utf8');
const chat = await read('../components/Chat.tsx');
const card = await read('../components/reminders/ReminderCard.tsx');
const panel = await read('../components/reminders/RemindersPanel.tsx');
const hook = await read('../components/reminders/useReminders.ts');

// 2026-11-14 12:00:00 in Asia/Kolkata (UTC+5:30) = 06:30 UTC.
const NOON_IST = Date.UTC(2026, 10, 14, 6, 30);
const reminder = (extra = {}) => ({ id: 'rem-12345678', text: 'Call Mom', dueAt: NOON_IST + 6 * 3600_000, timeZone: 'Asia/Kolkata', createdAt: NOON_IST - 60_000, status: 'active', revision: 1, ...extra });

test('reminder records are strictly validated', () => {
  assert.deepEqual(R.parseReminder(reminder()), reminder());
  for (const bad of [{ text: '' }, { text: 'x'.repeat(201) }, { status: 'due' }, { id: 'x' }, { dueAt: 'soon' }, { timeZone: '' }, { timeZone: 5 }])
    assert.equal(R.parseReminder(reminder(bad)), null, JSON.stringify(bad));
  assert.equal(R.parseReminder(reminder({ completedAt: NOON_IST, announcedAt: NOON_IST })).completedAt, NOON_IST);
  const state = R.parseReminders({ serverNow: NOON_IST, timeZone: 'Asia/Kolkata', reminders: [reminder(), { junk: 1 }] });
  assert.equal(state.reminders.length, 1);
  assert.equal(state.timeZone, 'Asia/Kolkata');
  assert.equal(R.parseReminders({ serverNow: 1, reminders: [] }).timeZone, 'Asia/Kolkata', 'documented default zone');
  assert.equal(R.parseReminders({ reminders: [] }), null);
});

test('due times are shown in the reminder’s own zone, relative to the server’s today', () => {
  assert.equal(R.formatDue(NOON_IST + 6 * 3600_000, 'Asia/Kolkata', NOON_IST), 'Today, 6:00 pm');
  assert.equal(R.formatDue(NOON_IST + 21 * 3600_000 + 30 * 60_000, 'Asia/Kolkata', NOON_IST), 'Tomorrow, 9:30 am');
  assert.match(R.formatDue(NOON_IST + 2 * 86400_000, 'Asia/Kolkata', NOON_IST), /^Mon 16 Nov, 12:00 pm$/);
  assert.match(R.formatDue(NOON_IST - 3600_000, 'Asia/Kolkata', NOON_IST), /^Today, 11:00 am$/);
});

test('local date and time defaults come from the server zone, not the browser', () => {
  assert.equal(R.localDate(NOON_IST, 'Asia/Kolkata'), '2026-11-14');
  assert.equal(R.localDate(NOON_IST, 'America/New_York'), '2026-11-14');
  assert.equal(R.localDate(Date.UTC(2026, 10, 14, 20, 0), 'Asia/Kolkata'), '2026-11-15', 'after 18:30 UTC it is already tomorrow in India');
  assert.deepEqual(R.nextHourDefault(NOON_IST, 'Asia/Kolkata'), { date: '2026-11-14', time: '13:00' });
  assert.deepEqual(R.nextHourDefault(Date.UTC(2026, 10, 14, 18, 15), 'Asia/Kolkata'), { date: '2026-11-15', time: '00:00' }, '23:45 local → tomorrow at midnight, never a past "today 00:00"');
  assert.deepEqual(R.nextHourDefault(Date.UTC(2026, 10, 14, 18, 29, 59), 'Asia/Kolkata'), { date: '2026-11-15', time: '00:00' }, 'the :30 offset is handled');
  assert.deepEqual(R.nextHourDefault(Date.UTC(2026, 11, 31, 18, 40), 'Asia/Kolkata'), { date: '2027-01-01', time: '01:00' }, 'year rollover');
  assert.deepEqual(R.nextHourDefault(Date.UTC(2026, 10, 14, 23, 50), 'America/New_York'), { date: '2026-11-14', time: '19:00' });
});

test('status merges never move backwards; the phrase is fixed', () => {
  assert.equal(R.mergeReminder(reminder({ status: 'completed' }), reminder()).status, 'completed');
  assert.equal(R.mergeReminder(reminder({ status: 'acknowledged' }), reminder({ status: 'completed' })).status, 'acknowledged');
  assert.equal(R.mergeReminder(reminder({ status: 'cancelled' }), reminder({ status: 'completed' })).status, 'cancelled');
  assert.equal(R.reminderPhrase(reminder()), 'Reminder: Call Mom.');
  assert.equal(R.reminderPhrase(reminder({ text: 'Take the pasta off.' })), 'Reminder: Take the pasta off.');
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

test('create sends the exact contract, validates its shape, and retries a dropped request once with the same requestId', async () => {
  await assert.rejects(R.createReminder({ text: '  ', localDate: '2026-11-14', localTime: '18:00' }, recorder([]).http, () => 'r'), /what to remind/i);
  await assert.rejects(R.createReminder({ text: 'x', localDate: '14/11/2026', localTime: '18:00' }, recorder([]).http, () => 'r'), /date/i);
  await assert.rejects(R.createReminder({ text: 'x', localDate: '2026-11-14', localTime: '6pm' }, recorder([]).http, () => 'r'), /time/i);
  const r = recorder([new TypeError('network'), { status: 200, body: { serverNow: NOON_IST, reminder: reminder() } }]);
  const reply = await R.createReminder({ text: ' Call Mom ', localDate: '2026-11-14', localTime: '18:00', timeZone: 'Asia/Kolkata' }, r.http, () => '5f1c3e7a-0000-4000-8000-000000000003');
  assert.equal(r.calls.length, 2);
  assert.equal(r.calls[0].body, r.calls[1].body);
  assert.deepEqual(JSON.parse(r.calls[0].body), { text: 'Call Mom', localDate: '2026-11-14', localTime: '18:00', timeZone: 'Asia/Kolkata', requestId: '5f1c3e7a-0000-4000-8000-000000000003' });
  assert.equal(reply.reminder.id, 'rem-12345678');
  const past = recorder([{ status: 400, body: { message: 'That time has already passed.' } }]);
  await assert.rejects(R.createReminder({ text: 'x', localDate: '2026-11-14', localTime: '09:00' }, past.http, () => 'r'), /already passed/, 'the server owns past/zone validation');
  assert.ok(!('timeZone' in JSON.parse(past.calls[0].body)), 'zone is optional; the server default applies');
});

test('cancel, acknowledge and claim post the reminder revision for that reminder only', async () => {
  for (const [fn, path] of [[R.cancelReminder, 'cancel'], [R.acknowledgeReminder, 'acknowledge']]) {
    const r = recorder([{ status: 200, body: { serverNow: 1, reminder: reminder({ status: path === 'cancel' ? 'cancelled' : 'acknowledged' }) } }]);
    await fn(reminder(), r.http);
    assert.deepEqual(r.calls[0], { url: `/api/reminders/rem-12345678/${path}`, method: 'POST', body: '{"revision":1}' });
  }
  const c = recorder([{ status: 200, body: { serverNow: 2, reminder: reminder({ status: 'completed' }), announce: true } }]);
  assert.equal((await R.claimReminder(reminder({ status: 'completed' }), c.http)).announce, true);
  const other = recorder([{ status: 200, body: { serverNow: 2, reminder: reminder({ id: 'rem-99999999' }) } }]);
  await assert.rejects(R.claimReminder(reminder(), other.http), /unexpected/i);
});

test('polling waits for the nearest due time instead of ticking for days', () => {
  assert.equal(R.nextReminderCheck([], NOON_IST, 0, 0), null);
  assert.equal(R.nextReminderCheck([reminder({ status: 'completed' })], NOON_IST, 0, 0), null);
  assert.equal(R.nextReminderCheck([reminder()], NOON_IST, 0, 0), 60_000, 'six hours away: capped at a minute');
  assert.equal(R.nextReminderCheck([reminder({ dueAt: NOON_IST + 10_000 })], NOON_IST, 0, 0), 10_750, 'just after it is due');
  assert.equal(R.nextReminderCheck([reminder({ dueAt: NOON_IST - 5000 })], NOON_IST, 0, 0), 1000, 'overdue but still active: check every second until the server completes it');
});

test('timers and reminders share one alert queue with namespaced keys', () => {
  const live = [{ id: 'timer:tea', status: 'completed' }, { id: 'reminder:rem-12345678', status: 'completed' }];
  let q = Q.enqueueAlert([], { id: 'timer:tea', phrase: 'Your tea timer is done.' }, live);
  q = Q.enqueueAlert(q, { id: 'reminder:rem-12345678', phrase: 'Reminder: Call Mom.' }, live);
  assert.equal(q.length, 2);
  let step = Q.takeAlert(q, live, { idle: true, gate: null });
  assert.equal(step.play.id, 'timer:tea');
  assert.equal(Q.takeAlert(step.queue, live, { idle: true, gate: Q.openGate(0) }).play, null, 'serial: the reminder waits for the timer alert');
  const dismissed = [{ id: 'timer:tea', status: 'completed' }, { id: 'reminder:rem-12345678', status: 'acknowledged' }];
  assert.equal(Q.takeAlert(step.queue, dismissed, { idle: true, gate: null }).play, null, 'a dismissed reminder is dropped');
});

test('Chat claims reminders with the same gates as timers and shows reminder cards', () => {
  assert.match(chat, /claimReminder\(/);
  assert.match(chat, /claimed\.current\.has\(reminderKey\(r\)\)/);
  assert.match(chat, /witnessedActive: seenActive\.current\.has\(reminderKey\(reply\.reminder\)\)/);
  assert.match(chat, /enqueueAlert\(queue, \{ id: reminderKey\(reply\.reminder\), phrase: reminderPhrase\(reply\.reminder\) \}, alertItemsRef\.current\)/);
  assert.match(chat, /takeAlert\(timerAlerts, alertItems, \{ idle: alertsReady, gate \}\)/);
  assert.match(chat, /parseReminder\(event\.reminder\)/);
  assert.match(chat, /reminderId: typeof t\.reminderId === "string" \? t\.reminderId : undefined/);
  assert.match(chat, /<ReminderCard /);
  assert.match(chat, /\["reminders", "Reminders"\]/);
});

test('reminder UI: Cancel, Hear again, Dismiss; the zone is shown; polling follows nextReminderCheck', () => {
  assert.match(card, /Cancel/);
  assert.match(card, /Hear again/);
  assert.match(card, /Dismiss/);
  assert.match(card, /formatDue\(/);
  assert.match(panel, /createReminder\(/);
  assert.match(panel, /Times are in \{zone\}/);
  assert.match(hook, /nextReminderCheck\(/);
  assert.doesNotMatch(card + hook, /status: "completed"/, 'only the server completes a reminder');
});

test('timer + reminder finishing together: voice unready → nothing claimed; ready → both claimed, spoken one at a time; dismissing the queued one drops it', () => {
  // Simulates Chat's single claim effect and single drain over the shared queue.
  let items = [{ id: 'timer:tea', status: 'completed' }, { id: 'reminder:rem-12345678', status: 'completed' }];
  const claimed = new Set(), claims = [];
  let queue = [];
  const claimPass = ready => {
    if (!ready) return;
    for (const item of items) {
      if (item.status !== 'completed' || claimed.has(item.id)) continue;
      claimed.add(item.id); claims.push(item.id);
      queue = Q.enqueueAlert(queue, { id: item.id, phrase: item.id }, items);
    }
  };
  claimPass(Q.alertReady({ idle: true, speakReplies: true, voiceSelected: '' }));
  assert.deepEqual(claims, [], 'voice not ready: no claim spent on either');
  claimPass(Q.alertReady({ idle: true, speakReplies: true, voiceSelected: 'heart' }));
  claimPass(Q.alertReady({ idle: true, speakReplies: true, voiceSelected: 'heart' }));
  assert.deepEqual(claims, ['timer:tea', 'reminder:rem-12345678'], 'each claimed exactly once');
  let step = Q.takeAlert(queue, items, { idle: true, gate: null });
  assert.equal(step.play.id, 'timer:tea');
  let gate = Q.openGate(0);
  gate = Q.updateGate(gate, 'speaking', 100);
  assert.equal(Q.takeAlert(step.queue, items, { idle: false, gate }).play, null, 'the reminder never interrupts the timer alert');
  items = [items[0], { id: 'reminder:rem-12345678', status: 'acknowledged' }];   // dismissed while queued
  gate = Q.updateGate(gate, 'idle', 2000);
  step = Q.takeAlert(step.queue, items, { idle: true, gate });
  assert.equal(step.play, null);
  assert.deepEqual(step.queue, [], 'dismissed reminder is dropped, never spoken');
});

test('Chat has exactly one alert drain and one place that speaks alerts', () => {
  assert.equal(chat.match(/voice\.announce\(/g).length, 1);
  assert.equal(chat.match(/takeAlert\(/g).length, 1);
  assert.equal(chat.match(/updateGate\(/g).length, 1);
});

test('reminder text length counts characters, not UTF-16 units; zones are validated by Intl', () => {
  const emoji = n => '😀'.repeat(n);
  assert.ok(R.parseReminder(reminder({ text: emoji(200) })), '200 emoji are 200 characters');
  assert.equal(R.parseReminder(reminder({ text: emoji(201) })), null);
  assert.equal(R.parseReminder(reminder({ timeZone: 'Not/AZone' })), null, 'shaped like a zone but not a real one');
  for (const zone of ['Asia/Kolkata', 'UTC', 'America/Argentina/Buenos_Aires', 'Etc/GMT+5']) assert.ok(R.parseReminder(reminder({ timeZone: zone })), zone);
});

test('create counts characters the same way; the panel keeps a user-chosen date', async () => {
  const ok = recorder([{ status: 200, body: { serverNow: 1, reminder: reminder() } }]);
  await R.createReminder({ text: '😀'.repeat(200), localDate: '2026-11-14', localTime: '18:00' }, ok.http, () => 'r');
  assert.equal(ok.calls.length, 1);
  await assert.rejects(R.createReminder({ text: '😀'.repeat(201), localDate: '2026-11-14', localTime: '18:00' }, recorder([]).http, () => 'r'), /200 characters/);
  assert.match(panel, /const next = nextHourDefault\(state\.serverNow, zone\); setDate\(next\.date\); setClock\(next\.time\);/);
  assert.match(panel, /if \(state && !date\)/, 'defaults apply once; a chosen date is never overwritten');
});

// ---- Edit and snooze (revisioned reminders) ----
const rev = (n, extra = {}) => reminder({ revision: n, ...extra });

test('revision is an integer ≥ 1, defaulting to 1 for legacy records', () => {
  assert.equal(R.parseReminder({ ...reminder(), revision: undefined }).revision, 1, 'legacy default');
  assert.equal(R.parseReminder(rev(3)).revision, 3);
  for (const bad of [0, -1, 1.5, '2', null]) assert.equal(R.parseReminder(rev(bad)), null, String(bad));
  assert.equal(R.reminderKey(rev(4)), 'reminder:rem-12345678:4');
});

test('a higher revision wins even completed → active; equal revisions keep the forward-only rule; lower never wins', () => {
  assert.equal(R.mergeReminder(rev(1, { status: 'completed' }), rev(2, { status: 'active' })).revision, 2, 'snoozed: due becomes scheduled again');
  assert.equal(R.mergeReminder(rev(2, { status: 'active' }), rev(1, { status: 'completed' })).revision, 2, 'a late old reply never overrides');
  assert.equal(R.mergeReminder(rev(2, { status: 'completed' }), rev(2, { status: 'active' })).status, 'completed');
  assert.equal(R.mergeReminder(rev(2, { status: 'acknowledged' }), rev(2, { status: 'completed' })).status, 'acknowledged');
});

test('reschedule and snooze send the exact contract with the current revision, retrying a dropped request once with the same requestId', async () => {
  const r = recorder([new TypeError('net'), { status: 200, body: { serverNow: 1, reminder: rev(3, { status: 'active' }) } }]);
  const reply = await R.rescheduleReminder(rev(2, { status: 'completed' }), { localDate: '2026-11-15', localTime: '19:00', timeZone: 'Asia/Kolkata', text: ' Stretch ' }, r.http, () => 'req-11111111');
  assert.equal(r.calls.length, 2); assert.equal(r.calls[0].body, r.calls[1].body);
  assert.equal(r.calls[0].url, '/api/reminders/rem-12345678/reschedule');
  assert.deepEqual(JSON.parse(r.calls[0].body), { revision: 2, requestId: 'req-11111111', localDate: '2026-11-15', localTime: '19:00', timeZone: 'Asia/Kolkata', text: 'Stretch' });
  assert.equal(reply.reminder.revision, 3);
  const s = recorder([{ status: 200, body: { serverNow: 1, reminder: rev(3) } }]);
  await R.snoozeReminder(rev(2, { status: 'completed' }), 600, s.http, () => 'req-22222222');
  assert.deepEqual(JSON.parse(s.calls[0].body), { revision: 2, requestId: 'req-22222222', seconds: 600 });
  assert.equal(s.calls[0].url, '/api/reminders/rem-12345678/snooze');
  for (const bad of [0, 86401, 1.5]) await assert.rejects(R.snoozeReminder(rev(1), bad, recorder([]).http, () => 'r'), /1 second and 24 hours/);
  await assert.rejects(R.rescheduleReminder(rev(1), { localDate: 'x', localTime: '19:00' }, recorder([]).http, () => 'r'), /date/i);
  await assert.rejects(R.rescheduleReminder(rev(1), { localDate: '2026-11-15', localTime: '19:00', text: '😀'.repeat(201) }, recorder([]).http, () => 'r'), /200 characters/);
  const noText = recorder([{ status: 200, body: { serverNow: 1, reminder: rev(2) } }]);
  await R.rescheduleReminder(rev(1), { localDate: '2026-11-15', localTime: '19:00' }, noText.http, () => 'r');
  assert.ok(!('text' in JSON.parse(noText.calls[0].body)), 'text is optional');
});

test('a 409 is a conflict carrying its status, never retried; replies for another reminder are rejected', async () => {
  const c = recorder([{ status: 409, body: { message: 'This reminder changed.' } }]);
  const error = await R.snoozeReminder(rev(2), 300, c.http, () => 'r').catch(e => e);
  assert.equal(error.status, 409);
  assert.equal(R.isConflict(error), true);
  assert.equal(c.calls.length, 1);
  const other = recorder([{ status: 200, body: { serverNow: 1, reminder: rev(3, { id: 'rem-99999999' }) } }]);
  await assert.rejects(R.snoozeReminder(rev(2), 300, other.http, () => 'r'), /unexpected/i);
});

test('the queue is versioned: an alert for an old revision drops when a newer one appears; each occurrence is claimed once', () => {
  const v1 = 'reminder:rem-12345678:1', v2 = 'reminder:rem-12345678:2';
  let queue = Q.enqueueAlert([], { id: v1, phrase: 'Reminder: stretch.' }, [{ id: v1, status: 'completed' }]);
  // Snoozed before June was free: the item list now carries revision 2 (active).
  const after = Q.takeAlert(queue, [{ id: v2, status: 'active' }], { idle: true, gate: null });
  assert.equal(after.play, null); assert.deepEqual(after.queue, []);
  // Revision 2 comes due: a new key, so it is claimed and queued on its own.
  const claimed = new Set([v1]);
  assert.equal(claimed.has(v2), false);
  queue = Q.enqueueAlert([], { id: v2, phrase: 'Reminder: stretch.' }, [{ id: v2, status: 'completed' }]);
  assert.equal(Q.takeAlert(queue, [{ id: v2, status: 'completed' }], { idle: true, gate: null }).play.id, v2);
  assert.match(chat, /\.\.\.speakable\.map\(r => \(\{ id: reminderKey\(r\), status: r\.status \}\)\)/);
  assert.match(chat, /if \(r\.status === "active"\) seenActive\.current\.add\(reminderKey\(r\)\);/);
});

test('the card offers Edit (active or due) and Snooze 5/10/30 min (due), blocks double clicks, and explains conflicts', () => {
  assert.match(card, />Edit</);
  assert.match(card, /snoozeOptionsBefore\(\[5, 10, 30\]/);
  assert.match(card, /snoozeReminder\(reminder, minutes \* 60\)/);
  assert.match(card, /rescheduleReminder\(base, \{/);
  assert.match(card, /if \(inFlight\.current\) return;\s*inFlight\.current = true;/);
  assert.match(card, /isConflict\(failure\)/);
  assert.match(card, /changed somewhere else/);
  assert.match(card, /onRefresh\?\.\(\)/);
});

test('a stale reminder claim (409) refreshes instead of retrying the old revision', () => {
  const block = chat.slice(chat.indexOf('void claimReminder(r)'), chat.indexOf('}, [timers.state, reminders.state, alertsReady]);'));
  assert.match(block, /\.catch\(failure => \{ if \(isConflict\(failure\)\) void reminders\.refresh\(\); else claimed\.current\.delete\(key\); \}\)/);
});

test('an open edit is bound to the revision it started from: a newer prop never rebinds the draft', () => {
  assert.match(card, /const \[base, setBase\] = useState<Reminder \| null>\(null\);/);
  assert.match(card, /setBase\(reminder\);/, 'startEdit captures an immutable base');
  assert.match(card, /rescheduleReminder\(base, \{/, 'submit uses the base, not the live prop');
  assert.doesNotMatch(card, /rescheduleReminder\(reminder,/);
  assert.match(card, /text\.trim\(\) !== base\.text/, 'text compared with the base');
  assert.match(card, /base && reminder\.revision !== base\.revision/, 'a newer revision is warned about');
  assert.match(card, /changed since you started editing/);
});
