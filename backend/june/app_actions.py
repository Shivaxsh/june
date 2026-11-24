"""June opens only the apps the person listed, by fixed bundle id, through reviewed plans."""
import asyncio
from contextlib import suppress
from dataclasses import dataclass
import json
from pathlib import Path
import re

from .app_info import DEVICE_ACTION, nonliteral_request
from .errors import JuneError
from .tool_plans import Capability, digest


@dataclass(frozen=True)
class App:
    label: str
    bundle: str
    aliases: tuple


APPS = {
    'vscode': App('Visual Studio Code', 'com.microsoft.VSCode', ('vscode', 'visualstudiocode', 'code')),
    'claude': App('Claude', 'com.anthropic.claudefordesktop', ('claude',)),
    'chatgpt': App('ChatGPT', 'com.openai.codex', ('chatgpt',)),
    'powerpoint': App('PowerPoint', 'com.microsoft.Powerpoint', ('powerpoint', 'microsoftpowerpoint', 'ppt')),
    'excel': App('Excel', 'com.microsoft.Excel', ('excel', 'microsoftexcel')),
    'word': App('Word', 'com.microsoft.Word', ('word', 'microsoftword')),
    'notes': App('Notes', 'com.apple.Notes', ('notes', 'applenotes')),
    'chrome': App('Google Chrome', 'com.google.Chrome', ('chrome', 'googlechrome')),
    'calendar': App('Calendar', 'com.apple.iCal', ('calendar', 'applecalendar')),
    'music': App('Music', 'com.apple.Music', ('music', 'applemusic')),
    'figma': App('Figma', 'com.figma.Desktop', ('figma',)),
    'mail': App('Mail', 'com.apple.mail', ('mail', 'applemail')),
    'affinity': App('Affinity', 'com.canva.affinity', ('affinity',)),
    'app-store': App('App Store', 'com.apple.AppStore', ('appstore',)),
    'terminal': App('Terminal', 'com.apple.Terminal', ('terminal',)),
    # Two system tools for the designer quick actions (8.2d).
    'screenshot': App('Screenshot', 'com.apple.screenshot.launcher', ('screenshot', 'screenshottool')),
    'color-meter': App('Digital Color Meter', 'com.apple.DigitalColorMeter', ('digitalcolormeter', 'colormeter', 'colorpicker', 'colourpicker', 'colourmeter')),
}
ALIASES = {alias: key for key, app in APPS.items() for alias in app.aliases}
# Everyday and spoken names for the same fifteen apps. They add no app.
ALIASES.update({'vs': 'vscode', 'visualstudio': 'vscode', 'msword': 'word', 'msexcel': 'excel', 'mspowerpoint': 'powerpoint',
                'browser': 'chrome', 'calender': 'calendar', 'ical': 'calendar', 'email': 'mail', 'emails': 'mail', 'itunes': 'music',
                'affinitydesigner': 'affinity', 'affinityphoto': 'affinity', 'affinitypublisher': 'affinity', 'affinitystudio': 'affinity',
                'claudeai': 'claude', 'commandline': 'terminal', 'macappstore': 'app-store'})
MAX_APPS = 3
_LEAD = (r"\s*(?:(?:ok(?:ay)?|so|well|no|yes|yeah|now|and|then|alright|right|oh|uh|um|hmm|hi|hello)[,.!\s]+)*(?:(?:hey\s+)?june[,!:\s]+)?"
         r"(?:(?:ok(?:ay)?|so|now|then)[,\s]+)?(?:just\s+(?:to\s+)?)?(?:please\s+)?"
         r"(?:(?:can|could|would|will)\s+you\s+|i\s+(?:want|need|would\s+like)(?:\s+you)?\s+to\s+|i['’]d\s+like(?:\s+you)?\s+to\s+|let['’]?s\s+)?"
         r"(?:please\s+)?(?:just\s+)?(?:go\s+ahead\s+and\s+)?(?:quickly\s+)?")
_VERB = r"(?:open(?:\s+up)?|launch|start(?:\s+up)?|fire\s+up|pull\s+up|bring\s+up|switch\s+(?:over\s+)?to)"
_TAIL = r"(?:\s+(?:please|for me|now|right now|quickly))*[\s.!?]*"
REQUEST = re.compile(_LEAD + r"(?P<verb>" + _VERB + r")\s+(?P<names>.+?)" + _TAIL, re.I)
# A short spoken lead-in ("I think you should open Figma") is accepted only when every name is a listed app.
LOOSE = re.compile(r"(?P<pre>[^?]{0,60}?)\b" + _VERB + r"\s+(?P<names>[^?]+?)(?:\s+(?:please|for me|now|right now|quickly))*[\s.!]*", re.I)
_NOT_A_REQUEST = re.compile(r"\b(?:how|what|why|when|where|which|who|whether|if|should\s+i|did|does|do|not|never|cannot|unable|without|before|after|"
                            r"instead|stop|was|were|is|has|have|had|\w+n['’]?t)\b", re.I)
CLOSE = re.compile(_LEAD + r"(?:close|quit|exit|kill|shut(?:\s+down)?)\s+(?P<names>.+?)" + _TAIL, re.I)
NEW_CHAT = re.compile(_LEAD + r"(?:open|start|create|make|begin)\s+(?:a\s+|an\s+)?(?:new|another|fresh)\s+(?:chat|conversation|thread)" + _TAIL, re.I)
_KIND = r"(?:app|application|program|software|sheets?|spreadsheet|presentation|document|doc|browser|window|desktop|editor)"


def _resolve(raw):
    """(registry key or None, the name as said) for one spoken app name."""
    name = re.sub(r"^(?:the|my|that|this)\s+", '', raw.strip(), flags=re.I)
    said = name
    while True:
        key = ALIASES.get(re.sub(r'[^a-z0-9]', '', name.lower()))
        shorter = re.sub(r"\s+" + _KIND + r"$", '', name, flags=re.I)
        if key is not None or shorter == name:
            return key, re.sub(r"\s+(?:app|application)$", '', said, flags=re.I)
        name = shorter


def _names(text):
    return [part for part in re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+", text.strip())]


def app_request(text):
    """(registry keys, names not on the list) for a direct request to open listed apps, else None.
    A lone "open VS Code" stays with the original VS Code action."""
    if not isinstance(text, str) or nonliteral_request(text):
        return None
    match, loose = REQUEST.fullmatch(text), False
    if not match:
        match, loose = LOOSE.fullmatch(text), True
        if not match or _NOT_A_REQUEST.search(match['pre']):
            return None
    keys, unknown = [], []
    for raw in _names(match['names']):
        key, name = _resolve(raw)
        if not name or len(name.split()) > 4:
            return None
        if key is None:
            unknown.append(name.lower())
        elif key not in keys:
            keys.append(key)
    if not keys or loose and unknown or keys == ['vscode'] and not unknown:
        return None
    return keys, unknown


def side_request(text):
    """An app-owned sentence for requests near app opening that June cannot perform, else None."""
    if not isinstance(text, str) or nonliteral_request(text):
        return None
    if NEW_CHAT.fullmatch(text):
        return 'I can’t start a new chat from inside a chat. Use New chat in the sidebar.'
    listed = ', '.join(app.label for app in APPS.values())
    match = CLOSE.fullmatch(text)
    if match and all(_resolve(raw)[0] for raw in _names(match['names'])):
        return 'I can open the apps on your list, but I can’t close or quit them yet. Nothing was changed.'
    match = REQUEST.fullmatch(text)
    if match and re.match(r"open|launch", match['verb'], re.I) and not re.search(r"\b(?:open|launch)\s+(?:up\s+)?my\s+[a-z]+\s*[.!?]*$", text):
        # "open my heart" is not an app; an unlisted app is named by itself ("open Safari")
        names = [_resolve(raw) for raw in _names(match['names'])]
        # The same narrow shape the not-connected reply already catches: a short app-like name, not a file or a phrase.
        if names and not any(key for key, _ in names) and all(DEVICE_ACTION.match('open ' + name) for _, name in names):
            return f'{", ".join(name.title() for _, name in names)} isn’t on the list of apps I can open. Nothing was opened. I can open: {listed}.'
    return None


class AppNative:
    def __init__(self, binary):
        self.binary = Path(binary)

    def ready(self):
        return self.binary.is_file()

    async def open(self, bundle):
        """The state macOS shows after asking: active, running, not-running, failed or unverified."""
        if bundle not in {app.bundle for app in APPS.values()} or not self.ready():
            return 'failed'
        process = None
        try:
            process = await asyncio.create_subprocess_exec(str(self.binary), '--open', bundle,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            output, _ = await asyncio.wait_for(process.communicate(), 27)
            reply = json.loads(output) if process.returncode == 0 and len(output) <= 4096 else None
            if not isinstance(reply, dict) or reply.get('protocol') != 1 or reply.get('bundleId') != bundle:
                return 'unverified'
            state = reply.get('state')
            return state if state in ('active', 'running', 'not-running', 'failed') else 'unverified'
        except (OSError, TimeoutError, ValueError):
            return 'unverified'
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                with suppress(ProcessLookupError): await process.wait()


def register(plans, native):
    async def open_app(payload):
        app = APPS.get(payload.get('app')) if isinstance(payload, dict) else None
        if app is None or payload.get('bundle') != app.bundle:
            return dict(verified=False, failed=True, message='That app is not on June’s list. Nothing was opened.')
        state = await native.open(app.bundle)
        if payload.get('app') == 'screenshot' and state in ('active', 'running'):
            return dict(verified=True, message='The screenshot toolbar is open. Choose an area or window, or press Escape to cancel.')
        if state == 'active': return dict(verified=True, message=f'{app.label} is open and in front.')
        if state == 'running': return dict(verified=True, message=f'{app.label} is running; it may be behind another window.')
        if state == 'failed': return dict(verified=False, failed=True, message=f'The Mac could not open {app.label}.')
        return dict(verified=False, message=f'June asked the Mac to open {app.label} but could not confirm it. Check before asking again.')

    plans.capabilities['app.open'] = Capability('app.open', 'Open an app from your list', 'local', 'local', True,
        open_app if native else None, available=False, unavailable_reason='The app helper is not installed. Run npm run apps:setup.')

    def steps(value):
        if not isinstance(value, dict) or set(value) != {'apps'} or not isinstance(value['apps'], list):
            raise JuneError('invalid-plan', 'Choose apps from June’s list.', 400)
        keys = value['apps']
        if not 1 <= len(keys) <= MAX_APPS or len(set(map(str, keys))) != len(keys) or any(not isinstance(k, str) or k not in APPS for k in keys):
            raise JuneError('invalid-plan', f'Choose one to {MAX_APPS} different apps from June’s list.', 400)
        return [('app.open', dict(app=key, bundle=APPS[key].bundle),
                 f'Open or bring {APPS[key].label} to the front (bundle {APPS[key].bundle}). Nothing else is opened, closed or changed.',
                 'Open ' + APPS[key].label) for key in keys]

    steps.accepts_input = True
    plans.intents['open-app'] = steps

    def app_list():
        with plans.db() as db:
            trusted = {row[0] for row in db.execute('SELECT signature FROM trust')}
        return plans.envelope(apps=[dict(id=key, label=app.label,
            remembered=digest([['app.open', dict(app=key, bundle=app.bundle)]]) in trusted) for key, app in APPS.items()])

    plans.app_list = app_list
    plans.apps_native = native


async def settled(plans, reply):
    """Follow a plan that started without a card (remembered approval) to its checked outcome."""
    plan = reply['plan']
    for _ in range(62):
        if plan['status'] not in ('approved', 'running'):
            break
        await asyncio.sleep(0.5)
        reply = await plans.get(plan['id']); plan = reply['plan']
    return reply


async def app_chat(question, request_key, plans):
    """App-owned reply to "open Chrome and Figma". None when the words are not such a request."""
    request = app_request(question)
    if plans is None or 'open-app' not in plans.intents:
        return None
    if request is None:
        said = side_request(question)
        return dict(reply=said) if said else None
    keys, unknown = request
    labels = [APPS[k].label for k in keys]
    names = labels[0] if len(labels) == 1 else ', '.join(labels[:-1]) + ' and ' + labels[-1]
    if unknown:
        return dict(reply=f'{", ".join(n.title() for n in unknown)} isn’t on the list of apps I can open. Nothing was opened. I can open: {", ".join(a.label for a in APPS.values())}.')
    if len(keys) > MAX_APPS:
        return dict(reply=f'I can open up to {MAX_APPS} apps at a time. Nothing was opened.')
    await plans.readiness()
    try:
        reply = await plans.propose({'requestId': request_key, 'intent': 'open-app', 'input': {'apps': keys}})
    except JuneError as failure:
        return dict(reply=failure.message + ' Nothing was opened.')
    if reply['plan']['status'] == 'proposed':
        return dict(plan=reply['plan'], serverNow=reply['serverNow'],
            reply=f'I’ve prepared a plan to open {names}. Approve it on the card below. Tick “Don’t ask again” to let me open {"it" if len(keys) == 1 else "them"} by voice next time.')
    reply = await settled(plans, reply)
    plan = reply['plan']
    results = [s.get('result') for s in plan['steps'] if s.get('result')]
    if plan['status'] == 'completed' and results:
        text = ' '.join(r['message'] for r in results)
    elif results:
        text = ' '.join(r['message'] for r in results)
    else:
        text = f'I couldn’t confirm that {names} opened. Check before asking again.'
    return dict(plan=plan, serverNow=reply['serverNow'], reply=text)
