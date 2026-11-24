"""Live-session phrasings that used to fall through to the model or to a refusal."""
import tempfile
import unittest
from pathlib import Path


class TimerPhrasing(unittest.TestCase):
    def test_duration_before_the_word_timer(self):
        from june.timers import timer_intent
        for text, seconds in (('start a 10 second timer', 10), ('set a 5 minute timer', 300), ('Set a ten-minute timer please', 600),
                              ('timer for 2 minutes', 120), ('Okay, set a timer of 90 seconds', 90), ('start a countdown for 3 minutes', 180),
                              ('give me a 1 hour timer', 3600), ('Hey June, 15 minute timer', 900), ('set a timer for 2 minutes', 120)):
            intent = timer_intent(text)
            self.assertEqual((intent or {}).get('operation'), 'create', text)
            self.assertEqual(intent['durationSeconds'], seconds, text)
        for text in ('how much time is left?', 'how long is left on the timer', 'is there a timer running?', 'show my timers'):
            self.assertEqual((timer_intent(text) or {}).get('operation'), 'list', text)
        for text in ('how do I write a timer in python', 'what is a countdown timer', 'the egg timer broke', 'I love this 5 minute timer app idea, explain it'):
            self.assertIsNone(timer_intent(text), text)


class Identity(unittest.TestCase):
    def test_model_questions_are_answered_by_the_app(self):
        from june.app_info import application_reply
        for text in ('what model are you running on', 'which model are you using?', 'what model do you run on', 'what LLM are you', 'what are you running on?',
                     'which AI model powers you'):
            reply = application_reply('qwen3:4b', text, True)
            self.assertIsNotNone(reply, text); self.assertIn('qwen3:4b', reply)
        for text in ('what model should I buy', 'which model is best for coding', 'what is a language model'):
            reply = application_reply('qwen3:4b', text, True)
            self.assertTrue(reply is None or 'running qwen3:4b' not in reply, text)


class Weather(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from june.daily_assistant import DailyAssistant
        self.tmp = tempfile.TemporaryDirectory()
        self.daily = DailyAssistant(Path(self.tmp.name))

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def test_weather_questions_are_recognised(self):
        from june.daily_assistant import weather_intent
        for text in ('what’s the weather like?', "what's the weather today", 'how is the weather outside', 'Hey June, what is the temperature right now?',
                     'how hot is it outside?', 'is it cold outside', 'weather', 'what’s the weather in Kanpur', 'how’s the weather'):
            self.assertIsNotNone(weather_intent(text), text)
        self.assertEqual(weather_intent('what’s the weather in Delhi?'), 'delhi')
        self.assertEqual(weather_intent('what’s the weather like?'), '')
        for text in ('what is weather', 'explain how weather forecasting works', 'write a poem about the weather', 'is it cold in space', 'what is the temperature of the sun'):
            self.assertIsNone(weather_intent(text), text)

    async def test_weather_chat_reports_only_what_the_source_gave(self):
        self.assertIsNone(await self.daily.weather_chat('tell me a joke'))
        off = await self.daily.weather_chat('what’s the weather like?')
        self.assertIn('Systems → Daily', off['reply'])
        async def fake(settings):
            return dict(kind='weather', title='Weather', status='ok', items=[dict(text='Kanpur: 28.4 degrees Celsius.')])
        self.daily._weather = fake
        with self.daily.db() as db:
            import json
            document = json.loads(db.execute('SELECT document FROM settings WHERE id=1').fetchone()[0])
            document['weather']['place'] = dict(name='Kanpur', latitude=26.4, longitude=80.3, timeZone='Asia/Kolkata')
            db.execute('UPDATE settings SET document=? WHERE id=1', (json.dumps(document),))
        self.daily.set_meta('open-meteo', dict(enabled=True, state='connected'))
        self.assertEqual((await self.daily.weather_chat('what’s the weather like?'))['reply'], 'Kanpur: 28.4 degrees Celsius. That is the current temperature; I don’t have a forecast.')
        other = await self.daily.weather_chat('what’s the weather in Delhi?')
        self.assertIn('Kanpur', other['reply']); self.assertIn('only', other['reply']); self.assertNotIn('28.4', other['reply'])


class Inventory(unittest.TestCase):
    def test_more_ways_to_ask_what_is_in_the_library(self):
        from june.library_chat import INVENTORY
        for text in ('what documents do I have?', 'which files do I have', 'what’s in my library?', 'what is in my documents', 'how many documents do I have?',
                     'what files are in my library', 'which documents have I uploaded?', 'show me my files', 'what docs do I have saved'):
            self.assertTrue(INVENTORY.match(text), text)
        for text in ('what documents do I need for a passport?', 'which files should I delete', 'what is a library', 'how many documents does a visa need'):
            self.assertFalse(INVENTORY.match(text), text)


class ReminderPhrasing(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from june.reminders import Reminders
        self.tmp = tempfile.TemporaryDirectory()
        self.reminders = Reminders(Path(self.tmp.name))

    async def asyncTearDown(self):
        close = getattr(self.reminders, 'close', None)
        if close: await close()
        self.tmp.cleanup()

    async def test_cancel_by_name_before_the_word_reminder_and_more_list_wordings(self):
        made = await self.reminders.chat('remind me in 2 hours to drink water', 'chat-rem-0001')
        self.assertIn('Reminder set', made['reply'])
        for text in ('do I have any reminders?', 'what are my reminders', 'any reminders?'):
            self.assertIn('drink water', (await self.reminders.chat(text, 'chat-rem-list'))['reply'], text)
        wrong = await self.reminders.chat('cancel my dentist reminder', 'chat-rem-0002')
        self.assertIn('No matching', wrong['reply'])
        done = await self.reminders.chat('cancel my drink water reminder', 'chat-rem-0003')
        self.assertEqual(done['reply'], 'That reminder is cancelled.')
        self.assertIn('no scheduled reminders', (await self.reminders.chat('what reminders do I have?', 'chat-rem-0004'))['reply'])
        await self.reminders.chat('remind me in 3 hours to stretch', 'chat-rem-0005')
        self.assertEqual((await self.reminders.chat('remove the reminder about stretch', 'chat-rem-0006'))['reply'], 'That reminder is cancelled.')
        self.assertIsNone(await self.reminders.chat('cancel my subscription reminder email draft please', 'chat-rem-0007'))


class Agenda(unittest.IsolatedAsyncioTestCase):
    """"Any reminders or events for today?" is answered from Calendar and June's reminders, not by the model."""
    async def asyncSetUp(self):
        from june.daily_assistant import DailyAssistant
        self.tmp = tempfile.TemporaryDirectory()
        self.daily = DailyAssistant(Path(self.tmp.name), clock=lambda: 1800000000.0)
        self.windows = []
        test = self
        class Native:
            async def permission(self): pass
            async def events(self, start, end):
                test.windows.append((start, end))
                return [dict(title='Dentist', start=start + 61200, allDay=False), dict(title='June Phase 8', start=start, allDay=True)]
        self.daily.calendar = Native()

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def test_agenda_questions_are_recognised(self):
        from june.daily_assistant import agenda_intent
        for text, day, reminders in (
                ('Any reminders or events for today?', 0, True), ('what’s on my calendar?', 0, False), ('What is on my calendar today', 0, False),
                ('do I have any meetings today?', 0, False), ('any events tomorrow?', 1, False), ('what’s my schedule for tomorrow', 1, False),
                ('Hey June, do I have anything today?', 0, True), ('check my calendar', 0, False), ('what do I have today', 0, True),
                ('anything on my calendar today?', 0, False), ('what are my events today', 0, False), ('are there any appointments scheduled today', 0, False),
                ('what events do I have tomorrow?', 1, False), ('what’s tomorrow on my calendar?', 1, False), ('what’s on tomorrow', 1, True),
                ('what’s happening today?', 0, True), ('what is planned for tomorrow', 1, True), ('whats on my calendar tomorrow', 1, False),
                ('what do I have on my calendar tomorrow', 1, False), ('show me tomorrow’s calendar', 1, False)):
            self.assertEqual(agenda_intent(text), (day, reminders), text)
        for text in ('what is a calendar', 'any ideas for today?', 'what events led to world war one', 'do I have any reason to worry', 'add an event today',
                     'what is my schedule for learning python', 'any good movies today?', 'what reminders do I have?', 'what’s today', 'what is tomorrow', 'what’s up', 'what’s on your mind today'):
            self.assertIsNone(agenda_intent(text), text)

    async def test_agenda_chat_reads_calendar_and_reminders(self):
        self.assertIsNone(await self.daily.agenda_chat('tell me a joke'))
        off = await self.daily.agenda_chat('what’s on my calendar?')
        self.assertIn('Systems → Daily', off['reply']); self.assertEqual(self.windows, [])
        self.daily.set_meta('apple-calendar', dict(enabled=True, state='connected'))
        today = await self.daily.agenda_chat('what’s on my calendar?')
        self.assertEqual(today['reply'], 'On your calendar today: All day: June Phase 8. 17:00: Dentist.')
        tomorrow = await self.daily.agenda_chat('any events tomorrow?')
        self.assertTrue(tomorrow['reply'].startswith('On your calendar tomorrow:'))
        self.assertEqual(self.windows[1][0] - self.windows[0][0], 86400)
        class Reminders:
            async def state(self):
                return dict(reminders=[dict(text='drink water', status='active', dueAt=(1800000000 + 3600) * 1000, timeZone='Asia/Kolkata'),
                                       dict(text='old', status='acknowledged', dueAt=1800000000 * 1000, timeZone='Asia/Kolkata'),
                                       dict(text='next week', status='active', dueAt=(1800000000 + 7 * 86400) * 1000, timeZone='Asia/Kolkata')])
        both = await self.daily.agenda_chat('Any reminders or events for today?', Reminders())
        self.assertIn('Dentist', both['reply']); self.assertIn('Reminders today: drink water at', both['reply']); self.assertNotIn('next week', both['reply'])
        class NoReminders:
            async def state(self): return dict(reminders=[])
        self.assertIn('No reminders are scheduled for today.', (await self.daily.agenda_chat('do I have anything today?', NoReminders()))['reply'])

    async def test_today_notice_reads_only_when_allowed(self):
        off = (await self.daily.today())['today']
        self.assertEqual((off['status'], off['items']), ('not-configured', [])); self.assertEqual(self.windows, [])
        self.daily.set_meta('apple-calendar', dict(enabled=True, state='connected'))
        on = (await self.daily.today())['today']
        self.assertEqual(on, dict(date='2027-01-15', status='ok', items=['All day: June Phase 8.', '17:00: Dentist.']))

    def test_the_capability_text_no_longer_denies_calendar_and_reminders(self):
        from june.app_info import CONNECTED_CAPABILITIES
        self.assertNotIn('calendars, reminders', CONNECTED_CAPABILITIES)
        self.assertIn('Calendar', CONNECTED_CAPABILITIES)


class MisheardTimers(unittest.TestCase):
    """Speech recognition in a noisy room turns "a ten second timer" into "it in second timer"."""
    def test_number_sound_alikes_are_repaired_only_inside_a_timer_request(self):
        from june.timers import timer_intent
        for text, seconds in (('Start it in second timer.', 10), ('start a tin second timer', 10), ('set attend minute timer', 600),
                              ('set a timer for to minutes', 120), ('set a timer for too minutes', 120), ('start a for minute timer', 240),
                              ('set a timer for ate seconds', 8), ('start a free minute timer', 180), ('set a timer for fife minutes', 300),
                              ('Set a timer for tin seconds', 10), ('start a won minute timer', 60)):
            intent = timer_intent(text)
            self.assertEqual((intent or {}).get('operation'), 'create', text)
            self.assertEqual(intent['durationSeconds'], seconds, text)
        # A request with no recoverable length asks instead of guessing.
        unclear = timer_intent('start the banana second timer')
        self.assertEqual(unclear['operation'], 'invalid'); self.assertIn('How long', unclear['message'])
        for text in ('it in second', 'to minutes', 'I went to the store for ten minutes'):
            self.assertIsNone(timer_intent(text), text)

    def test_a_bare_length_answers_junes_how_long_question(self):
        from june.timers import timer_followup, TIMER_ASK
        asked = [dict(role='user', content='start the banana second timer'), dict(role='assistant', content=TIMER_ASK)]
        for text, expected in (('ten seconds', 'set a timer for ten seconds'), ('Ten seconds.', 'set a timer for ten seconds'), ('5 minutes please', 'set a timer for 5 minutes'),
                               ('for two minutes', 'set a timer for two minutes'), ('make it 30 seconds', 'set a timer for 30 seconds')):
            self.assertEqual(timer_followup(asked + [dict(role='user', content=text)]), expected, text)
        self.assertIsNone(timer_followup(asked + [dict(role='user', content='never mind')]))
        self.assertIsNone(timer_followup([dict(role='user', content='ten seconds')]))
        self.assertIsNone(timer_followup([dict(role='user', content='hi'), dict(role='assistant', content='Hello!'), dict(role='user', content='ten seconds')]))


class SoundRepair(unittest.IsolatedAsyncioTestCase):
    async def test_the_repair_is_one_fixed_command_authorised_by_macos(self):
        from june import sound_repair
        calls = []
        class Process:
            def __init__(self, code, error=b''): self.returncode, self.error = code, error
            async def communicate(self): return b'', self.error
        outcomes = iter([Process(0), Process(1, b'execution error: User canceled. (-128)'), Process(1, b'other')])
        async def spawn(*argv, **options):
            calls.append(argv); return next(outcomes)
        self.assertEqual(await sound_repair.restart_sound_service(spawn), 'restarted')
        self.assertEqual(await sound_repair.restart_sound_service(spawn), 'cancelled')
        self.assertEqual(await sound_repair.restart_sound_service(spawn), 'failed')
        self.assertEqual(calls[0][:2], ('/usr/bin/osascript', '-e'))
        self.assertIn('/usr/bin/killall coreaudiod', calls[0][2]); self.assertIn('with administrator privileges', calls[0][2])
        self.assertEqual(len({c[2] for c in calls}), 1, 'the command never varies')
        source = (Path(__file__).resolve().parents[1] / 'june/voice_api.py').read_text()
        self.assertIn("!={}", source[source.index("'/repair'"):]); self.assertIn('audio.terminate()', source)
