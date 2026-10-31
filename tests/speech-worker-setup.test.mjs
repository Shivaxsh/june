import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const moduleUrl = new URL('../scripts/speech-worker.mjs', import.meta.url);
let worker;
try { worker = await import(moduleUrl); } catch (error) { if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error; }

test('worker check validates readiness and closes a real private process', async () => {
  assert.ok(worker, 'worker setup/check script must exist');
  const root = await mkdtemp(join(tmpdir(), 'june-worker-script-'));
  try {
    await mkdir(join(root, 'worker/build/bin'), { recursive: true });
    await writeFile(join(root, 'ggml-base.en.bin'), 'fixture');
    const binary = join(root, 'worker/build/bin/june-whisper-worker');
    await writeFile(binary, '#!/usr/bin/env node\nprocess.stdout.write(JSON.stringify({type:"ready",protocol:1,model:"base.en"})+"\\n");process.stdin.resume();process.stdin.on("end",()=>process.exit(0));\n', { mode: 0o700 });
    await worker.checkWorker({ root, timeoutMs: 20000 });
    await writeFile(binary, '#!/usr/bin/env node\nprocess.stdout.write("malformed\\n");process.stdin.resume();\n', { mode: 0o700 });
    await assert.rejects(worker.checkWorker({ root, timeoutMs: 20000 }), /worker|protocol/i);
    await writeFile(binary, '#!/usr/bin/env node\nprocess.stdin.resume();\n', { mode: 0o700 });
    await assert.rejects(worker.checkWorker({ root, timeoutMs: 100 }), /timed out/i);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('worker setup rejects builds inside the repository before writing files', async () => {
  assert.ok(worker, 'worker setup/check script must exist');
  await assert.rejects(worker.setupWorker({ root: new URL('../.june-work/forbidden', import.meta.url).pathname }), /outside.*repository/i);
});

test('npm worker setup entry point defaults to setup when no action is supplied', async () => {
  const { spawnSync } = await import('node:child_process');
  const root = await mkdtemp(join(tmpdir(), 'june-worker-cli-'));
  try {
    const result = spawnSync(process.execPath, [moduleUrl.pathname], { env: { ...process.env, JUNE_SPEECH_HOME: root }, encoding: 'utf8' });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Pinned Whisper libraries/);
  } finally { await rm(root, { recursive: true, force: true }); }
});
