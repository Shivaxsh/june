"""Current live-recruiter audit: synthetic state only; never contacts Chrome or voice."""
import tempfile
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace

from june.jobs import Jobs, answer_chat
from test_jobs import FakeChrome


class SimilarityAudit(unittest.TestCase):
    def test_negation_never_reuses_an_affirmative_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Jobs(Path(tmp)).profile
            profile.teach('Do you have experience building secure customer account dashboards?', 'Yes', 1)
            for q in ('Do you have no experience building secure customer account dashboards?',
                      'Do you not have experience building secure customer account dashboards?'):
                self.assertEqual(profile.similar(q, 'text', []), [], q)

    def test_changed_required_qualifier_cannot_be_a_sure_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Jobs(Path(tmp)).profile
            profile.teach('How much experience building customer account dashboards do you have?', 'One year in projects', 1)
            matches = profile.similar('How much professional experience building customer account dashboards do you have?', 'text', [])
            self.assertFalse(any(sure for _, _, _, sure in matches))

    def test_antonyms_cannot_send_affirmative_answers_to_the_model_judge(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Jobs(Path(tmp)).profile
            profile.teach('Are you willing to work night shifts?', 'Yes', 1)
            self.assertEqual(profile.similar('Are you unwilling to work night shifts?', 'text', []), [])
            profile.teach('Do you use AI coding tools in daily work?', 'Yes', 2)
            self.assertEqual(profile.similar('Would you avoid AI coding tools in daily work?', 'text', []), [])


class LifecycleAudit(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.jobs = Jobs(Path(self.tmp.name), FakeChrome())
        await self.jobs.enable(True)

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def waiting(self):
        self.jobs.profile.ask('What is your preferred work arrangement?', [], '181125000123', self.jobs.clock(), waiting=self.jobs.clock()+60)

    async def test_restart_clears_only_orphaned_waiting_state(self):
        self.waiting()
        self.jobs.profile.teach('What is your preferred city?', 'Example City', 1)
        again = Jobs(Path(self.tmp.name))
        self.assertIsNone(again.profile.pending()[0]['waitingUntil'])
        self.assertEqual(again.profile.learned('What is your preferred city?'), 'Example City')
        self.assertEqual(len(again.profile.pending()), 1)

    async def test_stop_commands_are_controls_not_recruiter_answers(self):
        for text in ('stop', 'cancel', 'stop applying', 'do not apply', "don't apply to this job"):
            self.jobs.set_setting('stopped', '0');self.waiting()
            result = answer_chat(text, SimpleNamespace(naukri=self.jobs))
            self.assertIsNone(self.jobs.profile.learned('What is your preferred work arrangement?'), text)
            self.assertEqual(self.jobs.setting('stopped'), '1', text)
            self.assertIn('stop', result['reply'].lower())

    async def test_wait_keeps_waiting_without_teaching_or_entering_it(self):
        self.waiting()
        reply = answer_chat('wait', SimpleNamespace(naukri=self.jobs))
        self.assertIn('waiting', reply['reply'])
        self.assertNotEqual(self.jobs.setting('stopped'), '1')
        self.assertIsNotNone(self.jobs.profile.pending()[0]['waitingUntil'])
        self.assertIsNone(self.jobs.profile.learned('What is your preferred work arrangement?'))

    async def test_revoked_service_does_not_capture_chat_as_an_answer(self):
        self.waiting();await self.jobs.enable(False)
        self.assertIsNone(answer_chat('Hybrid', SimpleNamespace(naukri=self.jobs)))
        self.assertIsNone(self.jobs.profile.learned('What is your preferred work arrangement?'))

    async def test_app_and_device_names_are_valid_answers_but_commands_are_not(self):
        for text in ('GPT and Claude', 'Mac', 'React and Node', 'Open to relocation', 'Yes, open to it'):
            self.waiting()
            self.assertIsNotNone(answer_chat(text, SimpleNamespace(naukri=self.jobs)))
            self.assertEqual(self.jobs.profile.learned('What is your preferred work arrangement?'), text)
        for command in ('open Chrome', 'set a timer for 5 minutes', 'what time is it?'):
            self.waiting()
            self.assertIsNone(answer_chat(command, SimpleNamespace(naukri=self.jobs)))

    async def test_nonmatching_choices_do_not_delete_a_saved_fact(self):
        q = 'Preferred transport?'
        self.jobs.profile.teach(q, 'Train', 1)
        self.jobs.ask_wait, self.jobs.ask_poll = .01, .001
        async def chat(): return {'page':dict(ok=True, open=True, question=q)}
        result, _ = await self.jobs._ask_live(chat, '181125000123', 'Synthetic role', q, 'radio', ['Bus', 'Car'], lambda:False)
        self.assertEqual(result, 'timeout')
        self.assertEqual(self.jobs.profile.learned(q), 'Train')

    async def test_queued_announcements_end_when_the_question_stops_waiting(self):
        q = 'Preferred transport?'
        cancelled = asyncio.Event()
        async def announce(*args):
            try: await asyncio.Event().wait()
            finally: cancelled.set()
        self.jobs.announce = announce
        self.jobs.ask_wait, self.jobs.ask_poll = .01, .001
        async def chat(): return {'page':dict(ok=True, open=True, question=q)}
        await self.jobs._ask_live(chat, '181125000123', 'Synthetic role', q, 'text', [], lambda:False)
        self.assertTrue(cancelled.is_set())
        self.assertTrue(all(task.done() for task in self.jobs._announcing))


class ChatRoutingAudit(unittest.IsolatedAsyncioTestCase):
    async def test_real_chat_pipeline_answers_before_the_app_router(self):
        import httpx
        from unittest.mock import AsyncMock, patch
        from june.chat import validate_chat
        from june.memory import Store
        from june.memory_service import Coordinator, persisted_chat
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);jobs=Jobs(root/'jobs', FakeChrome());await jobs.enable(True)
            store=Store(root/'chat');coordinator=Coordinator()
            settings=SimpleNamespace(model='synthetic-model', ollama='http://unused.invalid')
            daily=SimpleNamespace(plans=SimpleNamespace(naukri=jobs), creations=None,
                **{name:AsyncMock(return_value=None) for name in ('event_chat','agenda_chat','weather_chat','music_chat')})
            async with httpx.AsyncClient() as client:
                for text in ('GPT and Claude','Mac','React and Node'):
                    jobs.profile.ask('Preferred technology?',[], '181125000123', jobs.clock(), waiting=jobs.clock()+60)
                    request={'mode':'local','temporary':True,'knowledge':{'mode':'auto'},'messages':[{'role':'user','content':text}]}
                    mode,messages=validate_chat(request)
                    with patch('june.intent_router.route',AsyncMock(side_effect=AssertionError('Must answer before app routing'))):
                        events=[e async for e in persisted_chat(client,settings,store,coordinator,request,mode,messages,None,daily=daily)]
                    self.assertEqual(jobs.profile.learned('Preferred technology?'),text)
                    self.assertIn('Saved your answer',''.join(e['text'] for e in events if e['type']=='delta'))
