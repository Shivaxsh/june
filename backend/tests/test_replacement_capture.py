"""A spoken pause must retain the instruction arriving during decoding."""
import asyncio
import unittest

from june.realtime_state import VoiceTurn, pause_only


class ReplacementCapture(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events, self.clips = [], []
        self.started, self.release = asyncio.Event(), asyncio.Event()
        self.now = 0.
        self.first, self.second = 'Wait.', 'Keep it short.'

        async def emit(event):
            self.events.append(event)

        async def transcribe(clip):
            self.clips.append(clip)
            if len(self.clips) == 1:
                self.started.set()
                await self.release.wait()
                return {'text': self.first, 'durationMs': 1000}
            return {'text': self.second, 'durationMs': 100}

        self.turn = VoiceTurn(emit, transcribe, pause='short',
                              clock=lambda: self.now, processed_input=True)
        self.turn.number, self.turn.phase = 1, 'speaking'

    async def asyncTearDown(self):
        self.release.set()
        await self.turn.close()

    async def audio(self, voiced, count, sample=b'\x00\x10'):
        for _ in range(count):
            self.now += .02
            await self.turn.audio(sample * 320, voiced)
            await asyncio.sleep(0)

    def transcripts(self):
        return [e['text'] for e in self.events if e['type'] == 'transcript']

    async def begin_pause(self):
        await self.audio(True, 15)
        await self.audio(False, 41)
        await self.started.wait()

    async def test_instruction_during_wait_decode_is_not_discarded(self):
        await self.begin_pause()
        await self.audio(True, 30, b'\x00\x20')
        await self.audio(False, 41)
        self.release.set()
        await self.turn.flush()
        self.assertEqual(self.transcripts(), ['Keep it short.'])
        self.assertIn(b'\x00\x20' * 320, self.clips[-1])
        self.assertEqual(len([e for e in self.events if e['type'] == 'interrupt']), 1)

    async def test_wait_alone_listens_then_expires_without_model_reply(self):
        await self.begin_pause()
        self.release.set()
        await self.turn.flush()
        self.assertEqual(self.transcripts(), [])
        self.assertEqual(self.turn.phase, 'listening')
        self.now += 11
        await self.turn.tick()
        self.assertEqual(self.turn.phase, 'waiting')

    async def test_continued_question_redecodes_whole_audio_before_submission(self):
        self.first, self.second = 'Wait, explain', 'Wait, explain workers instead.'
        await self.begin_pause()
        await self.audio(True, 30, b'\x00\x20')
        await self.audio(False, 41)
        self.release.set()
        await self.turn.flush()
        self.assertEqual(self.transcripts(), [self.second])
        self.assertIn(b'\x00\x10' * 320, self.clips[-1])
        self.assertIn(b'\x00\x20' * 320, self.clips[-1])

    async def test_wait_during_generation_opens_replacement_window(self):
        self.turn.phase = 'generating'
        await self.begin_pause()
        self.release.set()
        await self.turn.flush()
        self.assertEqual(self.transcripts(), [])
        self.assertEqual(self.turn.phase, 'listening')

    async def test_wait_in_followup_window_is_a_control_not_a_question(self):
        self.turn.phase = 'followup'
        await self.audio(True, 30)
        await self.audio(False, 41)
        await self.started.wait()
        self.release.set()
        await self.turn.flush()
        self.assertEqual(self.transcripts(), [])
        self.assertEqual(self.turn.phase, 'listening')

    async def test_generation_replacement_retains_instruction_during_decoding(self):
        self.turn.phase = 'generating'
        self.first, self.second = 'Wait, explain', 'Wait, explain workers instead.'
        await self.begin_pause()
        await self.audio(True, 30, b'\x00\x20')
        await self.audio(False, 41)
        self.release.set()
        await self.turn.flush()
        self.assertEqual(self.transcripts(), [self.second])

    async def test_new_wake_invalidates_pending_replacement(self):
        await self.begin_pause()
        await self.audio(True, 30)
        await self.turn.wake()
        self.release.set()
        await self.turn.flush()
        self.assertEqual(self.transcripts(), [])
        self.assertEqual(self.turn.phase, 'listening')

    async def test_short_instruction_after_wait_needs_no_new_wake(self):
        await self.begin_pause()
        self.release.set()
        await self.turn.flush()
        await self.audio(True, 15)
        await self.audio(False, 41)
        await self.turn.flush()
        self.assertEqual(self.transcripts(), ['Keep it short.'])

    async def test_uncertain_first_clip_retains_pending_instruction(self):
        from june.errors import JuneError
        original = self.turn.transcribe

        async def transcribe(clip):
            result = await original(clip)
            if len(self.clips) == 1:
                raise JuneError('no-speech', 'Please repeat clearly.', 422)
            return result

        self.turn.transcribe = transcribe
        await self.begin_pause()
        await self.audio(True, 30)
        await self.audio(False, 41)
        self.release.set()
        await self.turn.flush()
        self.assertEqual(self.transcripts(), ['Keep it short.'])

    async def test_close_discards_pending_audio_and_late_results(self):
        await self.begin_pause()
        await self.audio(True, 30)
        await self.turn.close()
        self.assertEqual(self.transcripts(), [])
        self.assertEqual(self.turn.pending_question, b'')

    def test_pause_controls_do_not_rewrite_other_words_or_questions(self):
        for text in ('Wait.', 'Wait, wait!', 'Okay, wait.', 'I said wait.',
                     'Stop talking.', 'Hold on.', 'Please wait a second.'):
            self.assertTrue(pause_only(text), text)
        for text in ('Great.', 'What does wait mean?', 'Wait, keep it short.',
                     'Stop explaining workers and explain React.', 'Stop 5060'):
            self.assertFalse(pause_only(text), text)

