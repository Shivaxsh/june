import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
async function load(url) {
  const source=await readFile(url,'utf8');
  let { outputText }=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}});
  for(const match of [...outputText.matchAll(/from ["'](\.[^"']+)["']/g)]) outputText=outputText.replace(match[0],`from ${JSON.stringify(await load(new URL(match[1]+'.ts',url)))}`);
  return 'data:text/javascript;base64,'+Buffer.from(outputText).toString('base64');
}
const { prepareContext }=await import(await load(new URL('../lib/context.ts',import.meta.url)));
const pair=n=>[{role:'user',content:`Question ${n}`},{role:'assistant',content:`Reply ${n}`}];

test('long conversations retain recent whole pairs without exceeding the server contract',()=>{
  const history=Array.from({length:25},(_,i)=>pair(i)).flat();
  const result=prepareContext(history,{role:'user',content:'Current question'});
  assert.equal(result.messages.length,19);assert.equal(result.messages.at(-1).content,'Current question');
  assert.equal(result.messages[0].content,'Question 16');assert.equal(result.limited,true);
  assert.ok(result.messages.every((m,i)=>m.role===(i%2===0?'user':'assistant')));
});
test('character budget accounts for UTF16 and never shortens the current question',()=>{
  const history=Array.from({length:6},()=>[{role:'user',content:'a'.repeat(1700)},{role:'assistant',content:'b'.repeat(1700)}]).flat();
  const current={role:'user',content:'🙂'.repeat(1000)};
  const result=prepareContext(history,current);
  assert.ok(result.messages.reduce((n,m)=>n+m.content.length,0)<=6000);
  assert.equal(result.messages.at(-1).content,current.content);assert.equal(result.limited,true);
});
test('an oversized historical model reply is shortened only in context and input objects remain unchanged',()=>{
  const history=[{role:'user',content:'Explain'},{role:'assistant',content:'x'.repeat(2300)}];
  const result=prepareContext(history,{role:'user',content:'Continue'});
  assert.ok(result.messages[1].content.length<=2000);assert.equal(history[1].content.length,2300);assert.equal(result.limited,true);
});
test('short conversations preserve every message without showing a limit notice',()=>{
  const history=pair(1),current={role:'user',content:'Follow up'};
  const result=prepareContext(history,current);
  assert.deepEqual(result.messages,[...history,current]);assert.equal(result.limited,false);
});
test('shortening an old reply never splits a surrogate pair',()=>{
  const history=[{role:'user',content:'Explain'},{role:'assistant',content:'A'+'🙂'.repeat(1001)}];
  const result=prepareContext(history,{role:'user',content:'Continue'});
  assert.equal(result.messages[1].content.isWellFormed(),true);
});
test('context budgets stay valid across varied histories and Unicode message sizes',()=>{
  for(const turns of [0,1,9,10,25,100]) for(const width of [1,99,500,1000,1999,2000,2301]) {
    const history=Array.from({length:turns},(_,i)=>[
      {role:'user',content:'q'.repeat(Math.min(width,2000))},
      {role:'assistant',content:('🙂'+String(i)).repeat(width).slice(0,width).toWellFormed()},
    ]).flat();
    const current={role:'user',content:'Current — 🙂'};
    const result=prepareContext(history,current);
    assert.ok(result.messages.length<=20);
    assert.ok(result.messages.reduce((sum,m)=>sum+m.content.length,0)<=6000);
    assert.ok(result.messages.every((m,i)=>m.content.length<=2000 && m.content.isWellFormed() && m.role===(i%2?'assistant':'user')));
    assert.deepEqual(result.messages.at(-1),current);
  }
});
