import unittest
from june.speech_text import clean_transcript, ReplyIdentityGuard

class TranscriptText(unittest.TestCase):
    def test_noise_annotations_are_not_questions(self):
        for value in ('*cough*', '(coughing)', '[BLANK_AUDIO]', '*clears throat*', '[music]', '[silence]', '...'):
            self.assertEqual(clean_transcript(value), '')
        self.assertEqual(clean_transcript('*cough* How about the 5070 Ti?'), 'How about the 5070 Ti?')
        self.assertEqual(clean_transcript('I cough when it is dusty.'), 'I cough when it is dusty.')

    def test_digit_sequences_are_preserved_without_guessing(self):
        self.assertEqual(clean_transcript('I said five zero six zero.'), 'I said 5060.')
        self.assertEqual(clean_transcript('I said three zero six zero.'), 'I said 3060.')
        self.assertEqual(clean_transcript('The code is seven two nine four.'), 'The code is 7294.')
        self.assertEqual(clean_transcript('One or two people, fifty sixty, 506060.'), 'One or two people, fifty sixty, 506060.')

class Identities(unittest.TestCase):
    def guard(self, text):
        return ReplyIdentityGuard([{'role':'user','content':'Tell me about graphics cards.'}, {'role':'assistant','content':'An RTX 3060 is an option.'}, {'role':'user','content':text}])

    def test_wrong_identity_is_replaced_before_any_text_is_spoken(self):
        guard = self.guard('How about the 5070 Ti?')
        self.assertEqual(guard.push('The NVIDIA RTX 30'), [])
        output = guard.push('70 Ti is a good card. ')
        self.assertIn('5070', ''.join(output))
        self.assertNotIn('3070', ''.join(output))
        self.assertTrue(guard.rejected)

    def test_correct_card_comparison_and_prices_remain_ordinary_streamed_text(self):
        for reply in ('The RTX 5070 Ti is the model you asked about. ', 'Compared with the RTX 3060, the RTX 5070 Ti is a different model. ', 'A price of 3000 is only an example. '):
            guard = self.guard('How about the 5070 Ti?')
            self.assertEqual(''.join(guard.push(reply) + guard.finish()), reply)
            self.assertFalse(guard.rejected)

    def test_no_gpu_context_does_not_treat_a_year_or_code_as_a_card(self):
        guard = ReplyIdentityGuard([{'role':'user','content':'Tell me about the year 2026.'}])
        self.assertEqual(''.join(guard.push('In 2025, something happened. ') + guard.finish()), 'In 2025, something happened. ')

    def test_gpu_discussion_does_not_turn_budget_or_year_into_model_identity(self):
        for question in ('My budget is 3000 rupees.', 'What happened in 2026?'):
            guard = self.guard(question)
            reply = 'An RTX 3060 is only an example. '
            self.assertEqual(''.join(guard.push(reply) + guard.finish()), reply)
            self.assertFalse(guard.rejected)

    def test_explicitly_rejected_number_is_not_an_allowed_identity(self):
        guard = self.guard('I said 5060, not the RTX 3060.')
        self.assertIn('5060', ''.join(guard.push('The RTX 3060 is a good choice. ')))
        self.assertTrue(guard.rejected)

    def test_comparison_word_does_not_excuse_substitution_without_requested_model(self):
        guard=self.guard('How about the 5070 Ti?')
        output=''.join(guard.push('The RTX 3070 Ti is more efficient than older cards. '))
        self.assertTrue(guard.rejected)
        self.assertIn('5070 Ti',output)

    def test_model_suffix_is_part_of_identity(self):
        guard=self.guard('How about the 5070 Ti?')
        output=''.join(guard.push('The RTX 5070 is the card you asked about. '))
        self.assertTrue(guard.rejected)
        self.assertIn('5070 Ti',output)

class NumberConfirmation(unittest.TestCase):
    def test_repeating_user_supplied_identity_is_not_treated_as_unknown_product_facts(self):
        from june.chat import prompt_for_turn
        messages=[{'role':'user','content':'Tell me about graphics cards.'},{'role':'assistant','content':'A GPU renders images.'},{'role':'user','content':'I meant 5060, not 3060. Tell me the exact number I said.'}]
        prompt=prompt_for_turn(messages,ReplyIdentityGuard(messages))
        self.assertIn('You said 5060.',prompt)
        self.assertNotIn('You said 3060.',prompt)
        self.assertNotIn('You said 5060.',prompt_for_turn([{'role':'user','content':'What is a graphics card?'}],ReplyIdentityGuard([])))
