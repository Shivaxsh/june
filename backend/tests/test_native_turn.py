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
