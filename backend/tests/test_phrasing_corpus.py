"""The permanent guard: every realistic phrasing reaches the right tool, and ordinary chat never does."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from corpus_support import family  # noqa: E402
from phrasing_corpus import NEGATIVE, POSITIVE  # noqa: E402


class Corpus(unittest.TestCase):
    def test_every_phrase_reaches_its_tool_through_a_grammar_or_the_router(self):
        from june.intent_router import routable
        wrong, lost = [], []
        for intent, phrases in POSITIVE.items():
            for text in phrases:
                got = family(text)
                if got is not None and got != intent:
                    wrong.append(f'{text!r}: grammar gives {got}, wanted {intent}')
                elif got is None and not routable(text):
                    lost.append(f'{text!r} ({intent})')
        self.assertEqual(wrong, [], 'a grammar sends these to the wrong tool')
        self.assertEqual(lost, [], 'neither a grammar nor the router would see these')

    def test_ordinary_chat_never_triggers_a_grammar(self):
        hits = [f'{text!r} → {family(text)}' for text in NEGATIVE if family(text)]
        self.assertEqual(hits, [])

    def test_the_corpus_is_broad(self):
        self.assertGreaterEqual(sum(map(len, POSITIVE.values())), 320); self.assertGreaterEqual(len(NEGATIVE), 120)
        from june.intent_router import INTENTS
        self.assertEqual(set(POSITIVE), set(INTENTS) - {'none'}, 'every intent has phrasings')


if __name__ == '__main__':
    unittest.main()
