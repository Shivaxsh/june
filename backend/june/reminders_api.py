"""Local reminder endpoints; durations and transitions are server-owned."""
import json
from fastapi import APIRouter,Request
from .errors import JuneError
router=APIRouter(prefix='/api/reminders')
def service(request):
    reminders=getattr(request.app.state,'reminders',None)
    if reminders is None:raise JuneError('reminders-unavailable','Local reminders are unavailable. Check June’s local storage and restart.',503)
    return reminders
async def body(request,empty=False):
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>2048:raise JuneError('invalid-reminder','The reminder request is too large.',413)
    try:
        value=json.loads(raw)
        if not isinstance(value,dict) or (empty and value!={}):raise ValueError()
        return value
    except (ValueError,UnicodeError,RecursionError):raise JuneError('invalid-reminder','Send a valid reminder request.',400)
async def revision_body(request):
    value=await body(request)
    if set(value)-{'revision'} or ('revision' in value and (type(value['revision']) is not int or value['revision']<1)):
        raise JuneError('invalid-reminder','Send only the current reminder revision.',400)
    return value.get('revision')
@router.get('')
async def state(request:Request):return await service(request).state()
@router.post('')
async def create(request:Request):return await service(request).create(await body(request))
@router.post('/{tid}/cancel')
async def cancel(tid:str,request:Request):
    revision=await revision_body(request);return await service(request).cancel(tid,revision=revision)
@router.post('/{tid}/acknowledge')
async def acknowledge(tid:str,request:Request):
    revision=await revision_body(request);return await service(request).acknowledge(tid,revision=revision)
@router.post('/{tid}/claim')
async def claim(tid:str,request:Request):
    revision=await revision_body(request);return await service(request).claim(tid,revision=revision)

@router.post('/{tid}/reschedule')
async def reschedule(tid:str,request:Request):
    return await service(request).reschedule(tid,await body(request))
@router.post('/{tid}/snooze')
async def snooze(tid:str,request:Request):
    return await service(request).snooze(tid,await body(request))

# Repeating reminders. Every change is bound to the series revision (skip-next also to the date shown).
@router.post('/series')
async def create_series(request:Request):return await service(request).create_series(await body(request))
@router.post('/series/{sid}/update')
async def update_series(sid:str,request:Request):return await service(request).update_series(sid,await body(request))
@router.post('/series/{sid}/pause')
async def pause_series(sid:str,request:Request):return await service(request).pause_series(sid,await body(request))
@router.post('/series/{sid}/resume')
async def resume_series(sid:str,request:Request):return await service(request).resume_series(sid,await body(request))
@router.post('/series/{sid}/cancel')
async def cancel_series(sid:str,request:Request):return await service(request).cancel_series(sid,await body(request))
@router.post('/series/{sid}/skip-next')
async def skip_next(sid:str,request:Request):return await service(request).skip_next(sid,await body(request))
@router.post('/{tid}/skip')
async def skip(tid:str,request:Request):return await service(request).skip(tid,await body(request))
