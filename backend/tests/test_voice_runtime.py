import asyncio
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock
import httpx
from june.voice_runtime import VoiceRuntime

class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_residency_renewal_never_generates_text_and_defers_to_foreground(self):
        bodies=[]
        def response(req):
            import json
            bodies.append(json.loads(req.content));return httpx.Response(200,json={'done':True})
        audio=SimpleNamespace(capture_owner='owned')
        coordinator=SimpleNamespace(tasks={})
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            runtime=VoiceRuntime(SimpleNamespace(model='local',ollama='http://127.0.0.1:11434'),client,None,audio,None,coordinator,None)
            runtime.model_warm=True
            await runtime.renew()
            self.assertEqual(len(bodies),1);self.assertNotIn('prompt',bodies[0]);self.assertNotIn('messages',bodies[0]);self.assertEqual(bodies[0]['keep_alive'],'15m')
            coordinator.tasks={object():'chat'};await runtime.renew();self.assertEqual(len(bodies),1)
            coordinator.tasks={};audio.capture_owner=None;await runtime.renew();self.assertEqual(len(bodies),1)

    async def test_readiness_message_names_actual_missing_components(self):
        runtime=VoiceRuntime(SimpleNamespace(model='local'),None,None,None,None,None,None)
        runtime.message='Local voice components are warm.'
        runtime.detectors_warm=True
        runtime.model_warm=False
        message=runtime.readiness_message(whisper_warm=True,voice_warm=True)
        self.assertIn('selected language model',message)
        self.assertNotIn('are warm',message)
        runtime.model_warm=True
        message=runtime.readiness_message(whisper_warm=False,voice_warm=False)
        self.assertIn('Whisper',message)
        self.assertIn('voice playback',message)
        self.assertNotIn('language model',message)


class ReadinessHttpTests(unittest.TestCase):
    def test_expired_model_residency_never_reports_warm_in_preparing_state(self):
        import os
        from unittest.mock import patch, Mock
        from fastapi.testclient import TestClient
        from june.app import app
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'JUNE_DATA_HOME':directory,'JUNE_PREWARM':'0'}):
            with TestClient(app,base_url='http://127.0.0.1:8001') as client:
                runtime=app.state.voice_runtime
                runtime.enabled=True
                runtime.model_warm=False
                runtime.detectors_warm=True
                runtime.message='Local voice components are warm.'
                runtime.refresh_model=AsyncMock()
                runtime.retry_preparation=Mock()
                app.state.voice_assets.status=AsyncMock(return_value={'state':'ready','message':'Detection ready.'})
                app.state.native_audio.status=AsyncMock(return_value={'state':'ready','nativeReady':True,'voiceWarm':True,'permission':'granted'})
                app.state.speech.status=AsyncMock(return_value={'state':'ready','warm':True})
                result=client.get('/api/voice/status').json()
                self.assertEqual(result['state'],'preparing')
                self.assertFalse(result['modelWarm'])
                self.assertIn('selected language model',result['message'])
                self.assertNotIn('are warm',result['message'])
                runtime.retry_preparation.assert_called_once()


    def test_output_failure_reaches_status_without_stale_ready(self):
        import os
        from unittest.mock import patch, Mock
        from fastapi.testclient import TestClient
        from june.app import app
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'JUNE_DATA_HOME':directory,'JUNE_PREWARM':'0'}):
            with TestClient(app,base_url='http://127.0.0.1:8001') as client:
                runtime=app.state.voice_runtime
                runtime.enabled=True;runtime.model_warm=True;runtime.detectors_warm=True
                runtime.refresh_model=AsyncMock();runtime.retry_preparation=Mock()
                app.state.voice_assets.status=AsyncMock(return_value={'state':'ready','message':'Detection ready.'})
                app.state.native_audio.status=AsyncMock(return_value={'state':'ready','nativeReady':True,'voiceWarm':False,'outputError':'Audio output was interrupted.'})
                app.state.speech.status=AsyncMock(return_value={'state':'ready','warm':True})
                app.state.voice_provider.status=AsyncMock(return_value={'state':'ready','provider':'kokoro','voiceId':'kokoro-af-heart','voiceName':'June','ttsModel':'kokoro-v1.0','message':'Ready.'})
                result=client.get('/api/voice/status').json()
                self.assertEqual(result['state'],'preparing')
                self.assertFalse(result['voiceWarm'])
                self.assertEqual(result.get('outputError'),'Audio output was interrupted.')
                self.assertIn('interrupted',result['message'])

class RecoveryPreparation(unittest.IsolatedAsyncioTestCase):
    async def test_output_recovery_preserves_resident_model_and_loaded_detectors(self):
        from june.memory_service import Coordinator
        requests=[]
        async def response(req):
            requests.append(req.url.path);return httpx.Response(200,json={'done':True})
        audio=type('Audio',(),{'capture_owner':None,'jobs':{},'warm':AsyncMock()})()
        speech=type('Speech',(),{'worker':SimpleNamespace(ready=True),'warm':AsyncMock()})()
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            async def no_reload():raise AssertionError('Loaded detectors must not initialize again')
            assets=SimpleNamespace(status=no_reload)
            runtime=VoiceRuntime(SimpleNamespace(model='local',ollama='http://127.0.0.1:11434'),client,speech,audio,assets,Coordinator(),None)
            runtime.enabled=True;runtime.model_warm=True;runtime.detectors_warm=True
            runtime.detectors=object();detectors=runtime.detectors
            await runtime.prepare()
            self.assertEqual(requests,[],'Output recovery must not run a model prompt')
            self.assertIs(runtime.detectors,detectors)
            self.assertTrue(runtime.whisper_warm)

    async def test_preparation_waits_for_active_output_and_is_single_flight_with_backoff(self):
        from june.memory_service import Coordinator
        from unittest.mock import patch
        gate=asyncio.Event();entered=[]
        async def warm():entered.append('output');await gate.wait()
        audio=SimpleNamespace(capture_owner=None,jobs={'playing':{}},warm=warm)
        speech=SimpleNamespace(worker=SimpleNamespace(ready=True))
        runtime=VoiceRuntime(SimpleNamespace(model='local'),None,speech,audio,None,Coordinator(),None)
        runtime.enabled=True;runtime.model_warm=runtime.detectors_warm=True
        runtime.retry_preparation();await asyncio.sleep(0)
        self.assertEqual(entered,[])
        audio.jobs={};runtime.retry_preparation();await asyncio.sleep(0)
        runtime.retry_preparation();await asyncio.sleep(0)
        self.assertEqual(entered,['output'])
        gate.set();await runtime.task
        runtime.retry_preparation();await asyncio.sleep(0)
        self.assertEqual(entered,['output'])
        await runtime.close()

class HandsFreeOutputRecovery(unittest.IsolatedAsyncioTestCase):
    async def test_recovery_is_scheduled_while_hands_free_capture_is_flowing(self):
        from june.memory_service import Coordinator
        entered=[]
        async def warm():entered.append('output')
        flowing=[False]
        audio=SimpleNamespace(capture_owner='owner',jobs={},warm=warm,output_error='interrupted',capture_flowing=lambda:flowing[0])
        runtime=VoiceRuntime(SimpleNamespace(model='local'),None,SimpleNamespace(worker=SimpleNamespace(ready=True)),audio,None,Coordinator(),None)
        runtime.enabled=False
        runtime.retry_preparation();await asyncio.sleep(0)
        self.assertEqual(entered,[],'a stalled capture is not a safe moment')
        flowing[0]=True;runtime.retry_preparation();await asyncio.sleep(0)
        self.assertEqual(entered,['output'])
        await runtime.close()

class OutputOnlyRecovery(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_model_prewarm_still_recovers_reported_output_failure_only(self):
        from june.native_audio import NativeAudioService
        from june.memory_service import Coordinator
        audio=NativeAudioService('/not-installed');audio.binary=Path(__file__)
        async def ensure():pass
        audio.ensure_started=ensure
        async def send(value):
            self.assertEqual(value['type'],'prepare-output')
            await audio.receive({'type':'result','id':value['id'],'prepared':True})
        audio.send=send
        await audio.receive({'type':'device-error'})
        runtime=VoiceRuntime(None,None,None,audio,None,Coordinator(),None)
        runtime.enabled=False
        runtime.retry_preparation()
        self.assertIsNotNone(runtime.task,'Known output failure must recover even with model prewarm off')
        try:
            await runtime.task
            self.assertTrue(audio.voice_warm)
            self.assertIsNone(audio.output_error)
            self.assertFalse(runtime.model_warm)
            self.assertFalse(runtime.detectors_warm)
        finally:await runtime.close();await audio.close()
