import asyncio
import unittest
from june.realtime_state import VoiceTurn

class NativeTurnTests(unittest.IsolatedAsyncioTestCase):
    async def test_processed_native_speech_interrupts_without_whisper_probes(self):
        events=[]
        async def emit(e):events.append(e)
        async def decode(_):self.fail('Native barge-in must not require a decoder probe')
        turn=VoiceTurn(emit,decode,processed_input=True)
        turn.number=1;turn.phase='speaking'
        try:
            for _ in range(10):await turn.audio(b'\x00\x10'*320,True)
            self.assertEqual(turn.number,2)
            self.assertTrue(any(e['type']=='interrupt' for e in events))
            self.assertIsNone(turn.probe_job)
        finally:await turn.close()
    async def test_processed_noise_does_not_pause_and_old_generation_timeout_is_bounded(self):
        events=[];now=[0.0]
        async def emit(e):events.append(e)
        turn=VoiceTurn(emit,None,processed_input=True,clock=lambda:now[0])
        turn.number=1;turn.phase='speaking'
        try:
            for _ in range(60):await turn.audio(b'\x00\x00'*320,False)
            self.assertFalse(any(e['type']=='interrupt' for e in events))
        finally:await turn.close()

    async def test_timing_reports_measured_silence_and_decoder_duration(self):
        events=[]
        async def emit(e):events.append(e)
        async def decode(_):return {'text':'Hello there','durationMs':912}
        turn=VoiceTurn(emit,decode,pause='short',processed_input=True)
        turn.number=1;turn.phase='listening';turn.voiced=.7;turn.silence=.82;turn.buffer=bytearray(b'\x00\x10'*16000)
        try:
            await turn.finish_capture();await turn.flush()
            stages={e['stage']:e['durationMs'] for e in events if e['type']=='timing'}
            self.assertEqual(stages,{'endDetection':820,'transcription':912})
        finally:await turn.close()

    async def test_confirmed_wake_misspelling_preserves_the_buffered_question(self):
        events=[];release=asyncio.Event();calls=[]
        async def emit(e):events.append(e)
        async def decode(data):
            calls.append(data)
            if len(calls)==1:
                await release.wait()
                return {'text':'Hey, Jude.','durationMs':900}
            return {'text':'What is a web worker?','durationMs':850}
        turn=VoiceTurn(emit,decode,pause='short',processed_input=True,clock=lambda:0.)
        try:
            await turn.wake()
            turn.buffer=bytearray(b'\x00\x10'*16000);turn.voiced=.6;turn.silence=.8
            await turn.finish_capture();await asyncio.sleep(0)
            # The user begins their question while the wake-only clip decodes.
            turn.pending_question=bytearray(b'\x00\x20'*20000)
            turn.pending_started=0.;turn.pending_voiced=.8;turn.pending_silence=.8;turn.pending_finished=True
            release.set();await turn.flush()
            self.assertEqual([e['text'] for e in events if e['type']=='transcript'],['What is a web worker?'])
            self.assertEqual(len(calls),2)
        finally:await turn.close()

    async def test_unconfirmed_name_or_real_question_is_not_discarded_as_wake(self):
        for raw in ('Hey, Jude.', 'My name is Jude.', 'Hey Jude, what is a web worker?'):
            with self.subTest(raw=raw):
                events=[]
                async def emit(e):events.append(e)
                async def decode(data):return {'text':raw,'durationMs':900}
                turn=VoiceTurn(emit,decode,pause='short',processed_input=True)
                turn.number=1;turn.phase='listening';turn.buffer=bytearray(b'\x00\x10'*16000)
                try:
                    await turn.finish_capture();await turn.flush()
                    self.assertEqual([e['text'] for e in events if e['type']=='transcript'],[raw])
                finally:await turn.close()
