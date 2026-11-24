"""Same-origin offline commerce endpoints; no arbitrary merchant or payment data."""
import re
from fastapi import APIRouter,Request
from .integrations_api import body
from .errors import JuneError
router=APIRouter()


def service(request):
    plans=getattr(request.app.state,'plans',None);commerce=getattr(plans,'commerce',None)
    if commerce is None:raise JuneError('commerce-unavailable','Simulated commerce is unavailable.',503)
    if request.query_params:raise JuneError('invalid-commerce','No query arguments are accepted.',400)
    return commerce


def exact(value,keys):
    if set(value)!=set(keys):raise JuneError('invalid-commerce','Unexpected simulated-commerce fields.',400)


@router.get('/api/transactions')
async def state(request:Request):return service(request).state()


@router.post('/api/transactions/respond')
async def respond(request:Request):
    commerce=service(request);value=await body(request)
    if set(value) not in ({'requestId','conversationId','text'},{'requestId','conversationId','select'}):raise JuneError('invalid-commerce','Send free text or one structured selection.',400)
    return await commerce.respond(value['requestId'],value['conversationId'],value.get('text'),value.get('select'))


@router.get('/api/transactions/{tid}')
async def get(tid:str,request:Request):
    commerce=service(request);return commerce.plans.envelope(transaction=commerce.get(tid))


@router.post('/api/transactions/{tid}/arm')
async def arm(tid:str,request:Request):
    commerce=service(request);v=await body(request);exact(v,('planId','revision','fingerprint','sessionId','requestId'))
    if not all(isinstance(v[k],str) and re.fullmatch(r'[\w-]{1,128}',v[k]) for k in ('planId','fingerprint','sessionId')) or type(v['revision']) is not int or not isinstance(v['requestId'],str) or not re.fullmatch(r'[\w-]{8,128}',v['requestId']):
        raise JuneError('invalid-commerce','Use the current native review identifiers.',400)
    if commerce.voice is None:raise JuneError('voice-review','Voice approval is unavailable. Use typed or button approval.',409)
    return await commerce.voice.arm(tid,v)


async def voice_approve(pid,request):
    commerce=service(request);v=await body(request);exact(v,('requestId','revision','fingerprint','reviewToken','sessionId','turnId'))
    if not all(isinstance(v[k],str) and re.fullmatch(r'[\w-]{8,128}',v[k]) for k in ('requestId','fingerprint','reviewToken','sessionId')) or type(v['revision']) is not int or type(v['turnId']) is not int:
        raise JuneError('invalid-commerce','Use the current captured approval identifiers.',400)
    if commerce.voice is None:raise JuneError('voice-approval','Voice approval is unavailable.',409)
    return await commerce.voice.approve(pid,v)
