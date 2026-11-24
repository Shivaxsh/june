"""Documents June writes: a Word document, a presentation or a PDF, saved in her own folder.

The local model drafts the words as structured data. June builds the file herself from that data,
never overwrites an existing file, reads the finished file back to check it, and says plainly that
it is a draft. Nothing leaves this Mac. A template the person puts in the Templates folder gives the
look; its old text is not kept.
"""
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time
import uuid

from .chat import MODEL_KEEP_ALIVE
from . import designs
from .design_render import NOTE, keep_with_note, render_docx, render_pdf, render_pptx
from .errors import JuneError
from .knowledge import bounded_json
from .timers import number

OPEN = '/usr/bin/open'
KINDS = {'docx': ('Word document', 'section'), 'pptx': ('presentation', 'slide'), 'pdf': ('PDF', 'section'), 'site': ('website', 'section')}
_LEAD = (r"\s*(?:(?:ok(?:ay)?|so|well|now|and|oh|um|uh|alright)[,.!\s]+)*(?:(?:hey\s+)?june[,!:\s]+)?(?:(?:can|could|would|will)\s+you\s+|i\s+(?:want|need)\s+(?:you\s+to\s+)?|i['’]d\s+like\s+(?:you\s+to\s+)?)?"
         r"(?:please\s+)?(?:just\s+)?")
_WHAT = (r"(?P<site>(?:simple\s+|small\s+|one[-\s]page\s+|personal\s+)?(?:web\s?site|site|web\s?page|landing\s+page|home\s?page|portfolio(?:\s+(?:web\s?)?site)?))|(?P<word>word\s+(?:doc(?:ument)?|file)|docx|document|doc|report|write-?up|brief)|(?P<deck>power\s?point(?:\s+presentation)?|presentation|pptx?|slide\s+deck|slides|deck)|(?P<pdf>pdf(?:\s+(?:file|report|document))?)")
_STYLE = designs.STYLE_PHRASE
_STYLE_TAIL = (r"(?:\s*,?\s+(?:in|with|using)\s+(?:a\s+|an\s+)?(?P<style_after>" + _STYLE + r")(?:\s+(?:style|theme|look|design|feel|vibes?|aesthetics?|mood|tones?|palette|colou?rs?|colou?r\s+scheme|look\s+and\s+feel))?)")
_CONNECT = r"about|on|for|regarding|explaining|covering|describing|that\s+explains|that|which|where|to|called|named"
REQUEST = re.compile(_LEAD + r"(?:(?:create|make|write|draft|prepare|generate|build|design|produce|(?:put|toss|throw|knock|whip|cook|spin|bang)\s+(?:together|up|out))\s+(?:me\s+|us\s+)?(?:a\s+|an\s+|some\s+|the\s+|my\s+)?"
                     r"|(?:give\s+me|(?:can|could)\s+i\s+(?:get|have)|i\s+(?:want|need)|i['’]d\s+like)\s+(?:a|an)\s+)"
                     r"(?P<pre>(?:(?!(?:" + _CONNECT + r")\b)[\w'’&-]+\s+){0,6}?)(?:" + _WHAT + r")"
                     r"(?:\s+(?P<conn>" + _CONNECT + r")\s+(?P<topic>.+?))?" + _STYLE_TAIL + r"?"
                     r"(?:\s+(?:with|in|using)\s+(?P<count>\d{1,2}|[a-z]+)\s+(?:slides|pages|sections|parts))?" + _STYLE_TAIL.replace('style_after', 'style_end') + r"?"
                     r"(?P<as_pdf>\s+as\s+(?:a\s+)?pdf)?(?:\s+please)?[\s.!]*", re.I | re.S)
# Words before the kind of file that say nothing about its subject.
_FILLER = {'short', 'quick', 'new', 'small', 'little', 'basic', 'one', 'page', 'one-page', 'single', 'nice', 'good', 'beautiful', 'pretty', 'great', 'cool', 'lovely',
           'style', 'styled', 'themed', 'looking', 'simple'}
_IT = r"(?:it|this|that|the\s+(?:document|doc|presentation|deck|slides|pdf|file|report|web\s?site|site|page))"
_COMPARE = r"darker|lighter|brighter|calmer|warmer|cooler|bolder|softer|simpler|cleaner|fancier|prettier|cuter|more\s+[a-z-]+|less\s+[a-z-]+"
# What a comparison means as design words; anything else just asks for a different look.
_COMPARED = {'darker': 'dark', 'lighter': 'light', 'brighter': 'light', 'calmer': 'calm', 'softer': 'calm', 'warmer': 'warm', 'cooler': 'cool', 'bolder': 'bold',
             'simpler': 'minimal', 'cleaner': 'minimal', 'fancier': 'elegant', 'prettier': 'elegant', 'cuter': 'playful', 'less boring': 'energetic', 'less busy': 'minimal',
             'less serious': 'playful', 'less formal': 'friendly', 'more modern': 'futuristic', 'more colourful': 'colourful', 'more colorful': 'colorful', 'serif': 'serif',
             'sans': 'sans', 'sans-serif': 'sans', 'modern': 'modern', 'classic': 'classic'}
_LOOK = r"(?:style|design|look|theme|colou?rs?|colou?r\s+scheme|palette|layout|vibe)"
RESTYLE = re.compile(_LEAD + r"(?:(?:make|do|redo|restyle|redesign|remake|rebuild|design)\s+" + _IT + r"(?:\s+(?:look|again))?\s+(?:(?:in|with|using)\s+)?(?:a\s+|an\s+)?(?:(?:more|bit\s+more|little\s+more)\s+)?"
                     r"(?:(?P<different>different|new|another|fresh|other)(?:\s+" + _LOOK + r")?|(?P<words>" + _STYLE + r")(?:\s+" + _LOOK + r")?)"
                     r"|(?:restyle|redesign)\s+" + _IT + r"(?:\s+(?:in|with|using)\s+(?:a\s+|an\s+)?(?P<words2>" + _STYLE + r")(?:\s+" + _LOOK + r")?)?"
                     r"|(?:try|use|give\s+(?:me|it))\s+(?:a\s+|an\s+)?(?:(?P<different2>different|new|another|other)\s+|(?P<words3>" + _STYLE + r")\s+)" + _LOOK +
                     r"|change\s+(?:the|its|it['’]?s)\s+" + _LOOK + r"(?:\s+(?:to|into)\s+(?:a\s+|an\s+)?(?P<words4>" + _STYLE + r")(?:\s+(?:one|" + _LOOK[3:-1] + r"))?)?"
                     r"|(?:a\s+)?(?:different|another)\s+" + _LOOK +
                     # "make it darker", "make the website calmer", "can it look more modern", "try something more colourful"
                     r"|(?:(?:make|turn)\s+" + _IT + r"(?:\s+look)?|(?:can|could)\s+" + _IT + r"\s+look|try\s+something)\s+(?:a\s+(?:bit|little)\s+|much\s+|way\s+)?(?P<comp>" + _COMPARE + r")"
                     r"|change\s+(?:it|this|that|the\s+(?:theme|colou?rs?|look|style))\s+(?:to|into)\s+(?:a\s+|an\s+)?(?P<words5>" + _STYLE + r")(?:\s+" + _LOOK + r")?"
                     r"|use\s+(?:a\s+)?(?:different\s+|other\s+)?(?P<font>serif|sans(?:-serif)?|modern|classic|different|other|nicer)?\s*fonts?"
                     r")(?:\s+(?:please|for\s+me|instead|now))*[\s.!]*", re.I)
_YES = r"(?:(?:yes|yeah|yep|sure)[,.!\s]+)?"
OPEN_IT = re.compile(_LEAD + _YES + r"(?:open|show(?:\s+me)?|preview)\s+(?:it|that|(?:this|that)\s+one|the\s+one\s+you\s+(?:just\s+)?(?:made|created|wrote|built)|(?:the|that|this|my|my\s+new)\s+(?:new\s+)?(?:word\s+)?(?:document|doc|presentation|deck|slides|pdf|file|report|web\s?site|site|web\s?page|page))"
                     r"(?:\s+up)?(?:\s+(?:to|for)\s+me)?(?:\s+(?:please|now))?[\s.!]*", re.I)
BARE_OPEN = re.compile(_LEAD + _YES + r"(?:open(?:\s+up)?|show\s+me)(?:\s+(?:please|now))?[\s.!]*", re.I)
RECENT = 30 * 60  # how long a bare “open” still means the document June just made
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['title', 'summary', 'sections'], 'properties': {
    'title': {'type': 'string'}, 'summary': {'type': 'string'},
    'sections': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False, 'required': ['heading', 'text', 'bullets'], 'properties': {
        'heading': {'type': 'string'}, 'text': {'type': 'string'}, 'bullets': {'type': 'array', 'items': {'type': 'string'}}}}}}}


def creation_request(text):
    """dict(kind, topic, count) for a request to write a document, else None."""
    if not isinstance(text, str) or len(text) > 400 or re.search(r"\b(?:do not|don['’]?t|never)\b", text, re.I) or '?' in text and re.match(r"\s*(?:how|what|why|when|where|which|who)\b", text, re.I):
        return None
    match = REQUEST.fullmatch(text)
    if not match:
        return None
    styles, words = [], []
    for word in (match['pre'] or '').split():
        bare = re.sub(r'-(?:style|styled|looking|themed)$', '', word.lower())
        if designs.pins_from(bare):
            styles.append(bare)
        elif bare not in _FILLER:
            words.append(word)
    rest = re.sub(r"\s+", ' ', match['topic'] or '').strip(" \t.,;:!\"“”'‘’")
    if words and rest:
        topic = ' '.join(words) + (' ' + match['conn'].lower() + ' ' if match['conn'].lower() in ('about', 'on', 'for', 'to', 'called', 'named', 'regarding') else ': ') + rest
    else:
        topic = rest or ' '.join(words)
    topic = topic.strip(" \t.,;:!\"“”'‘’")
    if not 2 <= len(topic) <= 200 or re.search(r'[\x00-\x1f\x7f]', topic):
        return None
    kind = 'site' if match['site'] else 'pptx' if match['deck'] else 'pdf' if match['pdf'] or match['as_pdf'] else 'docx'
    count = None
    if match['count']:
        count = number(match['count'].lower())
        if count is None or not 2 <= count <= 12:
            return None
    style = ' '.join([*styles, *(x for x in (match['style_after'], match['style_end']) if x)])
    return dict(kind=kind, topic=topic, count=count, style=style)


def restyle_request(text):
    """dict(words) for “make it in a different style / redo it in dark / change the colours”, else None."""
    if not isinstance(text, str) or len(text) > 200 or re.search(r"\b(?:do not|don['’]?t|never|mode)\b", text, re.I):
        return None
    match = RESTYLE.fullmatch(text)
    if not match:
        return None
    words = [x for x in (match['words'], match['words2'], match['words3'], match['words4'], match['words5']) if x]
    for extra in (match['comp'], match['font']):
        if extra:
            key = re.sub(r'\s+', ' ', extra.lower())
            word = _COMPARED.get(key) or (key.split()[-1] if key.startswith('more ') else '')
            if word and designs.pins_from(word):
                words.append(word)
    return dict(words=' '.join(words))


def open_request(text):
    return isinstance(text, str) and OPEN_IT.fullmatch(text) is not None


def bare_open(text):
    """“Open” with nothing after it. It means the last document only just after one was made."""
    return isinstance(text, str) and BARE_OPEN.fullmatch(text) is not None


def _line(value, limit):
    if not isinstance(value, str):
        return ''
    value = re.sub(r'<[^>]{0,80}>', '', value)
    value = re.sub(r'[\x00-\x1f\x7f]+', ' ', value)
    value = re.sub(r'^(?:[\s#*•]+|-\s+|\d{1,2}[.)]\s+)+(?=\S)', '', re.sub(r'\*\*|__|`', '', value))  # list marks, not a title's own number
    return re.sub(r'\s+', ' ', value).strip()[:limit]


def clean_draft(value, count):
    """The model's draft as plain, bounded text, or None when it is not a usable document."""
    if not isinstance(value, dict) or not isinstance(value.get('sections'), list):
        return None
    title = _line(value.get('title'), 120)
    sections = []
    for row in value['sections'][:max(2, min(count, 12))]:
        if not isinstance(row, dict):
            continue
        heading, text = _line(row.get('heading'), 120), _line(row.get('text'), 1200)
        bullets = [b for b in (_line(x, 220) for x in row.get('bullets', []) if isinstance(row.get('bullets'), list)) if b][:8]
        if heading and (text or bullets):
            sections.append(dict(heading=heading, text=text, bullets=bullets))
    if not title or len(sections) < 2:
        return None
    return dict(title=title, summary=_line(value.get('summary'), 600), sections=sections)


def _file_name(title):
    name = re.sub(r'[^\w .()&+-]', ' ', title, flags=re.UNICODE).replace('..', ' ')
    name = re.sub(r'\s+', ' ', name).strip(' .')[:80].strip(' .')
    return name or 'June document'


def build_docx(path, draft, template=None):
    from docx import Document
    document = Document(str(template)) if template else Document()
    body = document.element.body
    for element in list(body):
        if not element.tag.endswith('}sectPr'):
            body.remove(element)  # a template gives styles and page setup, not its old text
    document.core_properties.title = draft['title']
    document.add_heading(draft['title'], 0)
    if draft['summary']:
        lead = document.add_paragraph(draft['summary'])
        if template and 'Subtitle' in document.styles:
            lead.style = document.styles['Subtitle']  # the template's lead-in look
    for section in draft['sections']:
        document.add_heading(section['heading'], 1)
        if section['text']:
            document.add_paragraph(section['text'])
        for bullet in section['bullets']:
            try:
                document.add_paragraph(bullet, style='List Bullet')
            except KeyError:
                document.add_paragraph('• ' + bullet)
    from docx.shared import Pt, RGBColor
    keep_with_note(document)
    note = document.add_paragraph().add_run(NOTE)
    note.italic, note.font.size, note.font.color.rgb = True, Pt(9), RGBColor(0x6B, 0x68, 0x62)
    document.save(str(path))
    return len(draft['sections'])


def build_pptx(path, draft, template=None):
    from pptx import Presentation
    deck = Presentation(str(template)) if template else Presentation()
    ids = deck.slides._sldIdLst
    for item in list(ids):  # drop a template's own slides; keep its layouts and theme
        deck.part.drop_rel(item.rId); ids.remove(item)
    first = deck.slides.add_slide(deck.slide_layouts[0])
    first.shapes.title.text = draft['title']
    if len(first.placeholders) > 1 and draft['summary']:
        first.placeholders[1].text = draft['summary'][:300]
    layout = deck.slide_layouts[1] if len(deck.slide_layouts) > 1 else deck.slide_layouts[0]
    for section in draft['sections']:
        slide = deck.slides.add_slide(layout)
        slide.shapes.title.text = section['heading']
        points = section['bullets'] or [section['text']]
        if len(slide.placeholders) > 1:
            frame = slide.placeholders[1].text_frame
            frame.text = points[0][:220]
            for point in points[1:6]:
                frame.add_paragraph().text = point
        if section['text']:
            slide.notes_slide.notes_text_frame.text = section['text']
    deck.save(str(path))
    return len(draft['sections']) + 1


def inspect(path, kind, draft):
    """Read the finished file back: (parts, pages or None). Raises when it is not what was written."""
    if kind == 'docx':
        from docx import Document
        document = Document(str(path))
        text = '\n'.join([p.text for p in document.paragraphs] + [cell.text for table in document.tables for row in table.rows for cell in row.cells])
        if draft['title'] not in text or draft['sections'][-1]['heading'] not in text: raise ValueError('docx')
        return len(draft['sections']), None
    if kind == 'pptx':
        from pptx import Presentation
        slides = len(Presentation(str(path)).slides)
        if slides != len(draft['sections']) + 1: raise ValueError('pptx')
        return slides, None
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    if not reader.pages or draft['title'].split()[0] not in (reader.pages[0].extract_text() or ''): raise ValueError('pdf')
    return len(draft['sections']), len(reader.pages)


class Creations:
    def __init__(self, data_home, folder=None, opener=None, sites=None):
        self.directory = Path(data_home) / 'tools'
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'creations.sqlite3'
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600); os.close(fd)
        self.folder = Path(folder or Path.home() / 'Documents' / 'June Documents')
        self.sites = Path(sites or self.folder.parent / 'June Websites')
        self.opener = opener or (lambda argv: subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15).returncode)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS creations(id TEXT PRIMARY KEY,kind TEXT NOT NULL,title TEXT NOT NULL,path TEXT NOT NULL,created REAL NOT NULL)')
            have = [r[1] for r in db.execute('PRAGMA table_info(creations)')]
            for column in ('url', 'design', 'draft'):
                if column not in have:
                    db.execute(f'ALTER TABLE creations ADD COLUMN {column} TEXT')

    def db(self):
        db = sqlite3.connect(self.path, timeout=3); db.row_factory = sqlite3.Row; return db

    def state(self):
        with self.db() as db:
            rows = db.execute('SELECT * FROM creations ORDER BY created DESC, rowid DESC LIMIT 50').fetchall()
        return dict(version=1, serverNow=round(time.time() * 1000), folder=self.folder.name,
                    creations=[dict(id=r['id'], kind=r['kind'], title=r['title'], fileName=Path(r['path']).parent.name if r['kind'] == 'site' else Path(r['path']).name,
                                   createdAt=round(r['created'] * 1000), exists=Path(r['path']).is_file(), url=r['url'], design=self._label(r['design'])) for r in rows])

    @staticmethod
    def _label(value):
        try:
            return designs.label(json.loads(value)) or None if value else None
        except (ValueError, TypeError, KeyError):
            return None

    def build(self, kind, draft, design=None):
        """Write one new file in June's chosen design, check it, record it. Never replaces an existing file.
        A template.docx or template.pptx the person put in Templates still sets the look for those kinds."""
        if kind not in KINDS:
            raise JuneError('invalid-creation', 'Choose a Word document, a presentation or a PDF.', 400)
        design = design if isinstance(design, dict) and design.get('palette') in designs.PALETTES else designs.resolve({}, {}, None, draft['title'])
        if kind == 'site':
            return self._build_site(draft, design)
        self.folder.mkdir(parents=True, exist_ok=True)
        base = _file_name(draft['title'])
        path = self.folder / f'{base}.{kind}'
        serial = 2
        while path.exists():
            path = self.folder / f'{base} {serial}.{kind}'; serial += 1
        template = self.folder / 'Templates' / f'template.{kind}'
        own = template.is_file() and kind != 'pdf'
        render = {'docx': render_docx, 'pptx': render_pptx, 'pdf': render_pdf}[kind]
        try:
            try:
                if own:
                    {'docx': build_docx, 'pptx': build_pptx}[kind](path, draft, template)
                else:
                    render(path, draft, design)
            except Exception:
                path.unlink(missing_ok=True)
                own = False
                render(path, draft, design)  # a template June cannot use never blocks the document
            parts, pages = inspect(path, kind, draft)
        except Exception:
            path.unlink(missing_ok=True)
            raise JuneError('creation-failed', 'June could not build that file. Nothing was created.', 500) from None
        cid = uuid.uuid4().hex
        with self.db() as db:
            db.execute('INSERT INTO creations(id,kind,title,path,created,design,draft) VALUES(?,?,?,?,?,?,?)',
                       (cid, kind, draft['title'], str(path), time.time(), None if own else json.dumps(design), json.dumps(draft)))
        return dict(id=cid, kind=kind, title=draft['title'], path=str(path), parts=parts, pages=pages, design=None if own else design)

    def _build_site(self, draft, design):
        from .websites import build_site, inspect_site, site_slug
        self.sites.mkdir(parents=True, exist_ok=True)
        base = site_slug(draft['title'])
        folder, serial = self.sites / base, 2
        while folder.exists():
            folder = self.sites / f'{base}-{serial}'; serial += 1
        folder.mkdir()
        path = folder / 'index.html'
        try:
            build_site(path, draft, design)
            parts, pages = inspect_site(path, draft)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise JuneError('creation-failed', 'June could not build that website. Nothing was created.', 500) from None
        cid = uuid.uuid4().hex
        with self.db() as db:
            db.execute('INSERT INTO creations(id,kind,title,path,created,design,draft) VALUES(?,?,?,?,?,?,?)',
                       (cid, 'site', draft['title'], str(path), time.time(), json.dumps(design), json.dumps(draft)))
        return dict(id=cid, kind='site', title=draft['title'], path=str(path), parts=parts, pages=pages, design=design)

    def house_pins(self, words):
        """Words the person said; else the house style named in Templates/house-style.txt, if any."""
        pins = designs.pins_from(words)
        if pins:
            return pins
        try:
            name = (self.folder / 'Templates' / 'house-style.txt').read_text()[:40].strip().lower()
        except OSError:
            return {}
        return designs.pins_from(name) if name in designs.PRESETS else {}

    def latest(self):
        """The newest creation that still exists, with its stored draft and design (either may be None)."""
        with self.db() as db:
            rows = db.execute('SELECT * FROM creations ORDER BY created DESC, rowid DESC LIMIT 20').fetchall()
        for row in rows:
            if Path(row['path']).is_file():
                def load(value):
                    try: return json.loads(value) if value else None
                    except ValueError: return None
                return dict(id=row['id'], kind=row['kind'], title=row['title'], created=row['created'], draft=load(row['draft']), design=load(row['design']))
        return None

    def _inside(self, kind, path):
        return path.parent.parent == self.sites if kind == 'site' else path.parent == self.folder

    def site(self, cid, present=True):
        """A website June made, for publishing: id, title, folder and slug. Raises when it is not one that still exists
        (with present=False the folder may be gone: taking a published page down needs only its name and address)."""
        with self.db() as db:
            row = db.execute('SELECT * FROM creations WHERE id=?', (cid,)).fetchone() if isinstance(cid, str) else None
        if not row or row['kind'] != 'site':
            raise JuneError('creation-missing', 'That is not one of the websites June made.', 404)
        path = Path(row['path'])
        if (present and not path.is_file()) or not self._inside('site', path):
            raise JuneError('creation-missing', 'That website’s folder was moved or deleted.', 404)
        return dict(id=row['id'], title=row['title'], folder=str(path.parent), slug=path.parent.name, url=row['url'])

    def set_url(self, cid, url):
        with self.db() as db:
            db.execute("UPDATE creations SET url=? WHERE id=? AND kind='site'", (url, cid))

    def open(self, cid, reveal=False):
        with self.db() as db:
            row = db.execute('SELECT kind, path FROM creations WHERE id=?', (cid,)).fetchone() if isinstance(cid, str) else None
        if not row:
            raise JuneError('creation-missing', 'That document is not in June’s list.', 404)
        path = Path(row['path'])
        if not path.is_file() or not self._inside(row['kind'], path):
            raise JuneError('creation-missing', 'That file was moved or deleted.', 404)
        if self.opener([OPEN, '-R', str(path)] if reveal else [OPEN, str(path)]) != 0:
            raise JuneError('creation-open', 'The Mac could not open that file.', 503)
        return self.state()

    async def draft(self, client, settings, kind, topic, count):
        label, part = KINDS[kind]
        count = count or (6 if kind == 'pptx' else 4)
        if kind == 'site':
            prompt = (f'Write the text of a one-page website for the request below. Reply with JSON only: the site name as the title, a one-sentence tagline as the summary, '
                      f'and exactly {count} sections. Each section has a short heading, a paragraph of 2 to 4 sentences in "text", and 0 to 4 short bullet points. '
                      'Use plain text only: no markdown, no HTML, no placeholders in brackets. Do not invent names of people, prices, addresses, phone numbers, email addresses, '
                      'opening hours, statistics or quotations; write so the owner can add those later.')
            result = await bounded_json(client, settings.ollama + '/api/chat', {
                'model': settings.model, 'stream': False, 'think': False, 'format': SCHEMA, 'keep_alive': MODEL_KEEP_ALIVE,
                'messages': [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': topic}],
                'options': {'temperature': 0.4, 'num_ctx': 4096, 'num_predict': 1500},
            }, 65536, 420)
            return clean_draft(json.loads(result['message']['content']), count)
        sections = count - 1 if kind == 'pptx' else count
        prompt = (f'Write the content of a {label} for the request below. Reply with JSON only: a short title, a one or two sentence summary, and exactly {sections} sections. '
                  + ('Each section is one slide: a short heading, 3 to 5 short bullet points, and one or two sentences of speaker notes in "text".' if kind == 'pptx'
                     else 'Each section has a heading, a paragraph of 3 to 5 sentences in "text", and 2 to 4 bullet points with the key facts.')
                  + ' Use plain text only: no markdown, no numbering, no placeholders. Be accurate and concrete; do not invent statistics, names or quotations.')
        result = await bounded_json(client, settings.ollama + '/api/chat', {
            'model': settings.model, 'stream': False, 'think': False, 'format': SCHEMA, 'keep_alive': MODEL_KEEP_ALIVE,
            'messages': [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': topic}],
            'options': {'temperature': 0.3, 'num_ctx': 4096, 'num_predict': 1500},
        }, 65536, 420)
        return clean_draft(json.loads(result['message']['content']), sections)

    async def chat(self, question, client, settings):
        """App-owned reply: write the requested document, or open the last one. None when it is neither."""
        bare = bare_open(question)
        if bare or open_request(question):
            rows = [c for c in self.state()['creations'] if c['exists']]
            if bare and not (rows and time.time() - rows[0]['createdAt'] / 1000 <= RECENT):
                return None
            if not rows:
                return dict(reply='I haven’t made a document yet. Ask me, for example: create a presentation about solar power.')
            try:
                self.open(rows[0]['id'])
            except JuneError as failure:
                return dict(reply=failure.message)
            return dict(reply=f'Opened “{rows[0]["title"]}”.')
        restyle = restyle_request(question)
        if restyle is not None:
            last = self.latest()
            if not last or time.time() - last['created'] > RECENT * 4:
                return None  # long after the last document, “make it …” is about something else
            if not last['draft']:
                return dict(reply='I can only restyle documents I made after designs were added. Ask me to make it again and I’ll choose a fresh look.')
            label = KINDS[last['kind']][0]
            design = await designs.choose(client, settings, question, label, last['title'], designs.restyle_pins(last['design'], designs.pins_from(restyle['words']), self.house_pins('')), avoid=last['design'])
            return self._finish(last['kind'], last['draft'], design, restyled=True)
        request = creation_request(question)
        if request is None:
            return None
        try:
            draft = await self.draft(client, settings, request['kind'], request['topic'], request['count'])
        except Exception:
            draft = None
        if draft is None:
            return dict(reply='I couldn’t write that document this time. Nothing was created. Try again, or give me a narrower topic.')
        design = await designs.choose(client, settings, question, KINDS[request['kind']][0], request['topic'], self.house_pins(request['style']))
        return self._finish(request['kind'], draft, design)

    def _finish(self, kind, draft, design, restyled=False):
        try:
            made = self.build(kind, draft, design)
        except JuneError as failure:
            return dict(reply=failure.message)
        label, part = KINDS[made['kind']]
        look = ''
        if made.get('design'):
            chosen = made['design']
            look = (f' I gave it a {chosen["mood"]} look: {designs.describe(chosen)}.' + (f' {designs.shown_reason(chosen)}' if designs.shown_reason(chosen) else ''))
        else:
            look = ' It uses your own template from the Templates folder.'
        verb = 'restyled' if restyled else 'created'
        if made['kind'] == 'site':
            return dict(creation=made['id'], reply=f'I’ve {"restyled" if restyled else "built"} “{made["title"]}” as a one-page website ({made["parts"]} sections).{look} It is saved in Documents → {self.sites.name} → '
                        f'{Path(made["path"]).parent.name}. It’s a draft from my local model, so read it first. Say “open it” to preview it, “make it in a different style” for another look, or “publish it” to put it online.')
        size = f'{made["parts"]} {part}s' + (f', {made["pages"]} page{"" if made["pages"] == 1 else "s"}' if made['pages'] else '')
        return dict(creation=made['id'], reply=f'I’ve {verb} “{made["title"]}” as a {label} ({size}).{look} It is saved as {Path(made["path"]).name} in Documents → {self.folder.name}. '
                    'It’s a draft from my local model, so check the facts. Say “open it” to open it, or “make it in a different style” for another look.')

