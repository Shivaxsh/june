"""8.2e: project commands. Built-in git recipes and the person's own saved commands, each reviewed."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from june.errors import JuneError


class Fixture(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from june.integrations import create_tools
        from june import project_commands
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / 'repo'; self.repo.mkdir()
        (self.repo / 'package.json').write_text(json.dumps({'scripts': {'test': 'node --test', 'build': 'next build'}}))
        self.ran = []
        self.git = dict(branch='feature/x', remote='https://github.com/shiv/june-app.git', changes=' M a.py\n?? b.py\n', ahead=0, fail=None)
        test = self
        def runner(argv, timeout=10, cwd=None):
            test.ran.append((list(argv), cwd))
            g = test.git; a = argv[-4:]
            if test.git['fail'] and test.git['fail'] in argv: return 1, 'fatal: it failed\n'
            if 'rev-parse' in argv: return (0, g['branch'] + '\n') if g['branch'] else (0, 'HEAD\n')
            if 'get-url' in argv: return (0, g['remote'] + '\n') if g['remote'] else (2, '')
            if 'status' in argv and '--porcelain' in argv: return 0, g['changes']
            if 'commit' in argv: g['changes'] = ''; g['ahead'] = 1; return 0, '[feature/x abc1234] msg\n'
            if 'push' in argv: g['ahead'] = 0; return 0, 'To github.com:shiv/june-app.git\n'
            if 'pull' in argv: return 0, 'Already up to date.\n'
            if 'rev-list' in argv: return 0, str(g['ahead']) + '\n'
            if 'log' in argv: return 0, 'abc1234\n'
            if argv[0].endswith('npm'): return (0, 'tests 12\npass 12\nfail 0\n') if argv[1] == 'test' else (1, 'Build error: boom\n')
            if argv[0] == '/bin/zsh': return 0, 'hello from ' + argv[-1] + '\n'
            return 0, ''
        class Hands:
            def project_list(self): return [dict(id='p1', name='June', folderPath=str(test.repo), remembered=False)]
        self.started = []
        class Proc:
            def __init__(self): self.dead = False
            def poll(self): return 0 if self.dead else None
        def spawn(text, cwd, log): proc = Proc(); self.started.append((text, cwd, proc)); return proc
        def stop(proc): proc.dead = True
        self.plans = create_tools(Path(self.tmp.name), None, None)
        self.commands = project_commands.register(self.plans, Path(self.tmp.name), hands=Hands(), runner=runner, spawn=spawn, stop=stop, npm='/usr/local/bin/npm', pause=0)
        self.count = 0

    async def asyncTearDown(self):
        await self.plans.close(); self.tmp.cleanup()

    async def propose(self, intent, value):
        self.count += 1
        return (await self.plans.propose({'requestId': f'req-pc-{self.count:05}', 'intent': intent, 'input': value}))['plan']

    async def run_plan(self, intent, value, remember=False):
        plan = await self.propose(intent, value)
        if plan['status'] == 'proposed':
            await self.plans.approve(plan['id'], {'requestId': f'req-pc-{self.count:05}-ok', 'revision': 1, 'fingerprint': plan['fingerprint'], **({'remember': True} if remember else {})})
        for _ in range(100):
            plan = (await self.plans.get(plan['id']))['plan']
            if plan['status'] not in ('approved', 'running'): break
            await asyncio.sleep(0.02)
        return plan

    def argvs(self, word):
        return [argv for argv, _ in self.ran if word in argv]


class Git(Fixture):
    async def test_github_needs_one_explicit_consent(self):
        for intent, value in (('project-pull', {'name': 'june'}), ('project-push', {'name': 'june', 'message': 'Fix bug'})):
            with self.assertRaisesRegex(JuneError, 'Allow GitHub'):
                await self.propose(intent, value)
        self.assertEqual(self.argvs('push') + self.argvs('pull'), [])

    async def test_push_is_reviewed_every_time_with_the_exact_files_branch_and_remote(self):
        self.commands.set_github(True)
        plan = await self.propose('project-push', {'name': 'june', 'message': 'Fix the bug'})
        preview = plan['steps'][0]['preview']
        for words in ('feature/x', 'https://github.com/shiv/june-app', 'Fix the bug', 'a.py', 'b.py', '2 changed files', 'never force'):
            self.assertIn(words, preview, words)
        self.assertFalse(plan['rememberable']); self.assertEqual(self.argvs('commit'), [])
        with self.assertRaises(JuneError):
            await self.plans.approve(plan['id'], {'requestId': 'req-pc-rem', 'revision': 1, 'fingerprint': plan['fingerprint'], 'remember': True})
        done = await self.run_plan('project-push', {'name': 'june', 'message': 'Fix the bug'})
        self.assertEqual(done['status'], 'completed', done['steps'][0].get('result'))
        self.assertIn('Pushed', done['steps'][0]['result']['message']); self.assertIn('feature/x', done['steps'][0]['result']['message'])
        commit = self.argvs('commit')[0]
        self.assertEqual(commit[commit.index('-m') + 1], 'Fix the bug')
        push = self.argvs('push')[0]
        self.assertNotIn('--force', push); self.assertNotIn('-f', push); self.assertEqual(push[-2:], ['origin', 'feature/x'])
        self.assertTrue(all(cwd is None or cwd == str(self.repo) for _, cwd in self.ran))

    async def test_push_refuses_unsafe_states(self):
        self.commands.set_github(True)
        self.git['branch'] = ''
        with self.assertRaisesRegex(JuneError, 'detached'): await self.propose('project-push', {'name': 'june', 'message': 'x'})
        self.git['branch'] = 'feature/x'; self.git['remote'] = 'https://gitlab.com/a/b.git'
        with self.assertRaisesRegex(JuneError, 'GitHub'): await self.propose('project-push', {'name': 'june', 'message': 'x'})
        self.git['remote'] = 'https://github.com/shiv/june-app.git'; self.git['changes'] = ''
        with self.assertRaisesRegex(JuneError, 'nothing to push'): await self.propose('project-push', {'name': 'june', 'message': 'x'})
        self.git['changes'] = ' M a.py\n'
        for bad in ({'name': 'june', 'message': ''}, {'name': 'june', 'message': 'x' * 201}, {'name': 'june', 'message': 'a\nb'}, {'name': 'june'}, {'name': 'june', 'message': 'x', 'force': True},
                    {'name': 'other', 'message': 'x'}):
            with self.assertRaises(JuneError, msg=str(bad)): await self.propose('project-push', bad)
        self.git['branch'] = 'main'
        self.assertIn('directly to main', (await self.propose('project-push', {'name': 'june', 'message': 'x'}))['steps'][0]['preview'])

    async def test_files_changed_after_review_stop_the_push(self):
        self.commands.set_github(True)
        plan = await self.propose('project-push', {'name': 'june', 'message': 'Fix'})
        self.git['changes'] = ' M a.py\n?? secrets.env\n'
        await self.plans.approve(plan['id'], {'requestId': 'req-pc-chg', 'revision': 1, 'fingerprint': plan['fingerprint']})
        for _ in range(100):
            done = (await self.plans.get(plan['id']))['plan']
            if done['status'] not in ('approved', 'running'): break
            await asyncio.sleep(0.02)
        self.assertEqual(done['status'], 'failed'); self.assertIn('changed since you reviewed', done['steps'][0]['result']['message'])
        self.assertEqual(self.argvs('commit') + self.argvs('push'), [])

    async def test_a_failed_push_says_the_commit_stayed_local(self):
        self.commands.set_github(True); self.git['fail'] = 'push'
        done = await self.run_plan('project-push', {'name': 'june', 'message': 'Fix'})
        self.assertEqual(done['status'], 'failed'); self.assertIn('committed on this Mac but not pushed', done['steps'][0]['result']['message'])

    async def test_pull_is_fast_forward_only(self):
        self.commands.set_github(True)
        done = await self.run_plan('project-pull', {'name': 'june'})
        self.assertEqual(done['status'], 'completed'); self.assertIn('Already up to date', done['steps'][0]['result']['message'])
        self.assertIn('--ff-only', self.argvs('pull')[0])
        real = self.commands  # a branch that was never pushed is not an error
        self.git['fail'] = 'pull'
        import june.project_commands as module
        original = module.tail
        self.addCleanup(setattr, module, 'tail', original)
        runner_reply = "fatal: couldn't find remote ref feature/x"
        async def fake_thread(function, argv, *rest):
            return (1, runner_reply) if 'pull' in argv else function(argv, *rest)
        original_thread = module.asyncio.to_thread
        module.asyncio.to_thread = fake_thread
        self.addCleanup(setattr, module.asyncio, 'to_thread', original_thread)
        missing = await self.run_plan('project-pull', {'name': 'june'})
        self.assertEqual(missing['status'], 'completed'); self.assertIn('not on GitHub yet', missing['steps'][0]['result']['message'])


class Recipes(Fixture):
    async def test_tests_and_build_use_the_projects_own_scripts_and_report_the_exit_code(self):
        ok = await self.run_plan('project-recipe', {'name': 'june', 'recipe': 'test'})
        self.assertEqual(ok['status'], 'completed'); self.assertIn('passed', ok['steps'][0]['result']['message']); self.assertIn('fail 0', ok['steps'][0]['result']['message'])
        self.assertEqual(self.ran[-1], (['/usr/local/bin/npm', 'test'], str(self.repo)))
        bad = await self.run_plan('project-recipe', {'name': 'june', 'recipe': 'build'})
        self.assertEqual(bad['status'], 'failed'); self.assertIn('Build error: boom', bad['steps'][0]['result']['message'])
        (self.repo / 'package.json').write_text('{"scripts": {}}')
        with self.assertRaisesRegex(JuneError, 'no test script'): await self.propose('project-recipe', {'name': 'june', 'recipe': 'test'})
        for value in ({'name': 'june', 'recipe': 'deploy'}, {'name': 'june', 'recipe': 'test', 'args': '--x'}):
            with self.assertRaises(JuneError): await self.propose('project-recipe', value)


class Saved(Fixture):
    async def test_saved_commands_are_typed_by_the_person_and_run_exactly(self):
        with self.assertRaises(JuneError): self.commands.add({'projectId': 'nope', 'name': 'lint', 'command': 'npm run lint', 'safe': False, 'kind': 'run'})
        for bad in ({'name': '', 'command': 'x'}, {'name': 'lint', 'command': ''}, {'name': 'lint', 'command': 'a\nb'}, {'name': 'lint', 'command': 'x' * 501}, {'name': 'lint', 'command': 'x', 'kind': 'daemon'}):
            with self.assertRaises(JuneError, msg=str(bad)): self.commands.add({'projectId': 'p1', 'safe': False, 'kind': 'run', **bad})
        state = self.commands.add({'projectId': 'p1', 'name': 'Lint', 'command': 'npm run lint -- --fix', 'safe': False, 'kind': 'run'})
        cid = state['commands'][0]['id']
        with self.assertRaises(JuneError): self.commands.add({'projectId': 'p1', 'name': 'lint', 'command': 'other', 'safe': False, 'kind': 'run'})
        plan = await self.propose('project-command', {'id': cid})
        self.assertIn('npm run lint -- --fix', plan['steps'][0]['preview']); self.assertIn(str(self.repo), plan['steps'][0]['preview']); self.assertFalse(plan['rememberable'])
        done = await self.run_plan('project-command', {'id': cid})
        self.assertEqual(self.ran[-1], (['/bin/zsh', '-c', 'npm run lint -- --fix'], str(self.repo)))
        self.assertEqual(done['status'], 'completed'); self.assertIn('hello from', done['steps'][0]['result']['message'])
        with self.assertRaises(JuneError): await self.propose('project-command', {'id': 'unknown-id'})
        self.assertEqual(self.commands.remove(cid)['commands'], [])
        with self.assertRaises(JuneError): await self.propose('project-command', {'id': cid})

    async def test_only_a_command_marked_safe_can_be_remembered_and_an_edit_asks_again(self):
        cid = self.commands.add({'projectId': 'p1', 'name': 'status', 'command': 'git status', 'safe': True, 'kind': 'run'})['commands'][0]['id']
        first = await self.run_plan('project-command', {'id': cid}, remember=True)
        self.assertEqual(first['status'], 'completed')
        again = await self.propose('project-command', {'id': cid})
        self.assertNotEqual(again['status'], 'proposed', 'the same safe command runs without a new card')
        self.commands.remove(cid)
        changed = self.commands.add({'projectId': 'p1', 'name': 'status', 'command': 'git status; rm -rf x', 'safe': True, 'kind': 'run'})['commands'][0]['id']
        self.assertEqual((await self.propose('project-command', {'id': changed}))['status'], 'proposed', 'different text is a different command')

    async def test_a_server_command_starts_in_the_background_and_can_be_stopped(self):
        cid = self.commands.add({'projectId': 'p1', 'name': 'dev server', 'command': 'npm run dev', 'safe': False, 'kind': 'server'})['commands'][0]['id']
        started = await self.run_plan('project-command', {'id': cid})
        self.assertEqual(started['status'], 'completed'); self.assertIn('is running', started['steps'][0]['result']['message'])
        self.assertEqual(self.started[0][:2], ('npm run dev', str(self.repo)))
        self.assertTrue(self.commands.state()['commands'][0]['running'])
        self.assertIn('already running', (await self.run_plan('project-command', {'id': cid}))['steps'][0]['result']['message'])
        stopped = await self.run_plan('project-stop', {'id': cid})
        self.assertIn('stopped', stopped['steps'][0]['result']['message']); self.assertTrue(self.started[0][2].dead)
        self.assertFalse(self.commands.state()['commands'][0]['running'])


class Chat(Fixture):
    async def test_spoken_requests(self):
        from june.project_commands import command_request
        saved = [dict(id='c1', name='dev server', kind='server', project='June'), dict(id='c2', name='Lint', kind='run', project='June')]
        cases = {
            'run the tests': ('project-recipe', {'name': '', 'recipe': 'test'}), 'run tests in June': ('project-recipe', {'name': 'june', 'recipe': 'test'}),
            'build June': ('project-recipe', {'name': 'june', 'recipe': 'build'}), 'run the build': ('project-recipe', {'name': '', 'recipe': 'build'}),
            'git pull': ('project-pull', {'name': ''}), 'pull the latest changes for June': ('project-pull', {'name': 'june'}),
            'push my changes with message Fix the login bug': ('project-push', {'name': '', 'message': 'Fix the login bug'}),
            'commit and push June with the message add quick actions': ('project-push', {'name': 'june', 'message': 'Add quick actions'}),
            'start the dev server': ('project-command', {'id': 'c1'}), 'stop the dev server': ('project-stop', {'id': 'c1'}), 'run lint': ('project-command', {'id': 'c2'}),
            'Hey June, run my lint command please': ('project-command', {'id': 'c2'}),
        }
        for text, expected in cases.items():
            self.assertEqual(command_request(text, saved), expected, text)
        pushed = command_request('upload this new patch on my github repo', saved)
        self.assertEqual(pushed[0], 'project-push'); self.assertRegex(pushed[1]['message'], r'^Update \d{1,2} \w{3} \d{4}')
        self.assertEqual(command_request('push my changes', saved)[0], 'project-push')
        for text in ('how do I run tests in python?', 'don’t push my changes', 'run', 'run rm -rf /', 'stop lint now and forever in the story', 'push the button', 'build a website for me',
                     'run a marathon', 'pull my leg', 'test my patience'):
            self.assertIsNone(command_request(text, saved), text)

    async def test_chat_prepares_a_card_or_explains(self):
        from june.project_commands import command_chat
        self.assertIsNone(await command_chat('tell me a joke', 'chat-pc-0001', self.plans))
        consent = await command_chat('push my changes with message Fix', 'chat-pc-0002', self.plans)
        self.assertNotIn('plan', consent); self.assertIn('Allow GitHub', consent['reply'])
        self.commands.set_github(True)
        card = await command_chat('push my changes with message Fix', 'chat-pc-0003', self.plans)
        self.assertEqual(card['plan']['status'], 'proposed'); self.assertIn('card', card['reply'])
        tests = await command_chat('run the tests', 'chat-pc-0004', self.plans)
        self.assertEqual(tests['plan']['status'], 'proposed')


class Safety(unittest.TestCase):
    def test_the_engine_allows_a_longer_time_only_where_a_tool_declares_it(self):
        from june.tool_plans import Capability
        self.assertEqual(Capability('x', 'X', 'local', 'local', True).timeout, 30)
        source = (Path(__file__).resolve().parents[1] / 'june/tool_plans.py').read_text()
        self.assertIn('timeout=cap.timeout', source)

    def test_no_force_and_no_model_written_commands(self):
        source = (Path(__file__).resolve().parents[1] / 'june/project_commands.py').read_text()
        for forbidden in ('--force', "'-f'", 'shell=True', 'os.system', 'create_subprocess_shell'):
            self.assertNotIn(forbidden, source)
        self.assertIn('does not run commands with administrator rights', source)
