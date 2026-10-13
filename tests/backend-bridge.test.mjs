import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import ts from 'typescript';

const source = await readFile(new URL('../lib/server/backend.ts', import.meta.url), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const { proxyBackend } = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
const request = (path = '/api/chat', options = {}) => new Request('http://127.0.0.1:3001' + path, {
  method: 'POST', headers: { Host: '127.0.0.1:3001', Origin: 'http://127.0.0.1:3001', 'Content-Type': 'application/json', ...options.headers }, body: '{}', ...options,
});
async function listen(server) { await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); return 'http://127.0.0.1:' + server.address().port; }
async function close(server) { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }

test('bridge refuses redirects instead of forwarding a private request', async () => {
  let redirected = 0, reachedBackend = 0;
  const destination = createServer((_req, res) => { redirected++; res.end('{}'); });
  const other = await listen(destination);
  const backend = createServer((_req, res) => { reachedBackend++; res.writeHead(307, { Location: other }); res.end(); });
  const before = process.env.JUNE_BACKEND_URL;
  process.env.JUNE_BACKEND_URL = await listen(backend);
  try {
    const response = await proxyBackend(request(), '/api/chat', 'chat');
    assert.equal(response.status, 503); assert.equal(redirected, 0); assert.equal(reachedBackend, 1);
    assert.match((await response.json()).message, /Python backend/);
  } finally { if (before === undefined) delete process.env.JUNE_BACKEND_URL; else process.env.JUNE_BACKEND_URL = before; await close(backend); await close(destination); }
});

test('bridge forwards incremental data and cancellation closes the upstream socket', async () => {
  let ended = false;
  const backend = createServer((_req, res) => {
    res.writeHead(200, { 'Content-Type': 'application/x-ndjson' });
    res.write('{"type":"delta","text":"first"}\n');
    res.on('close', () => { ended = true; });
  });
  const before = process.env.JUNE_BACKEND_URL;
  process.env.JUNE_BACKEND_URL = await listen(backend);
  try {
    const response = await proxyBackend(request(), '/api/chat', 'chat');
    const reader = response.body.getReader();
    assert.match(new TextDecoder().decode((await reader.read()).value), /first/);
    await reader.cancel();
    for (let i = 0; i < 50 && !ended; i++) await new Promise(resolve => setTimeout(resolve, 10));
    assert.equal(ended, true);
  } finally { if (before === undefined) delete process.env.JUNE_BACKEND_URL; else process.env.JUNE_BACKEND_URL = before; await close(backend); }
});

test('bridge rejects foreign origins and oversized uploads before connecting', async () => {
  const foreign = new Request('http://127.0.0.1:3001/api/chat', { method: 'POST', headers: { Host: '127.0.0.1:3001', Origin: 'https://example.com' }, body: '{}' });
  assert.equal((await proxyBackend(foreign, '/api/chat', 'chat')).status, 403);
  const large = new Request('http://127.0.0.1:3001/api/speech/transcribe', { method: 'POST', headers: { Host: '127.0.0.1:3001', 'Content-Type': 'audio/wav' }, body: new Uint8Array(1048577) });
  assert.equal((await proxyBackend(large, '/api/speech/transcribe', 'speech')).status, 413);
});
