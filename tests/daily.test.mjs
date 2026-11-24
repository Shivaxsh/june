import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const dataUrl = source => 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
const read = path => readFile(new URL(path, import.meta.url), 'utf8');
const compile = (source, jsx = false) => ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, ...(jsx ? { jsx: ts.JsxEmit.ReactJSX } : {}) } }).outputText;
const libUrl = dataUrl(compile(await read('../lib/integrations.ts')));
const dailyUrl = dataUrl(compile(await read('../lib/daily.ts')).replaceAll('"./integrations"', JSON.stringify(libUrl)));
const daily = await import(dailyUrl);

const place = (o = {}) => ({ name: 'Kanpur', region: 'Uttar Pradesh', country: 'India', latitude: 26.46, longitude: 80.33, timeZone: 'Asia/Kolkata', ...o });
const settings = (o = {}) => ({ revision: 3, weather: { place: place(), units: 'metric' }, music: { playlist: { id: 'ABCDEF0123456789', name: 'Focus' } }, briefing: { sections: ['weather', 'calendar', 'goals'] }, ...o });
const goal = (o = {}) => ({ id: 'goal-0000001', text: 'Finish Phase 8', status: 'active', revision: 2, createdAt: 10, doneAt: null, ...o });
const section = (o = {}) => ({ kind: 'weather', status: 'ok', title: 'Weather in Kanpur', items: [{ text: '24 °C, clear. High 31 °C.' }], ...o });
const briefing = (o = {}) => ({ id: 'brief-000001', generatedAt: 5, sections: [section()], spoken: 'Good morning. In Kanpur it is 24 degrees and clear.', ...o });
const connection = (o = {}) => ({ id: 'open-meteo', label: 'Weather', state: 'not-configured', hosts: [], scopes: [], checkedAt: null, message: 'Choose a city and enable weather.', ...o });

function http(replies) {
  const calls = [];
  const fn = async (url, init = {}) => {
    calls.push({ url, method: init.method ?? 'GET', body: init.body ? JSON.parse(init.body) : undefined });
    const next = replies.shift();
    if (next instanceof Error) throw next;
    return { ok: (next.status ?? 200) < 400, status: next.status ?? 200, json: async () => next.body };
  };
  return { fn, calls };
}
const env = extra => ({ version: 1, serverNow: 99, ...extra });

test('settings, places and goals parse strictly', () => {
  assert.deepEqual(daily.parseSettings(settings()), settings());
  assert.ok(daily.parseSettings(settings({ weather: { place: null, units: 'imperial' }, music: { playlist: null } })));
  for (const bad of [settings({ revision: 0 }), settings({ weather: { place: place({ timeZone: 'Mars/Base' }), units: 'metric' } }), settings({ weather: { place: place({ latitude: 91 }), units: 'metric' } }),
    settings({ weather: { place: null, units: 'kelvin' } }), settings({ briefing: { sections: ['weather', 'weather'] } }), settings({ briefing: { sections: ['news'] } }),
    settings({ music: { playlist: { id: '../x', name: 'Focus' } } }), { ...settings(), refreshToken: 'x' }]) assert.equal(daily.parseSettings(bad), null);
  assert.ok(daily.parseGoal(goal()));
  assert.ok(daily.parseGoal(goal({ status: 'done', doneAt: 20 })));
  for (const bad of [goal({ status: 'done' }), goal({ doneAt: 5 }), goal({ text: '' }), goal({ text: 'x'.repeat(201) }), goal({ revision: 0 })]) assert.equal(daily.parseGoal(bad), null);
});

test('a briefing section that is not ok names why and carries no facts; secrets and duplicates are refused', () => {
  assert.ok(daily.parseBriefing(briefing()));
  assert.ok(daily.parseBriefing(briefing({ sections: [section({ kind: 'calendar', status: 'not-configured', title: 'Calendar', items: [], message: 'Google Calendar is not connected.' })] })));
  for (const bad of [
    briefing({ sections: [section({ status: 'error', message: 'Could not load.' })] }), // facts alongside an error
    briefing({ sections: [section({ status: 'unavailable', items: [] })] }), // no reason
    briefing({ sections: [section(), section()] }), briefing({ sections: [] }), briefing({ spoken: '' }),
    briefing({ accessToken: 'ya29' }), briefing({ sections: [section({ items: [{ text: 'x', at: -1 }] })] }),
  ]) assert.equal(daily.parseBriefing(bad), null);
});

test('the Google Desktop JSON is read in memory; only a Desktop client id and secret are accepted', () => {
  const file = JSON.stringify({ installed: { client_id: '1234-abc.apps.googleusercontent.com', client_secret: 'GOCSPX-abcdef123', project_id: 'june', auth_uri: 'https://accounts.google.com/o/oauth2/auth' } });
  assert.deepEqual(daily.readGoogleClient(file), { clientId: '1234-abc.apps.googleusercontent.com', clientSecret: 'GOCSPX-abcdef123' });
  for (const bad of ['{', JSON.stringify({ web: { client_id: '1234-abc.apps.googleusercontent.com', client_secret: 'GOCSPX-abcdef123' } }),
    JSON.stringify({ installed: { client_id: 'evil.example.com', client_secret: 'GOCSPX-abcdef123' } }), JSON.stringify({ installed: { client_id: '1234-abc.apps.googleusercontent.com', client_secret: 'a b' } })])
    assert.throws(() => daily.readGoogleClient(bad), bad.slice(0, 40));
});

test('Google configure/authorize/revoke send exact bodies; consent opens only accounts.google.com over https', async () => {
  const configure = http([{ body: env({ connection: connection({ id: 'google', label: 'Google', state: 'needs-consent', message: 'Ready to connect.' }) }) }]);
  await daily.configureGoogle({ clientId: '1234-abc.apps.googleusercontent.com', clientSecret: 'GOCSPX-abcdef123' }, configure.fn, () => 'req-0000001');
  assert.deepEqual(configure.calls[0], { url: '/api/connections/google/configure', method: 'POST', body: { requestId: 'req-0000001', clientId: '1234-abc.apps.googleusercontent.com', clientSecret: 'GOCSPX-abcdef123' } });
  const auth = http([{ body: env({ authUrl: 'https://accounts.google.com/o/oauth2/v2/auth?client_id=x&code_challenge=y', expiresAt: 500 }) }]);
  const reply = await daily.authorizeGoogle(auth.fn, () => 'req-0000002');
  assert.match(reply.authUrl, /^https:\/\/accounts\.google\.com\//);
  assert.deepEqual(auth.calls[0].body, { requestId: 'req-0000002', scopes: ['calendar.events.readonly'] });
  for (const url of ['http://accounts.google.com/x', 'https://accounts.google.com.evil.example/x', 'https://evil.example/?accounts.google.com', 'javascript:alert(1)']) {
    const bad = http([{ body: env({ authUrl: url, expiresAt: 500 }) }]);
    await assert.rejects(daily.authorizeGoogle(bad.fn), url);
  }
  const revoke = http([{ body: env({ connection: connection({ id: 'google', label: 'Google', state: 'revoked', message: 'Access removed.' }) }) }]);
  await daily.revokeGoogle(revoke.fn, () => 'req-0000003');
  assert.deepEqual(revoke.calls[0].body, { requestId: 'req-0000003' });
});

test('settings, connections, places and goals send only the agreed fields and refuse mismatched replies', async () => {
  const s = http([{ body: env({ settings: settings({ revision: 4 }) }) }]);
  await daily.updateSettings(daily.parseSettings(settings()), { weather: { placeId: 'place-1' } }, s.fn, () => 'req-0000004');
  assert.deepEqual(s.calls[0].body, { requestId: 'req-0000004', revision: 3, weather: { placeId: 'place-1' } });
  const stale = http([{ status: 409, body: { code: 'settings-stale', message: 'Changed.' } }]);
  await assert.rejects(daily.updateSettings(daily.parseSettings(settings()), { music: { playlistId: null } }, stale.fn), e => e.status === 409);
  const enable = http([{ body: env({ connection: connection({ state: 'connected', checkedAt: 9, hosts: ['api.open-meteo.com'] }) }) }]);
  await daily.setConnection('open-meteo', true, enable.fn, () => 'req-0000005');
  assert.deepEqual(enable.calls[0], { url: '/api/connections/open-meteo/enable', method: 'POST', body: { requestId: 'req-0000005' } });
  const wrong = http([{ body: env({ connection: connection({ id: 'google', label: 'Google' }) }) }]);
  await assert.rejects(daily.setConnection('open-meteo', false, wrong.fn), 'a reply about another connector is refused');
  await assert.rejects(daily.searchPlaces(' k ', http([]).fn));
  const places = http([{ body: env({ places: [{ ...place(), id: 'place-1' }] }) }]);
  assert.equal((await daily.searchPlaces('Kanpur', places.fn, () => 'req-0000006')).places[0].id, 'place-1');
  assert.deepEqual(places.calls[0].body, { requestId: 'req-0000006', query: 'Kanpur' });
  await assert.rejects(daily.addGoal('😀'.repeat(201), http([]).fn), 'length counts characters, not UTF-16 units');
  const add = http([{ body: env({ goal: goal() }) }]);
  await daily.addGoal('😀'.repeat(200), add.fn, () => 'req-0000007');
  const done = http([{ body: env({ goal: goal({ status: 'done', doneAt: 30, revision: 3 }) }) }]);
  await daily.changeGoal(daily.parseGoal(goal()), 'complete', undefined, done.fn, () => 'req-0000008');
  assert.deepEqual(done.calls[0], { url: '/api/assistant/goals/goal-0000001/complete', method: 'POST', body: { requestId: 'req-0000008', revision: 2 } });
  const del = http([{ body: env({}) }]);
  await assert.rejects(daily.changeGoal(daily.parseGoal(goal()), 'delete', undefined, del.fn), 'delete needs deleted:true');
  const other = http([{ body: env({ goal: goal({ id: 'goal-9999999' }) }) }]);
  await assert.rejects(daily.changeGoal(daily.parseGoal(goal()), 'reopen', undefined, other.fn));
});

async function component(path, map) {
  let source = compile(await read(path), true)
    .replaceAll('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime')))
    .replaceAll('"react"', JSON.stringify(import.meta.resolve('react')));
  for (const [from, to] of Object.entries(map)) source = source.replaceAll(from, to);
  return dataUrl(source);
}
const React = await import('react');
const { renderToStaticMarkup } = await import('react-dom/server');
const planCard = await component('../components/integrations/PlanCard.tsx', { '"@/lib/integrations"': JSON.stringify(libUrl) });
const { default: DailyPanel } = await import(await component('../components/daily/DailyPanel.tsx', { '"@/lib/daily"': JSON.stringify(dailyUrl), '"@/lib/integrations"': JSON.stringify(libUrl), '"../integrations/PlanCard"': JSON.stringify(planCard) }));
const integrations = connections => ({ capabilities: [], connections, plans: [], serverNow: 1, receivedAt: Date.now(), error: '', refresh() {}, refreshPlans() {}, upsert() {}, replacePlans() {} });
const state = (o = {}) => ({ settings: daily.parseSettings(settings({ weather: { place: null, units: 'metric' }, music: { playlist: null } })), goals: [goal()], error: '', refresh() {}, putSettings() {}, putGoal() {}, dropGoal() {}, ...o });
const render = (connections, o) => renderToStaticMarkup(React.createElement(DailyPanel, { daily: state(o), integrations: integrations(connections), onHear() {}, onAnnounce() {} }));

test('nothing outward is enabled without a click, and weather shows its exact hosts before it can be enabled', () => {
  const listed = render([connection({ hosts: ['api.open-meteo.com', 'geocoding-api.open-meteo.com'] })]);
  assert.match(listed, /June contact api\.open-meteo\.com and geocoding-api\.open-meteo\.com/);
  assert.match(listed, /<button[^>]*>Enable weather</);
  assert.doesNotMatch(listed, /<button[^>]*disabled=""[^>]*>Enable weather</);
  const unlisted = render([connection()]);
  assert.match(unlisted, /<button[^>]*disabled=""[^>]*>Enable weather</, 'no hosts listed → cannot enable');
  assert.doesNotMatch(unlisted, /Find city/, 'no city search before weather is enabled');
  assert.doesNotMatch(unlisted, /Hear briefing/, 'nothing to hear before a briefing exists');
  assert.match(unlisted, /Brief me/);
});

test('calendar setup goes JSON → consent → connected, read-only, with an honest expiry note', () => {
  const google = o => connection({ id: 'google', label: 'Google Calendar and Gmail', message: 'Calendar setup.', ...o });
  const setup = render([google()]);
  assert.match(setup, /type="file"[^>]*accept="application\/json,\.json"/);
  assert.doesNotMatch(setup, /Connect Google Calendar/);
  const consent = render([google({ state: 'needs-consent' })]);
  assert.match(consent, /<button[^>]*>Connect Google Calendar</);
  assert.match(consent, /only to read your calendar events/);
  assert.match(consent, /about 7 days/);
  assert.match(render([google({ state: 'expired' })]), />Reconnect Google Calendar</);
  const connected = render([google({ state: 'connected', checkedAt: 5, scopes: ['calendar.events.readonly'] })]);
  assert.match(connected, />Disconnect Google</); assert.doesNotMatch(connected, /type="file"/);
});

test('music needs explicit permission first; play and focus are offered only for a chosen playlist, as reviewed plans', () => {
  const music = o => connection({ id: 'apple-music', label: 'Apple Music', message: 'Music control.', ...o });
  const asked = render([music()]);
  assert.match(asked, /<button[^>]*>Allow June to control Music</); assert.doesNotMatch(asked, /Choose playlist/);
  const allowed = render([music({ state: 'connected', checkedAt: 5 })]);
  assert.match(allowed, />Choose playlist</); assert.doesNotMatch(allowed, />Play /, 'no play button without a chosen playlist');
  const chosen = renderToStaticMarkup(React.createElement(DailyPanel, { daily: state({ settings: daily.parseSettings(settings()) }), integrations: integrations([music({ state: 'connected', checkedAt: 5 })]), onHear() {}, onAnnounce() {} }));
  assert.match(chosen, />Play Focus</); assert.match(chosen, />Start focus session</);
});

test('daily sources keep secrets out of the browser and open Google only from a click', async () => {
  const panel = await read('../components/daily/DailyPanel.tsx'), lib = await read('../lib/daily.ts');
  for (const source of [panel, lib]) assert.doesNotMatch(source, /localStorage|sessionStorage|indexedDB|console\.(log|debug|info)/);
  assert.equal(panel.match(/window\.open\(/g)?.length, 1, 'one window.open, inside the Connect click');
  assert.match(panel, /function connectGoogle\(\) \{\s*\/\/[^\n]*\n\s*const tab = window\.open\("about:blank", "_blank"\);/);
  assert.match(panel, /tab\.opener = null; tab\.location\.href = reply\.authUrl;/);
  const chat = await read('../components/Chat.tsx');
  assert.match(chat, /<div id="systems-daily"><DailyPanel daily=\{daily\} integrations=\{integrations\} onHear=\{phrase => voice\.replay\(phrase\)\}/);
  assert.match(chat, /<div id="systems-hands"><HandsPanel/);
});

test('review fixes: optional enabled flag, code-point lengths, enabled weather, Google error recovery, June Music wording', async () => {
  const lib = await import(libUrl);
  assert.equal(lib.parseConnection(connection({ enabled: true, hosts: ['api.open-meteo.com'] })).enabled, true);
  assert.equal('enabled' in lib.parseConnection(connection()), false, 'absent stays absent');
  assert.equal(lib.parseConnection(connection({ enabled: 'yes' })), null);
  assert.ok(daily.parseGoal(goal({ text: '😀'.repeat(200) })), 'a 200-character emoji goal the server accepts must display');
  assert.equal(daily.parseGoal(goal({ text: '😀'.repeat(201) })), null);
  // Weather enabled but not yet checked: city search and turn-off are available; no Enable.
  const enabled = render([connection({ enabled: true, hosts: ['api.open-meteo.com', 'geocoding-api.open-meteo.com'], message: 'Enabled. Choose a city.' })]);
  assert.match(enabled, />Find city</); assert.match(enabled, />Turn off weather</); assert.doesNotMatch(enabled, />Enable weather</);
  const off = render([connection({ enabled: false, hosts: ['api.open-meteo.com'] })]);
  assert.match(off, />Enable weather</); assert.doesNotMatch(off, />Find city</);
  const failed = render([connection({ id: 'google', label: 'Google', state: 'error', enabled: true, hosts: ['oauth2.googleapis.com'], message: 'Sign-in did not finish.' })]);
  assert.match(failed, />Reconnect Google Calendar</, 'a failed sign-in is never a dead end');
  const music = render([connection({ id: 'apple-music', label: 'Apple Music', state: 'connected', checkedAt: 5, enabled: true, message: 'Music control on.' })]);
  assert.match(await read('../components/daily/DailyPanel.tsx'), /allow June Music to control Music/);
  assert.doesNotMatch(await read('../components/daily/DailyPanel.tsx'), /June Actions to control Music/);
  assert.match(music, />Choose playlist</);
});

test('weather data is credited to Open-Meteo wherever it is used (CC BY 4.0)', async () => {
  const on = render([connection({ enabled: true, hosts: ['api.open-meteo.com', 'geocoding-api.open-meteo.com'] })]);
  assert.match(on, /Weather data by <a[^>]*href="https:\/\/open-meteo\.com\/"[^>]*>Open-Meteo\.com<\/a>/);
  assert.match(on, /rel="noopener noreferrer"/);
  const off = render([connection({ enabled: false, hosts: ['api.open-meteo.com'] })]);
  assert.doesNotMatch(off, /Weather data by/, 'no credit line before any weather data is used');
  // A briefing's weather section carries the same credit.
  const panel = await read('../components/daily/DailyPanel.tsx');
  assert.match(panel, /section\.kind === "weather" && section\.status === "ok" && <WeatherCredit \/>/);
});

test('Daily and Integrations are reachable from the Systems section buttons', async () => {
  const chat = await read('../components/Chat.tsx');
  const nav = chat.match(/<nav aria-label="Systems sections">\{(\[.*?\])\.map/s)?.[1] ?? '';
  assert.match(nav, /\["daily", "Daily"\]/);
  assert.match(nav, /\["integrations", "Integrations"\]/);
  assert.ok(nav.indexOf('"daily"') < nav.indexOf('"hands"'), 'Daily comes early, before Hands');
});

test('an empty playlist list explains how to add an Apple Music playlist to the Library', async () => {
  const panel = await read('../components/daily/DailyPanel.tsx');
  assert.match(panel, /Add to Library/);
  assert.doesNotMatch(panel, /"No playlists found in Music\."/);
});

test('a chat reply carrying a plan shows its review card under the message', async () => {
  const chat = await read('../components/Chat.tsx');
  assert.match(chat, /const proposedPlan = parsePlan\(event\.plan\);/);
  assert.match(chat, /integrations\.upsert\(proposedPlan, /);
  assert.match(chat, /message\.planId && \(\(\) => \{ const plan = integrations\.plans\.find\(p => p\.id === message\.planId\);/);
  const types = await read('../lib/chat-types.ts');
  assert.match(types, /plan\?: unknown/);
});

test('Apple Calendar is the calendar: an explicit Allow, nothing online, and Google only as a folded alternative', async () => {
  const apple = o => connection({ id: 'apple-calendar', label: 'Apple Calendar', message: 'Calendar reading is off.', ...o });
  const off = render([apple({ enabled: false })]);
  assert.match(off, /<button[^>]*>Allow June to read Calendar</);
  assert.match(off, /stays on this Mac/);
  const on = render([apple({ state: 'connected', enabled: true, checkedAt: 5 })]);
  assert.match(on, />Stop June reading Calendar</); assert.doesNotMatch(on, />Allow June to read Calendar</);
  const panel = await read('../components/daily/DailyPanel.tsx');
  assert.match(panel, /<details[^>]*>\s*<summary>Use Google Calendar instead/);
  const lib = await read('../lib/daily.ts');
  assert.match(lib, /"open-meteo" \| "apple-music" \| "apple-calendar"/);
});

test('the connections bridge allows every connector the Daily panel can switch', async () => {
  const route = await read('../app/api/connections/[...path]/route.ts');
  const lib = await read('../lib/daily.ts');
  const ids = lib.match(/setConnection\(id: ([^,]+),/)[1].match(/"[\w-]+"/g).map(s => s.slice(1, -1));
  assert.deepEqual(ids, ['open-meteo', 'apple-music', 'apple-calendar']);
  for (const id of ids) assert.ok(route.includes(id), `${id} missing from the bridge allowlist`);
});

test('a briefing item shows its time once: the label, then the text without the spoken prefix', () => {
  assert.equal(daily.itemText({ text: 'All day: June Phase 8.', allDay: true }), 'June Phase 8.');
  assert.equal(daily.itemText({ text: '18:00: Test event.', at: 5 }), 'Test event.');
  assert.equal(daily.itemText({ text: 'Kanpur: 29.5 degrees Celsius.' }), 'Kanpur: 29.5 degrees Celsius.', 'untimed text is untouched');
  assert.equal(daily.itemText({ text: '18:00: ', at: 5 }), '18:00: ', 'never left empty');
});

test('Daily offers Previous, Pause, Resume and Next once Music is allowed, each as a reviewed plan', async () => {
  const music = connection({ id: 'apple-music', label: 'Apple Music', state: 'connected', checkedAt: 5, enabled: true, message: 'ok' });
  const html = render([music]);
  for (const label of ['Previous', 'Pause', 'Resume', 'Next']) assert.match(html, new RegExp(`<button[^>]*>${label}</button>`));
  assert.match(html, /play Imagine Dragons/);
  assert.doesNotMatch(render([connection({ id: 'apple-music', label: 'Apple Music', message: 'off' })]), /<button[^>]*>Pause<\/button>/);
  const panel = await read('../components/daily/DailyPanel.tsx');
  assert.match(panel, /proposePlan\("music-control", undefined, undefined, \{ op \}\)/);
});

test('today’s calendar notice: strict read, one phrase, and a key that changes with the day or the events', async () => {
  const good = { date: '2026-11-16', status: 'ok', items: ['All day: June Phase 8.', '17:00: Dentist.'] };
  const { fn, calls } = http([{ body: env({ today: good }) }]);
  const reply = await daily.getToday(fn);
  assert.deepEqual(calls.map(c => [c.method, c.url]), [['GET', '/api/assistant/today']]);
  assert.deepEqual(reply.today, good);
  assert.equal(daily.todayPhrase(reply.today), 'Today on your calendar: All day: June Phase 8. 17:00: Dentist.');
  assert.equal(daily.todayPhrase({ ...good, items: [] }), null, 'an empty day says nothing');
  assert.equal(daily.todayPhrase({ ...good, status: 'not-configured' }), null);
  assert.notEqual(daily.todayKey(good), daily.todayKey({ ...good, date: '2026-11-17' }));
  assert.notEqual(daily.todayKey(good), daily.todayKey({ ...good, items: ['17:00: Dentist.'] }));
  for (const bad of [{ ...good, date: 'today' }, { ...good, items: 'x' }, { ...good, items: [5] }, { ...good, status: 'weird' }, { ...good, items: Array(21).fill('x') }, { ...good, command: 'rm' }, null]) {
    await assert.rejects(daily.getToday(http([{ body: env({ today: bad }) }]).fn), undefined, JSON.stringify(bad));
  }
});

test('the page shows today’s events once per day, speaks them only when June is free, and the bridge allows the read', async () => {
  const chat = await read('../components/Chat.tsx');
  assert.match(chat, /getToday\(\)/); assert.match(chat, /todayPhrase\(/); assert.match(chat, /june-today-notice-v1/);
  assert.match(chat, /className="today-notice" role="status"/);
  assert.match(chat, /todayNotice && alertsReady/, 'spoken only when the voice is ready and June is idle');
  assert.match(chat, />Dismiss</);
  const bridge = await read('../app/api/assistant/[...path]/route.ts');
  assert.match(bridge, /request\.method === "GET" && \/\^\(settings\|goals\|music\\\/playlists\|today\)\$\//);
});
