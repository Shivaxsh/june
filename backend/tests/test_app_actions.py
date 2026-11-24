"""8.2a: June opens only the apps the user listed, through reviewed plans."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from june.errors import JuneError


class Registry(unittest.TestCase):
    def test_the_users_fifteen_apps_two_system_tools_and_no_others(self):
        from june.app_actions import APPS
        self.assertEqual(set(APPS), {'vscode', 'claude', 'chatgpt', 'powerpoint', 'excel', 'word', 'notes', 'chrome',
                                     'calendar', 'music', 'figma', 'mail', 'affinity', 'app-store', 'terminal', 'screenshot', 'color-meter'})
        self.assertEqual(APPS['chrome'].bundle, 'com.google.Chrome')

    def test_spoken_requests_resolve_to_registry_keys(self):
        from june.app_actions import app_request
        for text, keys in (('open Chrome', ['chrome']), ('Hey June, open Figma and Notes', ['figma', 'notes']),
                           ('can you launch the terminal please?', ['terminal']), ('Open chrome, figma and notes.', ['chrome', 'figma', 'notes']),
                           ('open google chrome', ['chrome']), ('open the app store', ['app-store']), ('Open Microsoft Word', ['word']),
                           ('open power point', ['powerpoint']), ('switch to Mail', ['mail']), ('open chat gpt', ['chatgpt']),
                           ('open my calendar', ['calendar']), ('Open VS Code and Terminal', ['vscode', 'terminal'])):
            self.assertEqual(app_request(text), (keys, []), text)
        self.assertEqual(app_request('open Chrome and Safari'), (['chrome'], ['safari']))
        for text in ('open the pod bay doors', 'How do I open Chrome?', 'open Build.pdf', 'open a new file', 'Do not open Chrome',
                     'open Safari', 'what is Chrome', 'open', 'open my notes about Friday', 'Open VS Code'):
            self.assertIsNone(app_request(text), text)

    def test_everyday_phrasings_reach_the_app_tool_not_the_model(self):
        from june.app_actions import app_request
        for text, keys in (('open up the figma app', ['figma']), ('I want to open figma', ['figma']), ('fire up word', ['word']),
                           ('pull up figma', ['figma']), ('open powerpoint presentation app', ['powerpoint']), ('open excel sheet', ['excel']),
                           ('hey june open ms word and figma', ['word', 'figma']), ('open the chrome browser', ['chrome']),
                           ('I’d like you to open Notes', ['notes']), ('go ahead and launch terminal', ['terminal']),
                           ('let’s open figma', ['figma']), ('I think you should open figma now', ['figma']), ('open calender', ['calendar']),
                           ('open my email', ['mail']), ('start up affinity designer', ['affinity']), ('please open up claude for me', ['claude']),
                           ('open the browser', ['chrome']), ('Oh, um, open Figma right now', ['figma']), ('June can you open the Notes application', ['notes'])):
            self.assertEqual(app_request(text), (keys, []), text)
        for text in ('don’t open figma', "I can't open figma", 'did you open figma?', 'why does figma open slowly', 'should I open figma or sketch',
                     'how to open excel sheet', 'never open chrome', 'when I open figma it crashes', 'open word document report.docx',
                     'I opened figma', 'what happens if you open chrome', 'is it safe to open mail?'):
            self.assertIsNone(app_request(text), text)

    def test_swift_allowlist_matches_the_registry_exactly(self):
        import re
        from june.app_actions import APPS
        source = (Path(__file__).resolve().parents[2] / 'native/JuneApps.swift').read_text()
        allowed = set(re.findall(r'"((?:com|org)\.[\w.-]+)"', source[source.index('let allowed'):source.index(']', source.index('let allowed'))]))
        self.assertEqual(allowed, {app.bundle for app in APPS.values()})
        self.assertNotIn('Process(', source); self.assertNotIn('NSAppleScript', source)
        self.assertIn('com.apple.screencaptureui', source, 'the Screenshot launcher exits at once; its toolbar shows that it opened')


class Plans(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from june.integrations import create_tools
        self.tmp = tempfile.TemporaryDirectory()
        self.opened = []
        test = self
        class Native:
            state = 'active'
            def ready(self): return True
            async def open(self, bundle):
                test.opened.append(bundle); return self.state
        self.native = Native()
        self.plans = create_tools(Path(self.tmp.name), None, None, apps=self.native)
        await self.plans.readiness()

    async def asyncTearDown(self):
        await self.plans.close(); self.tmp.cleanup()

    async def propose(self, rid, apps):
        return (await self.plans.propose({'requestId': rid, 'intent': 'open-app', 'input': {'apps': apps}}))['plan']

    async def settle(self, pid):
        for _ in range(40):
            plan = (await self.plans.get(pid))['plan']
            if plan['status'] not in ('approved', 'running'): return plan
            await asyncio.sleep(0.02)
        return plan

    async def test_input_is_validated_against_the_registry(self):
        plan = await self.propose('req-apps-0001', ['chrome', 'figma'])
        self.assertEqual([s['label'] for s in plan['steps']], ['Open Google Chrome', 'Open Figma'])
        self.assertIn('com.google.Chrome', plan['steps'][0]['preview'])
        self.assertEqual(plan['status'], 'proposed')
        for bad in ({'apps': ['com.apple.Safari']}, {'apps': ['safari']}, {'apps': []}, {'apps': ['chrome', 'chrome']}, {'apps': ['chrome', 'figma', 'notes', 'mail']},
                    {'apps': 'chrome'}, {'apps': ['chrome'], 'path': '/x'}, {'bundle': 'com.google.Chrome'}, {}):
            with self.assertRaises(JuneError, msg=str(bad)):
                await self.plans.propose({'requestId': 'req-bad-' + str(abs(hash(str(bad))))[:8], 'intent': 'open-app', 'input': bad})
        with self.assertRaises(JuneError):
            await self.plans.propose({'requestId': 'req-apps-0002', 'intent': 'open-app'})
        self.assertEqual(self.opened, [], 'nothing opens before approval')

    async def test_approval_opens_exactly_the_reviewed_apps_and_reports_the_checked_state(self):
        plan = await self.propose('req-apps-0003', ['chrome', 'notes'])
        await self.plans.approve(plan['id'], {'requestId': 'req-apps-0004', 'revision': 1, 'fingerprint': plan['fingerprint']})
        done = await self.settle(plan['id'])
        self.assertEqual(self.opened, ['com.google.Chrome', 'com.apple.Notes'])
        self.assertEqual(done['status'], 'completed')
        self.assertEqual(done['steps'][0]['result']['message'], 'Google Chrome is open and in front.')

    async def test_unverified_or_failed_opens_are_never_reported_as_done(self):
        for state, status in (('unverified', 'unknown'), ('failed', 'failed'), ('not-running', 'unknown')):
            self.native.state = state
            plan = await self.propose('req-state-' + state.ljust(8, '0'), ['figma'])
            await self.plans.approve(plan['id'], {'requestId': 'req-st-ap-' + state.ljust(8, '0'), 'revision': 1, 'fingerprint': plan['fingerprint']})
            self.assertEqual((await self.settle(plan['id']))['status'], status, state)

    async def test_remembering_is_per_exact_app(self):
        plan = await self.propose('req-apps-0005', ['chrome'])
        await self.plans.approve(plan['id'], {'requestId': 'req-apps-0006', 'revision': 1, 'fingerprint': plan['fingerprint'], 'remember': True})
        await self.settle(plan['id'])
        again = await self.propose('req-apps-0007', ['chrome'])
        self.assertIn((await self.settle(again['id']))['status'], ('completed',), 'the same app runs without a new card')
        self.assertEqual((await self.propose('req-apps-0008', ['figma']))['status'], 'proposed', 'another app still needs review')
        self.assertEqual((await self.propose('req-apps-0009', ['chrome', 'figma']))['status'], 'proposed')

    async def test_existing_intents_still_refuse_arguments(self):
        with self.assertRaises(JuneError):
            await self.plans.propose({'requestId': 'req-apps-0010', 'intent': 'open-vscode', 'input': {'apps': ['chrome']}})

    async def test_chat_proposes_reports_and_refuses_honestly(self):
        from june.app_actions import app_chat
        reply = await app_chat('open Chrome and Figma', 'chat-apps-0001', self.plans)
        self.assertEqual(reply['plan']['status'], 'proposed'); self.assertIn('Approve', reply['reply'])
        mixed = await app_chat('open Chrome and Safari', 'chat-apps-0002', self.plans)
        self.assertNotIn('plan', mixed); self.assertIn('Safari', mixed['reply']); self.assertIn('Nothing was opened', mixed['reply'])
        unlisted = await app_chat('open Safari', 'chat-apps-0003', self.plans)
        self.assertNotIn('plan', unlisted); self.assertTrue(unlisted['reply'].startswith('Safari isn’t on the list')); self.assertIn('Nothing was opened', unlisted['reply'])
        for text in ('close Figma', 'quit chrome please', 'can you close the notes app'):
            closing = await app_chat(text, 'chat-apps-close', self.plans)
            self.assertNotIn('plan', closing); self.assertIn('can’t close or quit', closing['reply'])
        for text in ('open a new chat', 'start a new conversation', 'Hey June, open another chat please'):
            self.assertIn('New chat', (await app_chat(text, 'chat-apps-new', self.plans))['reply'], text)
        for text in ('open the pod bay doors', 'open my notes about Friday', 'open Build.pdf', 'close the door behind you and tell me a story'):
            self.assertIsNone(await app_chat(text, 'chat-apps-none', self.plans), text)
        self.assertIsNone(await app_chat('What is Chrome?', 'chat-apps-0004', self.plans))
        self.assertEqual(self.opened, [])
        plan = await self.propose('req-apps-0011', ['notes'])
        await self.plans.approve(plan['id'], {'requestId': 'req-apps-0012', 'revision': 1, 'fingerprint': plan['fingerprint'], 'remember': True})
        await self.settle(plan['id'])
        spoken = await app_chat('Hey June, open Notes', 'chat-apps-0005', self.plans)
        self.assertEqual(spoken['reply'], 'Notes is open and in front.')

    async def test_app_list_reports_install_and_remembered_state(self):
        apps = self.plans.app_list()['apps']
        self.assertEqual(len(apps), 17)
        self.assertEqual({'id', 'label', 'remembered'}, set(apps[0]))
        self.assertFalse(any('bundle' in a or 'path' in a for a in apps))
