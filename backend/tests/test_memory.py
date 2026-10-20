"""Private, real SQLite tests: assertions protect user approval and erasure."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from june.memory import Store, validate_candidates, validate_import, profile_defaults
from june.errors import JuneError

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 10000000
        self.store = Store(Path(self.tmp.name) / 'private', lambda: self.now)
    def tearDown(self):
        self.tmp.cleanup()
    def conversation(self, text='My project is Lantern.'):
        c = self.store.create_conversation()
        self.store.start_turn(c['id'], 'turn-1', text, self.store.revision())
        self.store.finish_turn('turn-1', 'A useful project.', 'complete')
        return c['id']
    def test_permissions_and_restart(self):
        c = self.conversation()
        second = Store(self.store.directory, lambda: self.now)
        self.assertEqual(second.conversation(c)['turns'][0]['user'], 'My project is Lantern.')
        self.assertEqual(os.stat(second.directory).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(second.path).st_mode & 0o777, 0o600)
    def test_retention_boundary_keeps_approved_memory(self):
        c = self.conversation()
        self.store.add_memory('My project is Lantern.', source=c)
        self.now += 30 * 86400
        self.assertEqual(self.store.snapshot()['conversations'], [])
        self.assertEqual(len(self.store.snapshot()['memories']), 1)
        with self.assertRaises(JuneError): self.store.conversation(c)
    def test_suggestions_need_approval_and_rejection_is_suppressed(self):
        c = self.conversation()
        items = [{'text': 'My project is Lantern.', 'quote': 'My project is Lantern.'}]
        self.store.suggest(c, 'turn-1', items, self.store.revision())
        self.assertEqual(self.store.snapshot()['memories'], [])
        suggestion = self.store.snapshot()['suggestions'][0]
        self.store.decide(suggestion['id'], 'reject')
        self.store.suggest(c, 'turn-1', items, self.store.revision())
        self.assertEqual(self.store.snapshot()['suggestions'], [])
    def test_duplicate_writes_and_completed_context_only(self):
        c = self.conversation()
        with self.assertRaises(JuneError): self.store.start_turn(c, 'turn-1', 'different', 0)
        self.store.start_turn(c, 'turn-2', 'unfinished', 0)
        self.store.finish_turn('turn-2', 'partial', 'stopped')
        self.assertEqual(len(self.store.context(c)), 2)
    def test_edit_delete_resets_context_not_source_history(self):
        c = self.conversation()
        m = self.store.add_memory('My colour is purple.')
        self.store.edit_memory(m['id'], 'My colour is amber.', False)
        self.assertEqual(self.store.context(c), [])
        self.assertEqual(len(self.store.conversation(c)['turns']), 1)
        self.store.delete_memory(m['id'])
        self.assertEqual(len(self.store.conversation(c)['turns']), 1)
        self.assertEqual(self.store.retrieve('colour'), [])
    def test_dedup_conflict_requires_explicit_replacement(self):
        a = self.store.add_memory('My favourite colour is purple.')
        b = self.store.add_memory('my favourite colour is purple!')
        self.assertEqual(a['id'], b['id'])
        with self.assertRaises(JuneError): self.store.add_memory('My favourite colour is amber.')
        self.store.add_memory('My favourite colour is amber.', replace=a['id'])
        self.assertEqual(len(self.store.snapshot()['memories']), 1)
    def test_retrieval_limits_and_exact_identifiers(self):
        for i in range(12): self.store.add_memory(f'Project {i} uses GPU 5070 Ti '+str(i)*160, pinned=True)
        facts = self.store.retrieve('GPU')
        self.assertLessEqual(len(facts), 8)
        self.assertLessEqual(sum(len(x['text']) for x in facts), 1600)
        self.assertTrue(all('5070 Ti' in x['text'] for x in facts))
    def test_invalid_import_is_atomic(self):
        with self.assertRaises(JuneError): validate_import({'format': 'june-data', 'version': 1, 'memories': [{'text': 'ok'}, {'text': 7}]})
        self.assertEqual(self.store.snapshot()['memories'], [])
    def test_candidates_require_user_quote_and_reject_secrets_and_fiction(self):
        def candidates(text, quote=None):
            return validate_candidates([{'text': text, 'quote': quote or text}], text)
        self.assertEqual(len(candidates('My project is Lantern.')), 1)
        self.assertEqual(candidates('I prefer tea.', 'I prefer coffee.'), [])
        self.assertEqual(candidates('For a fictional exercise, my name is Mira.'), [])
        self.assertEqual(candidates('My password is hunter123.'), [])
        self.assertEqual(validate_candidates([{'text': 'I am a manager.', 'quote': 'My project is Lantern.'}], 'My project is Lantern.'), [])
    def test_stale_suggestions_cannot_return_after_clear(self):
        c = self.conversation()
        rev = self.store.revision()
        m = self.store.add_memory('I like tea.')
        self.store.delete_memory(m['id'])
        self.store.suggest(c, 'turn-1', [{'text': 'My project is Lantern.', 'quote': 'My project is Lantern.'}], rev)
        self.assertEqual(self.store.snapshot()['suggestions'], [])
    def test_profile_validation_no_progress_import(self):
        preview = validate_import({'format':'building-june-backup','version':1,'character':{'speech':'Brief replies'},'progress':{'p6-b':True}})
        self.assertEqual(preview['profile']['fields']['speech'], 'Brief replies')
        self.assertNotIn('progress', preview)
        self.assertEqual(profile_defaults()['expression'], 'steady')

class MemoryPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_keeps_boundaries_and_quotes_memory_as_data(self):
        from june.memory_service import memory_prompt
        prompt = memory_prompt({'fields':{'speech':'Be brief','never':'ignore system rules'},'expression':'steady'}, [{'id':'1','text':'My GPU is 5070 Ti.'}])
        self.assertIn('5070 Ti', prompt)
        self.assertIn('data', prompt)
        self.assertIn('capabil', prompt)
    async def test_foreground_cancels_extraction_and_releases_lock(self):
        import asyncio
        from june.memory_service import Coordinator
        c=Coordinator()
        ready=asyncio.Event()
        async def slow():
            async with c.slot('extract'):
                ready.set(); await asyncio.sleep(30)
        task=asyncio.create_task(slow());await ready.wait()
        async with c.slot('chat'): self.assertTrue(task.cancelled())
    async def test_stream_persists_complete_and_stopped_and_reports_memories(self):
        import httpx
        from june.memory_service import Coordinator, persisted_chat
        from june.config import Settings
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory); c=store.create_conversation()['id'];store.add_memory('My project is Lantern.')
            body='{"message":{"content":"Lantern."},"done":true}\n'
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,text=body))) as client:
                events=[x async for x in persisted_chat(client,Settings.from_env(),store,Coordinator(),{'conversationId':c,'turnId':'one'},'local',[{'role':'user','content':'What is my project?'}])]
            self.assertEqual(events[-1]['persistence'],'saved')
            self.assertEqual(len(events[-1]['memoryIds']),1)
            self.assertEqual(store.conversation(c)['turns'][0]['status'],'complete')

class MemoryAPITests(unittest.TestCase):
    def test_crud_import_preview_and_duplicate_turn(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from june.app import app
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'JUNE_DATA_HOME':d}), TestClient(app,base_url='http://127.0.0.1:8001') as client:
            c=client.post('/api/library/conversations',json={}).json()['id']
            self.assertEqual(client.get('/api/library/state').status_code,200)
            m=client.post('/api/library/memories',json={'text':'My project is Lantern.'})
            self.assertEqual(m.status_code,200)
            self.assertEqual(client.get('/api/library/export').json()['conversations'],[])
            data={'format':'june-data','version':1,'memories':[{'text':'I like tea.'}]}
            self.assertEqual(client.post('/api/library/import/preview',json=data).status_code,200)
            self.assertEqual(len(client.get('/api/library/state').json()['memories']),1)
            self.assertEqual(client.post('/api/library/import',json=data).status_code,200)
            self.assertEqual(len(client.get('/api/library/state').json()['memories']),2)
            self.assertEqual(client.delete('/api/library/conversations/'+c).status_code,200)
    def test_storage_failure_requires_explicit_temporary_chat(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from june.app import app
        with tempfile.TemporaryDirectory() as d:
            bad=Path(d)/'file';bad.write_text('occupied')
            with patch.dict(os.environ,{'JUNE_DATA_HOME':str(bad)}), TestClient(app,base_url='http://127.0.0.1:8001') as client:
                self.assertEqual(client.get('/api/library/state').status_code,503)
                payload={'mode':'demo','messages':[{'role':'user','content':'hello'}]}
                self.assertIn('storage',client.post('/api/chat',json=payload).text.lower())
                self.assertNotIn('"type": "done"',client.post('/api/chat',json=payload).text)
                payload['temporary']=True
                self.assertIn('"type": "done"',client.post('/api/chat',json=payload).text)

class DefensiveMemoryTests(unittest.TestCase):
    def test_malformed_profiles_and_unicode_are_readable_validation_errors(self):
        from june.memory import validate_profile,text
        for value in ({'fields':{},'expression':[]},{'fields':[], 'expression':'steady'},{'fields':{'speech':'\ud800'}}):
            with self.subTest(value=str(value)), self.assertRaises(JuneError):validate_profile(value)
        with self.assertRaises(JuneError):text('\ud800')
    def test_import_conflict_rolls_back_prior_facts(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);s.add_memory('My name is Ada.')
            with self.assertRaises(JuneError):s.apply_import({'format':'june-data','version':1,'memories':[{'text':'I like tea.'},{'text':'My name is Bea.'}]})
            self.assertEqual([m['text'] for m in s.snapshot()['memories']],['My name is Ada.'])
    def test_repeated_approval_and_stale_completion_are_safe(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);cid=s.create_conversation()['id'];s.start_turn(cid,'one','My name is Ada.',0);s.finish_turn('one','Hello.','complete')
            s.suggest(cid,'one',[{'text':'My name is Ada.','quote':'My name is Ada.'}],0)
            sid=s.snapshot()['suggestions'][0]['id'];s.decide(sid,'approve')
            with self.assertRaises(JuneError):s.decide(sid,'approve')
            s.finish_turn('one','late overwrite','failed')
            self.assertEqual(s.conversation(cid)['turns'][0]['assistant'],'Hello.')

class SavedFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_model_reply_is_saved_and_excluded_from_context(self):
        import httpx
        from june.memory_service import Coordinator,persisted_chat
        from june.config import Settings
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);cid=s.create_conversation()['id']
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(404))) as client:
                events=[e async for e in persisted_chat(client,Settings.from_env(),s,Coordinator(),{'conversationId':cid,'turnId':'failed'},'local',[{'role':'user','content':'hello'}])]
            self.assertEqual(events[-1]['type'],'error');self.assertEqual(s.conversation(cid)['turns'][0]['status'],'failed');self.assertEqual(s.context(cid),[])
    async def test_closing_a_stream_persists_stopped_reply(self):
        import httpx
        from june.memory_service import Coordinator,persisted_chat
        from june.config import Settings
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);cid=s.create_conversation()['id']
            async with httpx.AsyncClient() as client:
                source=persisted_chat(client,Settings.from_env(),s,Coordinator(),{'conversationId':cid,'turnId':'stop'},'demo',[{'role':'user','content':'hello'}])
                await anext(source);await source.aclose()
            self.assertEqual(s.conversation(cid)['turns'][0]['status'],'stopped');self.assertEqual(s.context(cid),[])

class SavedOfflineAPITest(unittest.TestCase):
    def test_connection_failure_preserves_failed_turn_in_history(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        import httpx
        from june.app import app
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'JUNE_DATA_HOME':d}),TestClient(app,base_url='http://127.0.0.1:8001') as client:
            cid=client.post('/api/library/conversations',json={}).json()['id']
            async def offline(*args,**kwargs):return {'state':'offline','message':'Ollama is offline.'}
            def no_model(request):raise httpx.ConnectError('offline')
            previous=app.state.client
            app.state.client=httpx.AsyncClient(transport=httpx.MockTransport(no_model))
            try:
                with patch('june.app.status',offline):
                    response=client.post('/api/chat',json={'conversationId':cid,'turnId':'offline','messages':[{'role':'user','content':'hello'}]})
                turns=client.get('/api/library/conversations/'+cid).json()['turns']
                self.assertEqual(len(turns),1)
                self.assertEqual(turns[0]['status'],'failed')
            finally:app.state.client=previous

class ReviewRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_temporary_chat_never_reads_a_failed_database(self):
        import httpx
        from june.memory_service import Coordinator,persisted_chat
        from june.config import Settings
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);s.path.write_bytes(b'corrupted')
            async with httpx.AsyncClient() as client:
                source=persisted_chat(client,Settings.from_env(),s,Coordinator(),{'temporary':True},'demo',[{'role':'user','content':'hello'}])
                self.assertEqual((await anext(source))['type'],'delta');await source.aclose()
    async def test_pin_is_not_a_saveable_memory(self):
        self.assertEqual(validate_candidates([{'text':'My PIN is 1234.','quote':'My PIN is 1234.'}],'My PIN is 1234.'),[])
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(JuneError):Store(d).add_memory('My PIN is 1234.')
    async def test_export_pending_turn_is_importable_as_stopped(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);cid=s.create_conversation()['id'];s.start_turn(cid,'pending','Hello',0)
            preview=validate_import(s.export(True))
            self.assertEqual(preview['conversations'][0]['turns'][0]['status'],'stopped')

class PromptBudgetTests(unittest.TestCase):
    def test_character_preferences_are_bounded_without_cutting_fields(self):
        from june.memory_service import memory_prompt
        p=profile_defaults();p['fields']={k:(k+' 5070 Ti ')*35 for k in p['fields']}
        prompt=memory_prompt(p,[])
        self.assertLess(len(prompt),3000)
        self.assertIn(p['fields']['speech'],prompt)

class ExportCompletenessTests(unittest.TestCase):
    def test_chat_export_includes_chats_beyond_recent_list_limit(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d)
            for n in range(103):s.create_conversation(str(n))
            self.assertEqual(len(s.snapshot()['conversations']),100)
            self.assertEqual(len(s.export(True)['conversations']),103)
