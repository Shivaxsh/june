"""Personal recall routing and evidence boundaries; isolated SQLite, no live model."""
import json
import tempfile
import unittest

import httpx

from june.app_info import PREFIX, application_reply
from june.config import Settings
from june.memory import Store
from june.memory_service import Coordinator, persisted_chat


NAME_QUERY = 'Can you do you remember what my name is?'
COLOR_QUERY = 'what is my favorite color?'


class PersonalRecallRoutingTests(unittest.TestCase):
    def test_personal_recall_bypasses_generic_memory_capability(self):
        # Losing the recall exemption sends disfluent questions to app information.
        queries = (
            NAME_QUERY,
            'Okay, so can you do you remember what my name is?',
            'Can you remember what my name is?',
            'Could you remember what my favourite colour is?',
            'Will you remember where I live?',
            'Can you, do you still remember my name?',
            'Can you tell me, do you remember my city?',
            'Do you remember what my project is?',
            'Can you remember my name?',
            'What is my name?',
            COLOR_QUERY,
        )
        for query in queries:
            for enabled in (True, False):
                with self.subTest(query=query, memory_enabled=enabled):
                    self.assertIsNone(application_reply('test-model', query, enabled))

    def test_generic_or_future_memory_requests_keep_application_truth(self):
        queries = (
            'Can you remember information I give you?',
            'Will you remember my things?',
            'How does your memory work?',
            'Do you have saved memories?',
            'Can you remember my name if I tell you?',
            'Can you remember that my name is Mira?',
        )
        for query in queries:
            with self.subTest(query=query):
                answer = application_reply('test-model', query, True)
                self.assertTrue(answer.startswith(PREFIX))
                self.assertIn('approve', answer)
                self.assertIn('30 days', answer)
                temporary = application_reply('test-model', query, False)
                self.assertIn('not enabled', temporary)

    def test_other_application_and_quoted_question_boundaries(self):
        for query in ('Who are you?', 'Can you order groceries?', 'Book movie tickets.'):
            with self.subTest(query=query):
                self.assertTrue(application_reply('test-model', query, True).startswith(PREFIX))
        for query in ('What is React?', 'Translate: do you remember my name?',
                      'Explain the phrase "what is my favorite color?"'):
            with self.subTest(query=query):
                self.assertIsNone(application_reply('test-model', query, True))


class PersonalRecallEvidenceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.now = 10000000
        self.store = Store(directory.name, lambda: self.now)
        self.settings = Settings.from_env()

    async def collect(self, cid, query, tid='recall', temporary=False):
        bodies = []

        def model(request):
            bodies.append(json.loads(request.content))
            return httpx.Response(200, text='{"message":{"content":"MODEL RESPONSE"},"done":true}\n')

        value = {'temporary': True} if temporary else {'conversationId': cid, 'turnId': tid}
        async with httpx.AsyncClient(transport=httpx.MockTransport(model)) as client:
            events = [e async for e in persisted_chat(
                client, self.settings, self.store, Coordinator(), value, 'local',
                [{'role': 'user', 'content': query}])]
        self.assertEqual(''.join(e.get('text', '') for e in events), 'MODEL RESPONSE')
        self.assertEqual(len(bodies), 1)
        self.assertEqual(events[-1]['type'], 'done')
        self.assertNotEqual(events[-1].get('source'), 'application')
        self.assertEqual(bodies[0]['messages'][-1], {'role': 'user', 'content': query})
        return bodies[0]['messages'], events[-1]

    async def test_disfluent_recall_receives_approved_fact_and_latest_context(self):
        # The routing bug skips retrieval entirely, even when an approved fact exists.
        memory = self.store.add_memory('My name is Mira-X.')
        cid = self.store.create_conversation()['id']
        self.store.start_turn(cid, 'correction', 'Actually, my name is Meera-X.', self.store.revision())
        self.store.finish_turn('correction', 'Understood.', 'complete')
        messages, ending = await self.collect(cid, NAME_QUERY)
        self.assertIn('My name is Mira-X.', messages[0]['content'])
        self.assertEqual(messages[1:3], [
            {'role': 'user', 'content': 'Actually, my name is Meera-X.'},
            {'role': 'assistant', 'content': 'Understood.'}])
        self.assertEqual(ending['memoryIds'], [memory['id']])

    async def test_yesterdays_pending_facts_do_not_become_approved_recall(self):
        old_cid = self.store.create_conversation()['id']
        source = 'My name is Mira-X. I live in Leeds. My project is Lantern. My favorite color is amber.'
        self.store.start_turn(old_cid, 'yesterday', source, self.store.revision())
        self.store.finish_turn('yesterday', 'Understood.', 'complete', propose=True)
        pending = self.store.snapshot()['suggestions']
        self.assertEqual([s['text'] for s in pending], [
            'My name is Mira-X', 'I live in Leeds', 'My project is Lantern'])
        self.now += 86400
        for i, query in enumerate((NAME_QUERY, COLOR_QUERY)):
            with self.subTest(query=query):
                cid = self.store.create_conversation()['id']
                messages, ending = await self.collect(cid, query, tid=f'recall-{i}')
                self.assertEqual(ending['memoryIds'], [])
                self.assertEqual(len(messages), 2)
                for fact in ('Mira-X', 'Leeds', 'Lantern', 'amber'):
                    self.assertNotIn(fact, messages[0]['content'])
        self.assertEqual(self.store.snapshot()['memories'], [])
        self.assertEqual(self.store.snapshot()['suggestions'], pending)

    async def test_unapproved_color_in_current_context_remains_available(self):
        # Zero approved facts does not imply that recent user context is empty.
        cid = self.store.create_conversation()['id']
        source = 'My favorite color is amber.'
        self.store.start_turn(cid, 'color', source, self.store.revision())
        self.store.finish_turn('color', 'Understood.', 'complete', propose=True)
        messages, ending = await self.collect(cid, COLOR_QUERY)
        self.assertEqual(messages[1], {'role': 'user', 'content': source})
        self.assertNotIn('amber', messages[0]['content'])
        self.assertEqual(ending['memoryIds'], [])
        self.assertEqual(self.store.snapshot()['memories'], [])
        self.assertEqual(len(self.store.snapshot()['suggestions']), 1)

    async def test_temporary_recall_does_not_load_approved_or_pending_memory(self):
        self.store.add_memory('My name is Mira-X.')
        messages, ending = await self.collect(None, NAME_QUERY, temporary=True)
        self.assertEqual(ending['memoryIds'], [])
        self.assertEqual(ending['persistence'], 'temporary')
        self.assertNotIn('Mira-X', messages[0]['content'])
        self.assertEqual(self.store.snapshot()['conversations'], [])
