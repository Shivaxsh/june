import unittest
from june.chat import correction_focus
import json
import httpx
from june.chat import PROMPT,stream_chat
from june.config import Settings


class CorrectionFocusTests(unittest.TestCase):
    def test_recent_update_survives_an_unrelated_followup(self):
        messages = [
            {'role': 'user', 'content': 'The project code is Copper.'},
            {'role': 'assistant', 'content': 'Copper'},
            {'role': 'user', 'content': 'For this test the project code changes to Amber. Repeat Amber only.'},
            {'role': 'assistant', 'content': 'Amber'},
            {'role': 'user', 'content': 'Repeat the latest project code only.'},
        ]
        focus = correction_focus(messages)
        self.assertIn('changes to Amber', focus)
        self.assertNotIn('Copper', focus)
        self.assertIn('user data', focus)

    def test_newest_user_update_wins_and_assistant_text_is_not_a_correction(self):
        messages = [
            {'role': 'user', 'content': 'Actually, use the first value.'},
            {'role': 'assistant', 'content': 'Actually, use an invented value.'},
            {'role': 'user', 'content': 'Correction: use the second value.'},
            {'role': 'assistant', 'content': 'OK'},
            {'role': 'user', 'content': 'What is it now?'},
        ]
        focus = correction_focus(messages)
        self.assertIn('second value', focus)
        self.assertNotIn('first value', focus)
        self.assertNotIn('invented value', focus)

    def test_no_update_adds_no_recap(self):
        self.assertEqual(correction_focus([{'role': 'user', 'content': 'Explain React.'}]), '')


class StablePromptPrefix(unittest.IsolatedAsyncioTestCase):
    async def test_identifier_focus_follows_the_stable_memory_prefix(self):
        systems=[]
        def response(request):
            systems.append(json.loads(request.content)['messages'][0]['content'])
            return httpx.Response(200,text='{"message":{"content":"5060"},"done":true}\n')
        memory='\nCharacter preferences and approved data: []'
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            for query in ('Repeat my exact model number: RTX 5060.', 'Repeat my exact model number: RTX 5070 Ti.'):
                _=[e async for e in stream_chat(client,Settings.from_env(),'local',[{'role':'user','content':query}],memory)]
        for system in systems:
            self.assertTrue(system.startswith(PROMPT+memory))
            self.assertEqual(system.count(memory),1)
