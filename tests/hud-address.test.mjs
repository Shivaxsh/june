import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
const source = await readFile(new URL('../lib/hud/address.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } });
const { displayAddress } = await import('data:text/javascript;base64,' + Buffer.from(outputText).toString('base64'));

test('a short form of address is shown as written', () => {
  assert.equal(displayAddress('sir'), 'sir');
  assert.equal(displayAddress('  Dr. '), '');
  assert.equal(displayAddress('“Captain”'), 'Captain');
  assert.equal(displayAddress('Ms Rao'), 'Ms Rao');
});

test('instructions, sentences and long text are never shown as an address', () => {
  for (const value of [
    'Use sir only occasionally, otherwise my name',
    'Call me boss',
    'never use honorifics',
    'sir (sometimes)',
    'A very long description of how June should address me',
    'one two three four',
    '', null, undefined,
  ]) assert.equal(displayAddress(value), '', String(value));
});
