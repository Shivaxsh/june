"""8.3: June writes a Word document, a presentation or a PDF into her own folder and checks the file."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

DRAFT = {'title': 'Solar Power Basics', 'summary': 'A short introduction to solar power for a home.',
         'sections': [{'heading': 'How panels work', 'text': 'Panels turn sunlight into electricity.', 'bullets': ['Cells absorb light', 'An inverter makes AC']},
                      {'heading': 'Costs', 'text': 'Prices have fallen for a decade.', 'bullets': ['Panels', 'Installation', 'Maintenance']},
                      {'heading': 'Next steps', 'text': 'Start with a site survey.', 'bullets': ['Check your roof', 'Compare quotes']}]}


class Requests(unittest.TestCase):
    def test_spoken_requests(self):
        from june.creations import creation_request
        cases = {
            'create a word document about solar power': ('docx', 'solar power', None),
            'Hey June, make me a presentation on the history of jazz with 8 slides': ('pptx', 'the history of jazz', 8),
            'write a report about remote work as a pdf': ('pdf', 'remote work', None),
            'make a pdf about healthy breakfast ideas': ('pdf', 'healthy breakfast ideas', None),
            'can you prepare a powerpoint on our Q3 marketing plan please': ('pptx', 'our Q3 marketing plan', None),
            'draft a document explaining how compound interest works with 4 sections': ('docx', 'how compound interest works', 4),
            'create slides about machine learning': ('pptx', 'machine learning', None),
            'generate a ppt on climate change with ten slides': ('pptx', 'climate change', 10),
        }
        for text, (kind, topic, count) in cases.items():
            got = creation_request(text)
            self.assertIsNotNone(got, text)
            self.assertEqual((got['kind'], got['topic'], got['count']), (kind, topic, count), text)
        for text in ('how do I create a word document?', 'make a presentation', 'open my document about solar power', 'what documents do I have?', 'write a poem about the sea',
                     'don’t create a document about x', 'summarise my pdf about taxes', 'create a document about ' + 'x' * 300, 'make me a sandwich about noon'):
            self.assertIsNone(creation_request(text), text)

    def test_follow_up_to_open_the_last_one(self):
        from june.creations import open_request
        for text in ('open it', 'Open that document', 'open the presentation', 'show it to me', 'open the file please', 'open the pdf'):
            self.assertTrue(open_request(text), text)
        for text in ('open figma', 'open it up to discussion', 'what is it', 'open my calendar'):
            self.assertFalse(open_request(text), text)

    def test_a_bare_open_is_recognised_but_not_other_requests(self):
        from june.creations import open_request, bare_open
        for text in ('open', 'Open.', 'Hey June, open', 'open please', 'open up', 'yes open it', 'yeah, open', 'open now', 'show me', 'okay open'):
            self.assertTrue(bare_open(text) or open_request(text), text)
        for text in ('open it up', 'open that one', 'open this one', 'open it for me', 'open the one you just made', 'yes open it', 'open the word document'):
            self.assertTrue(open_request(text), text)
        for text in ('open figma', 'open sesame street', 'opening', 'open the pod bay doors', 'show me the weather', 'open a new chat'):
            self.assertFalse(bare_open(text) or open_request(text), text)


class Files(unittest.TestCase):
    def setUp(self):
        from june.creations import Creations
        self.tmp = tempfile.TemporaryDirectory()
        self.opened = []
        self.store = Creations(Path(self.tmp.name) / 'data', Path(self.tmp.name) / 'June Documents', opener=lambda argv: self.opened.append(argv) or 0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_kind_is_built_checked_and_never_overwrites(self):
        from docx import Document
        from pptx import Presentation
        from pypdf import PdfReader
        word = self.store.build('docx', DRAFT)
        self.assertTrue(word['path'].endswith('Solar Power Basics.docx')); self.assertEqual(word['parts'], 3)
        document = Document(word['path'])
        text = '\n'.join([p.text for p in document.paragraphs] + [cell.text for table in document.tables for row in table.rows for cell in row.cells])
        for words in ('Solar Power Basics', 'How panels work', 'Panels turn sunlight into electricity.', 'Compare quotes'):
            self.assertIn(words, text)
        deck = self.store.build('pptx', DRAFT)
        slides = Presentation(deck['path']).slides
        self.assertEqual(len(slides), 4, 'a title slide and one per section'); self.assertEqual(deck['parts'], 4)
        self.assertIn('Costs', [s.shapes.title.text for s in slides])
        pdf = self.store.build('pdf', DRAFT)
        reader = PdfReader(pdf['path'])
        self.assertGreaterEqual(len(reader.pages), 1); self.assertIn('Solar Power Basics', reader.pages[0].extract_text())
        again = self.store.build('docx', DRAFT)
        self.assertNotEqual(again['path'], word['path']); self.assertTrue(Path(word['path']).exists())
        listed = self.store.state()['creations']
        self.assertEqual([c['kind'] for c in listed], ['docx', 'pdf', 'pptx', 'docx'])
        self.assertTrue(all(set(c) == {'id', 'kind', 'title', 'fileName', 'createdAt', 'exists', 'url', 'design'} for c in listed), 'no path leaves the server')

    def test_unsafe_titles_and_drafts_are_cleaned_or_refused(self):
        from june.creations import clean_draft
        nasty = clean_draft({'title': '../../etc/passwd\x00 <b>Report</b>', 'summary': 'x', 'sections': [{'heading': 'A', 'text': 'B', 'bullets': ['c'] * 40}] * 3}, 5)
        made = self.store.build('docx', nasty)
        self.assertEqual(Path(made['path']).parent, Path(self.tmp.name) / 'June Documents')
        self.assertNotIn('..', Path(made['path']).name); self.assertNotIn('/', Path(made['path']).name)
        self.assertLessEqual(len(nasty['sections'][0]['bullets']), 8)
        kept = clean_draft({'title': '6th Birthday Party', 'summary': '', 'sections': [{'heading': '1. 10 games for kids', 'text': '- 3 cakes', 'bullets': ['• 2024 plan', '**Bold**']}] * 2}, 4)
        self.assertEqual(kept['title'], '6th Birthday Party', 'a number that starts a title is part of it')
        self.assertEqual((kept['sections'][0]['heading'], kept['sections'][0]['text'], kept['sections'][0]['bullets']), ('10 games for kids', '3 cakes', ['2024 plan', 'Bold']))
        for bad in (None, {}, {'title': '', 'sections': []}, {'title': 'T', 'sections': [{'heading': 'only one'}]}, {'title': 'T', 'sections': 'x'}, 'text'):
            self.assertIsNone(clean_draft(bad, 5), str(bad))

    def test_open_and_reveal_only_files_june_made_that_still_exist(self):
        from june.errors import JuneError
        made = self.store.build('pdf', DRAFT)
        self.store.open(made['id'])
        self.assertEqual(self.opened[-1], ['/usr/bin/open', made['path']])
        self.store.open(made['id'], reveal=True)
        self.assertEqual(self.opened[-1], ['/usr/bin/open', '-R', made['path']])
        Path(made['path']).unlink()
        with self.assertRaises(JuneError): self.store.open(made['id'])
        with self.assertRaises(JuneError): self.store.open('../../etc/passwd')
        self.assertFalse(self.store.state()['creations'][0]['exists'])

    def test_a_template_the_person_provides_is_used(self):
        from docx import Document
        from pptx import Presentation
        templates = Path(self.tmp.name) / 'June Documents' / 'Templates'; templates.mkdir(parents=True)
        base = Document(); base.core_properties.author = 'Template Owner'; base.add_paragraph('OLD BODY'); base.save(templates / 'template.docx')
        Presentation().save(templates / 'template.pptx')
        word = Document(self.store.build('docx', DRAFT)['path'])
        self.assertEqual(word.core_properties.author, 'Template Owner')
        self.assertNotIn('OLD BODY', [p.text for p in word.paragraphs], 'the template gives the look, not its old text')
        self.assertEqual(len(Presentation(self.store.build('pptx', DRAFT)['path']).slides), 4)

    def test_a_house_style_name_pins_the_preset(self):
        import subprocess, sys
        root = Path(__file__).resolve().parents[2]
        templates = Path(self.tmp.name) / 'June Documents' / 'Templates'
        subprocess.run([sys.executable, str(root / 'scripts/make-templates.py'), 'forest', str(templates)], check=True, capture_output=True, timeout=60)
        self.assertEqual(self.store.house_pins('')['palette'], 'forest')
        self.assertEqual(self.store.house_pins('dark')['tone'], 'dark', 'words the person says win')
        subprocess.run([sys.executable, str(root / 'scripts/make-templates.py'), 'none', str(templates)], check=True, capture_output=True, timeout=60)
        self.assertEqual(self.store.house_pins(''), {})

class Chat(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from june.creations import Creations
        self.tmp = tempfile.TemporaryDirectory()
        self.opened = []
        self.store = Creations(Path(self.tmp.name) / 'data', Path(self.tmp.name) / 'June Documents', opener=lambda argv: self.opened.append(argv) or 0)
        self.settings = SimpleNamespace(ollama='http://127.0.0.1:1', model='fixture')

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_chat_writes_the_file_says_where_and_opens_it_on_request(self):
        calls = []
        async def model(client, url, payload, limit, timeout):
            calls.append(payload); return {'message': {'content': json.dumps(DRAFT)}}
        with patch('june.creations.bounded_json', model):
            self.assertIsNone(await self.store.chat('tell me a joke', None, self.settings))
            reply = await self.store.chat('make me a presentation on solar power with 3 slides', None, self.settings)
        self.assertEqual(calls[0]['options']['num_ctx'], 4096); self.assertEqual(calls[0]['options']['temperature'], 0.3)
        for words in ('“Solar Power Basics”', 'presentation', '3 slides', 'June Documents', 'check the facts', 'open it'):
            self.assertIn(words, reply['reply'], words)
        self.assertEqual(len(self.store.state()['creations']), 1)
        opened = await self.store.chat('open it', None, self.settings)
        self.assertIn('Opened', opened['reply']); self.assertEqual(len(self.opened), 1)
        just = await self.store.chat('Open.', None, self.settings)
        self.assertIn('Opened', just['reply'], 'right after a document is made, “open” alone means that document'); self.assertEqual(len(self.opened), 2)
        later = time.time() + 3600
        with patch('june.creations.time.time', lambda: later):
            self.assertIsNone(await self.store.chat('open', None, self.settings), 'an hour later a bare “open” is no longer about the document')
        self.assertEqual(len(self.opened), 2)

    async def test_a_bad_draft_or_model_failure_creates_nothing(self):
        async def garbage(*args): return {'message': {'content': 'not json'}}
        async def broken(*args): raise RuntimeError('offline')
        for fake in (garbage, broken):
            with patch('june.creations.bounded_json', fake):
                reply = await self.store.chat('create a word document about solar power', None, self.settings)
            self.assertIn('Nothing was created', reply['reply'])
        self.assertEqual(self.store.state()['creations'], [])
        nothing = await self.store.chat('open it', None, self.settings)
        self.assertIn('haven’t made', nothing['reply'])


BIRDS = dict(DRAFT, title='Garden Birds Through the Year')


class Designs(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from june.creations import Creations
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Creations(Path(self.tmp.name) / 'data', Path(self.tmp.name) / 'June Documents', opener=lambda argv: 0)
        self.settings = SimpleNamespace(ollama='http://127.0.0.1:1', model='fixture')
        self.asked = []

    async def asyncTearDown(self):
        self.tmp.cleanup()

    def model(self, design):
        async def fake(client, url, payload, limit, timeout):
            self.asked.append(payload)
            from june.designs import FIELD
            if 'sections' in payload['format']['properties']:
                return {'message': {'content': json.dumps(BIRDS)}}
            return {'message': {'content': json.dumps({FIELD[k]: v for k, v in design.items() if k in FIELD})}}
        return fake

    def test_style_words_in_a_request_are_kept_apart_from_the_topic(self):
        from june.creations import creation_request
        for text, topic, style in (('make a dark presentation about solar power', 'solar power', 'dark'),
                                   ('create a playful pdf about my son’s birthday party', 'my son’s birthday party', 'playful'),
                                   ('make a presentation about green energy', 'green energy', ''),
                                   ('write a word document about the budget in a minimal style', 'the budget', 'minimal'),
                                   ('make a presentation about tea with 5 slides in blue and gold', 'tea', 'blue and gold'),
                                   ('build a retro-style website for a vinyl shop', 'a vinyl shop', 'retro')):
            got = creation_request(text)
            self.assertIsNotNone(got, text); self.assertEqual((got['topic'], got['style']), (topic, style), text)

    def test_restyle_requests(self):
        from june.creations import restyle_request
        for text, words in (('make it in a different style', ''), ('try another design', ''), ('redo it in dark', 'dark'), ('change the colours', ''),
                            ('make it more playful', 'playful'), ('restyle it in green', 'green'), ('change the theme to minimal', 'minimal'),
                            ('give me a different look please', ''), ('make the presentation elegant', 'elegant'), ('a different style', '')):
            got = restyle_request(text)
            self.assertIsNotNone(got, text); self.assertEqual(got['words'], words, text)
        for text in ('change the music', 'make it dark mode', 'switch to dark mode', 'make it louder', 'make a presentation about style', 'don’t change the colours', 'what style is it'):
            self.assertIsNone(restyle_request(text), text)

    async def test_june_designs_each_file_and_restyles_from_the_stored_draft(self):
        first = dict(reason='Birds and gardens: natural.', mood='natural', palette='forest', type='literary', motif='waves', cover='split', layout='two-column',
                     heading='underline', bullet='dot', corners='round', lines='regular', density='airy', accent='sparing')
        with patch('june.creations.bounded_json', self.model(first)), patch('june.knowledge.bounded_json', self.model(first)):
            made = await self.store.chat('make a presentation about garden birds', None, self.settings)
        self.assertIn('Forest', made['reply']); self.assertIn('Birds and gardens', made['reply'])
        self.assertEqual(self.store.state()['creations'][0]['design'], 'Forest · natural')
        drafts = len([a for a in self.asked if 'sections' in a['format']['properties']])
        with patch('june.creations.bounded_json', self.model(first)), patch('june.knowledge.bounded_json', self.model(first)):
            again = await self.store.chat('make it in a different style', None, self.settings)
        self.assertEqual(len([a for a in self.asked if 'sections' in a['format']['properties']]), drafts, 'restyling never rewrites the text')
        self.assertIn('different look from the last one', self.asked[-1]['messages'][1]['content'])
        rows = self.store.state()['creations']
        self.assertEqual(len(rows), 2); self.assertNotEqual(rows[0]['design'], rows[1]['design'], 'June never repeats the look she is asked to change')
        self.assertNotEqual(rows[0]['fileName'], rows[1]['fileName']); self.assertTrue(all(r['exists'] for r in rows))
        with patch('june.creations.bounded_json', self.model(first)), patch('june.knowledge.bounded_json', self.model(first)):
            dark = await self.store.chat('redo it in dark', None, self.settings)
        from june.designs import PALETTES
        self.assertEqual(PALETTES[self.store.latest()['design']['palette']]['tone'], 'dark', dark['reply'])

    async def test_nothing_to_restyle_or_an_old_file_is_explained(self):
        self.assertIsNone(await self.store.chat('make it in a different style', None, self.settings))
        with self.store.db() as db:
            db.execute("INSERT INTO creations(id,kind,title,path,created) VALUES('a'||hex(randomblob(15)),'pdf','Old',?,?)", (str(Path(__file__)), time.time()))
        self.store.folder = Path(__file__).parent
        reply = await self.store.chat('make it in a different style', None, self.settings)
        self.assertIn('made after designs were added', reply['reply'])

    async def test_your_own_template_still_wins(self):
        from docx import Document
        templates = Path(self.tmp.name) / 'June Documents' / 'Templates'; templates.mkdir(parents=True)
        base = Document(); base.core_properties.author = 'Template Owner'; base.save(templates / 'template.docx')
        design = dict(mood='playful', palette='candy', type='rounded')
        with patch('june.creations.bounded_json', self.model(design)), patch('june.knowledge.bounded_json', self.model(design)):
            reply = await self.store.chat('write a word document about garden birds', None, self.settings)
        self.assertIn('your own template', reply['reply'])
        self.assertEqual(Document(str(Path(self.tmp.name) / 'June Documents' / 'Garden Birds Through the Year.docx')).core_properties.author, 'Template Owner')
