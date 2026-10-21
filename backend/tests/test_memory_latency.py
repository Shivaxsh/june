"""Extraction latency regressions with synthetic turns and isolated SQLite."""
import json
import tempfile
import unittest

import httpx

from june.chat import stream_chat
from june.config import Settings
from june.memory import Store
from june.memory_service import Coordinator, extract


class MemoryLatencyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = Store(self.directory.name)
        self.cid = self.store.create_conversation()['id']
        self.settings = Settings.from_env()

    def completed(self, source, tid='turn', propose=False):
        self.store.start_turn(self.cid, tid, source, self.store.revision())
        self.store.finish_turn(tid, 'Understood.', 'complete', propose=propose)
        return tid

    async def test_pure_questions_greetings_and_nonpersonal_prose_need_no_model(self):
        # Removing the eligibility guard would send these completed turns to Ollama.
        sources = (
            'What current NVIDIA generation is available, and what is the latest model?',
            'Explain JavaScript async and await.',
            'What is the difference between a CPU and a GPU?',
            'Hello June!',
            'Hi, how are you?',
            'Thanks for the explanation.',
            'RTX cards support CUDA.',
            'The dog is a collie.',
            'I wanted to ask if there’s a 3090 NVIDIA graphics card available in India right now in 2026.',
            'Okay, so I wanted to know that which current generation is in production of NVIDIA graphics card.',
            'I mean, explain React.js in one short sentence.',
        )
        def no_model(request):
            self.fail('Nonpersonal turn must not incur an extraction inference')
        async with httpx.AsyncClient(transport=httpx.MockTransport(no_model)) as client:
            for i, source in enumerate(sources):
                with self.subTest(source=source):
                    tid = self.completed(source, str(i))
                    await extract(client, self.settings, self.store, Coordinator(), self.cid, tid)
        self.assertEqual(self.store.snapshot()['suggestions'], [])
        self.assertEqual(self.store.snapshot()['memories'], [])

    async def test_personal_clauses_still_reach_validated_model_fallback(self):
        # A question-mark ban or an explicit-pattern allowlist would lose these.
        cases = (
            ('I grew up in Leeds.', 'I grew up in Leeds', []),
            ('Our dog is a collie.', 'Our dog is a collie', ['Our dog is a collie']),
            ('I live in Leeds, can you remember that?', 'I live in Leeds', ['I live in Leeds']),
            ('Can you explain GPUs? I grew up in Leeds.', 'I grew up in Leeds', []),
            ('Since last autumn I am learning Rust.', 'I am learning Rust', ['I am learning Rust']),
            ('We are building a garden.', 'We are building a garden', ['We are building a garden']),
            ('I’m learning Rust.', 'I’m learning Rust', ['I’m learning Rust']),
            ('I wanted to learn React.', 'I wanted to learn React', []),
            ('I wanted to ask if our puppy is a spaniel.', 'our puppy is a spaniel', ['our puppy is a spaniel']),
            ('I mean, our cat is a tabby.', 'our cat is a tabby', ['our cat is a tabby']),
            ('Okay, so I wanted to know where I grew up.', 'I grew up', []),
        )
        for i, (source, clause, expected) in enumerate(cases):
            with self.subTest(source=source):
                requests = []
                def model(request):
                    body = json.loads(request.content)
                    requests.append(body)
                    self.assertEqual(body['messages'][-1]['content'], source)
                    return httpx.Response(200, json={'message': {'content': json.dumps({
                        'suggestions': [{'text': clause, 'quote': clause}]
                    })}})
                tid = self.completed(source, f'personal-{i}')
                async with httpx.AsyncClient(transport=httpx.MockTransport(model)) as client:
                    await extract(client, self.settings, self.store, Coordinator(), self.cid, tid)
                self.assertEqual(len(requests), 1)
                pending = [s['text'] for s in self.store.snapshot()['suggestions'] if s['turn']==tid]
                # The existing validator rejects "grew up" alone; preserve that
                # contract while ensuring ambiguous prose still gets extracted.
                self.assertEqual(pending, expected)
                self.assertEqual(self.store.snapshot()['memories'], [])

    async def test_exact_suggestions_stay_immediate_idempotent_and_pending(self):
        tid = self.completed('My name is Mira. I live in Leeds.', propose=True)
        initial = self.store.snapshot()['suggestions']
        self.assertEqual([s['text'] for s in initial], ['My name is Mira', 'I live in Leeds'])
        def no_model(request):
            self.fail('Exact suggestions must not invoke the model')
        async with httpx.AsyncClient(transport=httpx.MockTransport(no_model)) as client:
            for _ in range(2):
                await extract(client, self.settings, self.store, Coordinator(), self.cid, tid)
        self.assertEqual(self.store.snapshot()['suggestions'], initial)
        self.assertEqual(self.store.snapshot()['memories'], [])

    async def test_extraction_reuses_chat_context_capacity(self):
        # A lower extraction capacity forces a reload on the installed CPU runner.
        bodies = []
        def model(request):
            body = json.loads(request.content)
            bodies.append(body)
            if body['stream']:
                return httpx.Response(200, text='{"message":{"content":"A GPU processes graphics."},"done":true}\n')
            return httpx.Response(200, json={'message': {'content': '{"suggestions":[]}'}})
        tid = self.completed('Our dog is a collie.')
        async with httpx.AsyncClient(transport=httpx.MockTransport(model)) as client:
            events = [e async for e in stream_chat(client, self.settings, 'local', [
                {'role': 'user', 'content': 'What is a GPU?'}])]
            await extract(client, self.settings, self.store, Coordinator(), self.cid, tid)
        self.assertEqual(events[-1]['type'], 'done')
        self.assertEqual(len(bodies), 2)
        self.assertEqual(bodies[1]['options']['num_ctx'], bodies[0]['options']['num_ctx'])
        self.assertEqual(bodies[1]['model'], bodies[0]['model'])
        self.assertEqual(bodies[1]['options']['temperature'], 0)
        self.assertEqual(bodies[1]['format'], 'json')
        self.assertEqual(bodies[1]['think'], False)
