"""Local synthesis ownership and cleanup; no cloud or microphone access."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from june.errors import JuneError
from june.heart_voice import HeartVoice
from june.voice_identity import JUNE_VOICE_ID

WORKER = '''import base64,json,sys,time
print(json.dumps({'type':'ready','voice':'af_heart','sampleRate':24000}),flush=True)
for line in sys.stdin:
 v=json.loads(line)
 if v['text']=='slow':time.sleep(20)
 if v['text']=='broken':
  print(json.dumps({'id':v['id'],'type':'error'}),flush=True);continue
 print(json.dumps({'id':v['id'],'audio':base64.b64encode(b'\\1\\0'*400).decode()}),flush=True)
 print(json.dumps({'id':v['id'],'type':'done'}),flush=True)
'''

class HeartTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)
        for name in ('kokoro-v1.0.onnx','voices-v1.0.bin'): (self.home/name).touch()
        self.service=HeartVoice(None,self.home)
        self.service.python=Path(sys.executable)
        self.service.script=self.home/'worker.py';self.service.script.write_text(WORKER)
        self.addAsyncCleanup(self.service.close)
        self.value={'ownerId':'owner','requestId':'request','segmentId':'segment','voiceId':JUNE_VOICE_ID,'rate':.98,'text':'Hello June.'}

    async def test_status_is_local_fixed_identity_without_credentials_or_quota(self):
        state=await self.service.voices()
        self.assertEqual(state['state'],'ready');self.assertFalse(state['cloudText'])
        self.assertNotIn('quota',state);self.assertEqual(state['voices'][0]['id'],JUNE_VOICE_ID)
        process=self.service.process
        self.assertEqual(b''.join([p async for p in self.service.pcm(self.value)]),b'\1\0'*400)
        self.assertIs(self.service.process,process)

    async def test_missing_files_fail_without_substitution(self):
        (self.home/'voices-v1.0.bin').unlink()
        self.assertEqual((await self.service.status())['state'],'setup-required')
        self.assertIsNone(self.service.process)

    async def test_old_provider_voice_rejected_before_worker_starts(self):
        with self.assertRaises(JuneError):
            await anext(self.service.pcm({**self.value,'voiceId':'old-cloud-voice'}))
        self.assertIsNone(self.service.process)

    async def test_cancel_reaps_busy_worker_and_new_request_restarts_cleanly(self):
        await self.service.status();old=self.service.process
        stream=self.service.pcm({**self.value,'text':'slow'})
        pending=asyncio.create_task(anext(stream));await asyncio.sleep(.04)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError): await pending
        self.assertIsNotNone(old.returncode);self.assertIsNone(self.service.process)
        self.assertTrue(b''.join([p async for p in self.service.pcm(self.value)]))
        self.assertIsNot(self.service.process,old)

    async def test_error_retires_worker_and_close_releases_resources(self):
        with self.assertRaises(JuneError):
            async for _ in self.service.pcm({**self.value,'text':'broken'}): pass
        self.assertIsNone(self.service.process)
        await self.service.status();process=self.service.process
        await self.service.close();self.assertIsNotNone(process.returncode)
        self.assertNotEqual((await self.service.status())['state'],'ready')

    async def test_cancelled_start_reaps_late_child(self):
        self.service.script.write_text("import time\ntime.sleep(20)\n")
        pending=asyncio.create_task(self.service.ensure_started());await asyncio.sleep(.04);pending.cancel()
        with self.assertRaises(asyncio.CancelledError): await pending
        self.assertIsNone(self.service.process)

    async def test_speech_preempts_background_warmup_and_blocks_new_extraction(self):
        from june.memory_service import Coordinator
        coordinator=Coordinator();self.service.coordinator=coordinator
        started=asyncio.Event()
        async def warm():
            async with coordinator.slot('warm'):
                started.set();await asyncio.sleep(20)
        task=asyncio.create_task(warm());await started.wait()
        stream=self.service.pcm(self.value)
        self.assertTrue(await anext(stream))
        self.assertTrue(task.cancelled())
        self.assertIn('voice',coordinator.tasks.values())
        with self.assertRaises(JuneError):
            async with coordinator.slot('extract'):self.fail('Extraction competed with speech')
        await stream.aclose();self.assertEqual(coordinator.tasks,{})
