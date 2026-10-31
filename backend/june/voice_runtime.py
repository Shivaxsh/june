"""Warm local models without opening the microphone or creating chat turns."""
import asyncio
from contextlib import suppress
import importlib
import os
import time
import httpx
from .errors import JuneError
from .chat import PROMPT
from .memory_service import memory_prompt
from .memory import profile_defaults

class VoiceRuntime:
    def __init__(self,settings,client,speech,audio,assets,coordinator,store):
        self.settings,self.client,self.speech,self.audio,self.assets,self.coordinator,self.store=settings,client,speech,audio,assets,coordinator,store
        self.model_warm=False;self.detectors_warm=False;self.whisper_warm=False;self.message='Preparing local voice components…'
        self.task=None;self.keeper=None;self.detectors=None;self.last_prepare=0.
        self.enabled=os.environ.get('JUNE_PREWARM','0')=='1'

    def start(self):
        if self.enabled and self.task is None:
            self.task=asyncio.create_task(self.prepare());self.keeper=asyncio.create_task(self.keep())

    async def warm_detection(self):
        status=await self.assets.status()
        if status['state']!='ready':raise JuneError('setup-required',status['message'])
        engine=await asyncio.to_thread(importlib.import_module,'june.realtime_engine')
        self.detectors=await asyncio.to_thread(engine.Detectors,self.assets.model)
        self.detectors_warm=True

    def retry_preparation(self):
        if (self.enabled and (self.task is None or self.task.done()) and time.monotonic()-self.last_prepare>=30
                and self.audio.capture_owner is None and not self.coordinator.tasks):
            self.task=asyncio.create_task(self.prepare())

    async def prepare(self):
        self.last_prepare=time.monotonic()
        try:
            await self.audio.warm()
            await self.speech.warm();self.whisper_warm=True
            await self.warm_detection()
            await self.prime_model()
            self.message='Local voice components are warm.'
        except asyncio.CancelledError:raise
        except (JuneError,httpx.HTTPError,TimeoutError,OSError,ValueError):
            self.message='Local voice preparation is incomplete. Check model, speech and June Audio setup, then refresh.'

    async def prime_model(self):
        profile=self.store.snapshot()['profile'] if self.store else profile_defaults()
        try:
            async with self.coordinator.slot('warm'):
                response=await self.client.post(self.settings.ollama+'/api/chat',json={
                    'model':self.settings.model,'stream':False,'think':False,'keep_alive':'15m',
                    'messages':[{'role':'system','content':PROMPT+memory_prompt(profile,[])},{'role':'user','content':'Hello.'}],
                    'options':{'num_ctx':4096,'num_predict':1,'temperature':.1}},timeout=90)
                response.raise_for_status()
                if response.json().get('error'):raise ValueError()
                self.model_warm=True
        except asyncio.CancelledError:
            # Foreground inference owns the model now. Its successful reply
            # will refresh the residency status on the next status request.
            self.model_warm=False

    async def refresh_model(self):
        try:
            response=await self.client.get(self.settings.ollama+'/api/ps',timeout=3)
            response.raise_for_status()
            self.model_warm=any(m.get('name')==self.settings.model for m in response.json().get('models',[]) if isinstance(m,dict))
        except (httpx.HTTPError,ValueError,TypeError):self.model_warm=False

    async def renew(self):
        if not self.model_warm or self.audio.capture_owner is None or any(k in ('chat','extract','warm') for k in self.coordinator.tasks.values()):return
        # An empty load request extends residency; it contains no user prompt
        # and performs no text generation or conversation write.
        response=await self.client.post(self.settings.ollama+'/api/generate',json={
            'model':self.settings.model,'stream':False,'keep_alive':'15m','options':{'num_ctx':4096}},timeout=15)
        response.raise_for_status()

    async def keep(self):
        while True:
            await asyncio.sleep(60)
            with suppress(httpx.HTTPError,TimeoutError,JuneError):await self.renew()

    async def detector(self,engine):
        result,self.detectors=self.detectors,None
        return result if result is not None else await asyncio.to_thread(engine.Detectors,self.assets.model)

    async def close(self):
        for task in (self.task,self.keeper):
            if task:task.cancel()
        for task in (self.task,self.keeper):
            if task:
                with suppress(asyncio.CancelledError,Exception):await task
