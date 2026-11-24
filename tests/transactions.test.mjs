import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const dataUrl = source => 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
const read = path => readFile(new URL(path, import.meta.url), 'utf8');
const compile = (source, jsx = false) => ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, ...(jsx ? { jsx: ts.JsxEmit.ReactJSX } : {}) } }).outputText;
const integrationsUrl = dataUrl(compile(await read('../lib/integrations.ts')));
const libUrl = dataUrl(compile(await read('../lib/transactions.ts')).replaceAll('"./integrations"', JSON.stringify(integrationsUrl)));
const lib = await import(libUrl);
function http(replies) {
  const calls = [];
  const fn = async (url, init = {}) => { calls.push({ url, method: init.method ?? 'GET', body: init.body ? JSON.parse(init.body) : undefined }); const next = replies.shift(); return { ok: true, status: 200, json: async () => next }; };
  return { fn, calls };
}

// Three synthetic merchants (no real names, brands or card data).
export const quote = (o = {}) => ({ id: 'q1', revision: 1, fingerprint: 'fp-quote-0001', merchant: 'Sim Mart', currency: 'INR', totalMinor: 52000,
  lines: [{ label: 'Basmati rice 1 kg', quantity: 2, unitMinor: 21000, totalMinor: 42000 }, { label: 'Delivery', quantity: 1, unitMinor: 10000, totalMinor: 10000 }],
  terms: 'Simulated. Returns within 7 days.', expiresAt: 9999999999999, selection: { slot: 'Today 6–8 pm' }, summary: 'Two kilos of basmati rice delivered today 6–8 pm, ₹520 in total.', ...o });
export const retail = (o = {}) => ({ id: 'tx-retail-1', conversationId: 'panel-0123456789abcdef0123456789abcdef', domain: 'retail', status: 'quoted', simulated: true,
  slots: { city: 'Noida' }, missing: [], offers: [], quote: quote(), planId: null, receipt: null, lastReply: 'Here is the quote.', ...o });
const seat = (id, status = 'free') => ({ id, label: id.slice(1), status });
export const seatMap = { screen: 'top', rows: ['A', 'B', 'C', 'D', 'E', 'F'].map(r => ({ label: r, seats: [1, 2, 3, 4, 5, 6, 7, 8].map(n => seat(`${r}${n}`, r === 'E' && (n === 4 || n === 5) ? 'selected' : r === 'A' && n < 3 ? 'taken' : 'free')), gapsAfter: [3] })) };
export const tickets = (o = {}) => ({ id: 'tx-tickets-1', conversationId: 'panel-0123456789abcdef0123456789abcdef', domain: 'tickets', status: 'choosing', simulated: true,
  slots: { city: 'Noida', date: '2026-11-23', party: 2 }, missing: [],
  offers: [{ id: 'show-1', title: '7:15 pm · Hall 2', merchant: 'Sim Cinemas', description: 'Centre block, about two-thirds back', totalMinor: 64000, currency: 'INR', available: true, seats: ['E4', 'E5'], seatMap }],
  quote: null, planId: null, receipt: null, lastReply: 'Two shows have seats together.', ...o });
export const dining = (o = {}) => ({ id: 'tx-dining-1', conversationId: 'panel-0123456789abcdef0123456789abcdef', domain: 'dining', status: 'completed', simulated: true,
  slots: { city: 'Noida', party: 4, time: '8:00 pm' }, missing: [], offers: [],
  quote: quote({ merchant: 'Sim Table', totalMinor: 0, lines: [{ label: 'Table for 4 · 8:00 pm', quantity: 1, unitMinor: 0, totalMinor: 0 }], summary: 'A table for four at 8 pm, no charge.' }),
  planId: null, receipt: { id: 'r1', transactionId: 'tx-dining-1', status: 'confirmed', simulated: true, totalMinor: 0, currency: 'INR', createdAt: 5, detail: 'Simulated reservation · no payment' },
  lastReply: 'Your simulated table is held.', ...o });

test('all three simulated merchants parse strictly', () => {
  for (const t of [retail(), tickets(), dining()]) assert.equal(lib.parseTransaction(t).id, t.id);
  assert.equal(lib.parseTransaction(tickets()).offers[0].seatMap.rows[4].seats[3].status, 'selected');
  const bad = [
    retail({ simulated: false }), retail({ domain: 'flights' }), retail({ status: 'paid' }),
    retail({ quote: quote({ totalMinor: 52000.5 }) }), retail({ quote: quote({ totalMinor: 99 }) }),          // floats / total ≠ sum of lines
    retail({ quote: quote({ currency: 'USD' }) }), retail({ quote: quote({ lines: [] }) }),
    dining({ quote: quote({ merchant: 'Sim Table' }) }),                                                     // dining never charges
    dining({ receipt: { ...dining().receipt, totalMinor: 100 } }), dining({ receipt: { ...dining().receipt, simulated: false } }),
    retail({ receipt: { ...dining().receipt, transactionId: 'someone-else', totalMinor: 52000 } }),
    tickets({ offers: [{ ...tickets().offers[0], seatMap: { ...seatMap, rows: [{ label: 'A', seats: [seat('A1'), seat('A1')] }] } }] }),   // duplicate seat id
    tickets({ offers: [{ ...tickets().offers[0], seatMap: { ...seatMap, rows: [{ label: 'A', seats: [seat('A1')], gapsAfter: [0] }] } }] }),   // aisle after the last seat
    retail({ planId: 'not-a-plan' }), retail({ slots: { 'bad key': 'x' } }),
  ];
  for (const b of bad) assert.throws(() => lib.parseTransaction(b), JSON.stringify(b).slice(0, 80));
});

test('money is shown from integer paise with Indian grouping', () => {
  assert.equal(lib.rupees(124000), '₹1,240'); assert.equal(lib.rupees(124050), '₹1,240.50'); assert.equal(lib.rupees(12345600), '₹1,23,456');
  assert.equal(lib.rupees(0), '₹0'); assert.equal(lib.rupees(1.5), ''); assert.equal(lib.rupees(-1), '');
});

test('respond prepares drafts only: text or a tapped offer, never an approval', async () => {
  const plan = { id: 'a'.repeat(32), revision: 1, fingerprint: 'fp-0000001', status: 'proposed', title: 'Simulated purchase', createdAt: 1, expiresAt: 2, rememberable: false,
    steps: [{ id: 's1', capability: 'commerce.commit', label: 'Simulated purchase', preview: 'Sim Mart · ₹520', status: 'pending' }] };
  const a = http([{ version: 1, serverNow: 5, reply: 'Which city?', transaction: retail({ status: 'collecting', quote: null, missing: ['city'] }) },
                  { version: 1, serverNow: 6, reply: 'Quote ready.', transaction: retail({ planId: plan.id, status: 'awaiting-approval' }), plan }]);
  const first = await lib.respond({ conversationId: 'panel-0123456789abcdef0123456789abcdef', text: ' buy 2 kg rice ' }, a.fn, () => 'req-1');
  assert.deepEqual(first.transaction.missing, ['city']);
  const second = await lib.respond({ conversationId: 'panel-0123456789abcdef0123456789abcdef', select: { offerId: 'offer-1' } }, a.fn, () => 'req-2');
  assert.equal(second.plan.steps[0].capability, 'commerce.commit');
  assert.deepEqual(a.calls.map(c => [c.url, c.body]), [
    ['/api/transactions/respond', { requestId: 'req-1', conversationId: 'panel-0123456789abcdef0123456789abcdef', text: 'buy 2 kg rice' }],
    ['/api/transactions/respond', { requestId: 'req-2', conversationId: 'panel-0123456789abcdef0123456789abcdef', select: { offerId: 'offer-1' } }]]);
  for (const bad of [{ conversationId: 'x y', text: 'hi' }, { conversationId: 'panel-1', text: '  ' }, { conversationId: 'panel-1', select: { offerId: '../x' } }, { conversationId: 'panel-1', text: 'a\u0000b' }])
    await assert.rejects(lib.respond(bad, http([]).fn), JSON.stringify(bad));
  const source = await read('../lib/transactions.ts');
  assert.doesNotMatch(source, /\/approve|voice-approve/, 'the transactions client never approves: approval stays with the plan card / voice bridge');
});

test('the panel session id is stable and private to panel actions', () => {
  const store = new Map();
  const storage = { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  const first = lib.panelSession(storage);
  assert.match(first, /^panel-[a-f0-9]{32}$/); assert.equal(lib.panelSession(storage), first);
  assert.match(lib.panelSession(null), /^panel-[a-f0-9]{32}$/);
  const broken = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  assert.match(lib.panelSession(broken), /^panel-[a-f0-9]{32}$/, 'blocked storage still works');
});

async function component(path, extra = {}) {
  let source = compile(await read(path), true)
    .replaceAll('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime')))
    .replaceAll('"react"', JSON.stringify(import.meta.resolve('react')))
    .replaceAll('"@/lib/transactions"', JSON.stringify(libUrl));
  for (const [from, to] of Object.entries(extra)) source = source.replaceAll(from, to);
  return (await import(dataUrl(source))).default;
}
const React = await import('react');
const { renderToStaticMarkup } = await import('react-dom/server');
const seatMapUrl = dataUrl(compile(await read('../components/transactions/SeatMap.tsx'), true)
  .replaceAll('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime'))));
const Card = await component('../components/transactions/TransactionCard.tsx', { '"./SeatMap"': JSON.stringify(seatMapUrl) });
const render = (t, props = {}) => renderToStaticMarkup(React.createElement(Card, { transaction: lib.parseTransaction(t), now: 1000, ...props }));

test('every card says it is simulated, and a cinema offer shows the seat map with June’s contiguous pick', () => {
  for (const t of [retail(), tickets(), dining()]) assert.match(render(t), /Simulated/);
  const html = render(tickets(), { onChoose() {} });
  assert.match(html, /aria-label="Seat map for 7:15 pm · Hall 2"/);
  assert.match(html, /Row E seat 4, June&#x27;s pick for you/); assert.match(html, /Row A seat 1, taken/);
  assert.match(html, /June&#x27;s pick: E4, E5 \(together\)/);
  assert.match(html, />Choose this</, 'an offer is chosen as a whole (never one seat at a time, so a group is never split)');
  assert.match(html, /seat-aisle/);
});

test('a quote shows every line and the exact total; the card never offers its own approve button', () => {
  const html = render(retail());
  assert.match(html, /Basmati rice 1 kg × 2/); assert.match(html, /₹420/); assert.match(html, /Delivery/); assert.match(html, /Total<\/td><td>₹520/);
  assert.match(html, /Price held for/);
  assert.doesNotMatch(html, />Approve</, 'approval lives only in the existing plan card (exact fingerprint)');
  const withPlan = renderToStaticMarkup(React.createElement(Card, { transaction: lib.parseTransaction(retail()), now: 1000, planCard: React.createElement('div', { id: 'the-plan-card' }) }));
  assert.match(withPlan, /id="the-plan-card"/, 'the plan card is slotted in for approval');
  assert.match(render(retail({ status: 'expired', quote: quote({ expiresAt: 500 }) })), /Quote expired/);
});

test('a restaurant booking shows no charge anywhere and never a paid receipt', () => {
  const html = render(dining());
  assert.match(html, /No charge/); assert.doesNotMatch(html, /₹/, 'no rupee amount at all for a free reservation');
  assert.match(html, /Simulated receipt/); assert.match(html, /Nothing was really bought, booked or charged/);
});

test('an unknown outcome is honest and missing details are asked, not guessed', () => {
  assert.match(render(retail({ status: 'unknown' })), /never place it twice/);
  assert.match(render(tickets({ status: 'collecting', offers: [], missing: ['city', 'date'] })), /June still needs: city, date/);
});

test('chat and Systems wiring: replies carry a transaction card; the panel uses a private session and plan cards to approve', async () => {
  const chat = await read('../components/Chat.tsx');
  assert.match(chat, /const t = parseTransaction\(event\.transaction\); transactionId = t\.id; transactions\.upsert\(t\);/);
  assert.match(chat, /\["shopping", "Shopping"\]/);
  const panel = await read('../components/transactions/TransactionsPanel.tsx');
  assert.match(panel, /panelSession\(/, 'panel requests never write normal chat history');
  assert.match(panel, /onChoose=\{offerId => void send\(\{ select: \{ offerId \} \}, t\.conversationId\)\}/, 'choosing uses the booking’s own conversation (it may have started in chat)');
  assert.match(chat, /respondToBooking\(\{ conversationId: t\.conversationId, select: \{ offerId \} \}\)/, 'offers can be chosen from the chat card too');
  assert.match(panel, /<PlanCard plan=\{plan\}/); assert.doesNotMatch(panel, /approvePlan|voice-approve/);
  const bridge = await read('../app/api/transactions/[[...path]]/route.ts');
  assert.doesNotMatch(bridge, /approve/, 'the transactions bridge has no approval route');
  assert.match(await read('../app/api/plans/[[...path]]/route.ts'), /\(approve\|cancel\|voice-approve\)/);
});
