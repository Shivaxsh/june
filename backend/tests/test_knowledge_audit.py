"""Adversarial document boundaries; all storage is disposable and isolated."""
import asyncio
import os
import tempfile
import unittest
from unittest.mock import patch

import test_knowledge as fixtures
from june.errors import JuneError
from june.knowledge import passages,vector
from june.knowledge_chat import resolve_citations


class Audit(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.KnowledgeTests.asyncSetUp
    asyncTearDown=fixtures.KnowledgeTests.asyncTearDown
    ready=fixtures.KnowledgeTests.ready

    async def test_foreground_interrupts_extraction_and_retries_after_listening(self):
        entered=asyncio.Event();cancelled=asyncio.Event();calls=[]
        async def extract(_):
            calls.append(True)
            if len(calls)==1:
                entered.set()
                try:await asyncio.Future()
                finally:cancelled.set()
            return {'pages':[{'page':1,'text':'June launches on Monday.'}],'warning':''}
        self.service.extract=extract
        doc=self.service.upload('large.pdf',b'%PDF- synthetic')
        await asyncio.wait_for(entered.wait(),1)
        self.listen=True
        await asyncio.wait_for(cancelled.wait(),.5)
        self.assertEqual(self.service.db.get(doc['id'])['status'],'extracting')
        self.listen=False
        await asyncio.wait_for(self.service.jobs[doc['id']],2)
        self.assertEqual(self.service.db.get(doc['id'])['status'],'ready')
        self.assertEqual(len(calls),2)

    async def test_bad_scope_types_and_unready_sources_fail_closed(self):
        did=await self.ready()
        for scope in (None,{},'x',[],[None],[True],[[]],[''],[did,did],[did,'missing']):
            with self.subTest(scope=scope),self.assertRaises(JuneError):self.service.db.select(scope)

    def test_extreme_numeric_embeddings_report_a_safe_error(self):
        for value in ([10**500],[1e308,1e308],[-10**500],[True],[None],[[1]],{},[0,0]):
            with self.subTest(value=str(value)[:30]),self.assertRaises(JuneError):vector(value)

    def test_malformed_citation_labels_never_raise_a_type_error(self):
        for label in ([],{},None,False,1,'S2'):
            with self.subTest(label=label):
                self.assertIsNone(resolve_citations({'citations':[{'chunkId':label}]},[{'id':'real','text':'text'}]))

    def test_server_quotes_cannot_be_supplied_or_rewritten_by_model(self):
        source={'id':'real','text':'The active code is SAFE-2048.'}
        result=resolve_citations({'citations':[{'chunkId':'S1'}]},[source])
        self.assertEqual(result['citations'],[{'chunkId':'real','quote':source['text']}])
        for injected in ('Invented evidence',source['text']):
            self.assertIsNone(resolve_citations({'citations':[{'chunkId':'S1','quote':injected}]},[source]))

    def test_chunk_boundaries_preserve_unicode_and_content(self):
        for length in (0,1,499,500,501,599,600,601,1000,1201,3000):
            text=('June café 😀\n'*300)[:length]
            chunks=passages([{'page':None,'text':text}])
            if not text.strip():self.assertEqual(chunks,[]);continue
            rebuilt=''.join(c['text'][:500] for c in chunks[:-1])+chunks[-1]['text']
            self.assertEqual(rebuilt,text)
            for chunk in chunks:
                self.assertLessEqual(len(chunk['text']),600)
                self.assertGreaterEqual(chunk['lineEnd'],chunk['lineStart'])

    async def test_import_utf8_bom_crlf_and_partial_200_page_pdf(self):
        for name,data in [('café notes.md',b'\xef\xbb\xbfJune launches on Monday.\r\n'),('UPPER.TXT','June 😀 launches on Monday.'.encode())]:
            with self.subTest(name=name):
                did=await self.ready(data,name)
                self.assertTrue(self.service.db.get(did,True)['passages'])
        did=await self.ready(fixtures.pdf(pages=200),'max-pages.pdf')
        self.assertEqual(self.service.db.get(did)['pages'],200)


class Startup(unittest.TestCase):
    def test_failed_document_shutdown_still_releases_native_audio(self):
        from unittest.mock import AsyncMock
        from fastapi.testclient import TestClient
        from june.app import app
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'JUNE_DATA_HOME':directory,'JUNE_PREWARM':'0'}):
            with self.assertRaises(JuneError):
                with TestClient(app,base_url='http://127.0.0.1:8001'):
                    closed=AsyncMock(wraps=app.state.native_audio.close)
                    app.state.native_audio.close=closed
                    app.state.knowledge.close=AsyncMock(side_effect=JuneError('storage','Document cleanup failed.',503))
            closed.assert_awaited_once()

    def test_knowledge_storage_failure_does_not_stop_ordinary_chat(self):
        from fastapi.testclient import TestClient
        from june.app import app
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'JUNE_DATA_HOME':directory,'JUNE_PREWARM':'0'}),patch('june.app.Knowledge',side_effect=JuneError('storage','Document folder unavailable.',503)):
            with TestClient(app,base_url='http://127.0.0.1:8001') as client:
                self.assertEqual(client.get('/health').status_code,200)
                self.assertEqual(client.get('/api/library/state').status_code,200)
                self.assertEqual(client.get('/api/knowledge/documents').status_code,503)
