import tempfile
import unittest
from pathlib import Path
from june.errors import JuneError


class DailyAssistant(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from june.daily_assistant import DailyAssistant
        self.tmp = tempfile.TemporaryDirectory()
        self.now = [1800000000.0]
        self.daily = DailyAssistant(Path(self.tmp.name), clock=lambda: self.now[0])

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_defaults_make_no_network_or_music_requests(self):
        settings = self.daily.settings()['settings']
        self.assertIsNone(settings['weather']['place'])
        self.assertIsNone(settings['music']['playlist'])
        result = (await self.daily.briefing())['briefing']
        self.assertEqual([s['status'] for s in result['sections']], ['not-configured', 'not-configured', 'ok'])
        self.assertIn('No active goals', result['spoken'])

    async def test_goals_are_revision_bound_and_request_idempotent(self):
        request = {'requestId':'goal-request1','text':'Finish June'}
        first = self.daily.goal_create(request)['goal']
        self.assertEqual(self.daily.goal_create(request)['goal'], first)
        with self.assertRaises(JuneError):
            self.daily.goal_create({**request,'text':'different'})
        done = self.daily.goal_change(first['id'], 'complete', {'requestId':'goal-complete','revision':1})['goal']
        self.assertEqual(done['status'], 'done')
        self.assertEqual(done['revision'], 2)
        with self.assertRaises(JuneError):
            self.daily.goal_change(first['id'], 'update', {'requestId':'goal-edit000','revision':1,'text':'Changed'})

    async def test_invalid_goals_and_active_limit(self):
        for text in ('', 'x'*201, 'hello\x00world'):
            with self.assertRaises(JuneError):
                self.daily.goal_create({'requestId':'goal-invalid','text':text})
        for i in range(20):
            self.daily.goal_create({'requestId':f'goal-{i:08d}','text':f'Goal {i}'})
        with self.assertRaises(JuneError):
            self.daily.goal_create({'requestId':'goal-extra01','text':'Extra'})

    async def test_goal_delete_is_not_shown_and_reopen_respects_capacity(self):
        goal = self.daily.goal_create({'requestId':'goal-create1','text':'Temporary'})['goal']
        self.assertTrue(self.daily.goal_change(goal['id'], 'delete', {'requestId':'goal-delete1','revision':1})['deleted'])
        self.assertEqual(self.daily.goals()['goals'], [])

    async def test_weather_requires_consent_and_city_from_search(self):
        with self.assertRaises(JuneError):
            await self.daily.places({'requestId':'places-query','query':'Noida'})
        revision = self.daily.settings()['settings']['revision']
        with self.assertRaises(JuneError):
            await self.daily.settings_update({'requestId':'settings-001','revision':revision,'weather':{'placeId':'invented'}})

    async def test_city_selection_weather_numeric_facts_and_disable(self):
        from unittest.mock import AsyncMock
        await self.daily.enable('open-meteo', True, {'requestId':'enable-weather'})
        self.daily.weather_http.json = AsyncMock(return_value={'results':[{'id':1,'name':'Noida','admin1':'Uttar Pradesh','country':'India','latitude':28.58,'longitude':77.33,'timezone':'Asia/Kolkata'}]})
        places = (await self.daily.places({'requestId':'places-query','query':'Noida'}))['places']
        await self.daily.settings_update({'requestId':'settings-001','revision':1,'weather':{'placeId':places[0]['id']}})
        self.daily.weather_http.json = AsyncMock(return_value={'current':{'temperature_2m':27.5,'weather_code':0},'current_units':{'temperature_2m':'°C'}})
        brief = (await self.daily.briefing())['briefing']
        self.assertIn('27.5', brief['sections'][0]['items'][0]['text'])
        self.assertIn('Noida', brief['spoken'])
        self.assertEqual(self.daily.connection('open-meteo')['state'], 'connected')
        await self.daily.enable('open-meteo', False, {'requestId':'disable-weather'})
        self.assertFalse(self.daily.connection('open-meteo')['enabled'])
        self.assertIn('api.open-meteo.com',self.daily.connection('open-meteo')['hosts'])
        brief = (await self.daily.briefing())['briefing']
        self.assertEqual(brief['sections'][0]['status'], 'not-configured')

    async def test_settings_stale_and_unknown_fields_rejected(self):
        good = {'requestId':'settings-001','revision':1,'briefing':{'sections':['goals']}}
        self.assertEqual((await self.daily.settings_update(good))['settings']['revision'], 2)
        self.assertEqual((await self.daily.settings_update(good))['settings']['revision'], 2)
        for value in ({'requestId':'settings-002','revision':1,'briefing':{'sections':['goals']}},
                      {'requestId':'settings-002','revision':2,'shell':'oops'},
                      {'requestId':'settings-002','revision':2,'briefing':{'sections':['mail']}}):
            with self.assertRaises(JuneError):
                await self.daily.settings_update(value)

    async def test_remote_failure_is_named_and_not_persisted(self):
        from unittest.mock import AsyncMock
        self.daily.set_meta('google', {'state':'connected','checkedAt':1})
        self.daily.google = type('Google', (), {'events':AsyncMock(side_effect=JuneError('bad','private-mail-content',502))})()
        result = (await self.daily.briefing())['briefing']
        self.assertEqual(result['sections'][1]['status'], 'unavailable')
        self.assertNotIn('private-mail-content', result['spoken'])
        self.assertNotIn(b'private-mail-content', self.daily.path.read_bytes())

    async def test_briefing_intent_is_literal_not_quoted_or_negative(self):
        from june.daily_assistant import briefing_intent
        for text in ('Good morning', 'June, brief me.', 'Give me my morning briefing'):
            self.assertTrue(briefing_intent(text))
        for text in ('Do not brief me', 'Translate "Good morning"', 'What does good morning mean?', 'Good morning, delete my files'):
            self.assertFalse(briefing_intent(text))

    async def test_private_chat_briefing_is_delivered_without_persisting_fetched_details(self):
        from unittest.mock import AsyncMock,patch
        from june.config import Settings
        from june.memory import Store
        from june.memory_service import Coordinator,persisted_chat
        store=Store(Path(self.tmp.name));cid=store.create_conversation()['id']
        self.daily.briefing=AsyncMock(return_value={'briefing':{'spoken':'Private calendar workshop at 10:15.'}})
        value={'knowledge':{'mode':'auto'},'conversationId':cid,'turnId':'daily-briefing'}
        with patch('june.library_chat.stream_chat',side_effect=AssertionError('No inference for briefing')):
            events=[e async for e in persisted_chat(None,Settings.from_env(),store,Coordinator(),value,'local',[{'role':'user','content':'Good morning'}],daily=self.daily)]
        self.assertIn('Private calendar workshop',''.join(e.get('text','') for e in events))
        self.assertNotIn('Private calendar workshop',str(store.conversation(cid)))

    async def test_replayed_music_enable_does_not_request_permission_again(self):
        from unittest.mock import AsyncMock
        self.daily.music=type('Music',(),{'permission':AsyncMock()})()
        value={'requestId':'music-enable1'}
        await self.daily.enable('apple-music',True,value)
        await self.daily.enable('apple-music',True,value)
        self.daily.music.permission.assert_awaited_once()


class MusicChat(unittest.IsolatedAsyncioTestCase):
    """Live failure: hands-free "Can you play the music?" got an outdated 'music isn't connected' reply."""
    async def asyncSetUp(self):
        from june.daily_assistant import DailyAssistant
        self.tmp = tempfile.TemporaryDirectory()
        self.daily = DailyAssistant(Path(self.tmp.name), clock=lambda: 1800000000.0)
        self.proposed = []
        daily = self.daily
        class Plans:
            async def readiness(self): pass
            async def propose(inner, value):
                self.proposed.append(value)
                return {'serverNow': 1, 'plan': {'id': 'plan-0000001', 'status': self.status, 'steps': [{'status': 'completed', 'result': {'message': 'Music is playing the selected playlist: Drive.', 'verified': True, 'at': 1}}]}}
            async def get(inner, pid):
                return await inner.propose({'requestId': 'poll'})
        self.status = 'proposed'
        daily.plans = Plans()

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def setup_music(self):
        self.daily.music = object()  # a ready helper; playback itself goes through the plan
        self.daily.set_meta('apple-music', dict(enabled=True, state='connected', checkedAt=1, message='ok'))
        with self.daily.db() as db:
            import json
            settings = json.loads(db.execute('SELECT document FROM settings WHERE id=1').fetchone()[0])
            settings['music']['playlist'] = {'id': '32BA5314A1932A20', 'name': 'Drive'}
            db.execute('UPDATE settings SET document=? WHERE id=1', (json.dumps(settings),))

    def test_music_intent_is_specific(self):
        from june.daily_assistant import music_intent
        for text in ('Can you play the music?', 'Play my Drive playlist', 'Can you play my drive playlist from Music?', 'Hey June, play some music please',
                     'play my focus playlist', 'Play Drive', 'Start my playlist', 'Put on some music'):
            self.assertIsNotNone(music_intent(text), text)
        for text in ('How do I play guitar?', 'What music do you like?', 'Play a game with me', 'Can you explain playlist algorithms?', 'Do not play music'):
            self.assertIsNone(music_intent(text), text)
        self.assertEqual(music_intent('Play my Drive playlist'), 'drive')
        self.assertEqual(music_intent('Can you play the music?'), '')

    async def test_not_set_up_gives_guidance_and_proposes_nothing(self):
        reply = await self.daily.music_chat('Can you play the music?', 'chat-req-0001')
        self.assertIn('Systems → Daily', reply['reply'])
        self.assertNotIn('plan', reply)
        self.assertEqual(self.proposed, [])

    async def test_saved_playlist_is_proposed_as_a_reviewed_plan(self):
        self.setup_music()
        reply = await self.daily.music_chat('Can you play my Drive playlist?', 'chat-req-0002')
        self.assertEqual(self.proposed, [{'requestId': 'chat-req-0002', 'intent': 'play-playlist'}])
        self.assertEqual(reply['plan']['id'], 'plan-0000001')
        self.assertIn('approve', reply['reply'].lower())

    async def test_remembered_plan_runs_and_reports_the_checked_result(self):
        self.setup_music(); self.status = 'completed'
        reply = await self.daily.music_chat('Play my music', 'chat-req-0003')
        self.assertEqual(reply['reply'], 'Music is playing the selected playlist: Drive.')

    async def test_another_named_playlist_is_never_substituted(self):
        self.setup_music()
        reply = await self.daily.music_chat('Play my Workout playlist', 'chat-req-0004')
        self.assertEqual(self.proposed, [])
        self.assertIn('Drive', reply['reply']); self.assertIn('Workout', reply['reply'])

    def test_capability_text_no_longer_denies_music(self):
        from june.app_info import CONNECTED_CAPABILITIES, NOT_CONNECTED
        self.assertIn('Apple Music playlist', CONNECTED_CAPABILITIES)
        self.assertNotIn('music', NOT_CONNECTED.lower())


class AppleCalendar(unittest.IsolatedAsyncioTestCase):
    """The user chose the Mac's built-in Calendar instead of Google."""
    async def asyncSetUp(self):
        from june.daily_assistant import DailyAssistant
        self.tmp = tempfile.TemporaryDirectory()
        self.daily = DailyAssistant(Path(self.tmp.name), clock=lambda: 1800000000.0)
        self.calls = []
        test = self
        class Native:
            denied = False
            async def permission(self):
                test.calls.append('permission')
                if self.denied: raise JuneError('calendar-permission', 'Allow June Calendar in Privacy & Security → Calendars.', 403)
            async def events(self, start, end):
                test.calls.append(('events', start, end))
                return [dict(title='Dentist', start=1800003600.0, allDay=False), dict(title='Pay rent', start=1799990000.0, allDay=True),
                        dict(title='bad\x00title', start=1800007200.0, allDay=False)]
        self.native = Native(); self.daily.calendar = self.native

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_enable_asks_permission_once_and_reads_nothing_until_briefing(self):
        value = {'requestId': 'cal-enable-01'}
        connection = (await self.daily.enable('apple-calendar', True, value))['connection']
        self.assertEqual((connection['state'], connection['enabled'], connection['hosts']), ('connected', True, []))
        await self.daily.enable('apple-calendar', True, value)
        self.assertEqual(self.calls, ['permission'], 'a replayed enable does not ask again, and no events are read')

    async def test_denied_permission_is_an_error_and_stays_disabled(self):
        self.native.denied = True
        with self.assertRaises(JuneError) as caught:
            await self.daily.enable('apple-calendar', True, {'requestId': 'cal-enable-02'})
        self.assertEqual(caught.exception.code, 'calendar-permission')
        self.assertFalse(self.daily.enabled('apple-calendar'))

    async def test_briefing_reads_today_in_the_local_zone_with_app_built_text(self):
        await self.daily.enable('apple-calendar', True, {'requestId': 'cal-enable-03'})
        section = next(s for s in (await self.daily.briefing())['briefing']['sections'] if s['kind'] == 'calendar')
        self.assertEqual(section['status'], 'ok')
        texts = [i['text'] for i in section['items']]
        self.assertEqual(texts[0], 'All day: Pay rent.')
        self.assertRegex(texts[1], r'^\d\d:\d\d: Dentist\.$')
        self.assertEqual(len(texts), 2, 'an unsafe title is dropped, never shown')
        _, start, end = self.calls[-1]
        self.assertEqual(end - start, 86400)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        self.assertEqual(datetime.fromtimestamp(start, ZoneInfo('Asia/Kolkata')).strftime('%H:%M'), '00:00')

    async def test_disable_stops_reads_and_briefing_says_not_set_up(self):
        await self.daily.enable('apple-calendar', True, {'requestId': 'cal-enable-04'})
        await self.daily.enable('apple-calendar', False, {'requestId': 'cal-disable-04'})
        self.calls.clear()
        section = next(s for s in (await self.daily.briefing())['briefing']['sections'] if s['kind'] == 'calendar')
        self.assertEqual(section['status'], 'not-configured')
        self.assertIn('Calendar', section['message'])
        self.assertEqual(self.calls, [])

    async def test_revoked_permission_is_named_not_shown_as_no_events(self):
        await self.daily.enable('apple-calendar', True, {'requestId': 'cal-enable-05'})
        async def refused(start, end): raise JuneError('calendar-permission', 'Allow June Calendar.', 403)
        self.native.events = refused
        section = next(s for s in (await self.daily.briefing())['briefing']['sections'] if s['kind'] == 'calendar')
        self.assertEqual(section['status'], 'unavailable')

    def test_native_helper_is_read_only_signed_and_self_responsible(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / 'native/JuneCalendar.swift').read_text()
        self.assertIn('requestFullAccessToEvents', source)
        self.assertIn('responsibility_spawnattrs_setdisclaim', source)
        # 8.2c: the helper may add one approved event. It still never removes or edits anything.
        self.assertEqual(source.count('.save('), 1)
        for forbidden in ('.remove(', 'EKReminder', 'removeCalendar', 'saveCalendar'):
            self.assertNotIn(forbidden, source)
        script = (root / 'scripts/calendar.mjs').read_text()
        self.assertRegex(script, r"codesign',\[[^\]]*'--identifier','local\.june\.calendar'")
        self.assertIn('NSCalendarsFullAccessUsageDescription', (root / 'native/JuneCalendar-Info.plist').read_text())
