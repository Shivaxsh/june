"""Reply completeness survives storage and constrains subsequent claims."""
import json
import unittest
from unittest.mock import patch
import httpx
from june.chat import stream_chat, validate_chat
from june.config import Settings
from june.memory_service import persisted_chat
import test_knowledge as fixtures


class CompletionFlow(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.KnowledgeTests.asyncSetUp
    asyncTearDown = fixtures.KnowledgeTests.asyncTearDown

    async def ask(self, question, cid, tid, **extra):
        value = {'mode':'local','knowledge':{'mode':'auto'},'conversationId':cid,'turnId':tid,
                 'messages':[{'role':'user','content':question}], **extra}
        mode,messages=validate_chat(value)
        return [e async for e in persisted_chat(self.client,self.settings,self.store,self.coordinator,
                                               value,mode,messages,self.service)]

    async def test_limited_and_open_fence_flags_survive_reopen(self):
        cid=self.store.create_conversation()['id']
        async def partial(*args,**kwargs):
            yield {'type':'delta','text':'```python\ndef add(a, b):\n    return a +'}
            yield {'type':'done','model':'fixture','limited':True}
        with patch('june.library_chat.stream_chat',new=partial):
            events=await self.ask('Write a Python addition function.',cid,'a')
        self.assertIs(events[-1].get('incomplete'),True)
        row=self.store.conversation(cid)['turns'][0]
        self.assertTrue(row.get('limited'))
        self.assertTrue(row.get('incomplete'))
        from june.memory import Store
        self.assertTrue(Store(self.store.directory).conversation(cid)['turns'][0]['incomplete'])

    async def test_unclosed_fence_without_token_limit_is_still_incomplete(self):
        cid=self.store.create_conversation()['id']
        async def partial(*args,**kwargs):
            yield {'type':'delta','text':'```python\nprint(1)'}
            yield {'type':'done','model':'fixture'}
        with patch('june.library_chat.stream_chat',new=partial):
            events=await self.ask('Write Python code.',cid,'a')
        self.assertTrue(events[-1].get('incomplete'))
        self.assertFalse(events[-1].get('limited',False))

    async def test_partial_code_cannot_be_reported_as_complete(self):
        cid=self.store.create_conversation()['id']
        async def partial(*args,**kwargs):
            yield {'type':'delta','text':'```python\ndef add(a, b):'}
            yield {'type':'done','model':'fixture','limited':True}
        with patch('june.library_chat.stream_chat',new=partial):
            await self.ask('Write Python code.',cid,'a')
        async def mistaken(*args,**kwargs):
            yield {'type':'delta','text':'Yes, the program is fully complete.'}
            yield {'type':'done','model':'fixture'}
        with patch('june.library_chat.stream_chat',new=mistaken):
            events=await self.ask('Are you sure that the program is finished?',cid,'b')
        reply=''.join(e['text'] for e in events if e['type']=='delta')
        self.assertNotIn('fully complete',reply)
        self.assertRegex(reply.lower(),'cut off|incomplete|unfinished')

    async def test_invalid_continuation_does_not_create_a_turn(self):
        cid=self.store.create_conversation()['id']
        from june.errors import JuneError
        async def stream(*args,**kwargs):
            yield {'type':'delta','text':'A reply.'}
            yield {'type':'done','model':'fixture'}
        with patch('june.library_chat.stream_chat',new=stream):
            with self.assertRaises(JuneError):
                await self.ask('Continue.',cid,'b',continueTurn='missing')
        self.assertEqual(self.store.conversation(cid)['turns'],[])

    async def test_continuation_after_completion_check_saves_only_suffix(self):
        cid=self.store.create_conversation()['id']
        prefix='```python\ndef add(a, b):\n    return a'
        async def partial(*args,**kwargs):
            yield {'type':'delta','text':prefix}
            yield {'type':'done','model':'fixture','limited':True}
        with patch('june.library_chat.stream_chat',new=partial):
            await self.ask('Write Python code.',cid,'a')
        await self.ask('Is that complete?',cid,'check')
        async def suffix(*args,**kwargs):
            self.assertEqual(kwargs['continuation']['prefix'],prefix)
            yield {'type':'delta','text':' + b\n```'}
            yield {'type':'done','model':'fixture'}
        with patch('june.library_chat.stream_chat',new=suffix):
            events=await self.ask('Continue.',cid,'b',continueTurn='a')
        self.assertEqual(events[-1].get('continuedFrom'),'a')
        self.assertFalse(events[-1]['incomplete'])
        row=self.store.conversation(cid)['turns'][-1]
        self.assertEqual(row['assistant'],' + b\n```')
        self.assertEqual(row['continuedFrom'],'a')

    async def test_repeated_completeness_checks_remain_honest(self):
        cid=self.store.create_conversation()['id']
        async def partial(*args,**kwargs):
            yield {'type':'delta','text':'```python\nprint('}
            yield {'type':'done','model':'fixture','limited':True}
        with patch('june.library_chat.stream_chat',new=partial):
            await self.ask('Write Python code.',cid,'a')
        await self.ask('Is that complete?',cid,'b')
        async def mistaken(*args,**kwargs):
            yield {'type':'delta','text':'It is fully complete.'}
            yield {'type':'done','model':'fixture'}
        with patch('june.library_chat.stream_chat',new=mistaken):
            events=await self.ask('Is the program finished?',cid,'c')
        self.assertIn('cut off',''.join(e['text'] for e in events if e['type']=='delta'))


class RawCompletion(unittest.IsolatedAsyncioTestCase):
    async def test_raw_stream_reports_unclosed_code(self):
        body=json.dumps({'message':{'content':'```python\nprint(1)'},'done':True})+'\n'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,text=body))) as client:
            events=[e async for e in stream_chat(client,Settings.from_env(),'local',[{'role':'user','content':'Write Python code.'}])]
        self.assertTrue(events[-1].get('incomplete'))

    async def test_ollama_prefill_echo_is_removed_before_suffix_delivery(self):
        prefix='```python\ndef add(a, b):\n    return a'
        body=''.join(json.dumps(frame)+'\n' for frame in (
            {'message':{'content':prefix[:12]},'done':False},
            {'message':{'content':prefix[12:]+' + b\n```'},'done':False},
            {'message':{'content':''},'done':True}))
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,text=body))) as client:
            events=[e async for e in stream_chat(client,Settings.from_env(),'local',
                [{'role':'user','content':'Continue.'}],continuation={'question':'Write addition code.','prefix':prefix})]
        self.assertEqual(''.join(e['text'] for e in events if e['type']=='delta'),' + b\n```')
        self.assertFalse(events[-1].get('incomplete',False))

class ReplyStateRules(unittest.TestCase):
    def test_fences_are_line_delimiters_and_closing_run_must_match(self):
        from june.reply_state import open_fence
        for body,want in [('Use `x` inline.',False),('```python\nx=1\n```',False),
                          ('~~~~python\nx=1\n~~~',True),('~~~python\nx=1\n~~~',False),
                          ('````python\n```\ncode',True)]:
            self.assertEqual(open_fence(body),want,body)

    def test_completed_child_resolves_parent_incompleteness(self):
        from june.reply_state import completeness_reply
        turns=[{'id':'a','status':'complete','limited':True,'incomplete':True},
               {'id':'b','status':'complete','limited':False,'incomplete':False,'continuedFrom':'a'}]
        self.assertIsNone(completeness_reply('Is the program finished?',turns))

    def test_schema_three_migration_backs_up_and_marks_legacy_open_fence(self):
        import tempfile,sqlite3,os
        from pathlib import Path
        from june.memory import Store
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp));cid=store.create_conversation()['id']
            store.start_turn(cid,'old','Write code.',0)
            store.finish_turn('old','```python\nprint(', 'complete')
            with store.db() as db:
                for name in ('limited','incomplete','continuedFrom'):db.execute(f'ALTER TABLE turns DROP COLUMN {name}')
                db.execute('PRAGMA user_version=3')
            backup=Path(tmp)/'june.pre-reply-state.sqlite3';backup.unlink()
            restored=Store(Path(tmp))
            self.assertTrue(restored.conversation(cid)['turns'][0]['incomplete'])
            with sqlite3.connect(backup) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3)
                self.assertEqual(db.execute('SELECT assistant FROM turns').fetchone()[0],'```python\nprint(')
            self.assertEqual(os.stat(backup).st_mode & 0o777,0o600)


class ReviewBoundaries(unittest.TestCase):
    def test_completion_task_is_not_confused_with_completeness_question(self):
        from june.reply_state import completeness_reply
        turns=[{'id':'a','status':'complete','assistant':'partial','revision':0,'provenance':'general','limited':True}]
        for question in ('Can you complete the code?', 'Make it complete with tests.'):
            self.assertIsNone(completeness_reply(question,turns))
    def test_empty_migration_backup_is_repaired_and_old_backup_chats_are_expired(self):
        import tempfile,sqlite3
        from pathlib import Path
        from june.memory import Store,RETENTION
        with tempfile.TemporaryDirectory() as tmp:
            now=[10000000.0];store=Store(Path(tmp),lambda:now[0]);cid=store.create_conversation()['id']
            store.start_turn(cid,'old','Old conversation.',0);store.finish_turn('old','A reply.','complete')
            with store.db() as db:
                for name in ('limited','incomplete','continuedFrom'):db.execute(f'ALTER TABLE turns DROP COLUMN {name}')
                db.execute('PRAGMA user_version=3')
            backup=Path(tmp)/'june.pre-reply-state.sqlite3';backup.write_bytes(b'')
            store=Store(Path(tmp),lambda:now[0])
            with sqlite3.connect(backup) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM conversations').fetchone()[0],1)
            now[0]+=RETENTION+1;store.cleanup()
            with sqlite3.connect(backup) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM conversations').fetchone()[0],0)

class PrefillGuards(unittest.IsolatedAsyncioTestCase):
    async def test_prose_continuation_does_not_request_a_code_fence(self):
        captured=[];prefix='The first step is'
        def respond(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200,text=json.dumps({'message':{'content':prefix+' to measure.'},'done':True})+'\n')
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            events=[e async for e in stream_chat(client,Settings.from_env(),'local',
                [{'role':'user','content':'Continue.'}],continuation={'question':'Explain the steps.','prefix':prefix})]
        self.assertNotIn('An open code fence',captured[0]['messages'][0]['content'])
        self.assertEqual(''.join(e['text'] for e in events if e['type']=='delta'),' to measure.')
        self.assertFalse(events[-1].get('incomplete',False))

    async def test_divergent_prefill_fails_without_exposing_restarted_code(self):
        body=json.dumps({'message':{'content':'Here is a new program instead.'},'done':True})+'\n'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,text=body))) as client:
            events=[e async for e in stream_chat(client,Settings.from_env(),'local',
                [{'role':'user','content':'Continue.'}],continuation={'question':'Write code.','prefix':'```python\ndef add(a,b):'})]
        self.assertFalse(any(e['type']=='delta' for e in events))
        self.assertEqual(events[-1]['type'],'error')
