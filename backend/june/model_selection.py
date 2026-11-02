"""Private, restart-safe selection of an already installed local model."""
import asyncio
from contextlib import suppress
from dataclasses import replace
import json
import os
import re
import httpx
from .errors import JuneError

DESCRIPTIONS = {
    'qwen2.5:1.5b': ('Qwen2.5 1.5B', 'Lightweight · quicker on this Mac; less reliable answers.'),
    'qwen3:4b-instruct-2507-q4_K_M': ('Qwen3 4B Instruct', 'Experimental · more accurate in our checks, but slower; one long-chat request timed out. First replies can take 30+ seconds.'),
}

class ModelSelection:
    def __init__(self, home):
        self.path = home / 'model-selection.json'
        self.lock = asyncio.Lock()

    def saved_model(self):
        try:
            value = json.loads(self.path.read_text())
            model = value.get('model') if isinstance(value,dict) else None
            return model if valid_name(model) else None
        except (OSError,ValueError):
            return None

    def save(self, model):
        temporary = self.path.with_suffix('.tmp')
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with open(temporary, 'w', encoding='utf-8', opener=lambda p, f: os.open(p, f, 0o600)) as output:
                os.chmod(temporary,0o600)
                json.dump({'model': model}, output)
            os.replace(temporary, self.path)
        except OSError:
            with suppress(OSError):temporary.unlink()
            raise JuneError('storage','Could not save the model choice. June kept the previous model.',503) from None

    async def installed(self, state):
        try:
            response = await state.client.get(state.settings.ollama+'/api/tags',timeout=5)
            response.raise_for_status()
            models = response.json().get('models',[])
            if not isinstance(models,list):raise ValueError()
            return [m for m in models if isinstance(m,dict) and valid_name(m.get('name'))]
        except (httpx.HTTPError,ValueError,AttributeError):
            raise JuneError('model-offline','The local model server is unavailable. Reconnect after restarting June.',503) from None

    async def catalog(self, state):
        models = await self.installed(state)
        return {'active': state.settings.model, 'models': [
            {'id':m['name'],'label':DESCRIPTIONS.get(m['name'],(m['name'],''))[0],
             'description':DESCRIPTIONS.get(m['name'],('','Installed local model · speed and accuracy have not been verified.'))[1],
             'sizeBytes':m.get('size',0)} for m in models]}

    async def select(self, state, model):
        if not valid_name(model):raise JuneError('invalid-model','Choose an installed local model.',400)
        async with self.lock:
            if (state.voice_slots.owner is not None or state.native_audio.capture_owner is not None
                    or state.native_audio.jobs or any(k=='chat' for k in state.coordinator.tasks.values())):
                raise JuneError('busy','Stop replies, voice playback and hands-free in all June tabs before switching models.',409)
            async with state.coordinator.slot('model-switch'):
                if model not in {m['name'] for m in await self.installed(state)}:
                    raise JuneError('model-missing','This model is no longer installed. Refresh the model list.',400)
                try:
                    response=await state.client.post(state.settings.ollama+'/api/show',json={'model':model},timeout=5)
                    response.raise_for_status()
                    thinking=response.json().get('thinking')
                    if isinstance(thinking,dict) and thinking.get('values') and not any(x is False for x in thinking['values']):
                        raise JuneError('model-incompatible','This is a thinking-only model. Choose a direct-answer Instruct model for June’s voice chat.',400)
                except (httpx.HTTPError,ValueError,AttributeError):
                    raise JuneError('model-unavailable','Could not verify this model. The previous selection is unchanged.',503) from None
                runtime=state.voice_runtime
                if runtime.task and not runtime.task.done():
                    runtime.task.cancel()
                    with suppress(asyncio.CancelledError):await runtime.task
                await state.coordinator.cancel('extract')
                await state.coordinator.cancel('warm')
                self.save(model)
                previous=state.settings
                state.settings=replace(previous,model=model)
                runtime.settings=state.settings
                runtime.model_warm=False
                runtime.message='Model changed. The first reply may need time to load; refresh voice readiness before enabling hands-free.'
                # Release the previous model's residency rather than keeping two
                # models competing for this Mac's limited memory.
                if previous.model!=model:
                    with suppress(httpx.HTTPError):
                        await state.client.post(previous.ollama+'/api/generate',json={
                            'model':previous.model,'stream':False,'keep_alive':0},timeout=5)
                return {'active':model,'message':'Selected locally. Your next reply uses this model; the first load can be slower.'}


def valid_name(value):
    return isinstance(value,str) and bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}',value))
