"""Speaker-list echo with imperfect ASR, without changing raw user words."""
import asyncio
import unittest
from june.realtime_state import VoiceTurn

CAPTION='This series included the RTX 580, RTX 5700, RTX 5700 XT, and RTX 5700 XT.'
ECHO='5080, RTX 5700, RTX 5700 XT, NR...'


class ImperfectEcho(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events=[]
        async def emit(event):self.events.append(event)
        async def transcribe(_):return {'text':ECHO,'durationMs':1}
        self.turn=VoiceTurn(emit,transcribe)
        self.turn.number=1;self.turn.phase='generating'
        await self.turn.activity(1,'speaking',CAPTION)

    async def asyncTearDown(self):await self.turn.close()

    async def test_imperfect_list_fragment_is_still_echo(self):
        self.assertTrue(self.turn.is_playback_echo(ECHO,CAPTION))

    async def test_overlap_does_not_create_an_interrupt_or_user_message(self):
        for voiced,count in ((True,65),(False,80)):
            for _ in range(count):
                await self.turn.audio((b'\x00\x10' if voiced else b'\x00\x00')*320,voiced)
                await asyncio.sleep(0)
        await self.turn.flush()
        self.assertEqual(self.turn.number,1)
        self.assertFalse(any(e['type'] in ('interrupt','transcript','probe') for e in self.events))

    async def test_followup_does_not_send_a_clipped_list_echo(self):
        await self.turn.activity(1,'complete')
        for voiced,count in ((True,35),(False,80)):
            for _ in range(count):
                await self.turn.audio((b'\x00\x10' if voiced else b'\x00\x00')*320,voiced)
                await asyncio.sleep(0)
        await self.turn.flush()
        self.assertFalse(any(e['type']=='transcript' for e in self.events))

    async def test_explicit_corrections_questions_and_single_numbers_are_not_echo(self):
        for text in ('No, I meant RTX 5080, not RTX 580.',
                     'What about RTX 5080 and RTX 5700 XT?',
                     'Compare RTX 5080 and RTX 5700 XT.',
                     'Repeat RTX 5080, RTX 5700, RTX 5700 XT.',
                     '5080', '5070 Ti', 'RTX 5070 Ti, RTX 5080 and RTX 5090.',
                     '5080 and 5700 are my graphics cards.'):
            with self.subTest(text=text):
                self.assertFalse(self.turn.is_playback_echo(text,CAPTION))

    async def test_trailing_question_and_control_words_are_never_discarded(self):
        for ending in ('why?', 'how?', 'no.', 'NO...', 'WHY...', 'SHH...', 'hmm...'):
            with self.subTest(ending=ending):
                self.assertFalse(self.turn.is_playback_echo('5080, RTX 5700, RTX 5700 XT, '+ending,CAPTION))
