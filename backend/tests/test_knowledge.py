"""Isolated Phase 7 storage, subprocess, lifecycle and grounded-answer failures."""
import asyncio
from contextlib import aclosing
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import httpx
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
from june.errors import JuneError
from june.memory import Store
from june.memory_service import Coordinator,persisted_chat,extract
from june.knowledge import Knowledge,passages,MAX_UPLOAD
from june.knowledge_chat import validate_answer,UNSUPPORTED,resolve_citations,answer_schema


class SourceLabels(unittest.TestCase):
    def test_schema_quotes_are_exact_source_text_not_retyped_paraphrases(self):
        source={'text':'The workshop opens at 09:40.\nIt closes at 17:20.'}
        schema=answer_schema([source]);choice=schema['properties']['citations']['items']['anyOf'][0]
        self.assertEqual(choice['properties']['chunkId']['enum'],['S1'])
        self.assertTrue(all(quote in source['text'] for quote in choice['properties']['quote']['enum']))
        self.assertNotIn('The workshop opens at 09:40. It closes at 17:20.',choice['properties']['quote']['enum'])

    def test_short_labels_resolve_without_guessing_mistyped_ids(self):
        sources=[{'id':'3bff0028-f7b6-49cd-8011-988633f275ac'}]
        value={'supported':True,'answer':'KS-047-B','citations':[{'chunkId':'S1','quote':'KS-047-B'}]}
        self.assertEqual(resolve_citations(value,sources)['citations'][0]['chunkId'],sources[0]['id'])
        self.assertEqual(value['citations'][0]['chunkId'],'S1')
        for bad in ['S2','S01','3bff0028-f7b6-49cd-8011-988630f275ac']:
            wrong={**value,'citations':[{'chunkId':bad,'quote':'KS-047-B'}]}
            self.assertIsNone(resolve_citations(wrong,sources))


def pdf(text=True,blank=False,encrypted=False,pages=1):
    writer=PdfWriter()
    for _ in range(pages):writer.add_blank_page(width=300,height=300)
    if text:
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 10 100 Td (June launches on Monday.) Tj ET')
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        writer.pages[0][NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        writer.pages[0][NameObject('/Contents')]=writer._add_object(stream)
    if blank:writer.add_blank_page(width=300,height=300)
    if encrypted:writer.encrypt('secret')
    output=io.BytesIO();writer.write(output);return output.getvalue()


class KnowledgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_outage_is_failed_not_an_evidence_missing_answer(self):
        from unittest.mock import AsyncMock
        did=await self.ready()
        with patch('june.knowledge_chat.bounded_json',new=AsyncMock(side_effect=httpx.ConnectError('offline'))):
            with self.assertRaises(JuneError) as result:
                await self.events(did)
        self.assertEqual(result.exception.status,503)

    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.store=Store(self.root/'data');self.coordinator=Coordinator();self.calls=[];self.answer=None
        self.settings=SimpleNamespace(ollama='http://127.0.0.1:11434',model='qwen2.5:1.5b')
        self.block=False;self.listen=False
        async def handler(request):
            value=json.loads(request.content) if request.content else {};self.calls.append((request.url.path,value))
            if request.url.path=='/api/embed':
                if self.block:await asyncio.sleep(60)
                if len(value['input'][0])>250:
                    return httpx.Response(400,json={'error':'input exceeds context length'})
                return httpx.Response(200,json={'embeddings':[[1.,.1,.2]]})
            if request.url.path=='/api/chat':
                evidence=json.loads(value['messages'][-1]['content'])['evidence']
                result=self.answer if self.answer is not None else {'supported':True,'answer':'June launches on Monday.','citations':[{'chunkId':evidence[0]['chunkId'],'quote':'June launches on Monday.'}]}
                return httpx.Response(200,json={'message':{'content':json.dumps(result)}})
            return httpx.Response(200,json={'models':[{'name':'all-minilm:22m'}]})
        self.client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.service=Knowledge(self.store,self.client,self.settings,self.coordinator,busy=lambda:self.listen)

    async def asyncTearDown(self):
        await self.service.close();await self.client.aclose();self.tmp.cleanup()

    async def ready(self,text=b'June launches on Monday.',name='notes.md'):
        doc=self.service.upload(name,text)
        task=self.service.jobs.get(doc['id'])
        if task:await task
        self.assertEqual(self.service.db.get(doc['id'])['status'],'ready',self.service.db.get(doc['id']))
        return doc['id']

    async def events(self,did,**extra):
        value={'knowledge':{'documentIds':[did]},**extra}
        return [e async for e in persisted_chat(self.client,self.settings,self.store,self.coordinator,value,'local',[{'role':'user','content':'When does June launch?'}],self.service)]

    async def test_migration_backup_private_and_restart(self):
        backup=self.store.directory/'june.pre-phase7.sqlite3'
        with sqlite3.connect(backup) as db:self.assertEqual(db.execute('pragma user_version').fetchone()[0],1)
        self.assertEqual(os.stat(backup).st_mode&0o777,0o600)
        with self.store.db() as db:self.assertEqual(db.execute('pragma user_version').fetchone()[0],2)
        did=await self.ready()
        reopened=Store(self.store.directory)
        self.assertEqual(reopened.revision(),0)
        self.assertEqual(self.service.db.get(did)['status'],'ready')
        self.assertEqual(os.stat(self.service.db.directory/did).st_mode&0o777,0o600)
        self.assertEqual(os.stat(self.service.db.directory).st_mode&0o777,0o700)

    async def test_bad_files_limits_and_dedup(self):
        for name,data in [('x.doc',b'a'),('x.txt',b'\xff'),('x.md',b'\0'),('x.pdf',b'fake'),('../x.txt',b'a'),('x.txt',b' '),('x.txt',b'a'*(MAX_UPLOAD+1))]:
            with self.assertRaises(JuneError):self.service.upload(name,data)
        did=await self.ready()
        self.assertEqual(self.service.upload('renamed.txt',b'June launches on Monday.')['id'],did)
        with self.assertRaises(JuneError):self.service.db.select([])
        with self.assertRaises(JuneError):self.service.db.select([did,did])
        with self.assertRaises(JuneError):self.service.db.select(['missing'])

    async def test_pdf_real_macos_worker_partial_encrypted_malformed_page_limit(self):
        did=await self.ready(pdf(blank=True),'partial.pdf')
        meta=self.service.db.get(did,True)
        self.assertEqual(meta['pages'],2);self.assertIn('2',meta['warning'])
        self.assertEqual(meta['passages'][0]['page'],1)
        for data in (pdf(text=False),pdf(encrypted=True),b'%PDF- broken',pdf(pages=201)):
            doc=self.service.upload('bad.pdf',data)
            task=self.service.jobs.get(doc['id'])
            if task:await task
            self.assertEqual(self.service.db.get(doc['id'])['status'],'failed')
            self.assertEqual(self.service.db.get(doc['id'],True)['passages'],[])

    async def test_chunk_overlap_and_recursive_provenance(self):
        text=('June launches on Monday.\n'*35)
        chunks=passages([{'page':3,'text':text}])
        self.assertEqual(chunks[0]['text'][-100:],chunks[1]['text'][:100])
        self.assertTrue(all(len(c['text'])<=600 and c['page']==3 for c in chunks))
        did=await self.ready(text.encode())
        stored=self.service.db.get(did,True)['passages']
        self.assertTrue(all(len(c['text'])<=250 for c in stored))
        self.assertTrue(all(c['lineEnd']>=c['lineStart'] for c in stored))
        await self.service.search('When does June launch? '*35,[did])
        for path,payload in self.calls:
            if path=='/api/embed':
                self.assertIs(payload['truncate'],False);self.assertEqual(payload['keep_alive'],'15m')

    async def test_index_pauses_while_listening_and_cancel_has_no_stale_writes(self):
        self.listen=True
        doc=self.service.upload('pause.txt',b'June launches on Monday.')
        await asyncio.sleep(.15)
        self.assertEqual(self.calls,[])
        await self.service.stop(doc['id']);self.listen=False
        token=self.service.db.own(doc['id'])
        await self.service.stop(doc['id'])
        self.assertFalse(self.service.db.update(doc['id'],token,status='ready'))
        self.assertFalse(self.service.db.publish(doc['id'],token,[],1,''))
        self.assertEqual(self.service.db.get(doc['id'],True)['passages'],[])
        await self.service.retry(doc['id'])
        await self.service.jobs[doc['id']]
        self.assertEqual(self.service.db.get(doc['id'])['status'],'ready')

    async def test_restart_requires_explicit_retry_and_preserves_unknown_files(self):
        from june.knowledge_store import KnowledgeStore
        self.listen=True;doc=self.service.upload('waiting.txt',b'June launches on Monday.')
        await self.service.stop(doc['id'])
        self.service.db.own(doc['id'])
        unknown=self.service.db.directory/'keep-me.txt';unknown.write_text('unowned')
        restarted=KnowledgeStore(self.store)
        self.assertEqual(restarted.get(doc['id'])['status'],'interrupted')
        self.assertTrue(unknown.exists());self.assertTrue((restarted.directory/doc['id']).exists())

    async def test_grounded_answer_saved_restored_without_memory(self):
        did=await self.ready();self.store.add_memory('My name is PrivateName.')
        cid=self.store.create_conversation()['id']
        events=await self.events(did,conversationId=cid,turnId='t1')
        self.assertEqual([e['type'] for e in events],['stage','stage','delta','done'])
        self.assertEqual(events[-1]['memoryIds'],[])
        self.assertEqual(events[-1]['citations'][0]['quote'],'June launches on Monday.')
        chat=self.store.conversation(cid)
        self.assertEqual(chat['knowledge'],{'documentIds':[did]})
        self.assertEqual(chat['turns'][0]['citations'],events[-1]['citations'])
        self.assertEqual(self.store.snapshot()['suggestions'],[])
        await extract(self.client,self.settings,self.store,self.coordinator,cid,'t1')
        self.assertEqual(self.store.snapshot()['suggestions'],[])
        model_payload=[p for path,p in self.calls if path=='/api/chat'][0]
        self.assertNotIn('PrivateName',json.dumps(model_payload))
        self.assertEqual(self.store.export(True)['conversations'],[])
        with self.assertRaises(JuneError):self.store.context(cid)

    async def test_invalid_quotes_or_ids_never_emit_raw_json_or_fallback(self):
        did=await self.ready()
        for value in ({'supported':True,'answer':'UNSAFE','citations':[{'chunkId':'fake','quote':'Monday'}]},
                      {'supported':True,'answer':'UNSAFE','citations':[]}, {'supported':False,'answer':'UNSAFE','citations':[]}):
            self.answer=value;events=await self.events(did)
            self.assertEqual(events[-2]['text'],UNSUPPORTED)
            self.assertEqual(events[-1]['citations'],[])
            self.assertNotIn('UNSAFE',str(events))
        source={'id':'x','document':'d','name':'n','page':None,'lineStart':1,'lineEnd':1,'text':'Monday'}
        answer,citations=validate_answer({'supported':True,'answer':'unsafe','citations':[{'chunkId':'x','quote':'Tuesday'}]},[source])
        self.assertEqual((answer,citations),(UNSUPPORTED,[]))

    async def test_scope_change_and_delete_reset_context_keep_historical_label(self):
        did=await self.ready();cid=self.store.create_conversation()['id']
        await self.events(did,conversationId=cid,turnId='t1')
        other=await self.ready(b'Another document.','other.txt')
        with self.assertRaises(JuneError):await self.events(other,conversationId=cid,turnId='t2')
        revision=self.store.revision()
        await self.service.stop(did,delete=True)
        self.assertGreater(self.store.revision(),revision)
        self.assertFalse((self.service.db.directory/did).exists())
        old=self.store.conversation(cid)['turns'][0]
        self.assertEqual(old['assistant'],'June launches on Monday.')
        self.assertEqual(old['citations'][0]['name'],'Source deleted')
        with self.store.db() as db:
            self.assertEqual(db.execute('select count(*) from passage_fts where text like ?',('%Monday%',)).fetchone()[0],0)
        with self.assertRaises(JuneError):await self.events(did,conversationId=cid,turnId='t3')

    async def test_failed_embedding_never_ready_and_query_dimensions_fail_closed(self):
        with patch.object(self.service,'embed_piece',side_effect=JuneError('knowledge','bad vector',502)):
            doc=self.service.upload('failed.txt',b'June launches on Monday.')
            await self.service.jobs[doc['id']]
        self.assertEqual(self.service.db.get(doc['id'])['status'],'failed')
        with self.assertRaises(JuneError):await self.service.search('question',[doc['id']])

    async def test_document_limit_and_passage_limit(self):
        from june.knowledge_store import MAX_DOCUMENTS
        self.listen=True
        for i in range(MAX_DOCUMENTS):self.service.upload(f'{i}.txt',f'unique {i}'.encode())
        with self.assertRaises(JuneError):self.service.upload('too-many.txt',b'extra')
        with self.assertRaises(JuneError):passages([{'page':None,'text':'a'*2_501_000}])


class MoreKnowledgeFailures(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=KnowledgeTests.asyncSetUp
    asyncTearDown=KnowledgeTests.asyncTearDown
    ready=KnowledgeTests.ready
    events=KnowledgeTests.events
    # Reuse the isolated service fixture without duplicating inherited tests.
    async def test_preemption_releases_embedding_and_retries_after_transcription(self):
        self.block=True
        doc=self.service.upload('blocked.txt',b'June launches on Monday.')
        for _ in range(30):
            if self.calls:break
            await asyncio.sleep(.01)
        self.assertTrue(self.calls)
        self.listen=True
        await asyncio.sleep(.15)
        self.assertNotIn('index',self.coordinator.tasks.values())
        self.assertEqual(self.service.db.get(doc['id'])['status'],'indexing')
        self.listen=False;self.block=False
        await asyncio.wait_for(self.service.jobs[doc['id']],1)
        self.assertEqual(self.service.db.get(doc['id'])['status'],'ready')

    async def test_delete_cancels_active_answer_before_any_text(self):
        did=await self.ready();entered=asyncio.Event()
        from june.knowledge import bounded_json as real_json
        async def blocked(client,url,*args,**kwargs):
            if url.endswith('/api/chat'):
                entered.set();await asyncio.sleep(60)
            return await real_json(client,url,*args,**kwargs)
        events=[]
        async def run():
            async for event in persisted_chat(self.client,self.settings,self.store,self.coordinator,
                {'knowledge':{'documentIds':[did]}},'local',[{'role':'user','content':'When does June launch?'}],self.service):events.append(event)
        with patch('june.knowledge_chat.bounded_json',side_effect=blocked):
            task=asyncio.create_task(run());await asyncio.wait_for(entered.wait(),1)
            await self.service.stop(did,delete=True)
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertFalse(any(e['type'] in ('delta','done') for e in events))

    async def test_scope_isolated_from_plain_chat_and_temporary_bypass(self):
        did=await self.ready();cid=self.store.create_conversation()['id']
        await self.events(did,conversationId=cid,turnId='saved')
        for temporary in (False,True):
            with self.assertRaises(JuneError):
                _=[e async for e in persisted_chat(self.client,self.settings,self.store,self.coordinator,
                    {'conversationId':cid,'turnId':'next','temporary':temporary},'local',[{'role':'user','content':'Who am I?'}],self.service)]

    async def test_partial_preview_is_never_published(self):
        did=await self.ready();self.service.db.own(did)
        self.assertEqual(self.service.db.get(did,True)['passages'],[])
        with self.assertRaises(JuneError):await self.service.search('June',[did])

    async def test_api_raw_upload_percent_filename_errors_and_preview(self):
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from june.knowledge_api import router
        api=FastAPI();api.state.knowledge=self.service;api.include_router(router)
        @api.exception_handler(JuneError)
        async def failure(request,exc):return JSONResponse({'message':exc.message},status_code=exc.status)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api),base_url='http://test') as client:
            self.assertEqual((await client.get('/api/knowledge/status')).json()['state'],'ready')
            r=await client.post('/api/knowledge/documents',content=b'June launches on Monday.',headers={'content-type':'application/octet-stream','x-file-name':'my%20notes.md'})
            self.assertEqual(r.status_code,200);doc=r.json();self.assertEqual(doc['name'],'my notes.md')
            await self.service.jobs[doc['id']]
            preview=(await client.get('/api/knowledge/documents/'+doc['id'])).json()
            self.assertEqual(preview['passages'][0]['lineStart'],1)
            for headers in ({'content-type':'multipart/form-data'}, {'content-type':'application/octet-stream','content-length':str(MAX_UPLOAD+1)}, {'content-type':'application/octet-stream','x-file-name':'bad%FF.md'}):
                r=await client.post('/api/knowledge/documents',content=b'bad',headers=headers)
                self.assertGreaterEqual(r.status_code,400);self.assertEqual(set(r.json()),{'message'})
            r=await client.post('/api/knowledge/documents/'+doc['id']+'/retry');self.assertEqual(r.status_code,409)
            r=await client.delete('/api/knowledge/documents/'+doc['id']);self.assertEqual(r.status_code,200)
            self.assertEqual((await client.get('/api/knowledge/documents/'+doc['id'])).status_code,404)

    async def test_invalid_embedding_vectors_rejected(self):
        from june.knowledge import vector
        for value in ([],[float('nan')],[float('inf')],[0.,0.],[True],['x']):
            with self.assertRaises(JuneError):vector(value)

class KnowledgeProcessFailures(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=KnowledgeTests.asyncSetUp
    asyncTearDown=KnowledgeTests.asyncTearDown

    async def fake_extraction(self,read,**limits):
        # No PDF parser/model run: exercise the parent's timeout/output cleanup.
        from unittest.mock import AsyncMock
        self.listen=True
        doc=self.service.upload('bounded.pdf',b'%PDF- placeholder')
        await self.service.stop(doc['id'])
        proc=SimpleNamespace(returncode=None,stdout=SimpleNamespace(read=read),pid=12345,killed=False)
        def kill():proc.killed=True;proc.returncode=-9
        async def wait():proc.returncode=proc.returncode if proc.returncode is not None else 0;return proc.returncode
        proc.kill=kill;proc.wait=wait
        # Use the non-Darwin branch so the mocked child needs no live RSS probe.
        with patch('june.knowledge.sys.platform','linux'),patch('june.knowledge.asyncio.create_subprocess_exec',new=AsyncMock(return_value=proc)):
            with patch.multiple('june.knowledge',**limits):
                with self.assertRaises(JuneError):await self.service.extract(doc['id'])
        self.assertTrue(proc.killed)

    async def test_extraction_timeout_terminates_and_reaps_child(self):
        async def stalled(size):await asyncio.sleep(60)
        await self.fake_extraction(stalled,EXTRACT_TIMEOUT=.02)

    async def test_extraction_output_limit_terminates_and_reaps_child(self):
        async def oversized(size):return b'x'*100
        await self.fake_extraction(oversized,MAX_OUTPUT=10)

    async def test_library_passage_limit_is_atomic(self):
        self.listen=True;doc=self.service.upload('limit.txt',b'limit')
        await self.service.stop(doc['id']);token=self.service.db.own(doc['id'])
        with patch('june.knowledge_store.MAX_PASSAGES',0):
            with self.assertRaises(JuneError):self.service.db.publish(doc['id'],token,[{'id':'x','text':'x','page':None,'lineStart':1,'lineEnd':1,'vector':[1.]}],1,'')
        self.assertEqual(self.service.db.get(doc['id'],True)['passages'],[])
        with self.store.db() as db:self.assertEqual(db.execute('select count(*) from passage_fts').fetchone()[0],0)

    async def test_legacy_migration_backup_preserves_pending_turn_before_restart_cleanup(self):
        # Build a genuine v1 database by reversing only the new schema in a temp copy.
        legacy=self.root/'legacy';legacy.mkdir()
        path=legacy/'june.sqlite3'
        source=self.store.directory/'june.pre-phase7.sqlite3'
        import shutil
        shutil.copyfile(source,path)
        with sqlite3.connect(path) as db:
            db.execute("insert into conversations values('old','Old chat',?)",(self.store.clock(),))
            db.execute("insert into turns(id,conversation,user,status,revision,created) values('old-turn','old','hello','pending',0,?)",(self.store.clock(),))
        migrated=Store(legacy)
        with sqlite3.connect(legacy/'june.pre-phase7.sqlite3') as db:
            self.assertEqual(db.execute('pragma user_version').fetchone()[0],1)
            self.assertEqual(db.execute("select status from turns where id='old-turn'").fetchone()[0],'pending')
        self.assertEqual(migrated.conversation('old')['turns'][0]['status'],'stopped')

    async def test_empty_scope_and_invalid_source_ids_are_rejected(self):
        from june.chat import validate_chat
        for scope in ({'documentIds':[]},{'documentIds':['a','a']},None,{'documentIds':[[]]}, {'documentIds':['bad/id']}):
            with self.assertRaises(JuneError):validate_chat({'knowledge':scope,'messages':[{'role':'user','content':'question'}]})


if __name__=='__main__':unittest.main()
