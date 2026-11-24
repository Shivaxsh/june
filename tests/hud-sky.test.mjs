import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const load = async path => {
  const { outputText } = ts.transpileModule(await readFile(new URL(path, import.meta.url), 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
  return 'data:text/javascript;base64,' + Buffer.from(outputText).toString('base64');
};
const graphUrl = await load('../lib/hud/constellation.ts');
const sky = await import((await load('../lib/hud/sky.ts')));
const { buildConstellation } = await import(graphUrl);

const input = {
  documents: Array.from({ length: 5 }, (_, i) => ({ id: `d${i}`, name: `doc ${i}`, status: 'ready' })),
  memories: Array.from({ length: 4 }, (_, i) => ({ id: `m${i}`, source: `c${i}` })),
  conversations: Array.from({ length: 60 }, (_, i) => ({ id: `c${i}`, title: `chat ${i}`, updated: 1000 + i })),
  links: { citations: [{ conversation: 'c1', documentId: 'd0' }, { conversation: 'c2', documentId: 'd0' }, { conversation: 'c3', documentId: 'd2' }], memories: [] },
};
const graph = buildConstellation(input, 80);
const stars = sky.skyStars(graph.nodes, graph.edges, sky.recencyOf(input.conversations));

test('every star stays outside the orb and inside the layer, at desktop, tablet and phone sizes', () => {
  for (const [W, H] of [[1440, 780], [1000, 640], [390, 360]]) {
    const { cx, cy, R } = sky.orbGeometry(W, H);
    for (const spin of [0, 1.3, 4]) for (const s of stars) {
      const p = sky.placeStar(s, W, H, spin);
      assert.ok(Math.hypot(p.x - cx, p.y - cy) >= R * sky.CLEAR_ZONE * .999, `star ${s.id} covers the orb at ${W}x${H}`);
      assert.ok(p.x >= 0 && p.x <= W && p.y >= 0 && p.y <= H, `star ${s.id} leaves the ${W}x${H} layer`);
    }
  }
});

test('documents are the bright named stars; only the most cited are labelled, within the budget', () => {
  assert.ok(stars.filter(s => s.type === 'doc').every(s => s.mag === 1));
  assert.ok(stars.filter(s => s.type === 'chat').every(s => s.mag < 1));
  const named = sky.labelled(stars);
  assert.ok(named.size <= sky.LABEL_BUDGET);
  const d0 = stars.find(s => s.id === 'd0');
  assert.equal(d0.cites, 2);
  assert.ok(named.has(d0.i), 'the most cited document keeps its name');
});

test('the comet ends in the orb centre, and gravity and the shockwave are bounded and zero when idle', () => {
  const W = 1440, H = 780, { cx, cy } = sky.orbGeometry(W, H), from = sky.placeStar(stars[0], W, H);
  const end = sky.comet(from, W, H, 1), start = sky.comet(from, W, H, 0);
  assert.ok(Math.hypot(end.x - cx, end.y - cy) < 1e-6 && Math.hypot(start.x - from.x, start.y - from.y) < 1e-6);
  assert.deepEqual(sky.gravity(from, 0, W, H), from);
  for (const s of stars) {
    const p = sky.placeStar(s, W, H), g = sky.gravity(p, 1, W, H);
    assert.ok(Math.hypot(g.x - p.x, g.y - p.y) <= 14 + 1e-9);
    assert.ok(Math.hypot(g.x - cx, g.y - cy) < Math.hypot(p.x - cx, p.y - cy), 'gravity leans toward the orb');
  }
  assert.deepEqual(sky.shock(from, 0, W, H), from);
  assert.deepEqual(sky.shock(from, 1, W, H), from);
});

test('ignition follows creation order and finishes; the sky turns once per local day', () => {
  const order = sky.ignitionOrder(stars, new Map(input.conversations.map(c => [c.id, c.updated])));
  const types = order.map(i => stars[i].type);
  assert.equal(types.lastIndexOf('doc') < types.indexOf('mem'), true);
  assert.equal(types.lastIndexOf('mem') < types.indexOf('chat'), true);
  const chats = order.filter(i => stars[i].type === 'chat').map(i => stars[i].id);
  assert.deepEqual(chats.slice(0, 2), ['c0', 'c1'], 'oldest chats light first');
  assert.equal(sky.ignition(0, stars.length, 0), 0);
  assert.equal(sky.ignition(stars.length - 1, stars.length, 1500 + 300), 1);
  assert.equal(sky.siderealAngle(new Date(2026, 10, 23, 0, 0, 0)), 0);
  assert.ok(Math.abs(sky.siderealAngle(new Date(2026, 10, 23, 12, 0, 0)) - Math.PI) < 1e-9);
});


test('the Sky component respects reduced motion, pauses when hidden, and leaves the orb its own interactions', async () => {
  const source = await readFile(new URL('../components/hud/Sky.tsx', import.meta.url), 'utf8');
  assert.match(source, /if \(live\.current\.reduced\) draw\(performance\.now\(\)\); else frame = requestAnimationFrame\(loop\);/);
  assert.match(source, /if \(Math\.hypot\(x - cx, y - cy\) < R \* CLEAR_ZONE\) return null;/);
  assert.match(source, /L\.thinking \? 80 : 50/, '20 fps at rest, slower while the model thinks');
  assert.match(source, /if \(!visible \|\| document\.hidden\) return;/);
});

test('star names never run off the sky or under the side instruments', async () => {
  const src = await readFile(new URL('../components/hud/Sky.tsx', import.meta.url), 'utf8');
  const fn = src.slice(src.indexOf('export function labelX'), src.indexOf('\n}', src.indexOf('export function labelX')) + 2).replace('export function labelX(x: number, width: number, W: number)', 'function labelX(x, width, W)');
  const labelX = new Function(fn + '; return labelX;')();
  assert.equal(labelX(700, 80, 1440), 709);
  assert.equal(labelX(1000, 80, 1024), 911);
  assert.equal(labelX(1300, 80, 1440), null);
  assert.equal(labelX(120, 80, 1440), null);
  assert.equal(labelX(500, 80, 900), 509);
  assert.match(src, /W >= 600\) \{/, 'no permanent names on phones');
});
