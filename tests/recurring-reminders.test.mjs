import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const load = async path => {
  const source = await readFile(new URL(path, import.meta.url), 'utf8');
  return import('data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText).toString('base64'));
};
const R = await load('../lib/reminders.ts');
const read = path => readFile(new URL(path, import.meta.url), 'utf8');
const chat = await read('../components/Chat.tsx');
const card = await read('../components/reminders/ReminderCard.tsx');
const seriesCard = await read('../components/reminders/SeriesCard.tsx');
const panel = await read('../components/reminders/RemindersPanel.tsx');
const hook = await read('../components/reminders/useReminders.ts');

const NOON_IST = Date.UTC(2026, 10, 14, 6, 30);
const series = (extra = {}) => ({ id: 'ser-12345678', text: 'Drink water', rule: 'daily', weekdays: [1, 2, 3, 4, 5, 6, 7], localTime: '23:00', timeZone: 'Asia/Kolkata', startDate: '2026-11-14',
  status: 'active', revision: 1, createdAt: NOON_IST - 60_000, nextScheduledAt: NOON_IST + 11 * 3600_000, nextOccurrenceDate: '2026-11-14', lastMissed: null, ...extra });
const occurrence = (extra = {}) => ({ id: 'rem-87654321', text: 'Drink water', dueAt: NOON_IST, timeZone: 'Asia/Kolkata', createdAt: NOON_IST, status: 'completed', revision: 1,
  seriesId: 'ser-12345678', occurrenceDate: '2026-11-13', ...extra });

test('series records are strictly validated', () => {
  assert.deepEqual(R.parseSeries(series()), series());
  assert.deepEqual(R.parseSeries(series({ rule: 'weekly', weekdays: [4, 1] })).weekdays, [1, 4], 'weekdays sorted');
  for (const bad of [{ rule: 'monthly' }, { rule: 'weekly', weekdays: [] }, { weekdays: [0] }, { weekdays: [8] }, { weekdays: [1, 1] }, { weekdays: [1.5] },
    { localTime: '24:00' }, { startDate: '14/11/2026' }, { status: 'done' }, { revision: 0 }, { text: '' }, { text: '😀'.repeat(201) }, { timeZone: 'Not/AZone' },
    { nextScheduledAt: 'soon' }, { nextOccurrenceDate: '2026-1-1' }, { lastMissed: { count: 0, occurrenceDate: '2026-11-13', at: 1 } }])
    assert.equal(R.parseSeries(series(bad)), null, JSON.stringify(bad));
  assert.equal(R.parseSeries(series({ status: 'paused', nextScheduledAt: null, nextOccurrenceDate: null })).nextScheduledAt, null);
  assert.deepEqual(R.parseSeries(series({ lastMissed: { occurrenceDate: '2026-11-13', count: 2, at: NOON_IST } })).lastMissed, { occurrenceDate: '2026-11-13', count: 2, at: NOON_IST });
  const state = R.parseReminders({ serverNow: NOON_IST, timeZone: 'Asia/Kolkata', reminders: [], series: [series(), { junk: 1 }] });
  assert.equal(state.series.length, 1);
  assert.deepEqual(R.parseReminders({ serverNow: NOON_IST, reminders: [] }).series, [], 'older servers: no series');
});

test('occurrences carry optional series fields, strictly typed', () => {
  const parsed = R.parseReminder(occurrence({ outcome: 'missed', dstAdjusted: true, status: 'acknowledged' }));
  assert.equal(parsed.seriesId, 'ser-12345678'); assert.equal(parsed.occurrenceDate, '2026-11-13');
  assert.equal(parsed.outcome, 'missed'); assert.equal(parsed.dstAdjusted, true);
  for (const outcome of ['skipped', 'paused']) assert.equal(R.parseReminder(occurrence({ outcome })).outcome, outcome);
  for (const bad of [{ outcome: 'superseded' }, { seriesId: 'x' }, { occurrenceDate: 'today' }, { dstAdjusted: 'yes' }]) assert.equal(R.parseReminder(occurrence(bad)), null, JSON.stringify(bad));
  const oneShot = R.parseReminder({ ...occurrence(), seriesId: undefined, occurrenceDate: undefined });
  assert.ok(!('seriesId' in oneShot), 'one-shot reminders are unchanged');
});

test('series merges: higher revision wins; at equal revision the schedule only moves forward', () => {
  assert.equal(R.mergeSeries(series({ revision: 2, status: 'paused' }), series({ revision: 1 })).status, 'paused');
  assert.equal(R.mergeSeries(series({ revision: 1 }), series({ revision: 2, status: 'paused' })).status, 'paused');
  const advanced = series({ nextScheduledAt: NOON_IST + 35 * 3600_000, nextOccurrenceDate: '2026-11-15' });
  assert.equal(R.mergeSeries(series(), advanced).nextOccurrenceDate, '2026-11-15', 'the scheduler advanced without a revision bump');
  assert.equal(R.mergeSeries(advanced, series()).nextOccurrenceDate, '2026-11-15', 'a slow older snapshot never moves it back');
});

test('rules read naturally', () => {
  assert.equal(R.describeRule(series()), 'Daily · 11:00 pm');
  assert.equal(R.describeRule(series({ rule: 'weekly', weekdays: [1, 4], localTime: '09:00' })), 'Mon, Thu · 9:00 am');
  assert.equal(R.describeRule(series({ rule: 'weekly', weekdays: [1, 2, 3, 4, 5], localTime: '07:30' })), 'Weekdays · 7:30 am');
  assert.equal(R.describeRule(series({ rule: 'weekly', weekdays: [6, 7] })), 'Sat, Sun · 11:00 pm');
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

test('creating a series sends the exact contract, validates it, and retries once with the same requestId', async () => {
  const r = recorder([new TypeError('net'), { status: 200, body: { serverNow: NOON_IST, series: series() } }]);
  const reply = await R.createSeries({ text: ' Drink water ', rule: 'weekly', weekdays: [4, 1], localTime: '09:00', startDate: '2026-11-14', timeZone: 'Asia/Kolkata' }, r.http, () => 'req-11111111');
  assert.equal(r.calls.length, 2); assert.equal(r.calls[0].body, r.calls[1].body);
  assert.equal(r.calls[0].url, '/api/reminders/series');
  assert.deepEqual(JSON.parse(r.calls[0].body), { text: 'Drink water', rule: 'weekly', weekdays: [1, 4], localTime: '09:00', startDate: '2026-11-14', timeZone: 'Asia/Kolkata', requestId: 'req-11111111' });
  assert.equal(reply.series.id, 'ser-12345678');
  const daily = recorder([{ status: 200, body: { serverNow: 1, series: series() } }]);
  await R.createSeries({ text: 'x', rule: 'daily', localTime: '23:00', startDate: '2026-11-14' }, daily.http, () => 'r');
  assert.ok(!('weekdays' in JSON.parse(daily.calls[0].body)), 'daily sends no weekdays');
  await assert.rejects(R.createSeries({ text: 'x', rule: 'weekly', weekdays: [], localTime: '09:00', startDate: '2026-11-14' }, recorder([]).http, () => 'r'), /at least one day/i);
  await assert.rejects(R.createSeries({ text: '', rule: 'daily', localTime: '09:00', startDate: '2026-11-14' }, recorder([]).http, () => 'r'), /what to remind/i);
  await assert.rejects(R.createSeries({ text: 'x', rule: 'daily', localTime: '9am', startDate: '2026-11-14' }, recorder([]).http, () => 'r'), /time/i);
});

test('series mutations bind the revision; skip-next also binds the displayed occurrenceDate', async () => {
  const reply = { status: 200, body: { serverNow: 1, series: series({ revision: 2 }) } };
  const u = recorder([reply]);
  await R.updateSeries(series(), { localTime: '22:30', text: 'Water' }, u.http, () => 'req-1');
  assert.equal(u.calls[0].url, '/api/reminders/series/ser-12345678/update');
  assert.deepEqual(JSON.parse(u.calls[0].body), { revision: 1, requestId: 'req-1', localTime: '22:30', text: 'Water' });
  for (const [fn, path] of [[R.pauseSeries, 'pause'], [R.resumeSeries, 'resume'], [R.cancelSeries, 'cancel']]) {
    const c = recorder([{ ...reply }]);
    await fn(series(), c.http, () => 'req-2');
    assert.deepEqual([c.calls[0].url, JSON.parse(c.calls[0].body)], [`/api/reminders/series/ser-12345678/${path}`, { revision: 1, requestId: 'req-2' }]);
  }
  const s = recorder([{ ...reply }]);
  await R.skipNextSeries(series(), s.http, () => 'req-3');
  assert.deepEqual(JSON.parse(s.calls[0].body), { revision: 1, requestId: 'req-3', occurrenceDate: '2026-11-14' });
  await assert.rejects(R.skipNextSeries(series({ nextOccurrenceDate: null, nextScheduledAt: null }), recorder([]).http, () => 'r'), /nothing scheduled/i);
  const stale = recorder([{ status: 409, body: { message: 'Changed.' } }]);
  const error = await R.skipNextSeries(series(), stale.http, () => 'r').catch(e => e);
  assert.equal(R.isConflict(error), true, 'a scheduler-advanced date is a conflict, never retried');
  const other = recorder([{ status: 200, body: { serverNow: 1, series: series({ id: 'ser-99999999' }) } }]);
  await assert.rejects(R.pauseSeries(series(), other.http, () => 'r'), /unexpected/i);
});

test('skipping one occurrence binds its revision', async () => {
  const r = recorder([{ status: 200, body: { serverNow: 1, reminder: occurrence({ status: 'acknowledged', outcome: 'skipped', revision: 2 }) } }]);
  await R.skipReminder(occurrence(), r.http, () => 'req-4');
  assert.deepEqual([r.calls[0].url, JSON.parse(r.calls[0].body)], ['/api/reminders/rem-87654321/skip', { revision: 1, requestId: 'req-4' }]);
});

test('snooze options never reach the next regular deadline', () => {
  assert.deepEqual(R.snoozeOptionsBefore([5, 10, 30], NOON_IST, NOON_IST + 20 * 60_000), [5, 10]);
  assert.deepEqual(R.snoozeOptionsBefore([5, 10, 30], NOON_IST, NOON_IST + 10 * 60_000), [5], 'exactly at the deadline is not allowed');
  assert.deepEqual(R.snoozeOptionsBefore([5, 10, 30], NOON_IST, null), [5, 10, 30], 'one-shot reminders: no bound');
});

test('only reminders that may speak are alertable: one-shots and occurrences of an active series', () => {
  const list = [
    { ...occurrence(), id: 'rem-aaaaaaa1', seriesId: undefined },
    occurrence({ id: 'rem-aaaaaaa2' }),
    occurrence({ id: 'rem-aaaaaaa3', seriesId: 'ser-paused01' }),
    occurrence({ id: 'rem-aaaaaaa4', seriesId: 'ser-unknown1' }),
  ];
  const all = [series(), series({ id: 'ser-paused01', status: 'paused' })];
  assert.deepEqual(R.alertableReminders(list, all).map(r => r.id), ['rem-aaaaaaa1', 'rem-aaaaaaa2'], 'paused and unknown series never speak');
  assert.deepEqual(R.alertableReminders(list, [series({ status: 'cancelled' })]).map(r => r.id), ['rem-aaaaaaa1']);
});

test('Chat gates the shared queue and claims through alertableReminders, and shows series from chat', () => {
  assert.match(chat, /const speakable = alertableReminders\(reminders\.state\?\.reminders \?\? \[\], reminders\.state\?\.series \?\? \[\]\);/);
  assert.match(chat, /\.\.\.speakable\.map\(r => \(\{ id: reminderKey\(r\), status: r\.status \}\)\)/);
  assert.match(chat, /for \(const r of speakable\) \{/);
  assert.match(chat, /parseSeries\(event\.series\)/);
  assert.match(chat, /reminderSeriesId: typeof t\.reminderSeriesId === "string" \? t\.reminderSeriesId : undefined/);
  assert.match(chat, /<SeriesCard /);
});

test('occurrence cards: Snooze, Skip and Dismiss only; nothing but Dismiss while the series is not active', () => {
  assert.match(card, /const occurrence = !!reminder\.seriesId;/);
  assert.match(card, /editable = !occurrence && /, 'no Edit for occurrences');
  assert.match(card, /reminder\.status === "active" && !occurrence/, 'no Cancel for occurrences');
  assert.match(card, /seriesActive && .*skipReminder\(reminder\)/s);
  assert.match(card, /snoozeOptionsBefore\(\[5, 10, 30\], serverNow, occurrence \? series\?\.nextScheduledAt \?\? null : null\)/);
  assert.match(card, /Moved for daylight saving/);
  assert.match(card, /Dismiss/);
});

test('series card: immutable edit base, guarded actions, Skip next sends the displayed date, conflicts refresh', () => {
  assert.match(seriesCard, /const \[base, setBase\] = useState<Series \| null>\(null\);/);
  assert.match(seriesCard, /updateSeries\(base, /);
  assert.match(seriesCard, /if \(inFlight\.current\) return;\s*inFlight\.current = true;/);
  assert.match(seriesCard, /skipNextSeries\(series\)/);
  assert.match(seriesCard, /isConflict\(failure\)/);
  for (const label of ['Pause', 'Resume', 'Skip next', 'Edit', 'Stop repeating']) assert.match(seriesCard, new RegExp(`>${label}<`));
  assert.match(seriesCard, /describeRule\(/);
  assert.match(seriesCard, /lastMissed/);
});

test('the form offers Once / Daily / Weekly with weekday chips and creates a series for repeats', () => {
  assert.match(panel, /\["once", "Once"\], \["daily", "Daily"\], \["weekly", "Weekly"\]/);
  assert.match(panel, /aria-pressed=\{days\.includes\(day\)\}/);
  assert.match(panel, /createSeries\(\{/);
  assert.match(panel, /repeat === "once" \? "Date" : "Starts"/);
  assert.match(hook, /upsertSeries/);
  assert.match(hook, /mergeSeries\(/);
});
