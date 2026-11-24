"""Receipt probes never repeat outward actions; batch continuation stays reviewed."""
import asyncio
import unittest
import test_jobs as fixtures
from test_jobs import FakeChrome, OPEN, URL1, URL2


class RedirectChrome(FakeChrome):
    def __init__(self):
        super().__init__()
        self.receipt = True
        self.redirect = 'https://www.naukri.com/mnjuser/homepage'
        self.hook = None

    async def call(self, value, timeout=30):
        reply = await super().call(value, timeout)
        if value['operation'] == 'facts':
            tab = self.tabs[value['tab']]
            if tab['clicked']:
                reply['page'].update(url=self.redirect, applied=False, confirmation=False, questions=False)
            elif any(t['clicked'] for t in self.tabs.values()):
                reply['page'].update(applied=self.receipt)
                if self.hook: self.hook()
        return reply


class Receipts(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.Applying.asyncSetUp
    asyncTearDown = fixtures.Applying.asyncTearDown
    run_apply = fixtures.Applying.run_apply

    def redirect_browser(self):
        browser = RedirectChrome()
        browser.pages[URL1] = (OPEN, OPEN)
        browser.pages[URL2] = (OPEN, OPEN)
        self.jobs.browser = self.chrome = browser
        self.jobs.receipt_pause = 0
        return browser

    async def test_redirect_reads_exact_job_and_never_reapplies(self):
        b = self.redirect_browser()
        done = await self.run_apply(['181125000123'], 900)
        self.assertEqual(done['status'], 'completed')
        self.assertEqual(self.jobs.get('181125000123')['status'], 'applied')
        self.assertEqual(sum(c['operation']=='click-apply' for c in b.calls), 1)
        self.assertTrue(all(t.get('closed') for t in b.tabs.values()))

    async def test_missing_receipt_stops_batch_with_reason(self):
        b = self.redirect_browser(); b.receipt = False
        done = await self.run_apply(['181125000123', '181125000456'], 901)
        self.assertEqual(done['status'], 'unknown')
        self.assertEqual(done['steps'][1].get('reason'), 'blocked-by-unknown')
        self.assertEqual(sum(c['operation']=='facts' for c in b.calls), 5) # before, after, three probes
        self.assertEqual(sum(c['operation']=='click-apply' for c in b.calls), 1)

    async def test_stop_during_probe_cannot_turn_into_success(self):
        b = self.redirect_browser()
        b.hook = lambda: self.jobs.set_setting('stopped', '1')
        done = await self.run_apply(['181125000123'], 902)
        self.assertNotEqual(done['status'], 'completed')
        self.assertNotEqual(self.jobs.get('181125000123')['status'], 'applied')
        self.assertTrue(list(b.tabs.values())[-1].get('closed'))

    async def test_wrong_job_receipt_is_not_proof(self):
        b = self.redirect_browser()
        original = b.call
        async def call(value, timeout=30):
            reply = await original(value, timeout)
            if value['operation']=='facts' and reply['page'].get('applied'):
                reply['page']['url'] = URL2
            return reply
        b.call = call
        done = await self.run_apply(['181125000123'], 903)
        self.assertEqual(done['status'], 'unknown')

    async def test_daily_limit_does_not_block_read_only_receipt(self):
        b = self.redirect_browser()
        original = b.call
        async def call(value, timeout=30):
            reply = await original(value, timeout)
            if value['operation']=='click-apply': self.jobs.set_setting('daily-limit', '1')
            return reply
        b.call = call
        self.jobs.applied_today = lambda: 0 if not any(t['clicked'] for t in b.tabs.values()) else 1
        done = await self.run_apply(['181125000123'], 904)
        self.assertEqual(done['status'], 'completed')

    async def test_apply_rest_is_bound_to_batch_and_only_proposes_unstarted_jobs(self):
        from june.jobs import jobs_chat
        b = self.redirect_browser(); b.receipt = False
        self.jobs.set_setting('shown:chat-a', '["181125000123","181125000456"]')
        card = await jobs_chat('apply all', 'receipt-batch-01', self.plans, None, None, conversation='chat-a')
        plan = card['plan']
        await self.plans.approve(plan['id'], {'requestId':'receipt-approval-01', 'revision':1, 'fingerprint':plan['fingerprint']})
        for _ in range(200):
            done = (await self.plans.get(plan['id']))['plan']
            if done['status'] not in ('approved','running'): break
            await asyncio.sleep(.01)
        clicks = sum(c['operation']=='click-apply' for c in b.calls)
        wrong = await jobs_chat('apply to the rest', 'receipt-rest-wrong', self.plans, None, None, conversation='chat-b')
        self.assertNotIn('plan', wrong)
        rest = await jobs_chat('apply to the rest', 'receipt-rest-good', self.plans, None, None, conversation='chat-a')
        self.assertEqual(rest['plan']['status'], 'proposed')
        self.assertEqual(len(rest['plan']['steps']),1)
        self.assertIn('Zomato', rest['plan']['steps'][0]['label'])
        duplicate = await jobs_chat('apply to the rest', 'receipt-rest-good', self.plans, None, None, conversation='chat-a')
        self.assertEqual(rest['plan']['id'], duplicate['plan']['id'])
        self.assertEqual(sum(c['operation']=='click-apply' for c in b.calls),clicks)

    async def test_final_recruiter_save_navigation_reconciles_without_another_answer(self):
        b = self.redirect_browser()
        b.pages[URL1] = (OPEN, dict(OPEN, questions=True))
        b.questions = [dict(question='Have you used React?', kind='radio', options=['Yes','No'])]
        self.jobs.profile.teach('Have you used React?', 'Yes', self.jobs.clock())
        base = b.call
        async def call(value, timeout=30):
            if value['operation']=='facts' and b.tabs[value['tab']]['clicked'] and b.questions:
                return await FakeChrome.call(b,value,timeout)
            if value['operation']=='chat' and not b.questions:
                return dict(ok=True,page=dict(ok=False,reason='different-job'))
            return await base(value, timeout)
        b.call = call
        done = await self.run_apply(['181125000123'], 905)
        self.assertEqual(done['status'],'completed')
        self.assertEqual(len(b.typed),1)
        self.assertEqual(sum(c['operation']=='click-apply' for c in b.calls),1)

    async def test_receipt_gates_and_timeout_cleanup(self):
        from june.errors import JuneError
        for mode in ('login','captcha','external','revoked','generation','closed','timeout'):
            with self.subTest(mode=mode):
                b=self.redirect_browser()
                self.jobs.set_setting('enabled','1'); self.jobs.set_setting('stopped','0')
                base=b.call
                async def call(value,timeout=30):
                    reply=await base(value,timeout)
                    if value['operation']=='facts':
                        if mode in ('login','captcha','external'): reply['page'].update(applied=True, **{mode:True})
                        elif mode=='revoked': self.jobs.set_setting('enabled','0')
                        elif mode=='generation':
                            self.jobs.set_setting('stopped','1'); self.jobs.set_setting('stopped','0')
                        elif mode=='closed': raise JuneError('tab-missing','Closed',409)
                        elif mode=='timeout': await asyncio.sleep(.05)
                    return reply
                b.call=call; self.jobs.receipt_budget=.02
                self.assertFalse(await self.jobs.reconcile('181125000123', self.jobs.control_generation()))
                self.assertTrue(list(b.tabs.values())[-1].get('closed'))
                self.assertFalse(any(c['operation']=='click-apply' or c['operation']=='chat' for c in b.calls))

    async def test_diagnostics_never_retain_path_tokens_or_query(self):
        self.jobs.navigation_diagnostic('https://www.naukri.com/private-secret-123?token=secret#private', '181125000123', 'after-apply')
        path=self.jobs.directory/'diagnostics/job-navigation.jsonl'
        text=path.read_text()
        self.assertNotIn('secret',text); self.assertNotIn('123',text)
        self.assertEqual(path.stat().st_mode & 0o777,0o600)

    async def test_loading_probe_can_settle_on_exact_job(self):
        b=self.redirect_browser(); base=b.call
        reads=0
        async def call(value,timeout=30):
            nonlocal reads
            reply=await base(value,timeout)
            if value['operation']=='facts' and any(t['clicked'] for t in b.tabs.values()) and not b.tabs[value['tab']]['clicked']:
                reads+=1
                if reads==1:reply['page'].update(url='about:blank',ready='complete',applied=False)
            return reply
        b.call=call
        done=await self.run_apply(['181125000123'],906)
        self.assertEqual(done['status'],'completed');self.assertEqual(reads,2)

    async def test_rest_waits_for_active_application_and_does_not_read(self):
        from june.jobs import jobs_chat
        b=self.redirect_browser()
        card=(await self.plans.propose({'requestId':'receipt-active-fixture','intent':'job-apply','input':{'ids':['181125000123']}}))['plan']
        with self.plans.db() as db:
            db.execute("UPDATE plans SET status='running' WHERE id=?",(card['id'],))
        before=len(b.calls)
        reply=await jobs_chat('apply to the rest','receipt-active-check',self.plans,None,None,conversation='chat-a')
        self.assertNotIn('plan',reply);self.assertIn('still running',reply['reply'])
        self.assertEqual(len(b.calls),before)
        with self.plans.db() as db:db.execute("UPDATE plans SET status='cancelled' WHERE id=?",(card['id'],))
