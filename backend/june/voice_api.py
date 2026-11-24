"""Same-origin native voice bridge; all ownership and queue limits live in service."""
import json
from contextlib import aclosing
from fastapi import APIRouter,Request
from fastapi.responses import StreamingResponse
from .errors import JuneError
from .memory_api import body
from .native_audio import identifier,validate_speak
from .voice_identity import JUNE_VOICE

router=APIRouter(prefix='/api/voice')
class NativeStream(StreamingResponse):
    async def __call__(self,scope,receive,send):
        scope={**scope,'asgi':{**scope.get('asgi',{}),'spec_version':'2.3'}}
        try:await super().__call__(scope,receive,send)
        finally:await self.body_iterator.aclose()

@router.get('/voices')
async def voices(request:Request):
    return await request.app.state.voice_provider.voices()

@router.post('/stop')
async def stop(request:Request):
    value=await body(request,32000)
    if not all(identifier(value.get(k)) for k in ('ownerId','requestId')):raise JuneError('voice-request','Invalid voice ownership.',400)
    await request.app.state.native_audio.stop(value['ownerId'],value['requestId'])
    return {'stopped':True}

@router.post('/speak')
async def speak(request:Request):
    value=await body(request,32000)
    service=request.app.state.voice_provider
    value=validate_speak(value,[JUNE_VOICE])
    state=await service.status()
    if state['state']!='ready':raise JuneError('voice-unavailable',state['message'],503)
    async def events():
        try:
            async with aclosing(service.speak(value)) as source:
                async for event in source:yield json.dumps(event).encode()+b'\n'
        except JuneError as error:yield json.dumps({'type':'error','message':error.message}).encode()+b'\n'
    return NativeStream(events(),media_type='application/x-ndjson')


@router.post('/repair')
async def repair(request:Request):
    """Restart the Mac's sound service after the person authorises it in macOS's own prompt."""
    if await body(request,1000)!={}:raise JuneError('voice-request','Repair takes no arguments.',400)
    from .sound_repair import restart_sound_service
    outcome=await restart_sound_service()
    if outcome=='cancelled':return {'outcome':'cancelled','message':'Nothing was changed. The sound service was not restarted.'}
    if outcome!='restarted':raise JuneError('repair-failed','The Mac did not restart its sound service. Restart the Mac instead.',503)
    audio=request.app.state.native_audio
    # A helper that lived through the restart can report ready while silent: start a fresh one.
    audio.invalidate_output()
    await audio.terminate()
    request.app.state.voice_runtime.retry_preparation()
    return {'outcome':'restarted','message':'The Mac’s sound service was restarted. June is reconnecting her voice; this takes a few seconds.'}
