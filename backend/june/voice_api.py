"""Same-origin native voice bridge; all ownership and queue limits live in service."""
import json
from contextlib import aclosing
from fastapi import APIRouter,Request
from fastapi.responses import StreamingResponse
from .errors import JuneError
from .memory_api import body
from .native_audio import identifier,validate_speak

router=APIRouter(prefix='/api/voice')
class NativeStream(StreamingResponse):
    async def __call__(self,scope,receive,send):
        scope={**scope,'asgi':{**scope.get('asgi',{}),'spec_version':'2.3'}}
        try:await super().__call__(scope,receive,send)
        finally:await self.body_iterator.aclose()

@router.get('/voices')
async def voices(request:Request):
    return await request.app.state.native_audio.voices()

@router.post('/stop')
async def stop(request:Request):
    value=await body(request,32000)
    if not all(identifier(value.get(k)) for k in ('ownerId','requestId')):raise JuneError('voice-request','Invalid voice ownership.',400)
    await request.app.state.native_audio.stop(value['ownerId'],value['requestId'])
    return {'stopped':True}

@router.post('/speak')
async def speak(request:Request):
    value=await body(request,32000)
    service=request.app.state.native_audio
    await service.ensure_started()
    value=validate_speak(value,service.available_voices)
    async def events():
        try:
            async with aclosing(service.speak(value)) as source:
                async for event in source:yield json.dumps(event).encode()+b'\n'
        except JuneError as error:yield json.dumps({'type':'error','message':error.message}).encode()+b'\n'
    return NativeStream(events(),media_type='application/x-ndjson')
