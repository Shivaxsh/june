"""Versioned, same-origin bounded-plan endpoints. Never accept tool definitions."""
import json
import re
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .errors import JuneError
from .integrations import connection_state

router = APIRouter()


def service(request):
    if request.query_params:
        raise JuneError('invalid-plan', 'These endpoints accept no query arguments.', 400)
    value = getattr(request.app.state, 'plans', None)
    if value is None:
        raise JuneError('tools-unavailable', 'June’s workflow storage is unavailable.', 503)
    return value


async def body(request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 32000:
            raise JuneError('invalid-plan', 'The workflow request is too large.', 413)
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise JuneError('invalid-plan', 'Send a valid workflow request.', 400)


@router.get('/api/capabilities')
async def capabilities(request: Request):
    plans = service(request)
    await plans.readiness()
    return plans.envelope(capabilities=[c.public() for c in plans.capabilities.values()])


@router.get('/api/apps')
async def apps(request: Request):
    plans = service(request)
    if not hasattr(plans, 'app_list'):
        raise JuneError('tools-unavailable', 'The app list is unavailable.', 503)
    return plans.app_list()


@router.get('/api/connections')
async def connections(request: Request):
    return connection_state(service(request))


@router.get('/api/plans')
async def state(request: Request):
    return await service(request).state()


@router.post('/api/plans')
async def propose(request: Request):
    plans = service(request)
    await plans.readiness()
    return await plans.propose(await body(request))


@router.post('/api/plans/forget')
async def forget(request: Request):
    plans = service(request)
    value = await body(request)
    if set(value) != {'requestId'} or not isinstance(value['requestId'], str) or not re.fullmatch(r'[\w-]{8,128}', value['requestId'], re.ASCII):
        raise JuneError('invalid-plan', 'A valid forget request id is required.', 400)
    # Replay the same revocation without clearing a newer explicit approval.
    plans.forget(value)
    return await plans.state()


@router.get('/api/plans/{pid}')
async def get(pid: str, request: Request):
    return await service(request).get(pid)


@router.post('/api/plans/{pid}/{operation}')
async def change(pid: str, operation: str, request: Request):
    if operation == 'voice-approve':
        from .commerce_api import voice_approve
        return await voice_approve(pid, request)
    plans = service(request)
    value = await body(request)
    if operation == 'approve':
        return await plans.approve(pid, value)
    if operation == 'cancel':
        return await plans.cancel(pid, value)
    raise JuneError('invalid-plan', 'Unknown workflow operation.', 404)
