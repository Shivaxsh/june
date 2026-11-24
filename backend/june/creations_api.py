"""Documents June made: list them, open one, or show it in Finder. Paths never leave the server."""
import re
from fastapi import APIRouter, Request
from .errors import JuneError
from .integrations_api import body

router = APIRouter()


def service(request):
    if request.query_params:
        raise JuneError('invalid-creation', 'These endpoints accept no query arguments.', 400)
    creations = getattr(request.app.state, 'creations', None)
    if creations is None:
        raise JuneError('creations-unavailable', 'June’s documents are unavailable.', 503)
    return creations


@router.get('/api/creations')
async def state(request: Request): return service(request).state()

@router.post('/api/creations/{cid}/{operation}')
async def act(cid: str, operation: str, request: Request):
    if operation not in ('open', 'reveal') or not re.fullmatch(r'[a-f0-9]{32}', cid) or await body(request) != {}:
        raise JuneError('invalid-creation', 'Choose open or reveal for one of June’s documents.', 400)
    return service(request).open(cid, reveal=operation == 'reveal')
