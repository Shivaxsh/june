import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const dataUrl = source => 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
const read = path => readFile(new URL(path, import.meta.url), 'utf8');
const compile = source => ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const libUrl = dataUrl(compile(await read('../lib/integrations.ts')));
const creations = await import(dataUrl(compile(await read('../lib/creations.ts')).replaceAll('"./integrations"', JSON.stringify(libUrl))));
const id = n => String(n).padStart(32, 'a');
const item = (o = {}) => ({ id: id(1), kind: 'pptx', title: 'Solar Power', fileName: 'Solar Power.pptx', createdAt: 5, exists: true, ...o });
const state = (o = {}) => ({ version: 1, serverNow: 9, folder: 'June Documents', creations: [item()], ...o });
function http(replies) {
  const calls = [];
  const fn = async (url, init = {}) => { calls.push({ url, method: init.method ?? 'GET', body: init.body ? JSON.parse(init.body) : undefined }); const next = replies.shift(); return { ok: true, status: 200, json: async () => next.body }; };
  return { fn, calls };
}

test('June’s documents are listed by name only and opened by id', async () => {
  const a = http([{ body: state() }, { body: state() }, { body: state() }]);
  assert.equal((await creations.getCreations(a.fn)).creations[0].fileName, 'Solar Power.pptx');
  await creations.openCreation(id(1), 'open', a.fn); await creations.openCreation(id(1), 'reveal', a.fn);
  assert.deepEqual(a.calls.slice(1).map(c => [c.url, c.body]), [[`/api/creations/${id(1)}/open`, {}], [`/api/creations/${id(1)}/reveal`, {}]]);
  for (const bad of [state({ creations: [item({ fileName: '../x.pptx' })] }), state({ creations: [item({ kind: 'exe' })] }), state({ creations: [item({ id: 'x' })] }), state({ folder: '' }), state({ creations: 'x' })])
    await assert.rejects(creations.getCreations(http([{ body: bad }]).fn));
  await assert.rejects(creations.openCreation('../etc', 'open', http([]).fn), e => e.code === 'invalid-input');
  await assert.rejects(creations.openCreation(id(1), 'delete', http([]).fn), e => e.code === 'invalid-input');
});

test('the panel says what to ask, that files are drafts, and the bridge allows only list, open and reveal', async () => {
  const panel = await read('../components/knowledge/CreationsPanel.tsx');
  assert.match(panel, /create a presentation about solar power/); assert.match(panel, /drafts from June’s local model/); assert.match(panel, /template\.docx/);
  assert.match(panel, />Show in Finder</);
  const bridge = await read('../app/api/creations/[[...path]]/route.ts');
  assert.match(bridge, /\(open\|reveal\)/); assert.doesNotMatch(bridge, /delete|remove/);
  assert.match(await read('../components/Chat.tsx'), /<CreationsPanel refreshKey=\{messages\.length\}/);
});

test('websites June made are listed with their published address, and only a github.io address is accepted', async () => {
  const site = item({ id: id(2), kind: 'site', title: 'Riverside Bakery', fileName: 'riverside-bakery', url: 'https://tester.github.io/riverside-bakery/' });
  const got = (await creations.getCreations(http([{ body: state({ creations: [site, item()] }) }]).fn)).creations;
  assert.deepEqual([got[0].kind, got[0].url, got[1].url], ['site', 'https://tester.github.io/riverside-bakery/', null]);
  assert.equal(creations.KIND_WORDS.site, 'Website');
  for (const url of ['http://tester.github.io/x/', 'https://evil.example/x/', 'javascript:alert(1)', 'https://tester.github.io/../x/', 5])
    await assert.rejects(creations.getCreations(http([{ body: state({ creations: [{ ...site, url }] }) }]).fn), String(url));
  const panel = await read('../components/knowledge/CreationsPanel.tsx');
  assert.match(panel, /publish it/); assert.match(panel, /rel="noreferrer noopener"/); assert.match(panel, /June Websites/);
});

test('each document shows the design June chose, as plain short text', async () => {
  const got = (await creations.getCreations(http([{ body: state({ creations: [item({ design: 'Forest · natural' }), item({ id: id(3) })] }) }]).fn)).creations;
  assert.deepEqual(got.map(c => c.design), ['Forest · natural', null]);
  await assert.rejects(creations.getCreations(http([{ body: state({ creations: [item({ design: 'x'.repeat(81) })] }) }]).fn));
  await assert.rejects(creations.getCreations(http([{ body: state({ creations: [item({ design: 5 })] }) }]).fn));
  const panel = await read('../components/knowledge/CreationsPanel.tsx');
  assert.match(panel, /item\.design/); assert.match(panel, /make it in a different style/);
});
