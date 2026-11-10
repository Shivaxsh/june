import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from june.chat import validate_chat
from june.library_chat import mixed_schema, question_parts, source_scope
from june.memory_service import persisted_chat
from june.product_reference import motherboard_reference
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

    async def test_saved_delivery_preferences_reach_auto_chat_but_not_temporary_chat(self):
        profile = self.store.snapshot()['profile']
        profile['fields']['speech'] = 'Lead with the answer. Use natural contractions.'
        self.store.save_profile(profile)
        cid = self.store.create_conversation()['id']
        question = 'What does VRAM do?'
        with patch('june.library_chat.bounded_json', new=AsyncMock(return_value=
            self.model('not_needed', general='VRAM holds graphics data.')
        )) as model:
            await self.ask(question, cid, 'saved')
            for flags in ({'temporary':True}, {}):
                request = {'mode':'local', 'knowledge':{'mode':'auto'}, **flags,
                           'messages':[{'role':'user', 'content':question}]}
                mode, messages = validate_chat(request)
                async for _ in persisted_chat(
                    self.client, self.settings, self.store, self.coordinator, request, mode, messages, self.service,
                ):
                    pass
        saved, temporary, unsaved = (call.args[2]['messages'][0]['content'] for call in model.call_args_list)
        self.assertIn(profile['fields']['speech'], saved)
        self.assertNotIn(profile['fields']['speech'], temporary)
        self.assertNotIn(profile['fields']['speech'], unsaved)

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

    async def test_compound_build_question_uses_both_quotes_without_unrelated_context(self):
        first = await self.ready(b'Motherboard Example Board A.', 'First Build.pdf.txt')
        second = await self.ready(b'Motherboard Example Board B.', 'Second Build.txt')
        await self.ready(b'An unrelated personal profile.', 'Profile.txt')
        cid = self.store.create_conversation()['id']
        with patch('june.library_chat.bounded_json', new=AsyncMock(side_effect=[
            self.model('not_needed', general='VRAM stores graphics data.'),
            self.model('supported', 'The two quotes list Example Board A and Example Board B. Feature details are absent.', labels=['S1','S2']),
        ])) as model:
            await self.ask('What is VRAM used for?', cid, 'one')
            events = await self.ask('Can you fetch the motherboard inside my documents? Which motherboard is it? On both of the PC builds, what features are listed?', cid, 'two')
        payload = json.loads(model.call_args.args[2]['messages'][-1]['content'])
        self.assertEqual(payload['recentConversation'], [])
        self.assertEqual({c['documentId'] for c in events[-1]['citations']}, {first, second})
        self.assertIn('Feature details are absent', events[-2]['text'])

    async def test_unrelated_general_question_is_answered_when_passages_lack_it(self):
        await self.ready(b'Memory Example DDR5 32GB.', 'PC Build.txt')
        cid = self.store.create_conversation()['id']
        with patch('june.library_chat.bounded_json', new=AsyncMock(side_effect=[
            self.model('missing', general='Earth has no single furthest point; Voyager 1 is the furthest spacecraft.'),
            self.model('missing', general='I do not know your serial number.'),
        ])) as model:
            general = await self.ask("tell me what's the furthest point from the earth.", cid, 'one')
            personal = await self.ask('What is the serial number of my graphics card?', cid, 'two')
        self.assertEqual(general[-2]['text'], 'General knowledge\nEarth has no single furthest point; Voyager 1 is the furthest spacecraft.')
        self.assertEqual(general[-1]['provenance'], 'general')
        self.assertEqual(personal[-2]['text'], 'Document evidence\nI could not find that information in the documents I searched.')
        self.assertEqual(personal[-1]['provenance'], 'missing')
        schema = model.call_args_list[0].args[2]['format']
        for branch in schema['anyOf']:
            status = branch['properties']['documentStatus']['enum'][0]
            self.assertEqual(branch['properties']['generalAnswer'].get('minLength'), None if status == 'supported' else 1)

    def test_document_schema_requires_citations_for_a_supported_answer(self):
        schema = mixed_schema([{'text':'Motherboard Example Board.'}], required=True, general_only=False)
        branches = {branch['properties']['documentStatus']['enum'][0]:branch['properties']['citations']
                    for branch in schema['anyOf']}
        self.assertEqual(branches['supported']['minItems'], 1)
        self.assertEqual(branches['supported']['items']['properties']['chunkId']['enum'], ['S1'])
        self.assertEqual(branches['missing']['maxItems'], 0)

    def test_general_file_format_and_pronoun_followup(self):
        question = 'What is the PDF format?'
        self.assertEqual(question_parts(question), ('', question, False))
        self.assertEqual(question_parts('Which GPU does my build list, and what is it used for?'),
                         ('Which GPU does my build list', 'what is it used for?', True))
        self.assertEqual(question_parts('Which GPU does my build list, and where is it listed?')[1], '')

    def test_product_features_are_separate_from_the_cited_identification(self):
        source = 'Can you fetch the motherboard inside my documents? Which motherboard is it? On both of the PDFs, which are PC builds'
        extra = 'tell me their speciality and features and all.'
        self.assertEqual(question_parts(f'{source} and {extra}'), (source, extra, True))
        strict = 'Which motherboard is in my build PDF, and what features are listed?'
        self.assertEqual(question_parts(strict), (strict, '', True))
        followup = 'What are its features?'
        self.assertEqual(question_parts(followup, has_previous_source=True), (followup, followup, False))

    async def test_verified_board_details_extend_a_cited_answer_and_followup(self):
        board = 'MSI X870E Gaming Plus WIFI'
        await self.ready(f'Motherboard: {board}.'.encode(), 'Build.txt')
        cid = self.store.create_conversation()['id']
        with patch('june.library_chat.bounded_json', new=AsyncMock(return_value=
            self.model('supported', board, 'It has Wi-Fi 6E.', ['S1'])
        )) as model:
            first = await self.ask('Which motherboard is in Build.txt, and tell me its features?', cid, 'one')
            second = await self.ask("like slots, pcei's, wifi available or not, version, m.2 slots, bios, overcloacking, turbo mode and every small details.", cid, 'two')
        self.assertEqual(first[-1]['provenance'], 'mixed')
        self.assertEqual(first[-1]['citations'][0]['name'], 'Build.txt')
        self.assertIn('From your documents', first[-2]['text'])
        self.assertNotIn('Wi-Fi 6E', first[-2]['text'])
        for events in (first, second):
            for term in ('Manufacturer reference', 'Wi-Fi 7', 'three SSD M.2', 'PCIe 5.0', 'Click BIOS X', 'Precision Boost 2', 'msi.com'):
                self.assertIn(term, events[-2]['text'])
        self.assertEqual(second[-1]['model'], 'June product reference')
        self.assertEqual(model.await_count, 1)

    async def test_build_recommendation_is_not_a_pdf_lookup(self):
        board = 'MSI X870E Gaming Plus WiFi'
        parts = f'Motherboard: {board}. Processor: AMD Ryzen 7 9800X3D.'
        await self.ready(f'{parts} Graphics card: RTX 5070 Ti.'.encode(), 'First Build.txt')
        await self.ready(f'{parts} Graphics card: RX 9070 XT.'.encode(), 'Second Build.txt')
        cid = self.store.create_conversation()['id']
        question = 'do you have better recommended motherboard for both builds or these are enough ?'
        with patch('june.library_chat.bounded_json', new=AsyncMock(return_value=
            self.model('supported', board, labels=['S1','S2'])
        )) as model:
            identified = await self.ask('Which motherboard is in First Build.txt and Second Build.txt?', cid, 'one')
            # A later citation can correctly name the board but omit the CPU.
            revision = self.store.revision()
            self.store.start_turn(cid, 'two', question, revision)
            citations = [{**c, 'quote': f'Motherboard: {board}.'} for c in identified[-1]['citations']]
            self.store.finish_library_turn(cid, 'two', board, citations, 'documents', self.service.db.revision())
            events = await self.ask(question, cid, 'three')
        self.assertEqual(model.await_count, 1)
        self.assertEqual(events[-1]['provenance'], 'general')
        self.assertEqual(events[-1]['citations'], [])
        self.assertTrue(events[-2]['text'].startswith('Recommendation\nKeep the MSI X870E'))
        self.assertIn('B850 Tomahawk Max WiFi', events[-2]['text'])
        self.assertIn('40 Gb/s USB4', events[-2]['text'])
        self.assertNotIn('From your documents', events[-2]['text'])

    def test_recommendations_do_not_override_requests_about_document_contents(self):
        question = 'Which motherboard is recommended in my PDF?'
        self.assertEqual(question_parts(question), (question, '', True))
        question = 'Should I upgrade my motherboard for both builds?'
        self.assertEqual(question_parts(question), ('', question, False))

    def test_reference_stays_bound_to_the_exact_board(self):
        board = 'MSI X870E Gaming Plus WIFI'
        for question in ('What are the specs of MSI X870 Gaming Plus WIFI?',
                         'What are the features of MSI MAG X870E Gaming Plus MAX WIFI?',
                         'Compare MSI X870E Gaming Plus WIFI and Asus TUF Wi-Fi.',
                         'What are its features on the Gigabyte X870E?'):
            self.assertEqual(motherboard_reference(question, board), '')

    async def test_detailed_followup_can_retry_a_previously_missing_identification(self):
        board = 'MSI X870E Gaming Plus WIFI'
        await self.ready(f'Motherboard: {board}.'.encode(), 'Build.txt')
        cid = self.store.create_conversation()['id']
        with patch('june.library_chat.bounded_json', new=AsyncMock(side_effect=[
            self.model('missing'), self.model('supported', board, labels=['S1']),
        ])):
            await self.ask('Which motherboard is in Build.txt?', cid, 'one')
            events = await self.ask('What are its PCIe slots and BIOS features?', cid, 'two')
        self.assertEqual(events[-1]['provenance'], 'mixed')
        self.assertEqual(events[-1]['citations'][0]['name'], 'Build.txt')
        self.assertIn('Manufacturer reference', events[-2]['text'])

    async def test_other_products_can_use_an_imported_spec_sheet(self):
        board = 'Example Board A1'
        await self.ready(f'Motherboard: {board}.'.encode(), 'Build.txt')
        await self.ready(f'{board} specifications: two M.2 slots.'.encode(), 'Spec.txt')
        cid = self.store.create_conversation()['id']
        with patch('june.library_chat.bounded_json', new=AsyncMock(return_value=
            self.model('supported', board, labels=['S1'])
        )):
            await self.ask('Which motherboard is in Build.txt?', cid, 'one')
        with patch('june.library_chat.bounded_json', new=AsyncMock()) as model:
            async def cite_specs(_client, _url, request, *_args):
                evidence = json.loads(request['messages'][-1]['content'])['evidence']
                label = next(item['chunkId'] for item in evidence if item['name']=='Spec.txt')
                return self.model('supported', 'Two M.2 slots.', labels=[label])
            model.side_effect = cite_specs
            events = await self.ask('What are its M.2 slots?', cid, 'two')
        self.assertEqual(events[-1]['citations'][0]['name'], 'Spec.txt')
        self.assertNotIn('MSI', events[-2]['text'])

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
        with patch('june.library_chat.bounded_json', new=AsyncMock(return_value=self.model('not_needed', general='A launch introduces something.'))):
            await self.ask('What is a launch?', cid, 'one')
        chat = self.store.conversation(cid)
        self.assertEqual(chat['knowledge'], {'mode':'auto'})
        self.assertEqual(chat['turns'][:-1], previous)
        self.assertEqual(chat['turns'][-1]['provenance'], 'general')

    async def test_existing_general_chat_recalls_approved_memory_without_search(self):
        cid = self.store.create_conversation()['id']
        self.store.start_turn(cid, 'old', 'Hello.', self.store.revision())
        self.store.finish_turn('old', 'Hi.', 'complete')
        self.store.add_memory('My name is Avery.')
        await self.ready(b'An example document refers to a person named Jordan.', 'profile.txt')
        with patch.object(self.service, 'search', new=AsyncMock()) as search, patch(
            'june.library_chat.bounded_json', new=AsyncMock()
        ) as model:
            events = await self.ask('What is my approved name?', cid, 'new')
        search.assert_not_called()
        model.assert_not_called()
        self.assertEqual(events[-1]['provenance'], 'memory')
        self.assertIn('Avery', events[-2]['text'])
        chat = self.store.conversation(cid)
        self.assertEqual(chat['turns'][0]['assistant'], 'Hi.')
        self.assertEqual(json.loads(chat['turns'][1]['memories']), events[-1]['memoryIds'])
        self.assertTrue(events[-1]['memoryIds'])

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
