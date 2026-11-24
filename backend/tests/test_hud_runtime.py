"""HUD metadata contracts, using synthetic stores and a fake Ollama transport."""
from dataclasses import replace
import json
import tempfile
import unittest
from unittest.mock import patch

import httpx

from june.app import app
from june import chat
from june.config import Settings
from june.memory import Store
from june.memory_service import Coordinator


class ModelParametersTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cache = patch.object(chat, '_PARAMETERS', {})
        self.cache.start()
        self.addCleanup(self.cache.stop)
        self.settings = replace(Settings.from_env(), model='fixture-a')

    async def test_cache_keeps_each_models_count_when_switching_back(self):
        requests = []

        def ollama(request):
            model = json.loads(request.content)['model']
            requests.append((request.method, request.url.path, model))
            return httpx.Response(200, json={'model_info': {
                'general.parameter_count': {'fixture-a': 4000, 'fixture-b': 8000}[model]}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(ollama)) as client:
            values = [await chat.model_parameters(client, replace(self.settings, model=model))
                      for model in ('fixture-a', 'fixture-a', 'fixture-b', 'fixture-a')]
        self.assertEqual(values, [4000, 4000, 8000, 4000])
        self.assertEqual(requests, [('POST', '/api/show', 'fixture-a'), ('POST', '/api/show', 'fixture-b')])

    async def test_invalid_parameter_counts_never_become_display_metadata(self):
        for count in (True, False, 0, -1, 4.5, '4000', None):
            with self.subTest(count=count), patch.object(chat, '_PARAMETERS', {}):
                async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda _: httpx.Response(200, json={'model_info': {'general.parameter_count': count}})
                )) as client:
                    self.assertIsNone(await chat.model_parameters(client, self.settings))

    async def test_temporary_show_failure_does_not_poison_the_cache(self):
        for failure in ('offline', 'http', 'json'):
            calls = []

            def ollama(request):
                calls.append(request.url.path)
                if len(calls) == 1:
                    if failure == 'offline':
                        raise httpx.ConnectError('fixture outage', request=request)
                    if failure == 'http':
                        return httpx.Response(503)
                    return httpx.Response(200, text='invalid JSON')
                return httpx.Response(200, json={'model_info': {'general.parameter_count': 4000}})

            with self.subTest(failure=failure), patch.object(chat, '_PARAMETERS', {}):
                async with httpx.AsyncClient(transport=httpx.MockTransport(ollama)) as client:
                    self.assertIsNone(await chat.model_parameters(client, self.settings))
                    self.assertEqual(await chat.model_parameters(client, self.settings), 4000)
                    self.assertEqual(await chat.model_parameters(client, self.settings), 4000)
                self.assertEqual(calls, ['/api/show', '/api/show'])


class HudHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.settings = replace(Settings.from_env(), model='fixture-a')
        self.requests = []
        self.show_response = httpx.Response(200, json={'model_info': {'general.parameter_count': 4000}})

        def ollama(request):
            self.requests.append((request.method, request.url.path))
            if request.url.path == '/api/tags':
                return httpx.Response(200, json={'models': [{'name': 'fixture-a'}]})
            if request.url.path == '/api/show':
                return self.show_response
            if request.url.path == '/api/chat':
                return httpx.Response(200, text='{"message":{"content":"A synthetic answer."},"done":true}\n')
            raise AssertionError(f'Unexpected model request: {request.url.path}')

        self.model = httpx.AsyncClient(transport=httpx.MockTransport(ollama))
        self.addAsyncCleanup(self.model.aclose)
        # Exercise the real routes/middleware without starting voice/model workers.
        self.state = patch.multiple(app.state, settings=self.settings, client=self.model,
                                    store=self.store, coordinator=Coordinator(), knowledge=None, create=True)
        self.state.start()
        self.addCleanup(self.state.stop)
        self.cache = patch.object(chat, '_PARAMETERS', {})
        self.cache.start()
        self.addCleanup(self.cache.stop)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=self.settings.backend)
        self.addAsyncCleanup(self.client.aclose)

    async def test_status_adds_cached_parameters_but_readiness_survives_bad_metadata(self):
        first = await self.client.get('/api/status')
        second = await self.client.get('/api/status')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()['parameters'], 4000)
        self.assertEqual(second.json()['parameters'], 4000)
        self.assertEqual(self.requests, [('GET', '/api/tags'), ('POST', '/api/show'), ('GET', '/api/tags')])
        chat._PARAMETERS.clear()
        self.show_response = httpx.Response(503)
        response = await self.client.get('/api/status')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['state'], 'ready')
        self.assertNotIn('parameters', response.json())

    async def test_fresh_and_saved_chat_turns_never_query_show_even_with_a_cold_cache(self):
        cid = self.store.create_conversation()['id']
        for fields in ({'temporary': True}, {'conversationId': cid, 'turnId': 'fixture-turn'}):
            response = await self.client.post('/api/chat', json={
                **fields, 'messages': [{'role': 'user', 'content': 'Describe a triangle briefly.'}]})
            self.assertEqual(response.status_code, 200)
            events = [json.loads(line) for line in response.text.splitlines()]
            self.assertEqual(events[-1]['type'], 'done')
            self.assertEqual(''.join(e.get('text', '') for e in events), 'A synthetic answer.')
        self.assertEqual(self.requests.count(('POST', '/api/chat')), 2)
        self.assertIn(('GET', '/api/tags'), self.requests)
        self.assertNotIn(('POST', '/api/show'), self.requests)
        self.assertEqual(self.store.conversation(cid)['turns'][0]['status'], 'complete')

    async def test_graph_route_only_exposes_ids_and_filters_deleted_or_incomplete_citations(self):
        cid = self.store.create_conversation('PRIVATE conversation title')['id']
        memory = self.store.add_memory('I prefer PRIVATE memory text.', source=cid)
        # Seed the same persisted schema used by document chat; no embedding/model call.
        with self.store.db() as db:
            db.execute("INSERT INTO documents(id,name,hash,status,message,generation) VALUES(?,?,?,'ready',?,?)",
                       ('doc-live', 'PRIVATE filename.txt', 'fixture-hash', 'PRIVATE status', 'generation'))
        citation = {'documentId': 'doc-live', 'name': 'PRIVATE filename.txt', 'quote': 'PRIVATE passage'}
        for tid, status, citations in (
            ('complete', 'complete', [citation, citation, {'documentId': 'doc-deleted'}]),
            ('stopped', 'stopped', [{'documentId': 'doc-live', 'quote': 'PRIVATE stopped reply'}]),
            ('malformed', 'complete', 'invalid JSON'),
        ):
            turn_cid = cid if tid == 'complete' else self.store.create_conversation()['id']
            self.store.start_turn(turn_cid, tid, 'PRIVATE question', self.store.revision())
            self.store.finish_turn(tid, 'PRIVATE assistant reply', status)
            with self.store.db() as db:
                db.execute('UPDATE turns SET citations=? WHERE id=?',
                           (citations if isinstance(citations, str) else json.dumps(citations), tid))
        response = await self.client.get('/api/library/graph')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            'citations': [{'conversation': cid, 'documentId': 'doc-live'}],
            'memories': [{'id': memory['id'], 'source': cid}],
        })
        self.assertNotIn('PRIVATE', response.text)
