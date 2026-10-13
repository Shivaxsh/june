import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
async function moduleUrl(url) {
 let {outputText}=ts.transpileModule(await readFile(url,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}});
 for(const match of [...outputText.matchAll(/from ["'](\.[^"']+)["']/g)])outputText=outputText.replace(match[0],`from ${JSON.stringify(await moduleUrl(new URL(match[1]+'.ts',url)))}`);
 return 'data:text/javascript;base64,'+Buffer.from(outputText).toString('base64');
}
const {getModelStatus,getAdapter}=await import(await moduleUrl(new URL('../lib/server/model.ts',import.meta.url)));
test('default configuration is ready when only the selected replacement model is installed',async()=>{
 const old=process.env.JUNE_MODEL,original=globalThis.fetch; delete process.env.JUNE_MODEL;
 globalThis.fetch=async()=>Response.json({models:[{name:'qwen2.5:1.5b'}]});
 try {const result=await getModelStatus();assert.equal(result.state,'ready');assert.equal(result.model,'qwen2.5:1.5b');}
 finally {globalThis.fetch=original;if(old===undefined)delete process.env.JUNE_MODEL;else process.env.JUNE_MODEL=old;}
});
test('local adapter keeps follow-up context and uses conservative answer settings',async()=>{
 const old=process.env.JUNE_MODEL,original=globalThis.fetch;process.env.JUNE_MODEL='qwen2.5:1.5b';let request;
 const messages=[{role:'user',content:'Name a country in Europe.'},{role:'assistant',content:'France.'},{role:'user',content:'What is its capital?'}];
 globalThis.fetch=async(_url,options)=>{request=JSON.parse(options.body);return new Response('{"message":{"content":"Paris."}}\n{"done":true}\n');};
 try {
  const events=[];for await(const event of getAdapter('local').stream(messages,new AbortController().signal))events.push(event);
  assert.equal(request.model,'qwen2.5:1.5b');assert.equal(request.options.temperature,.1);assert.equal(request.options.num_ctx,4096);assert.equal(request.think,false);
  assert.equal(request.messages[0].role,'system');assert.deepEqual(request.messages.slice(1),messages);assert.deepEqual(events,[{type:'delta',text:'Paris.'},{type:'done',model:'qwen2.5:1.5b'}]);
 }finally{globalThis.fetch=original;if(old===undefined)delete process.env.JUNE_MODEL;else process.env.JUNE_MODEL=old;}
});
