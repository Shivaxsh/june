import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../lib/memory-types.ts',import.meta.url),'utf8');
const {outputText}=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}});
const {expressionRates,characterFields}=await import('data:text/javascript;base64,'+Buffer.from(outputText).toString('base64'));
test('character matches all ten workshop keys and expression rates stay modest',()=>{
 assert.deepEqual(characterFields,['who','values','speech','humour','quirks','taste','never','address','mood','growth']);
 assert.deepEqual(expressionRates,{steady:.98,calm:.92,bright:1.04});
});
