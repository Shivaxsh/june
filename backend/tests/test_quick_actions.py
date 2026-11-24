"""8.2d: Developer and Designer quick actions. Fixed commands only, each through a reviewed plan."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from june.errors import JuneError


class Grammar(unittest.TestCase):
    def test_spoken_quick_actions(self):
        from june.quick_actions import quick_request
        cases = {
            'start a coding session': ('coding-session', None), 'Hey June, start my coding session please': ('coding-session', None), 'let’s code': ('coding-session', None),
            'open my design workspace': ('design-workspace', None), 'design mode': ('design-workspace', None),
            'keep my Mac awake for 2 hours': ('keep-awake', {'minutes': 120}), 'keep the mac awake': ('keep-awake', {'minutes': 60}),
            'keep my mac awake for 45 minutes': ('keep-awake', {'minutes': 45}), 'let my mac sleep again': ('allow-sleep', None),
            'stop keeping the mac awake': ('allow-sleep', None),
            'switch to dark mode': ('appearance', {'mode': 'dark'}), 'light mode please': ('appearance', {'mode': 'light'}), 'toggle dark mode': ('appearance', {'mode': 'toggle'}),
            'turn off dark mode': ('appearance', {'mode': 'light'}), 'switch the appearance': ('appearance', {'mode': 'toggle'}),
            'take a screenshot': ('open-app', {'apps': ['screenshot']}), 'capture my screen': ('open-app', {'apps': ['screenshot']}),
            'open the colour picker': ('open-app', {'apps': ['color-meter']}), 'pick a color': ('open-app', {'apps': ['color-meter']}),
            'free port 3000': ('free-port', {'port': 3000}), 'kill whatever is on port 5173': ('free-port', {'port': 5173}), 'what’s using port 8080?': ('free-port', {'port': 8080}),
            'git status': ('git-status', {'name': ''}), 'git status of June': ('git-status', {'name': 'june'}), 'any uncommitted changes in June?': ('git-status', {'name': 'june'}),
            'open June on GitHub': ('open-github', {'name': 'june'}), 'open my github repo': ('open-github', {'name': ''}), 'open the repo on github': ('open-github', {'name': ''}),
            'convert my images to png': ('convert-images', {'format': 'png'}), 'resize my images to 1200 pixels': ('convert-images', {'format': 'png', 'width': 1200}),
            'convert the images to jpeg at 800 wide': ('convert-images', {'format': 'jpeg', 'width': 800}),
        }
        for text, expected in cases.items():
            self.assertEqual(quick_request(text), expected, text)
        for text in ('how do I check git status?', 'what is dark mode', 'don’t keep my mac awake', 'free port', 'explain coding sessions', 'take a screenshot of my feelings in a poem',
                     'convert 5 miles to km', 'keep me awake', 'git status "x"; rm -rf', 'free port 99999999', 'open github', 'I like dark mode'):
            self.assertIsNone(quick_request(text), text)


class Actions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from june.integrations import create_tools
        from june import quick_actions
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / 'home'; self.home.mkdir()
        self.repo = Path(self.tmp.name) / 'repo'; self.repo.mkdir()
        self.ran = []; self.opened = []; self.killed = []
        self.listening = {3000: (4242, 'node')}
        self.remote = 'git@github.com:shiv/june-app.git'
        test = self
        async def runner(argv, timeout=10):
            test.ran.append(argv)
            if argv[0].endswith('git') and 'status' in argv: return 0, '## main...origin/main [ahead 2]\n M a.py\n?? b.py\n'
            if argv[0].endswith('git') and 'log' in argv: return 0, 'Add quick actions\n'
            if argv[0].endswith('git') and 'get-url' in argv: return 0, test.remote + '\n'
            if argv[0].endswith('lsof'):
                port = int(argv[2].split(':')[1]); row = test.listening.get(port)
                return (0, f'p{row[0]}\nc{row[1]}\nu{quick_actions.os.getuid()}\n') if row else (1, '')
            if argv[0].endswith('open'): test.opened.append(argv[-1]); return 0, ''
            if argv[0].endswith('sips'): Path(argv[argv.index('--out') + 1]).write_bytes(b'img'); return 0, ''
            return 0, ''
        class Apps:
            def ready(self): return True
            async def open(self, bundle): test.opened.append(bundle); return 'active'
        class Quick:
            dark = False
            def ready(self): return True
            async def appearance(self, mode):
                self.dark = {'dark': True, 'light': False, 'toggle': not self.dark}[mode]; return self.dark
        class Hands:
            def project_list(self): return [dict(id='p1', name='June', folderPath=str(test.repo), remembered=False)]
        self.native = Quick()
        self.plans = create_tools(Path(self.tmp.name), None, None, apps=Apps())
        self.awake = []
        def spawn(seconds): self.awake.append(seconds); return SimpleProcess()
        class SimpleProcess:
            stopped = False
            def poll(self): return 0 if self.stopped else None
            def terminate(self): self.stopped = True
        def kill(pid): self.killed.append(pid); self.listening.pop(3000, None)
        quick_actions.register(self.plans, hands=Hands(), native=self.native, runner=runner, home=self.home, spawn=spawn, kill=kill)
        await self.plans.readiness()

    async def asyncTearDown(self):
        await self.plans.close(); self.tmp.cleanup()

    async def run_intent(self, intent, value=None, approve=True):
        self.count = getattr(self, 'count', 0) + 1
        rid = 'req-q-' + intent[:6] + '-' + str(self.count).zfill(4)
        request = {'requestId': rid, 'intent': intent}
        if value is not None: request['input'] = value
        plan = (await self.plans.propose(request))['plan']
        if not approve: return plan
        await self.plans.approve(plan['id'], {'requestId': rid + '-ok', 'revision': 1, 'fingerprint': plan['fingerprint']})
        for _ in range(80):
            plan = (await self.plans.get(plan['id']))['plan']
            if plan['status'] not in ('approved', 'running'): break
            await asyncio.sleep(0.02)
        return plan

    async def test_sessions_open_exactly_the_reviewed_apps(self):
        plan = await self.run_intent('coding-session')
        self.assertEqual(plan['status'], 'completed'); self.assertEqual(self.opened, ['com.microsoft.VSCode', 'com.apple.Terminal'])
        self.opened.clear()
        self.assertEqual((await self.run_intent('design-workspace'))['status'], 'completed')
        self.assertEqual(self.opened, ['com.figma.Desktop', 'com.canva.affinity', 'com.google.Chrome'])

    async def test_keep_awake_and_allow_sleep(self):
        plan = await self.run_intent('keep-awake', {'minutes': 90})
        self.assertEqual(self.awake, [5400]); self.assertIn('awake for 1 hour and 30 minutes', plan['steps'][0]['result']['message'])
        self.assertIn('awake again', (await self.run_intent('allow-sleep'))['steps'][0]['result']['message'].replace('sleep again', 'awake again'))
        self.assertIn('not keeping', (await self.run_intent('allow-sleep'))['steps'][0]['result']['message'])
        for bad in ({'minutes': 0}, {'minutes': 100000}, {'minutes': '60'}, {'seconds': 60}, {}):
            with self.assertRaises(JuneError): await self.run_intent('keep-awake', bad, approve=False)

    async def test_appearance_reports_the_checked_state(self):
        self.assertEqual((await self.run_intent('appearance', {'mode': 'dark'}))['steps'][0]['result']['message'], 'Your Mac is now in dark mode.')
        self.assertEqual((await self.run_intent('appearance', {'mode': 'toggle'}))['steps'][0]['result']['message'], 'Your Mac is now in light mode.')
        with self.assertRaises(JuneError): await self.run_intent('appearance', {'mode': 'sepia'}, approve=False)

    async def test_free_port_names_the_process_is_never_remembered_and_protects_june(self):
        plan = await self.run_intent('free-port', {'port': 3000}, approve=False)
        self.assertIn('node', plan['steps'][0]['preview']); self.assertIn('4242', plan['steps'][0]['preview']); self.assertIn('3000', plan['steps'][0]['preview'])
        self.assertFalse(self.plans.capabilities['quick.free-port'].public()['rememberable']); self.assertEqual(self.killed, [])
        done = await self.run_intent('free-port', {'port': 3000})
        self.assertEqual(self.killed, [4242]); self.assertEqual(done['status'], 'completed'); self.assertIn('Port 3000 is free', done['steps'][0]['result']['message'])
        for port in (3001, 8001, 11434):
            with self.assertRaisesRegex(JuneError, 'June'): await self.run_intent('free-port', {'port': port}, approve=False)
        with self.assertRaisesRegex(JuneError, 'Nothing is listening'): await self.run_intent('free-port', {'port': 5000}, approve=False)
        for bad in ({'port': 80}, {'port': 70000}, {'port': '3000'}, {'pid': 1}):
            with self.assertRaises(JuneError): await self.run_intent('free-port', bad, approve=False)

    async def test_a_changed_listener_is_not_killed(self):
        plan = await self.run_intent('free-port', {'port': 3000}, approve=False)
        self.listening[3000] = (5555, 'postgres')
        await self.plans.approve(plan['id'], {'requestId': 'req-q-changed-ok', 'revision': 1, 'fingerprint': plan['fingerprint']})
        for _ in range(80):
            done = (await self.plans.get(plan['id']))['plan']
            if done['status'] not in ('approved', 'running'): break
            await asyncio.sleep(0.02)
        self.assertEqual(self.killed, []); self.assertEqual(done['status'], 'failed'); self.assertIn('changed', done['steps'][0]['result']['message'])

    async def test_git_status_and_github_use_the_saved_project_only(self):
        plan = await self.run_intent('git-status', {'name': 'june'})
        message = plan['steps'][0]['result']['message']
        self.assertIn('June is on branch main', message); self.assertIn('2 changed files', message); self.assertIn('2 commits ahead', message); self.assertIn('Add quick actions', message)
        git = [argv for argv in self.ran if argv[0].endswith('git')][0]
        self.assertEqual(git[1:3], ['-C', str(self.repo)]); self.assertIn('core.fsmonitor=false', git)
        self.assertEqual((await self.run_intent('git-status', {'name': ''}))['status'], 'completed', 'one saved project is the default')
        with self.assertRaisesRegex(JuneError, 'Hands'): await self.run_intent('git-status', {'name': 'other'}, approve=False)
        opened = await self.run_intent('open-github', {'name': 'june'})
        self.assertEqual(self.opened[-1], 'https://github.com/shiv/june-app'); self.assertIn('https://github.com/shiv/june-app', opened['steps'][0]['preview'])
        for remote in ('https://evil.example.com/x/y.git', 'git@github.com:a/b;rm -rf.git', 'file:///tmp/x', ''):
            self.remote = remote
            with self.assertRaisesRegex(JuneError, 'GitHub'): await self.run_intent('open-github', {'name': 'june'}, approve=False)

    async def test_images_are_converted_as_copies_from_one_fixed_folder(self):
        with self.assertRaisesRegex(JuneError, 'June Images'): await self.run_intent('convert-images', {'format': 'png'}, approve=False)
        folder = self.home / 'June Images'; folder.mkdir()
        (folder / 'a.jpg').write_bytes(b'x'); (folder / 'b.HEIC').write_bytes(b'x'); (folder / 'notes.txt').write_text('no'); (folder / '.hidden.png').write_bytes(b'x')
        plan = await self.run_intent('convert-images', {'format': 'png', 'width': 1200})
        self.assertEqual(plan['status'], 'completed'); self.assertIn('2 images', plan['steps'][0]['result']['message'])
        self.assertEqual(sorted(p.name for p in (folder / 'converted').iterdir()), ['a.png', 'b.png'])
        self.assertTrue((folder / 'a.jpg').exists(), 'originals are never changed')
        sips = [argv for argv in self.ran if argv[0].endswith('sips')][0]
        self.assertIn('--resampleWidth', sips); self.assertIn('1200', sips)
        for bad in ({'format': 'exe'}, {'format': 'png', 'width': 5}, {'format': 'png', 'path': '/etc'}, {}):
            with self.assertRaises(JuneError): await self.run_intent('convert-images', bad, approve=False)

    async def test_chat_proposes_a_card_and_explains_missing_setup(self):
        from june.quick_actions import quick_chat
        self.assertIsNone(await quick_chat('tell me a joke', 'chat-q-0001', self.plans))
        card = await quick_chat('keep my mac awake for 2 hours', 'chat-q-0002', self.plans)
        self.assertEqual(card['plan']['status'], 'proposed'); self.assertIn('card', card['reply'])
        nothing = await quick_chat('free port 5000', 'chat-q-0003', self.plans)
        self.assertNotIn('plan', nothing); self.assertIn('Nothing is listening on port 5000', nothing['reply'])
        self.assertEqual(self.awake, [])


class Source(unittest.TestCase):
    def test_helper_and_runner_are_fixed(self):
        root = Path(__file__).resolve().parents[2]
        swift = (root / 'native/JuneQuick.swift').read_text()
        self.assertIn('appearance preferences', swift); self.assertIn('responsibility_spawnattrs_setdisclaim', swift)
        self.assertNotIn('do shell script', swift); self.assertNotIn('Process(', swift)
        module = (root / 'backend/june/quick_actions.py').read_text()
        self.assertNotIn('shell=True', module); self.assertNotIn('create_subprocess_shell', module); self.assertNotIn('os.system', module)
        from june.app_actions import APPS
        self.assertEqual(APPS['screenshot'].bundle, 'com.apple.screenshot.launcher'); self.assertEqual(APPS['color-meter'].bundle, 'com.apple.DigitalColorMeter')
