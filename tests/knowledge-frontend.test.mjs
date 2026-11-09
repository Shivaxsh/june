import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import ts from 'typescript';
const compile=source=>'data:text/javascript;base64,'+Buffer.from(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText).toString('base64');
const read=path=>readFile(new URL(path,import.meta.url),'utf8');
const types=await import(compile(await read('../lib/knowledge-types.ts')));
const backend=compile(await read('../lib/server/backend.ts'));
const {proxyKnowledge}=await import(compile((await read('../lib/server/knowledge.ts')).replace('"./backend"',JSON.stringify(backend))));
const citation={documentId:'doc-a',chunkId:'chunk-a',name:'Notes.md',page:null,lineStart:1,lineEnd:3,quote:'The launch is Friday.'};
const scope={documentIds:['doc-a']};
const done={citations:[citation],knowledgeRevision:2};

test('document completion requires valid scoped citations and revision',()=>{
  assert.deepEqual(types.validatedDocumentReply('The launch is Friday.',done,scope),[citation]);
  for(const invalid of [{...done,knowledgeRevision:undefined},{...done,knowledgeRevision:-1},{...done,citations:undefined},{...done,memoryIds:['personal-fact']},{...done,citations:[{...citation,documentId:'outside-scope'}]},{...done,citations:[{...citation,quote:''}]},{...done,citations:[{...citation,lineEnd:0}]}]){
    assert.throws(()=>types.validatedDocumentReply('Answer.',invalid,scope));
  }
});
test('raw structured model output cannot pass the document playback gate',()=>{
  for(const raw of ['{"answer":"Friday","citations":[]}','["answer"]','```json\n{}\n```',''])assert.throws(()=>types.validatedDocumentReply(raw,done,scope));
  assert.deepEqual(types.validatedDocumentReply('The selected documents do not support an answer.',{citations:[],knowledgeRevision:2},scope),[]);
});
test('scope and citation persistence accept JSON and parsed values safely',()=>{
  assert.deepEqual(types.parseScope(JSON.stringify(scope)),scope);
  assert.deepEqual(types.parseScope(scope),scope);
  for(const value of ['{',{},null,{documentIds:[]},{documentIds:[3]}])assert.equal(types.parseScope(value),null);
  assert.deepEqual(types.validateCitations(types.parseStored(JSON.stringify([citation]),[])),[citation]);
});
test('automatic replies require provenance consistent with their citations',()=>{
  const auto={mode:'auto'};
  assert.deepEqual(types.parseScope(JSON.stringify(auto)),auto);
  assert.deepEqual(types.validatedDocumentReply('General knowledge\nVRAM holds textures.',{...done,citations:[],provenance:'general'},auto),[]);
  assert.deepEqual(types.validatedDocumentReply('From your documents\nFriday.',{...done,provenance:'documents'},auto),[citation]);
  assert.throws(()=>types.validatedDocumentReply('Unlabeled reply.',done,auto));
  assert.throws(()=>types.validatedDocumentReply('From your documents\nFriday.',{...done,citations:[],provenance:'mixed'},auto));
  assert.throws(()=>types.validatedDocumentReply('General knowledge\nFriday.',{...done,provenance:'general'},auto));
});
test('citation preview resolves the exact supporting passage and rejects stale or mismatched sources',()=>{
  const passage={id:'chunk-a',text:'Notes. The launch is Friday. More context.',page:null,lineStart:1,lineEnd:3};
  assert.equal(types.supportingPassage({id:'doc-a',passages:[passage]},citation),passage);
  for(const doc of [{id:'doc-b',passages:[passage]},{id:'doc-a',passages:[]},{id:'doc-a',passages:[{...passage,text:'Different content'}]}])assert.throws(()=>types.supportingPassage(doc,citation));
});
const request=(options={})=>new Request('http://127.0.0.1:3000/api/knowledge/documents',{method:'POST',headers:{Host:'127.0.0.1:3000',Origin:'http://127.0.0.1:3000','Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent('Résumé.pdf'),...options.headers},body:options.body??new Uint8Array([0,255,128,10])});
test('knowledge proxy rejects foreign origin, invalid upload metadata and oversized bytes',async()=>{
  assert.equal((await proxyKnowledge(request({headers:{Origin:'https://example.com'}}),'documents')).status,403);
  assert.equal((await proxyKnowledge(request({headers:{'Content-Type':'application/json'}}),'documents')).status,415);
  assert.equal((await proxyKnowledge(request({headers:{'X-File-Name':'%invalid'}}),'documents')).status,400);
  assert.equal((await proxyKnowledge(request({body:new Uint8Array(types.DOCUMENT_LIMIT+1)}),'documents')).status,413);
  assert.equal((await proxyKnowledge(request({headers:{'Content-Length':String(types.DOCUMENT_LIMIT+1)}}),'documents')).status,413);
});
test('binary proxy preserves bytes, encoded filename, method and backend error response',async()=>{
  let captured;
  const server=createServer(async(req,res)=>{const parts=[];for await(const part of req)parts.push(part);captured={method:req.method,url:req.url,name:req.headers['x-file-name'],type:req.headers['content-type'],body:Buffer.concat(parts)};res.writeHead(422,{'Content-Type':'application/json'});res.end('{"message":"Malformed PDF."}');});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const before=process.env.JUNE_BACKEND_URL;process.env.JUNE_BACKEND_URL='http://127.0.0.1:'+server.address().port;
  try{const result=await proxyKnowledge(request(),'documents');assert.equal(result.status,422);assert.deepEqual(await result.json(),{message:'Malformed PDF.'});assert.deepEqual(captured.body,Buffer.from([0,255,128,10]));assert.equal(captured.name,encodeURIComponent('Résumé.pdf'));assert.equal(captured.type,'application/octet-stream');assert.equal(captured.url,'/api/knowledge/documents');assert.equal(captured.method,'POST');}
  finally{if(before===undefined)delete process.env.JUNE_BACKEND_URL;else process.env.JUNE_BACKEND_URL=before;server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
});
test('all typed/native sends use the shared scope and document streaming remains gated',async()=>{
  const chat=await read('../components/Chat.tsx');
  assert.match(chat,/transcript:.*send\(\{ content, voiceTurn: turn \}\)/);
  assert.match(chat,/scope\?\{knowledge:scope\}/);
  assert.match(chat,/if \(!scope\) \{voice.push\(id, event.text\);update\("pending"\);\}/);
  assert.match(chat,/if\(scope\) citations=validatedDocumentReply\(reply,event,scope\)/);
  assert.match(chat,/if\(!scope && !repetitionStopped && mode/);
});
test('citations render source buttons with provenance and disable deleted sources',async()=>{
  const React=await import('react');const {renderToStaticMarkup}=await import('react-dom/server');
  let component=ts.transpileModule(await read('../components/knowledge/CitationSources.tsx'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX}}).outputText;
  component=component.replaceAll('"react/jsx-runtime"',JSON.stringify(import.meta.resolve('react/jsx-runtime'))).replaceAll("'react'",JSON.stringify(import.meta.resolve('react'))).replaceAll("'@/lib/knowledge-types'",JSON.stringify(compile(await read('../lib/knowledge-types.ts'))));
  const {default:Sources}=await import('data:text/javascript;base64,'+Buffer.from(component).toString('base64'));
  const html=renderToStaticMarkup(React.createElement(Sources,{citations:[citation],deleted:[]}));
  assert.match(html,/<button[^>]*>Notes.md/);assert.match(html,/Lines 1–3/);assert.match(html,/Open supporting passage/);
  const deleted=renderToStaticMarkup(React.createElement(Sources,{citations:[citation],deleted:['doc-a']}));
  assert.match(deleted,/<button[^>]*disabled/);assert.match(deleted,/Source deleted/);
});
