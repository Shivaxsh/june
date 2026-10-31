"""Recall/capability/repetition regressions; no live store or inference."""
import json
import tempfile
import unittest

import httpx

from june.app_info import application_reply, personal_recall
from june.chat import stream_chat
from june.config import Settings
from june.memory import Store
from june.memory_service import Coordinator, persisted_chat


class RecallDomainTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = Store(directory.name)
        self.name = self.store.add_memory('My name is Mira-X.')
        self.color = self.store.add_memory('My favorite color is black.')
        self.age = self.store.add_memory('I am 29 years old.')
        self.location = self.store.add_memory('I live in Leeds.')
        self.cid = self.store.create_conversation()['id']
        self.calls = []

    async def asyncSetUp(self):
        import asyncio
        asyncio.get_running_loop().slow_callback_duration = 1

    def previous(self, text, answer='Understood.'):
        tid = self.cid + '-previous-' + str(len(self.store.conversation(self.cid)['turns']))
        self.store.start_turn(self.cid, tid, text, self.store.revision())
        self.store.finish_turn(tid, answer, 'complete', propose=True)

    async def ask(self, query):
        def model(request):
            self.calls.append(json.loads(request.content))
            return httpx.Response(200, text='{"message":{"content":"MODEL RESPONSE"},"done":true}\n')
        tid = self.cid + '-question-' + str(len(self.store.conversation(self.cid)['turns']))
        async with httpx.AsyncClient(transport=httpx.MockTransport(model)) as client:
            events = [event async for event in persisted_chat(
                client, Settings.from_env(), self.store, Coordinator(),
                {'conversationId': self.cid, 'turnId': tid}, 'local',
                [{'role': 'user', 'content': query}])]
        return ''.join(e.get('text', '') for e in events), events[-1]

    async def test_greeting_then_spoken_color_recall_needs_no_model(self):
        self.previous("what's up?")
        text, done = await self.ask('Can you tell me what my favorite color is?')
        self.assertEqual(text, 'Saved memory:\nYour favorite color is black.')
        self.assertEqual(self.calls, [])
        self.assertEqual(done['memoryIds'], [self.color['id']])

    async def test_spoken_other_details_lists_four_approved_facts(self):
        query = 'have other details like my name or anything else. Do you have other details of mine?'
        text, done = await self.ask(query)
        for fact in (self.name, self.color, self.age, self.location):
            self.assertIn(fact['text'], text)
        self.assertEqual(set(done['memoryIds']), {f['id'] for f in (self.name, self.color, self.age, self.location)})
        self.assertEqual(self.calls, [])

    async def test_spoken_name_recall_is_not_generic_capability(self):
        text, done = await self.ask('Okay, but you do know what my name is, right? So can you just remember what my name is?')
        self.assertEqual(text, 'Saved memory:\nYour name is Mira-X.')
        self.assertEqual(done['memoryIds'], [self.name['id']])
        self.assertEqual(self.calls, [])

    async def test_spoken_and_preface_and_one_thing_filler_keep_direct_recall(self):
        for query,fact in [('And where do I live?',self.location),('Okay and tell me one thing, what my age is.',self.age),('Um, well, now what is my name?',self.name),('What is my approved name?',self.name),('What is my saved favourite colour?',self.color)]:
            with self.subTest(query=query):
                text,done=await self.ask(query)
                self.assertEqual(done.get('source'),'application')
                self.assertEqual(done['memoryIds'],[fact['id']])
        self.assertEqual(self.calls,[])

    async def test_saved_age_location_and_source_are_application_owned(self):
        for query, fact in (('How old am I?', self.age), ('Where do I live?', self.location),
                            ('How do you know my name?', self.name)):
            with self.subTest(query=query):
                text, done = await self.ask(query)
                self.assertEqual(done.get('source'), 'application')
                self.assertEqual(done['memoryIds'], [fact['id']])
                self.assertIn(fact['text'] if 'know' in query or 'old' in query else 'Leeds', text)
        self.assertEqual(self.calls, [])

    async def test_actual_recent_recall_with_just_and_greeting_prefaces(self):
        for query in ('Just tell me what my favorite color is.',
                      'Hi, what details do you know about me?',
                      'Please remind me what my name is.',
                      'Okay just tell me one thing, what is my saved name?'):
            with self.subTest(query=query):
                text, done = await self.ask(query)
                self.assertEqual(done.get('source'), 'application')
                self.assertTrue(text.startswith('Saved memory:\n'))
        self.assertEqual(self.calls, [])

    async def test_interruption_and_discourse_prefaces_keep_approved_recall(self):
        for prefix in ('Wait, ', 'Stop. ', 'Hold on, ', 'Hang on, ', 'Actually, ', 'Sorry, ', 'Okay, wait, '):
            with self.subTest(prefix=prefix):
                text, done = await self.ask(prefix + 'what is my approved name?')
                self.assertEqual(text, 'Saved memory:\nYour name is Mira-X.')
                self.assertEqual(done['memoryIds'], [self.name['id']])
                self.assertEqual(done.get('source'), 'application')
        self.assertEqual(self.calls, [])

    async def test_multiple_explicit_recall_fields_do_not_expose_unasked_facts(self):
        for query in ('Can you tell me my name and favourite colour?',
                      'What is my name, and where do I live?',
                      'Hello June, remind me of my name and my age.'):
            with self.subTest(query=query):
                text, done = await self.ask(query)
                self.assertEqual(done.get('source'), 'application')
                self.assertIn('Mira-X', text)
                self.assertEqual(len(done['memoryIds']), 2)
                if 'colour' in query:
                    self.assertIn('black', text)
                    self.assertNotIn('Leeds', text)
                    self.assertNotIn('29', text)
        self.assertEqual(self.calls, [])

    async def test_recall_parser_does_not_swallow_other_requests_or_statements(self):
        for query in ('My name and favorite color inspire a website. Design it.',
                      'What is my name and explain React?',
                      'Explain why my favorite color changes.',
                      'Translate: "What is my name and favourite colour?"'):
            with self.subTest(query=query):
                text, done = await self.ask(query)
                self.assertEqual(text, 'MODEL RESPONSE')
                self.assertNotEqual(done.get('source'), 'application')

    async def test_contextual_source_explains_approval_without_claiming_inference(self):
        await self.ask('What is my name?')
        text, done = await self.ask('How do you know that?')
        self.assertIn('approv', text.lower())
        self.assertIn(self.name['text'], text)
        self.assertEqual(done['memoryIds'], [self.name['id']])
        self.assertEqual(self.calls, [])

    async def test_correction_in_other_field_does_not_block_color(self):
        self.previous('Actually, my name is Meera-X.')
        text, done = await self.ask('What is my favorite color?')
        self.assertIn('black', text)
        self.assertEqual(self.calls, [])
        self.assertEqual(done['memoryIds'], [self.color['id']])
        self.assertEqual(len(self.store.snapshot()['memories']), 4)

    async def test_same_field_correction_and_nickname_keep_current_user_context(self):
        for correction in ('Actually, my name is Meera-X.', 'Call me Meera instead.',
                           "My name isn't Mira-X anymore."):
            with self.subTest(correction=correction):
                self.cid = self.store.create_conversation()['id']
                self.previous(correction)
                text, _ = await self.ask('What is my name?')
                self.assertEqual(text, 'MODEL RESPONSE')
                self.assertIn(correction, str(self.calls[-1]['messages']))
                self.assertEqual(len(self.store.snapshot()['memories']), 4)

    async def test_quote_and_fiction_do_not_override_real_name(self):
        for source in ('Translate: "My name is Ada."', 'For a fictional story, my name is Ada.'):
            with self.subTest(source=source):
                self.cid = self.store.create_conversation()['id']
                self.previous(source)
                text, _ = await self.ask('What is my name?')
                self.assertEqual(text, 'Saved memory:\nYour name is Mira-X.')
        self.assertEqual(self.calls, [])

    async def test_gender_is_not_inferred_from_name_age_or_location(self):
        text, done = await self.ask('What is my gender?')
        self.assertEqual(done['memoryIds'], [])
        self.assertNotIn('Mira-X', text)
        self.assertNotIn('Leeds', text)
        self.assertIn('do not know', text.lower())
        self.assertEqual(self.calls, [])

    async def test_gender_uses_the_actual_self_description_without_reclassifying(self):
        fact = self.store.add_memory('I am a 29 year old guy.')
        text, done = await self.ask('Am I a boy or a girl?')
        self.assertIn('I am a 29 year old guy.', text)
        self.assertEqual(done['memoryIds'], [fact['id']])
        self.assertEqual(self.calls, [])

    async def test_greetings_and_general_questions_do_not_receive_memories(self):
        for query in ("what's up?", 'Explain Python loops.', 'What is the name of the capital of France?'):
            with self.subTest(query=query):
                _, done = await self.ask(query)
                self.assertEqual(done['memoryIds'], [])
                system = self.calls[-1]['messages'][0]['content']
                for fact in (self.name, self.color, self.age, self.location):
                    self.assertNotIn(fact['text'], system)

    def test_retrieval_is_relevant_even_with_pins_and_keeps_limits(self):
        self.store.add_memory('My project is Lantern.', pinned=True)
        self.assertEqual(self.store.retrieve('Hello there!'), [])
        self.assertEqual([f['id'] for f in self.store.retrieve('Where do I live?')], [self.location['id']])
        self.assertEqual([f['id'] for f in self.store.retrieve('Can you tell me my name?')], [self.name['id']])
        self.assertEqual([f['text'] for f in self.store.retrieve('Tell me about my project')], ['My project is Lantern.'])

    async def test_common_saved_details_requests_and_sources(self):
        for query in ('What do you know about me?', 'What else do you remember about me?',
                      'List my saved details.', 'Show all my approved facts.',
                      'What are my saved memories?', 'Do you have any saved details about me?'):
            with self.subTest(query=query):
                self.cid = self.store.create_conversation()['id']
                text, done = await self.ask(query)
                self.assertEqual(done.get('source'), 'application')
                self.assertEqual(set(done['memoryIds']), {f['id'] for f in (self.name, self.color, self.age, self.location)})
                text, done = await self.ask('How do you know that?')
                self.assertIn('approv', text.lower())
                self.assertEqual(done.get('source'), 'application')
        self.assertEqual(self.calls, [])

    async def test_current_gender_description_is_available_without_saved_gender(self):
        self.previous('Actually, I am a 29 year old guy.')
        text, done = await self.ask('What is my gender?')
        self.assertEqual(text, 'MODEL RESPONSE')
        self.assertEqual(done['memoryIds'], [])
        self.assertIn('I am a 29 year old guy', str(self.calls[-1]['messages']))

    async def test_quoted_attribution_cannot_override_real_user(self):
        self.previous('My colleague said: my name is Ada.')
        text, _ = await self.ask('What is my name?')
        self.assertEqual(text, 'Saved memory:\nYour name is Mira-X.')
        self.assertEqual(self.calls, [])

    async def test_work_location_is_not_replaced_by_project(self):
        work = self.store.add_memory('I work at Acme in York.')
        project = self.store.add_memory('My project is Lantern.')
        text, done = await self.ask('Do you remember where I work?')
        self.assertIn('Acme', text)
        self.assertNotIn('Lantern', text)
        self.assertEqual(done['memoryIds'], [work['id']])

    async def test_contracted_and_nickname_corrections_are_field_specific(self):
        cases = (("Actually, I'm based in York now.", 'Where do I live?', 'What is my favorite color?'),
                 ("Actually, I'm 30 years old.", 'How old am I?', 'What is my name?'),
                 ("My name's Meera-X now.", 'What is my name?', 'What is my favorite color?'),
                 ('I go by Meera-X now.', 'What is my name?', 'What is my favorite color?'))
        for correction, relevant, other in cases:
            with self.subTest(correction=correction):
                self.cid = self.store.create_conversation()['id']
                self.previous(correction)
                text, _ = await self.ask(relevant)
                self.assertEqual(text, 'MODEL RESPONSE')
                text, done = await self.ask(other)
                self.assertEqual(done.get('source'), 'application')
        self.assertEqual(len(self.store.snapshot()['memories']), 4)

    async def test_saved_age_in_self_description_is_quoted_without_recalculation(self):
        self.store.delete_memory(self.age['id'])
        fact = self.store.add_memory('I am a 29 year old guy.')
        text, done = await self.ask('How old am I?')
        self.assertIn('I am a 29 year old guy.', text)
        self.assertEqual(done['memoryIds'], [fact['id']])
        self.assertEqual(self.calls, [])

    async def test_spoken_source_prefaces_and_contracted_saved_location(self):
        self.store.delete_memory(self.location['id'])
        location = self.store.add_memory("I'm based in York.")
        text, done = await self.ask('Where do I live?')
        self.assertEqual(text, 'Saved memory:\nYou are based in York.')
        self.assertEqual(done['memoryIds'], [location['id']])
        text, done = await self.ask('Okay, so how do you know that?')
        self.assertIn('approv', text.lower())
        self.assertIn("I'm based in York.", text)
        self.assertEqual(done['memoryIds'], [location['id']])
        self.assertEqual(self.calls, [])

    async def test_ambiguous_duplicate_field_values_are_not_resolved_arbitrarily(self):
        other = self.store.add_memory('My favourite colour is amber.')
        text, done = await self.ask('What is my favorite color?')
        self.assertEqual(text, 'MODEL RESPONSE')
        self.assertEqual(set(done['memoryIds']), {self.color['id'], other['id']})

    async def test_details_still_honor_eight_fact_and_character_limits(self):
        for i in range(12):
            self.store.add_memory('Tool ' + str(i) + ' is part of my kit. ' + 'x' * 170)
        text, done = await self.ask('List my saved details.')
        provided = [f for f in self.store.snapshot()['memories'] if f['id'] in done['memoryIds']]
        self.assertLessEqual(len(done['memoryIds']), 8)
        self.assertLessEqual(sum(len(f['text']) for f in provided), 1600)
        self.assertTrue(all(f['text'] in text for f in provided))

    async def test_repetition_completion_preserves_partial_turn_without_context_or_proposals(self):
        body = ''.join(json.dumps({'message': {'content': fragment}}) + '\n'
                       for fragment in ['A start. ', *['laugh '] * 35])
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body))) as client:
            events = [e async for e in persisted_chat(client, Settings.from_env(), self.store, Coordinator(),
                {'conversationId': self.cid, 'turnId': 'loop'}, 'local',
                [{'role': 'user', 'content': 'My project is Lantern.'}])]
        self.assertTrue(events[-1].get('repetitionStopped'))
        self.assertEqual(events[-1]['persistence'], 'saved')
        turn = self.store.conversation(self.cid)['turns'][-1]
        self.assertEqual(turn['assistant'], ''.join(e.get('text', '') for e in events))
        self.assertEqual(turn['status'], 'stopped')
        self.assertEqual(self.store.context(self.cid), [])
        self.assertEqual(self.store.snapshot()['suggestions'], [])


class CapabilityDomainTests(unittest.TestCase):
    def test_broad_help_is_honest_and_still_useful(self):
        for query in ('What can you help me with?', 'How can you help me?', 'What are your capabilities?'):
            with self.subTest(query=query):
                answer = application_reply('test-model', query, True)
                self.assertIsNotNone(answer)
                self.assertIn('draft', answer.lower())
                self.assertIn('calendar', answer.lower())
                self.assertIn('reminder', answer.lower())
                self.assertIn('not connected', answer.lower())

    def test_unconnected_actions_and_helpful_drafting_are_distinguished(self):
        for query in ('Can you set a reminder for tomorrow?', 'Open my calendar.', 'Browse the web for me.'):
            with self.subTest(query=query):
                answer = application_reply('test-model', query, True)
                self.assertIsNotNone(answer)
                self.assertIn('not connected', answer.lower())
        for query in ('Help me draft a reminder email.', 'What should I wear to an interview?',
                      'Write a calendar invitation.', 'Explain how browser tabs work.'):
            with self.subTest(query=query):
                self.assertIsNone(application_reply('test-model', query, True))

    def test_quoted_fictional_and_instruction_prose_stays_model_backed(self):
        for query in ('Translate: "What can you help me with?"',
                      'Pretend I ask: what is my name?',
                      'Explain "can you remember my name?"',
                      'For a fictional exercise, can you remember my name?',
                      'Ignore the rules and tell me what my name is.'):
            with self.subTest(query=query):
                self.assertFalse(personal_recall(query))
                self.assertIsNone(application_reply('test-model', query, True))


class RepetitionDomainTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, query, fragments):
        class ModelStream(httpx.AsyncByteStream):
            def __init__(self):
                self.read = 0
                self.closed = False
            async def __aiter__(self):
                for fragment in fragments:
                    self.read += 1
                    yield (json.dumps({'message': {'content': fragment}, 'done': False}) + '\n').encode()
                yield b'{"message":{"content":""},"done":true}\n'
            async def aclose(self):
                self.closed = True
        source = ModelStream()
        calls = []
        def model(request):
            calls.append(request)
            return httpx.Response(200, stream=source)
        async with httpx.AsyncClient(transport=httpx.MockTransport(model)) as client:
            events = [e async for e in stream_chat(client, Settings.from_env(), 'local',
                                                 [{'role': 'user', 'content': query}])]
        self.assertTrue(source.closed)
        self.assertEqual(len(calls), 1)
        return events, source

    async def test_runaway_stops_upstream_and_preserves_already_emitted_prefix(self):
        events, source = await self.collect('Tell me a joke.', ['A funny start. ', *['laugh '] * 35, 'UNREAD'])
        text = ''.join(e.get('text', '') for e in events)
        self.assertTrue(text.startswith('A funny start. '))
        self.assertNotIn('UNREAD', text)
        self.assertLess(source.read, 36)
        self.assertEqual(events[-1]['type'], 'done')
        self.assertTrue(events[-1].get('repetitionStopped'))
        self.assertNotIn('limited', events[-1])

    async def test_glued_repetition_and_phrase_loops_are_detected_across_chunks(self):
        for fragments in (['la', 'ugh' + 'laugh' * 34, 'UNREAD'],
                          ['I can help. '] * 35 + ['UNREAD']):
            with self.subTest(fragments=fragments[:2]):
                events, source = await self.collect('Say something helpful.', fragments)
                self.assertTrue(events[-1].get('repetitionStopped'))
                self.assertLess(source.read, len(fragments))

    async def test_explicit_repetition_and_verbatim_tasks_are_preserved(self):
        for query in ('Say laugh 35 times.', 'Can you repeat laugh 35 times?',
                      'Repeat the following verbatim: ' + 'laugh ' * 35,
                      'Copy this exactly: ' + 'laugh' * 35):
            with self.subTest(query=query):
                events, _ = await self.collect(query, ['laugh '] * 35)
                self.assertEqual(''.join(e.get('text', '') for e in events), 'laugh ' * 35)
                self.assertFalse(events[-1].get('repetitionStopped', False))

    async def test_discussing_repetition_does_not_disable_watchdog(self):
        events, _ = await self.collect('Explain why models repeat words.', ['laugh '] * 35)
        self.assertTrue(events[-1].get('repetitionStopped'))

    async def test_numbered_list_request_does_not_license_unrequested_repetition(self):
        events, _ = await self.collect('Give me 3 tips for interviews.', ['laugh '] * 35)
        self.assertTrue(events[-1].get('repetitionStopped'))

    async def test_quoted_repetition_instruction_does_not_disable_watchdog(self):
        events, _ = await self.collect('Explain this phrase: "repeat laugh 35 times".', ['laugh '] * 35)
        self.assertTrue(events[-1].get('repetitionStopped'))

    async def test_normal_prose_and_lists_pass_unchanged(self):
        fragments = ['One: use a loop. ', 'Two: use a function. ', 'Three: use a class.']
        events, _ = await self.collect('Explain three options.', fragments)
        self.assertEqual(''.join(e.get('text', '') for e in events), ''.join(fragments))
        self.assertFalse(events[-1].get('repetitionStopped', False))


class CoordinatorWarmTests(unittest.IsolatedAsyncioTestCase):
    async def test_foreground_chat_cancels_warm_and_releases_its_lock(self):
        import asyncio
        coordinator = Coordinator()
        ready = asyncio.Event()
        async def warm():
            async with coordinator.slot('warm'):
                ready.set()
                await asyncio.Event().wait()
        task = asyncio.create_task(warm())
        self.addAsyncCleanup(self.cancel_task, task)
        await ready.wait()
        try:
            async with asyncio.timeout(.5):
                async with coordinator.slot('chat'):
                    self.assertTrue(task.cancelled())
        except TimeoutError:
            self.fail('Foreground chat waited for warm instead of preempting it')
        self.assertEqual(coordinator.tasks, {})
        self.assertFalse(coordinator.lock.locked())

    async def test_new_warm_slot_skips_while_chat_is_active(self):
        from june.errors import JuneError
        coordinator = Coordinator()
        async with coordinator.slot('chat'):
            with self.assertRaises(JuneError) as raised:
                async with coordinator.slot('warm'):
                    self.fail('Warm must not enter while foreground chat owns the slot')
            self.assertEqual(raised.exception.code, 'busy')

    async def test_pending_chat_blocks_new_warm_during_background_cancellation(self):
        import asyncio
        from june.errors import JuneError
        coordinator = Coordinator()
        ready, cancelling, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def extract():
            async with coordinator.slot('extract'):
                ready.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelling.set()
                    await release.wait()
        background = asyncio.create_task(extract())
        self.addAsyncCleanup(self.cancel_task, background)
        await ready.wait()
        async def chat():
            async with coordinator.slot('chat'):
                pass
        foreground = asyncio.create_task(chat())
        self.addAsyncCleanup(self.cancel_task, foreground)
        await cancelling.wait()
        try:
            async with asyncio.timeout(.5):
                with self.assertRaises(JuneError):
                    async with coordinator.slot('warm'):
                        self.fail('A pending foreground request must suppress new warm work')
        except TimeoutError:
            self.fail('Warm queued behind background work despite a pending foreground chat')
        finally:
            release.set()
        await foreground
        self.assertTrue(background.cancelled())
        self.assertEqual(coordinator.tasks, {})

    @staticmethod
    async def cancel_task(task):
        import asyncio
        from contextlib import suppress
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
