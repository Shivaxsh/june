import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const compile = async path => ts.transpileModule(await readFile(new URL(path, import.meta.url), 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const url = code => 'data:text/javascript;base64,' + Buffer.from(code).toString('base64');
const base = url(await compile('../lib/orb/renderer.ts'));
const { createHudOrbRenderer } = await import(url((await compile('../lib/orb/hud-renderer.ts')).replace(/from\s*["']\.\/renderer["']/, `from "${base}"`)));

function fixture(input = {}) {
  let next = 0;
  const frames = new Map(), timers = new Map();
  const ctx = new Proxy({ createRadialGradient() { return { addColorStop() {} }; }, createLinearGradient() { return { addColorStop() {} }; }, measureText: v => ({ width: v.length * 6 }) },
    { get(target, key) { return key in target ? target[key] : () => {}; } });
  const canvas = { width: 0, height: 0, getContext: () => ctx, getBoundingClientRect: () => ({ width: 400, height: 400 }) };
  const host = {
    requestFrame(cb) { frames.set(++next, cb); return next; }, cancelFrame(id) { frames.delete(id); },
    delay(cb) { timers.set(++next, cb); return next; }, cancelDelay(id) { timers.delete(id); },
    pixelRatio: () => 1, hidden: () => false,
    observeSize(cb) { cb(); return () => {}; }, observeVisibility() { return () => {}; }, onVisibility() { return () => {}; },
  };
  const state = { mood: 'idle', level: 0, focus: -1, reduced: false, ...input };
  const renderer = createHudOrbRenderer(canvas, () => state, host, () => .5);
  const step = time => { const pending = [...frames.values()]; frames.clear(); pending.forEach(cb => cb(time)); };
  return { renderer, state, frames, timers, step };
}

test('with reduced motion a click still selects the core and does not schedule animation frames', () => {
  const f = fixture({ reduced: true });
  f.renderer.pointerDown(200, 200);
  assert.deepEqual(f.renderer.pointerMove(200, 200, 260, 200), { kind: 'core' }, 'pressing never turns into a drag');
  assert.deepEqual(f.renderer.pointerUp(200, 200), { kind: 'core' });
  assert.equal(f.frames.size, 0);
  assert.equal(f.renderer.pointerUp(200, 200), null, 'a release without a press selects nothing');
});

test('with motion a drag rotates instead of selecting, and a plain click selects', () => {
  const f = fixture();
  f.step(16);
  f.renderer.pointerDown(100, 100);
  assert.deepEqual(f.renderer.pointerMove(140, 100, 140, 100), { kind: 'space' });
  assert.equal(f.renderer.pointerUp(140, 100), null);
  f.renderer.pointerDown(200, 200);
  assert.deepEqual(f.renderer.pointerUp(200, 200), { kind: 'core' });
  f.renderer.pointerDown(200, 200); f.renderer.pointerLeave();
  assert.equal(f.renderer.pointerUp(200, 200), null, 'leaving the canvas cancels a press');
  f.renderer.dispose();
});

test('the governor drops detail tiers when painting is slow and restores them when it is fast', () => {
  const f = fixture();
  const realNow = performance.now.bind(performance);
  let cost = 30, clock = 0;
  performance.now = () => (clock += cost / 2);
  try {
    let time = 0;
    for (let i = 0; i < 48; i++) f.step(time += 40);
    const slow = f.renderer.stats.tier;
    assert.ok(slow >= 1 && slow <= 4, `tier rose under slow paints (${slow})`);
    cost = 2;
    for (let i = 0; i < 90; i++) f.step(time += 40);
    assert.ok(f.renderer.stats.tier < slow, 'tier recovers when paints are fast');
  } finally { performance.now = realNow; f.renderer.dispose(); }
});
