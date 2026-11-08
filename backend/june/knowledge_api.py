"""Raw bounded upload and explicit knowledge lifecycle endpoints."""
from urllib.parse import unquote
from fastapi import APIRouter,Request
from .knowledge import MAX_UPLOAD
from .knowledge_store import error

router=APIRouter(prefix='/api/knowledge')


def service(request):
    result=getattr(request.app.state,'knowledge',None)
    if result is None:raise error('Private document storage is unavailable.',503)
    return result


@router.get('/status')
async def status(request:Request):
    return await service(request).status()


@router.get('/documents')
async def documents(request:Request):
    return service(request).db.list()


@router.post('/documents')
async def upload(request:Request):
    knowledge=service(request)
    if request.headers.get('content-type','').split(';')[0].strip()!='application/octet-stream':
        raise error('Upload raw document bytes as application/octet-stream.',415)
    try:
        length=int(request.headers.get('content-length','0'))
        if length<0:raise ValueError()
    except ValueError:raise error('Invalid upload size.')
    if length>MAX_UPLOAD:raise error('The upload exceeds 10 MiB.',413)
    raw_name=request.headers.get('x-file-name','')
    if len(raw_name)>3000:raise error('Filename is too long.')
    try:
        name=unquote(raw_name,errors='strict')
    except UnicodeError:raise error('Filename must use URI encoded UTF-8.')
    data=bytearray()
    async for part in request.stream():
        if len(data)+len(part)>MAX_UPLOAD:raise error('The upload exceeds 10 MiB.',413)
        data.extend(part)
    return knowledge.upload(name,bytes(data))


@router.get('/documents/{did}')
async def document(did:str,request:Request):
    return service(request).db.get(did,True)


@router.post('/documents/{did}/retry')
async def retry(did:str,request:Request):
    return await service(request).retry(did)


@router.post('/documents/{did}/cancel')
async def cancel(did:str,request:Request):
    knowledge=service(request)
    if knowledge.db.get(did)['status']=='ready':raise error('This document has already finished indexing.',409)
    return await knowledge.stop(did)


@router.delete('/documents/{did}')
async def delete(did:str,request:Request):
    return await service(request).stop(did,delete=True)
