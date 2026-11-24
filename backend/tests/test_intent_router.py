"""Requests about June's tools that the fixed grammars miss are translated, never improvised."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class Gate(unittest.TestCase):
    def test_only_short_direct_requests_about_junes_tools_are_routed(self):
        from june.intent_router import routable
        for text in ('what’s tomorrow on my calendar?', 'could you get some tunes going, play music', 'is there anything on my schedule later today',
                     'I wanna hear some music', 'give me the temperature outside', 'start the music up for me', 'which files have you got of mine',
                     'tell me my reminders for today', 'can you kill the timer'):
            self.assertTrue(routable(text), text)
        for text in ('how do I add an event to Google Calendar?', 'explain how weather forecasting works', 'write a poem about music', 'what is a calendar',
                     'don’t play music', 'tell me a joke', 'what is the capital of France', 'open "Safari"', 'write python code to play a song',
                     'what role did music play in the history of India', 'x' * 200 + ' play music', 'why is my calendar empty'):
            self.assertFalse(routable(text), text)


class Commands(unittest.TestCase):
    def test_june_builds_the_command_and_refuses_names_the_person_did_not_say(self):
        from june.intent_router import command
        text = 'could you get Figma going for me and play Talwiinder'
        self.assertEqual(command({'intent': 'open_app', 'name': 'Figma'}, text), 'open Figma')
        self.assertEqual(command({'intent': 'play_named', 'name': 'talwiinder'}, text), 'play talwiinder')
        self.assertEqual(command({'intent': 'calendar_tomorrow', 'name': 'ignored'}, text), 'what’s on my calendar tomorrow')
        self.assertEqual(command({'intent': 'set_timer', 'name': 'ten minutes'}, 'give me ten minutes on the clock, a timer'), 'set a timer for ten minutes')
        for bad in ({'intent': 'open_app', 'name': 'Terminal'}, {'intent': 'play_named', 'name': 'Imagine Dragons'}, {'intent': 'open_app', 'name': ''},
                    {'intent': 'none', 'name': ''}, {'intent': 'run_shell', 'name': 'rm -rf'}, {'intent': 'set_timer', 'name': '5 hours'}, {'intent': 'open_app'},
                    {'intent': 'open_app', 'name': 'Figma; rm -rf ~'}, 'open Figma', None):
            self.assertIsNone(command(bad, text), str(bad))


class Route(unittest.IsolatedAsyncioTestCase):
    async def test_route_asks_once_and_survives_any_model_failure(self):
        from june import intent_router
        settings = SimpleNamespace(ollama='http://127.0.0.1:1', model='fixture')
        calls = []
        async def reply(client, url, payload, limit, timeout):
            calls.append(payload)
            return {'message': {'content': json.dumps({'intent': 'calendar_tomorrow', 'name': ''})}}
        with patch('june.intent_router.bounded_json', reply):
            self.assertEqual(await intent_router.route(None, settings, 'what have I got going on tomorrow in my calendar'), 'what’s on my calendar tomorrow')
            self.assertIsNone(await intent_router.route(None, settings, 'tell me a joke'), 'not routable: no model call')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['format']['properties']['step1_intent']['enum'][0], 'none'); self.assertEqual(calls[0]['options']['temperature'], 0)
        self.assertEqual(calls[0]['options']['num_ctx'], 4096, 'a different context size reloads the model')
        async def broken(*args):
            raise RuntimeError('model offline')
        async def garbage(*args):
            return {'message': {'content': 'open the pod bay doors'}}
        for fake in (broken, garbage):
            with patch('june.intent_router.bounded_json', fake):
                self.assertIsNone(await intent_router.route(None, settings, 'what’s tomorrow on my calendar?'))

    def test_every_standard_command_is_understood_by_junes_own_grammars(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent))
        from corpus_support import understood
        from june.intent_router import _FIXED, command
        for intent, text in _FIXED.items():
            self.assertTrue(understood(text), intent)
        said = ('make me a simple coffee shop website with dark aesthetics and 5 sections, remind me tomorrow at 5 pm to call mom, add Dentist tomorrow at 5 pm, '
                'keep it awake 2 hours, port 3000, push June with message fix login, run lint, stop the dev server, presentation on jazz with 6 slides')
        for answer, expected in (
                (dict(step1_intent='create_document', step2_kind='website', step3_name='simple coffee shop', step4_detail='dark aesthetics', step5_number='5'),
                 'make a website about simple coffee shop with 5 sections in a dark style'),
                (dict(step1_intent='create_document', step2_kind='presentation', step3_name='jazz', step4_detail='', step5_number='6'), 'make a presentation about jazz with 6 slides'),
                (dict(step1_intent='create_document', step2_kind='presentation', step3_name='presentation on jazz'), 'make a presentation about jazz'),
                (dict(step1_intent='restyle', step4_detail='dark'), 'redo it in dark'), (dict(step1_intent='restyle'), 'make it in a different style'),
                (dict(step1_intent='set_reminder', step3_name='call mom', step4_detail='tomorrow at 5 pm'), 'remind me tomorrow at 5 pm to call mom'),
                (dict(step1_intent='add_event', step3_name='Dentist', step4_detail='tomorrow at 5 pm'), 'add an event tomorrow at 5 pm called Dentist'),
                (dict(step1_intent='keep_awake', step5_number='2'), 'keep my mac awake for 2 hours'), (dict(step1_intent='free_port', step5_number='3000'), 'free port 3000'),
                (dict(step1_intent='project_push', step3_name='June', step4_detail='fix login'), 'commit and push June with the message fix login'),
                (dict(step1_intent='run_saved_command', step3_name='lint'), 'run lint'), (dict(step1_intent='stop_command', step3_name='dev server'), 'stop the dev server')):
            built = command(answer, said)
            self.assertEqual(built, expected, answer)
            self.assertTrue(understood(built), built)
        self.assertIsNone(command(dict(step1_intent='open_creation'), 'I love the website'), 'opening needs the person to ask to open or see it')
        self.assertIsNone(command(dict(step1_intent='publish_site'), 'that website is great'))
        self.assertEqual(command(dict(step1_intent='open_creation'), 'let me see the site'), 'open it')
        for bad in (dict(step1_intent='create_document', step2_kind='none', step3_name='coffee shop'), dict(step1_intent='create_document', step2_kind='website', step3_name='a bakery'),
                    dict(step1_intent='free_port', step5_number='8080'), dict(step1_intent='set_reminder', step3_name='call mom'),
                    dict(step1_intent='run_saved_command', step3_name='rm -rf'), dict(step1_intent='add_event', step3_name='Dentist', step4_detail='friday')):
            self.assertIsNone(command(bad, said), bad)
        from june.app_actions import app_request
        self.assertEqual(app_request('open Figma'), (['figma'], []))
        from june.timers import timer_intent
        self.assertEqual(timer_intent('set a timer for ten minutes')['operation'], 'create')


class SecondChance(unittest.TestCase):
    def test_a_wrong_refusal_becomes_a_clear_hint(self):
        from june.intent_router import wrong_refusal
        for question, opening, words in (
                ('make me a simple coffee shop website with dark aesthetics', 'I can’t create or send a website directly, but I can draft the content', 'make a website about'),
                ('Make me a cute love letter website for a girl name Kuchupu', 'I can\'t create a website for you. That would require building', 'make a website about'),
                ('can you put my dentist appointment in the calendar for friday', 'Sorry, I cannot add events to your calendar.', 'add an event tomorrow'),
                ('play something by coldplay', 'I’m unable to play music.', 'play Imagine Dragons'),
                ('make it look less boring', 'I don\'t have the ability to change the design.', 'different style'),
                ('send my application to that company', "I can't apply to jobs for you. That action requires logging into Naukri", 'apply to the top 3')):
            hint = wrong_refusal(question, opening)
            self.assertIsNotNone(hint, question); self.assertIn(words, hint, question); self.assertIn('didn’t catch it as a request', hint)

    def test_honest_answers_and_unrelated_refusals_are_left_alone(self):
        from june.intent_router import wrong_refusal
        for question, opening in (
                ('make me a simple coffee shop website', 'Here is a simple plan for your coffee shop website.'),
                ('how do I make a website?', 'I can’t build it with you live, but here are the steps.'),
                ('tell me a joke', 'I can’t think of a good one right now.'),
                ('what is the weather like on Mars', 'I can’t check live conditions on Mars, but it is very cold.'),
                ('open the pod bay doors', 'I’m sorry, Dave. I’m afraid I can’t do that.')):
            self.assertIsNone(wrong_refusal(question, opening), question)


class SecondChanceInChat(unittest.IsolatedAsyncioTestCase):
    async def test_a_streamed_wrong_refusal_is_never_shown(self):
        import tempfile
        from pathlib import Path
        from june.config import Settings
        from june.memory import Store
        from june.memory_service import Coordinator, persisted_chat
        async def refusing(*args, **kwargs):
            for part in ('I can’t create', ' or send a website directly', ', but I can draft. ', 'Here is a plan.'):
                yield {'type': 'delta', 'text': part}
            yield {'type': 'done', 'model': 'fixture'}
        async def helpful(*args, **kwargs):
            for part in ('Here is', ' a plan for your bakery. ', 'Start with a menu.'):
                yield {'type': 'delta', 'text': part}
            yield {'type': 'done', 'model': 'fixture'}
        async def no_route(*args, **kwargs):
            return None
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            for fake, question, shown, hidden in ((refusing, 'make me a coffee shop website with a gloomy vibe', 'make a website about', 'I can’t create'),
                                                   (helpful, 'help me plan a bakery website', 'Here is a plan for your bakery.', 'didn’t catch')):
                with patch('june.library_chat.stream_chat', fake), patch('june.intent_router.route', no_route):
                    events = [e async for e in persisted_chat(None, Settings.from_env(), store, Coordinator(), {'knowledge': {'mode': 'auto'}}, 'local',
                                                              [{'role': 'user', 'content': question}])]
                text = ''.join(e.get('text', '') for e in events if e.get('type') == 'delta')
                self.assertIn(shown, text, question); self.assertNotIn(hidden, text, question)
