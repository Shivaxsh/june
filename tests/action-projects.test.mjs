import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
const source=await readFile(new URL('../lib/actions.ts',import.meta.url),'utf8');
const A=await import('data:text/javascript;base64,'+Buffer.from(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText).toString('base64'));
const record={id:'action-12345678',action:'open-project',projectId:'project-12345678',projectPath:'/Users/example/June',label:'Open June project',detail:'Open this saved folder.',fingerprint:'fingerprint-12345678',createdAt:1000,expiresAt:301000,status:'proposed'};
test('project cards require the exact registered id and folder; no executable fields',()=>{
 assert.deepEqual(A.parseAction(record),record);
 for(const extra of [{projectId:undefined},{projectPath:'relative'},{projectPath:undefined},{args:['bad']}])assert.equal(A.parseAction({...record,...extra}),null);
});
test('project state preserves folder and per-project remembered setting',()=>{
 const projects=[{id:'project-12345678',name:'June',folderPath:'/Users/example/June',remembered:true}];
 const state=A.parseState({serverNow:1000,actions:[record],available:true,projects});
 assert.deepEqual(state.projects,projects);
});
test('project propose sends only an id; run retries the identical request',async()=>{
 const calls=[];const http=async(url,init)=>{calls.push([url,JSON.parse(init.body)]);if(calls.length===2)throw new TypeError('lost');return {ok:true,status:200,json:async()=>({serverNow:1000,action:record})};};
 await A.proposeProject('project-12345678',http);
 await A.runProject('project-12345678',http,()=> 'request-12345678');
 assert.deepEqual(calls[0],['/api/actions/propose',{action:'open-project',projectId:'project-12345678'}]);
 assert.deepEqual(calls[1],calls[2]);assert.equal('path' in calls[1][1],false);
});
test('project outcome never upgrades app observation into verified folder contents',()=>{
 assert.match(A.statusText({...record,status:'completed',result:{state:'active',message:'macOS accepted the folder request; VS Code is in front.'}}),/accepted the folder request/);
});
