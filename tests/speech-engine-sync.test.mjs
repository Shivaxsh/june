import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { ENGINE, PARAKEET_ID, PARAKEET_DIR } from '../scripts/speech-parakeet.mjs';

test('setup scripts and the backend agree on the listening engine and model', async () => {
  const py = await readFile(new URL('../backend/june/speech.py', import.meta.url), 'utf8');
  assert.equal(py.match(/^ENGINE = '([^']+)'/m)[1], ENGINE);
  const [, id, dir] = py.match(/^PARAKEET_ID, PARAKEET_DIR = '([^']+)', '([^']+)'/m);
  assert.equal(id, PARAKEET_ID); assert.equal(dir, PARAKEET_DIR);
  const worker = await readFile(new URL('../backend/june/parakeet_worker.py', import.meta.url), 'utf8');
  assert.equal(worker.match(/^MODEL_ID = '([^']+)'/m)[1], PARAKEET_ID);
});
