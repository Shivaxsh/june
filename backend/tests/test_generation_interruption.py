"""Native input must be a valid utterance before replacing a pending answer."""
import asyncio
import unittest
from june.realtime_state import VoiceTurn

class GenerationInterruption(unittest.IsolatedAsyncioTestCase):
    async def make_turn(self, text='', error=None):
        self.events=[]
        async def emit(event): self.events.append(event)
        async def decode(_):
            if error: raise error
            return {'text':text,'durationMs':7}
        self.turn=VoiceTurn(emit,decode,pause='short',processed_input=True)
        self.turn.number=2; self.turn.phase='generating'
        return self.turn

    async def input(self, voiced, count):
        for _ in range(count):
            await self.turn.audio(b'\x00\x10'*320,voiced)
            await asyncio.sleep(0)

    async def test_empty_noise_cannot_cancel_answer_before_first_text(self):
        turn=await self.make_turn('')
        try:
            await self.input(True,12)
            self.assertEqual(turn.number,2,'A VAD candidate alone must not cancel generation')
            await self.input(False,42); await turn.flush()
            self.assertEqual(turn.number,2)
            self.assertEqual(turn.phase,'generating')
            self.assertFalse(any(e['type'] in ('interrupt','transcript') for e in self.events))
        finally: await turn.close()

    async def test_valid_replacement_is_delivered_once_after_confirmation(self):
        turn=await self.make_turn('Wait, keep it short.')
        try:
            await self.input(True,30)
            self.assertEqual(turn.number,2)
            await self.input(False,42); await turn.flush()
            self.assertEqual(turn.number,3)
            self.assertEqual([e['text'] for e in self.events if e['type']=='transcript'],['Wait, keep it short.'])
            self.assertEqual(len([e for e in self.events if e['type']=='interrupt']),1)
            self.assertEqual(turn.phase,'generating')
        finally: await turn.close()

    async def test_playback_still_interrupts_promptly(self):
        turn=await self.make_turn('Wait')
        turn.phase='speaking'
        try:
            await self.input(True,10)
            self.assertEqual(turn.number,3)
            self.assertEqual(turn.phase,'listening')
        finally: await turn.close()

    async def test_failed_candidate_leaves_generation_running(self):
        from june.errors import JuneError
        turn=await self.make_turn(error=JuneError('uncertain','Please repeat.',422))
        try:
            await self.input(True,30); await self.input(False,42); await turn.flush()
            self.assertEqual(turn.number,2)
            self.assertEqual(turn.phase,'generating')
            self.assertFalse(any(e['type']=='interrupt' for e in self.events))
        finally: await turn.close()

    async def test_late_candidate_cannot_replace_newer_wake(self):
        turn=await self.make_turn()
        started=asyncio.Event();release=asyncio.Event()
        async def decode(_):
            started.set()
            try: await release.wait()
            except asyncio.CancelledError: pass
            return {'text':'obsolete question','durationMs':10}
        turn.transcribe=decode
        try:
            await self.input(True,30); await self.input(False,42); await started.wait()
            await turn.wake(); release.set(); await asyncio.sleep(0)
            self.assertEqual(turn.number,3)
            self.assertEqual(turn.phase,'listening')
            self.assertFalse(any(e['type']=='transcript' for e in self.events))
        finally: release.set(); await turn.close()

    async def test_candidate_retains_beginning_when_output_starts(self):
        turn=await self.make_turn('Wait, keep it short.')
        try:
            await self.input(True,12)
            await turn.activity(2,'speaking','An existing answer.')
            self.assertEqual(turn.number,3)
            self.assertEqual(turn.phase,'listening')
            self.assertGreaterEqual(len(turn.buffer),12*640)
            await self.input(True,18); await self.input(False,42); await turn.flush()
            self.assertEqual([e['text'] for e in self.events if e['type']=='transcript'],['Wait, keep it short.'])
        finally: await turn.close()
