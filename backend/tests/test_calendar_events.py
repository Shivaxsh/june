"""8.2c: June adds a Calendar event only after the person reviews that exact event."""
import asyncio
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from june.errors import JuneError

NOW = 1800000000.0  # Friday 15 January 2027, 13:30 in Asia/Kolkata
ZONE = 'Asia/Kolkata'


def local(stamp):
    return datetime.fromtimestamp(stamp, ZoneInfo(ZONE)).strftime('%Y-%m-%d %H:%M')


class Parsing(unittest.TestCase):
    def parse(self, text):
        from june.calendar_events import event_request
        return event_request(text, NOW, ZONE)

    def test_spoken_requests_become_exact_events(self):
        for text, title, start, end, all_day in (
                ('add an event tomorrow at 5 pm called Dentist', 'Dentist', '2027-01-16 17:00', '2027-01-16 18:00', False),
                ('Hey June, add Dentist to my calendar tomorrow at 5pm', 'Dentist', '2027-01-16 17:00', '2027-01-16 18:00', False),
                ('schedule a meeting with Rahul on Monday at 3 pm', 'Meeting with Rahul', '2027-01-18 15:00', '2027-01-18 16:00', False),
                ('create an event called Team sync today at 4:30 pm for 30 minutes', 'Team sync', '2027-01-15 16:30', '2027-01-15 17:00', False),
                ('add an all-day event tomorrow called Mom’s birthday', 'Mom’s birthday', '2027-01-16 00:00', '2027-01-17 00:00', True),
                ('put lunch with Sam on my calendar on 2027-01-20 at 1 pm', 'Lunch with Sam', '2027-01-20 13:00', '2027-01-20 14:00', False),
                ('Add an event on 20 January at 10 am called Review', 'Review', '2027-01-20 10:00', '2027-01-20 11:00', False),
                ('add an event called Gym at 6 pm', 'Gym', '2027-01-15 18:00', '2027-01-15 19:00', False),
                ('add an event called Standup at 9 am', 'Standup', '2027-01-16 09:00', '2027-01-16 10:00', False),
                ('schedule a call with the bank tomorrow from 2 pm to 2:30 pm', 'Call with the bank', '2027-01-16 14:00', '2027-01-16 14:30', False),
                ('add a meeting at 17:00 tomorrow called Sprint review for 2 hours', 'Sprint review', '2027-01-16 17:00', '2027-01-16 19:00', False),
                ('can you add an appointment with the doctor on January 22nd at 11 am', 'Appointment with the doctor', '2027-01-22 11:00', '2027-01-22 12:00', False)):
            event = self.parse(text)
            self.assertIsNotNone(event, text); self.assertNotIn('ask', event, text)
            self.assertEqual((event['title'], local(event['start']), local(event['end']), event['allDay']), (title, start, end, all_day), text)

    def test_unclear_requests_ask_and_prepare_nothing(self):
        for text, words in (('add an event tomorrow at 5 called Dentist', 'AM or PM'), ('add an event tomorrow called Dentist', 'What time'),
                            ('add an event tomorrow at 5 pm', 'call it'), ('add an event today at 9 am called Early', 'already passed'),
                            ('add an event on 2030-01-01 at 5 pm called Far', 'within a year')):
            event = self.parse(text)
            self.assertIn('ask', event or {}, text); self.assertIn(words, event['ask'], text)

    def test_other_sentences_are_not_event_requests(self):
        for text in ('how do I add an event to Google Calendar?', 'add an event listener to the button', 'remind me tomorrow at 5 pm to call mom',
                     'what is on my calendar', 'add milk to my shopping list', 'make a meeting agenda for Monday', 'do not add an event tomorrow at 5 pm called X',
                     'schedule', 'add two and three', 'create a python script that adds an event to a calendar', 'delete the Dentist event'):
            self.assertIsNone(self.parse(text), text)


class Plans(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from june.daily_assistant import DailyAssistant
        from june.integrations import create_tools
        self.tmp = tempfile.TemporaryDirectory()
        self.daily = DailyAssistant(Path(self.tmp.name), clock=lambda: NOW)
        self.created = []
        test = self
        class Native:
            wrong = False
            async def permission(self): pass
            async def events(self, start, end): return []
            async def create(self, payload):
                test.created.append(payload)
                return dict(title='Other' if self.wrong else payload['title'], start=payload['start'], end=payload['end'], allDay=payload['allDay'], calendar='Home')
        self.native = Native(); self.daily.calendar = self.native
        self.plans = create_tools(Path(self.tmp.name), None, self.daily)
        self.daily.plans = self.plans
        self.event = dict(title='Dentist', start=NOW + 86400, end=NOW + 90000, allDay=False)

    async def asyncTearDown(self):
        await self.plans.close(); self.tmp.cleanup()

    async def settle(self, pid):
        for _ in range(60):
            plan = (await self.plans.get(pid))['plan']
            if plan['status'] not in ('approved', 'running'): return plan
            await asyncio.sleep(0.02)
        return plan

    async def test_calendar_must_be_allowed_and_input_is_validated(self):
        await self.plans.readiness()
        with self.assertRaises(JuneError):
            await self.plans.propose({'requestId': 'req-cal-0001', 'intent': 'calendar-add', 'input': self.event})
        self.daily.set_meta('apple-calendar', dict(enabled=True, state='connected'))
        await self.plans.readiness()
        for bad in ({**self.event, 'title': ''}, {**self.event, 'title': 'x\x00y'}, {**self.event, 'start': NOW - 4000}, {**self.event, 'end': self.event['start']},
                    {**self.event, 'end': self.event['start'] + 9 * 86400}, {**self.event, 'calendar': 'Work'}, {'title': 'Dentist'}, {**self.event, 'allDay': 'no'},
                    {**self.event, 'start': NOW + 400 * 86400, 'end': NOW + 400 * 86400 + 3600}):
            with self.assertRaises(JuneError, msg=str(bad)):
                await self.plans.propose({'requestId': 'req-cal-bad' + str(abs(hash(str(bad))))[:6], 'intent': 'calendar-add', 'input': bad})
        self.assertEqual(self.created, [])

    async def test_each_event_is_reviewed_and_never_remembered(self):
        self.daily.set_meta('apple-calendar', dict(enabled=True, state='connected'))
        await self.plans.readiness()
        plan = (await self.plans.propose({'requestId': 'req-cal-0002', 'intent': 'calendar-add', 'input': self.event}))['plan']
        self.assertEqual(plan['status'], 'proposed'); self.assertEqual(self.created, [])
        step = plan['steps'][0]
        self.assertIn('Dentist', step['preview']); self.assertIn('16 Jan 2027', step['preview']); self.assertIn('1:30 PM', step['preview'])
        self.assertFalse(self.plans.capabilities['calendar.add'].public()['rememberable'])
        with self.assertRaises(JuneError, msg='an event approval can never be remembered'):
            await self.plans.approve(plan['id'], {'requestId': 'req-cal-0003', 'revision': 1, 'fingerprint': plan['fingerprint'], 'remember': True})
        await self.plans.approve(plan['id'], {'requestId': 'req-cal-0007', 'revision': 1, 'fingerprint': plan['fingerprint']})
        done = await self.settle(plan['id'])
        self.assertEqual(done['status'], 'completed'); self.assertEqual(len(self.created), 1)
        self.assertIn('Added “Dentist” to your Home calendar', done['steps'][0]['result']['message'])
        again = (await self.plans.propose({'requestId': 'req-cal-0004', 'intent': 'calendar-add', 'input': self.event}))['plan']
        self.assertEqual(again['status'], 'proposed', 'the same event still needs a new review')

    async def test_a_mismatched_read_back_is_not_reported_as_added(self):
        self.daily.set_meta('apple-calendar', dict(enabled=True, state='connected'))
        await self.plans.readiness()
        self.native.wrong = True
        plan = (await self.plans.propose({'requestId': 'req-cal-0005', 'intent': 'calendar-add', 'input': self.event}))['plan']
        await self.plans.approve(plan['id'], {'requestId': 'req-cal-0006', 'revision': 1, 'fingerprint': plan['fingerprint']})
        done = await self.settle(plan['id'])
        self.assertNotEqual(done['status'], 'completed'); self.assertIn('could not confirm', done['steps'][0]['result']['message'])

    async def test_a_lost_macos_permission_is_reported_and_lets_the_person_allow_again(self):
        self.daily.set_meta('apple-calendar', dict(enabled=True, state='connected'))
        await self.plans.readiness()
        async def denied(*args):
            raise JuneError('calendar-permission', 'Allow June Calendar in System Settings.', 403)
        self.native.create = denied; self.native.events = denied
        plan = (await self.plans.propose({'requestId': 'req-cal-0010', 'intent': 'calendar-add', 'input': self.event}))['plan']
        await self.plans.approve(plan['id'], {'requestId': 'req-cal-0011', 'revision': 1, 'fingerprint': plan['fingerprint']})
        done = await self.settle(plan['id'])
        self.assertEqual(done['status'], 'failed', 'a refused add is a clear failure, not an unknown outcome')
        self.assertIn('nothing was added', done['steps'][0]['result']['message']); self.assertIn('Allow June to read Calendar', done['steps'][0]['result']['message'])
        self.assertFalse(self.daily.enabled('apple-calendar'), 'Daily offers Allow again instead of showing it as connected')
        self.daily.set_meta('apple-calendar', dict(enabled=True, state='connected'))
        reply = await self.daily.agenda_chat('what’s on my calendar?')
        self.assertIn('Allow', reply['reply']); self.assertFalse(self.daily.enabled('apple-calendar'))
        self.assertEqual((await self.daily.today())['today']['status'], 'not-configured')

    async def test_chat_prepares_a_card_or_asks(self):
        self.assertIsNone(await self.daily.event_chat('tell me a joke', 'chat-cal-0001'))
        off = await self.daily.event_chat('add an event tomorrow at 5 pm called Dentist', 'chat-cal-0002')
        self.assertIn('Systems → Daily', off['reply']); self.assertNotIn('plan', off)
        self.daily.set_meta('apple-calendar', dict(enabled=True, state='connected'))
        ask = await self.daily.event_chat('add an event tomorrow at 5 called Dentist', 'chat-cal-0003')
        self.assertIn('AM or PM', ask['reply']); self.assertNotIn('plan', ask)
        ready = await self.daily.event_chat('add an event tomorrow at 5 pm called Dentist', 'chat-cal-0004')
        self.assertEqual(ready['plan']['status'], 'proposed')
        self.assertIn('Dentist', ready['reply']); self.assertIn('Sat 16 Jan', ready['reply']); self.assertIn('5:00 PM', ready['reply']); self.assertIn('card', ready['reply'])
        self.assertEqual(self.created, [])


class Helper(unittest.TestCase):
    def test_swift_helper_only_creates_and_reads_back(self):
        source = (Path(__file__).resolve().parents[2] / 'native/JuneCalendar.swift').read_text()
        self.assertIn('"create"', source); self.assertIn('defaultCalendarForNewEvents', source); self.assertIn('event(withIdentifier', source)
        for forbidden in ('store.remove(', 'removeCalendar', 'Process(', 'NSAppleScript'):
            self.assertNotIn(forbidden, source)
        plist = (Path(__file__).resolve().parents[2] / 'native/JuneCalendar-Info.plist').read_text()
        self.assertIn('adds events you approve', plist); self.assertNotIn('never adds', plist.lower())

    def test_python_wrapper_validates_the_read_back(self):
        from june.calendar_tools import CalendarNative
        native = CalendarNative('/nonexistent')
        async def call(value, timeout):
            return dict(ok=True, title='Dentist', start=value['start'], end=value['end'], allDay=False, calendar='Home')
        native._call = call
        result = asyncio.run(native.create(dict(title='Dentist', start=NOW + 3600, end=NOW + 7200, allDay=False)))
        self.assertEqual(result['calendar'], 'Home')
        async def bad(value, timeout):
            return dict(ok=True, title=5)
        native._call = bad
        with self.assertRaises(JuneError):
            asyncio.run(native.create(dict(title='Dentist', start=NOW + 3600, end=NOW + 7200, allDay=False)))
