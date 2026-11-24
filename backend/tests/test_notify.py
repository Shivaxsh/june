"""Live recruiter questions get the person's attention: voice and notification carry only the question and choices."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch


class Spoken(unittest.TestCase):
    def test_the_sentence_names_the_job_question_and_choices_only(self):
        from june.notify import spoken
        text = spoken('Will you sign a 2 year bond?', ['Yes', 'No', 'Maybe later'], 'Developer at Acme')
        self.assertEqual(text, 'Naukri is asking for Developer at Acme: Will you sign a 2 year bond? The choices are Yes, No or Maybe later. Tell me in June’s chat.')
        self.assertTrue(spoken('Notice period', [], 'X', reminder=True).startswith('Reminder: Naukri is still asking for X: Notice period.'))
        self.assertNotIn('\n', spoken('a\nb', ['c\nd'], 'e\tf'))


class Announcing(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_notification_reaps_its_child_process(self):
        from june.notify import Announcer
        class Process:
            returncode = None
            def __init__(self): self.closed=asyncio.Event();self.killed=False
            async def wait(self): await self.closed.wait()
            def kill(self): self.killed=True;self.returncode=-9;self.closed.set()
        process=Process()
        with patch('june.notify.asyncio.create_subprocess_exec',AsyncMock(return_value=process)):
            task=asyncio.create_task(Announcer._osascript([]))
            await asyncio.sleep(.01);task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(process.killed)

    async def test_incomplete_or_failed_playback_is_not_success_or_blindly_retried(self):
        from june.notify import Announcer
        for events in ([], [{'type':'accepted'}, {'type':'error'}], [{'type':'cancelled'}]):
            calls = []
            class Voice:
                async def speak(self, value):
                    calls.append(value)
                    for event in events: yield event
            self.assertFalse(await Announcer(Voice(), gap=0).speak('Synthetic question'))
            self.assertEqual(len(calls), 1)

    async def test_voice_retries_while_busy_and_notification_passes_text_as_arguments(self):
        from june.errors import JuneError
        from june.notify import Announcer, NOTIFY
        calls, runs = [], []
        class Voice:
            def __init__(self): self.n = 0
            async def speak(self, value):
                self.n += 1; calls.append(value)
                if self.n == 1: raise JuneError('audio-busy', 'busy', 409)
                yield {'type': 'done'}
        async def runner(argv): runs.append(argv)
        voice = Voice()
        announce = Announcer(lambda: voice, runner=runner, gap=0)
        await announce('Will you sign a "bond"? & do shell script "x"', ['Yes', 'No'], 'Developer at Acme')
        self.assertEqual(len(calls), 2, 'retried after the busy attempt')
        self.assertEqual(calls[-1]['voiceId'], 'kokoro-af-heart'); self.assertEqual(calls[-1]['rate'], .98)
        self.assertEqual(runs[0][:len(NOTIFY)], NOTIFY, 'the script itself is fixed')
        self.assertIn('do shell script', runs[0][-1], 'question text travels as an argument, never as script')

    async def test_no_voice_or_a_failing_notifier_never_raises(self):
        from june.notify import Announcer
        async def broken(argv): raise OSError('blocked')
        await Announcer(None, runner=broken, gap=0)('Q?', [], 'Job')


if __name__ == '__main__':
    unittest.main()
