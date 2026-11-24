"""June's design system: she chooses a look for each document from many parameters, to fit what was asked.

A design is mood + palette + typography + motif + cover + content layout + heading + bullet + corners +
line weight + density + accent use (+ an optional accent colour). The local model picks every value
from closed lists, explaining why. This module checks her choices against each mood's rules, keeps
text readable (WCAG AA), honours words the person said explicitly ("dark", "in green", "minimal"),
and falls back to mood-based choices if the model gives nothing usable. No randomness: June decides.
"""
import colorsys
import json
import re

from .chat import MODEL_KEEP_ALIVE

# --- Palettes: paper, surface, ink, body, muted, accent, accent2, line --------------------------------------
_P = [
    # id, name, look, tone, paper, surface, ink, body, muted, accent, accent2, line, moods
    ('clay', 'Clay', 'cream paper, ink, terracotta', 'light', 'F5F0E8', 'FFFDF9', '1F1E1D', '3A3835', '67645E', 'D97757', '3A3835', 'E3DCCF', 'warm friendly editorial calm earthy'),
    ('linen-navy', 'Navy & Gold', 'linen white, navy, brass gold', 'light', 'F7F4EE', 'FFFFFF', '14213D', '2E3A55', '545D72', 'C8A44D', '14213D', 'E2DCCF', 'corporate professional luxurious solemn elegant academic'),
    ('forest', 'Forest', 'soft white, deep pine green, moss', 'light', 'F1F3EC', 'FFFFFF', '1E3A2B', '33463A', '56665A', '2F7D4F', 'A3B18A', 'DCE2D3', 'natural earthy calm rustic'),
    ('citrus', 'Citrus', 'warm white, tangerine, sunflower', 'light', 'FFFBF2', 'FFFFFF', '2B2118', '43362A', '6A5B4C', 'F28C28', 'F6C445', 'F0E3CC', 'playful energetic festive friendly warm'),
    ('mono', 'Mono', 'pure white, black, one red accent', 'light', 'FFFFFF', 'F4F4F4', '111111', '2A2A2A', '5A5A5A', 'E63323', '111111', 'E2E2E2', 'minimal bold corporate editorial solemn'),
    ('ocean-mist', 'Ocean Mist', 'mist blue, deep teal, coral', 'light', 'EEF4F7', 'FFFFFF', '0F3B4C', '274B5A', '4A6672', 'F07B62', '2A9DB5', 'D5E3EA', 'calm cool natural friendly'),
    ('blush', 'Blush', 'blush pink, plum ink, antique gold', 'light', 'FBF3F1', 'FFFFFF', '3B1F2B', '55343F', '76565F', 'C9707D', 'B8935A', 'EEDCD8', 'romantic elegant festive warm'),
    ('blueprint', 'Blueprint', 'pale blue paper, indigo, amber', 'light', 'F3F6FB', 'FFFFFF', '1B2A6B', '2F3D7A', '525C8B', 'F2A33A', '3D5AFE', 'D6DEF0', 'technical academic futuristic professional'),
    ('newsprint', 'Newsprint', 'newsprint, black ink, press red', 'light', 'F4F1EA', 'FBF9F4', '1A1A1A', '333333', '625C55', 'B3261E', '1A1A1A', 'DDD7CB', 'editorial solemn vintage bold'),
    ('sage', 'Sage', 'pale sage, slate green, honey', 'light', 'F3F5F0', 'FFFFFF', '2D3B33', '3F4D44', '5E6C63', '7A9E7E', 'D4A373', 'DEE4DA', 'calm natural minimal friendly'),
    ('desert', 'Desert', 'sand, dark umber, burnt orange', 'light', 'F8EFE4', 'FFF9F2', '3D2817', '54402D', '745F4B', 'C2703D', 'E0B07A', 'EAD9C4', 'earthy rustic warm vintage'),
    ('arctic', 'Arctic', 'ice white, deep slate blue, aqua', 'light', 'F5F9FC', 'FFFFFF', '102A43', '334E68', '4F6378', '3EBBD8', '9FB3C8', 'DCE6EF', 'cool minimal futuristic professional technical'),
    ('candy', 'Candy', 'pink white, grape ink, hot pink, violet', 'light', 'FFF6FA', 'FFFFFF', '33203A', '4B3554', '6B5673', 'FF5FA2', '7C5CFF', 'F2DDE8', 'playful festive energetic friendly'),
    ('sepia', 'Sepia', 'old paper, brown ink, rust, olive', 'light', 'F3E9D8', 'FAF3E6', '3B2A1A', '503C29', '6E5A46', '9C5B2E', '6B7F4E', 'E3D5BE', 'vintage rustic warm academic'),
    ('lavender', 'Lavender', 'lilac white, indigo, violet, apricot', 'light', 'F6F4FB', 'FFFFFF', '2E2552', '433A66', '615A7C', '8B6CEF', 'F2B880', 'E3DFF0', 'calm artistic friendly romantic'),
    ('sunset', 'Sunset', 'peach white, coral red, mango', 'light', 'FFF5EE', 'FFFFFF', '3A1C1C', '53302D', '75514C', 'F25C54', 'F7B267', 'F3DDD2', 'warm energetic festive romantic'),
    ('botanical', 'Botanical', 'cream, bottle green, clay, leaf', 'light', 'F4F1E8', 'FFFCF5', '213B2C', '34493C', '57665A', 'C76B4A', '6F8F5A', 'E2DDCF', 'natural earthy calm rustic'),
    ('slate', 'Slate', 'cool grey, slate navy, bright blue', 'light', 'F2F4F7', 'FFFFFF', '1D2939', '344054', '525F70', '2E90FA', '1D2939', 'DDE2E8', 'corporate professional technical minimal'),
    ('gallery', 'Gallery', 'gallery white, black, cobalt, yellow', 'light', 'FAFAF7', 'FFFFFF', '0E0E0E', '2B2B2B', '5B5B56', '2D5BFF', 'FFC93C', 'E6E6E0', 'artistic editorial bold minimal'),
    ('butter', 'Butter', 'butter yellow, olive ink, saffron, green', 'light', 'FFFAE6', 'FFFFFF', '2E2A1F', '46412F', '67614B', 'E2A400', '4E8F6A', 'EFE6C4', 'friendly warm playful'),
    ('stone', 'Stone', 'warm stone grey, charcoal, taupe', 'light', 'EFEDE8', 'F8F7F4', '2A2A28', '3F3E3B', '5D5B56', '8A7F6E', '2A2A28', 'DCD8D0', 'solemn minimal calm professional'),
    ('jewel', 'Jewel', 'ivory, sapphire ink, emerald, ruby', 'light', 'F7F5F2', 'FFFFFF', '1F2440', '353A57', '575B74', '0F7B6C', '9B2C5B', 'E3E0DA', 'luxurious elegant festive'),
    ('mint', 'Mint', 'mint white, deep green, jade, coral', 'light', 'F0FAF6', 'FFFFFF', '123A32', '2A4C44', '4A6760', '18A67A', 'FF8A5B', 'D3ECE2', 'friendly calm natural playful cool'),
    ('brick', 'Brick', 'warm white, oxblood, brick red', 'light', 'F6EFEA', 'FFFAF6', '2B1A16', '45302A', '67514B', 'A63A2B', '2B1A16', 'E6D8CF', 'rustic bold vintage solemn'),
    ('midnight', 'Midnight', 'navy night, ice, electric cyan', 'dark', '0F1B2D', '16253D', 'F1F5FB', 'D4DDEB', '9AA8BF', '37D6F0', '7C8CFF', '25344D', 'technical futuristic corporate cool professional'),
    ('neon', 'Neon', 'near black, neon green, magenta', 'dark', '0B0B10', '15151E', 'F5F5F7', 'D6D6E0', '9C9CB0', '39FF88', 'FF3DCB', '24242F', 'futuristic energetic bold festive'),
    ('ink-clay', 'Ink & Clay', 'warm black, cream, terracotta', 'dark', '1F1E1D', '2A2826', 'F5F0E8', 'DDD6CB', 'A8A196', 'E3876A', '6E8BA3', '3A3835', 'warm editorial bold artistic'),
    ('noir-gold', 'Noir & Gold', 'black, champagne, gold', 'dark', '111111', '1C1C1C', 'F4EFE6', 'D9D2C5', 'A59D90', 'D4AF37', '8C7853', '2C2C2C', 'luxurious elegant solemn'),
    ('forest-night', 'Forest Night', 'night green, fern, wheat', 'dark', '13231B', '1B3226', 'EEF2EA', 'D2DCCF', '9EAE9F', '8FCB7E', 'D9B26F', '2A4134', 'natural earthy calm'),
    ('plum', 'Plum', 'aubergine, gold, rose', 'dark', '2A1630', '361D3E', 'F7EEF4', 'E2D2DE', 'B49CB0', 'E8B04B', 'F28CB1', '47294F', 'luxurious romantic elegant festive'),
    ('deep-ocean', 'Deep Ocean', 'deep sea teal, coral, aqua', 'dark', '0B2A36', '103745', 'ECF6F8', 'CFE3E8', '93B4BD', 'FF8C6B', '4FD1C5', '1E4A59', 'cool calm natural'),
    ('charcoal-red', 'Charcoal & Red', 'charcoal, white, signal red', 'dark', '1A1A1A', '242424', 'F5F5F5', 'D8D8D8', 'A3A3A3', 'FF4D3D', 'F5F5F5', '333333', 'bold minimal energetic'),
    ('cocoa', 'Cocoa', 'cocoa brown, cream, caramel, sage', 'dark', '2B1E17', '36271F', 'F6EDE3', 'E1D3C3', 'B09D8A', 'E0A060', '9CB380', '45362C', 'earthy rustic warm vintage'),
    ('space', 'Space', 'deep violet night, lilac, cyan', 'dark', '0D0B1F', '17142E', 'EEEBFF', 'D3CEF0', '9C96C2', 'A78BFA', '22D3EE', '252147', 'futuristic technical artistic'),
    ('evergreen', 'Evergreen', 'evergreen, ivory, gold, berry', 'dark', '0F2A24', '163A32', 'F1EEDF', 'D9D6C2', 'A6AE9C', 'D9A441', 'E8705A', '24463D', 'festive luxurious natural'),
    ('graphite', 'Graphite', 'graphite, white, azure, amber', 'dark', '202327', '2A2E33', 'F2F3F5', 'D5D8DD', '9EA3AB', '5EA2FF', 'F2C14E', '363B42', 'professional corporate technical minimal'),
    ('wine', 'Wine', 'claret, blush, amber', 'dark', '2C0F16', '3A1720', 'F8EDEF', 'E5D1D5', 'B79AA0', 'E9A23B', 'D96C82', '4A2530', 'romantic luxurious solemn'),
    ('retro-teal', 'Retro Teal', 'teal, cream, mustard, tomato', 'dark', '123A3F', '18484E', 'F6EFD9', 'E3D9BC', 'B3AE92', 'F2A541', 'E85D4A', '22555B', 'vintage playful artistic warm'),
    ('sunset-night', 'Sunset Night', 'dusk purple, peach, coral', 'dark', '241425', '301B31', 'FFF1EA', 'F0D7CC', 'C2A2A0', 'FF7A59', 'FFC15E', '3F2840', 'energetic festive romantic warm'),
    ('storm', 'Storm', 'storm blue-grey, pale silver, brass', 'dark', '1C2430', '252F3D', 'EEF1F5', 'D3D9E1', '9AA5B4', '9FB8D6', 'E7C77E', '323D4D', 'solemn calm cool professional academic'),
]
PALETTES = {p[0]: dict(id=p[0], name=p[1], look=p[2], tone=p[3], paper=p[4], surface=p[5], ink=p[6], body=p[7], muted=p[8], accent=p[9], accent2=p[10], line=p[11],
                       moods=p[12].split()) for p in _P}

# --- Typography: heading (family, bold) and body family; the PDF files that embed them -----------------------
_S = '/System/Library/Fonts/Supplemental/'
_F = '/System/Library/Fonts/'
_T = [
    # id, name, look, kind, heading family, heading bold, body family, css heading stack, css body stack, pdf heading, pdf body, pdf body bold, moods
    ('classic', 'Georgia & Avenir', 'warm classic serif with a clean sans', 'serif', 'Georgia', False, 'Avenir Next', 'Georgia,"Times New Roman",serif', '"Avenir Next",Avenir,"Segoe UI",sans-serif',
     (_S + 'Georgia.ttf', 0), (_F + 'Avenir Next.ttc', 7), (_F + 'Avenir Next.ttc', 2), 'warm editorial friendly calm professional'),
    ('fashion', 'Didot & Avenir', 'high-contrast fashion serif', 'serif', 'Didot', False, 'Avenir Next', 'Didot,"Bodoni 72","Times New Roman",serif', '"Avenir Next",Avenir,sans-serif',
     (_S + 'Didot.ttc', 0), (_F + 'Avenir Next.ttc', 7), (_F + 'Avenir Next.ttc', 2), 'elegant luxurious romantic editorial'),
    ('literary', 'Baskerville & Gill Sans', 'bookish traditional serif', 'serif', 'Baskerville', True, 'Gill Sans', 'Baskerville,"Baskerville Old Face",Georgia,serif', '"Gill Sans","Gill Sans MT",Calibri,sans-serif',
     (_S + 'Baskerville.ttc', 4), (_S + 'GillSans.ttc', 0), (_S + 'GillSans.ttc', 4), 'academic natural vintage calm solemn earthy'),
    ('geometric', 'Futura & Avenir', 'geometric, punchy, modern', 'sans', 'Futura', True, 'Avenir Next', 'Futura,"Century Gothic","Avenir Next",sans-serif', '"Avenir Next",Avenir,sans-serif',
     (_S + 'Futura.ttc', 2), (_F + 'Avenir Next.ttc', 7), (_F + 'Avenir Next.ttc', 2), 'energetic bold playful futuristic festive artistic'),
    ('swiss', 'Helvetica Neue', 'neutral Swiss grotesk', 'sans', 'Helvetica Neue', True, 'Helvetica Neue', '"Helvetica Neue",Helvetica,Arial,sans-serif', '"Helvetica Neue",Helvetica,Arial,sans-serif',
     (_F + 'HelveticaNeue.ttc', 1), (_F + 'HelveticaNeue.ttc', 0), (_F + 'HelveticaNeue.ttc', 10), 'minimal corporate technical bold professional editorial'),
    ('humanist', 'Optima', 'graceful flared humanist', 'sans', 'Optima', True, 'Optima', 'Optima,Candara,"Segoe UI",sans-serif', 'Optima,Candara,"Segoe UI",sans-serif',
     (_F + 'Optima.ttc', 1), (_F + 'Optima.ttc', 0), (_F + 'Optima.ttc', 1), 'calm natural elegant cool romantic'),
    ('slab', 'Rockwell & Verdana', 'sturdy slab serif', 'serif', 'Rockwell', True, 'Verdana', 'Rockwell,"Roboto Slab",Georgia,serif', 'Verdana,Geneva,sans-serif',
     (_S + 'Rockwell.ttc', 2), (_S + 'Verdana.ttf', 0), (_S + 'Verdana Bold.ttf', 0), 'rustic vintage bold earthy technical'),
    ('renaissance', 'Palatino & Optima', 'scholarly old-style serif', 'serif', 'Palatino', True, 'Optima', 'Palatino,"Palatino Linotype","Book Antiqua",serif', 'Optima,Candara,sans-serif',
     (_F + 'Palatino.ttc', 2), (_F + 'Optima.ttc', 0), (_F + 'Optima.ttc', 1), 'academic solemn elegant warm'),
    ('heavy', 'Avenir Heavy', 'heavy friendly sans', 'sans', 'Avenir Next', True, 'Avenir Next', '"Avenir Next",Avenir,"Segoe UI",sans-serif', '"Avenir Next",Avenir,"Segoe UI",sans-serif',
     (_F + 'Avenir Next.ttc', 8), (_F + 'Avenir Next.ttc', 7), (_F + 'Avenir Next.ttc', 2), 'energetic bold playful friendly corporate'),
    ('gill', 'Gill Sans & Georgia', 'British humanist sans with serif text', 'sans', 'Gill Sans', True, 'Georgia', '"Gill Sans","Gill Sans MT",Calibri,sans-serif', 'Georgia,serif',
     (_S + 'GillSans.ttc', 4), (_S + 'Georgia.ttf', 0), (_S + 'Georgia Bold.ttf', 0), 'editorial warm natural vintage'),
    ('charter', 'Charter & Avenir', 'crisp, sober modern serif', 'serif', 'Charter', True, 'Avenir Next', 'Charter,"Bitstream Charter",Georgia,serif', '"Avenir Next",Avenir,sans-serif',
     (_S + 'Charter.ttc', 3), (_F + 'Avenir Next.ttc', 7), (_F + 'Avenir Next.ttc', 2), 'professional academic solemn corporate'),
    ('typewriter', 'American Typewriter', 'typewriter with a neutral sans', 'serif', 'American Typewriter', True, 'Helvetica Neue', '"American Typewriter","Courier New",serif', '"Helvetica Neue",Helvetica,sans-serif',
     (_S + 'AmericanTypewriter.ttc', 3), (_F + 'HelveticaNeue.ttc', 0), (_F + 'HelveticaNeue.ttc', 10), 'vintage rustic artistic friendly'),
    ('mono', 'Menlo & Helvetica', 'code-like monospace headings', 'mono', 'Menlo', True, 'Helvetica Neue', 'Menlo,Consolas,"Courier New",monospace', '"Helvetica Neue",Helvetica,sans-serif',
     (_F + 'Menlo.ttc', 1), (_F + 'HelveticaNeue.ttc', 0), (_F + 'HelveticaNeue.ttc', 10), 'technical futuristic minimal'),
    ('bodoni', 'Bodoni & Seravek', 'dramatic display serif', 'serif', 'Bodoni 72', True, 'Seravek', '"Bodoni 72","Bodoni MT",Didot,serif', 'Seravek,"Gill Sans",sans-serif',
     (_S + 'Bodoni 72.ttc', 2), (_S + 'Seravek.ttc', 0), (_S + 'Seravek.ttc', 3), 'luxurious editorial artistic festive romantic'),
    ('rounded', 'Seravek', 'soft, open, friendly sans', 'sans', 'Seravek', True, 'Seravek', 'Seravek,"Gill Sans",Calibri,sans-serif', 'Seravek,"Gill Sans",Calibri,sans-serif',
     (_S + 'Seravek.ttc', 9), (_S + 'Seravek.ttc', 0), (_S + 'Seravek.ttc', 3), 'friendly playful calm cool natural'),
]
TYPES = {t[0]: dict(id=t[0], name=t[1], look=t[2], kind=t[3], head=t[4], head_bold=t[5], body=t[6], css_head=t[7], css_body=t[8], pdf_head=t[9], pdf_body=t[10],
                    pdf_bold=t[11], moods=t[12].split()) for t in _T}

# --- Structural options -------------------------------------------------------------------------------
OPTIONS = {
    'motif': {'circles': 'large overlapping circles', 'slabs': 'angled diagonal slabs', 'stripes': 'bold parallel stripes', 'dots': 'a dot grid',
              'grid': 'fine blueprint grid lines', 'blobs': 'soft rounded blob shapes', 'frame': 'a thin inset frame', 'rules': 'only thin horizontal rules',
              'waves': 'layered wave bands', 'none': 'no decoration'},
    'cover': {'bleed': 'full-bleed colour cover', 'split': 'split half colour, half paper', 'band': 'title on a horizontal colour band', 'numeral': 'giant initial letter beside the title',
              'column': 'tall colour column at the left edge', 'poster': 'huge poster-style title'},
    'layout': {'bar': 'accent bar above each heading', 'margin-number': 'big section numbers in the margin', 'side-panel': 'a coloured side panel per section',
               'two-column': 'text in two columns', 'cards': 'points shown as cards'},
    'heading': {'bar': 'coloured bar beside headings', 'number': 'numbered headings', 'smallcaps': 'spaced small capitals', 'underline': 'rule under headings',
                'highlight': 'headings on a tinted block'},
    'bullet': {'square': '■', 'dot': '●', 'dash': '–', 'arrow': '→', 'number': '1.', 'check': '✓'},
    'corners': {'sharp': 'square corners', 'soft': 'slightly rounded', 'round': 'very rounded'},
    'lines': {'hairline': 'hairline strokes', 'regular': 'regular strokes', 'heavy': 'heavy strokes'},
    'density': {'airy': 'lots of white space', 'balanced': 'balanced spacing', 'compact': 'dense, information-rich'},
    'accent': {'sparing': 'accent colour used sparingly', 'generous': 'accent colour in large blocks'},
}

# Each mood: what fits it. The first value of each list is the mood's own default.
_M = {
    'calm':       ('peaceful, gentle', 'waves circles rules none blobs frame', 'band split column bleed', 'bar two-column cards side-panel', 'underline smallcaps bar', 'dot dash check', 'round soft', 'hairline regular', 'airy balanced', 'sparing'),
    'energetic':  ('lively, high-energy', 'slabs stripes circles dots waves', 'bleed poster split numeral', 'cards margin-number bar side-panel', 'highlight bar number', 'arrow square check', 'soft sharp round', 'heavy regular', 'balanced compact', 'generous sparing'),
    'playful':    ('fun, for kids or parties', 'blobs dots circles waves stripes', 'poster bleed numeral split', 'cards side-panel bar', 'highlight bar number', 'check dot arrow', 'round soft', 'heavy regular', 'balanced airy', 'generous sparing'),
    'elegant':    ('refined, graceful', 'frame rules circles none waves', 'band split column numeral', 'two-column bar margin-number', 'smallcaps underline', 'dash dot', 'sharp soft', 'hairline', 'airy', 'sparing'),
    'luxurious':  ('premium, opulent', 'frame rules circles none', 'bleed band numeral split', 'two-column margin-number side-panel', 'smallcaps underline', 'dash dot', 'sharp', 'hairline regular', 'airy', 'sparing'),
    'bold':       ('striking, confident', 'slabs stripes circles none', 'poster bleed split numeral', 'margin-number cards bar side-panel', 'highlight number bar', 'square arrow', 'sharp soft', 'heavy', 'balanced compact', 'generous'),
    'minimal':    ('clean, restrained', 'none rules frame grid', 'band numeral poster column', 'bar two-column margin-number', 'underline smallcaps number', 'dash dot square', 'sharp', 'hairline', 'airy balanced', 'sparing'),
    'corporate':  ('business, polished', 'stripes rules grid slabs none', 'split column band bleed', 'side-panel bar two-column cards', 'bar number underline', 'square dot arrow', 'sharp soft', 'regular', 'balanced compact', 'sparing generous'),
    'professional': ('competent, trustworthy', 'rules grid frame stripes none', 'column split band', 'bar side-panel two-column', 'bar underline number', 'square dot dash', 'soft sharp', 'regular hairline', 'balanced', 'sparing'),
    'academic':   ('scholarly, educational', 'rules frame grid none', 'band column numeral', 'margin-number two-column bar', 'number underline smallcaps', 'number dot dash', 'sharp', 'hairline regular', 'balanced compact', 'sparing'),
    'technical':  ('engineering, how-to, software', 'grid dots rules stripes none', 'split column band', 'margin-number side-panel cards', 'number bar', 'arrow square number', 'sharp soft', 'regular hairline', 'compact balanced', 'sparing generous'),
    'futuristic': ('high-tech, sci-fi', 'grid dots slabs circles', 'bleed poster split', 'cards side-panel margin-number', 'highlight number bar', 'arrow square', 'sharp round', 'hairline heavy', 'balanced airy', 'generous sparing'),
    'natural':    ('organic, plants, health', 'blobs waves circles dots none', 'split bleed band column', 'cards two-column bar', 'underline bar', 'dot check dash', 'round soft', 'regular hairline', 'airy balanced', 'sparing generous'),
    'earthy':     ('grounded, handmade', 'waves blobs stripes rules', 'split column bleed band', 'two-column cards bar', 'underline smallcaps bar', 'dot dash', 'soft round', 'regular', 'balanced airy', 'sparing generous'),
    'warm':       ('cosy, welcoming', 'circles waves blobs rules', 'bleed split band numeral', 'bar cards two-column', 'bar underline highlight', 'dot check', 'soft round', 'regular', 'balanced airy', 'sparing generous'),
    'cool':       ('crisp, fresh, serene', 'waves circles grid rules none', 'split band bleed column', 'two-column bar cards', 'underline bar', 'dash dot arrow', 'soft round', 'hairline regular', 'airy balanced', 'sparing'),
    'romantic':   ('love, weddings, tender', 'circles frame waves rules', 'band numeral split', 'two-column bar', 'smallcaps underline', 'dot dash', 'round soft', 'hairline', 'airy', 'sparing'),
    'vintage':    ('retro, nostalgic', 'stripes frame rules circles', 'band poster numeral', 'margin-number two-column bar', 'smallcaps underline number', 'dash square', 'sharp soft', 'regular heavy', 'balanced', 'generous sparing'),
    'editorial':  ('magazine, journalism', 'rules none frame slabs', 'poster numeral column split', 'two-column margin-number bar', 'smallcaps number underline', 'dash square', 'sharp', 'hairline regular', 'balanced compact', 'sparing'),
    'artistic':   ('creative, gallery, design', 'slabs blobs circles dots stripes', 'poster numeral split bleed', 'cards margin-number side-panel', 'highlight number smallcaps', 'square dash arrow', 'sharp round', 'heavy hairline', 'airy balanced', 'generous'),
    'rustic':     ('countryside, crafts, food', 'stripes waves frame rules', 'column band split', 'two-column cards bar', 'underline smallcaps', 'dash dot', 'soft', 'regular heavy', 'balanced', 'sparing generous'),
    'festive':    ('celebration, holidays, events', 'dots circles stripes waves blobs', 'bleed poster numeral', 'cards side-panel bar', 'highlight number', 'check dot', 'round soft', 'heavy regular', 'balanced', 'generous'),
    'solemn':     ('serious, memorial, formal notices', 'rules frame none', 'band column', 'bar two-column', 'underline smallcaps', 'dash dot', 'sharp', 'hairline', 'airy balanced', 'sparing'),
    'friendly':   ('approachable, everyday', 'circles blobs dots waves', 'split bleed band', 'cards bar side-panel', 'bar highlight', 'dot check arrow', 'round soft', 'regular', 'balanced airy', 'sparing generous'),
}
MOODS = {k: dict(look=v[0], motif=v[1].split(), cover=v[2].split(), layout=v[3].split(), heading=v[4].split(), bullet=v[5].split(), corners=v[6].split(),
                 lines=v[7].split(), density=v[8].split(), accent=v[9].split()) for k, v in _M.items()}
PARAMS = ('motif', 'cover', 'layout', 'heading', 'bullet', 'corners', 'lines', 'density', 'accent')

PRESETS = {
    'clay': dict(mood='warm', palette='clay', type='classic', motif='circles', cover='bleed', layout='bar', heading='bar', bullet='square'),
    'midnight': dict(mood='technical', palette='midnight', type='mono', motif='grid', cover='split', layout='margin-number', heading='number', bullet='arrow'),
    'forest': dict(mood='natural', palette='forest', type='literary', motif='waves', cover='split', layout='two-column', heading='underline', bullet='dot'),
    'citrus': dict(mood='playful', palette='citrus', type='geometric', motif='dots', cover='poster', layout='cards', heading='highlight', bullet='check'),
    'mono': dict(mood='minimal', palette='mono', type='swiss', motif='none', cover='numeral', layout='bar', heading='underline', bullet='dash'),
    'ocean': dict(mood='calm', palette='ocean-mist', type='humanist', motif='waves', cover='band', layout='two-column', heading='underline', bullet='dot'),
    'plum': dict(mood='luxurious', palette='plum', type='fashion', motif='frame', cover='band', layout='two-column', heading='smallcaps', bullet='dash'),
    'blueprint': dict(mood='technical', palette='blueprint', type='slab', motif='grid', cover='column', layout='margin-number', heading='number', bullet='number'),
    'sunset': dict(mood='energetic', palette='sunset', type='heavy', motif='slabs', cover='bleed', layout='cards', heading='highlight', bullet='arrow'),
    'newsprint': dict(mood='editorial', palette='newsprint', type='bodoni', motif='rules', cover='poster', layout='two-column', heading='smallcaps', bullet='square'),
    'neon': dict(mood='futuristic', palette='neon', type='geometric', motif='dots', cover='poster', layout='cards', heading='highlight', bullet='arrow'),
    'botanical': dict(mood='natural', palette='botanical', type='gill', motif='blobs', cover='split', layout='cards', heading='bar', bullet='dot'),
}

# --- Colour arithmetic ---------------------------------------------------------------------------------
def _rgb(h): return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
def _hex(rgb): return ''.join(f'{max(0, min(255, round(c * 255))):02X}' for c in rgb)


def luminance(h):
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in _rgb(h)]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a, b, t):
    """a blended toward b by t (0..1)."""
    return _hex(tuple(x + (y - x) * t for x, y in zip(_rgb(a), _rgb(b))))


def readable(color, background, target=4.5):
    """color nudged toward black or white until it reaches the target contrast on background."""
    toward = '000000' if luminance(background) > 0.18 else 'FFFFFF'
    for step in range(0, 21):
        candidate = mix(color, toward, step / 20)
        if contrast(candidate, background) >= target:
            return candidate
    return toward


def hue(h):
    r, g, b = _rgb(h)
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    return hh * 360, ss, ll


def hue_distance(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


# --- Words the person says explicitly -----------------------------------------------------------------
MOOD_WORDS = {'calm': 'calm', 'peaceful': 'calm', 'serene': 'calm', 'gentle': 'calm', 'energetic': 'energetic', 'vibrant': 'energetic', 'lively': 'energetic',
              'dynamic': 'energetic', 'playful': 'playful', 'fun': 'playful', 'whimsical': 'playful', 'elegant': 'elegant', 'classy': 'elegant',
              'graceful': 'elegant', 'luxurious': 'luxurious', 'luxury': 'luxurious', 'premium': 'luxurious', 'opulent': 'luxurious', 'bold': 'bold', 'striking': 'bold',
              'loud': 'bold', 'minimal': 'minimal', 'minimalist': 'minimal', 'minimalistic': 'minimal', 'clean': 'minimal', 'simple': 'minimal', 'corporate': 'corporate',
              'business': 'corporate', 'professional': 'professional', 'formal': 'professional', 'academic': 'academic', 'scholarly': 'academic', 'technical': 'technical',
              'techy': 'technical', 'futuristic': 'futuristic', 'sci-fi': 'futuristic', 'cyberpunk': 'futuristic', 'natural': 'natural', 'organic': 'natural', 'earthy': 'earthy',
              'warm': 'warm', 'cosy': 'warm', 'cozy': 'warm', 'cool': 'cool', 'fresh': 'cool', 'romantic': 'romantic', 'vintage': 'vintage', 'retro': 'vintage',
              'old-school': 'vintage', 'editorial': 'editorial', 'magazine': 'editorial', 'artistic': 'artistic', 'creative': 'artistic', 'artsy': 'artistic', 'rustic': 'rustic',
              'festive': 'festive', 'celebratory': 'festive', 'party': 'festive', 'solemn': 'solemn', 'serious': 'solemn', 'sombre': 'solemn', 'somber': 'solemn',
              'friendly': 'friendly', 'approachable': 'friendly', 'colourful': 'energetic', 'colorful': 'energetic'}
HUE_WORDS = {'red': 5, 'crimson': 350, 'orange': 25, 'yellow': 50, 'gold': 45, 'golden': 45, 'green': 135, 'teal': 175, 'turquoise': 175, 'aqua': 185, 'blue': 215,
             'navy': 222, 'purple': 275, 'violet': 265, 'lilac': 265, 'pink': 335, 'rose': 345, 'brown': 28, 'coral': 10}
TONE_WORDS = {'dark': 'dark', 'night': 'dark', 'black': 'dark', 'light': 'light', 'white': 'light', 'bright': 'light', 'pastel': 'light'}
_STYLE_WORD = r"(?:" + '|'.join(sorted(set(MOOD_WORDS) | set(HUE_WORDS) | set(TONE_WORDS) | set(PRESETS) | {'serif', 'sans', 'sans-serif', 'modern', 'classic', 'spacious', 'airy', 'compact', 'dense',
                                                                                                        'monochrome', 'grey', 'gray'}, key=len, reverse=True)) + r")"
STYLE_PHRASE = _STYLE_WORD + r"(?:(?:\s*,\s*|\s+and\s+|\s+)" + _STYLE_WORD + r"){0,3}"


def pins_from(text):
    """Parameters the person fixed in words, e.g. 'dark minimal in green' → tone, mood, hue."""
    pins = {}
    if not isinstance(text, str):
        return pins
    words = re.findall(r"[a-z]+(?:-[a-z]+)?", text.lower())
    for word in words:
        if word in PRESETS:
            pins.update({k: v for k, v in PRESETS[word].items()}); pins['preset'] = word
        elif word in MOOD_WORDS and 'mood' not in pins:
            pins['mood'] = MOOD_WORDS[word]
            if word in ('colourful', 'colorful', 'vibrant'): pins['accent'] = 'generous'
        if word in TONE_WORDS:
            pins['tone'] = TONE_WORDS[word]
        if word in HUE_WORDS and 'hue' not in pins:
            pins['hue'] = HUE_WORDS[word]
        if word in ('monochrome', 'grey', 'gray'):
            pins['palette'] = 'mono' if pins.get('tone') != 'dark' else 'charcoal-red'
        if word in ('serif', 'classic'): pins['typekind'] = 'serif'
        if word in ('sans', 'sans-serif', 'modern'): pins['typekind'] = 'sans'
        if word in ('spacious', 'airy'): pins['density'] = 'airy'
        if word in ('compact', 'dense'): pins['density'] = 'compact'
    return pins


# --- Resolving June's choice --------------------------------------------------------------------------
_TOPIC_MOODS = [(r'kid|child|birthday|party|game|toy|fun|cartoon|school trip', 'playful'), (r'wedding|love|valentine|anniversary|romance', 'romantic'),
                (r'funeral|memorial|obituar|condolence|tribute|grief', 'solemn'), (r'christmas|diwali|holiday|festival|celebrat|new year|eid|holi', 'festive'),
                (r'security|software|code|program|ai\b|machine learning|data|cloud|network|engineer|api', 'technical'), (r'space|future|robot|quantum', 'futuristic'),
                (r'finance|quarter|business|startup|sales|market|investor|strategy|company', 'corporate'), (r'research|study|history|science|thesis|lecture|course', 'academic'),
                (r'garden|plant|nature|health|wellness|yoga|food|recipe|organic|climate|ocean|forest', 'natural'), (r'luxury|jewel|fashion|hotel|wine|perfume', 'luxurious'),
                (r'art|design|photograph|gallery|music|portfolio', 'artistic'), (r'coffee|bakery|cafe|home|family|community', 'warm'), (r'retro|vintage|classic car|vinyl', 'vintage'),
                (r'news|magazine|story|journal|blog', 'editorial'), (r'farm|craft|wood|countryside|cabin', 'rustic'), (r'fitness|sport|gym|marathon|energy', 'energetic')]


def topic_mood(text):
    lowered = (text or '').lower()
    for pattern, mood in _TOPIC_MOODS:
        if re.search(pattern, lowered):
            return mood
    return 'friendly'


def _palette_for(mood, pins, preferred=None, avoid=None):
    candidates = list(PALETTES.values())
    if pins.get('tone'):
        candidates = [p for p in candidates if p['tone'] == pins['tone']] or candidates
    fitting = [p for p in candidates if mood in p['moods']]
    pool = fitting or candidates
    if avoid:
        pool = [p for p in pool if p['id'] != avoid] or pool
    if pins.get('hue') is not None:
        pool = sorted(pool, key=lambda p: (hue_distance(hue(p['accent'])[0], pins['hue']) if hue(p['accent'])[1] > 0.2 else 180))
        if not fitting or hue_distance(hue(pool[0]['accent'])[0], pins['hue']) > 35:
            near = sorted(candidates, key=lambda p: hue_distance(hue(p['accent'])[0], pins['hue']) if hue(p['accent'])[1] > 0.2 else 180)
            near = [p for p in near if p['id'] != avoid] or near
            if hue_distance(hue(near[0]['accent'])[0], pins['hue']) < hue_distance(hue(pool[0]['accent'])[0], pins['hue']):
                return near[0]
        return pool[0]
    if preferred in PALETTES and PALETTES[preferred] in pool:
        return PALETTES[preferred]
    if preferred in PALETTES:  # the nearest fitting palette to what she asked for
        want = hue(PALETTES[preferred]['accent'])[0]
        return sorted(pool, key=lambda p: (PALETTES[preferred]['tone'] != p['tone'], hue_distance(hue(p['accent'])[0], want)))[0]
    return pool[0]


def _type_for(mood, pins, preferred=None, avoid=None):
    pool = [t for t in TYPES.values() if mood in t['moods']] or list(TYPES.values())
    if pins.get('typekind'):
        kind = [t for t in TYPES.values() if t['kind'] == pins['typekind']]
        pool = [t for t in pool if t['kind'] == pins['typekind']] or kind
    if avoid:
        pool = [t for t in pool if t['id'] != avoid] or pool
    return TYPES[preferred] if preferred in TYPES and TYPES[preferred] in pool else pool[0]


def resolve(raw, pins=None, avoid=None, topic=''):
    """A complete, valid design from June's choice (raw), the person's explicit words (pins) and,
    when restyling, the previous design to differ from (avoid). Never raises."""
    raw = raw if isinstance(raw, dict) else {}
    pins = dict(pins or {})
    avoid = avoid if isinstance(avoid, dict) else {}
    if pins.get('preset'):
        raw = dict(raw, **PRESETS[pins['preset']])
    mood = pins.get('mood') or (raw.get('mood') if raw.get('mood') in MOODS else None) or topic_mood(topic)
    rules = MOODS[mood]
    pinned_palette = pins.get('palette') or (pins.get('preset') and PRESETS[pins['preset']]['palette'])
    if pinned_palette in PALETTES and not (pins.get('tone') and PALETTES[pinned_palette]['tone'] != pins['tone']):
        palette = PALETTES[pinned_palette]
    else:
        palette = _palette_for(mood, pins, raw.get('palette'), avoid.get('palette'))
    kind = _type_for(mood, pins, (pins.get('preset') and PRESETS[pins['preset']]['type']) or raw.get('type'), avoid.get('type'))
    design = dict(mood=mood, palette=palette['id'], type=kind['id'])
    for key in PARAMS:
        allowed = rules[key]
        value = pins.get(key) if pins.get(key) in OPTIONS[key] else raw.get(key)
        if value not in allowed and not (pins.get(key) == value and value in OPTIONS[key]):
            value = allowed[0]
        if key in ('motif', 'cover', 'layout') and avoid.get(key) == value and not pins.get(key):
            value = next((v for v in allowed if v != value), value)
        design[key] = value
    accent = raw.get('accent_color')
    if isinstance(accent, str) and re.fullmatch(r'#?[0-9A-Fa-f]{6}', accent) and not pinned_palette and pins.get('hue') is None:
        design['accent_color'] = accent.lstrip('#').upper()
    design['reason'] = clean_reason(raw.get('reason'))
    # What the person asked for in words, kept so a later restyle ("change its colours") still honours it.
    asked = {k: pins[k] for k in ('tone', 'typekind', 'density') if isinstance(pins.get(k), str)}
    if asked:
        design['asked'] = asked
    return design


def clean_reason(value):
    """June's reason as a tidy sentence: Latin text only, cut at a word or clause, never mid-garble."""
    if not isinstance(value, str):
        return ''
    text = re.sub(r'[\x00-\x1f\x7f<>]', ' ', value)
    text = re.split(r'[^\x20-\x7E\u00A0-\u024F\u2010-\u2027]', text)[0]  # stop at the first character from another script
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > 140:
        text = text[:140].rsplit(' ', 1)[0]
    if not re.search(r'[.!?]$', text):
        cut = max(text.rfind(mark) for mark in (',', ';', ':', ' —', ' –'))
        text = (text[:cut] if cut >= 25 else text).rstrip(' ,;:—–-')
    return text


def carried(previous, new_pins):
    """Pins for a restyle: the person's earlier words (e.g. dark) still hold unless the new request says otherwise."""
    earlier = (previous or {}).get('asked') if isinstance(previous, dict) else None
    pins = {k: v for k, v in (earlier or {}).items() if k in ('tone', 'typekind', 'density') and isinstance(v, str)}
    if new_pins.get('preset') or new_pins.get('palette'):
        pins.pop('tone', None)  # a named look or palette decides its own tone
    pins.update(new_pins)
    return pins


def restyle_pins(previous, said, house):
    """Pins for a restyle, strongest first: words said now, then words said when it was made, then the house style."""
    pins = carried(previous, said)
    return pins if pins else dict(house or {})


def shown_reason(design):
    """The reason as said to the person: only a complete sentence (it ended on its own with . ! or ?), else nothing.
    A note cut at its length limit reads as a broken half-sentence ("the audience is … seeking a warm, inviting")."""
    text = (design or {}).get('reason') or ''
    if not re.search(r'[.!?]$', text) or len(text.split()) < 3:
        return ''
    return text


def colours(design):
    """The palette with the accent applied and every text colour checked for contrast."""
    palette = dict(PALETTES[design['palette']])
    if design.get('accent_color'):
        palette['accent'] = design['accent_color']
    paper, ink = palette['paper'], palette['ink']
    for key in ('ink', 'body', 'muted'):
        palette[key] = readable(palette[key], paper, 4.5)
    palette['accent_text'] = readable(palette['accent'], paper, 4.5)
    palette['accent_shape'] = readable(palette['accent'], paper, 1.4)
    palette['tint'] = mix(palette['accent'], paper, 0.84 if palette['tone'] == 'light' else 0.78)
    palette['on_tint'] = readable(ink, palette['tint'], 4.5)
    if design.get('accent') == 'generous':
        cover = palette['accent']
    else:
        cover = ink if palette['tone'] == 'light' else palette['surface']
    best = max((paper, ink, 'FFFFFF', '111111'), key=lambda c: contrast(c, cover))
    if contrast(best, cover) < 4.5:
        cover = readable(cover, best, 4.5)
    palette['cover'] = cover
    palette['on_cover'] = max((paper, ink, 'FFFFFF', '111111'), key=lambda c: contrast(c, cover))
    palette['on_cover_muted'] = readable(mix(palette['on_cover'], cover, 0.25), cover, 4.5)
    palette['on_accent'] = max((paper, ink, 'FFFFFF', '111111'), key=lambda c: contrast(c, palette['accent']))
    return palette


def describe(design):
    palette, kind = PALETTES[design['palette']], TYPES[design['type']]
    return f'{palette["name"]} ({palette["look"]}), {kind["name"]}, {OPTIONS["motif"][design["motif"]]}, {OPTIONS["cover"][design["cover"]]}'


def label(design):
    return f'{PALETTES[design["palette"]]["name"]} · {design["mood"]}' if isinstance(design, dict) and design.get('palette') in PALETTES else ''


# --- Asking the model ----------------------------------------------------------------------------------
# June writes about 5 tokens a second on this Mac, so she answers the choices that shape the look most;
# bullet, corners, lines, density and accent use follow her mood (or the person's own words).
CHOSEN = ('motif', 'cover', 'layout', 'heading')
# The model writes fields in alphabetical order, so the names put the decisions in a sensible order:
# why first, then mood, and only then the details that should follow from it.
ORDER = ('reason', 'mood', 'palette', 'type', *CHOSEN)
FIELD = {key: f'step{n}_{key}' for n, key in enumerate(ORDER, 1)}
_ENUMS = dict(mood=list(MOODS), palette=list(PALETTES), type=list(TYPES), **{k: list(OPTIONS[k]) for k in CHOSEN})
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': [FIELD[k] for k in ORDER], 'properties': {
    FIELD['reason']: {'type': 'string', 'maxLength': 140}, **{FIELD[k]: {'type': 'string', 'enum': v} for k, v in _ENUMS.items()}}}


def unpack(answer):
    """The model's step-named fields as plain design keys."""
    if not isinstance(answer, dict):
        return {}
    return {key: answer.get(FIELD[key], answer.get(key)) for key in ORDER}


def prompt(kind_label):
    """Short on purpose: June reads this from scratch each time (about 20 tokens a second on this Mac)."""
    lines = [f'Choose the design of a {kind_label}. First say in under 10 words who it is for and the feeling it needs, then choose a mood that fits, '
             'then a palette, type and details that suit that mood. Fit any style words in the request. JSON only.',
             'Moods suit: kids, parties: playful/festive; business, finance: corporate/professional; tech, software, security: technical/futuristic; '
             'school, research: academic; weddings, love: romantic/elegant; memorials: solemn; nature, food, health: natural/earthy; luxury, fashion: luxurious/elegant; '
             'art, music: artistic/editorial; history, retro: vintage; home, cafes: warm/friendly.',
             'mood: ' + ', '.join(MOODS),
             'palette (light): ' + ', '.join(p['id'] for p in PALETTES.values() if p['tone'] == 'light'),
             'palette (dark): ' + ', '.join(p['id'] for p in PALETTES.values() if p['tone'] == 'dark'),
             'type: ' + ', '.join(f'{t["id"]}={t["look"].split(",")[0]}' for t in TYPES.values())]
    for key in CHOSEN:
        lines.append(f'{key}: ' + ', '.join(OPTIONS[key]))
    return '\n'.join(lines)


async def choose(client, settings, request_text, kind_label, topic, pins=None, avoid=None):
    """June's design for this request. Falls back to mood rules if the model is unavailable."""
    from .knowledge import bounded_json
    ask = f'Request: {request_text}\nTopic: {topic}'
    if avoid:
        ask += f'\nThe person wants a different look from the last one ({describe(avoid)}). Choose a clearly different palette, motif and cover.'
    raw = {}
    try:
        result = await bounded_json(client, settings.ollama + '/api/chat', {
            'model': settings.model, 'stream': False, 'think': False, 'format': SCHEMA, 'keep_alive': MODEL_KEEP_ALIVE,
            'messages': [{'role': 'system', 'content': prompt(kind_label)}, {'role': 'user', 'content': ask}],
            'options': {'temperature': 0.7, 'num_ctx': 4096, 'num_predict': 120},
        }, 16384, 180)
        raw = unpack(json.loads(result['message']['content']))
    except Exception:
        raw = {}
    return resolve(raw, pins or {}, avoid, topic)
