import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from june.chat import validate_chat
from june.errors import JuneError
from june.library_chat import question_parts, source_scope
from june.memory_service import persisted_chat
import test_knowledge as fixtures


class LibraryChatTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.KnowledgeTests.asyncSetUp
    asyncTearDown = fixtures.KnowledgeTests.asyncTearDown
    ready = fixtures.KnowledgeTests.ready

    async def ask(self, question, cid, tid, *, library=True):
        request = {'mode':'local', 'knowledge':{'mode':'auto'}, 'conversationId':cid, 'turnId':tid,
                   'messages':[{'role':'user', 'content':question}]}
        mode, messages = validate_chat(request)
        return [event async for event in persisted_chat(
            self.client, self.settings, self.store, self.coordinator, request, mode, messages,
            self.service if library else None,
        )]

    @staticmethod
    def model(status, document='', general='', labels=()):
        return {'message':{'content':json.dumps({'documentStatus':status, 'documentAnswer':document,
                'generalAnswer':general, 'citations':[{'chunkId':label} for label in labels]})}}

    async def test_library_followups_and_mixed_provenance_are_saved(self):
        did = await self.ready(b'Graphics card Example 5070. VRAM 16 GB.', 'build.txt')
        cid = self.store.create_conversation()['id']
        with patch('june.library_chat.bounded_json', new=AsyncMock(side_effect=[
            self.model('supported', 'Example 5070.', labels=['S1']),
            self.model('not_needed', general='VRAM holds textures and other graphics data.'),
            self.model('supported', '16 GB.', 'VRAM holds graphics data.', ['S1']),
            self.model('missing', general='VRAM holds graphics data.'),
        ])) as model:
            first = await self.ask('Which graphics card is in build.txt?', cid, 'one')
            second = await self.ask('What does VRAM do?', cid, 'two')
            third = await self.ask('How much VRAM is in build.txt, and what is VRAM?', cid, 'three')
            fourth = await self.ask('What serial number is in that file, and what is VRAM?', cid, 'four')
        self.assertEqual(first[-1]['citations'][0]['documentId'], did)
        self.assertEqual(second[-1]['citations'], [])
        self.assertIn('General knowledge\nVRAM', second[-2]['text'])
        self.assertIn('From your documents\n16 GB.\n\nGeneral knowledge', third[-2]['text'])
        self.assertIn('Document evidence\nI could not find', fourth[-2]['text'])
        self.assertIn('General knowledge', fourth[-2]['text'])
        followup_payload = model.call_args_list[1].args[2]['messages'][-1]['content']
        self.assertIn('Example 5070.', followup_payload)
        mixed_payload = json.loads(model.call_args_list[2].args[2]['messages'][-1]['content'])
        self.assertEqual(mixed_payload['recentConversation'], [])
        saved = self.store.conversation(cid)
        self.assertEqual(saved['knowledge'], {'mode':'auto'})
        self.assertEqual([t['provenance'] for t in saved['turns']], ['documents','general','mixed','mixed-missing'])
        self.assertEqual(saved['turns'][2]['citations'], third[-1]['citations'])
        self.assertEqual(self.store.export(True)['conversations'], [])
        self.assertEqual(self.store.snapshot()['suggestions'], [])

    async def test_missing_document_fact_cannot_turn_into_model_guess(self):
        await self.ready(name='build.txt')
        cid = self.store.create_conversation()['id']
        with patch('june.library_chat.bounded_json', new=AsyncMock(side_effect=[
            self.model('not_needed', general='The serial is fabricated.'),
            self.model('supported', 'Fabricated.', labels=['S2']),
        ])):
            for tid in ('one','two'):
                events = await self.ask('What serial number is in build.txt?', cid, tid)
                self.assertEqual(events[-1]['provenance'], 'missing')
                self.assertEqual(events[-1]['citations'], [])
                self.assertNotIn('fabricated', events[-2]['text'].lower())

    async def test_scope_named_missing_and_ambiguous(self):
        a = await self.ready(b'First build.', 'build A.txt')
        b = await self.ready(b'Second build.', 'build B.txt')
        docs = self.service.db.list()['documents']
        self.assertEqual(source_scope('What is listed in build A.txt?', docs, [])[0], [a])
        self.assertEqual(source_scope('What is listed in that file?', docs, [a])[0], [a])
        self.assertEqual(set(source_scope('Compare build A.txt and build B.txt.', docs, [])[0]), {a, b})
        cid = self.store.create_conversation()['id']
        with patch('june.library_chat.bounded_json', new=AsyncMock()) as model:
            ambiguous = await self.ask('What is listed in my build?', cid, 'one')
            missing = await self.ask('What is listed in missing.txt?', cid, 'two')
        model.assert_not_called()
        self.assertIn('Which document', ambiguous[-2]['text'])
        self.assertIn('could not find that file', missing[-2]['text'])

    def test_filename_scope_respects_full_names_and_pdf_plural(self):
        docs = [{'id':key,'name':name,'status':'ready'} for key,name in (
            ('short','Build.pdf'), ('office','Office Build.pdf'), ('note','parts.md'),
        )]
        for question in ('What is listed in Office Build.pdf?', 'Summarize Office Build.pdf.', 'What is in the graphics section of Office Build.pdf?'):
            with self.subTest(question=question):
                self.assertEqual(source_scope(question, docs, []), (['office'], ''))
        for question in ('What is listed in Unknown Build.pdf?', 'Summarize "Unknown Build.pdf".', 'Read Unknown Build.pdf.', 'Compare Office Build.pdf and Unknown Build.pdf.'):
            with self.subTest(question=question):
                ids, message = source_scope(question, docs, [])
                self.assertFalse(ids)
                self.assertIn('could not find', message)
        self.assertEqual(source_scope('What do my PDFs say?', docs, []), (['short','office'], ''))
        self.assertEqual(source_scope('What do those PDFs say?', docs, ['office']), (['office'], ''))
        ids, message = source_scope('What is listed in that PDF?', docs, ['removed'])
        self.assertFalse(ids)
        self.assertIn('unavailable', message)

    async def test_serial_followup_cannot_use_another_source_after_deletion(self):
        build = await self.ready(b'Example 5070. No serial number given.', 'build.txt')
        await self.ready(b'A different machine has serial number XYZ.', 'other.txt')
        cid = self.store.create_conversation()['id']
        with patch('june.library_chat.bounded_json', new=AsyncMock(side_effect=[
            self.model('supported', 'Example 5070.', labels=['S1']),
            self.model('not_needed', general='XYZ'),
        ])) as model:
            await self.ask('What is listed in build.txt?', cid, 'one')
            missing = await self.ask('What is its serial number?', cid, 'two')
            self.assertEqual(missing[-1]['provenance'], 'missing')
            payload = json.loads(model.call_args.args[2]['messages'][-1]['content'])
            self.assertEqual({p['name'] for p in payload['evidence']}, {'build.txt'})
            await self.service.stop(build, delete=True)
            deleted = await self.ask('What is its serial number?', cid, 'three')
        self.assertIn('unavailable', deleted[-2]['text'])
        self.assertEqual(model.await_count, 2)

    async def test_latest_named_file_wins_even_without_a_cited_answer(self):
        await self.ready(b'Example 5070.', 'first.txt')
        await self.ready(b'Example 5080.', 'second.txt')
        cid = self.store.create_conversation()['id']
        with patch('june.library_chat.bounded_json', new=AsyncMock(side_effect=[
            self.model('supported', 'Example 5070.', labels=['S1']),
            self.model('missing'),
            self.model('supported', 'Example 5080.', labels=['S1']),
        ])) as model:
            await self.ask('Which GPU is in first.txt?', cid, 'one')
            await self.ask('What serial number is in second.txt?', cid, 'two')
            second = await self.ask('What does that file list?', cid, 'three')
            await self.ask('What is listed in absent.txt?', cid, 'four')
            unknown = await self.ask('What does that file list?', cid, 'five')
        self.assertEqual(second[-1]['citations'][0]['name'], 'second.txt')
        self.assertIn('last named is unavailable', unknown[-2]['text'])
        self.assertEqual(model.await_count, 3)

    def test_general_file_format_and_pronoun_followup(self):
        question = 'What is the PDF format?'
        self.assertEqual(question_parts(question), ('', question, False))
        self.assertEqual(question_parts('Which GPU does my build list, and what is it used for?'),
                         ('Which GPU does my build list', 'what is it used for?', True))
        self.assertEqual(question_parts('Which GPU does my build list, and where is it listed?')[1], '')

    async def test_unavailable_library_allows_general_question(self):
        cid = self.store.create_conversation()['id']
        with patch('june.library_chat.bounded_json', new=AsyncMock(return_value=self.model('not_needed', general='A GPU renders graphics.'))) as model:
            general = await self.ask('What is a GPU?', cid, 'one', library=False)
            missing = await self.ask('What is listed in my PDF?', cid, 'two', library=False)
        self.assertEqual(model.await_count, 1)
        self.assertEqual(general[-1]['provenance'], 'general')
        self.assertIn('library is unavailable', missing[-2]['text'])

    async def test_explicit_general_override_skips_search_and_keeps_topic(self):
        did = await self.ready(b'Graphics Card Example 5070.', 'build.txt')
        cid = self.store.create_conversation()['id']
        await fixtures.KnowledgeTests.events(self, did, conversationId=cid, turnId='strict')
        self.store.bind_library_chat(cid, upgrade=True)
        with patch.object(self.service, 'search', new=AsyncMock()) as search, patch(
            'june.library_chat.bounded_json', new=AsyncMock(return_value=self.model('not_needed', general='Choose a processor for your workload.'))
        ) as model:
            await self.ask('What is the best processor to pair it with?', cid, 'one')
            events = await self.ask('dont search in the document, tell me according to your own knowledge', cid, 'two')
        search.assert_not_called()
        payload = json.loads(model.call_args.args[2]['messages'][-1]['content'])
        self.assertEqual(payload['evidence'], [])
        self.assertEqual(payload['generalQuestion'], 'What is the best processor to pair it with?')
        self.assertEqual(payload['recentConversation'][-1]['question'], 'What is the best processor to pair it with?')
        self.assertEqual(events[-1]['provenance'], 'general')

    async def test_selected_chat_can_upgrade_without_replacing_its_history(self):
        did = await self.ready()
        cid = self.store.create_conversation()['id']
        await fixtures.KnowledgeTests.events(self, did, conversationId=cid, turnId='strict')
        previous = self.store.conversation(cid)['turns']
        with self.assertRaises(JuneError):
            await self.ask('What is a launch?', cid, 'one')
        self.store.bind_library_chat(cid, upgrade=True)
        with patch('june.library_chat.bounded_json', new=AsyncMock(return_value=self.model('not_needed', general='A launch introduces something.'))):
            await self.ask('What is a launch?', cid, 'one')
        chat = self.store.conversation(cid)
        self.assertEqual(chat['knowledge'], {'mode':'auto'})
        self.assertEqual(chat['turns'][:-1], previous)
        self.assertEqual(chat['turns'][-1]['provenance'], 'general')

    async def test_deleted_source_cancels_inflight_reply(self):
        did = await self.ready(name='build.txt')
        cid = self.store.create_conversation()['id']
        started = asyncio.Event()

        async def blocked(*args):
            started.set()
            await asyncio.Future()

        with patch('june.library_chat.bounded_json', new=blocked):
            pending = asyncio.create_task(self.ask('What is listed in build.txt?', cid, 'one'))
            await asyncio.wait_for(started.wait(), 2)
            await self.service.stop(did, delete=True)
            with self.assertRaises(asyncio.CancelledError):
                await pending
        self.assertEqual(self.store.conversation(cid)['turns'][0]['status'], 'stopped')
        self.assertFalse(self.service.chat_tasks)
