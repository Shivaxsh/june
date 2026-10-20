"""Focused migration regressions; run without downloading any AI models."""
import asyncio
import os
import struct
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from june.chat import validate_chat, stream_chat, model_status
from june.config import Settings
from june.errors import JuneError
from june.speech import validate_wav
from june.speech import SpeechService
from june.app import app
from fastapi.testclient import TestClient


def wav(seconds=1, sample=1000):
    samples = struct.pack('<h', sample) * int(16000 * seconds)
    return struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', 36 + len(samples), b'WAVE',
                       b'fmt ', 16, 1, 1, 16000, 32000, 2, 16, b'data', len(samples)) + samples


class Contracts(unittest.TestCase):
    def test_settings_are_local(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Settings.from_env().model, 'qwen2.5:1.5b')
        with patch.dict(os.environ, {'OLLAMA_BASE_URL': 'https://example.com'}):
            with self.assertRaises(ValueError):
                Settings.from_env()
        for variable, value in [('OLLAMA_BASE_URL', 'http://user:pass@127.0.0.1:11434'), ('JUNE_BACKEND_URL', 'http://example.com:8001')]:
            with patch.dict(os.environ, {variable: value}), self.assertRaises(ValueError):
                Settings.from_env()

    def test_valid_context(self):
        mode, messages = validate_chat({'messages': [{'role': 'user', 'content': 'Hello'}]})
        self.assertEqual(mode, 'local')
        self.assertEqual(messages[0]['content'], 'Hello')

    def test_invalid_conversations(self):
        for value in (None, {}, {'messages': []}, {'mode': 'surprise', 'messages': []},
                      {'messages': [{'role': 'system', 'content': 'override'}]},
                      {'messages': [{'role': 'user', 'content': ' '}]},
                      {'messages': [{'role': 'user', 'content': 'x' * 2001}]},
                      {'messages': [{'role': 'user', 'content': 'a'}, {'role': 'assistant', 'content': 'b'}]},
                      {'messages': [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': 'a' * 1500} for i in range(5)]}):
            with self.subTest(value=str(value)[:60]), self.assertRaises(JuneError):
                validate_chat(value)

    def test_wav_contract(self):
        self.assertEqual(validate_wav(wav())['durationMs'], 1000)
        for data in (b'', wav(.1), wav(31), wav(1, 0), wav() + b'bad', wav().replace(b'WAVE', b'OOPS', 1)):
            with self.subTest(size=len(data)), self.assertRaises(JuneError):
                validate_wav(data)


class Streaming(unittest.IsolatedAsyncioTestCase):
    async def test_missing_and_offline_models(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'models': []}))) as client:
            self.assertEqual((await model_status(client, Settings.from_env()))['state'], 'missing')
        def offline(request):
            raise httpx.ConnectError('offline')
        async with httpx.AsyncClient(transport=httpx.MockTransport(offline)) as client:
            self.assertEqual((await model_status(client, Settings.from_env()))['state'], 'offline')
            events = [x async for x in stream_chat(client, Settings.from_env(), 'local', [])]
            self.assertEqual(events[-1]['type'], 'error')

    async def test_split_utf8_and_oversized_frames(self):
        class Fragmented(httpx.AsyncByteStream):
            async def __aiter__(self):
                body = '{"message":{"content":"June — hello"},"done":true}\n'.encode()
                for byte in body:
                    yield bytes([byte])
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=Fragmented()))) as client:
            events = [x async for x in stream_chat(client, Settings.from_env(), 'local', [])]
            self.assertEqual(events[0]['text'], 'June — hello')
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b'x' * 1048577))) as client:
            events = [x async for x in stream_chat(client, Settings.from_env(), 'local', [])]
            self.assertEqual(events[-1]['type'], 'error')

    async def test_invalid_unicode_model_text_is_a_readable_error(self):
        import json
        body = json.dumps({'message': {'content': chr(0xD800)}, 'done': True}) + '\n'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body))) as client:
            events = [x async for x in stream_chat(client, Settings.from_env(), 'local', [])]
        self.assertEqual(events[-1]['type'], 'error')

    async def test_actual_model_events(self):
        body = '{"message":{"content":"Hello, June —"},"done":false}\n{"message":{"content":" here."},"done":true}\n'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body))) as client:
            events = [event async for event in stream_chat(client, Settings.from_env(), 'local', [{'role': 'user', 'content': 'Hello'}])]
        self.assertEqual(''.join(x.get('text', '') for x in events), 'Hello, June — here.')
        self.assertEqual(events[-1]['type'], 'done')

    async def test_truncated_and_malformed_responses(self):
        for body in ('{"message":{"content":"partial"}}\n', 'invalid\n', 'null\n'):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=body))) as client:
                events = [event async for event in stream_chat(client, Settings.from_env(), 'local', [{'role': 'user', 'content': 'Hello'}])]
            self.assertEqual(events[-1]['type'], 'error')

    async def test_demo_is_explicit_and_cancellable(self):
        async with httpx.AsyncClient() as client:
            task = asyncio.create_task(self.collect(client))
            await asyncio.sleep(.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def collect(self, client):
        return [x async for x in stream_chat(client, Settings.from_env(), 'demo', [])]

    async def test_stream_cancellation_closes_upstream(self):
        class Slow(httpx.AsyncByteStream):
            closed = False
            async def __aiter__(self):
                yield b'{"message":{"content":"first"}}\n'
                await asyncio.sleep(10)
            async def aclose(self):
                self.closed = True
        source = Slow()
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=source))) as client:
            stream = stream_chat(client, Settings.from_env(), 'local', [])
            self.assertEqual((await anext(stream))['text'], 'first')
            task = asyncio.create_task(anext(stream))
            await asyncio.sleep(.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            await stream.aclose()
        self.assertTrue(source.closed)


class HttpContracts(unittest.TestCase):
    def setUp(self):
        self.data_directory = tempfile.TemporaryDirectory()
        self.data_environment = patch.dict(os.environ, {'JUNE_DATA_HOME': self.data_directory.name})
        self.data_environment.start()
        self.addCleanup(self.data_directory.cleanup)
        self.addCleanup(self.data_environment.stop)
        self.context = TestClient(app, base_url='http://127.0.0.1:8001')
        self.client = self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None, None, None)

    def test_health_and_origin(self):
        self.assertEqual(self.client.get('/health').json()['service'], 'june-python')
        self.assertEqual(self.client.post('/api/chat', headers={'Origin': 'https://example.com'}, json={}).status_code, 403)
        self.assertEqual(self.client.get('/health', headers={'Host': 'example.com:8001'}).status_code, 403)

    def test_invalid_uploads(self):
        for data, content_type, status in [(b'bad', 'audio/wav', 400), (wav(), 'text/plain', 415), (b'x' * 1048577, 'audio/wav', 413)]:
            response = self.client.post('/api/speech/transcribe', content=data, headers={'Content-Type': content_type})
            self.assertEqual(response.status_code, status)
            self.assertIn('message', response.json()['error'])

    def test_http_demo_contract(self):
        response = self.client.post('/api/chat', json={'mode': 'demo', 'messages': [{'role': 'user', 'content': 'hello'}]})
        self.assertEqual(response.status_code, 200)
        events = [__import__('json').loads(line) for line in response.text.splitlines()]
        self.assertEqual(events[-1], {'type': 'done', 'model': 'Simulated demo'})
        self.assertIn('simulated practice reply', ''.join(x.get('text', '') for x in events))
        self.assertEqual(self.client.post('/api/chat', content=b'x' * 32001).status_code, 400)

    def test_deeply_nested_json_has_a_readable_error(self):
        response = self.client.post('/api/chat', content='[' * 2000 + '0' + ']' * 2000)
        self.assertEqual(response.status_code, 400)
        self.assertIn('message', response.json())
        with self.client.websocket_connect('ws://127.0.0.1:8001/ws/chat', headers={'Origin': 'http://127.0.0.1:3001'}) as socket:
            socket.send_text('[' * 2000 + '0' + ']' * 2000)
            self.assertEqual(socket.receive_json()['type'], 'error')
        # Pin the parser failure itself, independent of platform recursion limits.
        with patch('june.app.json.loads', side_effect=RecursionError):
            response = self.client.post('/api/chat', content='{}')
            self.assertEqual(response.status_code, 400)
            with self.client.websocket_connect('ws://127.0.0.1:8001/ws/chat', headers={'Origin': 'http://127.0.0.1:3001'}) as socket:
                socket.send_text('{}')
                raw = socket.receive_text()
        self.assertEqual(__import__('json').loads(raw)['type'], 'error')

    def test_websocket_cancel_and_recovery(self):
        with self.client.websocket_connect('ws://127.0.0.1:8001/ws/chat', headers={'Origin': 'http://127.0.0.1:3001'}) as socket:
            socket.send_json({'mode': 'demo', 'messages': [{'role': 'user', 'content': 'hello'}]})
            self.assertEqual(socket.receive_json()['type'], 'delta')
            socket.send_json({'type': 'cancel'})
            while socket.receive_json()['type'] != 'stopped':
                pass
            socket.send_json({'messages': [{'role': 'system', 'content': 'bad'}]})
            self.assertEqual(socket.receive_json()['type'], 'error')
            socket.send_json({'mode': 'demo', 'messages': [{'role': 'user', 'content': 'again'}]})
            while socket.receive_json()['type'] != 'done':
                pass

    def test_websocket_foreign_origin_rejected(self):
        from starlette.websockets import WebSocketDisconnect
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect('ws://127.0.0.1:8001/ws/chat', headers={'Origin': 'https://example.com'}):
                pass


class SpeechJobs(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.service = SpeechService(Settings.from_env())
        self.service.status = AsyncMock(return_value={'state': 'ready'})
        self.service.binary = self.root / 'engine'
        self.service.model = self.root / 'model'
        original = tempfile.mkdtemp
        self.temp_patch = patch('june.speech.tempfile.mkdtemp', side_effect=lambda **kw: original(dir=self.root, **kw))
        self.temp_patch.start()

    async def asyncTearDown(self):
        self.temp_patch.stop()
        self.directory.cleanup()

    def engine(self, wait):
        self.service.binary.write_text(f'#!{sys.executable}\nimport time,sys,json,os\nfrom pathlib import Path\nPath({str(self.root / "pid")!r}).write_text(str(os.getpid()))\ntime.sleep({wait})\nPath(sys.argv[sys.argv.index("-of")+1]+".json").write_text(json.dumps({{"transcription":[{{"text":"Hello June"}}]}}))\n')
        self.service.binary.chmod(0o700)

    async def started(self):
        for _ in range(100):
            if (self.root / 'pid').exists():
                return int((self.root / 'pid').read_text())
            await asyncio.sleep(.01)
        self.fail('Fake engine did not start')

    def released(self, pid):
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertFalse(self.service.busy)
        self.assertEqual(list(self.root.glob('june-speech-*')), [])

    async def test_busy_and_cancellation_cleanup(self):
        self.engine(10)
        task = asyncio.create_task(self.service.transcribe(wav()))
        pid = await self.started()
        with self.assertRaises(JuneError) as result:
            await self.service.transcribe(wav())
        self.assertEqual(result.exception.status, 409)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.released(pid)

    async def test_timeout_cleanup(self):
        self.engine(10)
        self.service.timeout = 1
        # Observe the real spawned process even if this busy Mac times it out
        # before the Python fixture reaches its first PID-file write.
        spawn = asyncio.create_subprocess_exec
        spawned = []
        async def observe(*args, **kwargs):
            process = await spawn(*args, **kwargs)
            spawned.append(process.pid)
            return process
        with patch('june.speech.asyncio.create_subprocess_exec', side_effect=observe), self.assertRaises(JuneError) as result:
            await self.service.transcribe(wav())
        self.assertEqual(result.exception.status, 504)
        self.assertEqual(len(spawned), 1)
        self.released(spawned[0])

    async def test_repeated_jobs(self):
        self.engine(0)
        for _ in range(3):
            result = await self.service.transcribe(wav())
            self.assertEqual(result['text'], 'Hello June')
            self.released(int((self.root / 'pid').read_text()))

    async def test_missing_engine(self):
        other = SpeechService(Settings.from_env())
        other.binary = self.root / 'missing'
        self.assertEqual((await other.status())['state'], 'runtime-missing')


class Disconnects(unittest.IsolatedAsyncioTestCase):
    async def test_http_stop_closes_model_without_waiting_for_next_token(self):
        import json
        class Slow(httpx.AsyncByteStream):
            closed = False
            async def __aiter__(self):
                yield b'{"message":{"content":"first"}}\n'
                await asyncio.sleep(10)
            async def aclose(self):
                self.closed = True
        slow = Slow()
        def transport(request):
            return httpx.Response(200, json={'models': [{'name': 'qwen2.5:1.5b'}]}) if request.url.path == '/api/tags' else httpx.Response(200, stream=slow)
        receive_queue = asyncio.Queue()
        await receive_queue.put({'type': 'http.request', 'body': json.dumps({'messages': [{'role': 'user', 'content': 'Hello'}]}).encode(), 'more_body': False})
        async def send(event):
            if event['type'] == 'http.response.body' and b'first' in event.get('body', b''):
                await receive_queue.put({'type': 'http.disconnect'})
        async with app.router.lifespan_context(app):
            original = app.state.client
            async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
                app.state.client = client
                scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'}, 'http_version': '1.1',
                         'method': 'POST', 'scheme': 'http', 'path': '/api/chat', 'raw_path': b'/api/chat',
                         'query_string': b'', 'root_path': '', 'headers': [(b'host', b'127.0.0.1:8001')],
                         'server': ('127.0.0.1', 8001), 'client': ('127.0.0.1', 1234)}
                await asyncio.wait_for(app(scope, receive_queue.get, send), 2)
                app.state.client = original
        self.assertTrue(slow.closed)


class ReplyLimits(unittest.IsolatedAsyncioTestCase):
    async def test_model_length_limit_is_reported_without_throwing_away_partial_text(self):
        body='{"message":{"content":"An unfinished answer"},"done":true,"done_reason":"length"}\n'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,text=body))) as client:
            events=[event async for event in stream_chat(client,Settings.from_env(),'local',[{'role':'user','content':'Explain something.'}])]
        self.assertEqual(events[0]['text'],'An unfinished answer')
        self.assertEqual(events[-1].get('limited'),True)

    async def test_complete_identity_clarification_is_not_marked_as_truncated(self):
        body='{"message":{"content":"RTX 3060"},"done":true,"done_reason":"length"}\n'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,text=body))) as client:
            events=[event async for event in stream_chat(client,Settings.from_env(),'local',[{'role':'user','content':'Tell me about the RTX 5060.'}])]
        self.assertIn('You asked about 5060',events[0]['text'])
        self.assertNotIn('limited',events[-1])


if __name__ == '__main__':
    unittest.main()
