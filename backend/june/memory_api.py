"""Same-origin bridge targets. No endpoint accepts SQL, file paths or system prompts."""
import asyncio
from contextlib import suppress
import json
import httpx
from fastapi import APIRouter, Request
from .errors import JuneError
from .memory import validate_import
from .memory_service import extract

router=APIRouter(prefix='/api/library')

def store(request):
    result=request.app.state.store
    if result is None:raise JuneError('storage','June cannot open private storage. Check JUNE_DATA_HOME or explicitly choose temporary chat.',503)
    return result

async def body(request,limit=2*1024*1024):
    result=bytearray()
    async for part in request.stream():
        result.extend(part)
        if len(result)>limit:raise JuneError('too-large','June imports must be smaller than 2 MiB.',413)
    try:
        value=json.loads(result)
        if not isinstance(value,dict):raise ValueError()
        return value
    except (ValueError,UnicodeError,RecursionError):raise JuneError('invalid-data','Send a valid JSON object.',400)

@router.get('/state')
async def state(request:Request,search:str=''):
    return store(request).snapshot(search[:200])
@router.post('/conversations')
async def create(request:Request):
    return store(request).create_conversation()
@router.get('/conversations/{cid}')
async def conversation(cid:str,request:Request):
    return store(request).conversation(cid)
@router.delete('/conversations')
async def clear(request:Request):
    await request.app.state.coordinator.cancel()
    store(request).delete_conversation()
    return {'saved':True}
@router.delete('/conversations/{cid}')
async def delete_chat(cid:str,request:Request):
    await request.app.state.coordinator.cancel()
    store(request).delete_conversation(cid)
    return {'saved':True}
@router.post('/memories')
async def add(request:Request):
    v=await body(request)
    # Replacing a reviewed conflict resets inference before the old fact disappears.
    if v.get('replace'):await request.app.state.coordinator.cancel()
    return store(request).add_memory(v.get('text'),v.get('pinned') is True,replace=v.get('replace'))
@router.patch('/memories/{mid}')
async def edit(mid:str,request:Request):
    v=await body(request)
    await request.app.state.coordinator.cancel()
    store(request).edit_memory(mid,v.get('text'),v.get('pinned') is True)
    return {'saved':True}
@router.delete('/memories/{mid}')
async def delete_memory(mid:str,request:Request):
    await request.app.state.coordinator.cancel()
    store(request).delete_memory(mid)
    return {'saved':True}
@router.post('/suggestions/{sid}')
async def decide(sid:str,request:Request):
    v=await body(request)
    if v.get('replace'):await request.app.state.coordinator.cancel()
    store(request).decide(sid,v.get('action'),v.get('text'),v.get('pinned') is True,v.get('replace'))
    return {'saved':True}
@router.put('/personality')
async def personality(request:Request):
    v=await body(request)
    await request.app.state.coordinator.cancel()
    store(request).save_profile(v)
    return {'saved':True}
@router.get('/export')
async def export(request:Request,chats:bool=False):
    return store(request).export(chats)
@router.post('/import/preview')
async def preview(request:Request):
    return validate_import(await body(request))
@router.post('/import')
async def apply(request:Request):
    value=await body(request)
    validate_import(value)
    await request.app.state.coordinator.cancel()
    store(request).apply_import(value)
    return {'saved':True}
@router.post('/cancel')
async def cancel(request:Request):
    await request.app.state.coordinator.cancel('extract')
    return {'cancelled':True}
@router.post('/extract')
async def suggestions(request:Request):
    value=await body(request)
    if not isinstance(value.get('conversationId'),str) or not isinstance(value.get('turnId'),str):raise JuneError('invalid-turn','Choose a completed turn.',400)
    async def run():
        try:
            await extract(request.app.state.client,request.app.state.settings,store(request),request.app.state.coordinator,value['conversationId'],value['turnId'])
            return {'suggested':True}
        except (TimeoutError,httpx.HTTPError):return {'suggested':False,'message':'No suggestions available from this reply. Your chat is saved.'}
    task=asyncio.create_task(run())
    async def watch():
        while (await request.receive())['type']!='http.disconnect':pass
    watcher=asyncio.create_task(watch())
    try:
        done,_=await asyncio.wait((task,watcher),return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            if task.cancelled():return {'suggested':False}
            return await task
        raise JuneError('cancelled','Memory suggestions cancelled.',499)
    finally:
        for t in (task,watcher):
            t.cancel()
            with suppress(asyncio.CancelledError):await t
