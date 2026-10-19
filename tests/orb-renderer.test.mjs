import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import ts from 'typescript';
const source = await readFile(new URL('../lib/orb/renderer.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
const { createNetwork, createOrbRenderer, MOODS } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'));

test('geometry exactly reproduces the artifact seed, all 510 nodes and precomputed edges', async () => {
  const html = await readFile(new URL('../docs/roadmap/building-june.html', import.meta.url), 'utf8');
  const start = html.indexOf('  let seed = 7;');
  const end = html.indexOf('  const MOODS =', start);
  const expected = JSON.parse(vm.runInNewContext(html.slice(start, end) + ';JSON.stringify({clusters:CLUSTERS,nodes,edges,hubs,icoV,icoE,orbits:ORBITS})'));
  const network = createNetwork();
  assert.deepEqual(network, expected);
  assert.deepEqual(createNetwork(), network);
  assert.equal(network.nodes.length, 510);
  assert.equal(network.hubs.length, 24);
  assert.equal(network.icoE.length, 30);
  assert.equal(network.orbits.length, 3);
  assert.deepEqual(network.clusters.map(c => c.n), [95, 90, 120, 80, 70, 55]);
});

function fixture(size = 400) {
  let next = 0, visible = true, intersect;
  const frames = new Map(), timers = new Map(), paths = [], text = [], vertices = [], labels = [], levels = [], listeners = new Map(), disposals = [];
  const ctx = new Proxy({
    setTransform() {}, clearRect() { paths.length = 0; text.length = 0; vertices.length = 0; labels.length = 0; },
    createRadialGradient() { return { addColorStop() {} }; },
    arc(x,y,r) { assert.ok([x,y,r].every(Number.isFinite)); assert.ok(r >= 0); paths.push([x,y,r]); },
    moveTo(x,y) { vertices.push([x,y]); }, lineTo(x,y) { vertices.push([x,y]); },
    fillText(value,x,y) { text.push(value); labels.push([x,y,value.length * 3]); }, measureText(value) { return { width: value.length * 6 }; },
  }, { get(target, key) { return key in target ? target[key] : () => {}; } });
  const canvas = { width: 0, height: 0, getContext: () => ctx, getBoundingClientRect: () => ({ width: size, height: size }) };
  const host = {
    requestFrame(cb) { frames.set(++next, cb); return next; }, cancelFrame(id) { frames.delete(id); },
    delay(cb) { timers.set(++next, cb); return next; }, cancelDelay(id) { timers.delete(id); },
    pixelRatio: () => 3, hidden: () => !visible,
    observeSize(cb) { cb(); return () => disposals.push('size'); },
    observeVisibility(cb) { intersect = cb; return () => disposals.push('intersection'); },
    onVisibility(cb) { listeners.set('visibility', cb); return () => { listeners.delete('visibility'); disposals.push('visibility'); }; },
  };
  const state = { mood: 'idle', level: 0, activity: 0, preview: false, speechActive: false, reduced: false };
  const renderer = createOrbRenderer(canvas, () => state, value => levels.push(value), host);
  function step(time) { const pending = [...frames.values()]; frames.clear(); pending.forEach(cb => cb(time)); }
  return { canvas, state, renderer, frames, timers, paths, text, vertices, labels, levels, listeners, disposals, step,
    visibility(value) { visible = value; listeners.get('visibility')?.(); }, intersection(value) { intersect(value); },
    tick() { const pending = [...timers.values()]; timers.clear(); pending.forEach(cb => cb()); },
  };
}

test('all moods draw finite geometry, measured levels stay bounded, and backing resolution is capped', () => {
  const f = fixture();
  assert.ok(f.renderer); assert.equal(f.canvas.width, 800);
  let time = 0;
  for (const mood of Object.keys(MOODS)) {
    f.state.mood = mood; f.state.level = .8; f.renderer.invalidate(); f.step(time += 50);
    assert.ok(f.paths.length > 510); assert.ok(f.text.length); assert.equal(f.levels.at(-1), .8);
  }
  f.state.level = NaN; f.step(time += 50); assert.equal(f.levels.at(-1), 0);
  f.state.level = 4; f.step(time += 50); assert.equal(f.levels.at(-1), 1);
  f.renderer.dispose();
});

test('hidden and offscreen canvases stop scheduling; resume owns one loop and disposal releases observers', () => {
  const f = fixture(); f.step(50); assert.equal(f.frames.size, 1);
  f.visibility(false); assert.equal(f.frames.size, 0);
  f.visibility(true); f.renderer.invalidate(); assert.equal(f.frames.size, 1);
  f.intersection(false); assert.equal(f.frames.size, 0);
  f.intersection(true); assert.equal(f.frames.size, 1);
  f.renderer.dispose(); f.renderer.dispose();
  assert.equal(f.frames.size, 0); assert.equal(f.timers.size, 0); assert.equal(f.listeners.size, 0);
  assert.deepEqual(f.disposals.sort(), ['intersection','size','visibility']);
  f.renderer.invalidate(); assert.equal(f.frames.size, 0);
});

test('still mode keeps geometry frozen while its honest meter and mood can update', () => {
  const f = fixture(); f.state.reduced = true; f.renderer.invalidate(); f.step(0);
  assert.equal(f.frames.size, 0); assert.equal(f.timers.size, 1);
  const initial = structuredClone(f.paths);
  f.state.level = .9; f.tick(); assert.equal(f.levels.at(-1), .9);
  assert.deepEqual(f.paths, initial);
  f.state.mood = 'listening'; f.renderer.invalidate(); assert.ok(f.paths.length);
  f.renderer.dispose(); assert.equal(f.timers.size, 0);
});

test('a missing Canvas context falls back without allocating a loop', () => {
  assert.equal(createOrbRenderer({ getContext: () => null }, () => ({}), () => {}), null);
});

test('orbit paths, marker and labels fit throughout a full rotation on desktop and mobile', () => {
  for (const size of [400, 240]) {
    const f = fixture(size);
    for (let time = 0; time <= 65000; time += 50) {
      f.step(time);
      // Outer glow can fade at the border; visible circles, lines and labels must fit.
      for (const [x,y,r] of f.paths) assert.ok(x-r >= 0 && y-r >= 0 && x+r <= size && y+r <= size, `Clipped circle at ${[x,y,r]}`);
      for (const [x,y] of f.vertices) assert.ok(x >= 0 && y >= 0 && x <= size && y <= size, `Clipped path at ${[x,y]}`);
      for (const [x,y,halfWidth] of f.labels) assert.ok(x-halfWidth >= 0 && x+halfWidth <= size && y-10 >= 0 && y+10 <= size, `Clipped label at ${[x,y,halfWidth]}`);
    }
    f.renderer.dispose();
  }
});

test('labelled synthetic previews never appear as measured sound', () => {
  const f = fixture(); f.state.mood = 'speaking'; f.state.preview = true;
  f.step(0); f.step(50); assert.equal(f.levels.at(-1), 0);
  f.state.speechActive = true; f.state.preview = false; f.state.activity = .9;
  f.step(100); assert.equal(f.levels.at(-1), 0);
  f.renderer.dispose();
});
