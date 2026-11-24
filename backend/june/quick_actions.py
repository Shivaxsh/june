"""Developer and Designer quick actions. Fixed programs and fixed arguments only; each is a reviewed plan.

Nothing here builds a shell command. A request can supply a number of minutes, a port, a saved
project's name, an image format or a width, and each is checked against a fixed rule before use.
"""
import asyncio
from contextlib import suppress
import json
import os
from pathlib import Path
import re
import signal
import subprocess

from .app_actions import APPS, settled
from .app_info import nonliteral_request
from .errors import JuneError
from .timers import duration_phrase, number
from .tool_plans import Capability

GIT, LSOF, OPEN, SIPS, CAFFEINATE = '/usr/bin/git', '/usr/sbin/lsof', '/usr/bin/open', '/usr/bin/sips', '/usr/bin/caffeinate'
JUNE_PORTS = {3001: 'June’s app', 8001: 'June’s backend', 11434: 'June’s model'}
IMAGE_TYPES = {'.png', '.jpg', '.jpeg', '.heic', '.tif', '.tiff', '.gif', '.bmp', '.webp'}
IMAGE_FOLDER = 'June Images'
_LEAD = (r"\s*(?:(?:ok(?:ay)?|so|well|now|and|oh|um|uh|alright)[,.!\s]+)*(?:(?:hey\s+)?june[,!:\s]+)?(?:(?:can|could|would|will)\s+you\s+|i\s+(?:want|need)\s+(?:you\s+)?to\s+)?"
         r"(?:please\s+)?(?:just\s+)?")
_TAIL = r"(?:\s+(?:please|for me|now|right now))*[\s.!?]*"


def _match(pattern, text):
    return re.fullmatch(_LEAD + "(?:" + pattern + ")" + _TAIL, text, re.I)


def quick_request(text):
    """(intent, input or None) for a spoken quick action, else None."""
    # "Don't let my Mac sleep" is a request to keep it awake; any other negation is not a request.
    if not isinstance(text, str) or len(text) > 200 or nonliteral_request(text) or re.search(
            r"\b(?:do not|don['’]?t|never)\b(?!\s+let\s+(?:my\s+|the\s+|this\s+)?(?:mac|computer|laptop|screen)\b)", text, re.I):
        return None
    if _match(r"(?:start|begin|open)\s+(?:a\s+|my\s+|the\s+)?coding\s+(?:session|mode|workspace)|coding\s+mode|let['’]?s\s+code|start\s+coding", text):
        return ('coding-session', None)
    if _match(r"(?:start|begin|open)\s+(?:a\s+|my\s+|the\s+)?design\s+(?:session|mode|workspace)|design\s+mode|let['’]?s\s+design|start\s+designing", text):
        return ('design-workspace', None)
    awake = _match(r"(?:(?:keep|make)\s+(?:my\s+|the\s+|this\s+)?(?:mac|computer|laptop|screen)\s+(?:stay\s+)?awake|(?:stop|prevent|keep)\s+(?:my\s+|the\s+|this\s+)?(?:mac|computer|laptop|screen)\s+from\s+(?:going\s+to\s+)?sleep(?:ing)?"
                   r"|(?:don['’]?t|do\s+not)\s+let\s+(?:my\s+|the\s+|this\s+)?(?:mac|computer|laptop|screen)\s+(?:go\s+to\s+)?sleep)(?:\s+for\s+(?P<count>\d+|an?|[a-z]+(?:[- ][a-z]+)?)\s*(?P<unit>hours?|hrs?|minutes?|mins?))?", text)
    if awake:
        minutes = 60
        if awake['count']:
            count = number(awake['count'].lower())
            if count is None:
                return None
            minutes = count * (60 if awake['unit'].lower().startswith('h') else 1)
        return ('keep-awake', {'minutes': minutes}) if 1 <= minutes <= 720 else None
    if _match(r"(?:let|allow)\s+(?:my\s+|the\s+|this\s+)?(?:mac|computer|laptop)\s+(?:to\s+)?sleep(?:\s+again)?|stop\s+keeping\s+(?:my\s+|the\s+|this\s+)?(?:mac|computer|laptop)\s+awake|allow\s+sleep", text):
        return ('allow-sleep', None)
    mode = _match(r"(?:(?:switch|change|go)\s+(?:to|into)\s+|turn\s+on\s+|enable\s+|use\s+)?(?P<mode>dark|light)\s+mode(?:\s+on)?", text)
    if mode:
        return ('appearance', {'mode': mode['mode'].lower()})
    if _match(r"(?:turn\s+off|disable)\s+dark\s+mode|turn\s+dark\s+mode\s+off", text):
        return ('appearance', {'mode': 'light'})
    if _match(r"(?:turn\s+off|disable)\s+light\s+mode", text):
        return ('appearance', {'mode': 'dark'})
    if _match(r"toggle\s+(?:the\s+)?(?:dark\s+mode|light\s+mode|appearance|theme)|(?:switch|change)\s+(?:the\s+|my\s+)?(?:appearance|theme)", text):
        return ('appearance', {'mode': 'toggle'})
    if _match(r"(?:take|grab|capture)\s+(?:a\s+|the\s+)?screen\s?shot|screen\s?shot|capture\s+(?:my\s+|the\s+)?screen", text):
        return ('open-app', {'apps': ['screenshot']})
    if _match(r"(?:open|show|start|launch)\s+(?:the\s+|my\s+|a\s+)?colou?r\s+(?:picker|meter)|pick\s+(?:a\s+)?colou?r|colou?r\s+picker", text):
        return ('open-app', {'apps': ['color-meter']})
    port = _match(r"(?:free(?:\s+up)?|clear|kill|stop)\s+(?:whatever\s+is\s+(?:on|using)\s+|what(?:['’]s|\s+is)\s+(?:on|using)\s+|the\s+process\s+on\s+)?port\s+(?P<port>\d{2,5})"
                  r"|(?:what(?:['’]s|\s+is)|who(?:['’]s|\s+is))\s+(?:using|on|listening\s+on)\s+port\s+(?P<asked>\d{2,5})", text)
    if port:
        value = int(port['port'] or port['asked'])
        return ('free-port', {'port': value}) if 1024 <= value <= 65535 else None
    name = r"(?P<name>[a-z0-9][\w .-]{0,59}?)"
    status = _match(r"(?:(?:show|check|get)\s+(?:me\s+)?(?:the\s+)?|what['’]s\s+(?:the\s+)?|what\s+is\s+the\s+)?git\s+status(?:\s+(?:of|for|in|on)\s+(?:the\s+|my\s+)?" + name + r"(?:\s+(?:project|repo|repository))?)?"
                    r"|(?:(?:are\s+there|do\s+i\s+have)\s+)?(?:any\s+)?uncommitted\s+changes(?:\s+(?:in|on|for)\s+(?:the\s+|my\s+)?(?P<other>[a-z0-9][\w .-]{0,59}?)(?:\s+(?:project|repo|repository))?)?", text)
    if status:
        return ('git-status', {'name': (status['name'] or status['other'] or '').strip().lower()})
    hub = _match(r"open\s+(?:the\s+|my\s+)?(?:" + name + r"\s+)?(?:(?:repo|repository|project)\s+)?on\s+github|open\s+(?:the\s+|my\s+)?github\s+(?:repo|repository|page)(?:\s+(?:of|for)\s+(?P<other>[a-z0-9][\w .-]{0,59}?))?", text)
    if hub:
        named = re.sub(r"(?:^|\s+)(?:repo|repository|project)$", '', (hub['name'] or hub['other'] or '').strip().lower())
        return ('open-github', {'name': named})
    images = _match(r"(?:convert|resize|export)\s+(?:my\s+|the\s+|all\s+(?:my\s+|the\s+)?)?(?:images|pictures|photos)(?:\s+(?:to|as|into)\s+(?P<format>png|jpe?g))?"
                    r"(?:\s+(?:to|at)\s+(?P<width>\d{2,5})(?:\s*(?:px|pixels?))?(?:\s+wide)?)?", text)
    if images and (images['format'] or images['width'] or re.match(r"\s*\W*(?:\w+\W+){0,4}?(?:convert|resize)", text, re.I)):
        value = {'format': 'jpeg' if (images['format'] or 'png').lower().startswith('jp') else 'png'}
        if images['width']:
            value['width'] = int(images['width'])
        return ('convert-images', value)
    return None


async def run(argv, timeout=10):
    """(exit code, output) from one fixed program with a minimal environment. No shell is involved."""
    process = None
    try:
        process = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env={'PATH': '/usr/bin:/bin:/usr/sbin', 'HOME': str(Path.home()), 'LANG': 'en_US.UTF-8', 'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'})
        output, _ = await asyncio.wait_for(process.communicate(), timeout)
        return process.returncode, output[:65536].decode('utf-8', 'replace')
    except (OSError, TimeoutError):
        return -1, ''
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            with suppress(ProcessLookupError): await process.wait()


def _blocking(coroutine):
    """Resolve an injected (test) runner from synchronous plan-building code."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, coroutine).result(10)


class QuickNative:
    """The signed June Quick helper: one fixed operation, switching the Mac's appearance."""
    def __init__(self, binary):
        self.binary = Path(binary)

    def ready(self):
        return self.binary.is_file()

    async def appearance(self, mode):
        process = None
        try:
            process = await asyncio.create_subprocess_exec(str(self.binary), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            output, _ = await asyncio.wait_for(process.communicate(json.dumps({'operation': 'appearance', 'mode': mode}).encode()), 25)
            reply = json.loads(output) if len(output) <= 4096 else None
        except (OSError, TimeoutError, ValueError):
            raise JuneError('quick-unavailable', 'The Mac did not confirm the appearance change.', 503) from None
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                with suppress(ProcessLookupError): await process.wait()
        if not isinstance(reply, dict) or reply.get('ok') is not True or type(reply.get('dark')) is not bool:
            if isinstance(reply, dict) and reply.get('code') == 'automation-permission':
                raise JuneError('automation-permission', 'Allow June Quick to control System Events in System Settings → Privacy & Security → Automation, then ask again.', 403)
            raise JuneError('quick-unavailable', 'The Mac did not confirm the appearance change.', 503)
        return reply['dark']


def register(plans, *, hands=None, native=None, runner=run, home=None, spawn=None, kill=None):
    home = Path(home or Path.home())
    state = {'awake': None}
    spawn = spawn or (lambda seconds: subprocess.Popen([CAFFEINATE, '-d', '-i', '-t', str(seconds)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    kill = kill or (lambda pid: os.kill(pid, signal.SIGTERM))
    invalid = lambda message: JuneError('invalid-plan', message, 400)

    def only(value, keys, optional=()):
        if not isinstance(value, dict) or not set(keys) <= set(value) or set(value) - set(keys) - set(optional):
            raise invalid('June cannot plan that request.')

    # --- Sessions: the reviewed apps, in order -------------------------------------------------
    def apps(*keys):
        return [('app.open', dict(app=key, bundle=APPS[key].bundle),
                 f'Open or bring {APPS[key].label} to the front (bundle {APPS[key].bundle}). Nothing else is opened, closed or changed.', 'Open ' + APPS[key].label) for key in keys]

    def coding(value):
        steps = apps('vscode', 'terminal')
        playlist = plans.intents.get('play-playlist')
        if playlist:
            with suppress(JuneError): steps += playlist({})
        return steps
    plans.intents['coding-session'] = coding
    plans.intents['design-workspace'] = lambda value: apps('figma', 'affinity', 'chrome')

    # --- Keep the Mac awake ---------------------------------------------------------------------
    def stop_awake():
        process, state['awake'] = state['awake'], None
        if process is not None and process.poll() is None:
            process.terminate(); return True
        return False

    async def keep_awake(payload):
        stop_awake()
        state['awake'] = spawn(payload['minutes'] * 60)
        await asyncio.sleep(0.2)
        alive = state['awake'].poll() is None
        return dict(verified=alive, failed=not alive, message=f'Your Mac will stay awake for {duration_phrase(payload["minutes"] * 60)}. Say “let my Mac sleep” to end it early.' if alive
                    else 'The Mac did not start staying awake.')

    async def allow_sleep(payload):
        return dict(verified=True, message='Your Mac can sleep again.' if stop_awake() else 'June is not keeping your Mac awake, so nothing was changed.')

    def awake_steps(value):
        only(value, ['minutes'])
        if type(value['minutes']) is not int or not 1 <= value['minutes'] <= 720:
            raise invalid('Choose from 1 minute to 12 hours.')
        return [('quick.keep-awake', dict(minutes=value['minutes']),
                 f'Keep this Mac and its display awake for {duration_phrase(value["minutes"] * 60)} (caffeinate). It ends by itself, or when you say “let my Mac sleep”. Nothing else is changed.',
                 'Keep the Mac awake for ' + duration_phrase(value['minutes'] * 60))]
    awake_steps.accepts_input = True
    plans.capabilities['quick.keep-awake'] = Capability('quick.keep-awake', 'Keep the Mac awake', 'local', 'local', True, keep_awake)
    plans.capabilities['quick.allow-sleep'] = Capability('quick.allow-sleep', 'Let the Mac sleep again', 'local', 'local', True, allow_sleep)
    plans.intents['keep-awake'] = awake_steps
    plans.intents['allow-sleep'] = lambda value: [('quick.allow-sleep', {}, 'Stop keeping this Mac awake. Normal sleep settings apply again.')]

    # --- Light and dark appearance --------------------------------------------------------------
    async def appearance(payload):
        try:
            dark = await native.appearance(payload['mode'])
        except JuneError as failure:
            return dict(verified=False, failed=True, message=failure.message + ' Nothing was changed.')
        wanted = payload['mode']
        ok = wanted == 'toggle' or dark == (wanted == 'dark')
        return dict(verified=ok, message=f'Your Mac is now in {"dark" if dark else "light"} mode.' if ok else 'The Mac did not change its appearance.')

    def appearance_steps(value):
        only(value, ['mode'])
        if value['mode'] not in ('dark', 'light', 'toggle'):
            raise invalid('Choose dark, light or toggle.')
        words = {'dark': 'Switch this Mac to dark mode', 'light': 'Switch this Mac to light mode', 'toggle': 'Switch this Mac between light and dark mode'}[value['mode']]
        return [('quick.appearance', dict(mode=value['mode']), words + ' (System Settings → Appearance). Nothing else is changed. macOS may ask once to let June Quick control System Events.', words)]
    appearance_steps.accepts_input = True
    plans.capabilities['quick.appearance'] = Capability('quick.appearance', 'Switch light and dark mode', 'local', 'local', True, appearance if native else None,
        available=bool(native and native.ready()), unavailable_reason='The quick-action helper is not installed. Run npm run quick:setup.')
    plans.intents['appearance'] = appearance_steps

    # --- Free a port: shows the process first, reviewed every time ------------------------------
    def listener_sync(port):
        """(pid, command) of this user's process listening on the port, or None. Read-only."""
        try:
            done = subprocess.run([LSOF, '-nP', '-iTCP:' + str(port), '-sTCP:LISTEN', '-Fpcu'], capture_output=True, timeout=4, text=True, stdin=subprocess.DEVNULL)
            return parse_listener(done.stdout if done.returncode == 0 else '')
        except (OSError, subprocess.SubprocessError):
            return None

    def parse_listener(output):
        fields = {line[0]: line[1:] for line in output.splitlines() if line}
        if not fields.get('p', '').isdigit() or fields.get('u') != str(os.getuid()):
            return None
        return int(fields['p']), re.sub(r'[^\w .()+-]', '', fields.get('c', 'unknown'))[:60] or 'unknown'

    async def listener(port):
        if runner is run:
            return await asyncio.to_thread(listener_sync, port)
        code, output = await runner([LSOF, '-nP', '-iTCP:' + str(port), '-sTCP:LISTEN', '-Fpcu'], 4)
        return parse_listener(output if code == 0 else '')

    def listener_now(port):
        if runner is run:
            return listener_sync(port)
        code, output = _blocking(runner([LSOF, '-nP', '-iTCP:' + str(port), '-sTCP:LISTEN', '-Fpcu'], 4))
        return parse_listener(output if code == 0 else '')

    async def free_port(payload):
        found = await listener(payload['port'])
        if found is None:
            return dict(verified=True, message=f'Port {payload["port"]} is already free. Nothing was stopped.')
        if found != (payload['pid'], payload['command']):
            return dict(verified=False, failed=True, message=f'The process on port {payload["port"]} changed since you reviewed it, so nothing was stopped. Ask again to review the new one.')
        try:
            kill(payload['pid'])
        except OSError:
            return dict(verified=False, failed=True, message=f'The Mac did not let June stop {payload["command"]}. Nothing was changed.')
        for _ in range(10):
            await asyncio.sleep(0.3 if runner is run else 0)
            if await listener(payload['port']) is None:
                return dict(verified=True, message=f'Port {payload["port"]} is free. {payload["command"]} (process {payload["pid"]}) was stopped.')
        return dict(verified=False, message=f'{payload["command"]} was asked to stop but is still using port {payload["port"]}.')

    def port_steps(value):
        only(value, ['port'])
        port = value['port']
        if type(port) is not int or not 1024 <= port <= 65535:
            raise invalid('Choose a port from 1024 to 65535.')
        if port in JUNE_PORTS:
            raise invalid(f'Port {port} is {JUNE_PORTS[port]}. June will not stop herself.')
        found = listener_now(port)
        if found is None:
            raise JuneError('port-free', f'Nothing is listening on port {port} for your account, so there is nothing to stop.', 409)
        pid, command = found
        return [('quick.free-port', dict(port=port, pid=pid, command=command),
                 f'Stop {command} (process {pid}), which is listening on port {port}, by asking it to quit (SIGTERM). Unsaved work in that program may be lost. Nothing else is stopped.',
                 f'Stop {command} on port {port}')]
    port_steps.accepts_input = True
    # Stopping a program is reviewed every time.
    plans.capabilities['quick.free-port'] = Capability('quick.free-port', 'Stop the program using a port', 'local', 'local', False, free_port)
    plans.intents['free-port'] = port_steps

    # --- Saved projects: git status and the GitHub page -----------------------------------------
    def project(value):
        only(value, ['name'])
        if not isinstance(value['name'], str) or len(value['name']) > 60:
            raise invalid('Name a project saved in Hands.')
        saved = hands.project_list() if hands else []
        wanted = value['name'].strip().casefold()
        chosen = [p for p in saved if p['name'].casefold() == wanted] if wanted else saved if len(saved) == 1 else []
        if not chosen:
            raise JuneError('project-missing', ('That project is not saved in Hands. ' if wanted else 'Say which project. ' if saved else 'No project is saved yet. ')
                            + 'Add its folder in Systems → Hands' + (': ' + ', '.join(p['name'] for p in saved) + ' is saved.' if saved and wanted else '.'), 404)
        folder = Path(chosen[0]['folderPath'])
        if not folder.is_dir():
            raise JuneError('project-changed', 'That project folder is unavailable. Check it in Hands.', 409)
        return chosen[0]['id'], chosen[0]['name'], str(folder)

    def git(folder, *arguments):
        return [GIT, '-C', folder, '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', *arguments]

    async def git_status(payload):
        code, output = await runner(git(payload['path'], 'status', '--short', '--branch'), 15)
        if code != 0:
            return dict(verified=False, failed=True, message=f'{payload["name"]} is not a git repository, or git could not read it.')
        lines = output.splitlines()
        head = lines[0][3:] if lines and lines[0].startswith('## ') else 'an unknown branch'
        branch = re.split(r'\.\.\.| \[', head)[0][:80]
        ahead, behind = re.search(r'ahead (\d+)', head), re.search(r'behind (\d+)', head)
        changed = len([line for line in lines[1:] if line.strip()])
        _, last = await runner(git(payload['path'], 'log', '-1', '--format=%s'), 10)
        parts = [f'{payload["name"]} is on branch {branch}', f'{changed} changed file{"" if changed == 1 else "s"}' if changed else 'no uncommitted changes']
        if ahead: parts.append(f'{ahead[1]} commit{"" if ahead[1] == "1" else "s"} ahead of the remote')
        if behind: parts.append(f'{behind[1]} behind')
        message = ', '.join(parts) + '.'
        last = re.sub(r'[\x00-\x1f\x7f]', ' ', last).strip()[:120]
        return dict(verified=True, message=message + (f' Last commit: “{last}”.' if last else ''))

    def status_steps(value):
        pid, name, folder = project(value)
        return [('quick.git-status', dict(project=pid, name=name, path=folder),
                 f'Read the git status of {name} ({folder}): its branch, how many files changed, and the last commit message. Nothing is changed, committed or sent.', 'Git status of ' + name)]
    status_steps.accepts_input = True
    plans.capabilities['quick.git-status'] = Capability('quick.git-status', 'Read a saved project’s git status', 'local', 'read', True, git_status)
    plans.intents['git-status'] = status_steps

    def remote_now(folder):
        if runner is run:
            try:
                done = subprocess.run(git(folder, 'remote', 'get-url', 'origin'), capture_output=True, timeout=5, text=True, stdin=subprocess.DEVNULL,
                                      env={'PATH': '/usr/bin:/bin', 'HOME': str(Path.home()), 'GIT_TERMINAL_PROMPT': '0'})
                return done.stdout.strip() if done.returncode == 0 else ''
            except (OSError, subprocess.SubprocessError):
                return ''
        code, output = _blocking(runner(git(folder, 'remote', 'get-url', 'origin'), 5))
        return output.strip() if code == 0 else ''

    def github_url(remote):
        match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?', remote)
        return f'https://github.com/{match[1]}/{match[2]}' if match else None

    async def open_github(payload):
        if github_url(payload['url']) != payload['url']:
            return dict(verified=False, failed=True, message='That is not a GitHub repository page. Nothing was opened.')
        code, _ = await runner([OPEN, '-b', APPS['chrome'].bundle, payload['url']], 15)
        return dict(verified=code == 0, failed=code != 0, message=f'Opened {payload["url"]} in Chrome.' if code == 0 else 'Chrome did not open the page.')

    def github_steps(value):
        pid, name, folder = project(value)
        url = github_url(remote_now(folder))
        if not url:
            raise JuneError('no-github', f'{name} has no GitHub remote named origin, so there is no GitHub page to open.', 409)
        return [('quick.open-github', dict(project=pid, name=name, url=url), f'Open {url} in Google Chrome. Chrome contacts github.com as it would if you typed the address. Nothing is pushed or changed.',
                 f'Open {name} on GitHub')]
    github_steps.accepts_input = True
    plans.capabilities['quick.open-github'] = Capability('quick.open-github', 'Open a saved project’s GitHub page', 'local', 'local', True, open_github)
    plans.intents['open-github'] = github_steps

    # --- Images: copies only, from one fixed folder ---------------------------------------------
    def images():
        folder = home / IMAGE_FOLDER
        if not folder.is_dir():
            raise JuneError('no-images', f'Create a folder named “{IMAGE_FOLDER}” in your home folder and put the images there first.', 409)
        files = sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith('.') and p.suffix.lower() in IMAGE_TYPES and not p.is_symlink())
        if not files:
            raise JuneError('no-images', f'There are no images in your “{IMAGE_FOLDER}” folder.', 409)
        if len(files) > 200:
            raise JuneError('too-many-images', f'Keep up to 200 images in “{IMAGE_FOLDER}” at a time.', 409)
        return folder, files

    async def convert(payload):
        try:
            folder, files = images()
        except JuneError as failure:
            return dict(verified=False, failed=True, message=failure.message)
        out = folder / 'converted'
        out.mkdir(exist_ok=True)
        extension = 'jpg' if payload['format'] == 'jpeg' else 'png'
        made = 0
        for source in files:
            target = out / (source.stem + '.' + extension)
            argv = [SIPS, '-s', 'format', payload['format']] + (['--resampleWidth', str(payload['width'])] if payload.get('width') else []) + [str(source), '--out', str(target)]
            code, _ = await runner(argv, 20)
            made += code == 0 and target.is_file()
        what = payload['format'].upper() + (f', {payload["width"]} pixels wide' if payload.get('width') else '')
        return dict(verified=made == len(files), failed=made == 0,
                    message=f'Saved {made} image{"" if made == 1 else "s"} as {what} in “{IMAGE_FOLDER}/converted”. The originals are unchanged.' if made == len(files)
                    else f'Only {made} of {len(files)} images could be converted. Check “{IMAGE_FOLDER}/converted”.')

    def convert_steps(value):
        only(value, ['format'], ['width'])
        if value['format'] not in ('png', 'jpeg') or 'width' in value and (type(value['width']) is not int or not 16 <= value['width'] <= 10000):
            raise invalid('Choose PNG or JPEG, and a width from 16 to 10000 pixels.')
        _, files = images()
        payload = dict(format=value['format'], **({'width': value['width']} if 'width' in value else {}))
        what = value['format'].upper() + (f', resized to {value["width"]} pixels wide' if 'width' in value else '')
        return [('quick.convert-images', payload, f'Save a copy of the {len(files)} image{"" if len(files) == 1 else "s"} in your “{IMAGE_FOLDER}” folder as {what}, into “{IMAGE_FOLDER}/converted”. '
                 'Originals are never changed or deleted; copies with the same name there are replaced.', f'Convert images to {what}')]
    convert_steps.accepts_input = True
    plans.capabilities['quick.convert-images'] = Capability('quick.convert-images', 'Convert or resize images as copies', 'local', 'local', True, convert)
    plans.intents['convert-images'] = convert_steps
    plans.quick_state = state


CARD = {
    'coding-session': 'your coding session', 'design-workspace': 'your design workspace', 'keep-awake': 'keeping your Mac awake', 'allow-sleep': 'letting your Mac sleep',
    'appearance': 'the appearance change', 'open-app': 'that', 'free-port': 'stopping that program', 'git-status': 'the git status check', 'open-github': 'opening the GitHub page',
    'convert-images': 'the image conversion',
}


async def quick_chat(question, request_key, plans):
    """App-owned reply to a quick action: a card to review, or the checked result when remembered."""
    request = quick_request(question)
    if request is None or plans is None or request[0] not in plans.intents:
        return None
    intent, value = request
    readiness = getattr(plans, 'readiness', None)
    if readiness: await readiness()
    try:
        reply = await plans.propose({'requestId': request_key, 'intent': intent, **({'input': value} if value is not None else {})})
    except JuneError as failure:
        return dict(reply=failure.message + ' Nothing was changed.')
    if reply['plan']['status'] == 'proposed':
        remember = '' if not reply['plan'].get('rememberable') else ' Tick “Don’t ask again” to skip the card next time.'
        return dict(plan=reply['plan'], serverNow=reply['serverNow'], reply=f'I’ve prepared {CARD[intent]}. Check the card below and approve it.' + remember)
    reply = await settled(plans, reply)
    results = [s.get('result') for s in reply['plan']['steps'] if s.get('result')]
    return dict(plan=reply['plan'], serverNow=reply['serverNow'], reply=' '.join(r['message'] for r in results) if results else 'I couldn’t confirm the result. Check before asking again.')
