"""Websites June makes: one self-contained page, previewed on this Mac, published to GitHub Pages after review.

The local model writes the words (the same draft shape as a document). June writes the page herself:
every piece of text is escaped, and the page loads nothing from anywhere else. Publishing copies the
site's folder into the person's <account>.github.io repository and pushes one commit. It is outward,
so it is reviewed every time and never remembered; June never force-pushes and never reads a password.
"""
import asyncio
from datetime import date
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import tempfile
import time
import unicodedata
import urllib.request

import certifi

from .errors import JuneError
from .project_commands import ALLOW, GIT, github_url, run, tail
from .tool_plans import Capability

URL = re.compile(r'https://[a-z0-9](?:[a-z0-9-]{0,38})\.github\.io/[a-z0-9]+(?:-[a-z0-9]+)*/')
_LEAD = (r"\s*(?:(?:ok(?:ay)?|so|well|now|and|oh|um|uh|alright|great|nice|yes|yeah)[,.!\s]+)*(?:(?:hey\s+)?june[,!:\s]+)?"
         r"(?:(?:can|could|would|will)\s+you\s+|i\s+(?:want|need)\s+(?:you\s+)?to\s+|let['’]?s\s+)?(?:please\s+)?(?:just\s+|now\s+)?")
_THING = r"(?:it|that|this|(?:the|my|that|this|our)\s+(?:new\s+)?(?:web\s?site|site|web\s?page|page|landing\s+page|portfolio))"
_WHERE = r"(?:online|live|(?:to|on|onto)\s+(?:the\s+)?(?:internet|web|github(?:\s+pages)?))"
PUBLISH = re.compile(_LEAD + r"(?:(?:publish|deploy|launch|upload)\s+" + _THING + r"(?:\s+" + _WHERE + r")?|(?:put|get)\s+" + _THING + r"\s+" + _WHERE
                     + r"|make\s+" + _THING + r"\s+live)(?:\s+(?:please|for\s+me|now))*[\s.!]*", re.I)


def publish_request(text):
    return isinstance(text, str) and len(text) <= 160 and not re.search(r"\b(?:do not|don['’]?t|never)\b", text, re.I) and PUBLISH.fullmatch(text) is not None


_SITE = r"(?:(?:the|my|that|this|our)\s+(?:new\s+)?(?:web\s?site|site|web\s?page|page|landing\s+page|portfolio))"
_FROM = r"(?:from|off)\s+(?:the\s+)?(?:internet|web|github(?:\s+pages)?)"
_TAIL = r"(?:\s+(?:please|for\s+me|now))*[\s.!]*"
_EARLIER = r"(?:the\s+)?(?:old|older|earlier|previous|last)\s+version\s+of\s+" + _SITE
UNPUBLISH = re.compile(_LEAD + r"(?:unpublish\s+" + _THING + r"(?:\s+" + _FROM + r")?|take\s+" + _THING + r"\s+(?:down|offline|" + _FROM + r")"
                       r"|take\s+(?:down|offline)\s+" + _THING + r"|(?:remove|delete|pull)\s+" + _THING + r"\s+(?:offline|" + _FROM + r"))" + _TAIL, re.I)
ROLLBACK = re.compile(_LEAD + r"(?:(?:undo|revert|reverse)\s+(?:the\s+|my\s+|that\s+)?(?:last\s+|latest\s+)?publish(?:ing)?(?:\s+(?:of\s+)?" + _SITE + r")?"
                      r"|(?:roll|revert)\s+back\s+" + _SITE + r"|roll\s+(?:it|" + _SITE + r")\s+back|revert\s+" + _SITE
                      + r"|(?:put|bring)\s+back\s+" + _EARLIER + r"|(?:go\s+back|revert|roll\s+back)\s+to\s+" + _EARLIER + r"|restore\s+" + _EARLIER + r")" + _TAIL, re.I)


def withdraw_request(text):
    """'unpublish' for taking a published page down, 'rollback' for putting back the version published before, else None."""
    if not isinstance(text, str) or len(text) > 160 or re.search(r"\b(?:do not|don['’]?t|never)\b", text, re.I):
        return None
    return 'unpublish' if UNPUBLISH.fullmatch(text) else 'rollback' if ROLLBACK.fullmatch(text) else None


def site_slug(title):
    text = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode().lower()
    text = re.sub(r'<[^>]{0,80}>', ' ', text)
    words = re.findall(r'[a-z0-9]+', text)
    slug = ''
    for word in words:
        if len(slug) + len(word) + 1 > 48: break
        slug = f'{slug}-{word}' if slug else word
    return slug or 'site'


BASE_CSS = """
*{box-sizing:border-box}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--body);font:calc(16px + .15vw)/1.65 var(--body-font)}
h1,h2{font-family:var(--head-font);font-weight:var(--head-weight);color:var(--ink);letter-spacing:-.01em}
h1,h2,p,li{overflow-wrap:break-word}
.wrap{width:min(1100px,100% - 40px);margin:0 auto}
.hero{position:relative;overflow:hidden;isolation:isolate;padding:calc(var(--space) * 2.4) 0 calc(var(--space) * 2)}
.hero h1{font-size:clamp(40px,7.2vw,86px);line-height:1.04;margin:0 0 22px;max-width:15ch}
.hero p{font-size:clamp(18px,2.1vw,22px);max-width:36em;margin:0 0 32px}
.hero .wrap{position:relative;z-index:1}
.mark{display:block;width:64px;height:calc(var(--stroke) + 3px);background:var(--accent);margin-bottom:26px}
.button{display:inline-block;padding:13px 24px;border-radius:var(--pill);background:var(--accent);color:var(--on-accent);font-weight:700;text-decoration:none;transition:transform .15s ease,filter .15s ease}
.button:hover{transform:translateY(-1px);filter:brightness(1.06)}
a:focus-visible,.button:focus-visible{outline:3px solid var(--accent-text);outline-offset:3px}
.art{position:absolute;inset:0;z-index:0;pointer-events:none}
.initial{position:absolute;right:2vw;bottom:-.18em;font:var(--head-weight) clamp(220px,38vw,520px)/1 var(--head-font);color:var(--tint);z-index:0;pointer-events:none}
.on-cover{background:var(--cover);color:var(--on-cover)}
.on-cover h1{color:var(--on-cover)}.on-cover p{color:var(--on-cover-muted)}
.on-paper h1{color:var(--ink)}.on-paper p{color:var(--muted)}
.hero-split{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,.85fr);padding:0}
.hero-split .side{padding:calc(var(--space) * 2.2) max(20px,(100vw - 1100px)/2) calc(var(--space) * 1.8);position:relative;z-index:1}
.hero-split .art{position:relative;min-height:320px}
.hero-band .band{background:var(--cover);color:var(--on-cover);padding:calc(var(--space) * 1.4) 0;text-align:center;position:relative;z-index:1}
.hero-band .band h1,.hero-band .band p{margin-left:auto;margin-right:auto}
.hero-band .band h1{color:var(--on-cover)}.hero-band .band p{color:var(--on-cover-muted)}
.generous .on-cover .button,.generous .hero-split .button{background:var(--on-cover);color:var(--cover)}.hero-band .band .mark{margin:0 auto 26px}
.hero-column{border-left:min(22vw,200px) solid var(--cover)}
.hero-poster h1{font-size:clamp(52px,11vw,150px);max-width:none;line-height:.96;text-transform:var(--poster-case)}
nav{position:sticky;top:0;z-index:5;background:var(--paper);border-bottom:var(--stroke) solid var(--line)}
nav .wrap{display:flex;gap:6px 26px;flex-wrap:wrap;padding:14px 0;font-size:13px;letter-spacing:.08em;text-transform:uppercase}
nav a{color:var(--muted);text-decoration:none;font-weight:700}
nav a:hover{color:var(--accent-text)}
main{padding:var(--space) 0}
section{padding:calc(var(--space) * .9) 0;scroll-margin-top:64px;border-top:var(--stroke) solid var(--line)}
section:first-child{border-top:0}
.generous section:nth-child(even){background:var(--tint);box-shadow:0 0 0 100vmax var(--tint);clip-path:inset(0 -100vmax);border-top:0;color:var(--on-tint)}
.generous section:nth-child(even) h2,.generous section:nth-child(even) li{color:var(--on-tint)}
.num{display:block;font:700 14px/1 var(--body-font);letter-spacing:.16em;color:var(--accent-text);margin-bottom:12px}
h2{font-size:clamp(28px,3.6vw,42px);line-height:1.12;margin:0 0 16px}
.h-bar h2{border-left:calc(var(--stroke) + 4px) solid var(--accent);padding-left:16px}
.h-underline h2{padding-bottom:10px;border-bottom:calc(var(--stroke) + 1px) solid var(--accent);display:inline-block}
.h-smallcaps h2{font-variant:small-caps;letter-spacing:.06em;text-transform:lowercase}
.h-highlight h2{display:inline;background:linear-gradient(transparent 55%,var(--tint) 55%);padding:0 .1em;box-decoration-break:clone;-webkit-box-decoration-break:clone}
.h-highlight .head{margin-bottom:16px}
.text p{margin:0 0 18px;max-width:40em}
ul{list-style:none;margin:6px 0 0;padding:0;counter-reset:pt}
li{position:relative;padding:6px 0 6px 30px;line-height:1.5;color:var(--ink);counter-increment:pt}
li::before{content:var(--glyph);position:absolute;left:0;top:6px;color:var(--accent-text);font-weight:700}
.l-margin-number section{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.7fr);gap:clamp(18px,4vw,64px)}
.l-margin-number .big{display:block;font:var(--head-weight) clamp(56px,8vw,104px)/1 var(--head-font);color:var(--accent-text);margin-bottom:10px}
.l-side-panel section{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:clamp(18px,4vw,56px);align-items:start}
.l-side-panel aside{background:var(--tint);color:var(--on-tint);border-radius:var(--radius);padding:22px 24px;border-left:calc(var(--stroke) + 3px) solid var(--accent)}
.l-side-panel aside li{color:var(--on-tint)}
.l-two-column ul{columns:2 14em;column-gap:40px}
.l-two-column li{break-inside:avoid}
.l-cards ul{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(230px,100%),1fr));gap:14px}
.l-cards li{background:var(--surface);border:var(--stroke) solid var(--line);border-radius:var(--radius);padding:18px 18px 18px 48px}
.l-cards li::before{left:18px;top:18px}
.l-bar .text{max-width:46em}
footer{border-top:var(--stroke) solid var(--line);padding:30px 0 42px;color:var(--muted);font-size:14px}
footer .wrap{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
@media (max-width:760px){.hero:not(.hero-split) .art{opacity:.3}.hero-split{grid-template-columns:1fr}.hero-split .art{min-height:160px}.l-margin-number section,.l-side-panel section{grid-template-columns:1fr}.hero-column{border-left-width:14px}.initial{opacity:.6}}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}.button{transition:none}}
"""

MOTIF_CSS = {
    'circles': ".art::before{content:'';position:absolute;width:min(56vw,560px);aspect-ratio:1;border-radius:50%;background:var(--m1);right:-12vw;top:-18vw}"
               ".art::after{content:'';position:absolute;width:min(14vw,130px);aspect-ratio:1;border-radius:50%;background:var(--m2);right:24vw;bottom:-30px}",
    'slabs': ".art{background:linear-gradient(112deg,transparent 0 58%,var(--m1) 58% 66%,transparent 66% 71%,var(--m2) 71% 77%,transparent 77% 82%,var(--m3) 82% 86%,transparent 86%)}",
    'stripes': ".art{background:repeating-linear-gradient(90deg,var(--m1) 0 14px,transparent 14px 30px,var(--m2) 30px 38px,transparent 38px 56px);"
               "-webkit-mask:linear-gradient(90deg,transparent 55%,#000 75%);mask:linear-gradient(90deg,transparent 55%,#000 75%)}",
    'dots': ".art{background:radial-gradient(circle,var(--m1) 3px,transparent 3.6px) 0 0/24px 24px;-webkit-mask:linear-gradient(90deg,transparent 45%,#000 85%);mask:linear-gradient(90deg,transparent 45%,#000 85%)}",
    'grid': ".art{background:linear-gradient(var(--m3) 1px,transparent 1px) 0 0/32px 32px,linear-gradient(90deg,var(--m3) 1px,transparent 1px) 0 0/32px 32px;"
            "-webkit-mask:linear-gradient(90deg,transparent 35%,#000 80%);mask:linear-gradient(90deg,transparent 35%,#000 80%)}",
    'blobs': ".art::before{content:'';position:absolute;width:min(48vw,480px);aspect-ratio:1.15;background:var(--m1);border-radius:58% 42% 55% 45%/48% 60% 40% 52%;right:-6vw;top:-10vw;transform:rotate(-12deg)}"
             ".art::after{content:'';position:absolute;width:min(20vw,200px);aspect-ratio:1;background:var(--m2);border-radius:42% 58% 47% 53%/55% 45% 55% 45%;right:28vw;bottom:-50px}",
    'frame': ".art{inset:18px;border:calc(var(--stroke) + 1px) solid var(--m1);border-radius:var(--radius)}",
    'rules': ".art::before,.art::after{content:'';position:absolute;left:max(20px,(100% - 1100px)/2);right:max(20px,(100% - 1100px)/2);height:calc(var(--stroke) + 1px);background:var(--m1)}"
             ".art::before{top:28px}.art::after{bottom:28px;background:var(--m2)}",
    'waves': ".art::before,.art::after{content:'';position:absolute;left:-10%;width:120%;height:60%;border-radius:50%}"
             ".art::before{bottom:-40%;background:var(--m3)}.art::after{bottom:-48%;left:5%;background:var(--m1)}",
    'none': ".art{display:none}",
}
GLYPHS = {'square': r"'\25A0'", 'dot': r"'\25CF'", 'dash': r"'\2013'", 'arrow': r"'\2192'", 'check': r"'\2713'", 'number': "counter(pt) '.'"}


def site_css(design):
    from .designs import TYPES, colours, mix
    c, t = colours(design), TYPES[design['type']]
    hero_bg = c['cover'] if design['cover'] in ('bleed',) or (design['cover'] == 'poster' and design['accent'] == 'generous') else c['paper']
    m1 = c['accent'] if hero_bg != c['accent'] else c['accent2']
    m2 = mix(hero_bg, c['accent2'] if hero_bg != c['accent2'] else c['paper'], 0.4)
    m3 = mix(hero_bg, m1, 0.28)
    vars_ = dict(paper=c['paper'], surface=c['surface'], ink=c['ink'], body=c['body'], muted=c['muted'], accent=c['accent'], accent2=c['accent2'], line=c['line'],
                 cover=c['cover'], tint=c['tint'])
    vars_.update({'accent-text': c['accent_text'], 'on-cover': c['on_cover'], 'on-cover-muted': c['on_cover_muted'], 'on-tint': c['on_tint'], 'on-accent': c['on_accent'],
                  'm1': m1, 'm2': m2, 'm3': m3})
    root = ';'.join(f'--{k}:#{v}' for k, v in vars_.items())
    root += (f";--head-font:{t['css_head']};--body-font:{t['css_body']};--head-weight:{700 if t['head_bold'] else 400}"
             f";--radius:{dict(sharp='0', soft='10px', round='22px')[design['corners']]};--pill:{dict(sharp='0', soft='8px', round='999px')[design['corners']]}"
             f";--stroke:{dict(hairline='1px', regular='2px', heavy='4px')[design['lines']]};--space:{dict(airy='88px', balanced='68px', compact='48px')[design['density']]}"
             f";--glyph:{GLYPHS[design['bullet']]};--poster-case:{'uppercase' if design['heading'] == 'smallcaps' else 'none'}")
    return (f':root{{{root};color-scheme:{"dark" if c["tone"] == "dark" else "light"}}}' + BASE_CSS + MOTIF_CSS[design['motif']]
            + ('.hero-band .art{opacity:.9}.hero-band .art::after{display:none}' if design['cover'] == 'band' else '')
            + ('.hero-band .art::before{bottom:auto;top:-42%}' if design['cover'] == 'band' and design['motif'] == 'waves' else ''))


def site_html(draft, design=None):
    from .designs import resolve
    design = design if isinstance(design, dict) and design.get('palette') else resolve({}, {}, None, draft['title'])
    title, summary = escape(draft['title']), escape(draft['summary'])
    links = ''.join(f'<a href="#s{i}">{escape(s["heading"])}</a>' for i, s in enumerate(draft['sections'], 1))
    layout = design['layout']
    blocks = []
    for i, section in enumerate(draft['sections'], 1):
        paragraphs = ''.join(f'<p>{escape(p)}</p>' for p in re.split(r'(?<=[.!?])\s{2,}', section['text']) if p) if section['text'] else ''
        points = ('<ul>' + ''.join(f'<li>{escape(b)}</li>' for b in section['bullets']) + '</ul>') if section['bullets'] else ''
        number = f'<span class="big">{i:02d}</span>' if layout == 'margin-number' else (f'<span class="num">{i:02d}</span>' if design['heading'] == 'number' else '')
        head = f'<div class="head">{number}<h2>{escape(section["heading"])}</h2></div>'
        if layout == 'margin-number':
            blocks.append(f'<section id="s{i}">{head}<div class="text">{paragraphs}{points}</div></section>')
        elif layout == 'side-panel':
            aside = f'<aside>{points}</aside>' if points else ''
            blocks.append(f'<section id="s{i}"><div>{head}<div class="text">{paragraphs}</div></div>{aside}</section>')
        else:
            blocks.append(f'<section id="s{i}">{head}<div class="text">{paragraphs}{points}</div></section>')
    cover = design['cover']
    initial = escape((re.findall(r'[A-Za-z0-9]', draft['title']) or ['J'])[0].upper())
    text = (f'<span class="mark"></span><h1>{title}</h1>' + (f'<p>{summary}</p>' if summary else '') + '<a class="button" href="#s1">Read more</a>')
    if cover == 'split':
        hero = f'<header class="hero hero-split"><div class="side on-cover">{text}</div><div class="art" aria-hidden="true"></div></header>'
    elif cover == 'band':
        hero = f'<header class="hero hero-band on-paper"><div class="art" aria-hidden="true"></div><div class="band"><div class="wrap">{text}</div></div></header>'
    else:
        tone = 'on-cover' if cover == 'bleed' or (cover == 'poster' and design['accent'] == 'generous') else 'on-paper'
        extra = f'<span class="initial" aria-hidden="true">{initial}</span>' if cover == 'numeral' else ''
        hero = f'<header class="hero hero-{cover} {tone}"><div class="art" aria-hidden="true"></div>{extra}<div class="wrap">{text}</div></header>'
    classes = f'l-{layout} h-{design["heading"]}' + (' generous' if design['accent'] == 'generous' else '')
    year = date.today().year
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:">\n'
            f'<meta name="description" content="{summary}">\n<meta name="generator" content="June">\n'
            f'<title>{title}</title>\n<style>{site_css(design)}</style>\n</head>\n<body class="{classes}">\n{hero}\n'
            f'<nav aria-label="Sections"><div class="wrap">{links}</div></nav>\n<main class="wrap">{"".join(blocks)}</main>\n'
            f'<footer><div class="wrap"><span>© {year} {title}</span><span>Made with June</span></div></footer>\n</body>\n</html>\n')


def build_site(path, draft, design=None):
    Path(path).write_text(site_html(draft, design), encoding='utf-8')
    return len(draft['sections'])


def inspect_site(path, draft):
    text = Path(path).read_text(encoding='utf-8')
    if f'<title>{escape(draft["title"])}</title>' not in text or escape(draft['sections'][-1]['heading']) not in text:
        raise ValueError('site')
    return len(draft['sections']), None


def folder_digest(folder):
    """sha256 over every file's relative name and bytes, so any edit after review is noticed."""
    hasher = hashlib.sha256()
    items = sorted(Path(folder).rglob('*'))
    if Path(folder).is_symlink() or any(p.is_symlink() for p in items):
        raise JuneError('invalid-site', 'Website folders cannot contain symbolic links. Nothing was published.', 400)
    for item in (p for p in items if p.is_file()):
        hasher.update(str(item.relative_to(folder)).encode() + b'\0' + item.read_bytes() + b'\0')
    return hasher.hexdigest()


def github_owner(projects, runner=run):
    """The one GitHub account the person's saved projects push to, or None when there is none or more than one."""
    owners = set()
    for project in projects:
        code, output = runner([GIT, '-C', project['folderPath'], 'remote', 'get-url', 'origin'], 10)
        page = github_url(output.strip()) if code == 0 else None
        if page:
            owners.add(page.split('/')[3])
    return owners.pop() if len(owners) == 1 else None


async def fetch_page(url):
    def get():
        if not URL.fullmatch(url):
            return 0, ''
        request = urllib.request.Request(url, headers={'User-Agent': 'June', 'Cache-Control': 'no-cache'})
        try:
            # Use the same maintained CA bundle as HTTPX. Some macOS Python installs
            # have no system CA file; never solve that by disabling TLS verification.
            context = ssl.create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(request, timeout=10, context=context) as reply:
                return reply.status, reply.read(400000).decode('utf-8', 'replace')
        except urllib.error.HTTPError as failure:
            return failure.code, ''
        except (OSError, ValueError):
            return 0, ''
    return await asyncio.to_thread(get)


def register(plans, creations, commands, *, runner=run, fetch=fetch_page, owner=None, remote=None, pause=10):
    """Add the site-publish intent. `owner` and `remote` are replaceable in tests; by default the account
    comes from the saved projects' GitHub remotes and the repository is <account>.github.io on github.com."""
    owner = owner or (lambda: github_owner(commands.projects(), runner))
    remote = remote or (lambda account: f'https://github.com/{account}/{account}.github.io.git')
    work_root = Path(creations.directory) / 'pages'
    invalid = lambda message: JuneError('invalid-plan', message, 400)

    def git(folder, *arguments, timeout=60):
        return runner([GIT, '-C', str(folder), *arguments], timeout)

    publish_lock = asyncio.Lock()
    history_root = Path(creations.directory) / 'published'
    KEEP = 10  # published versions kept on this Mac per site, for undoing a publish
    PUBLISHED, CHANGED = 'Nothing was published.', 'Nothing was changed.'

    def history(slug):
        try:
            entries = json.loads((history_root / slug / 'versions.json').read_text())
        except (OSError, ValueError):
            return []
        return [e for e in entries if isinstance(e, dict) and type(e.get('n')) is int and isinstance(e.get('digest'), str)] if isinstance(entries, list) else []

    def private(path):
        """Saved published versions are this user's alone: every folder from history_root down is 0700, files 0600."""
        for folder in (history_root, *([path] if path != history_root else [])):
            folder.mkdir(parents=True, exist_ok=True, mode=0o700); os.chmod(folder, 0o700)
        for item in path.rglob('*'):
            os.chmod(item, 0o700 if item.is_dir() else 0o600)

    def save_history(slug, entries):
        folder = history_root / slug
        private(folder)
        temporary = folder / 'versions.json.tmp'
        temporary.write_text(json.dumps(entries))
        os.replace(temporary, folder / 'versions.json')

    def remember(payload, folder, digest):
        """Keep a copy of exactly what went online, so 'undo the last publish' can put it back later."""
        entries = history(payload['slug'])
        if entries and entries[-1]['digest'] == digest:
            return
        number = entries[-1]['n'] + 1 if entries else 1
        target = history_root / payload['slug'] / str(number)
        private(target.parent)
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(folder, target)
        private(target.parent)
        entries.append(dict(n=number, digest=digest, title=payload['title'], time=time.time()))
        for old in entries[:-KEEP]:
            shutil.rmtree(history_root / payload['slug'] / str(old['n']), ignore_errors=True)
        save_history(payload['slug'], entries[-KEEP:])

    def failed(message, nothing, hard=True):
        return dict(verified=False, failed=hard, message=f'{message} {nothing}'.strip())

    def prepare(payload, nothing):
        """A fresh copy of the Pages repository at its default branch: (clone, branch, found), or a failure."""
        account, repo = payload['owner'], payload['repo']
        clone = work_root / repo
        if (clone / '.git').is_dir():
            code, output = git(clone, 'fetch', '--depth', '1', 'origin', timeout=120)
        else:
            shutil.rmtree(clone, ignore_errors=True)
            work_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            code, output = runner([GIT, 'clone', '--depth', '1', payload['remote'], str(clone)], 150)
        if code != 0:
            if re.search(r'not found|does not exist|does not appear to be a git repository', output, re.I):
                return failed(f'Your GitHub account {account} has no repository named {repo} yet.', nothing + (f' One time only: open github.com/new, name it exactly {repo}, '
                              'choose Public, click Create repository, then ask me to publish again.' if nothing == PUBLISHED else ''))
            return failed('June could not reach your GitHub repository.', nothing + ' ' + tail(output), code > 0)
        code, output = git(clone, 'ls-remote', '--symref', 'origin', 'HEAD', timeout=60)
        found = re.search(r'ref: refs/heads/(\S+)\s+HEAD', output) if code == 0 else None
        branch = found[1] if found else 'main'
        if found:
            code, output = git(clone, 'fetch', '--depth', '1', 'origin', f'+refs/heads/{branch}:refs/remotes/origin/{branch}', timeout=120)  # '+': only June's local tracking copy follows GitHub; pushes are never forced
            if code != 0:
                return failed('The website branch could not be fetched.', nothing + ' ' + tail(output))
            for arguments in (('checkout', '-q', '-B', branch, f'origin/{branch}'), ('reset', '-q', '--hard', f'origin/{branch}'), ('clean', '-q', '-fd')):
                code, output = git(clone, *arguments, timeout=30)
                if code != 0:
                    return failed('The website repository could not be prepared.', nothing + ' ' + tail(output))
        else:
            code, output = git(clone, 'symbolic-ref', 'HEAD', f'refs/heads/{branch}', timeout=10)
            if code != 0:
                return failed('The empty website repository could not be prepared.', nothing + ' ' + tail(output))
        return clone, branch, found

    def deliver(clone, branch, found, slug, message, nothing):
        """Stage only the site's folder, then one ordinary commit and push (never forced). {'changed': bool} or a failure."""
        if not commands.github():
            return failed(ALLOW, nothing)
        code, output = git(clone, 'add', '-A', '--', slug, timeout=30)
        if code != 0:
            return failed('The website could not be staged.', nothing + ' ' + tail(output))
        code, output = git(clone, 'diff', '--cached', '--quiet', timeout=30)
        if code not in (0, 1):
            return failed('The website changes could not be checked.', nothing + ' ' + tail(output))
        if code == 0:
            return dict(changed=False)
        code, output = git(clone, 'commit', '-q', '-m', message, timeout=60)
        if code != 0:
            return failed('The commit for your website did not succeed.', nothing + ' ' + tail(output))
        if not commands.github():
            return failed(ALLOW, nothing)
        code, output = git(clone, 'push', 'origin', f'HEAD:refs/heads/{branch}', timeout=150)
        if code != 0:
            git(clone, 'reset', '-q', '--hard', f'origin/{branch}', timeout=30) if found else None
            return failed('GitHub did not accept the push.', nothing + ' ' + tail(output), code > 0)
        return dict(changed=True)

    async def exclusive(work):
        async with publish_lock:
            worker = asyncio.create_task(asyncio.to_thread(work))
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                await worker  # do not release the clone to another publisher mid-push
                raise

    async def watch(url, expected):
        """Whether the address serves exactly `expected` (a sha256), or is gone when `expected` is None."""
        for attempt in range(15 if fetch else 0):
            status, body = await fetch(url)
            if expected is None and status == 404:
                return True
            if expected is not None and status == 200 and hashlib.sha256(body.encode('utf-8')).hexdigest() == expected:
                return True
            await asyncio.sleep(pause)
        return False

    CHANGED_SINCE = 'The website changed since you reviewed the card, so nothing was published. Ask again to review it.'

    async def publish(payload):
        def push():
            # Freeze the reviewed bytes before any network operation. Never copy the
            # mutable source folder again after checking this private snapshot.
            with tempfile.TemporaryDirectory(prefix='june-publish-') as temporary:
                source = Path(payload['folder'])
                folder_digest(source)  # reject links before copying
                folder = Path(temporary) / 'site'
                shutil.copytree(source, folder, symlinks=True)
                if folder_digest(folder) != payload['digest']:
                    return dict(verified=False, failed=True, message=CHANGED_SINCE)
                return push_snapshot(folder)

        def push_snapshot(folder):
            if not commands.github():
                return dict(verified=False, failed=True, message=ALLOW + ' Nothing was published.')
            if not (folder / 'index.html').is_file() or folder_digest(folder) != payload['digest']:
                return dict(verified=False, failed=True, message=CHANGED_SINCE)
            prepared = prepare(payload, PUBLISHED)
            if isinstance(prepared, dict):
                return prepared
            clone, branch, found = prepared
            target = clone / payload['slug']
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(folder, target)
            expected = hashlib.sha256((folder / 'index.html').read_bytes()).hexdigest()
            done = deliver(clone, branch, found, payload['slug'], f'Publish {payload["title"]} with June', PUBLISHED)
            if 'changed' not in done:
                return done
            creations.set_url(payload['id'], payload['url'])
            remember(payload, folder, payload['digest'])
            return dict(verified=True, message='', expected=expected, unchanged=not done['changed'])

        result = await exclusive(push)
        if not result.get('verified') or result.get('message'):
            result.pop('live', None)
            return result
        if await watch(payload['url'], result['expected']):
            return dict(verified=True, message=('The repository already contains this version. ' if result.get('unchanged') else '') + f'“{payload["title"]}” is live at {payload["url"]}. I opened the address and checked that the page is there.')
        return dict(verified=True, message=(f'The repository already contains “{payload["title"]}”' if result.get('unchanged') else f'I pushed “{payload["title"]}” to {payload["repo"]}') + ', but this exact page version was not live yet when I checked. GitHub usually needs a minute or two; '
                    f'it will be at {payload["url"]}. If it still is not there in five minutes, open the repository on github.com, go to Settings → Pages, and choose “Deploy from a branch”.')

    async def unpublish(payload):
        def remove():
            if not commands.github():
                return failed(ALLOW, CHANGED)
            prepared = prepare(payload, CHANGED)
            if isinstance(prepared, dict):
                return prepared
            clone, branch, found = prepared
            target = clone / payload['slug']
            if not target.exists():
                creations.set_url(payload['id'], None)
                return dict(verified=True, message='', absent=True)
            shutil.rmtree(target)
            done = deliver(clone, branch, found, payload['slug'], f'Take down {payload["title"]} with June', CHANGED)
            if 'changed' not in done:
                return done
            creations.set_url(payload['id'], None)
            return dict(verified=True, message='')

        result = await exclusive(remove)
        if not result.get('verified'):
            return result
        where = f'{payload["slug"]}/ was already gone from {payload["repo"]}' if result.get('absent') else f'I removed {payload["slug"]}/ from {payload["repo"]}'
        if await watch(payload['url'], None):
            return dict(verified=True, message=f'“{payload["title"]}” is no longer online: {where}, and {payload["url"]} now says the page isn’t there. '
                        'The website is still saved on this Mac; say “publish it” to put it back.')
        return dict(verified=True, message=f'{where}, but {payload["url"]} was still showing a page when I last checked. GitHub can take a few minutes to stop serving it; '
                    'open the address again later to confirm it is gone. The website is still saved on this Mac.')

    async def rollback(payload):
        def restore():
            if not commands.github():
                return failed(ALLOW, CHANGED)
            entries = history(payload['slug'])
            if len(entries) < 2 or entries[-1]['digest'] != payload['current'] or entries[-2]['n'] != payload['previous']:
                return failed('What was published changed since you reviewed the card. Ask again to review it.', CHANGED)
            with tempfile.TemporaryDirectory(prefix='june-rollback-') as temporary:
                saved = history_root / payload['slug'] / str(payload['previous'])
                folder = Path(temporary) / 'site'
                try:
                    folder_digest(saved)  # reject links before copying
                    shutil.copytree(saved, folder, symlinks=True)
                    intact = (folder / 'index.html').is_file() and folder_digest(folder) == payload['digest']
                except (OSError, JuneError):
                    intact = False
                if not intact:
                    return failed('The earlier version saved on this Mac is missing or was changed, so June will not put it online.', CHANGED)
                prepared = prepare(payload, CHANGED)
                if isinstance(prepared, dict):
                    return prepared
                clone, branch, found = prepared
                target = clone / payload['slug']
                try:
                    online = folder_digest(target) if target.is_dir() else None
                except JuneError:
                    online = None
                if online != payload['current']:
                    return failed(f'The page in {payload["repo"]} was changed or removed outside June since June last published it, so June did not replace it.', CHANGED)
                shutil.rmtree(target)
                shutil.copytree(folder, target)
                expected = hashlib.sha256((folder / 'index.html').read_bytes()).hexdigest()
                done = deliver(clone, branch, found, payload['slug'], f'Put back the earlier {payload["title"]} with June', CHANGED)
                if 'changed' not in done:
                    return done
            newest = entries.pop()
            shutil.rmtree(history_root / payload['slug'] / str(newest['n']), ignore_errors=True)
            save_history(payload['slug'], entries)
            creations.set_url(payload['id'], payload['url'])
            return dict(verified=True, message='', expected=expected)

        result = await exclusive(restore)
        if not result.get('verified'):
            return result
        if await watch(payload['url'], result['expected']):
            return dict(verified=True, message=f'“{payload["title"]}” is live at {payload["url"]} again in the version from {payload["when"]}. I opened the address and checked that the page is there.')
        return dict(verified=True, message=f'I put back the version of “{payload["title"]}” from {payload["when"]} in {payload["repo"]}, but it was not live yet when I checked. '
                    f'GitHub usually needs a minute or two; open {payload["url"]} again shortly.')

    def target(value, present=True):
        if not isinstance(value, dict) or set(value) != {'id'} or not isinstance(value['id'], str) or not re.fullmatch(r'[a-f0-9]{32}', value['id']):
            raise invalid('June cannot plan that request.')
        site = creations.site(value['id'], present=present)
        account = owner()
        if not account or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})', account):
            raise JuneError('no-github-account', 'June does not know your GitHub account yet. Save a project that is on GitHub in Systems → Hands, then ask again.', 409)
        repo = f'{account.lower()}.github.io'
        return site, account, repo, f'https://{repo}/{site["slug"]}/'

    def published(site):
        if not site.get('url'):
            raise JuneError('not-published', f'“{site["title"]}” isn’t online, so there is nothing to change on the internet. Say “publish it” to put it online.', 409)

    def take_down_steps(value):
        site, account, repo, url = target(value, present=False)
        published(site)
        payload = dict(id=site['id'], title=site['title'], slug=site['slug'], owner=account, repo=repo, remote=remote(account), url=url)
        return [('site.unpublish', payload,
                 f'Take “{site["title"]}” off the internet at {url}. June removes the folder {site["slug"]}/ and everything in it from your GitHub repository {account}/{repo} '
                 'and pushes one commit; nothing else in the repository changes. June never force-pushes. The website stays saved on this Mac. Contacts github.com.',
                 f'Take down {site["title"]}')]

    def rollback_steps(value):
        site, account, repo, url = target(value, present=False)
        published(site)
        entries = history(site['slug'])
        if len(entries) < 2:
            raise JuneError('no-earlier-version', f'“{site["title"]}” has only been published in one version, so there is no earlier one to go back to. '
                            'To remove it from the internet instead, say “take my website down”.', 409)
        before = entries[-2]
        when = time.strftime('%-d %b at %H:%M', time.localtime(before['time'])) if isinstance(before.get('time'), (int, float)) else 'earlier'
        payload = dict(id=site['id'], title=site['title'], slug=site['slug'], owner=account, repo=repo, remote=remote(account), url=url,
                       current=entries[-1]['digest'], previous=before['n'], digest=before['digest'], when=when)
        return [('site.rollback', payload,
                 f'Undo the last publish of “{site["title"]}” at {url}: June puts back the version you published on {when}, saved on this Mac, into {site["slug"]}/ of your '
                 f'GitHub repository {account}/{repo} and pushes one commit. It replaces the version online now and is public. If the page on GitHub was changed outside '
                 'June, nothing is replaced. June never force-pushes. Contacts github.com.',
                 f'Undo the last publish of {site["title"]}')]

    def steps(value):
        site, account, repo, url = target(value)
        files = [p for p in Path(site['folder']).rglob('*') if p.is_file()]
        payload = dict(id=site['id'], title=site['title'], folder=site['folder'], slug=site['slug'], owner=account, repo=repo, remote=remote(account), url=url,
                       digest=folder_digest(site['folder']))
        return [('site.publish', payload,
                 f'Publish “{site["title"]}” on the public internet at {url}. June copies its folder ({len(files)} file{"" if len(files) == 1 else "s"}) into the folder {site["slug"]}/ '
                 f'of your GitHub repository {account}/{repo} and pushes one commit. Anyone with the link can read it, so check the page first. If {site["slug"]}/ is already there, '
                 'it is replaced; nothing else in the repository changes. June never force-pushes. Contacts github.com.',
                 f'Publish {site["title"]}')]
    steps.accepts_input = take_down_steps.accepts_input = rollback_steps.accepts_input = True
    # Outward: reviewed every time, never remembered.
    plans.capabilities['site.publish'] = Capability('site.publish', 'Publish a website June made to GitHub Pages', 'github', 'outward', False, publish, timeout=330)
    plans.capabilities['site.unpublish'] = Capability('site.unpublish', 'Take a website June published off GitHub Pages', 'github', 'outward', False, unpublish, timeout=330)
    plans.capabilities['site.rollback'] = Capability('site.rollback', 'Put back the version of a website published before', 'github', 'outward', False, rollback, timeout=330)
    plans.intents['site-publish'] = steps
    plans.intents['site-unpublish'] = take_down_steps
    plans.intents['site-rollback'] = rollback_steps
    plans.creations = creations


async def publish_chat(question, request_key, plans):
    """A review card for publishing the newest website, or None when the question is not about that."""
    creations = getattr(plans, 'creations', None) if plans is not None else None
    if creations is None or not publish_request(question):
        return None
    sites = [c for c in creations.state()['creations'] if c['kind'] == 'site' and c['exists']]
    if not sites:
        return dict(reply='I haven’t made a website yet. Ask me, for example: make a website about my bakery. Then say “publish it”.')
    try:
        reply = await plans.propose({'requestId': request_key, 'intent': 'site-publish', 'input': {'id': sites[0]['id']}})
    except JuneError as failure:
        return dict(reply=failure.message + ' Nothing was published.')
    plan = reply['plan']
    url = plan['steps'][0]['preview'].split(' at ', 1)[1].split('. ', 1)[0] if ' at ' in plan['steps'][0]['preview'] else ''
    return dict(plan=plan, serverNow=reply['serverNow'],
                reply=f'I’ve prepared “{plan["steps"][0]["label"]}”. Check the card below: approving puts the page on the public internet' + (f' at {url}' if url else '')
                + '. It’s a draft from my local model, so say “open it” to read it first if you haven’t.')


async def withdraw_chat(question, request_key, plans):
    """A review card for taking the newest published website down or undoing its last publish, or None when not asked."""
    creations = getattr(plans, 'creations', None) if plans is not None else None
    kind = withdraw_request(question) if creations is not None else None
    if kind is None:
        return None
    online = [c for c in creations.state()['creations'] if c['kind'] == 'site' and c.get('url')]
    if not online:
        return dict(reply='Your website isn’t online right now, so there’s nothing to ' + ('take down.' if kind == 'unpublish' else 'undo.')
                    + ' Say “publish it” after making one to put it online.')
    try:
        reply = await plans.propose({'requestId': request_key, 'intent': 'site-unpublish' if kind == 'unpublish' else 'site-rollback', 'input': {'id': online[0]['id']}})
    except JuneError as failure:
        return dict(reply=failure.message + ' Nothing was changed.')
    plan = reply['plan']
    effect = (f'removes the page at {online[0]["url"]} from the internet; it stays saved on this Mac' if kind == 'unpublish'
              else f'puts the earlier version back at {online[0]["url"]}, replacing the one online now')
    return dict(plan=plan, serverNow=reply['serverNow'], reply=f'I’ve prepared “{plan["steps"][0]["label"]}”. Check the card below: approving {effect}.')
