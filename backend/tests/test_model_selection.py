"""Switch only installed direct-answer models; retain the old selection on error."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from june.config import Settings
from june.errors import JuneError
from june.memory_service import Coordinator
from june.model_selection import ModelSelection

OLD='qwen2.5:1.5b'
NEW='qwen3:4b-instruct-2507-q4_K_M'

class SelectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with patch.dict(os.environ,{'JUNE_DATA_HOME':self.temp.name}):
            self.settings=Settings.from_env()
            self.home=self.settings.data_home
        def respond(request):
            if request.url.path=='/api/tags':
                return httpx.Response(200,json={'models':[{'name':OLD,'size':986061892},{'name':NEW,'size':2497293803}]})
            if request.url.path=='/api/show':
                return httpx.Response(200,json={'thinking':{'values':[True]}} if json.loads(request.content)['model']=='thinking-only' else {})
            return httpx.Response(200,json={})
        self.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
        self.addAsyncCleanup(self.client.aclose)
        self.runtime=SimpleNamespace(settings=self.settings,task=None,model_warm=True,message='warm')
        self.state=SimpleNamespace(settings=self.settings,client=self.client,coordinator=Coordinator(),voice_slots=SimpleNamespace(owner=None),native_audio=SimpleNamespace(capture_owner=None,jobs={}),voice_runtime=self.runtime)
        self.selection=ModelSelection(self.home)

    async def test_installed_choices_and_atomic_persisted_switch(self):
        catalog=await self.selection.catalog(self.state)
        self.assertEqual(catalog['active'],OLD)
        self.assertEqual({m['id'] for m in catalog['models']},{OLD,NEW})
        result=await self.selection.select(self.state,NEW)
        self.assertEqual(result['active'],NEW)
        self.assertEqual(self.state.settings.model,NEW)
        self.assertEqual(self.runtime.settings.model,NEW)
        self.assertFalse(self.runtime.model_warm)
        self.assertEqual(self.selection.saved_model(),NEW)
        self.assertEqual(self.selection.path.stat().st_mode & 0o777,0o600)

    async def test_missing_invalid_and_thinking_models_do_not_switch(self):
        for value in ('missing',None,{},'x'*121):
            with self.subTest(value=value),self.assertRaises(JuneError):
                await self.selection.select(self.state,value)
        self.assertEqual(self.state.settings.model,OLD)
        self.assertFalse(self.selection.path.exists())

    async def test_active_voice_and_chat_cannot_switch(self):
        self.state.voice_slots.owner='another-tab'
        with self.assertRaises(JuneError) as error:await self.selection.select(self.state,NEW)
        self.assertEqual(error.exception.status,409)
        self.state.voice_slots.owner=None
        async with self.state.coordinator.slot('chat'):
            with self.assertRaises(JuneError):await self.selection.select(self.state,NEW)
        self.assertEqual(self.state.settings.model,OLD)

    async def test_failed_save_keeps_previous_model(self):
        with patch.object(self.selection,'save',side_effect=JuneError('storage','Cannot save model choice.')):
            with self.assertRaises(JuneError):await self.selection.select(self.state,NEW)
        self.assertEqual(self.state.settings.model,OLD)

    async def test_model_switch_excludes_new_inference(self):
        async with self.state.coordinator.slot('model-switch'):
            with self.assertRaises(JuneError):
                async with self.state.coordinator.slot('chat'):pass

    async def test_corrupt_preference_is_ignored(self):
        self.selection.path.write_text('{broken')
        self.assertIsNone(self.selection.saved_model())

    async def test_installed_thinking_only_is_rejected(self):
        def respond(request):
            return httpx.Response(200,json={'models':[{'name':'thinking-only'}]} if request.url.path=='/api/tags' else {'thinking':{'values':[True]}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            self.state.client=client
            with self.assertRaises(JuneError) as error:await self.selection.select(self.state,'thinking-only')
        self.assertEqual(error.exception.code,'model-incompatible')
        self.assertEqual(self.state.settings.model,OLD)

    async def test_background_warm_is_cancelled_before_switch(self):
        started=asyncio.Event()
        async def warm():
            async with self.state.coordinator.slot('warm'):
                started.set()
                await asyncio.sleep(30)
        task=asyncio.create_task(warm())
        await started.wait()
        await asyncio.wait_for(self.selection.select(self.state,NEW),1)
        self.assertTrue(task.cancelled())


class ModelHttpTests(unittest.TestCase):
    def test_selection_routes_restore_after_restart_and_use_selected_model(self):
        from june.app import app
        from fastapi.testclient import TestClient
        seen=[]
        def respond(request):
            if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[{'name':OLD},{'name':NEW}]})
            if request.url.path=='/api/show':return httpx.Response(200,json={})
            value=json.loads(request.content)
            if request.url.path=='/api/chat':
                seen.append(value['model'])
                return httpx.Response(200,text=json.dumps({'message':{'content':'Hello from the selected model.'},'done':True})+'\n')
            return httpx.Response(200,json={})
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'JUNE_DATA_HOME':directory,'JUNE_PREWARM':'0'}):
            with TestClient(app,base_url='http://127.0.0.1:8001') as browser:
                original=app.state.client
                app.state.client=httpx.AsyncClient(transport=httpx.MockTransport(respond))
                try:
                    self.assertEqual(browser.get('/api/models').json()['active'],OLD)
                    self.assertEqual(browser.post('/api/models',json={'model':NEW},headers={'Origin':'https://example.com'}).status_code,403)
                    self.assertEqual(browser.post('/api/models',json={'model':NEW,'url':'remote'}).status_code,400)
                    self.assertEqual(browser.post('/api/models',content='{'*2048).status_code,400)
                    self.assertEqual(browser.post('/api/models',json={'model':NEW}).json()['active'],NEW)
                    events=[json.loads(line) for line in browser.post('/api/chat',json={'temporary':True,'messages':[{'role':'user','content':'Say hello briefly.'}]}).text.splitlines()]
                    self.assertEqual(events[-1]['type'],'done')
                    self.assertEqual(events[-1]['model'],NEW)
                    self.assertEqual(seen,[NEW])
                finally:
                    browser.portal.call(app.state.client.aclose)
                    app.state.client=original
            with TestClient(app,base_url='http://127.0.0.1:8001'):
                self.assertEqual(app.state.settings.model,NEW)
