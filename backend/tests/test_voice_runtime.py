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
