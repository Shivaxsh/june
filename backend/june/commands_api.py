"""Saved project commands and the one GitHub consent. Running a command is always a reviewed plan."""
from fastapi import APIRouter, Request
from .errors import JuneError
from .integrations_api import body

router = APIRouter()


def service(request):
    if request.query_params:
        raise JuneError('invalid-command', 'Project command endpoints accept no query arguments.', 400)
    commands = getattr(getattr(request.app.state, 'plans', None), 'commands', None)
    if commands is None:
        raise JuneError('commands-unavailable', 'Project commands are unavailable.', 503)
    return commands


@router.get('/api/commands')
async def state(request: Request): return service(request).state()

@router.post('/api/commands')
async def add(request: Request): return service(request).add(await body(request))

@router.post('/api/commands/github')
async def github(request: Request):
    value = await body(request)
    if set(value) != {'allowed'}:
        raise JuneError('invalid-command', 'Send allowed as true or false.', 400)
    return service(request).set_github(value['allowed'])

@router.post('/api/commands/{cid}/remove')
async def remove(cid: str, request: Request):
    if await body(request) != {}:
        raise JuneError('invalid-command', 'Removing a command takes no arguments.', 400)
    return service(request).remove(cid)
