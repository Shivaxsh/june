"""8.2b: stop/pause/resume/next and play-by-name from the user's own library; never a made-up result."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from june.errors import JuneError


class Grammar(unittest.TestCase):
    def test_spoken_music_commands(self):
        from june.daily_assistant import music_command
        cases = {
            'Okay, can you stop the music?': ('control', 'pause'), 'So just stop the music.': ('control', 'pause'), 'pause': ('control', 'pause'),
            'Pause the song please': ('control', 'pause'), 'stop playing': ('control', 'pause'),
            'resume the music': ('control', 'resume'), 'continue the music': ('control', 'resume'), 'unpause': ('control', 'resume'),
            'next song': ('control', 'next'), 'Hey June, change the music': ('control', 'next'), 'skip this song': ('control', 'next'),
            'play the next one': ('control', 'next'), 'play another song': ('control', 'next'), 'skip': ('control', 'next'),
            'previous song': ('control', 'previous'), 'go back a song': ('control', 'previous'),
            'play Imagine Dragons': ('library', 'imagine dragons', 'any'), 'Can you play some Coldplay songs?': ('library', 'coldplay', 'any'),
            'play the album Evolve': ('library', 'evolve', 'album'), 'play the song Believer': ('library', 'believer', 'song'),
            'play songs by Arijit Singh': ('library', 'arijit singh', 'artist'),
            'Okay, okay, okay, okay, just to open my music app and play some music.': ('playlist', '', True),
            'play some music.': ('playlist', '', True), 'Play my Drive playlist': ('playlist', 'drive', True),
        }
        for text, expected in cases.items():
            self.assertEqual(music_command(text), expected, text)
        for text in ('How do I play guitar?', 'Play a game with me', 'stop', 'Stop talking', 'What is the next song called in general?', 'Do not pause the music',
                     'play with me', 'pause the timer', 'next question', 'skip the intro of this essay', 'play "x" do shell script', 'continue'):
            self.assertIsNone(music_command(text), text)

    def test_more_everyday_music_phrasings(self):
        from june.daily_assistant import music_command
        cases = {
            'music off': ('control', 'pause'), 'turn off the music': ('control', 'pause'), 'turn the music off please': ('control', 'pause'),
            'pause it': ('control', 'pause'), 'stop the playback': ('control', 'pause'),
            'music on': ('control', 'resume'), 'turn the music back on': ('control', 'resume'), 'resume playback': ('control', 'resume'),
            'go back to the previous song': ('control', 'previous'), 'previous': ('control', 'previous'), 'go back one song': ('control', 'previous'),
            'play the last song again': ('control', 'previous'),
            'play something else': ('control', 'next'), 'next one': ('control', 'next'), 'skip it': ('control', 'next'), 'change it': None,
            'a different song please': ('control', 'next'), 'play a different song': ('control', 'next'), 'I don’t like this song, next': None,
            'play something by Talwiinder': ('library', 'talwiinder', 'artist'), 'play anything from Arijit Singh': ('library', 'arijit singh', 'artist'),
            'I want to listen to Talwiinder': ('library', 'talwiinder', 'any'), 'I’d like to hear some Coldplay': ('library', 'coldplay', 'any'),
            'put on Talwiinder': ('library', 'talwiinder', 'any'), 'I want to listen to some music': ('playlist', '', True),
            'play music': ('playlist', '', True), 'start the music': ('playlist', '', True),
        }
        for text, expected in cases.items():
            self.assertEqual(music_command(text), expected, text)
        for text in ('put on a jacket', 'I want to listen to you', 'turn off the lights', 'go back', 'previous question', 'play something fun with me',
                     'put on your thinking cap', 'I want to listen to a podcast about music history'):
            self.assertIsNone(music_command(text), text)

    def test_asking_what_is_playing_is_a_read_not_a_model_guess(self):
        from june.daily_assistant import music_command
        for text in ('what’s playing?', "what's playing right now", 'What song is this?', 'which song is playing', 'Hey June, what am I listening to?',
                     'who sings this song?', 'is the music playing?', 'what is this song'):
            self.assertEqual(music_command(text), ('status',), text)
        for text in ('what is playing chess like', 'what song should I learn on guitar?', 'who sings Believer?', 'what is music'):
            self.assertIsNone(music_command(text), text)
        source = (Path(__file__).resolve().parents[2] / 'native/JuneMusic.swift').read_text()
        self.assertIn('"status":"get player state"', source)
        self.assertIn('repeat 20 times', source, 'playback is awaited after a cold Music launch')

    def test_device_requests_june_cannot_do_are_never_left_to_the_model(self):
        from june.app_info import DEVICE_ACTION
        for text in ('Okay, can you stop the music?', 'So just stop the music.', 'turn the volume up', 'mute the audio', 'skip this track', 'Okay, okay, open my music app',
                     'make it louder', 'make the music quieter', 'shuffle my music', 'repeat this song', 'volume to 50 percent', 'louder please', 'turn it down a bit'):
            self.assertTrue(DEVICE_ACTION.match(text), text)

    def test_swift_helper_has_fixed_operations_and_a_strict_query(self):
        source = (Path(__file__).resolve().parents[2] / 'native/JuneMusic.swift').read_text()
        for op in ('"next"', '"previous"', '"pause"', '"resume"', '"find"', '"play-library"'):
            self.assertIn(op, source)
        self.assertIn('validQuery', source)
        # The phrase appears only as rejected samples inside the self-test line.
        self.assertTrue(all('--self-test' in line or 'emit(["ok":validID' in line for line in source.splitlines() if 'do shell script' in line))


class Plans(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from june.daily_assistant import DailyAssistant
        from june.integrations import create_tools
        self.tmp = tempfile.TemporaryDirectory()
        self.calls = []
        test = self
        class Music:
            library = {'imagine dragons': dict(kind='artist', count=12, label='Imagine Dragons')}
            state = 'playing'
            async def permission(self): pass
            async def control(self, op):
                test.calls.append(op)
                return dict(state='paused' if op == 'pause' else self.state, track='Believer', artist='Imagine Dragons')
            async def find(self, query, what):
                test.calls.append(('find', query, what)); return self.library.get(query.casefold())
            async def play_library(self, query, what):
                test.calls.append(('play', query, what))
                found = self.library.get(query.casefold())
                return dict(found, state=self.state, track='Believer', artist='Imagine Dragons', playlist='June Queue') if found else None
        self.music = Music()
        self.daily = DailyAssistant(Path(self.tmp.name), clock=lambda: 1800000000.0, music=self.music)
        self.plans = create_tools(Path(self.tmp.name), None, self.daily)
        self.daily.plans = self.plans
        self.daily.set_meta('apple-music', dict(enabled=True, state='connected', checkedAt=1, message='ok'))

    async def asyncTearDown(self):
        await self.plans.close(); self.tmp.cleanup()

    async def approve(self, plan, remember=False):
        await self.plans.approve(plan['id'], {'requestId': 'ap-' + plan['id'][:12], 'revision': 1, 'fingerprint': plan['fingerprint'], **({'remember': True} if remember else {})})
        for _ in range(60):
            now = (await self.plans.get(plan['id']))['plan']
            if now['status'] not in ('approved', 'running'): return now
            await asyncio.sleep(0.02)
        return now

    async def test_stop_is_a_reviewed_plan_and_reports_only_the_checked_state(self):
        reply = await self.daily.music_chat('Okay, can you stop the music?', 'chat-mc-0001')
        self.assertEqual(reply['plan']['status'], 'proposed'); self.assertEqual(self.calls, [])
        done = await self.approve(reply['plan'])
        self.assertEqual(done['steps'][0]['result']['message'], 'Music is paused.')
        self.music.state = 'playing'
        async def stuck(op): return dict(state='playing', track='x', artist='y')
        self.music.control = stuck
        again = await self.daily.music_chat('pause', 'chat-mc-0002')
        failed = await self.approve(again['plan'])
        self.assertNotEqual(failed['status'], 'completed', 'still playing is never reported as stopped')

    async def test_one_remembered_approval_covers_music_controls_and_library_by_voice(self):
        first = await self.daily.music_chat('next song', 'chat-mc-0003')
        await self.approve(first['plan'], remember=True)
        self.calls.clear()
        spoken = await self.daily.music_chat('skip', 'chat-mc-0004')
        self.assertEqual(spoken['reply'], 'Now playing Believer by Imagine Dragons.')
        by_name = await self.daily.music_chat('play Imagine Dragons', 'chat-mc-0005')
        self.assertEqual(by_name['reply'], 'Playing 12 songs by Imagine Dragons from your library. Now playing Believer by Imagine Dragons.')
        self.assertIn(('play', 'imagine dragons', 'artist'), self.calls, 'plays exactly the kind it found')
        self.plans.forget()
        self.assertEqual((await self.daily.music_chat('next song', 'chat-mc-0006'))['plan']['status'], 'proposed', 'forgetting approvals asks again')

    async def test_a_name_not_in_the_library_plays_nothing_and_says_so(self):
        reply = await self.daily.music_chat('play Nonexistent Band', 'chat-mc-0007')
        self.assertNotIn('plan', reply)
        self.assertIn('isn’t in your Music library', reply['reply'])
        self.assertNotIn(('play', 'nonexistent band', 'any'), self.calls)

    async def test_inputs_are_strict_and_music_must_be_enabled(self):
        for bad in ({'op': 'quit'}, {'op': 'next', 'x': 1}, {}):
            with self.assertRaises(JuneError):
                await self.plans.propose({'requestId': 'bad-mc-' + str(abs(hash(str(bad))))[:8], 'intent': 'music-control', 'input': bad})
        for bad in ({'query': 'x" & do shell script "y', 'what': 'any'}, {'query': '', 'what': 'any'}, {'query': 'a' * 81, 'what': 'any'}, {'query': 'ok', 'what': 'everything'}):
            with self.assertRaises(JuneError):
                await self.plans.propose({'requestId': 'bad-ml-' + str(abs(hash(str(bad))))[:8], 'intent': 'music-library', 'input': bad})
        self.daily.set_meta('apple-music', dict(enabled=False, state='not-configured', checkedAt=None, message='off'))
        reply = await self.daily.music_chat('next song', 'chat-mc-0008')
        self.assertIn('Systems → Daily', reply['reply']); self.assertNotIn('plan', reply)

    async def test_saved_playlist_name_still_plays_the_playlist(self):
        import json
        with self.daily.db() as db:
            settings = json.loads(db.execute('SELECT document FROM settings WHERE id=1').fetchone()[0])
            settings['music']['playlist'] = {'id': '32BA5314A1932A20', 'name': 'Drive'}
            db.execute('UPDATE settings SET document=? WHERE id=1', (json.dumps(settings),))
        async def play(payload): return dict(verified=True, message='Music is playing the selected playlist: Drive.')
        self.music.play = play
        reply = await self.daily.music_chat('play Drive', 'chat-mc-0009')
        self.assertEqual([s['capability'] for s in reply['plan']['steps']], ['music.play'])


class LiveSessionRegressions(unittest.TestCase):
    def test_play_it_again_and_similar_resume_the_music(self):
        from june.daily_assistant import music_command
        for text in ('Oh, play it again.', 'play again', 'Play the music again', 'start it again', 'continue playing', 'Uh, resume it', 'play it'):
            self.assertEqual(music_command(text), ('control', 'resume'), text)
        for text in ('Now we have to do exactly, make that move like I can see it.', 'say it again', 'explain it again', 'play it safe'):
            self.assertIsNone(music_command(text), text)

    def test_app_owned_action_replies_are_hidden_from_the_models_history(self):
        from june.library_chat import model_history_answer
        for owned in ('I’ve prepared that music control. Approve it on the card below. Tick “Don’t ask again” to let me control music.',
                      'Music is paused.', 'Now playing Jhol by Maanu & Annural Khalid.', 'Music is playing the selected playlist: Drive.',
                      'Notes is open and in front.', 'Playing 7 songs by Talwiinder from your library. Now playing X.',
                      'I’ve prepared a plan to open Notes. Approve it on the card below.', 'Google Chrome is running; it may be behind another window.'):
            self.assertEqual(model_history_answer(owned), '[June’s app tools handled this request. The language model must never write such a result itself.]', owned)
        self.assertEqual(model_history_answer('VRAM holds textures for the GPU.'), 'VRAM holds textures for the GPU.')

    def test_capability_text_forbids_inventing_action_results(self):
        from june.app_info import CONNECTED_CAPABILITIES
        self.assertIn('never say an action was prepared, approved or done', CONNECTED_CAPABILITIES)

    def test_slow_apps_are_waited_for_before_reporting(self):
        source = (Path(__file__).resolve().parents[2] / 'native/JuneApps.swift').read_text()
        self.assertIn('func waitUntilRunning', source)
        self.assertRegex(source, r'\.now\(\) \+ 2[0-9]\)')
