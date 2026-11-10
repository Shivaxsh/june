import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../lib/conversation-open.ts',import.meta.url),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText;
const {openLatestConversation}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const saved={id:'old',knowledge:{documentIds:['old-source']},turns:[]};
for(const transition of ['new chat','mode change','document sources','General chat']){
  test(`late saved chat cannot override ${transition} or clear its newer draft`,async()=>{
    const generation={current:0};const response=deferred();
    let view={id:'initial',knowledge:null,draft:''};let notices=[];
    const opening=openLatestConversation(generation,()=>response.promise,chat=>{
      view={id:chat.id,knowledge:chat.knowledge,draft:''};notices.push('opened');
    },error=>notices.push(error.message));
    // These transitions use Chat.newChat, which invalidates synchronously.
    generation.current++;
    view={id:null,knowledge:transition==='document sources'?{documentIds:['new-source']}:null,draft:'Keep this newer draft'};
    const expected=structuredClone(view);
    response.resolve(saved);await opening;
    assert.deepEqual(view,expected);assert.deepEqual(notices,[]);
  });
}
test('second open wins even when first response arrives last',async()=>{
  const generation={current:0};const a=deferred(),b=deferred();const opened=[];
  const first=openLatestConversation(generation,()=>a.promise,chat=>opened.push(chat.id),assert.fail);
  const second=openLatestConversation(generation,()=>b.promise,chat=>opened.push(chat.id),assert.fail);
  b.resolve({...saved,id:'newer'});await second;
  a.resolve(saved);await first;
  assert.deepEqual(opened,['newer']);
});
test('obsolete rejection is ignored while a current request can open or report failure',async()=>{
  const generation={current:0};const late=deferred();const errors=[];const opened=[];
  const pending=openLatestConversation(generation,()=>late.promise,chat=>opened.push(chat.id),e=>errors.push(e.message));
  generation.current++;late.reject(new Error('obsolete failure'));await pending;
  assert.deepEqual(errors,[]);
  await openLatestConversation(generation,async()=>saved,(chat,token)=>{assert.equal(token,generation.current);opened.push(chat.id);},assert.fail);
  await openLatestConversation(generation,async()=>{throw new Error('current failure');},assert.fail,e=>errors.push(e.message));
  assert.deepEqual(opened,['old']);assert.deepEqual(errors,['current failure']);
});
test('Chat and LibraryPanel share synchronous invalidation and check before applying fetched data',async()=>{
  const chat=await readFile(new URL('../components/Chat.tsx',import.meta.url),'utf8');
  const panel=await readFile(new URL('../components/memory/LibraryPanel.tsx',import.meta.url),'utf8');
  assert.match(chat,/function newChat\(\) \{\s*conversationOpenGeneration.current\+\+/);
  assert.match(chat,/function openConversation\(chat:SavedConversation,token:number\) \{\s*if\(token!==conversationOpenGeneration.current\)return;/);
  assert.match(chat,/openGeneration=\{conversationOpenGeneration\}/);
  assert.match(chat,/onClick=\{\(\) => newChat\(\)\}>New chat/);
  assert.match(chat,/onDeleteActive=\{\(\)=>newChat\(\)\}/);
  assert.match(panel,/openLatestConversation\(openGeneration/);
  assert.match(panel,/onClick=\{\(\)=>openSavedChat\(c.id\)\}/);
  assert.match(panel,/useEffect\(\(\)=>\(\)=>\{openGeneration.current\+\+;/);
});
