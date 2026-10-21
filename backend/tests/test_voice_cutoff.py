"""Regression for a clipped playback word falsely cancelling a complete reply."""
import asyncio
import unittest
from june.realtime_state import VoiceTurn

class ClippedPlayback(unittest.IsolatedAsyncioTestCase):
    async def test_saved_allow_fragment_cannot_cancel_internet_answer(self):
        events=[]
        async def emit(event):events.append(event)
        async def transcribe(_):return {'text':'allow', 'durationMs':10}
        turn=VoiceTurn(emit,transcribe)
        turn.number=1;turn.phase='generating'
        await turn.activity(1,'speaking','The internet allows people to connect and share information across different locations.')
        try:
            for _ in range(60):
                await turn.audio(b'\x00\x10'*320,True)
                await asyncio.sleep(0)
            await turn.flush()
            self.assertEqual(turn.number,1)
            self.assertFalse(any(e['type'] in ('interrupt','transcript') for e in events))
        finally:await turn.close()

    def test_clipped_word_rule_preserves_real_controls_and_different_identifiers(self):
        turn=VoiceTurn(None,None)
        reference='It allows workers to continue waiting for code 3060.'
        for text in ('wait','stop','no','5060','Linux','allow me to ask another question','what allows that?'):
            with self.subTest(text=text):self.assertFalse(turn.is_playback_echo(text,reference))
        for text in ('allow','worke','continu'):
            with self.subTest(text=text):self.assertTrue(turn.is_playback_echo(text,reference))
