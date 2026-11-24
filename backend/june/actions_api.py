"""Local action approvals; paths are accepted only for manual project registration."""
import json
from fastapi import APIRouter,Request
from .errors import JuneError
router=APIRouter(prefix='/api/actions')
def service(request):
    value=getattr(request.app.state,'actions',None)
    if value is None:raise JuneError('actions-unavailable','Mac actions are unavailable.',503)
    return value
async def body(request):
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>1024:raise JuneError('invalid-action','The action request is too large.',413)
    try:
        value=json.loads(data)
        if not isinstance(value,dict):raise ValueError()
        return value
    except (ValueError,UnicodeError,RecursionError):raise JuneError('invalid-action','Send a valid action request.',400)
@router.get('')
async def state(request:Request):return await service(request).state()
@router.post('/propose')
async def propose(request:Request):return await service(request).propose(await body(request))
@router.post('/preferences')
async def preferences(request:Request):return await service(request).preferences(await body(request))
@router.post('/run')
async def run(request:Request):return await service(request).run(await body(request))
@router.post('/{aid}/approve')
async def approve(aid:str,request:Request):return await service(request).approve(aid,await body(request))
@router.post('/{aid}/cancel')
async def cancel(aid:str,request:Request):return await service(request).cancel(aid,await body(request))

@router.post('/projects')
async def add_project(request:Request):return await service(request).add_project(await body(request))
@router.post('/projects/{pid}/remove')
async def remove_project(pid:str,request:Request):
    if await body(request)!={}:raise JuneError('invalid-action','Send no extra project arguments.',400)
    return await service(request).remove_project(pid)
@router.post('/projects/{pid}/forget')
async def forget_project(pid:str,request:Request):
    if await body(request)!={}:raise JuneError('invalid-action','Send no extra project arguments.',400)
    return await service(request).forget_project(pid)
