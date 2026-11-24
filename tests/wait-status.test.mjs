import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const source = await readFile(new URL('../lib/wait-status.ts', import.meta.url), 'utf8');
const W = await import('data:text/javascript;base64,' + Buffer.from(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText).toString('base64'));
const chat = await readFile(new URL('../components/Chat.tsx', import.meta.url), 'utf8');

test('the waiting label names only stages the server actually reported', () => {
  assert.equal(W.waitLabel(''), 'Thinking');
  assert.equal(W.waitLabel('', { continuing: true }), 'Continuing');
  assert.equal(W.waitLabel('queued'), 'Waiting for the model');
  assert.equal(W.waitLabel('loading'), 'Loading the model');
  assert.equal(W.waitLabel('searching'), 'Searching documents');
  assert.equal(W.waitLabel('answering'), 'Preparing an answer');
  assert.equal(W.waitLabel('made-up-stage'), 'Thinking', 'unknown stages are ignored, not displayed');
  assert.ok(W.isWaitStage('queued') && W.isWaitStage('loading') && !W.isWaitStage('eval'));
});

test('elapsed time is measured, shown only after a few seconds, and never an estimate', () => {
  assert.equal(W.elapsedText(2900), '');
  assert.equal(W.elapsedText(3000), '3 s');
  assert.equal(W.elapsedText(74_600), '1 min 14 s');
  assert.equal(W.elapsedText(-5), '');
  const all = [W.waitLabel(''), W.waitLabel('loading'), W.elapsedText(12_000), W.elapsedText(600_000)].join(' ');
  assert.doesNotMatch(all, /%|remaining|left|almost|ETA|about \d/i);
});

test('Chat shows real signals: server stages, first text as writing, and measured elapsed time', () => {
  assert.match(chat, /event\.type === 'stage' && isWaitStage\(event\.stage\)/);
  assert.match(chat, /setWaitStage\(event\.stage\)/);
  assert.match(chat, /if \(!firstToken\) \{\s*firstToken = performance\.now\(\);\s*setWriting\(true\);/);
  assert.match(chat, /<Elapsed since=\{waitSince\}/);
  assert.match(chat, /writing \? "writing the reply…"/);
});
