"""Draw June's documents from a design (see designs.py): presentations, Word documents and PDFs.

Each format reads the same design: palette, fonts, motif, cover, content layout, heading treatment,
bullet glyph, corners, line weight, density and accent use. Text is always the draft's own words.
"""
import re

from .designs import OPTIONS, PALETTES, TYPES, colours, mix

NOTE = 'Draft written by June’s local model. Check facts and figures before using it.'
SCALE = {'airy': 1.0, 'balanced': 0.94, 'compact': 0.86}
GLYPH = {'square': '■', 'dot': '●', 'dash': '–', 'arrow': '→', 'check': '✓'}


def _font(design):
    return TYPES[design['type']]


def _light(c):
    """A dark palette on white paper: Word drops page colour when printing and in previews."""
    from .designs import contrast, readable
    if c['tone'] != 'dark':
        return c
    dark = dict(c)
    paper = 'FFFFFF'
    dark.update(paper=paper, surface=mix(c['paper'], paper, 0.92), line=mix(c['paper'], paper, 0.8), ink=readable(c['paper'], paper, 7),
                body=readable(mix(c['paper'], '333333', 0.4), paper, 7), muted=readable(c['muted'], paper, 4.5), cover=c['paper'], on_cover=c['ink'],
                on_cover_muted=c['body'] if contrast(c['body'], c['paper']) >= 4.5 else c['ink'], accent_text=readable(c['accent'], paper, 4.5),
                accent_shape=readable(c['accent'], paper, 2.2), tint=mix(c['accent'], paper, 0.86))
    dark['on_tint'] = readable(dark['ink'], dark['tint'], 4.5)
    dark['tone'] = 'light'
    return dark


# ============================================================ PowerPoint ====================================
def render_pptx(path, draft, design):
    from lxml import etree
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    from pptx.oxml.ns import qn
    from pptx.util import Emu, Pt

    c, t = colours(design), _font(design)
    scale = SCALE[design['density']]
    W, H = 12192000, 6858000
    IN = 914400
    margin = int({'airy': 0.95, 'balanced': 0.8, 'compact': 0.62}[design['density']] * IN)
    stroke = {'hairline': 6350, 'regular': 15875, 'heavy': 44450}[design['lines']]
    radius = {'sharp': 0.0, 'soft': 0.08, 'round': 0.32}[design['corners']]
    deck = Presentation()
    deck.slide_width, deck.slide_height = Emu(W), Emu(H)
    theme = deck.slide_master.part.part_related_by(RT.THEME)
    blob = theme.blob.decode('utf-8')
    blob = re.sub(r'(<a:majorFont>\s*<a:latin typeface=")[^"]*', r'\g<1>' + t['head'], blob)
    blob = re.sub(r'(<a:minorFont>\s*<a:latin typeface=")[^"]*', r'\g<1>' + t['body'], blob)
    for slot, colour in (('dk1', c['ink']), ('lt1', c['paper']), ('dk2', c['body']), ('lt2', c['surface']), ('accent1', c['accent']), ('accent2', c['accent2']),
                         ('accent3', c['accent_text']), ('accent4', c['muted']), ('accent5', c['tint']), ('accent6', c['line']), ('hlink', c['accent_text']), ('folHlink', c['muted'])):
        blob = re.sub(rf'<a:{slot}>.*?</a:{slot}>', f'<a:{slot}><a:srgbClr val="{colour}"/></a:{slot}>', blob, flags=re.S)
    theme._blob = blob.encode('utf-8')
    layout = deck.slide_layouts[5]  # title only: a real title placeholder, everything else drawn by June

    def rgb(value): return RGBColor.from_string(value)

    def shape(slide, x, y, w, h, fill=None, kind=MSO_SHAPE.RECTANGLE, line=None, rotation=0.0, rounded=None):
        item = slide.shapes.add_shape(kind, Emu(int(x)), Emu(int(y)), Emu(max(1, int(w))), Emu(max(1, int(h))))
        if fill:
            item.fill.solid(); item.fill.fore_color.rgb = rgb(fill)
        else:
            item.fill.background()
        if line:
            item.line.color.rgb = rgb(line[0]); item.line.width = Emu(line[1])
        else:
            item.line.fill.background()
        if rotation: item.rotation = rotation
        if rounded is not None and kind == MSO_SHAPE.ROUNDED_RECTANGLE: item.adjustments[0] = rounded
        sp = item._element.spPr
        sp.append(etree.SubElement(sp, qn('a:effectLst')))  # no default shadow
        return item

    def runs(paragraph, text, font, size, colour, bold=False, caps=False, spacing=0, italic=False):
        run = paragraph.add_run(); run.text = text
        run.font.name, run.font.size, run.font.bold, run.font.italic = font, Pt(size), bold, italic
        run.font.color.rgb = rgb(colour)
        props = run._r.get_or_add_rPr()
        if caps: props.set('cap', 'all')
        if spacing: props.set('spc', str(spacing))
        for tag in ('a:ea', 'a:cs'):
            props.append(etree.fromstring(f'<{tag} xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" typeface="{font}"/>'))
        return run

    def frame(item, anchor='t', wrap=True):
        tf = item.text_frame; tf.word_wrap = wrap
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = {'t': MSO_ANCHOR.TOP, 'm': MSO_ANCHOR.MIDDLE, 'b': MSO_ANCHOR.BOTTOM}[anchor]
        return tf

    def text(slide, x, y, w, h, value, font, size, colour, bold=False, anchor='t', align='l', caps=False, spacing=0, line=1.0):
        box = slide.shapes.add_textbox(Emu(int(x)), Emu(int(y)), Emu(int(w)), Emu(int(h)))
        tf = frame(box, anchor)
        p = tf.paragraphs[0]; p.alignment = {'l': PP_ALIGN.LEFT, 'c': PP_ALIGN.CENTER, 'r': PP_ALIGN.RIGHT}[align]; p.line_spacing = line
        runs(p, value, font, size, colour, bold, caps, spacing)
        return box

    def heading(slide, value, x, y, w, h, size, colour, align='l', anchor='b'):
        title = slide.shapes.title
        title.left, title.top, title.width, title.height = Emu(int(x)), Emu(int(y)), Emu(int(w)), Emu(int(h))
        tf = frame(title, anchor)
        tf.text = ''
        p = tf.paragraphs[0]; p.alignment = {'l': PP_ALIGN.LEFT, 'c': PP_ALIGN.CENTER}[align]; p.line_spacing = 0.95
        runs(p, value, t['head'], size, colour, t['head_bold'], caps=design['heading'] == 'smallcaps' and size < 40, spacing=180 if design['heading'] == 'smallcaps' else 0)
        bodyPr = tf._txBody.find(qn('a:bodyPr'))
        for child in list(bodyPr): bodyPr.remove(child)
        bodyPr.append(etree.fromstring('<a:normAutofit xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"/>'))
        return title

    def bullets(tf, points, size, colour, start=0):
        for n, point in enumerate(points):
            p = tf.paragraphs[0] if n == 0 and not tf.paragraphs[0].runs else tf.add_paragraph()
            p.space_after = Pt(int(9 * scale)); p.line_spacing = 1.08
            pPr = p._p.get_or_add_pPr(); indent = int(0.34 * IN)
            pPr.set('marL', str(indent)); pPr.set('indent', str(-indent))
            for child in list(pPr): pPr.remove(child)
            pPr.append(etree.fromstring(f'<a:buClr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:srgbClr val="{c["accent_text"]}"/></a:buClr>'))
            if design['bullet'] == 'number':
                pPr.append(etree.fromstring(f'<a:buFont xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" typeface="{t["body"]}"/>'))
                pPr.append(etree.fromstring(f'<a:buAutoNum xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" type="arabicPeriod" startAt="{start + n + 1}"/>'))
            else:
                pPr.append(etree.fromstring('<a:buSzPct xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" val="85000"/>'))
                pPr.append(etree.fromstring('<a:buFont xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" typeface="Arial"/>'))
                pPr.append(etree.fromstring(f'<a:buChar xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" char="{GLYPH[design["bullet"]]}"/>'))
            runs(p, point, t['body'], size, colour)

    def raise_title(slide):
        """The title placeholder comes from the layout first; bring it above the shapes June drew."""
        title = slide.shapes.title
        if title is not None:
            tree = title._element.getparent(); tree.remove(title._element); tree.append(title._element)

    def background(slide, colour):
        slide.background.fill.solid(); slide.background.fill.fore_color.rgb = rgb(colour)

    def motif(slide, x, y, w, h, on, strong=True):
        """Decoration inside an area; `on` is the colour underneath."""
        kind = design['motif']
        first = c['accent'] if on != c['accent'] else c['accent2']
        second = mix(on, c['accent2'] if on != c['accent2'] else c['paper'], 0.35)
        soft = mix(on, first, 0.22)
        if kind == 'circles':
            d = min(w, h) * (1.0 if strong else 0.5)
            shape(slide, x + w - d * 0.75, y - d * 0.25, d, d, first, MSO_SHAPE.OVAL)
            shape(slide, x + w - d * 1.05, y + d * 0.55, d * 0.32, d * 0.32, second, MSO_SHAPE.OVAL)
        elif kind == 'slabs':
            for n in range(3 if strong else 1):
                shape(slide, x + w * (0.55 + n * 0.14), y - h * 0.2, w * 0.1, h * 1.5, (first, second, soft)[n], rotation=18)
        elif kind == 'stripes':
            for n in range(6 if strong else 3):
                shape(slide, x + w - (n + 1) * w * 0.05, y, w * 0.022, h, first if n % 2 == 0 else second)
        elif kind == 'dots':
            step = min(w, h) / (9 if strong else 6)
            for row in range(5 if strong else 3):
                for col in range(6 if strong else 4):
                    shape(slide, x + w - (col + 1) * step, y + step * (row + 0.6), step * 0.32, step * 0.32, first if (row + col) % 3 else second, MSO_SHAPE.OVAL)
        elif kind == 'grid':
            step = int(0.55 * IN)
            for gx in range(int(x + w * (0.45 if strong else 0.75)), int(x + w), step):
                shape(slide, gx, y, max(6350, stroke // 2), h, soft)
            for gy in range(int(y), int(y + h), step):
                shape(slide, x + w * (0.45 if strong else 0.75), gy, w * (0.55 if strong else 0.25), max(6350, stroke // 2), soft)
        elif kind == 'blobs':
            d = min(w, h) * (0.9 if strong else 0.45)
            shape(slide, x + w - d * 0.8, y - d * 0.2, d, d * 0.8, first, MSO_SHAPE.ROUNDED_RECTANGLE, rotation=-12, rounded=0.5)
            shape(slide, x + w - d * 1.1, y + d * 0.55, d * 0.45, d * 0.38, second, MSO_SHAPE.ROUNDED_RECTANGLE, rotation=20, rounded=0.5)
        elif kind == 'frame':
            inset = int(0.28 * IN)
            shape(slide, x + inset, y + inset, w - 2 * inset, h - 2 * inset, None, line=(first, max(stroke, 9525)))
        elif kind == 'rules':
            shape(slide, x + margin, y + h - int(0.5 * IN), w - 2 * margin, max(stroke, 9525), first)
            if strong: shape(slide, x + margin, y + int(0.45 * IN), w * 0.3, max(stroke, 9525), second)
        elif kind == 'waves':
            for n in range(3 if strong else 2):
                shape(slide, x - w * 0.1 + n * w * 0.12, y + h * (0.72 + n * 0.08), w * 1.0, h * 0.5, (soft, second, first)[n], MSO_SHAPE.OVAL)

    total = len(draft['sections']) + 1

    # ---- cover ----
    cover = deck.slides.add_slide(layout)
    title_size = 54 if len(draft['title']) < 40 else 44 if len(draft['title']) < 70 else 36
    kind = design['cover']
    if kind == 'bleed':
        background(cover, c['cover']); motif(cover, W * 0.5, 0, W * 0.5, H, c['cover'])
        heading(cover, draft['title'], margin, H * 0.28, W * 0.5 - margin, H * 0.4, title_size * 0.92, c['on_cover'])
        sub_y, sub_c, width = H * 0.7, c['on_cover_muted'], W * 0.5 - margin
    elif kind == 'split':
        background(cover, c['paper']); shape(cover, 0, 0, W * 0.52, H, c['cover']); motif(cover, W * 0.52, 0, W * 0.48, H, c['paper'])
        heading(cover, draft['title'], margin, H * 0.22, W * 0.52 - 2 * margin, H * 0.46, title_size * 0.88, c['on_cover'])
        sub_y, sub_c, width = H * 0.7, c['on_cover_muted'], W * 0.52 - 2 * margin
    elif kind == 'band':
        background(cover, c['paper']); motif(cover, 0, 0, W, H * 0.3, c['paper'], strong=False)
        shape(cover, 0, H * 0.3, W, H * 0.4, c['cover'])
        heading(cover, draft['title'], margin, H * 0.3, W - 2 * margin, H * 0.4, title_size, c['on_cover'], align='c', anchor='m')
        sub_y, sub_c, width = H * 0.74, c['body'], W - 2 * margin
    elif kind == 'numeral':
        background(cover, c['paper']); motif(cover, 0, 0, W, H, c['paper'], strong=False)
        initial = (re.findall(r'[A-Za-z0-9]', draft['title']) or ['J'])[0].upper()
        text(cover, W * 0.55, -H * 0.08, W * 0.45, H * 1.1, initial, t['head'], 420, c['tint'], True, 'm', 'c')
        heading(cover, draft['title'], margin, H * 0.3, W * 0.56, H * 0.38, title_size, c['ink'])
        sub_y, sub_c, width = H * 0.7, c['body'], W * 0.5
    elif kind == 'column':
        background(cover, c['paper']); shape(cover, 0, 0, W * 0.3, H, c['cover']); motif(cover, 0, 0, W * 0.3, H, c['cover'], strong=False)
        heading(cover, draft['title'], W * 0.3 + margin, H * 0.25, W * 0.7 - 2 * margin, H * 0.42, title_size, c['ink'])
        sub_y, sub_c, width = H * 0.69, c['body'], W * 0.7 - 2 * margin
        margin_left = W * 0.3 + margin
    else:  # poster
        back = c['cover'] if design['accent'] == 'generous' else c['paper']
        fore = c['on_cover'] if back == c['cover'] else c['ink']
        background(cover, back); motif(cover, 0, H * 0.62, W, H * 0.38, back, strong=False)
        heading(cover, draft['title'], margin, margin * 0.8, W - 2 * margin, H * 0.6, title_size * 1.3, fore, anchor='t')
        sub_y, sub_c, width = H * 0.66, c['on_cover_muted'] if back == c['cover'] else c['body'], W * 0.62
    sub_x = W * 0.3 + margin if kind == 'column' else margin
    if kind == 'band':
        sub_x = margin
    if draft['summary']:
        text(cover, sub_x, sub_y, width, H * 0.2, draft['summary'][:300], t['body'], 18 * scale, sub_c, align='c' if kind == 'band' else 'l')
    raise_title(cover)

    # ---- content ----
    for number, section in enumerate(draft['sections'], 1):
        slide = deck.slides.add_slide(layout)
        background(slide, c['paper'])
        # Decoration stays in a small top corner, clear of the heading, and is left out where the slide
        # is already full (side panel, cards, highlighted heading).
        if (design['accent'] == 'generous' or design['motif'] in ('frame', 'grid')) and design['layout'] not in ('side-panel', 'cards') and design['heading'] != 'highlight':
            motif(slide, W * 0.8, 0, W * 0.2, int(0.62 * IN), c['paper'], strong=False)
        left, top, width = margin, int(0.55 * IN), W - 2 * margin
        style = design['layout']
        if style == 'margin-number':
            text(slide, margin, int(0.55 * IN), W * 0.2, H * 0.4, f'{number:02d}', t['head'], 88 * scale, c['accent_text'], True)
            left, width = margin + W * 0.2, W - 2 * margin - W * 0.2
        if design['heading'] == 'bar':
            shape(slide, left, top, int(0.7 * IN), max(stroke * 2, 50800), c['accent_shape'])
        if design['heading'] == 'number' and style != 'margin-number':
            text(slide, left, top - int(0.05 * IN), width, int(0.35 * IN), f'{number:02d}', t['body'], 14, c['accent_text'], True, spacing=200)
        if design['heading'] == 'highlight':
            shape(slide, left - int(0.15 * IN), top + int(0.15 * IN), width + int(0.3 * IN), int(1.15 * IN), c['tint'], MSO_SHAPE.ROUNDED_RECTANGLE, rounded=radius)
        heading(slide, section['heading'], left, top + int(0.2 * IN), width, int(1.05 * IN), 32 * scale, c['on_tint'] if design['heading'] == 'highlight' else c['ink'])
        if design['heading'] == 'underline':
            shape(slide, left, top + int(1.32 * IN), width, max(stroke, 9525), c['accent_shape'])
        body_top = top + int(1.55 * IN)
        body_h = H - body_top - int(0.8 * IN)
        points = (section['bullets'] or [section['text']])[:5]
        size = (24 if len(points) <= 3 else 21) * scale
        if style == 'side-panel':
            panel_w = width * 0.36
            shape(slide, left + width - panel_w, body_top, panel_w, body_h, c['tint'], MSO_SHAPE.ROUNDED_RECTANGLE, rounded=min(radius, 0.06))  # a tall panel never turns into a pill
            if section['text']:
                text(slide, left + width - panel_w + int(0.3 * IN), body_top + int(0.3 * IN), panel_w - int(0.6 * IN), body_h - int(0.6 * IN), section['text'][:420],
                     t['body'], 17 * scale, c['on_tint'], line=1.15)
            box = slide.shapes.add_textbox(Emu(int(left)), Emu(int(body_top)), Emu(int(width - panel_w - 0.4 * IN)), Emu(int(body_h)))
            bullets(frame(box), points, size, c['body'])
        elif style == 'two-column' and len(points) > 2:
            half = (len(points) + 1) // 2
            for col, chunk in enumerate((points[:half], points[half:])):
                box = slide.shapes.add_textbox(Emu(int(left + col * width / 2)), Emu(int(body_top)), Emu(int(width / 2 - 0.3 * IN)), Emu(int(body_h)))
                bullets(frame(box), chunk, size, c['body'], start=0 if col == 0 else half)
        elif style == 'cards':
            cols = 2 if len(points) <= 4 else 3
            rows = (len(points) + cols - 1) // cols
            gap = int(0.25 * IN)
            cw, ch = (width - gap * (cols - 1)) / cols, min((body_h - gap * (rows - 1)) / rows, 1.7 * IN)
            for n, point in enumerate(points):
                cx, cy = left + (n % cols) * (cw + gap), body_top + (n // cols) * (ch + gap)
                shape(slide, cx, cy, cw, ch, c['surface'], MSO_SHAPE.ROUNDED_RECTANGLE, line=(c['line'], 9525), rounded=radius)
                mark = f'{n + 1:02d}' if design['bullet'] == 'number' else GLYPH[design['bullet']]
                text(slide, cx + int(0.25 * IN), cy + int(0.2 * IN), cw - int(0.5 * IN), int(0.4 * IN), mark, t['head'], 16, c['accent_text'], True)
                text(slide, cx + int(0.25 * IN), cy + int(0.62 * IN), cw - int(0.5 * IN), ch - int(0.8 * IN), point, t['body'], (18 if cols == 2 else 16) * scale, c['ink'], line=1.1)
        else:
            box = slide.shapes.add_textbox(Emu(int(left)), Emu(int(body_top)), Emu(int(width)), Emu(int(body_h)))
            bullets(frame(box), points, size, c['body'])
        text(slide, margin, H - int(0.55 * IN), W * 0.6, int(0.3 * IN), 'Draft · check the facts', t['body'], 9, c['muted'], spacing=100)
        text(slide, W - margin - W * 0.2, H - int(0.55 * IN), W * 0.2, int(0.3 * IN), f'{number + 1} / {total}', t['body'], 9, c['muted'], align='r')
        raise_title(slide)
        if section['text']:
            slide.notes_slide.notes_text_frame.text = section['text']
    deck.core_properties.title = draft['title']; deck.core_properties.author = 'June'
    deck.save(str(path))
    return total


# ============================================================ Word ==========================================
def keep_with_note(document):
    """Keep the closing draft note on the same page as the last real text: Word may otherwise push it alone onto a new page.
    Walks back over empty spacer paragraphs and a final table row to the last line with words, marking each keep-with-next."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    for element in reversed(list(document.element.body.iterchildren())):
        tag = element.tag.rsplit('}', 1)[-1]
        if tag == 'p':
            paragraph = Paragraph(element, document)
            paragraph.paragraph_format.keep_with_next = True
            if paragraph.text.strip():
                return
        elif tag == 'tbl':
            for cell in Table(element, document).rows[-1].cells:
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.keep_with_next = True
            return


def render_docx(path, draft, design):
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls, qn
    from docx.shared import Mm, Pt, RGBColor

    c, t = _light(colours(design)), _font(design)
    scale = SCALE[design['density']]
    border = {'hairline': 6, 'regular': 12, 'heavy': 30}[design['lines']]
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    side = {'airy': 26, 'balanced': 22, 'compact': 18}[design['density']]
    section.left_margin = section.right_margin = Mm(side)
    section.top_margin, section.bottom_margin = Mm(side), Mm(side - 2)

    def colour(run, value): run.font.color.rgb = RGBColor.from_string(value)

    def fonts(element, family):
        rfonts = element.get_or_add_rPr().get_or_add_rFonts()
        for key in ('ascii', 'hAnsi', 'cs', 'eastAsia'): rfonts.set(qn(f'w:{key}'), family)
        for key in ('asciiTheme', 'hAnsiTheme', 'cstheme', 'eastAsiaTheme'): rfonts.attrib.pop(qn(f'w:{key}'), None)

    def style(name, family, size, ink, bold=False, before=0, after=8, line=1.3):
        item = document.styles[name]
        item.font.name, item.font.size, item.font.bold, item.font.italic = family, Pt(size), bold, False
        item.font.color.rgb = RGBColor.from_string(ink)
        fonts(item.element, family)
        fmt = item.paragraph_format
        fmt.space_before, fmt.space_after, fmt.line_spacing = Pt(before), Pt(after), line
        return item

    def shade(element_pr, fill):
        element_pr.append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{fill}"/>'))

    def edge(paragraph, side_name, size, colour_value, space=6):
        pPr = paragraph._p.get_or_add_pPr()
        borders = pPr.find(qn('w:pBdr'))
        if borders is None:
            borders = parse_xml(f'<w:pBdr {nsdecls("w")}/>')
            anchor = next((pPr.find(qn(f'w:{tag}')) for tag in ('shd', 'tabs', 'spacing', 'ind', 'jc') if pPr.find(qn(f'w:{tag}')) is not None), None)
            anchor.addprevious(borders) if anchor is not None else pPr.append(borders)
        borders.append(parse_xml(f'<w:{side_name} {nsdecls("w")} w:val="single" w:sz="{size}" w:space="{space}" w:color="{colour_value}"/>'))

    style('Normal', t['body'], 11 * scale, c['body'], after=9 * scale, line=1.35)
    style('Title', t['head'], 32 * scale, c['ink'], t['head_bold'], after=10, line=1.05)
    style('Subtitle', t['body'], 13 * scale, c['muted'], after=14)
    h1 = style('Heading 1', t['head'], 18 * scale, c['ink'], t['head_bold'], before=22 * scale, after=8, line=1.1)
    h1.paragraph_format.keep_with_next = True
    for name in ('Header', 'Footer'):
        style(name, t['body'], 8.5, c['muted'], after=0)
    if design['heading'] == 'smallcaps':
        rpr = h1.element.get_or_add_rPr()
        rpr.append(parse_xml(f'<w:smallCaps {nsdecls("w")}/>')); rpr.append(parse_xml(f'<w:spacing {nsdecls("w")} w:val="30"/>'))

    body = document.element.body
    for element in list(body):
        if not element.tag.endswith('}sectPr'): body.remove(element)

    def block(fill, rows, width_split=None):
        """A borderless table used as a coloured cover block."""
        table = document.add_table(rows=1, cols=len(rows))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        tblPr = table._tbl.tblPr
        tblPr.append(parse_xml(f'<w:tblBorders {nsdecls("w")}>' + ''.join(f'<w:{s} w:val="nil"/>' for s in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV')) + '</w:tblBorders>'))
        for n, (fill_value, fill_rows) in enumerate(rows):
            cell = table.rows[0].cells[n]
            if fill_value: shade(cell._tc.get_or_add_tcPr(), fill_value)
            cell.paragraphs[0].text = ''
            for i, (text_value, size, ink, family, bold) in enumerate(fill_rows):
                p = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
                p.paragraph_format.space_before = Pt(18 if i == 0 else 4); p.paragraph_format.space_after = Pt(18 if i == len(fill_rows) - 1 else 6)
                p.paragraph_format.left_indent = p.paragraph_format.right_indent = Mm(6)
                r = p.add_run(text_value); r.font.size, r.font.bold, r.font.name = Pt(size), bold, family; colour(r, ink); fonts(r._r, family)
        if width_split:
            for n, share in enumerate(width_split):
                table.rows[0].cells[n].width = Mm((210 - 2 * side) * share)
        return table

    title, summary = draft['title'], draft['summary']
    big = 34 * scale if len(title) < 50 else 28 * scale
    kind = design['cover']
    if kind == 'bleed':
        block(None, [(c['cover'], [(title, big, c['on_cover'], t['head'], t['head_bold'])] + ([(summary, 12.5, c['on_cover_muted'], t['body'], False)] if summary else []))])
    elif kind == 'split':
        block(None, [(c['cover'], [(title, big * 0.9, c['on_cover'], t['head'], t['head_bold'])]), (c['tint'], [(summary or ' ', 12, c['on_tint'], t['body'], False)])], (0.55, 0.45))
    elif kind == 'column':
        block(None, [(c['cover'], [(' ', 10, c['on_cover'], t['body'], False)]), (None, [(title, big, c['ink'], t['head'], t['head_bold'])] + ([(summary, 12.5, c['muted'], t['body'], False)] if summary else []))], (0.12, 0.88))
    else:
        if kind == 'numeral':
            p = document.add_paragraph(); r = p.add_run((re.findall(r'[A-Za-z0-9]', title) or ['J'])[0].upper()); r.font.size = Pt(110); r.font.bold = True; colour(r, c['accent_shape']); r.font.name = t['head']; fonts(r._r, t['head'])
            p.paragraph_format.space_after = Pt(0); p.paragraph_format.line_spacing = 0.9
        heading = document.add_heading(title, 0)
        if kind == 'poster':
            for r in heading.runs: r.font.size = Pt(44 * scale)
        if kind == 'band':
            edge(heading, 'top', border * 3, c['accent_shape'], 14); edge(heading, 'bottom', border * 3, c['accent_shape'], 14)
            heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        else:
            edge(heading, 'bottom', border * 2, c['accent_shape'], 10)
        if summary:
            lead = document.add_paragraph(summary, style='Subtitle')
            if kind == 'band': lead.alignment = WD_ALIGN_PARAGRAPH.CENTER
    ornament = {'circles': '●  ○  ●', 'dots': '·  ·  ·  ·  ·  ·  ·  ·', 'stripes': '▮▮▮▮▮▮', 'grid': '┼   ┼   ┼   ┼', 'slabs': '◢◤◢◤◢◤', 'blobs': '⬮  ⬯  ⬮',
                'waves': '〰〰〰〰', 'rules': '', 'frame': '', 'none': ''}[design['motif']]
    if ornament:
        p = document.add_paragraph(); r = p.add_run(ornament); r.font.size = Pt(14); colour(r, c['accent_shape'])
        p.paragraph_format.space_before = Pt(10)
    if design['motif'] == 'rules':
        edge(document.add_paragraph(), 'bottom', border, c['line'], 1)
    if design['motif'] == 'frame':
        section._sectPr.append(parse_xml(f'<w:pgBorders {nsdecls("w")} w:offsetFrom="page">' + ''.join(
            f'<w:{s} w:val="single" w:sz="{max(border, 8)}" w:space="24" w:color="{c["accent_shape"]}"/>' for s in ('top', 'left', 'bottom', 'right')) + '</w:pgBorders>'))
    if design['layout'] == 'two-column':
        flow = document.add_section(WD_SECTION.CONTINUOUS)
        flow._sectPr.append(parse_xml(f'<w:cols {nsdecls("w")} w:num="2" w:space="567"/>'))

    def point_line(container, text_value, n):
        p = container.add_paragraph()
        p.paragraph_format.left_indent = Mm(7); p.paragraph_format.first_line_indent = Mm(-7); p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.tab_stops.add_tab_stop(Mm(7))
        mark = f'{n}.' if design['bullet'] == 'number' else GLYPH[design['bullet']]
        r = p.add_run(mark + '\t'); colour(r, c['accent_text']); r.font.bold = True
        p.add_run(text_value)
        return p

    for number, part in enumerate(draft['sections'], 1):
        prefix = f'{number:02d}  ' if design['heading'] == 'number' or design['layout'] == 'margin-number' else ''
        h = document.add_heading(level=1)
        if prefix:
            r = h.add_run(prefix); colour(r, c['accent_text'])
            if design['layout'] == 'margin-number': r.font.size = Pt(26 * scale)
        h.add_run(part['heading'])
        if design['heading'] == 'bar': edge(h, 'left', border * 3, c['accent_shape'], 8)
        elif design['heading'] == 'underline': edge(h, 'bottom', border, c['accent_shape'], 4)
        elif design['heading'] == 'highlight':
            shade(h._p.get_or_add_pPr(), c['tint'])
            for r in h.runs: colour(r, c['on_tint'])
        if part['text']:
            p = document.add_paragraph(part['text'])
            if design['layout'] == 'side-panel':
                shade(p._p.get_or_add_pPr(), c['tint']); edge(p, 'left', border * 3, c['accent_shape'], 8)
                for r in p.runs: colour(r, c['on_tint'])
        if part['bullets'] and design['layout'] == 'cards':
            cols = 2
            table = document.add_table(rows=(len(part['bullets']) + 1) // cols, cols=cols)
            table._tbl.tblPr.append(parse_xml(f'<w:tblBorders {nsdecls("w")}>' + ''.join(f'<w:{s} w:val="single" w:sz="12" w:color="{c["paper"]}"/>' for s in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV')) + '</w:tblBorders>'))
            for n, point in enumerate(part['bullets']):
                cell = table.rows[n // cols].cells[n % cols]
                shade(cell._tc.get_or_add_tcPr(), c['surface'] if c['surface'] != c['paper'] else c['tint'])
                cell.paragraphs[0].text = ''
                r = cell.paragraphs[0].add_run((f'{n + 1}.' if design['bullet'] == 'number' else GLYPH[design['bullet']]) + '  '); colour(r, c['accent_text']); r.font.bold = True
                cell.paragraphs[0].add_run(point)
                cell.paragraphs[0].paragraph_format.space_before = Pt(6); cell.paragraphs[0].paragraph_format.space_after = Pt(6)
            document.add_paragraph().paragraph_format.space_after = Pt(2)
        else:
            for n, point in enumerate(part['bullets'], 1):
                point_line(document, point, n)
    keep_with_note(document)
    note = document.add_paragraph().add_run(NOTE)
    note.italic, note.font.size = True, Pt(9); colour(note, c['muted'])
    for part_section in document.sections:
        header = part_section.header.paragraphs[0]; header.text = ''
        r = header.add_run(title[:90]); colour(r, c['muted'])
        footer = part_section.footer.paragraphs[0]; footer.text = ''
        # Word's own Footer style has centre and right tab stops; clear them so the page number goes to the right edge.
        for default in (Mm(82.55), Mm(165.1)):
            footer.paragraph_format.tab_stops.add_tab_stop(default, WD_TAB_ALIGNMENT.CLEAR)
        footer.paragraph_format.tab_stops.add_tab_stop(Mm(210 - 2 * side), WD_TAB_ALIGNMENT.RIGHT)
        footer.add_run('Written with June\t')
        for xml in (f'<w:fldChar {nsdecls("w")} w:fldCharType="begin"/>', f'<w:instrText {nsdecls("w")} xml:space="preserve"> PAGE </w:instrText>', f'<w:fldChar {nsdecls("w")} w:fldCharType="end"/>'):
            footer.add_run()._r.append(parse_xml(xml))
    document.core_properties.title = title; document.core_properties.author = 'June'
    document.save(str(path))
    return len(draft['sections'])


# ============================================================ PDF ===========================================
_REGISTERED = {}


def _pdf_fonts(design):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    t = _font(design)
    names = []
    for role, fallback in (('pdf_head', 'Times-Bold' if t['kind'] == 'serif' else 'Helvetica-Bold'), ('pdf_body', 'Helvetica'), ('pdf_bold', 'Helvetica-Bold')):
        path, index = t[role]
        name = f'J-{t["id"]}-{role}'
        if name not in _REGISTERED:
            try:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=index)); _REGISTERED[name] = name
            except Exception:
                _REGISTERED[name] = fallback
        names.append(_REGISTERED[name])
    return names


def render_pdf(path, draft, design):
    from xml.sax.saxutils import escape
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import simpleSplit
    from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    c = colours(design)
    head, body, bold = _pdf_fonts(design)
    scale = SCALE[design['density']]
    hx = lambda value: HexColor('#' + value)
    width, height = A4
    side = {'airy': 24, 'balanced': 20, 'compact': 16}[design['density']] * mm
    stroke = {'hairline': 0.6, 'regular': 1.4, 'heavy': 3.2}[design['lines']]
    radius = {'sharp': 0, 'soft': 4, 'round': 12}[design['corners']]
    cover_h = {'bleed': 120, 'split': 120, 'band': 105, 'numeral': 100, 'column': 100, 'poster': 130}[design['cover']] * mm
    text_style = ParagraphStyle('text', fontName=body, fontSize=10.5 * scale + 0.5, leading=16 * scale + 1, textColor=hx(c['body']), spaceAfter=3 * mm)
    point_style = ParagraphStyle('point', parent=text_style, leftIndent=14, bulletIndent=0, spaceAfter=1.6 * mm, bulletColor=hx(c['accent_text']), bulletFontName=bold)
    head_style = ParagraphStyle('head', fontName=head, fontSize=17 * scale + 1, leading=22 * scale + 1, textColor=hx(c['on_tint'] if design['heading'] == 'highlight' else c['ink']),
                                spaceBefore=7 * mm * scale, spaceAfter=3 * mm, leftIndent=11 if design['heading'] == 'bar' else 0)
    note_style = ParagraphStyle('note', fontName=body, fontSize=8.5, leading=12, textColor=hx(c['muted']), spaceBefore=8 * mm)

    def motif(canvas, x, y, w, h, on, strong=True):
        kind = design['motif']
        first = c['accent'] if on != c['accent'] else c['accent2']
        second = mix(on, c['accent2'] if on != c['accent2'] else c['paper'], 0.35)
        soft = mix(on, first, 0.22)
        canvas.saveState()
        p = canvas.beginPath(); p.rect(x, y, w, h); canvas.clipPath(p, stroke=0, fill=0)
        if kind == 'circles':
            d = min(w, h) * (1.0 if strong else 0.55)
            canvas.setFillColor(hx(first)); canvas.circle(x + w - d * 0.25, y + h - d * 0.15, d * 0.5, stroke=0, fill=1)
            canvas.setFillColor(hx(second)); canvas.circle(x + w - d * 0.85, y + h - d * 0.95, d * 0.16, stroke=0, fill=1)
        elif kind == 'slabs':
            for n, fill in enumerate((first, second, soft)[:3 if strong else 1]):
                canvas.setFillColor(hx(fill)); q = canvas.beginPath(); bx = x + w * (0.55 + n * 0.13)
                q.moveTo(bx, y); q.lineTo(bx + w * 0.08, y); q.lineTo(bx + w * 0.08 + h * 0.4, y + h); q.lineTo(bx + h * 0.4, y + h); q.close(); canvas.drawPath(q, stroke=0, fill=1)
        elif kind == 'stripes':
            for n in range(6 if strong else 3):
                canvas.setFillColor(hx(first if n % 2 == 0 else second)); canvas.rect(x + w - (n + 1) * w * 0.05, y, w * 0.022, h, stroke=0, fill=1)
        elif kind == 'dots':
            step = min(w, h) / (8 if strong else 6)
            for row in range(5 if strong else 3):
                for col in range(6 if strong else 4):
                    canvas.setFillColor(hx(first if (row + col) % 3 else second)); canvas.circle(x + w - (col + 0.8) * step, y + h - (row + 0.8) * step, step * 0.16, stroke=0, fill=1)
        elif kind == 'grid':
            canvas.setStrokeColor(hx(soft)); canvas.setLineWidth(max(0.4, stroke / 2)); step = 9 * mm
            gx = x + w * (0.45 if strong else 0.7)
            while gx < x + w: canvas.line(gx, y, gx, y + h); gx += step
            gy = y
            while gy < y + h: canvas.line(x + w * (0.45 if strong else 0.7), gy, x + w, gy); gy += step
        elif kind == 'blobs':
            d = min(w, h) * (0.85 if strong else 0.45)
            canvas.setFillColor(hx(first)); canvas.roundRect(x + w - d * 0.85, y + h - d * 0.75, d, d * 0.8, d * 0.38, stroke=0, fill=1)
            canvas.setFillColor(hx(second)); canvas.roundRect(x + w - d * 1.15, y + h - d * 1.25, d * 0.45, d * 0.38, d * 0.18, stroke=0, fill=1)
        elif kind == 'frame':
            canvas.setStrokeColor(hx(first)); canvas.setLineWidth(max(stroke, 0.8)); canvas.rect(x + 6 * mm, y + 6 * mm, w - 12 * mm, h - 12 * mm, stroke=1, fill=0)
        elif kind == 'rules':
            canvas.setStrokeColor(hx(first)); canvas.setLineWidth(max(stroke, 0.8)); canvas.line(x + side, y + 8 * mm, x + w - side, y + 8 * mm)
        elif kind == 'waves':
            for n, fill in enumerate((soft, second, first)[:3 if strong else 2]):
                canvas.setFillColor(hx(fill)); canvas.ellipse(x - w * 0.1 + n * w * 0.12, y - h * (0.55 - n * 0.1), x + w * (1.0 + n * 0.12), y + h * (0.25 - n * 0.06), stroke=0, fill=1)
        canvas.restoreState()

    def fitted(canvas, text_value, font, size, max_w, max_lines):
        while size > 16:
            lines = simpleSplit(text_value, font, size, max_w)
            if len(lines) <= max_lines: return lines, size
            size -= 2
        return simpleSplit(text_value, font, size, max_w)[:max_lines + 1], size

    def draw_lines(canvas, lines, font, size, x, top, colour_value, centre=False, box_w=0):
        canvas.setFont(font, size); canvas.setFillColor(hx(colour_value))
        for n, line in enumerate(lines):
            yy = top - size * 1.08 * (n + 1)
            canvas.drawCentredString(x + box_w / 2, yy, line) if centre else canvas.drawString(x, yy, line)
        return top - size * 1.08 * len(lines)

    def first_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(hx(c['paper'])); canvas.rect(0, 0, width, height, stroke=0, fill=1)
        top = height - cover_h
        kind = design['cover']
        title_font = 34 * scale + 4 if len(draft['title']) < 45 else 28 * scale + 2
        tx, tw, tcolour, centre, area_w = side, width - 2 * side, c['on_cover'], False, 0
        scolour = c['on_cover_muted']
        if kind == 'bleed':
            canvas.setFillColor(hx(c['cover'])); canvas.rect(0, top, width, cover_h, stroke=0, fill=1); motif(canvas, width * 0.45, top, width * 0.55, cover_h, c['cover']); tw = width * 0.6
        elif kind == 'split':
            canvas.setFillColor(hx(c['cover'])); canvas.rect(0, top, width * 0.56, cover_h, stroke=0, fill=1); motif(canvas, width * 0.56, top, width * 0.44, cover_h, c['paper']); tw = width * 0.56 - 2 * side
        elif kind == 'band':
            motif(canvas, 0, height - 30 * mm, width, 30 * mm, c['paper'], strong=False)
            canvas.setFillColor(hx(c['cover'])); canvas.rect(0, top + 8 * mm, width, cover_h - 40 * mm, stroke=0, fill=1); centre, area_w = True, width - 2 * side
        elif kind == 'numeral':
            initial = (re.findall(r'[A-Za-z0-9]', draft['title']) or ['J'])[0].upper()
            canvas.setFillColor(hx(c['tint'])); canvas.setFont(head, 300); canvas.drawRightString(width - side * 0.6, top + 8 * mm, initial)
            motif(canvas, 0, top, width, cover_h, c['paper'], strong=False); tcolour, scolour, tw = c['ink'], c['body'], width * 0.6
        elif kind == 'column':
            canvas.setFillColor(hx(c['cover'])); canvas.rect(0, 0, 16 * mm, height, stroke=0, fill=1)
            motif(canvas, 16 * mm, top, width - 16 * mm, cover_h, c['paper'], strong=False); tx, tw, tcolour, scolour = 16 * mm + side, width - 16 * mm - 2 * side, c['ink'], c['body']
        else:
            back = c['cover'] if design['accent'] == 'generous' else c['paper']
            canvas.setFillColor(hx(back)); canvas.rect(0, top, width, cover_h, stroke=0, fill=1); motif(canvas, 0, top, width, cover_h * 0.35, back, strong=False)
            title_font *= 1.3
            if back == c['paper']: tcolour, scolour = c['ink'], c['body']
        lines, size = fitted(canvas, draft['title'], head, title_font, tw, 3)
        start = height - (cover_h * 0.3 if kind != 'band' else cover_h * 0.42)
        after = draw_lines(canvas, lines, head, size, tx, start, tcolour, centre, area_w or tw)
        if draft['summary']:
            canvas.setFillColor(hx(scolour)); canvas.setFont(body, 11.5)
            for n, line in enumerate(simpleSplit(draft['summary'], body, 11.5, tw)[:4]):
                yy = after - 8 * mm - n * 16
                canvas.drawCentredString(tx + (area_w or tw) / 2, yy, line) if centre else canvas.drawString(tx, yy, line)
        footer(canvas, doc)
        canvas.restoreState()

    def later_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(hx(c['paper'])); canvas.rect(0, 0, width, height, stroke=0, fill=1)
        canvas.setFillColor(hx(c['accent_shape'])); canvas.rect(0, height - 3 * mm, width, 3 * mm, stroke=0, fill=1)
        if design['motif'] == 'frame' or design['accent'] == 'generous':
            motif(canvas, width * 0.75, height - 28 * mm, width * 0.25, 25 * mm, c['paper'], strong=False)
        if design['cover'] == 'column':
            canvas.setFillColor(hx(c['cover'])); canvas.rect(0, 0, 6 * mm, height, stroke=0, fill=1)
        footer(canvas, doc)
        canvas.restoreState()

    def footer(canvas, doc):
        canvas.setFillColor(hx(c['muted'])); canvas.setFont(body, 8)
        canvas.drawString(side, 11 * mm, draft['title'][:80]); canvas.drawRightString(width - side, 11 * mm, str(doc.page))

    class Heading(Flowable):
        def __init__(self, text_value, number):
            super().__init__(); self.number = number
            label = (f'{number:02d}  ' if design['heading'] == 'number' and design['layout'] != 'margin-number' else '') + text_value
            self.para = Paragraph(escape(label.upper() if design['heading'] == 'smallcaps' else label), head_style)
        def wrap(self, aw, ah):
            self.width = aw; offset = 22 * mm if design['layout'] == 'margin-number' else 0
            w, h = self.para.wrap(aw - offset - (12 if design['heading'] == 'highlight' else 0), ah)
            self.h = h + (8 if design['heading'] in ('highlight', 'underline') else 2)
            return aw, self.h + head_style.spaceBefore
        def draw(self):
            canvas = self.canv; offset = 22 * mm if design['layout'] == 'margin-number' else 0
            if design['layout'] == 'margin-number':
                canvas.setFillColor(hx(c['accent_text'])); canvas.setFont(head, 26 * scale + 2); canvas.drawString(0, 4, f'{self.number:02d}')
            if design['heading'] == 'highlight':
                canvas.setFillColor(hx(c['tint'])); canvas.roundRect(offset, 0, self.width - offset, self.h, radius, stroke=0, fill=1)
                self.para.drawOn(canvas, offset + 6, 4)
            else:
                self.para.drawOn(canvas, offset, 4 if design['heading'] == 'underline' else 1)
            if design['heading'] == 'bar':
                canvas.setFillColor(hx(c['accent_shape'])); canvas.rect(offset, 3, max(stroke * 2, 3), self.h - 4, stroke=0, fill=1)
            if design['heading'] == 'underline':
                canvas.setStrokeColor(hx(c['accent_shape'])); canvas.setLineWidth(max(stroke, 0.8)); canvas.line(offset, 1, self.width, 1)

    class Card(Flowable):
        def __init__(self, text_value, mark):
            super().__init__(); self.mark = mark
            self.para = Paragraph(escape(text_value), ParagraphStyle('card', parent=text_style, textColor=hx(c['ink']), spaceAfter=0))
        def wrap(self, aw, ah):
            self.width = aw; _, h = self.para.wrap(aw - 30, ah); self.h = h + 16; return aw, self.h
        def draw(self):
            canvas = self.canv
            canvas.setFillColor(hx(c['surface'] if c['surface'] != c['paper'] else c['tint'])); canvas.setStrokeColor(hx(c['line'])); canvas.setLineWidth(0.6)
            canvas.roundRect(0, 0, self.width, self.h, radius, stroke=1, fill=1)
            glyph, font = self.mark
            canvas.setFillColor(hx(c['accent_text'])); canvas.setFont(font, 9 if font == 'ZapfDingbats' else 10); canvas.drawString(9, self.h - 18, glyph)
            self.para.drawOn(canvas, 24, 8)

    def mark(n):
        """(glyph, font): ZapfDingbats draws the symbols every body font may lack."""
        if design['bullet'] == 'number': return f'{n}.', bold
        return {'square': ('n', 'ZapfDingbats'), 'dot': ('l', 'ZapfDingbats'), 'check': ('4', 'ZapfDingbats'), 'dash': ('–', bold), 'arrow': ('›', bold)}[design['bullet']]

    def point(text_value, n):
        glyph, font = mark(n)
        style = ParagraphStyle('pt', parent=point_style, bulletFontName=font, bulletFontSize=7 if font == 'ZapfDingbats' else text_style.fontSize)
        return Paragraph(escape(text_value), style, bulletText=glyph)

    story = [Spacer(1, cover_h - side + 6 * mm)]
    for number, part in enumerate(draft['sections'], 1):
        group = [Heading(part['heading'], number)]
        if part['text']:
            para = Paragraph(escape(part['text']), text_style)
            if design['layout'] == 'side-panel':
                panel = Table([[para]], colWidths=[width - 2 * side])
                panel.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), hx(c['tint'])), ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                                           ('TOPPADDING', (0, 0), (-1, -1), 8), ('LINEBEFORE', (0, 0), (0, -1), max(stroke * 2, 2), hx(c['accent_shape']))]))
                para.style = ParagraphStyle('panel', parent=text_style, textColor=hx(c['on_tint']))
                group.append(panel); group.append(Spacer(1, 3 * mm))
            else:
                group.append(para)
        story.append(KeepTogether(group))
        points = part['bullets']
        if not points: continue
        if design['layout'] in ('cards', 'two-column') and len(points) > 1:
            cells = [Card(p, mark(n)) if design['layout'] == 'cards' else point(p, n) for n, p in enumerate(points, 1)]
            rows = [cells[i:i + 2] + ([''] if len(cells[i:i + 2]) == 1 else []) for i in range(0, len(cells), 2)]
            grid = Table(rows, colWidths=[(width - 2 * side) / 2] * 2)
            grid.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
            story.append(grid)
        else:
            story += [point(p, n) for n, p in enumerate(points, 1)]
    story.append(Paragraph(NOTE, note_style))
    SimpleDocTemplate(str(path), pagesize=A4, title=draft['title'], author='June', leftMargin=side, rightMargin=side, topMargin=side, bottomMargin=side + 4 * mm).build(
        story, onFirstPage=first_page, onLaterPages=later_page)
    return len(draft['sections'])
