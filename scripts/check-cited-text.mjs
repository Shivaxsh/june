// Run with node --test scripts/check-cited-text.mjs.
// Execute the real local renderer without mounting voice or the whole chat page.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import ts from 'typescript';

const source = await readFile(new URL('../components/Chat.tsx', import.meta.url), 'utf8');
const ast = ts.createSourceFile('Chat.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let renderer;
function visit(node) {
  if (ts.isFunctionDeclaration(node) && node.name?.text === 'citedText') renderer = node.getText(ast);
  ts.forEachChild(node, visit);
}
visit(ast);
assert.ok(renderer, 'Chat must provide its citation renderer');
const require = createRequire(import.meta.url);
const { outputText } = ts.transpileModule(
  `import React from ${JSON.stringify(pathToFileURL(require.resolve('react')).href)}; export ${renderer}`,
  { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.React } },
);
const { citedText } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'));
const marks = (content, quotes) => {
  const result = citedText(content, quotes.map(quote => ({ quote })));
  return typeof result === 'string' ? [] : result.filter(part => typeof part !== 'string').map(part => part.props.children[0]);
};

test('a partial numeric identifier never receives another values citation', () => {
  assert.deepEqual(marks('The value is 100', ['The value is 1000.']), []);
  assert.deepEqual(marks('Model 5070 is available', ['Model 5070Ti is available']), []);
  assert.deepEqual(marks('Model RTX5070 is available', ['Model XRTX5070 is available']), []);
  assert.deepEqual(marks('The value is 100', ['Budget 100.5 GB']), []);
  assert.deepEqual(marks('The value is 100', ['Ratio 0.100']), []);
  assert.deepEqual(marks('Version 2.5', ['Version 12.5 or 2.50']), []);
});

test('whole identifiers and units match case-insensitively beside punctuation', () => {
  assert.deepEqual(marks('Value 100, and 16 GB of VRAM', ['(100), with 16 gb of VRAM.']), ['100', '16 GB']);
  assert.deepEqual(marks('Choose RTX5070 or 5070 Ti', ['RTX5070 and 5070 Ti.']), ['RTX5070', '5070 Ti']);
});

test('uncited text and content without evidence remain intact', () => {
  assert.equal(citedText('No citations here.', []), 'No citations here.');
  assert.equal(citedText('The value is 1000.', [{ quote: '100' }]), 'The value is 1000.');
});

test('sentence-final punctuation stays outside marks and decimal identifiers stay whole', () => {
  const result = citedText('The value is 100. Version 2.5.', [{ quote: '(100), version 2.5 is current.' }]);
  assert.deepEqual(marks('The value is 100. Version 2.5.', ['(100), version 2.5 is current.']), ['100', '2.5']);
  assert.equal(result.at(-1), '.');
  assert.equal(result[2], '. Version ');
});
