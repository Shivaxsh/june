import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

// Drives useDocuments with a minimal hook runtime and mocked /api/knowledge responses.
const dataUrl = source => 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
const react = dataUrl(`export const useRef = v => globalThis.docHooks.ref(v);
export const useState = v => globalThis.docHooks.state(v);
export const useEffect = (e, d) => globalThis.docHooks.effect(e, d);
export const useCallback = (f, d) => globalThis.docHooks.memo(() => f, d);`);
const compile = source => ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const types = dataUrl(compile(await readFile(new URL('../lib/knowledge-types.ts', import.meta.url), 'utf8')));
const hookSource = compile(await readFile(new URL('../components/knowledge/useDocuments.ts', import.meta.url), 'utf8'))
  .replace(/from ["']react["']/, `from ${JSON.stringify(react)}`).replace(/from ["']@\/lib\/knowledge-types["']/, `from ${JSON.stringify(types)}`);
const { useDocuments } = await import(dataUrl(hookSource));
const tick = async () => { for (let i = 0; i < 10; i++) await new Promise(resolve => setImmediate(resolve)); };
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };

function fixture() {
  const slots = [], pending = [], cleanups = [];
  let cursor = 0;
  const server = { documents: [], revision: 1, status: [] };
  const calls = [];
  const set = (key, value) => Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const saved = Object.fromEntries(['docHooks', 'window', 'document', 'fetch', 'BroadcastChannel', 'localStorage'].map(k => [k, Object.getOwnPropertyDescriptor(globalThis, k)]));
  set('docHooks', {
    ref(v) { const i = cursor++; return slots[i] ??= { current: v }; },
    state(v) { const i = cursor++; if (!(i in slots)) slots[i] = v; return [slots[i], next => { slots[i] = typeof next === 'function' ? next(slots[i]) : next; }]; },
    memo(make, deps) { const i = cursor++; const prev = slots[i]; if (!prev || deps.some((d, j) => d !== prev.deps[j])) slots[i] = { value: make(), deps }; return slots[i].value; },
    effect(effect, deps) { const i = cursor++; const prev = slots[i]; if (!prev || deps.some((d, j) => d !== prev[j])) { slots[i] = deps; pending.push(() => { cleanups[i]?.(); cleanups[i] = effect(); }); } },
  });
  set('window', { addEventListener() {}, removeEventListener() {} });
  set('document', { hidden: true }); // no interval polls: every refresh in a test is explicit
  set('BroadcastChannel', undefined);
  set('localStorage', { setItem() {} });
  set('fetch', async (url, options = {}) => {
    const path = String(url).replace('/api/knowledge/', ''); const method = options.method ?? 'GET';
    calls.push(`${method} ${path}`);
    if (path === 'documents' && method === 'GET') return Response.json({ documents: server.documents.map(d => ({ ...d })), revision: server.revision });
    if (path === 'status') { const gate = server.status.shift(); if (gate) await gate.promise; return Response.json({ state: 'ready', message: 'Local documents ready.', model: 'all-minilm:22m' }); }
    return Response.json({});
  });
  let result;
  const deleted = [];
  const render = () => { cursor = 0; result = useDocuments(ids => deleted.push(...ids)); while (pending.length) pending.shift()(); return result; };
  return {
    server, calls, deleted, render, get current() { cursor = 0; return (result = useDocuments(ids => deleted.push(...ids))); },
    restoreHooksOnly() { cleanups.forEach(c => c?.()); cleanups.length = 0; },
    restore() { cleanups.forEach(c => c?.()); for (const [k, d] of Object.entries(saved)) d ? Object.defineProperty(globalThis, k, d) : delete globalThis[k]; },
  };
}

test('a refresh asked for after a change returns a list fetched after that change, even while a slow status check is in flight', async () => {
  const f = fixture();
  try {
    const slowStatus = deferred(); f.server.status.push(slowStatus); // Ollama busy: /status can take up to 5 s
    f.render(); await tick();
    assert.deepEqual(f.current.documents, []);
    // An upload (or retry/cancel) finishes on the server while the first status check is still pending.
    f.server.documents = [{ id: 'doc-new', name: 'Notes.md', status: 'queued', message: 'Waiting', progress: 0, pages: 0 }];
    await f.current.refresh(); // DocumentsPanel.action awaits this before re-enabling its buttons
    assert.deepEqual(f.current.documents.map(d => d.id), ['doc-new'], 'the awaited refresh must show the change, not the pre-change list');
    slowStatus.resolve(); await tick();
  } finally { f.restore(); }
});

test('concurrent refreshes coalesce into at most one follow-up list request', async () => {
  const f = fixture();
  try {
    f.render(); await tick();
    const before = f.calls.filter(c => c === 'GET documents').length;
    await Promise.all([f.current.refresh(), f.current.refresh(), f.current.refresh(), f.current.refresh()]);
    const lists = f.calls.filter(c => c === 'GET documents').length - before;
    assert.ok(lists >= 1 && lists <= 2, `expected 1–2 list requests, saw ${lists}`);
  } finally { f.restore(); }
});

test('a document removed on the server is reported once and dropped from the list', async () => {
  const f = fixture();
  try {
    f.server.documents = [{ id: 'doc-a', name: 'A.md', status: 'ready', message: 'Ready', progress: 1, pages: 0 }];
    f.render(); await tick();
    f.server.documents = []; f.server.revision = 2;
    await f.current.refresh(); await f.current.refresh();
    assert.deepEqual(f.deleted, ['doc-a']);
    assert.deepEqual(f.current.documents, []);
  } finally { f.restore(); }
});

test('a citation already deleted on the server is labelled once and never offers to open', async () => {
  const React = await import('react'); const { renderToStaticMarkup } = await import('react-dom/server');
  let component = ts.transpileModule(await readFile(new URL('../components/knowledge/CitationSources.tsx', import.meta.url), 'utf8'), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  component = component.replaceAll('"react/jsx-runtime"', JSON.stringify(import.meta.resolve('react/jsx-runtime'))).replaceAll("'react'", JSON.stringify(import.meta.resolve('react'))).replaceAll("'@/lib/knowledge-types'", JSON.stringify(types));
  const { default: Sources } = await import(dataUrl(component));
  // The saved-chat API replaces a deleted source's name with "Source deleted" and sets deleted.
  const gone = { documentId: 'doc-a', chunkId: 'chunk-a', name: 'Source deleted', page: null, lineStart: 1, lineEnd: 3, quote: 'The launch is Friday.', deleted: true };
  const html = renderToStaticMarkup(React.createElement(Sources, { citations: [gone], deleted: [] }));
  assert.equal(html.match(/Source deleted/g)?.length, 1, html);
  assert.doesNotMatch(html, /Open supporting passage/);
  assert.match(html, /<button[^>]*disabled/);
  // Deleted during this session: the real name stays, with one deleted label.
  const live = { ...gone, name: 'Notes.md', deleted: undefined };
  const later = renderToStaticMarkup(React.createElement(Sources, { citations: [live], deleted: ['doc-a'] }));
  assert.match(later, /Notes\.md · Source deleted/); assert.doesNotMatch(later, /Open supporting passage/);
  const open = renderToStaticMarkup(React.createElement(Sources, { citations: [live], deleted: [] }));
  assert.match(open, /Notes\.md · Lines 1–3 · Open supporting passage/);
});

test('a refresh queued behind an in-flight one sends no request after unmount', async () => {
  const f = fixture();
  try {
    f.render(); await tick();
    let release; const gate = new Promise(r => { release = r; });
    const realFetch = globalThis.fetch;
    const sent = [];
    globalThis.fetch = async (url, options) => { sent.push(String(url)); if (String(url).endsWith('/documents')) await gate; return realFetch(url, options); };
    const first = f.current.refresh(); const queued = f.current.refresh();
    assert.equal(sent.length, 1, 'one list request in flight, one refresh queued');
    f.restoreHooksOnly(); // unmount: effect cleanup only
    release(); await first; await queued; await tick();
    assert.deepEqual(sent.slice(1), [], 'no request after unmount');
  } finally { f.restore(); }
});
