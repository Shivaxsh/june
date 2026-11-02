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
