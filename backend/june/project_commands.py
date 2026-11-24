"""Project commands for folders saved in Hands: fixed git recipes and the person's own saved commands.

The language model never writes a command. Built-in recipes are fixed argument lists. A saved command
is text the person typed in Systems, stored here, and run exactly as typed after they review it.
Pushing is reviewed every time; June never pushes with force and never uses administrator rights.
"""
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import time
import uuid

from .app_actions import settled
from .app_info import nonliteral_request
from .errors import JuneError
from .tool_plans import Capability, digest

GIT = '/usr/bin/git'
PATH = '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'
ALLOW = 'Allow GitHub first: open Systems → Integrations → Project commands and click Allow GitHub.'


def environment():
    env = {'PATH': PATH, 'HOME': str(Path.home()), 'LANG': 'en_US.UTF-8', 'USER': os.environ.get('USER', ''), 'GIT_TERMINAL_PROMPT': '0'}
    if os.environ.get('SSH_AUTH_SOCK'):
        env['SSH_AUTH_SOCK'] = os.environ['SSH_AUTH_SOCK']
    return env


def run(argv, timeout=10, cwd=None):
    """(exit code, output) of one program. Blocking; callers use a worker thread. -1 means it did not finish."""
    try:
        done = subprocess.run(argv, cwd=cwd, env=environment(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        return done.returncode, done.stdout[-65536:].decode('utf-8', 'replace')
    except subprocess.TimeoutExpired:
        return -1, 'The command did not finish in time and was stopped.'
    except OSError:
        return -1, 'The command could not be started.'


def start_server(text, cwd, log):
    with open(log, 'ab') as output:
        return subprocess.Popen(['/bin/zsh', '-c', text], cwd=cwd, env=environment(), stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)


def stop_server(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, AttributeError):
        pass


def github_url(remote):
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9][A-Za-z0-9-]{0,38})/([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?', remote or '')
    return f'https://github.com/{match[1]}/{match[2]}' if match else None


def tail(output, limit=380):
    text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', output or '')
    text = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', text).strip()
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    text = ' / '.join(lines[-8:])
    return text[-limit:]


_LEAD = (r"\s*(?:(?:ok(?:ay)?|so|well|now|and|oh|um|uh|alright)[,.!\s]+)*(?:(?:hey\s+)?june[,!:\s]+)?(?:(?:can|could|would|will)\s+you\s+|i\s+(?:want|need)\s+(?:you\s+)?to\s+)?"
         r"(?:please\s+)?(?:just\s+)?")
_TAIL = r"(?:\s+(?:please|for me|now|right now))*[\s.!?]*"
_PROJECT = r"(?:\s+(?:in|for|of|on)\s+(?:the\s+|my\s+)?(?P<name>[a-z0-9][\w .-]{0,59}?)(?:\s+(?:project|repo|repository))?)?"


# Words after "test" or "build" that are not a project ("test my patience", "build muscle").
_NOT_PROJECTS = {'my', 'your', 'our', 'me', 'it', 'this', 'that', 'them', 'him', 'her', 'patience', 'out', 'drive', 'yourself', 'muscle', 'muscles', 'trust',
                 'confidence', 'strength', 'stamina', 'habits', 'wealth', 'up', 'bridges', 'everything', 'something', 'anything', 'positive', 'negative', 'results', 'run'}


def _match(pattern, text):
    return re.fullmatch(_LEAD + '(?:' + pattern + ')' + _TAIL, text, re.I)


def command_request(text, saved=()):
    """(intent, input) for a spoken project command, else None. `saved` lists the person's saved commands."""
    if not isinstance(text, str) or len(text) > 300 or nonliteral_request(text) or re.search(r"\b(?:do not|don['’]?t|never)\b", text, re.I):
        return None
    name = lambda match: (match['name'] or '').strip().lower()
    found = _match(r"(?:run|start)\s+(?:the\s+|my\s+|all\s+(?:the\s+)?)?tests?(?:\s+suite)?" + _PROJECT, text)
    if found:
        return ('project-recipe', {'name': name(found), 'recipe': 'test'})
    found = _match(r"test\s+(?P<direct>[a-z0-9][\w.-]{1,59})(?:\s+(?:project|repo|repository))?", text)  # "test June"
    if found and found['direct'].lower() not in _NOT_PROJECTS:
        return ('project-recipe', {'name': found['direct'].lower(), 'recipe': 'test'})
    found = _match(r"(?:run|start|make|do)\s+(?:the\s+|a\s+)?build" + _PROJECT + r"|build\s+(?:the\s+|my\s+)?(?P<direct>[a-z0-9][\w.-]{0,59})(?:\s+(?:project|repo|repository))?", text)
    if found:
        direct = (found.groupdict().get('direct') or '').strip().lower()
        if direct in ('a', 'an', 'me', 'us', 'it', 'something') or direct in _NOT_PROJECTS:
            return None
        if direct in ('project', 'app', 'code', 'repo', 'repository'):
            direct = ''
        return ('project-recipe', {'name': direct or name(found), 'recipe': 'build'})
    found = _match(r"(?:git\s+pull|pull\s+(?:the\s+)?(?:latest|newest|new)(?:\s+(?:changes|code|commits))?|pull\s+(?:the\s+)?(?:changes|code)|update\s+(?:the\s+|my\s+)?(?:repo|repository|code)(?:\s+from\s+github)?)" + _PROJECT, text)
    if found:
        return ('project-pull', {'name': name(found)})
    found = re.fullmatch(_LEAD + r"(?:(?:commit\s+and\s+push|push|upload|publish)\s+(?:(?:my|the|this|these|all(?:\s+my)?)\s+)?(?:new\s+|latest\s+)?(?:changes|patch|work|code|commit|commits|update|updates)?"
                         r"|commit\s+and\s+push)(?:\s+(?:to|on|in|for)\s+(?:my\s+|the\s+)?(?:github(?:\s+(?:repo|repository))?|(?P<name>[a-z0-9][\w .-]{0,59}?)(?:\s+(?:project|repo|repository))?))?"
                         r"(?:\s+(?P<bare>[a-z0-9][\w.-]{0,59}))??(?:\s+(?:with|using)\s+(?:the\s+)?(?:commit\s+)?message\s+(?P<message>.+?))?[\s.!?]*", text, re.I)
    if found and re.search(r"\b(?:changes|patch|work|code|commits?|updates?|github|commit\s+and\s+push)\b", text, re.I):
        message = (found['message'] or '').strip(" \t.\"“”'‘’")
        if not message:
            now = datetime.now()
            message = f'Update {now.day} {now.strftime("%b %Y %H:%M")}'
        return ('project-push', {'name': (found['name'] or found['bare'] or '').strip().lower(), 'message': message[0].upper() + message[1:]})
    for verb, intent in (('stop', 'project-stop'), ('run|start|launch', 'project-command')):
        found = _match(r"(?:" + verb + r")\s+(?:the\s+|my\s+)?(?P<command>[\w][\w .-]{0,59}?)(?:\s+command)?", text)
        if found:
            wanted = found['command'].strip().casefold()
            chosen = [c for c in saved if c['name'].casefold() == wanted and (intent != 'project-stop' or c.get('kind') == 'server')]
            if len(chosen) == 1:
                return (intent, {'id': chosen[0]['id']})
    return None


class Commands:
    """The person's saved commands and the one GitHub consent. Text is stored exactly as typed."""
    def __init__(self, directory, hands):
        self.directory = Path(directory) / 'tools'
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'commands.sqlite3'
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600); os.close(fd)
        self.hands = hands
        self.running = {}
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY,project TEXT NOT NULL,name TEXT NOT NULL COLLATE NOCASE,command TEXT NOT NULL,safe INTEGER NOT NULL,kind TEXT NOT NULL,UNIQUE(project,name))')
            db.execute('CREATE TABLE IF NOT EXISTS settings(id TEXT PRIMARY KEY,value TEXT NOT NULL)')

    def db(self):
        db = sqlite3.connect(self.path, timeout=3); db.row_factory = sqlite3.Row; return db

    def projects(self):
        return self.hands.project_list() if self.hands else []

    def github(self):
        with self.db() as db:
            row = db.execute("SELECT value FROM settings WHERE id='github'").fetchone()
        return bool(row and row[0] == '1')

    def set_github(self, allowed):
        if type(allowed) is not bool:
            raise JuneError('invalid-command', 'Send allowed as true or false.', 400)
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES('github',?)", ('1' if allowed else '0',))
        return self.state()

    def is_running(self, cid):
        process = self.running.get(cid)
        if process is not None and process.poll() is not None:
            self.running.pop(cid, None); process = None
        return process is not None

    def rows(self):
        names = {p['id']: p['name'] for p in self.projects()}
        with self.db() as db:
            return [dict(id=r['id'], projectId=r['project'], project=names.get(r['project'], ''), name=r['name'], command=r['command'], safe=bool(r['safe']), kind=r['kind'],
                         running=self.is_running(r['id'])) for r in db.execute('SELECT * FROM commands ORDER BY name')]

    def state(self):
        return dict(version=1, serverNow=round(time.time() * 1000), githubAllowed=self.github(), projects=[dict(id=p['id'], name=p['name']) for p in self.projects()],
                    commands=[c for c in self.rows() if c['project']])

    def get(self, cid):
        chosen = [c for c in self.rows() if c['id'] == cid and c['project']] if isinstance(cid, str) else []
        if not chosen:
            raise JuneError('command-missing', 'That saved command no longer exists. Check Systems → Integrations → Project commands.', 404)
        return chosen[0]

    def add(self, value):
        if not isinstance(value, dict) or set(value) != {'projectId', 'name', 'command', 'safe', 'kind'}:
            raise JuneError('invalid-command', 'Send a project, a name, the command, whether it is safe, and its kind.', 400)
        name, text = value['name'], value['command']
        if value['projectId'] not in {p['id'] for p in self.projects()}:
            raise JuneError('project-missing', 'Choose a project saved in Hands.', 404)
        if not isinstance(name, str) or not re.fullmatch(r"[\w][\w .-]{0,39}", name.strip()):
            raise JuneError('invalid-command', 'Give the command a short name using letters, numbers, spaces, dots or hyphens.', 400)
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 500 or re.search(r'[\x00-\x1f\x7f]', text):
            raise JuneError('invalid-command', 'Type one command on a single line, up to 500 characters.', 400)
        if type(value['safe']) is not bool or value['kind'] not in ('run', 'server'):
            raise JuneError('invalid-command', 'Choose whether it is safe to run without asking, and whether it keeps running.', 400)
        if re.match(r'\s*sudo\b', text):
            raise JuneError('invalid-command', 'June does not run commands with administrator rights.', 400)
        try:
            with self.db() as db:
                if db.execute('SELECT COUNT(*) FROM commands').fetchone()[0] >= 30:
                    raise JuneError('command-limit', 'Keep up to 30 saved commands. Remove one first.', 409)
                db.execute('INSERT INTO commands VALUES(?,?,?,?,?,?)', (uuid.uuid4().hex, value['projectId'], name.strip(), text.strip(), int(value['safe']), value['kind']))
        except sqlite3.IntegrityError:
            raise JuneError('command-duplicate', 'That project already has a command with this name.', 409) from None
        return self.state()

    def remove(self, cid):
        self.get(cid)
        with self.db() as db:
            db.execute('DELETE FROM commands WHERE id=?', (cid,))
        return self.state()


def register(plans, directory, *, hands=None, runner=run, spawn=start_server, stop=stop_server, npm=None, pause=1.5):
    commands = Commands(directory, hands)
    invalid = lambda message: JuneError('invalid-plan', message, 400)
    logs = commands.directory / 'command-logs'

    def only(value, keys):
        if not isinstance(value, dict) or set(value) != set(keys):
            raise invalid('June cannot plan that request.')

    def project(name):
        if not isinstance(name, str) or len(name) > 60:
            raise invalid('Name a project saved in Hands.')
        saved = commands.projects()
        wanted = name.strip().casefold()
        chosen = [p for p in saved if p['name'].casefold() == wanted] if wanted else saved if len(saved) == 1 else []
        if not chosen:
            raise JuneError('project-missing', ('That project is not saved in Hands. ' if wanted else 'Say which project. ' if saved else 'No project is saved yet. ') + 'Add its folder in Systems → Hands.', 404)
        folder = Path(chosen[0]['folderPath'])
        if not folder.is_dir():
            raise JuneError('project-changed', 'That project folder is unavailable. Check it in Hands.', 409)
        return chosen[0]['id'], chosen[0]['name'], str(folder)

    def git(folder, *arguments, timeout=10):
        return runner([GIT, '-C', folder, *arguments], timeout)

    def repository(folder, name):
        """(branch, GitHub page, changed lines) read now; refuses anything June will not push."""
        if not commands.github():
            raise JuneError('github-consent', ALLOW, 403)
        code, branch = git(folder, 'rev-parse', '--abbrev-ref', 'HEAD')
        branch = branch.strip()
        if code != 0:
            raise JuneError('not-a-repo', f'{name} is not a git repository.', 409)
        if branch in ('', 'HEAD') or not re.fullmatch(r'[\w./-]{1,120}', branch):
            raise JuneError('detached-head', f'{name} is on a detached HEAD, not a branch. Check out a branch first.', 409)
        code, remote = git(folder, 'remote', 'get-url', 'origin')
        page = github_url(remote.strip()) if code == 0 else None
        if not page:
            raise JuneError('no-github', f'{name} has no GitHub remote named origin. June only pushes to and pulls from GitHub.', 409)
        code, changes = git(folder, 'status', '--porcelain')
        if code != 0:
            raise JuneError('not-a-repo', f'git could not read {name}.', 409)
        return branch, page, [line for line in changes.splitlines() if line.strip()]

    # --- Pull ------------------------------------------------------------------------------------
    async def pull(payload):
        if not commands.github():
            return dict(verified=False, failed=True, message=ALLOW + ' Nothing was pulled.')
        code, output = await asyncio.to_thread(runner, [GIT, '-C', payload['path'], 'pull', '--ff-only', 'origin', payload['branch']], 100)
        if code != 0 and re.search(r"couldn['’]?t find remote ref", output):
            return dict(verified=True, message=f'Branch {payload["branch"]} of {payload["name"]} is not on GitHub yet, so there was nothing to pull. Nothing was changed.')
        return dict(verified=code == 0, failed=code > 0, message=(f'{payload["name"]} is up to date with GitHub. ' if code == 0 else f'The pull did not finish cleanly, so {payload["name"]} was left as it was. ') + tail(output))

    def pull_steps(value):
        only(value, ['name'])
        pid, name, folder = project(value['name'])
        branch, page, _ = repository(folder, name)
        return [('project.pull', dict(project=pid, name=name, path=folder, branch=branch, remote=page),
                 f'Download new commits for {name} from {page} into branch {branch} (git pull, fast-forward only). If your branch and GitHub have diverged, nothing is changed. Contacts github.com.',
                 f'Pull {name} from GitHub')]
    pull_steps.accepts_input = True
    plans.capabilities['project.pull'] = Capability('project.pull', 'Pull a saved project from GitHub', 'github', 'local', True, pull, timeout=110)
    plans.intents['project-pull'] = pull_steps

    # --- Commit and push: reviewed every time -----------------------------------------------------
    async def push(payload):
        def work():
            if not commands.github():
                return dict(verified=False, failed=True, message=ALLOW + ' Nothing was committed or pushed.')
            folder = payload['path']
            try:
                branch, page, changes = repository(folder, payload['name'])
            except JuneError as failure:
                return dict(verified=False, failed=True, message=failure.message + ' Nothing was committed or pushed.')
            if branch != payload['branch'] or page != payload['remote'] or digest(changes) != payload['files']:
                return dict(verified=False, failed=True, message='The branch or the changed files changed since you reviewed the card, so nothing was committed or pushed. Ask again to review them.')
            if changes:
                code, output = git(folder, 'add', '-A', timeout=30)
                if code != 0:
                    return dict(verified=False, failed=True, message='git could not stage the files. Nothing was committed or pushed. ' + tail(output))
                code, output = git(folder, 'commit', '-m', payload['message'], timeout=120)
                if code != 0:
                    return dict(verified=False, failed=True, message='The commit did not succeed, so nothing was pushed. ' + tail(output))
            code, output = git(folder, 'push', '-u', 'origin', branch, timeout=150)
            if code != 0:
                return dict(verified=False, failed=code > 0, message='Your changes are committed on this Mac but not pushed to GitHub. ' + tail(output))
            _, commit = git(folder, 'log', '-1', '--format=%h')
            count = len(changes)
            return dict(verified=True, message=f'Pushed {payload["name"]} to {page} on branch {branch}' + (f': {count} file{"" if count == 1 else "s"} in commit {commit.strip()[:12]}.' if count else '.'))
        return await asyncio.to_thread(work)

    def push_steps(value):
        only(value, ['name', 'message'])
        message = value['message']
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 200 or re.search(r'[\x00-\x1f\x7f]', message):
            raise invalid('Give a one-line commit message, up to 200 characters.')
        pid, name, folder = project(value['name'])
        branch, page, changes = repository(folder, name)
        ahead = 0
        if not changes:
            code, count = git(folder, 'rev-list', '--count', '@{upstream}..HEAD')
            ahead = int(count.strip()) if code == 0 and count.strip().isdigit() else 0
            if not ahead:
                raise JuneError('nothing-to-push', f'{name} has no changed files and no unpushed commits, so there is nothing to push.', 409)
        shown = ', '.join(line[3:].strip()[:80] for line in changes[:25]) + (f' and {len(changes) - 25} more' if len(changes) > 25 else '')
        what = (f'Commit all {len(changes)} changed file{"" if len(changes) == 1 else "s"} ({shown}) with the message “{message.strip()}”, then push' if changes
                else f'Push {ahead} commit{"" if ahead == 1 else "s"} already made')
        warning = f' This pushes directly to {branch}.' if branch in ('main', 'master') else ''
        return [('project.push', dict(project=pid, name=name, path=folder, branch=branch, remote=page, message=message.strip(), files=digest(changes)),
                 f'{what} to {page}, branch {branch}.{warning} June never force-pushes and never rewrites history. Contacts github.com. Check the file list for anything private before approving.',
                 f'Commit and push {name}')]
    push_steps.accepts_input = True
    # Outward: never remembered.
    plans.capabilities['project.push'] = Capability('project.push', 'Commit and push a saved project to GitHub', 'github', 'outward', False, push, timeout=320)
    plans.intents['project-push'] = push_steps

    # --- Tests and build: the project's own package scripts ----------------------------------------
    def npm_path():
        return npm or shutil.which('npm', path=PATH)

    async def recipe(payload):
        program = npm_path()
        if not program:
            return dict(verified=False, failed=True, message='npm was not found on this Mac, so nothing was run.')
        argv = [program, 'test'] if payload['recipe'] == 'test' else [program, 'run', 'build']
        code, output = await asyncio.to_thread(runner, argv, 840, payload['path'])
        word = 'Tests' if payload['recipe'] == 'test' else 'The build'
        return dict(verified=code == 0, failed=code != 0, message=(f'{word} passed for {payload["name"]}. ' if code == 0 else f'{word} failed for {payload["name"]}. ') + tail(output))

    def recipe_steps(value):
        only(value, ['name', 'recipe'])
        if value['recipe'] not in ('test', 'build'):
            raise invalid('Choose test or build.')
        pid, name, folder = project(value['name'])
        try:
            scripts = json.loads((Path(folder) / 'package.json').read_text()[:1000000]).get('scripts', {})
        except (OSError, ValueError, AttributeError):
            scripts = {}
        script = scripts.get(value['recipe']) if isinstance(scripts, dict) else None
        if not isinstance(script, str) or not script.strip():
            raise JuneError('no-script', f'{name} has no {value["recipe"]} script in package.json. Save your own command in Systems → Integrations → Project commands instead.', 409)
        shown = 'npm test' if value['recipe'] == 'test' else 'npm run build'
        return [('project.run', dict(project=pid, name=name, path=folder, recipe=value['recipe'], script=script.strip()[:300]),
                 f'Run {shown} in {name} ({folder}), which runs this project’s own script: {script.strip()[:300]}. It may take several minutes; the result appears on this card.',
                 ('Run tests in ' if value['recipe'] == 'test' else 'Build ') + name)]
    recipe_steps.accepts_input = True
    plans.capabilities['project.run'] = Capability('project.run', 'Run a saved project’s tests or build', 'local', 'local', True, recipe, timeout=860)
    plans.intents['project-recipe'] = recipe_steps

    # --- Saved commands -----------------------------------------------------------------------------
    def folder_of(command):
        chosen = [p for p in commands.projects() if p['id'] == command['projectId']]
        if not chosen or not Path(chosen[0]['folderPath']).is_dir():
            raise JuneError('project-changed', 'That command’s project folder is unavailable. Check it in Hands.', 409)
        return str(Path(chosen[0]['folderPath']))

    async def saved(payload):
        try:
            current = commands.get(payload['id'])
        except JuneError as failure:
            return dict(verified=False, failed=True, message=failure.message + ' Nothing was run.')
        if current['command'] != payload['command'] or current['kind'] != payload['kind']:
            return dict(verified=False, failed=True, message='That saved command was edited since you reviewed it, so nothing was run. Ask again to review it.')
        if payload['kind'] == 'server':
            if commands.is_running(payload['id']):
                return dict(verified=True, message=f'{current["name"]} is already running.')
            logs.mkdir(exist_ok=True, mode=0o700)
            process = spawn(payload['command'], payload['path'], str(logs / (payload['id'] + '.log')))
            commands.running[payload['id']] = process
            await asyncio.sleep(pause)
            alive = commands.is_running(payload['id'])
            return dict(verified=alive, failed=not alive, message=f'{current["name"]} is running in {current["project"]}. Say “stop the {current["name"]}” to end it.' if alive
                        else f'{current["name"]} stopped straight away. Check the command.')
        code, output = await asyncio.to_thread(runner, ['/bin/zsh', '-c', payload['command']], 840, payload['path'])
        return dict(verified=code == 0, failed=code != 0, message=(f'{current["name"]} finished. ' if code == 0 else f'{current["name"]} failed (exit code {code}). ') + tail(output))

    def saved_steps(value):
        only(value, ['id'])
        command = commands.get(value['id'])
        folder = folder_of(command)
        payload = dict(id=command['id'], name=command['name'], command=command['command'], kind=command['kind'], path=folder)
        extra = ' It keeps running in the background until you stop it.' if command['kind'] == 'server' else ' Its output appears on this card when it finishes.'
        return [('project.safe-command' if command['safe'] else 'project.command', payload,
                 f'Run your saved command “{command["name"]}” in {command["project"]} ({folder}), exactly as you typed it: {command["command"]}{extra}', 'Run ' + command['name'])]
    saved_steps.accepts_input = True
    plans.capabilities['project.command'] = Capability('project.command', 'Run one of your saved commands', 'local', 'local', False, saved, timeout=860)
    # Only a command the person marked safe can be remembered; the approval is tied to its exact text.
    plans.capabilities['project.safe-command'] = Capability('project.safe-command', 'Run a saved command you marked safe', 'local', 'local', True, saved, timeout=860)
    plans.intents['project-command'] = saved_steps

    async def halt(payload):
        process = commands.running.pop(payload['id'], None)
        if process is None or process.poll() is not None:
            return dict(verified=True, message=f'{payload["name"]} is not running, so nothing was stopped.')
        stop(process)
        for _ in range(20):
            if process.poll() is not None: break
            await asyncio.sleep(0.2 if pause else 0)
        return dict(verified=process.poll() is not None, message=f'{payload["name"]} was stopped.' if process.poll() is not None else f'{payload["name"]} was asked to stop but is still running.')

    def halt_steps(value):
        only(value, ['id'])
        command = commands.get(value['id'])
        if command['kind'] != 'server':
            raise invalid('Only a command that keeps running can be stopped.')
        return [('project.stop', dict(id=command['id'], name=command['name']), f'Stop your saved command “{command["name"]}” that June started. Nothing else is stopped.', 'Stop ' + command['name'])]
    halt_steps.accepts_input = True
    plans.capabilities['project.stop'] = Capability('project.stop', 'Stop a command June started', 'local', 'local', True, halt)
    plans.intents['project-stop'] = halt_steps
    plans.commands = commands
    return commands


async def command_chat(question, request_key, plans):
    """App-owned reply to a project command: a card to review, or the checked result when remembered."""
    commands = getattr(plans, 'commands', None) if plans is not None else None
    if commands is None:
        return None
    request = command_request(question, commands.state()['commands'])
    if request is None:
        return None
    intent, value = request
    try:
        reply = await plans.propose({'requestId': request_key, 'intent': intent, 'input': value})
    except JuneError as failure:
        return dict(reply=failure.message + ' Nothing was run.')
    plan = reply['plan']
    if plan['status'] == 'proposed':
        remember = ' Tick “Don’t ask again” to skip the card next time.' if plan.get('rememberable') else ''
        return dict(plan=plan, serverNow=reply['serverNow'], reply=f'I’ve prepared “{plan["steps"][0]["label"]}”. Check the card below and approve it.' + remember)
    reply = await settled(plans, reply)
    plan = reply['plan']
    results = [s.get('result') for s in plan['steps'] if s.get('result')]
    text = ' '.join(r['message'] for r in results) if results else f'“{plan["steps"][0]["label"]}” is still running. Its result will appear on the card.'
    return dict(plan=plan, serverNow=reply['serverNow'], reply=text)
