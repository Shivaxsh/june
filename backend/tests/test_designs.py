"""June chooses each document's design; the catalogue covers every mood and keeps text readable."""
import itertools
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch


class Catalogue(unittest.TestCase):
    def test_every_mood_has_real_choice(self):
        from june.designs import MOODS, PALETTES, TYPES
        self.assertEqual(len(MOODS), 24); self.assertGreaterEqual(len(PALETTES), 40); self.assertGreaterEqual(len(TYPES), 14)
        for mood, rules in MOODS.items():
            self.assertGreaterEqual(len([p for p in PALETTES.values() if mood in p['moods']]), 3, mood)
            self.assertGreaterEqual(len([t for t in TYPES.values() if mood in t['moods']]), 2, mood)
            self.assertGreaterEqual(len(rules['motif']), 3, mood); self.assertGreaterEqual(len(rules['cover']), 2, mood)
        for palette in PALETTES.values():
            self.assertTrue(set(palette['moods']) <= set(MOODS), palette['id'])
        for kind in TYPES.values():
            self.assertTrue(set(kind['moods']) <= set(MOODS), kind['id'])

    def test_every_option_is_reachable_from_some_mood(self):
        from june.designs import MOODS, OPTIONS, PALETTES, PARAMS, TYPES
        for key in PARAMS:
            used = set(itertools.chain.from_iterable(rules[key] for rules in MOODS.values()))
            self.assertEqual(used, set(OPTIONS[key]), key)
            for rules in MOODS.values():
                self.assertTrue(set(rules[key]) <= set(OPTIONS[key]), key)
        self.assertTrue(all(p['moods'] for p in PALETTES.values())); self.assertTrue(all(t['moods'] for t in TYPES.values()))

    def test_text_is_readable_in_every_palette(self):
        from june.designs import PALETTES, colours, contrast, resolve
        for pid, palette in PALETTES.items():
            for key in ('ink', 'body', 'muted'):
                self.assertGreaterEqual(contrast(palette[key], palette['paper']), 4.5, f'{pid} {key}')
            for accent in ('sparing', 'generous'):
                c = colours(dict(resolve({'palette': pid}, {'palette': pid}), accent=accent))
                self.assertGreaterEqual(contrast(c['on_cover'], c['cover']), 4.5, f'{pid} cover {accent}')
                self.assertGreaterEqual(contrast(c['on_cover_muted'], c['cover']), 4.5, f'{pid} cover muted')
                self.assertGreaterEqual(contrast(c['accent_text'], c['paper']), 4.5, pid)
                self.assertGreaterEqual(contrast(c['on_tint'], c['tint']), 4.5, pid)
                self.assertGreaterEqual(contrast(c['on_accent'], c['accent']), 3, pid)

    def test_the_schema_offers_every_option(self):
        from june.designs import MOODS, OPTIONS, PALETTES, PARAMS, SCHEMA, TYPES, prompt
        from june.designs import FIELD
        props = {key.split('_', 1)[1]: value for key, value in SCHEMA['properties'].items()}
        self.assertEqual(sorted(SCHEMA['properties']), [FIELD[k] for k in ('reason', 'mood', 'palette', 'type', 'motif', 'cover', 'layout', 'heading')],
                         'alphabetical order is the order June decides in: why, mood, then details')
        self.assertEqual(set(props['mood']['enum']), set(MOODS)); self.assertEqual(set(props['palette']['enum']), set(PALETTES))
        self.assertEqual(set(props['type']['enum']), set(TYPES))
        from june.designs import CHOSEN
        for key in CHOSEN:
            self.assertEqual(set(props[key]['enum']), set(OPTIONS[key]))
        self.assertLessEqual(len(props), 8, 'every field costs seconds of generation on this Mac')
        text = prompt('presentation')
        for name in list(PALETTES) + list(TYPES) + list(MOODS):
            self.assertIn(name, text)
        self.assertLess(len(text), 2400, 'June reads this from scratch for every document, so it stays short')


class Choosing(unittest.TestCase):
    def test_a_valid_choice_is_used_as_given(self):
        from june.designs import resolve
        raw = dict(reason='Wedding: romantic.', mood='romantic', palette='blush', type='fashion', motif='frame', cover='band', layout='two-column', heading='smallcaps',
                   bullet='dash', corners='round', lines='hairline', density='airy', accent='sparing')
        got = resolve(raw, {}, None, 'a wedding')
        for key, value in raw.items():
            self.assertEqual(got[key], value, key)

    def test_clashing_choices_are_corrected_to_fit_the_mood(self):
        from june.designs import MOODS, PALETTES, TYPES, resolve
        got = resolve(dict(mood='solemn', palette='neon', type='geometric', motif='blobs', cover='poster', accent='generous', bullet='check'), {}, None, 'memorial')
        self.assertIn('solemn', PALETTES[got['palette']]['moods']); self.assertIn('solemn', TYPES[got['type']]['moods'])
        for key in ('motif', 'cover', 'accent', 'bullet'):
            self.assertIn(got[key], MOODS['solemn'][key], key)

    def test_no_composed_design_breaks_a_mood_rule(self):
        from june.designs import MOODS, OPTIONS, PALETTES, PARAMS, TYPES, resolve
        palettes, kinds = list(PALETTES), list(TYPES)
        for n, mood in enumerate(itertools.islice(itertools.cycle(MOODS), 500)):
            raw = dict(mood=mood, palette=palettes[n * 7 % len(palettes)], type=kinds[n * 5 % len(kinds)],
                       **{k: list(OPTIONS[k])[n * (i + 3) % len(OPTIONS[k])] for i, k in enumerate(PARAMS)})
            got = resolve(raw, {}, None, '')
            self.assertIn(mood, PALETTES[got['palette']]['moods']); self.assertIn(mood, TYPES[got['type']]['moods'])
            for key in PARAMS:
                self.assertIn(got[key], MOODS[mood][key])

    def test_nothing_usable_falls_back_by_topic_mood(self):
        from june.designs import resolve
        self.assertEqual(resolve(None, {}, None, 'my son’s 7th birthday party')['mood'], 'playful')
        self.assertEqual(resolve('garbage', {}, None, 'cloud security basics')['mood'], 'technical')
        self.assertEqual(resolve({'mood': 'nonsense'}, {}, None, 'a memorial service')['mood'], 'solemn')
        self.assertNotEqual(resolve({}, {}, None, 'kids party')['palette'], resolve({}, {}, None, 'quarterly sales report')['palette'], 'never one fixed look')

    def test_a_custom_accent_is_kept_but_made_readable(self):
        from june.designs import colours, contrast, resolve
        got = resolve(dict(mood='friendly', palette='clay', accent_color='#FFFF00'), {}, None, '')
        self.assertEqual(got['accent_color'], 'FFFF00')
        c = colours(got)
        self.assertEqual(c['accent'], 'FFFF00'); self.assertGreaterEqual(contrast(c['accent_text'], c['paper']), 4.5)
        self.assertNotIn('accent_color', resolve(dict(accent_color='red; </style>'), {}, None, ''))

    def test_explicit_words_are_honoured(self):
        from june.designs import PALETTES, TYPES, hue, hue_distance, pins_from, resolve
        dark = resolve(dict(mood='calm', palette='ocean-mist'), pins_from('dark'), None, '')
        self.assertEqual(PALETTES[dark['palette']]['tone'], 'dark')
        green = resolve(dict(mood='corporate', palette='slate'), pins_from('in green'), None, '')
        self.assertLess(hue_distance(hue(PALETTES[green['palette']]['accent'])[0], 135), 40, green['palette'])
        self.assertEqual(resolve({'mood': 'playful'}, pins_from('minimal'), None, '')['mood'], 'minimal')
        self.assertEqual(TYPES[resolve({'mood': 'technical', 'type': 'mono'}, pins_from('serif'), None, '')['type']]['kind'], 'serif')
        preset = resolve({'mood': 'playful', 'palette': 'candy'}, pins_from('plum'), None, '')
        self.assertEqual((preset['palette'], preset['type'], preset['motif']), ('plum', 'fashion', 'frame'))
        self.assertEqual(pins_from('a presentation about solar power'), {}, 'topic words are not style words')

    def test_restyling_differs_from_the_last_design(self):
        from june.designs import resolve
        first = resolve(dict(mood='warm', palette='clay', motif='circles', cover='bleed'), {}, None, 'bakery')
        again = resolve(dict(mood='warm', palette='clay', motif='circles', cover='bleed'), {}, first, 'bakery')
        for key in ('palette', 'motif', 'cover'):
            self.assertNotEqual(again[key], first[key], key)

    def test_the_reason_is_plain_text(self):
        from june.designs import clean_reason, resolve
        self.assertEqual(resolve({'reason': 'Fun <b>party</b>\x00 look'}, {}, None, '')['reason'], 'Fun b party /b look')
        self.assertEqual(clean_reason('For luxury watch enthusiasts seeking elegance and exclusivity, the feeling needs to be op醇'),
                         'For luxury watch enthusiasts seeking elegance and exclusivity')
        self.assertEqual(clean_reason('Calm and clear.'), 'Calm and clear.')
        self.assertLessEqual(len(clean_reason('word ' * 80)), 140)

    def test_a_restyle_keeps_what_the_person_asked_for_unless_they_change_it(self):
        from june.designs import PALETTES, carried, pins_from, resolve
        first = resolve({}, pins_from('dark themed cafe'), None, 'cafe')
        self.assertEqual(first['asked'], {'tone': 'dark'})
        again = resolve({'palette': 'botanical'}, carried(first, pins_from('change its color theme')), first, 'cafe')
        self.assertEqual(PALETTES[again['palette']]['tone'], 'dark', 'a new colour theme for a dark site is still dark')
        light = resolve({}, carried(first, pins_from('make it light')), first, 'cafe')
        self.assertEqual(PALETTES[light['palette']]['tone'], 'light', 'new words win')
        self.assertEqual(carried({}, {}), {}, 'older designs carry nothing')

    def test_earlier_words_beat_the_house_style_on_a_plain_restyle(self):
        from june.designs import PALETTES, pins_from, resolve, restyle_pins
        first = resolve({}, pins_from('dark themed cafe'), None, 'cafe')
        house = pins_from('editorial')  # a house style named in Templates/house-style.txt
        self.assertEqual(restyle_pins(first, pins_from('change its color theme'), house).get('tone'), 'dark', 'the person said dark; the house default does not undo it')
        self.assertEqual(restyle_pins({}, {}, house), house, 'nothing said before or now: the house style applies')
        self.assertEqual(restyle_pins(first, pins_from('make it light'), house).get('tone'), 'light', 'new words win')

    def test_only_complete_reasons_are_said_to_the_person(self):
        from june.designs import clean_reason, shown_reason
        for broken in ('For a dark-themed Japanese food cafe, targeting adults seeking authentic, cozy, and culturally rich experiences and a calm evening mood for',
                       'For a Sakura Japanese Café, the audience is children and adults seeking a warm, inviting, relaxed place to eat with friends and family after',
                       'Calm'):
            self.assertEqual(shown_reason({'reason': clean_reason(broken)}), '', broken)
        self.assertEqual(shown_reason({'reason': clean_reason('Dark and warm suits an evening cafe.')}), 'Dark and warm suits an evening cafe.')
        self.assertEqual(shown_reason({}), '')


class Model(unittest.IsolatedAsyncioTestCase):
    async def test_june_is_asked_with_every_option_and_her_answer_is_used(self):
        from june import designs
        calls = []
        async def model(client, url, payload, limit, timeout):
            calls.append(payload)
            answer = dict(reason='A kids party: playful.', mood='playful', palette='candy', type='rounded', motif='blobs', cover='poster', layout='cards', heading='highlight')
            return {'message': {'content': json.dumps({designs.FIELD[k]: v for k, v in answer.items()})}}
        with patch('june.knowledge.bounded_json', model):
            got = await designs.choose(None, SimpleNamespace(ollama='http://x', model='m'), 'make a party invite', 'PDF', 'a party')
        self.assertEqual((got['palette'], got['motif'], got['reason']), ('candy', 'blobs', 'A kids party: playful.'))
        self.assertEqual(calls[0]['options']['num_ctx'], 4096); self.assertEqual(calls[0]['format'], designs.SCHEMA)
        async def broken(*args): raise RuntimeError('offline')
        with patch('june.knowledge.bounded_json', broken):
            fallback = await designs.choose(None, SimpleNamespace(ollama='http://x', model='m'), 'x', 'PDF', 'wedding invitation')
        self.assertEqual(fallback['mood'], 'romantic')


if __name__ == '__main__':
    unittest.main()


DRAFT = {'title': 'Garden Birds Through the Year', 'summary': 'Which birds visit a garden in each season & how to help them.',
         'sections': [{'heading': 'Winter visitors', 'text': 'Food is scarce, so feeders matter most.', 'bullets': ['Robins', 'Blue tits', 'Fieldfares', 'Wrens']},
                      {'heading': 'Spring nesting', 'text': 'Birds pair up and build nests.', 'bullets': ['Leave hedges uncut', 'Put up a nest box']},
                      {'heading': 'Summer and autumn', 'text': 'Young birds fledge and later migrate.', 'bullets': []}]}


class Rendering(unittest.TestCase):
    """Every value of every parameter builds a valid file in all four formats."""
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def build_all(self, design, tag):
        from pathlib import Path
        from docx import Document
        from pptx import Presentation
        from pypdf import PdfReader
        from june.creations import inspect
        from june.design_render import render_docx, render_pdf, render_pptx
        from june.websites import inspect_site, site_html
        root = Path(self.tmp.name)
        for kind, render in (('docx', render_docx), ('pptx', render_pptx), ('pdf', render_pdf)):
            path = root / f'{tag}.{kind}'
            render(path, DRAFT, design)
            inspect(path, kind, DRAFT)
        page = root / f'{tag}.html'
        page.write_text(site_html(DRAFT, design)); inspect_site(page, DRAFT)
        text = page.read_text()
        for outside in ('http://', 'https://', '<script', '@import', 'url('):
            self.assertNotIn(outside, text, tag)
        self.assertNotIn('& how', text)
        return root

    def test_every_option_and_palette_and_typeface_builds(self):
        from june.designs import OPTIONS, PALETTES, PARAMS, TYPES, resolve
        base = resolve({'mood': 'friendly'}, {}, None, '')
        for key in PARAMS:
            for value in OPTIONS[key]:
                self.build_all(dict(base, **{key: value}), f'{key}-{value}')
        for pid in PALETTES:
            self.build_all(dict(base, palette=pid), f'palette-{pid}')
        for tid in TYPES:
            self.build_all(dict(base, type=tid), f'type-{tid}')

    def test_designs_really_differ_in_the_files(self):
        from pathlib import Path
        from pptx import Presentation
        from june.design_render import render_pptx
        from june.designs import resolve
        from june.websites import site_html
        a = resolve(dict(mood='playful', palette='candy', type='rounded'), {}, None, '')
        b = resolve(dict(mood='solemn', palette='storm', type='charter'), {}, None, '')
        root = Path(self.tmp.name)
        render_pptx(root / 'a.pptx', DRAFT, a); render_pptx(root / 'b.pptx', DRAFT, b)
        def theme(path):
            deck = Presentation(str(path))
            from pptx.opc.constants import RELATIONSHIP_TYPE as RT
            return deck.slide_master.part.part_related_by(RT.THEME).blob.decode()
        self.assertIn('FF5FA2', theme(root / 'a.pptx')); self.assertNotIn('FF5FA2', theme(root / 'b.pptx'))
        self.assertIn('Seravek', theme(root / 'a.pptx')); self.assertIn('Charter', theme(root / 'b.pptx'))
        self.assertIn('--accent:#FF5FA2', site_html(DRAFT, a)); self.assertIn('--paper:#1C2430', site_html(DRAFT, b))

    def test_the_closing_draft_note_never_sits_alone_on_a_page(self):
        from pathlib import Path
        from docx import Document
        from june.design_render import NOTE, render_docx
        from june.designs import OPTIONS, resolve
        for layout in OPTIONS['layout']:
            path = Path(self.tmp.name) / f'note-{layout}.docx'
            render_docx(path, DRAFT, resolve({'layout': layout}, {'layout': layout}, None, ''))
            body = list(Document(str(path)).element.body.iterchildren())
            texts = [''.join(t.text or '' for t in e.iter() if t.tag.endswith('}t')) for e in body]
            at = texts.index(NOTE)
            before = body[at - 1]
            while before.tag.endswith('}p') and not texts[body.index(before)].strip() and before.xpath('.//w:keepNext'):
                before = body[body.index(before) - 1]
            self.assertTrue(before.xpath('.//w:keepNext'), f'{layout}: the line before the note keeps with it')
            if before.tag.endswith('}p'):
                self.assertTrue(texts[body.index(before)].strip(), f'{layout}: it is a line with words, not a spacer')

    def test_word_documents_stay_readable_on_white_paper_even_in_dark_designs(self):
        from june.design_render import _light
        from june.designs import PALETTES, colours, contrast, resolve
        for pid, palette in PALETTES.items():
            if palette['tone'] != 'dark': continue
            c = _light(colours(dict(resolve({'palette': pid}, {'palette': pid}))))
            self.assertEqual(c['paper'], 'FFFFFF')
            for key in ('ink', 'body', 'muted', 'accent_text'):
                self.assertGreaterEqual(contrast(c[key], c['paper']), 4.5, f'{pid} {key}')
            self.assertGreaterEqual(contrast(c['on_cover'], c['cover']), 4.5, pid); self.assertGreaterEqual(contrast(c['on_tint'], c['tint']), 4.5, pid)
