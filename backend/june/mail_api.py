"""Email and Naukri jobs for Systems → Email & jobs. Sending and applying are always reviewed plans."""
from fastapi import APIRouter, Request
from .errors import JuneError
from .integrations_api import body

router = APIRouter()


def _plans(request):
    if request.query_params:
        raise JuneError('invalid-mail', 'These endpoints accept no query arguments.', 400)
    plans = getattr(request.app.state, 'plans', None)
    if plans is None:
        raise JuneError('mail-unavailable', 'Email and jobs are unavailable.', 503)
    return plans


def mail(request):
    found = getattr(_plans(request), 'mail', None)
    if found is None:
        raise JuneError('mail-unavailable', 'Email is unavailable.', 503)
    return found


def jobs(request):
    found = getattr(_plans(request), 'naukri', None)
    if found is None:
        raise JuneError('jobs-unavailable', 'Jobs are unavailable.', 503)
    return found


async def allowed(request):
    value = await body(request)
    if set(value) != {'allowed'} or type(value['allowed']) is not bool:
        raise JuneError('invalid-mail', 'Send allowed as true or false.', 400)
    return value['allowed']


@router.get('/api/mail')
async def mail_state(request: Request): return await mail(request).state()

@router.post('/api/mail/enable')
async def mail_enable(request: Request): return await mail(request).enable(await allowed(request))

@router.post('/api/mail/receipts/{rid}/check')
async def mail_receipt_check(rid: str, request: Request):
    service=mail(request)
    if await body(request)!={}:
        raise JuneError('invalid-mail','Checking Sent takes no arguments.',400)
    await service.check_receipt(rid)
    return await service.state()

@router.get('/api/jobs')
async def jobs_state(request: Request): return jobs(request).state()

@router.post('/api/jobs/enable')
async def jobs_enable(request: Request): return await jobs(request).enable(await allowed(request))

@router.post('/api/jobs/find')
async def jobs_find(request: Request):
    from .jobs import resume_text
    if await body(request) != {}:
        raise JuneError('invalid-jobs', 'Finding jobs takes no arguments.', 400)
    service, plans = jobs(request), _plans(request)
    if not service.enabled():
        from .jobs import ALLOW
        raise JuneError('jobs-consent', ALLOW, 403)
    await service.from_naukri()
    try:
        await service.from_mail(getattr(plans, 'mail', None))
    except JuneError:
        pass
    await service.rank(request.app.state.client, request.app.state.settings, resume_text(getattr(request.app.state, 'knowledge', None)))
    return service.state()

@router.post('/api/jobs/settings')
async def jobs_settings(request: Request):
    value = await body(request)
    service = jobs(request)
    if not value or set(value) - {'dailyLimit', 'stopped'}:
        raise JuneError('invalid-jobs', 'Send dailyLimit and/or stopped.', 400)
    if 'dailyLimit' in value:
        if type(value['dailyLimit']) is not int or not 1 <= value['dailyLimit'] <= 25:
            raise JuneError('invalid-jobs', 'Choose a daily limit from 1 to 25.', 400)
        service.set_setting('daily', value['dailyLimit'])
    if 'stopped' in value:
        if type(value['stopped']) is not bool:
            raise JuneError('invalid-jobs', 'Send stopped as true or false.', 400)
        service.set_setting('stopped', '1' if value['stopped'] else '0')
    return service.state()

@router.post('/api/jobs/{jid}/skip')
async def jobs_skip(jid: str, request: Request):
    if await body(request) != {}:
        raise JuneError('invalid-jobs', 'Skipping takes no arguments.', 400)
    service = jobs(request)
    service.get(jid)
    service.mark(jid, 'skipped')
    return service.state()


@router.post('/api/jobs/{jid}/check')
async def jobs_check(jid: str, request: Request):
    if await body(request) != {}:
        raise JuneError('invalid-jobs', 'Checking takes no arguments.', 400)
    service = jobs(request)
    result = await service.recheck(jid)
    return dict(service.state(), message=result['message'])


@router.post('/api/jobs/answers')
async def jobs_teach(request: Request):
    """Your answer to a recruiter question June asked about; she uses it automatically from then on."""
    value = await body(request)
    if set(value) != {'question', 'answer'} or not isinstance(value['question'], str) or not 1 <= len(value['question']) <= 300:
        raise JuneError('invalid-jobs', 'Send the question and your answer.', 400)
    service = jobs(request)
    try:
        service.profile.teach(value['question'], value['answer'], service.clock())
    except ValueError:
        raise JuneError('invalid-jobs', 'Write an answer of up to 300 characters.', 400) from None
    return service.state()


@router.post('/api/jobs/answers/forget')
async def jobs_forget(request: Request):
    value = await body(request)
    if set(value) != {'key'} or not isinstance(value['key'], str) or not 1 <= len(value['key']) <= 300:
        raise JuneError('invalid-jobs', 'Choose a saved answer.', 400)
    service = jobs(request)
    service.profile.forget(value['key'])
    return service.state()


def screen(request):
    found = getattr(_plans(request), 'screen', None)
    if found is None:
        raise JuneError('screen-unavailable', 'Screen reading is unavailable.', 503)
    return found


@router.get('/api/screen')
async def screen_state(request: Request): return await screen(request).state()

@router.post('/api/screen/enable')
async def screen_enable(request: Request): return await screen(request).enable(await allowed(request))
