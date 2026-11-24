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

    async def test_native_barge_in_clip_keeps_the_start_of_the_users_words(self):
        # 2026-11-23: an interruption clip began at full volume (its first word was missing).
        clips=[];events=[]
        async def emit(e):events.append(e)
        async def decode(data):clips.append(data);return {'text':'two','durationMs':1}
        turn=VoiceTurn(emit,decode,pause='short',processed_input=True)
        turn.number=1;turn.phase='speaking'
        EARLY,LATE=b'\x05\x50',b'\x00\x10'
        try:
            for _ in range(40):await turn.audio(EARLY*320,False)  # the soft start the gate missed (0.8 s)
            for _ in range(10):await turn.audio(LATE*320,True)    # the part that confirmed the barge-in
            for _ in range(50):await turn.audio(b'\x00\x00'*320,False)
            await turn.flush()
            self.assertTrue(any(e['type']=='interrupt' for e in events))
            audio=clips[0][44:]
            kept=sum(1 for i in range(0,len(audio),2) if audio[i:i+2]==EARLY)*2/32000
            self.assertGreaterEqual(kept,.75,f'only {kept:.2f} s from before the trigger was kept')
        finally:await turn.close()


class MeasuredBargeIn(unittest.IsolatedAsyncioTestCase):
    """Frame numbers (VAD probability / RMS) measured on this Mac's voice-processed input on 2026-11-23."""
    ECHO = [(0,0),(0,.002),(.66,.020),(.66,.039),(.62,.042),(.62,.045),(.46,.049),(.31,.029),(.31,.020),(.15,.017),(.07,.002)]
    TWO = [(0,0),(.02,.089),(.02,.321),(.68,.199),(.73,.162),(.73,.130),(.43,.129),(.44,.246),(.44,.209),(.34,.184),(.34,.055),(.52,.018),(.48,.019)]
    STOP = [(0,.144),(0,.440),(.70,.203),(.61,.190),(.61,.195),(.35,.208),(.35,.153),(.30,.171),(.22,.253),(.22,.243),(.32,.196),(.32,.109),(.32,.075)]
    FLOOR = .00111

    async def replay(self, frames):
        from june.signal_gate import barge_evidence, ProcessedSignalGate
        events=[]
        async def emit(e):events.append(e)
        async def decode(_):return {'text':'two','durationMs':1}
        turn=VoiceTurn(emit,decode,pause='short',processed_input=True)
        turn.number=1;turn.phase='speaking';gate=ProcessedSignalGate()
        try:
            for p,rms in [(0,0)]*20+frames+[(0,0)]*20:
                voiced,_=gate.accept(640,p,rms,self.FLOOR,False)
                await turn.audio(b'\x00\x10'*320,voiced,barge=barge_evidence(p,rms,self.FLOOR))
            return any(e['type']=='interrupt' for e in events)
        finally:await turn.close()

    async def test_the_users_measured_words_interrupt_june(self):
        for name,frames in (('two',self.TWO),('stop',self.STOP)):
            with self.subTest(word=name):
                self.assertTrue(await self.replay(frames),f'"{name}" (VAD 0.3-0.73, RMS up to 0.44) must interrupt')

    async def test_junes_measured_echo_and_silence_never_interrupt(self):
        self.assertFalse(await self.replay(self.ECHO*3),'her own echo peaked at RMS 0.049')
        self.assertFalse(await self.replay([(0,0)]*200))
        self.assertFalse(await self.replay([(.9,.5),(0,0),(0,0),(0,0),(.9,.5)]),'two isolated 20 ms spikes are not a word')

    def test_the_old_rule_missed_both_words(self):
        # The previous gate needed VAD >= 0.8 for 0.18 s unbroken: none of these frames qualified.
        self.assertFalse(any(p>=.8 for p,_ in self.TWO+self.STOP))
