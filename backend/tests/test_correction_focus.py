import unittest
from june.chat import correction_focus


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
