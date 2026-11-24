"""8.5: Naukri jobs are found, ranked, applied to only after review, and counted only on Naukri's confirmation."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

URL1 = 'https://www.naukri.com/job-listings-react-developer-acme-bengaluru-3-to-5-years-181125000123'
URL2 = 'https://www.naukri.com/job-listings-frontend-engineer-zomato-gurugram-2-to-4-years-181125000456'
URL3 = 'https://www.naukri.com/job-listings-ui-designer-studio-pune-1-to-3-years-181125000789'
LISTED = [dict(url=URL1, title='React Developer', company='Acme', location='Bengaluru', experience='3-5 Yrs', salary='Not disclosed'),
          dict(url=URL2, title='Frontend Engineer', company='Zomato', location='Gurugram', experience='2-4 Yrs', salary='12-18 Lacs'),
          dict(url=URL3, title='UI Designer', company='Studio', location='Pune', experience='1-3 Yrs', salary='')]


class FakeChrome:
    """Plays back page facts: `pages[url]` is (before, after) for a job page."""
    def __init__(self):
        self.calls, self.tabs, self.pages, self.logged_out = [], {}, {}, False
        self.questions, self.typed = [], []  # a recruiter-question box: dicts of question/kind/options[/accept]

    def ready(self): return True

    async def call(self, value, timeout=30):
        self.calls.append(value)
        op = value['operation']
        if op == 'status': return dict(ok=True, windows=1)
        if op == 'open':
            tab = len(self.tabs) + 1; self.tabs[tab] = dict(url=value['url'], clicked=False); return dict(ok=True, tab=tab)
        tab = self.tabs[value['tab']]
        if op == 'close': tab['closed'] = True; return dict(ok=True)
        if op == 'list': return dict(ok=True, page=dict(url=tab['url'], ready='complete', loggedOut=self.logged_out, jobs=[] if self.logged_out else LISTED))
        before, after = self.pages[tab['url']]
        if op == 'click-apply':
            from june.jobs import job_id
            assert value['jobId'] == job_id(tab['url']), 'click must be bound to the reviewed job'
            tab['clicked'] = True; return dict(ok=True, page=dict(clicked=bool(before.get('apply'))))
        if op == 'facts':
            page = dict(url=tab['url'], ready='complete', title='Job', **(after if tab['clicked'] else before))
            if tab['clicked'] and page.get('questions') and not self.questions:
                page.update(questions=False, confirmation=True)  # the last question was answered: Naukri confirms
            return dict(ok=True, page=page)
        if op == 'chat':
            from june.jobs import job_id
            assert value['jobId'] == job_id(tab['url']), 'answers are bound to the reviewed job'
            if not self.questions:
                return dict(ok=True, page=dict(ok=True, open=False, applied=True))
            current = self.questions[0]
            if value['mode'] == 'read':
                return dict(ok=True, page=dict(ok=True, open=True, applied=False, question=current['question'], kind=current['kind'], options=current.get('options', [])))
            if value['mode'] == 'option' and value['value'] not in current.get('options', []):
                return dict(ok=True, page=dict(ok=False, reason='no-such-option'))
            self.typed.append((current['question'], value['value']))
            if current.get('accept', True): self.questions.pop(0)
            return dict(ok=True, page=dict(ok=True, answered=True))
        raise AssertionError(op)


OPEN = dict(apply=True, applied=False, external=False, login=False, questions=False, captcha=False)


class Parsing(unittest.TestCase):
    def test_keyword_evidence_ignores_negated_skills_and_substrings(self):
        from june.jobs import resume_keywords,title_keywords
        self.assertEqual(title_keywords('JavaScript Developer'),{'JavaScript'})
        self.assertEqual(title_keywords('Node.js Developer'),{'Node.js'})
        self.assertEqual(title_keywords('React Native Developer'),{'React Native'})
        self.assertEqual(title_keywords('Spring Internship 2026 TS'),set())
        self.assertEqual(resume_keywords('Skills: React, Node.js. No Java, .NET or React Native experience.'),{'React','Node.js'})
        self.assertEqual(resume_keywords('I have not used Python but I use React.'),{'React'})
    def test_job_links_come_from_naukri_alert_emails(self):
        from june.jobs import jobs_from_email
        source = ('Content-Type: text/html; charset=utf-8\n\n<html><a href="' + URL1 + '?src=jobalert&amp;sid=1">React Developer</a>'
                  '<a href="https://evil.test/job-listings-x-181125000999">Phish</a><a href="' + URL2 + '">Frontend Engineer</a></html>')
        jobs = jobs_from_email(source)
        self.assertEqual([j['url'] for j in jobs], [URL1, URL2]); self.assertEqual(jobs[0]['title'], 'React Developer')

    def test_requests(self):
        from june.jobs import jobs_request
        cases = {'find me jobs on naukri': ('find', {}), 'any new jobs': ('find', {}), 'check naukri': ('find', {}), 'apply to the top 3': ('apply', {'top': 3}),
                 'apply to the first one': ('apply', {'positions': [1]}), 'apply to the Zomato one': ('apply', {'company': 'Zomato'}),
                 'apply the second job': ('apply', {'positions': [2]}), 'apply to job 2': ('apply', {'positions': [2]}), 'apply to number 3': ('apply', {'positions': [3]}),
                 'apply to jobs 1 and 3': ('apply', {'positions': [1, 3]}), 'apply to the second and fourth ones': ('apply', {'positions': [2, 4]}),
                 'can you apply to the 2nd one please': ('apply', {'positions': [2]}), 'apply to the last one': ('apply', {'positions': [-1]}),
                 'apply to #4': ('apply', {'positions': [4]}), 'apply to all of them': ('apply', {'all': True}), 'apply for the third job': ('apply', {'positions': [3]}),
                 'what jobs did I apply to this week': ('applied', {}), 'any replies from recruiters': ('applied', {})}
        for text, expected in cases.items():
            self.assertEqual(jobs_request(text), expected, text)
        for text in ('how do I find a job', 'what is naukri', 'don’t apply to anything', 'apply sunscreen', 'tell me about jobs in AI', 'apply the second coat of paint',
                     'how do I apply to the second job'):
            self.assertIsNone(jobs_request(text), text)


class Applying(unittest.IsolatedAsyncioTestCase):
    async def test_request_failures_do_not_become_connector_permission_problems(self):
        from june.jobs import BrowserNative
        from june.errors import JuneError
        from unittest.mock import AsyncMock
        for code,expected in [('tab-missing',None),('page-unreadable',None),('automation-permission','automation-permission'),('javascript-off','javascript-off')]:
            process=SimpleNamespace(communicate=AsyncMock(return_value=(json.dumps({'ok':False,'code':code}).encode(),b'')),returncode=0)
            native=BrowserNative(Path(__file__))
            with patch('june.jobs.asyncio.create_subprocess_exec',AsyncMock(return_value=process)):
                with self.assertRaises(JuneError):await native.call({'operation':'status'})
            self.assertEqual(native.problem,expected)

    async def asyncSetUp(self):
        from june.integrations import create_tools
        from june.jobs import Jobs, register
        self.tmp = tempfile.TemporaryDirectory()
        self.chrome = FakeChrome()
        self.jobs = Jobs(Path(self.tmp.name), self.chrome)
        self.jobs.ask_wait, self.jobs.ask_poll, self.jobs.reminders = 0.05, 0.005, ()  # the live wait, shortened for tests
        self.said = []
        async def announce(question, options, name, reminder=False): self.said.append((question, tuple(options), name, reminder))
        self.jobs.announce = announce
        self.plans = create_tools(Path(self.tmp.name), None, None)
        await self.plans.readiness()
        register(self.plans, self.jobs, pause=0, gap=0)
        await self.jobs.enable(True)
        await self.jobs.from_naukri(pause=0)

    async def asyncTearDown(self):
        await self.plans.close(); self.tmp.cleanup()

    async def run_apply(self, ids, n, wait=200):
        plan = (await self.plans.propose({'requestId': f'req-job-{n:04d}', 'intent': 'job-apply', 'input': {'ids': ids}}))['plan']
        self.assertEqual(plan['status'], 'proposed'); self.assertFalse(plan.get('rememberable'))
        await self.plans.approve(plan['id'], {'requestId': f'req-jap-{n:04d}', 'revision': 1, 'fingerprint': plan['fingerprint']})
        for _ in range(wait):
            done = (await self.plans.get(plan['id']))['plan']
            if done['status'] not in ('approved', 'running'): return done
            await asyncio.sleep(0.01)
        return done

    async def test_found_jobs_are_stored_and_nothing_is_clicked_while_finding(self):
        self.assertEqual(len(self.jobs.list()), 3)
        self.assertFalse(any(c['operation'] == 'click-apply' for c in self.chrome.calls))
        self.assertTrue(self.chrome.tabs[1].get('closed'), 'the list tab is closed after reading')

    async def test_only_naukris_own_confirmation_counts(self):
        self.chrome.pages[URL1] = (OPEN, dict(OPEN, applied=True))
        done = await self.run_apply(['181125000123'], 1)
        self.assertEqual(done['status'], 'completed'); self.assertIn('Naukri’s page confirmed', done['steps'][0]['result']['message'])
        self.assertEqual(self.jobs.get('181125000123')['status'], 'applied')
        self.chrome.pages[URL2] = (OPEN, OPEN)  # pressed, but no confirmation
        done = await self.run_apply(['181125000456'], 2)
        self.assertNotEqual(done['status'], 'completed'); self.assertIn('not counting it as applied', done['steps'][0]['result']['message'])
        self.assertEqual(self.jobs.get('181125000456')['status'], 'not-confirmed')

    async def test_questions_redirects_and_logins_go_back_to_the_person(self):
        for n, (url, jid, before, after, words) in enumerate((
                (URL2, '181125000456', dict(OPEN, apply=False, external=True), OPEN, 'company’s own website'),
                (URL3, '181125000789', dict(OPEN, login=True), OPEN, 'log in')), 10):
            self.chrome.pages[url] = (before, after)
            done = await self.run_apply([jid], n)
            self.assertIn(words, done['steps'][0]['result']['message']); self.assertEqual(self.jobs.get(jid)['status'], 'needs-you')
            tab = max(self.chrome.tabs)
            self.assertFalse(self.chrome.tabs[tab].get('closed'), 'the page stays open for the person')
        self.assertEqual(sum(1 for c in self.chrome.calls if c['operation'] == 'click-apply'), 0, 'June presses Apply only on a plain Apply page')

    async def test_limits_stop_and_already_applied(self):
        from june.errors import JuneError
        self.jobs.set_setting('stopped', '1')
        self.chrome.pages[URL1] = (OPEN, dict(OPEN, applied=True))
        done = await self.run_apply(['181125000123'], 20)
        self.assertIn('stopped', done['steps'][0]['result']['message']); self.assertFalse(any(c['operation'] == 'open' and c['url'] == URL1 for c in self.chrome.calls))
        self.jobs.set_setting('stopped', '0'); self.jobs.set_setting('daily', '1')
        await self.run_apply(['181125000123'], 21)
        self.chrome.pages[URL2] = (OPEN, dict(OPEN, applied=True))
        done = await self.run_apply(['181125000456'], 22)
        self.assertIn('limit of 1', done['steps'][0]['result']['message'])
        with self.assertRaises(JuneError):
            await self.plans.propose({'requestId': 'req-job-0030', 'intent': 'job-apply', 'input': {'ids': ['181125000123']}})
        for bad in ({'ids': []}, {'ids': ['1'] * 6}, {'ids': ['abc']}, {'ids': ['181125000999']}, {'url': URL1}):
            with self.assertRaises(JuneError, msg=str(bad)):
                await self.plans.propose({'requestId': 'req-bad-' + str(abs(hash(str(bad))))[:8], 'intent': 'job-apply', 'input': bad})

    async def test_a_different_page_is_never_applied_to(self):
        self.chrome.pages[URL1] = (dict(OPEN), dict(OPEN, applied=True))
        original = self.chrome.call
        async def redirect(value, timeout=30):
            reply = await original(value, timeout)
            if value['operation'] == 'facts': reply['page']['url'] = URL3
            return reply
        self.chrome.call = redirect
        done = await self.run_apply(['181125000123'], 40)
        self.assertIn('different page', done['steps'][0]['result']['message'])
        self.assertFalse(any(c['operation'] == 'click-apply' for c in self.chrome.calls))

    async def test_an_expired_job_is_reported_as_closed_and_never_applied_to(self):
        expired = dict(OPEN, apply=False, expired=True)  # Naukri's "expired" page, often at another address and without a job title
        self.chrome.pages[URL1] = (expired, expired)
        original = self.chrome.call
        async def redirect(value, timeout=30):
            reply = await original(value, timeout)
            if value['operation'] == 'facts': reply['page'].update(url=URL3, title='')
            return reply
        self.chrome.call = redirect
        done = await self.run_apply(['181125000123'], 41)
        message = done['steps'][0]['result']['message']
        self.assertIn('expired', message); self.assertNotIn('different page', message)
        self.assertFalse(done['steps'][0]['result'].get('verified'))
        self.assertFalse(any(c['operation'] == 'click-apply' for c in self.chrome.calls))
        row = next(j for j in self.jobs.state()['jobs'] if j['id'] == '181125000123')
        self.assertEqual(row['status'], 'skipped'); self.assertIn('expired', row['detail'])

    async def test_a_job_finished_by_hand_is_confirmed_read_only_from_naukri(self):
        from june.errors import JuneError
        self.chrome.pages[URL1] = (OPEN, dict(OPEN, questions=True))
        self.chrome.questions = [dict(question='What is your CGPA?', kind='text')]  # nothing saved: June asks the person
        done = await self.run_apply(['181125000123'], 42)
        self.assertIn('CGPA', done['steps'][0]['result']['message'])
        row = lambda: next(j for j in self.jobs.state()['jobs'] if j['id'] == '181125000123')
        self.assertEqual(row()['status'], 'needs-you')
        clicks = sum(c['operation'] == 'click-apply' for c in self.chrome.calls)
        self.chrome.pages[URL1] = (dict(OPEN), dict(OPEN))  # not finished yet: nothing changes
        reply = await self.jobs.recheck('181125000123', pause=0)
        self.assertEqual(row()['status'], 'needs-you'); self.assertIn('doesn’t show', reply['message'])
        self.chrome.pages[URL1] = (dict(OPEN, apply=False, applied=True), dict(OPEN, apply=False, applied=True))  # the person finished it
        reply = await self.jobs.recheck('181125000123', pause=0)
        self.assertEqual(row()['status'], 'applied'); self.assertIn('Naukri shows', reply['message'])
        self.assertEqual(sum(c['operation'] == 'click-apply' for c in self.chrome.calls), clicks, 'checking never clicks')
        self.assertTrue(all(t.get('closed') for t in list(self.chrome.tabs.values())[-2:]), 'the tabs June opened to check are closed again')
        with self.assertRaises(JuneError): await self.jobs.recheck('181125000123', pause=0)  # applied: nothing to check
        with self.assertRaises(JuneError): await self.jobs.recheck('../x', pause=0)
        await self.jobs.enable(False)
        with self.assertRaises(JuneError): await self.jobs.recheck('181125000456', pause=0)

    def profile(self, **extra):
        from june.job_answers import write_profile
        write_profile(self.jobs.directory / 'job-profile.json', dict(dict(noticeDays=0, currentCtcLpa=3.6, expectedCtcLpa=6, skills=['react', 'html'],
                      zeroForOtherSkills=True, nearbyPlaces=['noida', 'gurugram'], openAcrossNcr=True, ownLaptop=True), **extra))

    async def test_recruiter_questions_are_answered_from_saved_answers_and_submitted(self):
        self.profile()
        self.chrome.pages[URL1] = (OPEN, dict(OPEN, questions=True))
        self.chrome.questions = [dict(question='What is your notice period?', kind='text'),
                                 dict(question='Expected CTC (in Lacs)', kind='number'),
                                 dict(question='Are you willing to relocate to Gurugram?', kind='radio', options=['Yes', 'No']),
                                 dict(question='How many years of experience do you have in Java?', kind='chips', options=['0', '1-2', '3+']),
                                 dict(question='Do you have your own laptop?', kind='chips', options=['Yes', 'No'])]
        done = await self.run_apply(['181125000123'], 50)
        result = done['steps'][0]['result']
        self.assertTrue(result['verified'], result); self.assertIn('answered 5 recruiter questions', result['message'])
        self.assertEqual([a for _, a in self.chrome.typed], ['Immediate joiner', '6', 'Yes', '0', 'Yes'])
        self.assertEqual(self.jobs.get('181125000123')['status'], 'applied')
        self.assertEqual(len(self.jobs.answered('181125000123')), 5, 'every typed answer is logged for the person to see')

    async def test_an_unknown_question_is_asked_once_then_remembered(self):
        self.profile()
        self.chrome.pages[URL1] = (OPEN, dict(OPEN, questions=True))
        self.chrome.questions = [dict(question='What is your notice period?', kind='text'), dict(question='Will you sign a 2 year bond?', kind='radio', options=['Yes', 'No'])]
        done = await self.run_apply(['181125000123'], 51)
        self.assertFalse(done['steps'][0]['result']['verified']); self.assertIn('2 year bond', done['steps'][0]['result']['message'])
        self.assertEqual(self.jobs.get('181125000123')['status'], 'needs-you')
        pending = self.jobs.profile.pending()
        self.assertEqual(pending[0]['question'], 'Will you sign a 2 year bond?'); self.assertEqual(pending[0]['options'], ['Yes', 'No'])
        self.jobs.profile.teach('Will you sign a 2 year bond?', 'No', 1)
        self.chrome.pages[URL2] = (OPEN, dict(OPEN, questions=True))
        self.chrome.questions = [dict(question='Will you sign a 2 year bond?', kind='radio', options=['Yes', 'No'])]
        done = await self.run_apply(['181125000456'], 52)
        self.assertTrue(done['steps'][0]['result']['verified']); self.assertEqual(self.chrome.typed[-1], ('Will you sign a 2 year bond?', 'No'))

    async def test_hard_stops_and_rejected_answers_go_back_to_the_person(self):
        self.profile()
        for n, (questions, words) in enumerate(((
                [dict(question='Please enter the OTP sent to your mobile', kind='text')], 'yourself'),
                ([dict(question='What is your notice period?', kind='text', accept=False)], 'didn’t accept'),
                ([dict(question='Upload your resume', kind='multi')], 'can’t fill in')), 53):
            jid, url = ('181125000123', URL1) if n % 2 else ('181125000456', URL2)
            self.jobs.mark(jid, 'found')
            self.chrome.pages[url] = (OPEN, dict(OPEN, questions=True)); self.chrome.questions = questions
            done = await self.run_apply([jid], n)
            self.assertFalse(done['steps'][0]['result']['verified']); self.assertIn(words, done['steps'][0]['result']['message'])
            self.assertEqual(self.jobs.get(jid)['status'], 'needs-you')
        self.assertNotIn(('Please enter the OTP sent to your mobile', ''), self.chrome.typed)
        self.assertFalse(any('OTP' in q for q, _ in self.chrome.typed), 'nothing is ever typed into a hard stop')

    async def test_a_new_question_is_asked_live_and_the_same_application_continues(self):
        self.profile()
        self.jobs.ask_wait, self.jobs.reminders = 5.0, (0.02,)
        self.chrome.pages[URL1] = (OPEN, dict(OPEN, questions=True))
        self.chrome.questions = [dict(question='Will you sign a 2 year bond?', kind='radio', options=['Yes', 'No']),
                                 dict(question='What is your notice period?', kind='text')]
        async def person():  # answers in June's chat a moment after being asked
            for _ in range(400):
                if self.jobs.profile.pending() and self.jobs.profile.pending()[0]['waitingUntil']:
                    break
                await asyncio.sleep(0.005)
            pending = self.jobs.profile.pending()[0]
            self.assertEqual(pending['title'], 'React Developer at Acme'); self.assertEqual(pending['options'], ['Yes', 'No'])
            await asyncio.sleep(0.05)
            self.jobs.profile.teach(pending['question'], 'No', 1)
        helper = asyncio.ensure_future(person())
        done = await self.run_apply(['181125000123'], 60, wait=600)
        await helper
        result = done['steps'][0]['result']
        self.assertTrue(result['verified'], result); self.assertIn('answered 2 recruiter questions', result['message'])
        self.assertEqual(self.chrome.typed, [('Will you sign a 2 year bond?', 'No'), ('What is your notice period?', 'Immediate joiner')])
        self.assertEqual(self.jobs.profile.pending(), [], 'answered: nothing left waiting')
        spoken = [s for s in self.said if s[0] == 'Will you sign a 2 year bond?']
        self.assertEqual(spoken[0], ('Will you sign a 2 year bond?', ('Yes', 'No'), 'React Developer at Acme', False), 'said out loud once when asked')
        self.assertTrue(any(s[3] for s in spoken), 'and reminded while waiting')
        self.assertFalse(any('No' == part for s in self.said for part in s[:1]), 'answers are never spoken')

    async def test_waiting_ends_on_timeout_stop_or_a_changed_page_with_nothing_typed(self):
        self.profile()
        self.chrome.pages[URL1] = (OPEN, dict(OPEN, questions=True))
        self.chrome.questions = [dict(question='Will you sign a 2 year bond?', kind='radio', options=['Yes', 'No'])]
        done = await self.run_apply(['181125000123'], 61)
        self.assertIn('I waited', done['steps'][0]['result']['message']); self.assertEqual(self.jobs.get('181125000123')['status'], 'needs-you')
        self.assertEqual(self.jobs.profile.pending()[0]['waitingUntil'], None, 'still listed to answer later, no longer waiting')
        self.assertEqual(self.chrome.typed, [])
        self.jobs.mark('181125000123', 'found'); self.jobs.ask_wait = 5.0
        async def stop_soon():
            await asyncio.sleep(0.05); self.jobs.set_setting('stopped', '1')
        stopper = asyncio.ensure_future(stop_soon())
        done = await self.run_apply(['181125000123'], 62, wait=600)
        await stopper
        self.assertIn('stopped', done['steps'][0]['result']['message']); self.assertEqual(self.chrome.typed, [])

    async def test_a_similar_question_reuses_the_saved_answer(self):
        self.profile()
        self.jobs.profile.teach('Do you use AI coding tools in your daily work?', 'Yes, GPT and Claude', 1)
        self.chrome.pages[URL1] = (OPEN, dict(OPEN, questions=True))
        self.chrome.questions = [dict(question='Do you use AI coding tools daily at work?', kind='text')]
        done = await self.run_apply(['181125000123'], 63)
        self.assertTrue(done['steps'][0]['result']['verified'], done['steps'][0]['result'])
        self.assertEqual(self.chrome.typed, [('Do you use AI coding tools daily at work?', 'Yes, GPT and Claude')])
        self.assertEqual(self.jobs.profile.learned('Do you use AI coding tools daily at work?'), 'Yes, GPT and Claude', 'remembered for this wording too')

    async def test_a_borderline_similar_question_needs_a_yes_from_the_second_opinion(self):
        self.profile()
        self.jobs.profile.teach('Do you use AI coding tools in your daily work?', 'Yes, GPT and Claude', 1)
        asked = []
        async def judge(new, old): asked.append((new, old)); return False
        self.jobs.judge = judge
        self.chrome.pages[URL1] = (OPEN, dict(OPEN, questions=True))
        self.chrome.questions = [dict(question='Do you use AI coding tools like Cursor, Copilot or ChatGPT in your daily work?', kind='text')]
        done = await self.run_apply(['181125000123'], 64)
        self.assertEqual(len(asked), 1); self.assertEqual(self.chrome.typed, [], 'the second opinion said no: June asks instead')
        self.assertIn('I waited', done['steps'][0]['result']['message'])

    def test_a_short_chat_reply_answers_the_question_june_is_waiting_on(self):
        from types import SimpleNamespace
        from june.jobs import answer_chat
        plans = SimpleNamespace(naukri=self.jobs)
        self.assertIsNone(answer_chat('yes', plans), 'nothing waiting')
        future = self.jobs.clock() + 60
        self.jobs.profile.ask('Will you sign a 2 year bond?', ['Yes', 'No'], '181125000123', 1, title='Dev at Acme', waiting=future)
        self.assertIsNone(answer_chat('maybe', plans), 'not one of the choices')
        self.assertIn('Saved your answer', answer_chat('no', plans)['reply'])
        self.assertEqual(self.jobs.profile.learned('Will you sign a 2 year bond?'), 'No')
        self.jobs.profile.ask('What is your CGPA?', [], '181125000123', 2, title='Dev at Acme', waiting=future)
        for not_an_answer in ('what time is it?', 'play some music', 'find me jobs on naukri', 'x' * 101):
            self.assertIsNone(answer_chat(not_an_answer, plans), not_an_answer)
        self.assertIn('Saved', answer_chat('8.1', plans)['reply']); self.assertEqual(self.jobs.profile.learned('What is your CGPA?'), '8.1')

    def test_state_reports_last_native_permission_failure(self):
        self.chrome.problem='javascript-off'
        self.assertEqual(self.jobs.state()['problem'],'javascript-off')

    async def test_scoped_confirmation_after_click_is_accepted(self):
        self.chrome.pages[URL1]=(OPEN,dict(OPEN,confirmation=True))
        done=await self.run_apply(['181125000123'],43)
        self.assertEqual(done['status'],'completed')

    async def test_stop_during_page_load_prevents_click(self):
        self.chrome.pages[URL1] = (OPEN, dict(OPEN, applied=True))
        original = self.chrome.call
        async def stop(value, timeout=30):
            reply = await original(value, timeout)
            if value['operation'] == 'facts': self.jobs.set_setting('stopped', '1')
            return reply
        self.chrome.call = stop
        done = await self.run_apply(['181125000123'], 41)
        self.assertNotEqual(done['status'], 'completed')
        self.assertFalse(any(c['operation'] == 'click-apply' for c in self.chrome.calls))

    async def test_confirmation_on_another_job_is_not_counted(self):
        self.chrome.pages[URL1] = (OPEN, dict(OPEN, applied=True))
        original = self.chrome.call
        async def redirect(value, timeout=30):
            reply = await original(value, timeout)
            if value['operation'] == 'facts' and self.chrome.tabs[value['tab']]['clicked']:
                reply['page']['url'] = URL3
            return reply
        self.chrome.call = redirect
        done = await self.run_apply(['181125000123'], 42)
        self.assertNotEqual(done['status'], 'completed')
        self.assertNotEqual(self.jobs.get('181125000123')['status'], 'applied')

    async def test_logged_out_naukri_is_explained(self):
        from june.errors import JuneError
        self.chrome.logged_out = True
        with self.assertRaises(JuneError) as caught:
            await self.jobs.from_naukri(pause=0)
        self.assertIn('Log in to Naukri', caught.exception.message)


class Chat(unittest.IsolatedAsyncioTestCase):
    async def test_status_filter_precedes_limit_and_legacy_reset_preserves_applications(self):
        from june.jobs import Jobs
        with tempfile.TemporaryDirectory() as tmp:
            service=Jobs(Path(tmp))
            rows=[dict(url=f'https://www.naukri.com/job-listings-react-developer-{201126100000+n}',title='React Developer',company='Fixture') for n in range(205)]
            service.upsert(rows,'fixture')
            with service.db() as db:
                db.execute("UPDATE jobs SET status='applied',score=99,at=42")
                db.execute("UPDATE jobs SET status='found',score=NULL WHERE id='201126100000'")
            self.assertEqual(len(service.list(['found'],200)),1)
            await service.rank(None,SimpleNamespace(),'Skills: React.')
            self.assertEqual(service.get('201126100000')['score'],100)
            service.set_setting('ranking-method','legacy-model')
            service.set_setting('enabled','1')
            restarted=Jobs(Path(tmp))
            row=restarted.get('201126100001')
            self.assertIsNone(row['score']);self.assertEqual(row['status'],'applied');self.assertEqual(row['at'],42)
            self.assertTrue(restarted.enabled())
            with restarted.db() as db:db.execute("UPDATE jobs SET score=50 WHERE id='201126100001'")
            self.assertEqual(Jobs(Path(tmp)).get('201126100001')['score'],50,'the migration runs once')

    async def test_title_matching_preserves_explicit_skills_and_abstains_on_generic_roles(self):
        from june.jobs import Jobs
        cases=json.loads((Path(__file__).resolve().parents[2]/'tests/fixtures/assistant-accuracy/cases.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            service=Jobs(Path(tmp))
            service.upsert(cases['jobs']+[dict(url='https://www.naukri.com/job-listings-software-engineer-201126999999',title='Software Engineer',company='Fixture',location='Noida',experience='0-2 Yrs',salary='')],'fixture')
            async def no_model(*a,**kw):raise AssertionError('Keyword matching must not ask a model to invent candidate facts')
            with patch('june.jobs.bounded_json',no_model):
                await service.rank(None,SimpleNamespace(),cases['resume'],limit=30)
            for n in (1,2,3,4,5,12,13,14):
                self.assertEqual(service.get(str(201126000000+n))['score'],100,n)
            for n in (6,7,8,10,11,15):
                self.assertEqual(service.get(str(201126000000+n))['score'],0,n)
            self.assertIsNone(service.get('201126999999')['score'])
            self.assertIn('description',service.get('201126999999')['reason'])
            await service.rank(None,SimpleNamespace(),'Skills: Java and Spring.',limit=30)
            self.assertEqual(service.get('201126000015')['score'],100,'resume changes must invalidate prior derived scores')
            self.assertEqual(service.get('201126000001')['score'],0)
            await service.rank(None,SimpleNamespace(),'')
            self.assertIsNone(service.get('201126000015')['score'],'removed resume must not leave a stale score')
            await service.rank(None,SimpleNamespace(),'Profile. '+('background '*510)+' Skills: React.',limit=30)
            self.assertEqual(service.get('201126000001')['score'],100,'skills after 5000 characters still count')

    async def test_find_ranks_against_the_resume_and_apply_prepares_a_card(self):
        from june.integrations import create_tools
        from june.jobs import Jobs, jobs_chat, register
        with tempfile.TemporaryDirectory() as tmp:
            chrome = FakeChrome(); jobs = Jobs(Path(tmp), chrome)
            plans = create_tools(Path(tmp), None, None); await plans.readiness(); register(plans, jobs, pause=0, gap=0)
            settings = SimpleNamespace(ollama='http://127.0.0.1:1', model='fixture')
            self.assertIn('Allow Chrome', (await jobs_chat('find me jobs on naukri', 'chat-job-0001', plans, None, settings))['reply'])
            await jobs.enable(True)
            asked = []
            async def model(client, url, payload, limit, timeout):
                asked.append(payload)
                return {'message': {'content': json.dumps({'scores': [{'n': 2, 'score': 88, 'reason': 'React and TypeScript match'}, {'n': 1, 'score': 70, 'reason': 'Some overlap'},
                                                                      {'n': 3, 'score': 20, 'reason': 'Design role'}]})}}
            knowledge = SimpleNamespace(db=SimpleNamespace(list=lambda: {'documents': [{'id': 'd1', 'name': 'Person_Resume.pdf', 'status': 'ready'}]},
                                                           get=lambda did, preview=False: {'passages': [{'text': 'React, TypeScript, 3 years'}]}))
            with patch('june.jobs.bounded_json', model):
                found = await jobs_chat('find me jobs on naukri', 'chat-job-0002', plans, None, settings, knowledge, conversation='test-chat')
            self.assertIn('React Developer at Acme (100% title keywords', found['reply']); self.assertEqual(asked,[],'keyword evidence must not be invented by a model')
            self.assertNotRegex(found['reply'], r'(?<!\d)0% title keywords', 'no-overlap jobs are listed without a misleading 0%')
            shown = [r['title'] for r in jobs.list(['found'], 5)]
            second = await jobs_chat('apply the second job', 'chat-job-0005', plans, None, settings, conversation='test-chat')
            self.assertIn(shown[1], second['plan']['steps'][0]['label'], 'the second job is the second one June showed')
            jobs.mark(jobs.list(['found'], 5)[1]['id'], 'applied')
            gone = await jobs_chat('apply to job 2', 'chat-job-0006', plans, None, settings, conversation='test-chat')
            self.assertNotIn('plan', gone); self.assertIn('no longer open', gone['reply'], 'numbers keep meaning the list shown, not a reshuffled one')
            jobs.mark(jobs.list(['applied'], 5)[0]['id'], 'found')
            again = await jobs_chat('find me jobs on naukri', 'chat-job-0007', plans, None, settings, knowledge, conversation='test-chat')
            self.assertIn('No new jobs on Naukri since I last looked', again['reply'])
            card = await jobs_chat('apply to the top 2', 'chat-job-0003', plans, None, settings)
            self.assertEqual(len(card['plan']['steps']), 2); self.assertIn('Acme', card['plan']['steps'][0]['label'])
            self.assertIn('only if Naukri’s page confirms', card['plan']['steps'][0]['preview'])
            self.assertFalse(any(c['operation'] == 'click-apply' for c in chrome.calls), 'nothing is pressed before approval')
            await plans.close()
