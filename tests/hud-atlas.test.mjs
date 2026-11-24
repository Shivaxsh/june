import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const compile = async path => ts.transpileModule(await readFile(new URL(path, import.meta.url), 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const url = source => 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
const skyUrl = url(await compile('../lib/hud/sky.ts'));
const atlas = await import(url((await compile('../lib/hud/atlas.ts')).replace('"./sky"', JSON.stringify(skyUrl))));

const frame = atlas.frameFrom(1440, 756, { left: 432, top: 0, width: 1065, height: 606 });   // the desktop plate: orb right of centre

test('the frame follows the orb box, matching the orb renderer\'s sphere radius', () => {
  assert.equal(frame.cx, 432 + 1065 / 2); assert.equal(frame.cy, 303);
  assert.ok(Math.abs(frame.R - (303 - 12) / 1.62) < 1e-9);
});

test('fans: one strand per citing chat (at least one), each starting at the tag and ending on the orb rim', () => {
  const apex = atlas.docApex(0, 5, frame, 282);
  assert.equal(atlas.fan(apex, ['c1', 'c2', 'c3'], frame, 'd1').length, 3);
  const lone = atlas.fan(apex, [], frame, 'd2');
  assert.equal(lone.length, 1, 'an uncited document still has one strand');
  for (const s of atlas.fan(apex, ['a', 'b', 'c', 'd'], frame, 'd3')) {
    assert.deepEqual(atlas.at(s, 0), apex);
    const end = atlas.at(s, 1), d = Math.hypot(end.x - frame.cx, end.y - frame.cy);
    assert.ok(Math.abs(d - frame.R * .98) < 1e-6, 'ends on the rim');
  }
});

test('tags stay left of the orb\'s reach and clear of the rail, and are spread apart', () => {
  const apexes = atlas.spread(Array.from({ length: 5 }, (_, i) => atlas.docApex(i, 5, frame, 282)), 28, 24, 732);
  for (const p of apexes) { assert.ok(p.x >= 282 + 24 && p.x < frame.cx - frame.R * atlas.REACH * .5); assert.ok(p.y >= 24 && p.y <= 732); }
  const ys = apexes.map(p => p.y).sort((a, b) => a - b);
  for (let k = 1; k < ys.length; k++) assert.ok(ys[k] - ys[k - 1] >= 28 - 1e-9, 'no two tags stacked');
  const crowded = atlas.spread([{ x: 0, y: 10 }, { x: 0, y: 10 }, { x: 0, y: 10 }], 28, 24, 60);
  assert.deepEqual(crowded.map(p => p.y), [24, 42, 60], 'no room for 28 px: the gap shrinks evenly, never out of bounds');
});

test('cells sit tangent outside the orb\'s visible reach, inside the canvas; chats and memories stay off the orb', () => {
  for (const c of atlas.cells(frame)) {
    assert.ok(Math.hypot(c.x - frame.cx, c.y - frame.cy) >= frame.R * atlas.REACH - 1e-6);
    assert.ok(c.x - c.r >= 0 && c.x + c.r <= frame.W && c.y - c.r >= 0 && c.y + c.r <= frame.H);
  }
  for (let i = 0; i < 60; i++) {
    const p = atlas.chatGlyph(i, 'chat-' + i, frame, 282);
    assert.ok(p.x >= 282 && p.x <= frame.cx - frame.R * atlas.REACH, 'chats scatter in the left field');
  }
  for (let i = 0; i < 4; i++) { const p = atlas.memoryMark(i, 4, frame); assert.ok(Math.hypot(p.x - frame.cx, p.y - frame.cy) >= frame.R * atlas.REACH * .9 || p.y <= 10); }
});

test('listening gravity is bounded, zero at rest and at the strand ends; launch draws strands in order', () => {
  const p = { x: 500, y: 200 };
  assert.deepEqual(atlas.lean(p, .5, 0, frame), p);
  const leaned = atlas.lean(p, .5, 1, frame);
  assert.ok(Math.hypot(leaned.x - p.x, leaned.y - p.y) <= 16 + 1e-9);
  assert.ok(Math.hypot(atlas.lean(p, 0, 1, frame).x - p.x, 0) < 1e-9, 'the tag end stays put');
  assert.equal(atlas.drawn(0, 10, 0), 0);
  assert.ok(atlas.drawn(0, 10, 800) > atlas.drawn(9, 10, 800), 'earlier strands draw first');
  assert.equal(atlas.drawn(9, 10, 1600), 1);
});

test('voice bits and cell numbers are real readouts', () => {
  let bits = '0'.repeat(36);
  bits = atlas.pushBit(bits, .5); bits = atlas.pushBit(bits, .01);
  assert.equal(bits.length, 36); assert.ok(bits.endsWith('10'));
  assert.deepEqual(atlas.bitRows('101010111111', 6), ['101010', '111111']);
  assert.equal(atlas.cellNumber(4022468096, 'params'), '4.0225');
  assert.equal(atlas.cellNumber(97, 'count'), '97');
  assert.equal(atlas.cellNumber(420, 'seconds'), '0.42');
  assert.equal(atlas.cellNumber(null, 'count'), '—');
});

test('the Atlas canvas respects reduced motion, pauses when hidden, and leaves the orb its own interactions', async () => {
  const src = await readFile(new URL('../components/hud/Atlas.tsx', import.meta.url), 'utf8');
  assert.match(src, /if \(live\.current\.reduced\) draw\(performance\.now\(\)\); else raf = requestAnimationFrame\(loop\);/);
  assert.match(src, /if \(!visible \|\| document\.hidden\) return;/);
  assert.match(src, /Math\.hypot\(x - f\.cx, y - f\.cy\) < f\.R \* 1\.05\) return null;/);
  assert.match(src, /live\.current\.thinking \? 80 : 50/);
  assert.match(src, /for \(const c of graph\.links\?\.citations \?\? \[\]\)/, 'counts come from every stored citation');
});
