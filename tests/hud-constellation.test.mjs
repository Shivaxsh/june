import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const source = await readFile(new URL('../lib/hud/constellation.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
const { buildConstellation, NODE_CAP, trimLabel } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'));

const make = (docs, mems, chats, links = null) => ({
  documents: Array.from({ length: docs }, (_, i) => ({ id: `d${i}`, name: `Document number ${i} with a long name`, status: i % 7 === 6 ? 'processing' : 'ready' })),
  memories: Array.from({ length: mems }, (_, i) => ({ id: `m${i}`, source: i % 2 ? `c${i}` : null })),
  conversations: Array.from({ length: chats }, (_, i) => ({ id: `c${i}`, title: `Chat ${i}` })),
  links,
});

test('layout is deterministic and finite for the same input', () => {
  const input = make(6, 5, 8, { citations: [{ conversation: 'c1', documentId: 'd0' }], memories: [{ id: 'm1', source: 'c1' }] });
  const a = buildConstellation(input, 60), b = buildConstellation(input, 60);
  assert.deepEqual(a, b);
  assert.ok(a.nodes.every(n => Number.isFinite(n.x) && Number.isFinite(n.y)));
  assert.ok(a.nodes.every(n => !('text' in n)), 'nodes carry ids and short labels only');
});

test('only ready documents are drawn and labels are trimmed', () => {
  const graph = buildConstellation(make(7, 0, 0), 1);
  assert.equal(graph.counts.documents, 6);
  assert.equal(graph.totals.documents, 6);
  assert.ok(graph.nodes.every(n => n.label.length <= 18));
  assert.equal(trimLabel('  a   b  '), 'a b');
});

test('more than the cap of memories and chats is bounded, and counts report shown versus total', () => {
  const graph = buildConstellation(make(0, NODE_CAP + 25, NODE_CAP + 40), 1);
  assert.equal(graph.counts.memories, NODE_CAP);
  assert.equal(graph.counts.chats, NODE_CAP);
  assert.equal(graph.totals.memories, NODE_CAP + 25);
  assert.equal(graph.totals.chats, NODE_CAP + 40);
  assert.equal(graph.nodes.length, NODE_CAP * 2);
});

test('links to omitted or missing nodes produce no edges, and duplicates collapse', () => {
  const omitted = `c${NODE_CAP + 5}`;
  const links = {
    citations: [
      { conversation: 'c1', documentId: 'd0' }, { conversation: 'c1', documentId: 'd0' },
      { conversation: omitted, documentId: 'd0' }, { conversation: 'c2', documentId: 'gone' },
    ],
    memories: [{ id: 'm1', source: 'c1' }, { id: 'm3', source: omitted }, { id: 'missing', source: 'c1' }],
  };
  const graph = buildConstellation(make(2, 4, NODE_CAP + 10, links), 1);
  assert.equal(graph.edges.filter(e => e.type === 'cite').length, 1);
  assert.equal(graph.edges.filter(e => e.type === 'mem').length, 1);
  assert.equal(graph.counts.citations, 1);
  assert.equal(graph.totals.citations, 4);
  for (const e of graph.edges) assert.ok(graph.nodes[e.a] && graph.nodes[e.b]);
});
