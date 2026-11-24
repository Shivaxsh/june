import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const dataUrl = source => 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
const read = path => readFile(new URL(path, import.meta.url), 'utf8');
const compile = (source, jsx = false) => ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, ...(jsx ? { jsx: ts.JsxEmit.ReactJSX } : {}) } }).outputText;
const libUrl = dataUrl(compile(await read('../lib/integrations.ts')));
const lib = await import(libUrl);

const step = (over = {}) => ({ id: 'step-1', capability: 'mac.open-vscode', label: 'Open VS Code', preview: 'Open or bring forward: Visual Studio Code (com.microsoft.VSCode)', status: 'pending', ...over });
const plan = (over = {}) => ({ id: 'plan-0001', revision: 1, fingerprint: 'fp-0000001', status: 'proposed', title: 'Open VS Code', createdAt: 1000, expiresAt: 121000, rememberable: true, steps: [step()], ...over });
const capability = (over = {}) => ({ id: 'mac.open-vscode', label: 'Open VS Code', connector: 'local', risk: 'local', rememberable: true, available: true, ...over });
const connection = (over = {}) => ({ id: 'google', label: 'Google', state: 'not-configured', hosts: ['oauth2.googleapis.com'], scopes: [], checkedAt: null, message: 'Not connected. Nothing is shared.', ...over });

function http(replies) {
  const calls = [];
  const fn = async (url, init = {}) => {
    calls.push({ url, method: init.method ?? 'GET', body: init.body ? JSON.parse(init.body) : undefined });
    const next = replies.shift();
    if (next instanceof Error) throw next;
    return { ok: next.status === undefined || next.status < 400, status: next.status ?? 200, json: async () => next.body };
  };
  return { fn, calls };
}

test('plans parse strictly; executable fields, bad shapes and oversize plans are refused', () => {
  assert.deepEqual(lib.parsePlan(plan()), plan());
  for (const bad of [
    plan({ command: 'open -a Code' }), plan({ steps: [step({ argv: ['x'] })] }), plan({ steps: [step({ result: { message: 'ok', verified: true, at: 1, shell: 'sh' } })] }),
    plan({ revision: 0 }), plan({ revision: 1.5 }), plan({ status: 'done' }), plan({ steps: [] }), plan({ steps: Array.from({ length: 13 }, (_, i) => step({ id: `s${i}` })) }),
    plan({ steps: [step(), step()] }), plan({ fingerprint: 'x' }), plan({ steps: [step({ preview: '' })] }), plan({ steps: [step({ status: 'retrying' })] }),
  ]) assert.equal(lib.parsePlan(bad), null, JSON.stringify(bad).slice(0, 120));
});

test('capabilities and connections cannot overstate what June can do', () => {
  assert.ok(lib.parseCapability(capability()));
  assert.equal(lib.parseCapability(capability({ risk: 'outward', rememberable: true })), null, 'sending is never rememberable');
  assert.equal(lib.parseCapability(capability({ risk: 'financial', rememberable: true })), null);
  assert.equal(lib.parseCapability(capability({ available: false })), null, 'unavailable needs an honest reason');
  assert.deepEqual(lib.parseCapability(capability({ available: false, unavailableReason: 'Google is not connected.', rememberable: false })).unavailableReason, 'Google is not connected.');
  assert.ok(lib.parseConnection(connection()));
  assert.equal(lib.parseConnection(connection({ state: 'connected' })), null, 'connected requires a verification time');
  assert.equal(lib.parseConnection(connection({ scopes: ['calendar.readonly'] })), null, 'scopes only on a live connection');
  assert.equal(lib.parseConnection(connection({ hosts: ['https://evil.example/x'] })), null);
  assert.ok(lib.parseConnection(connection({ state: 'connected', checkedAt: 5, scopes: ['calendar.readonly'] })));
});

test('a reply with any invalid record or the wrong version is refused whole', async () => {
  for (const body of [{ version: 2, serverNow: 1, plans: [] }, { version: 1, plans: [] }, { version: 1, serverNow: 1, plans: [plan(), { ...plan({ id: 'plan-0002' }), cwd: '/' }] }]) {
    const { fn } = http([{ body }]);
    await assert.rejects(lib.getPlans(fn));
  }
  const { fn } = http([{ body: { version: 1, serverNow: 9, plans: [plan()] } }]);
  assert.equal((await lib.getPlans(fn)).plans.length, 1);
});

test('propose sends only requestId + intent and retries a dropped connection once with the same requestId', async () => {
  const { fn, calls } = http([new TypeError('reset'), { body: { version: 1, serverNow: 5, plan: plan() } }]);
  const reply = await lib.proposePlan('open-vscode', fn, () => 'req-00000001');
  assert.equal(reply.plan.id, 'plan-0001');
  assert.equal(calls.length, 2);
  for (const call of calls) assert.deepEqual(call.body, { requestId: 'req-00000001', intent: 'open-vscode' });
  const twice = http([new TypeError('a'), new TypeError('b')]);
  await assert.rejects(lib.proposePlan('open-vscode', twice.fn, () => 'req-00000002'), e => e.code === 'outcome-unknown');
  await assert.rejects(lib.proposePlan('rm -rf', twice.fn), e => e.code === 'unknown-intent');
});

test('approve binds the reviewed revision and fingerprint; remember only when allowed; lost replies are read back', async () => {
  const reviewed = plan();
  const ok = http([{ body: { version: 1, serverNow: 7, plan: plan({ status: 'running' }) } }]);
  await lib.approvePlan(reviewed, true, ok.fn, () => 'req-00000003');
  assert.deepEqual(ok.calls[0].body, { requestId: 'req-00000003', revision: 1, fingerprint: 'fp-0000001', remember: true });
  assert.equal(ok.calls[0].url, '/api/plans/plan-0001/approve');
  const noRemember = http([{ body: { version: 1, serverNow: 7, plan: plan({ status: 'running', rememberable: false }) } }]);
  await lib.approvePlan(plan({ rememberable: false }), true, noRemember.fn, () => 'req-00000004');
  assert.equal('remember' in noRemember.calls[0].body, false);
  const stale = http([{ status: 409, body: { code: 'plan-stale', message: 'Plan changed.' } }]);
  await assert.rejects(lib.approvePlan(reviewed, false, stale.fn), e => lib.isConflict(e) && e.code === 'plan-stale');
  const lost = http([new TypeError('a'), new TypeError('b'), { body: { version: 1, serverNow: 8, plan: plan({ status: 'unknown' }) } }]);
  const back = await lib.approvePlan(reviewed, false, lost.fn, () => 'req-00000005');
  assert.equal(back.reconciled, true); assert.equal(back.plan.status, 'unknown');
  assert.deepEqual(lost.calls.map(c => c.method), ['POST', 'POST', 'GET'], 'never a third POST');
  assert.equal(lost.calls[0].body.requestId, lost.calls[1].body.requestId);
  const wrong = http([{ body: { version: 1, serverNow: 7, plan: plan({ id: 'plan-9999' }) } }]);
  await assert.rejects(lib.cancelPlan(reviewed, wrong.fn), 'a reply about another plan is refused');
});

test('plan merges never move backwards, keep the first final outcome, and accept a new revision', () => {
  assert.equal(lib.mergePlan(plan({ status: 'running' }), plan({ status: 'proposed' })).status, 'running');
  assert.equal(lib.mergePlan(plan({ status: 'completed' }), plan({ status: 'failed' })).status, 'completed');
  assert.equal(lib.mergePlan(plan({ status: 'running' }), plan({ status: 'partial' })).status, 'partial');
  assert.equal(lib.mergePlan(plan({ status: 'completed' }), plan({ revision: 2, status: 'proposed', fingerprint: 'fp-0000002' })).revision, 2);
  assert.equal(lib.mergePlan(plan({ revision: 2 }), plan({ revision: 1, status: 'completed' })).revision, 2);
  assert.equal(lib.mergePlans([], Array.from({ length: 25 }, (_, i) => plan({ id: `plan-${String(i).padStart(4, '0')}` }))).length, 20);
});

async function component(path, extra = {}) {
  let source = compile(await read(path), true)
    .replaceAll('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime')))
    .replaceAll('"react"', JSON.stringify(import.meta.resolve('react')))
    .replaceAll('"@/lib/integrations"', JSON.stringify(libUrl));
  for (const [from, to] of Object.entries(extra)) source = source.replaceAll(from, to);
  return (await import(dataUrl(source))).default;
}
const React = await import('react');
const { renderToStaticMarkup } = await import('react-dom/server');
const PlanCard = await component('../components/integrations/PlanCard.tsx');
const render = (p, caps = [capability()]) => renderToStaticMarkup(React.createElement(PlanCard, {
  plan: p, capabilities: new Map(caps.map(c => [c.id, c])), serverNow: 1000, receivedAt: Date.now(), onChange() {}, onRefresh() {}, onAnnounce() {} }));

test('a plan under review shows every exact preview, Approve and Cancel, and remember only for a safe local plan', () => {
  const html = render(plan());
  assert.match(html, /Open or bring forward: Visual Studio Code \(com\.microsoft\.VSCode\)/);
  assert.match(html, />Approve</); assert.match(html, />Cancel</);
  assert.match(html, /Don&#x27;t ask again for this exact request/);
  const outward = render(plan({ rememberable: true, steps: [step({ capability: 'gmail.send', preview: 'To: a@example.com\nSubject: Hi\n\nBody' })] }), [capability({ id: 'gmail.send', risk: 'outward', rememberable: false })]);
  assert.doesNotMatch(outward, /Don&#x27;t ask again/);
  assert.match(outward, /reviewed every time|need your review every time/i);
  assert.match(outward, /To: a@example.com/);
  const unknownCap = render(plan({ steps: [step({ capability: 'mystery.tool' })] }), []);
  assert.doesNotMatch(unknownCap, /Don&#x27;t ask again/, 'an uncatalogued capability is never rememberable');
});

test('finished plans show checked results; an unknown outcome is stated and never offers a retry', () => {
  const done = render(plan({ status: 'completed', steps: [step({ status: 'completed', result: { message: 'VS Code is open and in front.', verified: true, at: 2000 } })] }));
  assert.match(done, /Checked: VS Code is open and in front\./); assert.doesNotMatch(done, />Approve</);
  const unknown = render(plan({ status: 'unknown', steps: [step({ status: 'unknown' })] }));
  assert.match(unknown, /could not confirm whether this happened/i);
  assert.doesNotMatch(unknown, />(Approve|Retry|Try again)</);
  const unconfirmed = render(plan({ status: 'completed', steps: [step({ status: 'completed', result: { message: 'Asked macOS to open it.', verified: false, at: 2000 } })] }));
  assert.match(unconfirmed, /Not confirmed: Asked macOS to open it\./);
});

test('the panel lists connections honestly and offers no way to connect or run without a plan', async () => {
  const Panel = await component('../components/integrations/IntegrationsPanel.tsx', { '"./PlanCard"': JSON.stringify(dataUrl(compile(await read('../components/integrations/PlanCard.tsx'), true)
    .replaceAll('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime'))).replaceAll('"react"', JSON.stringify(import.meta.resolve('react'))).replaceAll('"@/lib/integrations"', JSON.stringify(libUrl)))) });
  const integrations = { capabilities: [capability(), capability({ id: 'calendar.read', label: 'Read Google Calendar', connector: 'google', risk: 'read', rememberable: true, available: false, unavailableReason: 'Google is not connected.' })],
    connections: [connection(), connection({ id: 'apple-music', label: 'Apple Music', hosts: [], message: 'Not available yet.' , state: 'unsupported' })],
    plans: [plan()], serverNow: 1000, receivedAt: Date.now(), error: '', refresh() {}, refreshPlans() {}, upsert() {} };
  const html = renderToStaticMarkup(React.createElement(Panel, { integrations, onAnnounce() {} }));
  assert.match(html, /Not set up/); assert.match(html, /Not available yet/); assert.match(html, /No online access enabled/);
  assert.match(html, /Google is not connected\./);
  assert.doesNotMatch(html, /<button[^>]*>\s*(Connect|Sign in|Authori[sz]e|Retry)\b/i, 'no account connection or blind retry from this panel');
  assert.match(html, />Open VS Code</);
  assert.match(html, /Waiting for review/);
  const panel = await read('../components/integrations/IntegrationsPanel.tsx');
  assert.doesNotMatch(panel, /fetch\(|\/api\/actions/, 'the panel only uses the plan contract');
  const chat = await read('../components/Chat.tsx');
  assert.match(chat, /<div id="systems-hands"><HandsPanel/, 'legacy Hands stays mounted');
  assert.match(chat, /<div id="systems-integrations"><IntegrationsPanel integrations=\{integrations\}/);
});

test('a same-status reply never moves a step backwards or drops its result', () => {
  const ahead = plan({ status: 'running', steps: [step({ id: 's1', status: 'completed', result: { message: 'Opened.', verified: true, at: 5 } }), step({ id: 's2', status: 'running' })] });
  const stale = plan({ status: 'running', steps: [step({ id: 's1', status: 'running' }), step({ id: 's2', status: 'pending' })] });
  const merged = lib.mergePlan(ahead, stale);
  assert.deepEqual(merged.steps.map(s => s.status), ['completed', 'running']);
  assert.equal(merged.steps[0].result.message, 'Opened.');
  const later = plan({ status: 'running', steps: [step({ id: 's1', status: 'completed', result: { message: 'Opened.', verified: true, at: 5 } }), step({ id: 's2', status: 'completed', result: { message: 'Played.', verified: true, at: 9 } })] });
  assert.deepEqual(lib.mergePlan(ahead, later).steps.map(s => s.status), ['completed', 'completed']);
  // The first final step outcome is kept, as for plans.
  assert.equal(lib.mergePlan(later, plan({ status: 'running', steps: [step({ id: 's1', status: 'failed' }), step({ id: 's2', status: 'completed' })] })).steps[0].status, 'completed');
});

test('cancelRequested is an optional honest flag; forget sends only a requestId and returns the plan list', async () => {
  assert.equal(lib.parsePlan(plan({ status: 'running', cancelRequested: true })).cancelRequested, true);
  assert.equal(lib.parsePlan(plan({ cancelRequested: 'yes' })), null);
  const { fn, calls } = http([new TypeError('reset'), { body: { version: 1, serverNow: 3, plans: [plan({ status: 'cancelled', steps: [step({ status: 'cancelled' })] })] } }]);
  const reply = await lib.forgetApprovals(fn, () => 'req-00000009');
  assert.equal(reply.plans[0].status, 'cancelled');
  assert.equal(calls[0].url, '/api/plans/forget');
  assert.deepEqual(calls.map(c => c.body), [{ requestId: 'req-00000009' }, { requestId: 'req-00000009' }]);
});

test('approved or running plans can be cancelled with the bound proof and say what cancelling can and cannot stop', () => {
  const running = render(plan({ status: 'running', steps: [step({ id: 's1', status: 'running' }), step({ id: 's2', status: 'pending' })] }));
  assert.match(running, />Cancel remaining steps</);
  assert.match(running, /already running may still finish/i);
  assert.doesNotMatch(running, />Approve</);
  const stopping = render(plan({ status: 'running', cancelRequested: true, steps: [step({ status: 'running' })] }));
  assert.match(stopping, /Stop requested/);
  assert.doesNotMatch(stopping, />Cancel remaining steps</);
  assert.doesNotMatch(render(plan({ status: 'completed', steps: [step({ status: 'completed' })] })), />Cancel/);
});

test('a connection with no enabled service hosts never claims to be local-only', async () => {
  const Panel = await component('../components/integrations/IntegrationsPanel.tsx', { '"./PlanCard"': JSON.stringify(dataUrl(compile(await read('../components/integrations/PlanCard.tsx'), true)
    .replaceAll('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime'))).replaceAll('"react"', JSON.stringify(import.meta.resolve('react'))).replaceAll('"@/lib/integrations"', JSON.stringify(libUrl)))) });
  const integrations = { capabilities: [capability()], connections: [connection({ hosts: [] })], plans: [], serverNow: 1, receivedAt: Date.now(), error: '', refresh() {}, refreshPlans() {}, upsert() {}, replacePlans() {} };
  const html = renderToStaticMarkup(React.createElement(Panel, { integrations, onAnnounce() {} }));
  assert.doesNotMatch(html, /On this Mac only/);
  assert.match(html, /No online access enabled/);
  assert.match(html, /<button[^>]*>Forget remembered approvals</);
});

test('plans in progress are shown open, never folded into the collapsed history', async () => {
  const Panel = await component('../components/integrations/IntegrationsPanel.tsx', { '"./PlanCard"': JSON.stringify(dataUrl(compile(await read('../components/integrations/PlanCard.tsx'), true)
    .replaceAll('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime'))).replaceAll('"react"', JSON.stringify(import.meta.resolve('react'))).replaceAll('"@/lib/integrations"', JSON.stringify(libUrl)))) });
  const integrations = { capabilities: [capability()], connections: [], serverNow: 1, receivedAt: Date.now(), error: '', refresh() {}, refreshPlans() {}, upsert() {}, replacePlans() {},
    plans: [plan({ id: 'plan-run-0001', status: 'running', steps: [step({ status: 'running' })] }), plan({ id: 'plan-old-0001', status: 'completed', steps: [step({ status: 'completed' })] })] };
  const html = renderToStaticMarkup(React.createElement(Panel, { integrations, onAnnounce() {} }));
  const history = html.indexOf('<details');
  const running = html.indexOf('Cancel remaining steps');
  assert.ok(running > -1 && (history === -1 || running < history), 'the running plan and its Cancel are outside collapsed history');
  assert.match(html, /In progress/);
  assert.match(html, /Recent plans \(1\)/);
});

test('hosts are what a connector would contact; only a connected one is described as talking to them', async () => {
  const Panel = await component('../components/integrations/IntegrationsPanel.tsx', { '"./PlanCard"': JSON.stringify(dataUrl(compile(await read('../components/integrations/PlanCard.tsx'), true)
    .replaceAll('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime'))).replaceAll('"react"', JSON.stringify(import.meta.resolve('react'))).replaceAll('"@/lib/integrations"', JSON.stringify(libUrl)))) });
  const integrations = { capabilities: [capability()], plans: [], serverNow: 1, receivedAt: Date.now(), error: '', refresh() {}, refreshPlans() {}, upsert() {}, replacePlans() {},
    connections: [connection({ id: 'open-meteo', label: 'Weather', hosts: ['api.open-meteo.com'] }), connection({ id: 'google', label: 'Google', state: 'connected', checkedAt: 5, scopes: ['calendar.events.readonly'], hosts: ['www.googleapis.com'] })] };
  const html = renderToStaticMarkup(React.createElement(Panel, { integrations, onAnnounce() {} }));
  assert.match(html, /Would contact: api\.open-meteo\.com · not enabled/);
  assert.match(html, /Talks to: www\.googleapis\.com/);
  assert.doesNotMatch(html, /Talks to: api\.open-meteo\.com/);
});

test('an enabled connector not yet checked is described as allowed, not as talking or disabled', async () => {
  const Panel = await component('../components/integrations/IntegrationsPanel.tsx', { '"./PlanCard"': JSON.stringify(dataUrl(compile(await read('../components/integrations/PlanCard.tsx'), true)
    .replaceAll('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime'))).replaceAll('"react"', JSON.stringify(import.meta.resolve('react'))).replaceAll('"@/lib/integrations"', JSON.stringify(libUrl)))) });
  const integrations = { capabilities: [capability()], plans: [], serverNow: 1, receivedAt: Date.now(), error: '', refresh() {}, refreshPlans() {}, upsert() {}, replacePlans() {},
    connections: [connection({ id: 'open-meteo', label: 'Weather', enabled: true, hosts: ['api.open-meteo.com'] })] };
  const html = renderToStaticMarkup(React.createElement(Panel, { integrations, onAnnounce() {} }));
  assert.match(html, /Allowed to contact: api\.open-meteo\.com · not checked yet/);
  assert.doesNotMatch(html, /not enabled/);
});

test('opening an app sends only registry ids, and the app list never carries a bundle id or path', async () => {
  const { fn, calls } = http([{ body: { version: 1, serverNow: 5, plan: plan() } }]);
  await lib.proposePlan('open-app', fn, () => 'req-00000020', { apps: ['chrome', 'figma'] });
  assert.deepEqual(calls[0].body, { requestId: 'req-00000020', intent: 'open-app', input: { apps: ['chrome', 'figma'] } });
  await assert.rejects(lib.proposePlan('open-app', http([]).fn, () => 'req-00000021', { apps: ['com.google.Chrome'] }), e => e.code === 'invalid-input');
  await assert.rejects(lib.proposePlan('open-app', http([]).fn, () => 'req-00000022', { apps: [] }));
  await assert.rejects(lib.proposePlan('open-app', http([]).fn, () => 'req-00000023', { apps: ['a', 'b', 'c', 'd'] }));
  const apps = http([{ body: { version: 1, serverNow: 5, apps: [{ id: 'chrome', label: 'Google Chrome', remembered: true }, { id: 'figma', label: 'Figma', remembered: false }] } }]);
  assert.deepEqual((await lib.getApps(apps.fn)).apps.map(a => a.id), ['chrome', 'figma']);
  for (const bad of [{ id: 'chrome', label: 'Chrome', remembered: true, bundle: 'com.google.Chrome' }, { id: 'chrome', label: 'Chrome', remembered: true, path: '/Applications' }, { id: 'Chrome App', label: 'x', remembered: false }, { id: 'chrome', label: 'Chrome' }]) {
    await assert.rejects(lib.getApps(http([{ body: { version: 1, serverNow: 5, apps: [bad] } }]).fn), JSON.stringify(bad));
  }
});

test('the panel lists the apps with an Open button each and says which open without asking', async () => {
  const Panel = await component('../components/integrations/IntegrationsPanel.tsx', { '"./PlanCard"': JSON.stringify(dataUrl(compile(await read('../components/integrations/PlanCard.tsx'), true)
    .replaceAll('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime'))).replaceAll('"react"', JSON.stringify(import.meta.resolve('react'))).replaceAll('"@/lib/integrations"', JSON.stringify(libUrl)))) });
  const integrations = { capabilities: [capability({ id: 'app.open', label: 'Open an app from your list' })], connections: [], plans: [], serverNow: 1, receivedAt: Date.now(), error: '', refresh() {}, refreshPlans() {}, upsert() {}, replacePlans() {},
    apps: [{ id: 'chrome', label: 'Google Chrome', remembered: true }, { id: 'figma', label: 'Figma', remembered: false }] };
  const html = renderToStaticMarkup(React.createElement(Panel, { integrations, onAnnounce() {} }));
  assert.match(html, /<button[^>]*>Open Google Chrome<\/button>/); assert.match(html, /<button[^>]*>Open Figma<\/button>/);
  assert.match(html, /Opens without asking/); assert.match(html, /Asks first/);
  assert.match(html, /open Chrome and Figma/i, 'tells the person what to say');
});

test('music control and library plans send strict inputs; their remember wording says what it covers', async () => {
  const a = http([{ body: { version: 1, serverNow: 5, plan: plan() } }]);
  await lib.proposePlan('music-control', a.fn, () => 'req-00000030', { op: 'pause' });
  assert.deepEqual(a.calls[0].body, { requestId: 'req-00000030', intent: 'music-control', input: { op: 'pause' } });
  await assert.rejects(lib.proposePlan('music-control', http([]).fn, () => 'r', { op: 'quit' }), e => e.code === 'invalid-input');
  await assert.rejects(lib.proposePlan('music-library', http([]).fn, () => 'r', { query: 'x" & y', what: 'any' }), e => e.code === 'invalid-input');
  await assert.rejects(lib.proposePlan('open-vscode', http([]).fn, () => 'r', { op: 'pause' }), e => e.code === 'invalid-input');
  const music = render(plan({ steps: [step({ capability: 'music.control', label: 'Pause music', preview: 'Pause playback in Music.' })] }), [capability({ id: 'music.control', label: 'Control music playback' })]);
  assert.match(music, /Don&#x27;t ask again for music controls and playing from my library/);
  assert.doesNotMatch(music, /for this exact request/);
});

test('quick actions send only fixed words and checked numbers', async () => {
  const reply = () => ({ body: { version: 1, serverNow: 5, plan: plan() } });
  const a = http([reply(), reply(), reply(), reply()]);
  await lib.proposePlan('coding-session', a.fn, () => 'req-00000040');
  await lib.proposePlan('keep-awake', a.fn, () => 'req-00000041', { minutes: 60 });
  await lib.proposePlan('appearance', a.fn, () => 'req-00000042', { mode: 'toggle' });
  await lib.proposePlan('convert-images', a.fn, () => 'req-00000043', { format: 'png' });
  assert.deepEqual(a.calls.map(c => c.body), [{ requestId: 'req-00000040', intent: 'coding-session' }, { requestId: 'req-00000041', intent: 'keep-awake', input: { minutes: 60 } },
    { requestId: 'req-00000042', intent: 'appearance', input: { mode: 'toggle' } }, { requestId: 'req-00000043', intent: 'convert-images', input: { format: 'png' } }]);
  for (const [intent, input] of [['keep-awake', { minutes: 0 }], ['keep-awake', { minutes: 1.5 }], ['appearance', { mode: 'sepia' }], ['convert-images', { format: 'exe' }],
    ['convert-images', { format: 'png', width: 5 }], ['coding-session', { minutes: 5 }], ['free-port', { port: 3000 }], ['keep-awake', { minutes: 60, command: 'x' }]]) {
    await assert.rejects(lib.proposePlan(intent, http([]).fn, () => 'r', input), e => e.code === 'invalid-input' || e.code === 'unknown-intent', JSON.stringify([intent, input]));
  }
});

test('the panel offers Developer and Designer quick actions and says what to ask for the rest', async () => {
  const Panel = await component('../components/integrations/IntegrationsPanel.tsx', { '"./PlanCard"': JSON.stringify(dataUrl(compile(await read('../components/integrations/PlanCard.tsx'), true)
    .replaceAll('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime'))).replaceAll('"react"', JSON.stringify(import.meta.resolve('react'))).replaceAll('"@/lib/integrations"', JSON.stringify(libUrl)))) });
  const integrations = { capabilities: [capability({ id: 'app.open', label: 'Open an app from your list' }), capability({ id: 'quick.appearance', label: 'Switch light and dark mode', available: false, unavailableReason: 'Run npm run quick:setup.' })],
    connections: [], plans: [], serverNow: 1, receivedAt: Date.now(), error: '', refresh() {}, refreshPlans() {}, upsert() {}, replacePlans() {}, apps: [] };
  const html = renderToStaticMarkup(React.createElement(Panel, { integrations, onAnnounce() {} }));
  for (const label of ['Start coding session', 'Keep Mac awake 1 hour', 'Let Mac sleep', 'Open design workspace', 'Switch light / dark', 'Take a screenshot', 'Colour picker', 'Convert images to PNG'])
    assert.match(html, new RegExp(`<button[^>]*>${label}</button>`), label);
  assert.match(html, /<button[^>]*disabled=""[^>]*>Switch light \/ dark<\/button>/, 'an unavailable tool disables its button');
  assert.match(html, /git status of June/); assert.match(html, /free port 3000/); assert.match(html, /June Images/);  const source = await read('../components/integrations/IntegrationsPanel.tsx');
  assert.match(source, /className="quick-result" role="status"/, 'a remembered action shows its checked result in the panel');
  assert.match(source, /setQuickRun\(\{ id: reply\.plan\.id, label \}\)/);
});

test('a step that never started because an earlier one was not confirmed says so (strict reason contract)', () => {
  const blocked = step({ id: 'step-2', capability: 'jobs.apply', status: 'skipped', reason: 'blocked-by-unknown' });
  const parsed = lib.parsePlan(plan({ status: 'unknown', steps: [step({ status: 'unknown', capability: 'jobs.apply' }), blocked] }));
  assert.equal(parsed.steps[1].reason, 'blocked-by-unknown', 'the reason is kept');
  for (const bad of [step({ status: 'skipped', reason: 'user-choice' }), step({ status: 'pending', reason: 'blocked-by-unknown' }),
                     step({ status: 'completed', reason: 'blocked-by-unknown' }), step({ status: 'skipped', reason: 5 }),
                     step({ status: 'skipped', reason: null }), step({ status: 'pending', reason: null })])
    assert.equal(lib.parsePlan(plan({ steps: [bad] })), null, JSON.stringify(bad));
  assert.equal(lib.parsePlan(plan({ steps: [step({ status: 'skipped' })] })).steps[0].reason, undefined, 'a plain skipped step stays plain');
  assert.equal(lib.stepWords(parsed.steps[1]), 'Not started — previous application not confirmed');
  assert.equal(lib.stepWords(step({ status: 'skipped', reason: 'blocked-by-unknown' })), 'Not started — previous step not confirmed');
  assert.equal(lib.stepWords(step({ status: 'skipped' })), 'Skipped', 'only the reason, never the bare status, means not started');
  assert.equal(lib.stepWords(step({ status: 'unknown' })), 'Outcome unknown');
});

test('a plan’s outcome counts keep confirmed, unconfirmed and not-started apart', () => {
  const s = (status, extra = {}) => step({ id: 'x' + Math.random().toString(36).slice(2, 8), capability: 'jobs.apply', status, ...extra });
  const mixed = plan({ status: 'unknown', steps: [s('completed'), s('unknown'), s('skipped', { reason: 'blocked-by-unknown' }), s('skipped', { reason: 'blocked-by-unknown' }), s('cancelled')] });
  assert.deepEqual(lib.planCounts(mixed), { confirmed: 1, unconfirmed: 1, notStarted: 2, failed: 0, cancelled: 1, skipped: 0 });
  assert.equal(lib.countsLine(mixed), '1 confirmed · 1 not confirmed · 2 not started · 1 cancelled');
  assert.equal(lib.countsLine(plan({ status: 'completed', steps: [s('completed')] })), '', 'nothing to explain for a single finished step');
  assert.equal(lib.countsLine(plan({ status: 'running', steps: [s('completed'), s('pending')] })), '', 'only after the plan ends');
});

test('PlanCard and the Email & jobs panel use the reason-aware wording and counts', async () => {
  const apply = capability({ id: 'jobs.apply', label: 'Apply to a Naukri job in your Chrome', risk: 'outward', rememberable: false });
  const s = (id, status, extra = {}) => step({ id, capability: 'jobs.apply', label: 'Apply: ' + id, preview: 'Apply to ' + id, status, ...extra });
  const html = render(plan({ status: 'unknown', rememberable: false, steps: [s('done-1', 'completed'), s('unsure-2', 'unknown'), s('later-3', 'skipped', { reason: 'blocked-by-unknown' })] }), [apply]);
  assert.match(html, /Not started — previous application not confirmed/, 'the never-started step says why');
  assert.match(html, /1 confirmed · 1 not confirmed · 1 not started/);
  assert.match(html, /apply to the rest/, 'and how to continue: a new card to review, nothing automatic');
  const plain = render(plan({ status: 'cancelled', rememberable: false, steps: [s('later-4', 'skipped')] }), [apply]);
  assert.doesNotMatch(plain, /Not started — previous/, 'a plain skip (for example a cancellation) is not described as blocked');
  const panel = await read('../components/integrations/MailJobsPanel.tsx');
  assert.match(panel, /countsLine\(shown\)/);
});
