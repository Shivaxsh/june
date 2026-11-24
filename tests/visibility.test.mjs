import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const source = await readFile(new URL('../lib/visibility.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
});
const { onSustainedHide } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'));

function setup(t) {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const events = new EventTarget();
  const doc = {
    hidden: false,
    addEventListener: events.addEventListener.bind(events),
    removeEventListener: events.removeEventListener.bind(events),
  };
  let releases = 0;
  const dispose = onSustainedHide(() => releases++, doc);
  t.after(dispose);
  return {
    get releases() { return releases; },
    change(hidden) { doc.hidden = hidden; events.dispatchEvent(new Event('visibilitychange')); },
    tick(ms) { t.mock.timers.tick(ms); },
    dispose,
  };
}

test('media releases only after 500 ms continuously hidden, once per hide', t => {
  const env = setup(t);
  env.change(true);
  env.tick(499);
  assert.equal(env.releases, 0);
  env.tick(1);
  assert.equal(env.releases, 1);
  env.tick(2000);
  assert.equal(env.releases, 1);
});

test('a layout flicker cancels release; a later hide gets a fresh 500 ms grace', t => {
  const env = setup(t);
  env.change(true);
  env.tick(300);
  env.change(false);
  env.tick(1000);
  assert.equal(env.releases, 0);
  env.change(true);
  env.tick(499);
  assert.equal(env.releases, 0);
  env.tick(1);
  assert.equal(env.releases, 1);
});

test('disposal cancels the pending release and unregisters visibility events', t => {
  const env = setup(t);
  env.change(true);
  env.tick(200);
  env.dispose();
  env.tick(1000);
  env.change(false);
  env.change(true);
  env.tick(1000);
  assert.equal(env.releases, 0);
});
