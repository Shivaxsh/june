"""Adversarial recruiter regressions; synthetic profiles/pages only, no real applications."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from test_job_answers import PROFILE
from test_jobs import FakeChrome, LISTED, OPEN, URL1, URL2
from june.job_answers import choose, standing_answer, write_profile
from june.jobs import Jobs, jobs_chat, jobs_request


class AnswerAccuracy(unittest.TestCase):
    def test_alternative_positions_and_zero_jobs_need_clarification(self):
        self.assertEqual(jobs_request('apply to jobs 1 or 3')[0], 'clarify')
        self.assertEqual(jobs_request('apply to the top 0')[0], 'clarify')

    def test_numeric_prefixes_do_not_inflate_experience(self):
        self.assertIsNone(choose('1', ['10 years', '15 years']))
        self.assertIsNone(choose('4 LPA', ['40 LPA', '45 LPA']))

    def test_month_questions_use_months(self):
        self.assertEqual(standing_answer('How many months of experience do you have in React?', 'number', PROFILE), '12')
        self.assertEqual(standing_answer('Total experience in months', 'number', PROFILE), '12')

    def test_related_skill_names_are_not_the_same_skill(self):
        self.assertEqual(standing_answer('Years of experience in React Native', 'number', PROFILE), '0')
        self.assertIsNone(standing_answer('Years of experience in Node JS', 'number', PROFILE))

    def test_javascript_alias_does_not_claim_other_dot_js_frameworks(self):
        profile = dict(PROFILE, skills=[*PROFILE['skills'], 'js'])
        for skill in ('Vue.js', 'Angular.js'):
            self.assertEqual(standing_answer(f'Years of experience in {skill}', 'number', profile), '0')
            self.assertEqual(standing_answer(f'Do you have experience with {skill}?', 'radio', profile), 'No')

    def test_compound_skill_questions_do_not_borrow_one_skills_answer(self):
        self.assertIsNone(standing_answer('How many years of experience in React and Angular?', 'number', PROFILE))
        self.assertIsNone(standing_answer('Do you have experience with React and Angular?', 'radio', PROFILE))

    def test_salary_unit_and_frequency_are_both_respected(self):
        self.assertEqual(standing_answer('Expected salary per month in lakhs', 'number', PROFILE), '0.5')
        self.assertEqual(standing_answer('Current CTC in thousands', 'number', PROFILE), '360')
        self.assertEqual(standing_answer('Expected salary in K per month', 'number', PROFILE), '50')

    def test_numeric_ranges_cannot_mix_months_years_or_money_units(self):
        self.assertEqual(choose('1', ['Less than 6 months', '6 months - 1 year', '1-2 years'],
                                question='Years of experience in React'), '1-2 years')
        self.assertIsNone(choose('1', ['0-6 months', '6-12 months'], question='Years of experience in React'))
        self.assertIsNone(choose('4', ['3-5 thousand'], question='Expected CTC in LPA'))

    def test_unknown_entity_fields_are_not_personal_name(self):
        for question in ('What is your university name?', 'What is your manager name?', 'What is your reference email?'):
            self.assertIsNone(standing_answer(question, 'text', PROFILE), question)

    def test_previous_employment_is_not_a_universal_no_or_a_referral_answer(self):
        self.assertEqual(standing_answer('Have you ever been employed by Example Co?', 'radio', PROFILE), 'Yes')
        self.assertIsNone(standing_answer('Have you ever been employed by Another Company?', 'radio', PROFILE))
        self.assertIsNone(standing_answer('Were you referred by an employee?', 'radio', PROFILE))


class RecruiterLifecycle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.chrome = FakeChrome()
        self.jobs = Jobs(Path(self.tmp.name), self.chrome)
        self.jobs.upsert(LISTED, 'synthetic')
        await self.jobs.enable(True)
        write_profile(self.jobs.profile.path, PROFILE)
        self.chrome.pages[URL1] = (OPEN, dict(OPEN, questions=True))
        self.tab = (await self.chrome.call({'operation':'open', 'url':URL1}))['tab']
        self.chrome.tabs[self.tab]['clicked'] = True

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def run_questions(self):
        return await self.jobs.answer_questions(self.tab, '181125000123', 'Synthetic role', pause=0)

    async def test_greeting_waits_for_real_question_even_with_a_learned_greeting_answer(self):
        greeting = "Hi Test Person, thank you for showing interest. Kindly answer all the recruiter's questions to successfully apply for the job."
        self.jobs.profile.teach(greeting, 'Never type this greeting answer', 1)
        q = 'What is your notice period?'
        self.chrome.questions = [dict(question=q, kind='text')]
        original, reads = self.chrome.call, 0
        async def loading(value, timeout=30):
            nonlocal reads
            if value['operation']=='chat' and value['mode']=='read':
                reads += 1
                if reads <= 3:
                    return {'page':dict(ok=True, open=True, question=greeting, kind='text')}
            return await original(value, timeout)
        self.chrome.call = loading
        status, _, _ = await self.jobs.answer_questions(self.tab, '181125000123', 'Synthetic role', pause=0, limit=2)
        self.assertEqual(status, 'applied')
        self.assertEqual([question for question, _ in self.chrome.typed], [q])
        self.assertEqual(self.jobs.profile.pending(), [])

    async def test_unknown_control_waits_for_ready_question_without_typing_early(self):
        q = 'What is your notice period?'
        self.chrome.questions = [dict(question=q, kind='text')]
        original, reads = self.chrome.call, 0
        async def loading(value, timeout=30):
            nonlocal reads
            if value['operation']=='chat' and value['mode']=='read':
                reads += 1
                if reads <= 2:
                    return {'page':dict(ok=True, open=True, question=q, kind='unknown')}
            return await original(value, timeout)
        self.chrome.call = loading
        status, _, _ = await self.run_questions()
        self.assertEqual(status, 'applied')
        self.assertEqual(len(self.chrome.typed), 1)

    async def test_loading_timeout_is_bounded_and_never_teaches_a_greeting(self):
        greeting = "Hi Test Person, thank you for showing interest. Kindly answer all the recruiter's questions to successfully apply for the job."
        self.chrome.questions = [dict(question=greeting, kind='text')]
        status, detail, _ = await self.run_questions()
        self.assertEqual(status, 'needs-you')
        self.assertIn('ready', detail)
        self.assertEqual(self.chrome.typed, [])
        self.assertEqual(self.jobs.profile.pending(), [])
        self.assertLessEqual(len(self.chrome.calls), 15)

    async def test_greeting_wording_variants_are_never_saved_as_questions(self):
        for greeting in ('Hi Test Person, thank you for showing interest',
                         "Hello Test Person! Please answer the recruiter's questions",
                         'Dear Test Person, thank you for your interest in this job'):
            with self.subTest(greeting=greeting):
                self.chrome.questions = [dict(question=greeting, kind='text')]
                status, _, message = await self.run_questions()
                self.assertEqual(status, 'needs-you')
                self.assertNotIn('Test Person', message)
                self.assertEqual(self.chrome.typed, [])
                self.assertEqual(self.jobs.profile.pending(), [])

    async def test_greeting_with_real_question_is_answered_with_full_native_binding(self):
        q = 'Hi Test Person, thank you for your interest. What is your notice period?'
        self.chrome.questions = [dict(question=q, kind='text')]
        status, _, _ = await self.run_questions()
        self.assertEqual(status, 'applied')
        writes = [v for v in self.chrome.calls if v['operation']=='chat' and v['mode']!='read']
        self.assertEqual(writes[0]['expectedQuestion'], q)

    async def test_stop_during_greeting_wait_enters_nothing(self):
        greeting = "Hi Test Person, thank you for showing interest. Kindly answer all the recruiter's questions to successfully apply for the job."
        self.chrome.questions = [dict(question=greeting, kind='text')]
        original, reads = self.chrome.call, 0
        async def stopped(value, timeout=30):
            nonlocal reads
            result = await original(value, timeout)
            if value['operation']=='chat' and value['mode']=='read':
                reads += 1
                if reads == 2: self.jobs.set_setting('stopped', '1')
            return result
        self.chrome.call = stopped
        status, _, _ = await self.run_questions()
        self.assertEqual(status, 'needs-you')
        self.assertEqual(reads, 2)
        self.assertEqual(self.chrome.typed, [])
        self.assertEqual(self.jobs.profile.pending(), [])

    async def test_question_without_question_mark_is_not_a_loading_greeting(self):
        q = 'Years of experience in React'
        self.chrome.questions = [dict(question=q, kind='text')]
        status, _, _ = await self.run_questions()
        self.assertEqual(status, 'applied')
        self.assertEqual(self.chrome.typed, [(q, '1')])

    async def test_legacy_learned_answer_cannot_bypass_hard_stop(self):
        from june.job_answers import key
        q = 'Enter the OTP sent to your phone'
        with self.jobs.db() as db:
            db.execute('INSERT INTO answers VALUES(?,?,?,?)', (key(q), q, '123456', 1))
        self.chrome.questions = [dict(question=q, kind='text')]
        status, _, _ = await self.run_questions()
        self.assertEqual(status, 'needs-you')
        self.assertEqual(self.chrome.typed, [])

    async def test_stop_after_read_prevents_any_answer(self):
        self.chrome.questions = [dict(question='What is your notice period?', kind='text')]
        original = self.chrome.call
        async def stopped(value, timeout=30):
            result = await original(value, timeout)
            if value['operation']=='chat' and value['mode']=='read':
                self.jobs.set_setting('stopped', '1')
            return result
        self.chrome.call = stopped
        status, _, _ = await self.run_questions()
        self.assertNotEqual(status, 'applied')
        self.assertEqual(self.chrome.typed, [])

    async def test_off_then_on_does_not_resume_a_revoked_application(self):
        self.chrome.questions = [dict(question='What is your notice period?', kind='text')]
        original = self.chrome.call
        async def toggled(value, timeout=30):
            result = await original(value, timeout)
            if value['operation']=='chat' and value['mode']=='read':
                self.jobs.set_setting('enabled', '0')
                self.jobs.set_setting('enabled', '1')
            return result
        self.chrome.call = toggled
        status, _, _ = await self.run_questions()
        self.assertNotEqual(status, 'applied')
        self.assertEqual(self.chrome.typed, [])

    async def test_skipping_during_read_prevents_the_answer(self):
        self.chrome.questions = [dict(question='What is your notice period?', kind='text')]
        original = self.chrome.call
        async def skipped(value, timeout=30):
            result = await original(value, timeout)
            if value['operation']=='chat' and value['mode']=='read':
                self.jobs.mark('181125000123', 'skipped')
            return result
        self.chrome.call = skipped
        status, _, _ = await self.run_questions()
        self.assertNotEqual(status, 'applied')
        self.assertEqual(self.chrome.typed, [])

    async def test_teaching_controls_or_a_hard_stop_is_refused(self):
        for q, a in [('Enter the OTP', '123456'), ('Custom answer?', 'a\nb'), ('Custom answer?', 'a\tb')]:
            with self.assertRaises(ValueError):
                self.jobs.profile.teach(q, a, 1)

    async def test_disable_after_first_answer_prevents_next(self):
        self.chrome.questions = [dict(question='What is your notice period?', kind='text'),
                                 dict(question='What is your expected salary?', kind='text')]
        original = self.chrome.call
        async def disabled(value, timeout=30):
            result = await original(value, timeout)
            if value['operation']=='chat' and value['mode']!='read':
                self.jobs.set_setting('enabled', '0')
            return result
        self.chrome.call = disabled
        status, _, _ = await self.run_questions()
        self.assertNotEqual(status, 'applied')
        self.assertEqual(len(self.chrome.typed), 1)

    async def test_another_jobs_confirmation_never_counts(self):
        original = self.chrome.call
        async def changed(value, timeout=30):
            if value['operation']=='facts':
                return {'page':dict(url=URL2, applied=True, confirmation=True)}
            return await original(value, timeout)
        self.chrome.call = changed
        status, _, _ = await self.run_questions()
        self.assertNotEqual(status, 'applied')

    async def test_each_write_is_bound_to_the_question_that_was_answered(self):
        q = 'What is your notice period?'
        self.chrome.questions = [dict(question=q, kind='text')]
        await self.run_questions()
        writes = [v for v in self.chrome.calls if v['operation']=='chat' and v['mode']!='read']
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].get('expectedQuestion'), q)

    async def test_changed_question_before_entry_is_reread_without_using_the_stale_answer(self):
        q = 'What is your notice period?'
        self.chrome.questions = [dict(question=q, kind='text')]
        original = self.chrome.call
        changed = False
        async def racing(value, timeout=30):
            nonlocal changed
            if value['operation']=='chat' and value['mode']!='read' and not changed:
                changed = True
                self.chrome.questions = [dict(question='Expected CTC (in Lacs)', kind='number')]
                return {'page':{'ok':True, 'answered':False, 'reason':'question-changed'}}
            return await original(value, timeout)
        self.chrome.call = racing
        status, _, _ = await self.run_questions()
        self.assertEqual(status, 'applied')
        self.assertEqual(self.chrome.typed, [('Expected CTC (in Lacs)', '6')])

    async def test_failed_save_is_not_misreported_as_a_rejected_answer(self):
        q = 'What is your notice period?'
        self.chrome.questions = [dict(question=q, kind='text', accept=False)]
        original = self.chrome.call
        async def unsaved(value, timeout=30):
            result = await original(value, timeout)
            if value['operation']=='chat' and value['mode']=='read' and self.chrome.typed:
                result['page']['lastSave'] = {'question':q, 'saved':False, 'reason':'no-save-button'}
            return result
        self.chrome.call = unsaved
        status, _, message = await self.run_questions()
        self.assertEqual(status, 'needs-you')
        self.assertIn('save', message.lower())
        self.assertNotIn('didn’t accept', message)
        self.assertEqual(len(self.chrome.typed), 1, 'no blind re-entry after an uncertain Save')

    async def test_two_approved_cards_for_the_same_job_never_double_click(self):
        import asyncio
        from june.integrations import create_tools
        from june.jobs import register
        plans = create_tools(Path(self.tmp.name), None, None)
        await plans.readiness()
        register(plans, self.jobs, pause=0, gap=0)
        self.chrome.pages[URL1] = (OPEN, dict(OPEN, applied=True))
        original = self.chrome.call
        async def delayed(value, timeout=30):
            result = await original(value, timeout)
            if value['operation']=='click-apply': await asyncio.sleep(0.04)
            return result
        self.chrome.call = delayed
        try:
            cards = [(await plans.propose({'requestId':f'duplicate-review-{n}', 'intent':'job-apply',
                     'input':{'ids':['181125000123']}}))['plan'] for n in (1,2)]
            for n,card in enumerate(cards):
                await plans.approve(card['id'], {'requestId':f'duplicate-approve-{n}', 'revision':1, 'fingerprint':card['fingerprint']})
            for _ in range(100):
                results = [(await plans.get(card['id']))['plan'] for card in cards]
                if all(p['status'] not in ('approved','running') for p in results): break
                await asyncio.sleep(0.01)
            self.assertTrue(all(p['status'] not in ('approved','running') for p in results))
            self.assertEqual(sum(v['operation']=='click-apply' for v in self.chrome.calls), 1)
        finally:
            await plans.close()


class ListedPositions(unittest.IsolatedAsyncioTestCase):
    async def test_saved_chats_keep_their_own_list_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = Jobs(Path(tmp), FakeChrome())
            await jobs.enable(True)
            jobs.upsert(LISTED, 'synthetic')
            jobs.from_naukri = AsyncMock(return_value=0)
            jobs.from_mail = AsyncMock(return_value=0)
            jobs.rank = AsyncMock(return_value=0)
            async def propose(value):
                return {'plan': {'id':'fixture-plan-id', 'ids':value['input']['ids']}, 'serverNow':1}
            plans = SimpleNamespace(naukri=jobs, propose=propose)
            settings = SimpleNamespace()
            with jobs.db() as db:
                for n,row in enumerate(LISTED): db.execute('UPDATE jobs SET score=? WHERE url=?', (90-n*10,row['url']))
            original = [j['id'] for j in jobs.list(['found'], 5)]
            await jobs_chat('find me jobs on naukri', 'list-a', plans, None, settings, conversation='chat-a')
            with jobs.db() as db:
                db.execute('UPDATE jobs SET score=100-score')
            await jobs_chat('find me jobs on naukri', 'list-b', plans, None, settings, conversation='chat-b')
            selected = await jobs_chat('apply the second job', 'pick-a', plans, None, settings, conversation='chat-a')
            self.assertEqual(selected['plan']['ids'], [original[1]])
            absent = await jobs_chat('apply the second job', 'pick-c', plans, None, settings, conversation='chat-c')
            self.assertNotIn('plan', absent)
