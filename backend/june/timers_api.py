"""Local timer endpoints; durations and transitions are server-owned."""
import json
from fastapi import APIRouter,Request
from .errors import JuneError
router=APIRouter(prefix='/api/timers')
def service(request):
    timers=getattr(request.app.state,'timers',None)
    if timers is None:raise JuneError('timers-unavailable','Local timers are unavailable. Check June’s local storage and restart.',503)
    return timers
async def body(request,empty=False):
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>1024:raise JuneError('invalid-timer','The timer request is too large.',413)
    try:
        value=json.loads(raw)
        if not isinstance(value,dict) or (empty and value!={}):raise ValueError()
        return value
    except (ValueError,UnicodeError,RecursionError):raise JuneError('invalid-timer','Send a valid timer request.',400)
@router.get('')
async def state(request:Request):return await service(request).state()
@router.post('')
async def create(request:Request):return await service(request).create(await body(request))
@router.post('/{tid}/cancel')
async def cancel(tid:str,request:Request):
    await body(request,True);return await service(request).cancel(tid)
@router.post('/{tid}/acknowledge')
async def acknowledge(tid:str,request:Request):
    await body(request,True);return await service(request).acknowledge(tid)
@router.post('/{tid}/claim')
async def claim(tid:str,request:Request):
    await body(request,True);return await service(request).claim(tid)
