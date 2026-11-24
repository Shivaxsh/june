"""Daily setup and local goals. Consent and OAuth are explicit UI operations."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from .errors import JuneError
from .integrations_api import body

router=APIRouter()


def service(request, query=False):
    if request.query_params and not query:
        raise JuneError('invalid-assistant','Daily endpoints accept no query arguments.',400)
    daily=getattr(request.app.state,'daily',None)
    if daily is None:raise JuneError('assistant-unavailable','Daily assistant storage is unavailable.',503)
    return daily


@router.get('/api/assistant/settings')
async def settings(request:Request):return service(request).settings()

@router.post('/api/assistant/settings')
async def update_settings(request:Request):return await service(request).settings_update(await body(request))

@router.get('/api/assistant/goals')
async def goals(request:Request):return service(request).goals()

@router.post('/api/assistant/goals')
async def create_goal(request:Request):return service(request).goal_create(await body(request))

@router.post('/api/assistant/goals/{gid}/{operation}')
async def change_goal(gid:str,operation:str,request:Request):return service(request).goal_change(gid,operation,await body(request))

@router.post('/api/assistant/weather/places')
async def places(request:Request):return await service(request).places(await body(request))

@router.get('/api/assistant/music/playlists')
async def playlists(request:Request):return await service(request).playlists()

@router.get('/api/assistant/today')
async def today(request:Request):return await service(request).today()

@router.post('/api/assistant/briefing')
async def briefing(request:Request):
    daily=service(request);value=await body(request)
    if set(value)!={'requestId'} or not isinstance(value['requestId'],str) or not 8<=len(value['requestId'])<=128:
        raise JuneError('invalid-assistant','A briefing request id is required.',400)
    return await daily.briefing()

@router.post('/api/connections/{cid}/enable')
async def enable(cid:str,request:Request):return await service(request).enable(cid,True,await body(request))

@router.post('/api/connections/{cid}/disable')
async def disable(cid:str,request:Request):return await service(request).enable(cid,False,await body(request))

@router.post('/api/connections/google/configure')
async def configure_google(request:Request):return await service(request).google.configure(await body(request))

@router.post('/api/connections/google/authorize')
async def authorize_google(request:Request):return await service(request).google.authorize(await body(request))

@router.post('/api/connections/google/revoke')
async def revoke_google(request:Request):return await service(request).google.revoke(await body(request))

@router.get('/api/connections/google/callback')
async def google_callback(request:Request):
    status=200
    try:
        await service(request,query=True).google.callback(dict(request.query_params))
        title='Calendar connected'
        message='Return to June and refresh Daily. You can close this tab.'
    except JuneError as error:
        status=error.status
        title='Calendar was not connected'
        message='Nothing was connected by this attempt. Return to June and choose Reconnect Google Calendar. You can close this tab.'
    return HTMLResponse('<!doctype html><html lang="en"><meta charset="utf-8"><title>June Calendar</title><body><h1>'+title+'</h1><p>'+message+'</p></body></html>',status_code=status,headers={'Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'"})
