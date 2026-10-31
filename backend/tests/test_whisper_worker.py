"""Real pipe/process tests: no model, database, audio fixture, or network needed."""
import asyncio
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

from june.errors import JuneError
try:
    from june.whisper_worker import WhisperWorker
except ImportError:
    WhisperWorker = None


def audio():
    pcm = struct.pack('<h', 1500) * 8000
    return b'RIFF' + struct.pack('<I', len(pcm) + 36) + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, 1, 16000, 32000, 2, 16) + b'data' + struct.pack('<I', len(pcm)) + pcm


# This peer exercises the supervisor with actual subprocess pipes. Inference is
# deliberately absent; native protocol tests cover the real C++ implementation.
PEER = r'''
import json,sys,os,time,threading
mode=sys.argv[1]
lock=threading.Lock()
def emit(value):
    with lock: print(json.dumps(value),flush=True)
if mode=='startup-hang': time.sleep(30)
emit({'type':'ready','protocol':1,'model':'base.en'})
for line in sys.stdin.buffer:
    command=json.loads(line)
    kind=command['type']; identity=command['id']
    if kind=='cancel':
        if mode!='ignore-cancel': emit({'type':'cancelled','id':identity})
        continue
    data=sys.stdin.buffer.read(command['bytes'])
    if mode=='eof': sys.exit(0)
    if mode=='malformed': print('{broken',flush=True);continue
    if mode=='oversized': print('x'*70000,flush=True);continue
    if mode=='flood':
        while True: os.write(1,b'x'*8192)
    if mode=='hang' or mode=='ignore-cancel': continue
    if mode=='stale': emit({'type':'result','id':'stale-id','text':'Wrong turn','confidence':.99,'noSpeechProbability':.01})
    if mode=='bad-metadata': confidence='invalid'
    else: confidence=.85
    emit({'type':'result','id':identity,'text':'Hello June','confidence':confidence,'noSpeechProbability':.05})
'''


class SupervisorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIsNotNone(WhisperWorker, 'resident worker supervisor must exist')
        self.directory = tempfile.TemporaryDirectory()
        self.peer = Path(self.directory.name) / 'peer.py'
        self.peer.write_text(PEER)
        self.workers = []

    async def asyncTearDown(self):
        for worker in self.workers:
            await worker.close()
        self.directory.cleanup()

    def worker(self, mode='ok', **options):
        worker = WhisperWorker([sys.executable, str(self.peer), mode], **options)
        self.workers.append(worker)
        return worker

    async def test_reuses_loaded_process_and_ignores_stale_ids(self):
        worker = self.worker('stale')
        await worker.warm()
        pid = worker.pid
        for _ in range(2):
            self.assertEqual((await worker.transcribe(audio()))['text'], 'Hello June')
            self.assertEqual(worker.pid, pid)
        await worker.close()
        with self.assertRaises(ProcessLookupError): os.kill(pid, 0)
        self.assertFalse(worker.ready)

    async def test_busy_cancellation_releases_slot_without_restarting(self):
        worker = self.worker('hang', cancel_timeout=.4)
        await worker.warm()
        pid = worker.pid
        task = asyncio.create_task(worker.transcribe(audio()))
        await asyncio.sleep(.05)
        with self.assertRaises(JuneError) as error: await worker.transcribe(audio())
        self.assertEqual(error.exception.code, 'busy')
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertFalse(worker.busy)
        self.assertEqual(worker.pid, pid)
        self.assertTrue(worker.ready)

    async def test_cancel_without_ack_kills_and_next_warm_restarts(self):
        worker = self.worker('ignore-cancel', cancel_timeout=.05)
        await worker.warm()
        pid = worker.pid
        task = asyncio.create_task(worker.transcribe(audio()))
        await asyncio.sleep(.05)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertFalse(worker.ready)
        with self.assertRaises(ProcessLookupError): os.kill(pid, 0)
        await worker.warm()
        self.assertNotEqual(worker.pid, pid)

    async def test_timeout_terminates_worker_and_releases_slot(self):
        worker = self.worker('hang')
        await worker.warm()
        pid = worker.pid
        with self.assertRaises(JuneError) as error: await worker.transcribe(audio(), timeout=.05)
        self.assertEqual(error.exception.code, 'timeout')
        self.assertFalse(worker.busy)
        self.assertFalse(worker.ready)
        with self.assertRaises(ProcessLookupError): os.kill(pid, 0)

    async def test_malformed_oversized_eof_and_bad_metadata_reap_process(self):
        for mode in ('malformed', 'oversized', 'flood', 'eof', 'bad-metadata'):
            with self.subTest(mode=mode):
                worker = self.worker(mode)
                await worker.warm()
                pid = worker.pid
                with self.assertRaises(JuneError) as error: await worker.transcribe(audio())
                self.assertEqual(error.exception.code, 'engine-failed')
                self.assertFalse(worker.ready)
                with self.assertRaises(ProcessLookupError): os.kill(pid, 0)

    async def test_close_during_active_job_and_warm_is_bounded_and_idempotent(self):
        worker = self.worker('hang', cancel_timeout=.05)
        await worker.warm()
        pid = worker.pid
        task = asyncio.create_task(worker.transcribe(audio()))
        await asyncio.sleep(.05)
        await asyncio.wait_for(worker.close(), 2)
        with self.assertRaises(JuneError): await task
        await worker.close()
        with self.assertRaises(ProcessLookupError): os.kill(pid, 0)
        self.assertFalse(worker.busy)
        slow = self.worker('startup-hang', startup_timeout=.05)
        with self.assertRaises(JuneError): await slow.warm()
        self.assertFalse(slow.ready)

    async def test_cancellation_while_starting_does_not_orphan_process(self):
        worker = self.worker('startup-hang')
        task = asyncio.create_task(worker.warm())
        while worker.pid is None: await asyncio.sleep(.01)
        pid = worker.pid
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        with self.assertRaises(ProcessLookupError): os.kill(pid, 0)

    async def test_cancel_during_subprocess_creation_reaps_late_child(self):
        from unittest.mock import patch
        worker = self.worker('startup-hang')
        real_spawn = asyncio.create_subprocess_exec
        spawned, release = asyncio.Event(), asyncio.Event()
        children = []
        async def delayed(*args, **kwargs):
            process = await real_spawn(*args, **kwargs)
            children.append(process)
            spawned.set()
            await release.wait()
            return process
        with patch('june.whisper_worker.asyncio.create_subprocess_exec', side_effect=delayed):
            task = asyncio.create_task(worker.warm())
            await asyncio.wait_for(spawned.wait(), 5)
            task.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 5)
        self.assertIsNone(worker.pid)
        for process in children:
            with self.assertRaises(ProcessLookupError): os.kill(process.pid, 0)

    async def test_refuses_oversized_input_without_starting_worker(self):
        worker = self.worker()
        with self.assertRaises(JuneError): await worker.transcribe(b'x' * 1048577)
        self.assertIsNone(worker.pid)


class SpeechServiceWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from types import SimpleNamespace
        from june.speech import SpeechService
        from unittest.mock import AsyncMock
        self.directory = tempfile.TemporaryDirectory()
        self.peer = Path(self.directory.name) / 'peer.py'
        self.peer.write_text(PEER)
        self.service = SpeechService(SimpleNamespace(speech_home=Path(self.directory.name)))
        self.service.worker_binary.parent.mkdir(parents=True)
        self.service.worker_binary.write_text('placeholder')
        self.service.worker_binary.chmod(0o700)
        with self.service.model.open('wb') as model: model.truncate(100000001)
        (self.service.home / 'ready.json').write_text(json.dumps({'version':'v1.9.5','model':'base.en','sha256':'0'*64}))
        # Integrity hashing is covered separately; this fixture has no model.
        self.service._hash = lambda: '0' * 64
        self.worker = None

    async def asyncTearDown(self):
        if self.worker is not None: await self.worker.close()
        if hasattr(self.service, 'close'): await self.service.close()
        self.directory.cleanup()

    async def test_service_reuses_worker_and_exports_confidence(self):
        self.assertTrue(hasattr(self.service, 'worker'), 'SpeechService must use resident supervisor')
        self.worker = WhisperWorker([sys.executable, str(self.peer), 'ok'])
        self.service.worker = self.worker
        await self.service.warm()
        pid = self.worker.pid
        for _ in range(2):
            result = await self.service.transcribe(audio())
            self.assertEqual(result['text'], 'Hello June')
            self.assertEqual(result['confidence'], .85)
            self.assertEqual(result['noSpeechProbability'], .05)
            self.assertEqual(self.worker.pid, pid)
        await self.service.close()
        self.assertFalse(self.worker.ready)

    async def test_low_confidence_and_no_speech_never_return_invented_turns(self):
        self.assertTrue(hasattr(self.service, 'worker'), 'SpeechService must use resident supervisor')
        from unittest.mock import AsyncMock
        for confidence, no_speech in ((.1, .05), (.9, .8)):
            self.service.worker.transcribe = AsyncMock(return_value={'type':'result','id':'one','text':'Invented words','confidence':confidence,'noSpeechProbability':no_speech})
            with self.assertRaises(JuneError) as error: await self.service.transcribe(audio())
            self.assertEqual(error.exception.code, 'no-speech')
            self.assertFalse(self.service.busy)


class SpeechReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_never_loads_worker_or_hashes_model_but_warm_verifies(self):
        from types import SimpleNamespace
        from june.speech import SpeechService
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = SpeechService(SimpleNamespace(speech_home=root))
            service.worker_binary.parent.mkdir(parents=True)
            service.worker_binary.write_text('unused')
            service.worker_binary.chmod(0o700)
            with service.model.open('wb') as model: model.truncate(100000001)
            (root / 'ready.json').write_text(json.dumps({'version':'v1.9.5','model':'base.en','sha256':'0'*64}))
            try:
                with patch.object(service, '_hash', side_effect=ValueError('bad hash')):
                    status = await service.status()
                    self.assertEqual(status['state'], 'ready')
                    self.assertFalse(status['workerReady'])
                    self.assertFalse(status['warm'])
                    with self.assertRaises(JuneError) as error: await service.warm()
                    self.assertEqual(error.exception.code, 'error')
                self.assertIsNone(service.worker.pid)
            finally:
                await service.close()
