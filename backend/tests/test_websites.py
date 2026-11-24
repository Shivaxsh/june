"""8.4: June builds a one-page website, previews it, and publishes it to GitHub Pages after review."""
import asyncio
import html
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

DRAFT = {'title': 'Riverside Bakery', 'summary': 'Fresh bread & pastries baked every morning <by hand>.',
         'sections': [{'heading': 'What we bake', 'text': 'Sourdough, rye and seasonal pastries.', 'bullets': ['Sourdough loaves', 'Cinnamon buns']},
                      {'heading': 'Visit us', 'text': 'We open early on weekdays.', 'bullets': ['Weekdays from 7', 'Weekends from 8']},
                      {'heading': 'Order ahead', 'text': 'Ask in the shop about larger orders.', 'bullets': []}]}
ENV = {'GIT_AUTHOR_NAME': 'Test', 'GIT_AUTHOR_EMAIL': 'test@example.invalid', 'GIT_COMMITTER_NAME': 'Test', 'GIT_COMMITTER_EMAIL': 'test@example.invalid',
       'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_CONFIG_NOSYSTEM': '1', 'PATH': '/usr/bin:/bin', 'HOME': '/tmp'}


def git_runner(log):
    def run(argv, timeout=10, cwd=None):
        log.append(argv)
        done = subprocess.run(argv, cwd=cwd, env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        return done.returncode, done.stdout.decode('utf-8', 'replace')
    return run


class Requests(unittest.TestCase):
    def test_website_requests_are_recognised(self):
        from june.creations import creation_request
        cases = {'make me a website about my bakery called Riverside Bakery': ('site', 'my bakery called Riverside Bakery'),
                 'Hey June, build a landing page for a yoga class': ('site', 'a yoga class'),
                 'create a web page about the history of tea': ('site', 'the history of tea'),
                 'can you make a portfolio site for a wedding photographer': ('site', 'a wedding photographer'),
                 'make a simple website about houseplant care with 3 sections': ('site', 'houseplant care')}
        for text, (kind, topic) in cases.items():
            got = creation_request(text)
            self.assertIsNotNone(got, text); self.assertEqual((got['kind'], got['topic']), (kind, topic), text)
        self.assertEqual(creation_request('make a simple website about houseplant care with 3 sections')['count'], 3)
        for text, kind, topic in (('Make me a cute love letter website for a girl name Kuchupu', 'site', 'cute love letter for a girl name Kuchupu'),
                                  ('build a birthday invitation website for my son', 'site', 'birthday invitation for my son'),
                                  ('make me a love letter website', 'site', 'love letter'),
                                  ('can you make a small portfolio website for my photography', 'site', 'my photography'),
                                  ('create a website that shows my recipes', 'site', 'shows my recipes'),
                                  ('make a website where people can learn about bees', 'site', 'people can learn about bees'),
                                  ('make a quarterly sales presentation for my boss', 'pptx', 'quarterly sales for my boss'),
                                  ('write a cover letter document for a design job', 'docx', 'cover letter for a design job'),
                                  ('make a one page pdf about tea', 'pdf', 'tea'), ('I want a website about my cat', 'site', 'my cat'),
                                  ('can I get a presentation on climate change', 'pptx', 'climate change'), ('I’d like a pdf about tea', 'pdf', 'tea')):
            got = creation_request(text)
            self.assertIsNotNone(got, text); self.assertEqual((got['kind'], got['topic']), (kind, topic), text)
        for text in ('how do I make a website?', 'open the website', 'what is a landing page', 'don’t make a website about cats', 'make a website',
                     'make me a new website', 'make a sandwich for the website', 'why can’t you make a website for me?', 'I want to open the website', 'I need the pdf about taxes'):
            self.assertIsNone(creation_request(text), text)

    def test_publish_requests_are_recognised(self):
        from june.websites import publish_request
        for text in ('publish it', 'Publish the website', 'put it online', 'put my site on github pages', 'make it live', 'Hey June, publish the site please',
                     'deploy it', 'publish my website to the internet', 'ok, put it on the internet'):
            self.assertTrue(publish_request(text), text)
        for text in ('publish a book', 'how do I publish a website?', 'don’t publish it', 'put it in the fridge', 'publish', 'push my changes'):
            self.assertFalse(publish_request(text), text)


class FetchPage(unittest.IsolatedAsyncioTestCase):
    async def test_public_page_checks_use_a_verified_ca_context_and_bounded_read(self):
        import ssl
        from unittest.mock import MagicMock
        from june.websites import fetch_page
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'reviewed page'
        with patch('june.websites.urllib.request.urlopen', return_value=response) as get:
            self.assertEqual(await fetch_page('https://tester.github.io/demo/'), (200, 'reviewed page'))
        context = get.call_args.kwargs.get('context')
        self.assertIsNotNone(context, 'macOS Python default trust store may be absent; supply the application CA bundle')
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        response.read.assert_called_once_with(400000)

    async def test_unapproved_hosts_never_reach_the_network(self):
        from june.websites import fetch_page
        with patch('june.websites.urllib.request.urlopen') as get:
            self.assertEqual(await fetch_page('https://example.invalid/demo/'), (0, ''))
        get.assert_not_called()


class Building(unittest.TestCase):
    def setUp(self):
        from june.creations import Creations
        self.tmp = tempfile.TemporaryDirectory()
        self.opened = []
        self.store = Creations(Path(self.tmp.name) / 'data', Path(self.tmp.name) / 'June Documents', opener=lambda argv: self.opened.append(argv) or 0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_site_is_one_safe_self_contained_page_that_never_overwrites(self):
        made = self.store.build('site', DRAFT)
        page = Path(made['path'])
        self.assertEqual(page.name, 'index.html'); self.assertEqual(page.parent.name, 'riverside-bakery')
        self.assertEqual(page.parent.parent, Path(self.tmp.name) / 'June Websites')
        text = page.read_text()
        self.assertIn('<title>Riverside Bakery</title>', text)
        self.assertIn(html.escape(DRAFT['summary']), text); self.assertNotIn('<by hand>', text, 'model text is escaped')
        for words in ('What we bake', 'Visit us', 'Order ahead', 'Weekends from 8', 'name="viewport"', '--paper:#', "default-src 'none'"):
            self.assertIn(words, text, words)
        for outside in ('http://', 'https://', '<script', '@import', 'url('):
            self.assertNotIn(outside, text, 'a site June makes loads nothing from elsewhere')
        again = self.store.build('site', DRAFT)
        self.assertEqual(Path(again['path']).parent.name, 'riverside-bakery-2'); self.assertTrue(page.exists())
        listed = self.store.state()['creations'][0]
        self.assertEqual((listed['kind'], listed['fileName'], listed['url']), ('site', 'riverside-bakery-2', None))
        self.store.open(made['id'])
        self.assertEqual(self.opened[-1], ['/usr/bin/open', str(page)], 'open previews it in the browser')

    def test_unsafe_titles_become_plain_folder_names(self):
        from june.creations import clean_draft
        made = self.store.build('site', clean_draft({'title': '../../Ünïcode <b>Café</b> ☕ Site', 'summary': '', 'sections': DRAFT['sections']}, 4))
        folder = Path(made['path']).parent
        self.assertEqual(folder.parent, Path(self.tmp.name) / 'June Websites')
        self.assertRegex(folder.name, r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


class Publishing(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from june.creations import Creations
        from june.integrations import create_tools
        from june.project_commands import register as register_commands
        from june.websites import register
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.remote = root / 'tester.github.io.git'
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(self.remote)], env=ENV, check=True)
        self.store = Creations(root / 'data', root / 'June Documents', opener=lambda argv: 0)
        self.plans = create_tools(root / 'data', None, None)
        await self.plans.readiness()
        self.commands = register_commands(self.plans, root / 'data')
        self.log, self.fetched = [], []
        self.live = True
        async def fetch(url):
            self.fetched.append(url)
            return (200, Path(self.site['path']).read_text()) if self.live else (404, '')
        register(self.plans, self.store, self.commands, runner=git_runner(self.log), fetch=fetch, owner=lambda: 'Tester',
                 remote=lambda owner: str(self.remote) if owner == 'Tester' else '/nonexistent', pause=0)
        self.site = self.store.build('site', DRAFT)

    async def asyncTearDown(self):
        await self.plans.close(); self.tmp.cleanup()

    async def settle(self, pid):
        for _ in range(200):
            plan = (await self.plans.get(pid))['plan']
            if plan['status'] not in ('approved', 'running'): return plan
            await asyncio.sleep(0.02)
        return plan

    async def approve(self, plan, rid):
        await self.plans.approve(plan['id'], {'requestId': rid, 'revision': 1, 'fingerprint': plan['fingerprint']})
        return await self.settle(plan['id'])

    def remote_files(self):
        done = subprocess.run(['git', '--git-dir', str(self.remote), 'ls-tree', '-r', '--name-only', 'main'], env=ENV, capture_output=True, text=True)
        return done.stdout.split()

    async def test_publishing_is_reviewed_every_time_and_puts_the_site_on_pages(self):
        self.commands.set_github(True)
        plan = (await self.plans.propose({'requestId': 'req-site-0001', 'intent': 'site-publish', 'input': {'id': self.site['id']}}))['plan']
        self.assertEqual(plan['status'], 'proposed'); self.assertFalse(plan.get('rememberable'))
        preview = plan['steps'][0]['preview']
        for words in ('https://tester.github.io/riverside-bakery/', 'Tester/tester.github.io', 'public', 'github.com'):
            self.assertIn(words, preview, words)
        self.assertEqual(self.log, [], 'nothing touches the network before approval')
        done = await self.approve(plan, 'req-site-0002')
        self.assertEqual(done['status'], 'completed', done['steps'][0].get('result'))
        self.assertIn('https://tester.github.io/riverside-bakery/', done['steps'][0]['result']['message'])
        self.assertIn('riverside-bakery/index.html', self.remote_files())
        self.assertEqual(self.store.state()['creations'][0]['url'], 'https://tester.github.io/riverside-bakery/')
        self.assertTrue(all('--force' not in argv and '-f' not in argv[3:4] for argv in self.log if 'push' in argv))
        again = (await self.plans.propose({'requestId': 'req-site-0003', 'intent': 'site-publish', 'input': {'id': self.site['id']}}))['plan']
        self.assertEqual(again['status'], 'proposed', 'never remembered')
        unchanged = await self.approve(again, 'req-site-0004')
        self.assertIn('already', unchanged['steps'][0]['result']['message'])

    async def test_other_files_in_the_repository_are_kept(self):
        self.commands.set_github(True)
        seed = Path(self.tmp.name) / 'seed'
        subprocess.run(['git', 'clone', '-q', str(self.remote), str(seed)], env=ENV, check=True)
        (seed / 'README.md').write_text('mine'); (seed / 'riverside-bakery').mkdir(); (seed / 'riverside-bakery' / 'old.txt').write_text('old')
        subprocess.run(['git', '-C', str(seed), 'add', '-A'], env=ENV, check=True)
        subprocess.run(['git', '-C', str(seed), 'commit', '-qm', 'seed'], env=ENV, check=True)
        subprocess.run(['git', '-C', str(seed), 'push', '-q', 'origin', 'HEAD:main'], env=ENV, check=True)
        plan = (await self.plans.propose({'requestId': 'req-site-0010', 'intent': 'site-publish', 'input': {'id': self.site['id']}}))['plan']
        self.assertEqual((await self.approve(plan, 'req-site-0011'))['status'], 'completed')
        files = self.remote_files()
        self.assertIn('README.md', files); self.assertIn('riverside-bakery/index.html', files)
        self.assertNotIn('riverside-bakery/old.txt', files, 'the site folder is replaced as a whole')

    async def test_old_page_with_same_title_does_not_prove_new_content_is_live(self):
        from june.websites import register
        async def stale(url):return 200,'<title>Riverside Bakery</title><p>old content</p>'
        register(self.plans,self.store,self.commands,runner=git_runner(self.log),fetch=stale,owner=lambda:'Tester',remote=lambda owner:str(self.remote),pause=0)
        self.commands.set_github(True)
        plan=(await self.plans.propose({'requestId':'site-stale-001','intent':'site-publish','input':{'id':self.site['id']}}))['plan']
        done=await self.approve(plan,'site-stale-002')
        self.assertNotIn('is live at',done['steps'][0]['result']['message'])

    async def test_unchanged_git_content_still_checks_deployment(self):
        self.commands.set_github(True)
        plan=(await self.plans.propose({'requestId':'site-nochange1','intent':'site-publish','input':{'id':self.site['id']}}))['plan']
        await self.approve(plan,'site-nochange2')
        self.live=False;self.fetched.clear()
        plan=(await self.plans.propose({'requestId':'site-nochange3','intent':'site-publish','input':{'id':self.site['id']}}))['plan']
        done=await self.approve(plan,'site-nochange4')
        self.assertTrue(self.fetched)
        self.assertNotIn('already published',done['steps'][0]['result']['message'])

    def test_site_cannot_publish_symlinked_files_from_outside_the_review(self):
        from june.websites import folder_digest
        from june.errors import JuneError
        external=Path(self.tmp.name)/'private-fixture.txt';external.write_text('private fixture')
        (Path(self.site['path']).parent/'linked.txt').symlink_to(external)
        with self.assertRaises(JuneError):folder_digest(Path(self.site['path']).parent)

    async def test_changes_during_clone_cannot_enter_the_reviewed_publish(self):
        from june.websites import register
        original = git_runner(self.log)
        approved = Path(self.site['path']).read_text()
        def mutate(argv, timeout):
            if 'clone' in argv: Path(self.site['path']).write_text('unreviewed content')
            return original(argv, timeout)
        async def served(url): return 200, approved
        register(self.plans,self.store,self.commands,runner=mutate,fetch=served,owner=lambda:'Tester',remote=lambda owner:str(self.remote),pause=0)
        self.commands.set_github(True)
        plan=(await self.plans.propose({'requestId':'site-race-review','intent':'site-publish','input':{'id':self.site['id']}}))['plan']
        done=await self.approve(plan,'site-race-approve')
        self.assertEqual(done['status'],'completed')
        output=subprocess.run(['git','--git-dir',str(self.remote),'show','main:riverside-bakery/index.html'],capture_output=True,text=True,check=True)
        self.assertEqual(output.stdout,approved)

    async def test_revoking_github_during_clone_prevents_the_push(self):
        from june.websites import register
        original = git_runner(self.log)
        def revoked(argv, timeout):
            result = original(argv, timeout)
            if 'clone' in argv: self.commands.set_github(False)
            return result
        register(self.plans, self.store, self.commands, runner=revoked, fetch=None,
                 owner=lambda:'Tester', remote=lambda owner:str(self.remote), pause=0)
        self.commands.set_github(True)
        plan = (await self.plans.propose({'requestId':'revoke-site-review','intent':'site-publish','input':{'id':self.site['id']}}))['plan']
        done = await self.approve(plan, 'revoke-site-approve')
        self.assertNotEqual(done['status'], 'completed')
        self.assertFalse(any('push' in argv for argv in self.log))
        self.assertEqual(self.remote_files(), [])

    async def test_failed_staging_never_commits_or_pushes(self):
        from june.websites import register
        original=git_runner(self.log)
        def fail(argv, timeout):
            if 'add' in argv:return 1,'staging failed'
            return original(argv, timeout)
        register(self.plans,self.store,self.commands,runner=fail,fetch=None,owner=lambda:'Tester',remote=lambda owner:str(self.remote),pause=0)
        self.commands.set_github(True)
        plan=(await self.plans.propose({'requestId':'site-stage-review','intent':'site-publish','input':{'id':self.site['id']}}))['plan']
        done=await self.approve(plan,'site-stage-approve')
        self.assertEqual(done['status'],'failed')
        self.assertFalse(any('push' in argv or 'commit' in argv for argv in self.log))

    async def test_refusals_publish_nothing(self):
        from june.errors import JuneError
        plan = (await self.plans.propose({'requestId': 'req-site-0020', 'intent': 'site-publish', 'input': {'id': self.site['id']}}))['plan']
        done = await self.approve(plan, 'req-site-0021')
        self.assertEqual(done['status'], 'failed'); self.assertIn('Allow GitHub', done['steps'][0]['result']['message'])
        self.commands.set_github(True)
        plan = (await self.plans.propose({'requestId': 'req-site-0022', 'intent': 'site-publish', 'input': {'id': self.site['id']}}))['plan']
        Path(self.site['path']).write_text('<p>edited after review</p>')
        done = await self.approve(plan, 'req-site-0023')
        self.assertEqual(done['status'], 'failed'); self.assertIn('changed since you reviewed', done['steps'][0]['result']['message'])
        self.assertEqual(self.remote_files(), [])
        doc = self.store.build('docx', DRAFT)
        for bad in ({'id': doc['id']}, {'id': '0' * 32}, {'id': '../x'}, {}, {'id': self.site['id'], 'url': 'x'}):
            with self.assertRaises(JuneError, msg=str(bad)):
                await self.plans.propose({'requestId': 'req-site-bad-' + str(abs(hash(str(bad))))[:6], 'intent': 'site-publish', 'input': bad})

    async def test_a_missing_repository_explains_the_one_time_setup(self):
        from june.websites import register
        self.commands.set_github(True)
        register(self.plans, self.store, self.commands, runner=git_runner(self.log), fetch=None, owner=lambda: 'Nobody', remote=lambda owner: str(Path(self.tmp.name) / 'missing.git'), pause=0)
        plan = (await self.plans.propose({'requestId': 'req-site-0030', 'intent': 'site-publish', 'input': {'id': self.site['id']}}))['plan']
        done = await self.approve(plan, 'req-site-0031')
        self.assertEqual(done['status'], 'failed')
        message = done['steps'][0]['result']['message']
        self.assertIn('nobody.github.io', message); self.assertIn('Public', message); self.assertIn('Nothing was published', message)

    async def test_a_page_not_live_yet_is_reported_honestly(self):
        self.commands.set_github(True); self.live = False
        plan = (await self.plans.propose({'requestId': 'req-site-0040', 'intent': 'site-publish', 'input': {'id': self.site['id']}}))['plan']
        done = await self.approve(plan, 'req-site-0041')
        message = done['steps'][0]['result']['message']
        self.assertIn('not live yet', message); self.assertIn('Settings → Pages', message)
        self.assertIn('riverside-bakery/index.html', self.remote_files())

    async def test_chat_proposes_the_latest_site(self):
        from june.websites import publish_chat
        reply = await publish_chat('publish it', 'chat-site-0001', self.plans)
        self.assertEqual(reply['plan']['status'], 'proposed'); self.assertIn('card', reply['reply'])
        self.assertEqual(reply['plan']['steps'][0]['label'], 'Publish Riverside Bakery')
        self.assertIn('https://tester.github.io/riverside-bakery/', reply['reply'])
        self.assertIsNone(await publish_chat('tell me a joke', 'chat-site-0002', self.plans))


class Withdrawing(unittest.IsolatedAsyncioTestCase):
    """Taking a published page down, or putting back the version published before: reviewed every time, checked live."""
    asyncTearDown, settle, approve, remote_files = Publishing.asyncTearDown, Publishing.settle, Publishing.approve, Publishing.remote_files

    async def asyncSetUp(self):
        await Publishing.asyncSetUp(self)
        from june.websites import register
        async def served(url):  # what GitHub Pages would serve: the page in the repository right now
            self.fetched.append(url)
            done = subprocess.run(['git', '--git-dir', str(self.remote), 'show', 'main:riverside-bakery/index.html'], env=ENV, capture_output=True, text=True)
            return (200, done.stdout) if done.returncode == 0 else (404, '')
        register(self.plans, self.store, self.commands, runner=git_runner(self.log), fetch=served, owner=lambda: 'Tester',
                 remote=lambda owner: str(self.remote), pause=0)
        self.commands.set_github(True)

    def remote_page(self):
        return subprocess.run(['git', '--git-dir', str(self.remote), 'show', 'main:riverside-bakery/index.html'], env=ENV, capture_output=True, text=True).stdout

    async def publish(self, key):
        plan = (await self.plans.propose({'requestId': f'pub-{key}-review', 'intent': 'site-publish', 'input': {'id': self.site['id']}}))['plan']
        done = await self.approve(plan, f'pub-{key}-approve')
        self.assertEqual(done['status'], 'completed', done['steps'][0].get('result'))

    def seed(self, change):
        seed = Path(self.tmp.name) / 'seed'
        subprocess.run(['git', 'clone', '-q', str(self.remote), str(seed)], env=ENV, check=True)
        change(seed)
        subprocess.run(['git', '-C', str(seed), 'add', '-A'], env=ENV, check=True)
        subprocess.run(['git', '-C', str(seed), 'commit', '-qm', 'outside June'], env=ENV, check=True)
        subprocess.run(['git', '-C', str(seed), 'push', '-q', 'origin', 'HEAD:main'], env=ENV, check=True)

    async def test_take_down_is_reviewed_every_time_and_removes_only_that_page(self):
        await self.publish('one')
        self.seed(lambda seed: (seed / 'README.md').write_text('mine'))
        self.log.clear()
        plan = (await self.plans.propose({'requestId': 'down-0001-review', 'intent': 'site-unpublish', 'input': {'id': self.site['id']}}))['plan']
        self.assertEqual(plan['status'], 'proposed'); self.assertFalse(plan.get('rememberable'))
        preview = plan['steps'][0]['preview']
        for words in ('https://tester.github.io/riverside-bakery/', 'riverside-bakery/', 'Tester/tester.github.io', 'github.com'):
            self.assertIn(words, preview, words)
        self.assertEqual(self.log, [], 'nothing touches the network before approval')
        done = await self.approve(plan, 'down-0001-approve')
        self.assertEqual(done['status'], 'completed', done['steps'][0].get('result'))
        self.assertIn('no longer', done['steps'][0]['result']['message'])
        files = self.remote_files()
        self.assertIn('README.md', files); self.assertFalse(any(f.startswith('riverside-bakery/') for f in files))
        self.assertIsNone(self.store.state()['creations'][0]['url'])
        self.assertTrue(Path(self.site['path']).is_file(), 'the site on this Mac is kept')
        self.assertTrue(all('--force' not in argv for argv in self.log if 'push' in argv))
        again = (await self.plans.propose({'requestId': 'down-0002-review', 'intent': 'site-publish', 'input': {'id': self.site['id']}}))['plan']
        self.assertEqual(again['status'], 'proposed', 'publishing again is a fresh review')

    async def test_saved_published_versions_are_private_to_this_user(self):
        import stat
        saved = Path(self.store.directory) / 'published'
        saved.mkdir(parents=True); os.chmod(saved, 0o755)  # an older June made it readable by others
        await self.publish('private')
        for folder in [saved, *[p for p in saved.rglob('*') if p.is_dir()]]:
            self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700, folder)

    async def test_take_down_reports_a_page_still_being_served_honestly(self):
        from june.websites import register
        await self.publish('cache')
        async def cached(url): return 200, 'old copy'
        register(self.plans, self.store, self.commands, runner=git_runner(self.log), fetch=cached, owner=lambda: 'Tester', remote=lambda owner: str(self.remote), pause=0)
        plan = (await self.plans.propose({'requestId': 'down-cache-review', 'intent': 'site-unpublish', 'input': {'id': self.site['id']}}))['plan']
        done = await self.approve(plan, 'down-cache-approve')
        message = done['steps'][0]['result']['message']
        self.assertNotIn('no longer', message); self.assertIn('still', message)

    async def test_undo_puts_back_the_version_published_before(self):
        await self.publish('v1')
        first = self.remote_page()
        Path(self.site['path']).write_text(first.replace('Riverside Bakery</h1>', 'Riverside Bakery, now open late</h1>'))
        await self.publish('v2')
        self.assertNotEqual(self.remote_page(), first)
        Path(self.site['path']).write_text('<p>local edits after publishing never go online by undoing</p>')
        self.log.clear()
        plan = (await self.plans.propose({'requestId': 'undo-0001-review', 'intent': 'site-rollback', 'input': {'id': self.site['id']}}))['plan']
        self.assertFalse(plan.get('rememberable')); self.assertEqual(self.log, [])
        self.assertIn('https://tester.github.io/riverside-bakery/', plan['steps'][0]['preview'])
        done = await self.approve(plan, 'undo-0001-approve')
        self.assertEqual(done['status'], 'completed', done['steps'][0].get('result'))
        self.assertEqual(self.remote_page(), first)
        self.assertIn('is live at', done['steps'][0]['result']['message'])
        with self.assertRaises(Exception):  # only one published version is left: nothing earlier to go back to
            await self.plans.propose({'requestId': 'undo-0002-review', 'intent': 'site-rollback', 'input': {'id': self.site['id']}})

    async def test_undo_with_only_one_version_offers_nothing_to_go_back_to(self):
        from june.errors import JuneError
        await self.publish('only')
        with self.assertRaises(JuneError) as caught:
            await self.plans.propose({'requestId': 'undo-only-review', 'intent': 'site-rollback', 'input': {'id': self.site['id']}})
        self.assertIn('take', caught.exception.message.lower())

    async def test_undo_never_overwrites_a_page_changed_outside_june(self):
        await self.publish('a')
        Path(self.site['path']).write_text(self.remote_page() + '<!-- v2 -->')
        await self.publish('b')
        self.seed(lambda seed: (seed / 'riverside-bakery' / 'index.html').write_text('edited on github.com'))
        plan = (await self.plans.propose({'requestId': 'undo-edit-review', 'intent': 'site-rollback', 'input': {'id': self.site['id']}}))['plan']
        done = await self.approve(plan, 'undo-edit-approve')
        self.assertEqual(done['status'], 'failed')
        self.assertIn('changed', done['steps'][0]['result']['message'])
        self.assertEqual(self.remote_page(), 'edited on github.com')

    async def test_a_tampered_saved_version_is_never_published(self):
        await self.publish('t1')
        Path(self.site['path']).write_text(self.remote_page() + '<!-- v2 -->')
        await self.publish('t2')
        plan = (await self.plans.propose({'requestId': 'undo-tamper-review', 'intent': 'site-rollback', 'input': {'id': self.site['id']}}))['plan']
        saved = Path(self.store.directory) / 'published' / 'riverside-bakery'
        for page in saved.rglob('index.html'): page.write_text('tampered')
        done = await self.approve(plan, 'undo-tamper-approve')
        self.assertEqual(done['status'], 'failed')
        self.assertNotEqual(self.remote_page(), 'tampered')

    async def test_chat_offers_cards_only_for_a_published_site(self):
        from june.websites import withdraw_chat
        reply = await withdraw_chat('take my website down', 'chat-down-0001', self.plans)
        self.assertNotIn('plan', reply); self.assertIn('isn’t online', reply['reply'])
        await self.publish('chat')
        reply = await withdraw_chat('take my website down', 'chat-down-0002', self.plans)
        self.assertEqual(reply['plan']['steps'][0]['label'], 'Take down Riverside Bakery')
        reply = await withdraw_chat('undo the last publish', 'chat-down-0003', self.plans)
        self.assertNotIn('plan', reply); self.assertIn('take my website down', reply['reply'])
        self.assertIsNone(await withdraw_chat('tell me a joke', 'chat-down-0004', self.plans))


class WithdrawRequests(unittest.TestCase):
    def test_take_down_and_undo_requests_are_recognised(self):
        from june.websites import withdraw_request
        for text in ('take it down', 'take my website down', 'unpublish it', 'unpublish the site', 'take the site offline', 'take it offline',
                     'remove my website from the internet', 'delete the site from github', 'take down the website please', 'Hey June, take the page down',
                     'take my site off the internet'):
            self.assertEqual(withdraw_request(text), 'unpublish', text)
        for text in ('undo the last publish', 'undo the publish', 'roll back the website', 'roll the site back', 'revert the website',
                     'put back the old version of the site', 'go back to the previous version of my website', 'restore the earlier version of the website',
                     'undo publishing'):
            self.assertEqual(withdraw_request(text), 'rollback', text)
        for text in ('take it down a notch', 'remove it', 'delete it', 'undo that', 'roll back the carpet', 'how do I take a website down?',
                     'don’t take it down', 'revert my last commit', 'take down notes', 'go back to the previous song'):
            self.assertIsNone(withdraw_request(text), text)


class NoSiteYet(unittest.IsolatedAsyncioTestCase):
    async def test_publish_without_a_site_says_how_to_make_one(self):
        from june.creations import Creations
        from june.integrations import create_tools
        from june.project_commands import register as register_commands
        from june.websites import publish_chat, register
        with tempfile.TemporaryDirectory() as tmp:
            store = Creations(Path(tmp) / 'data', Path(tmp) / 'June Documents', opener=lambda argv: 0)
            plans = create_tools(Path(tmp) / 'data', None, None); await plans.readiness()
            register(plans, store, register_commands(plans, Path(tmp) / 'data'), owner=lambda: 'Tester', pause=0)
            reply = await publish_chat('put it online', 'chat-site-0003', plans)
            self.assertNotIn('plan', reply); self.assertIn('haven’t made a website', reply['reply'])
            await plans.close()


class Owner(unittest.TestCase):
    def test_the_github_account_comes_from_saved_project_remotes(self):
        from june.websites import github_owner
        projects = [{'folderPath': '/a'}, {'folderPath': '/b'}]
        remotes = {'/a': 'https://github.com/Shivaxsh/june.git', '/b': 'git@github.com:Shivaxsh/other.git'}
        runner = lambda argv, timeout=10, cwd=None: (0, remotes[argv[2]] + '\n')
        self.assertEqual(github_owner(projects, runner), 'Shivaxsh')
        remotes['/b'] = 'https://github.com/someone-else/x.git'
        self.assertIsNone(github_owner(projects, runner), 'two different accounts: June does not guess')
        self.assertIsNone(github_owner([], runner))


if __name__ == '__main__':
    unittest.main()
