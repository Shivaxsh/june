"""Naukri jobs: find, rank against the person's resume, apply in their own Chrome, and track honestly.

June opens only naukri.com pages, in tabs she opens, and runs only the page scripts built into the
June Browser helper. Applying is an outward plan step, reviewed every time and never remembered. A job
counts as applied only when Naukri's own page says so. Recruiter questions are answered from the person's
saved answers (job_answers.py; their choice, 21 Nov 2026); a new question is asked once and remembered.
Company-site redirects, log-in walls, captchas, OTPs and tests are handed back with the page left open, and
June never reports a submission she did not see confirmed.
"""
import asyncio
from contextlib import suppress
from email import message_from_string
from email.policy import default as email_policy
import html
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlsplit

from .chat import MODEL_KEEP_ALIVE
from .errors import JuneError
from .job_answers import STOP_ANSWER, Profile, choose, key, standing_answer
from .knowledge import bounded_json
from .tool_plans import Capability

RECOMMENDED = 'https://www.naukri.com/mnjuser/recommendedjobs'
JOB_URL = re.compile(r'https://(?:www\.)?naukri\.com/job-listings-[a-z0-9-]{3,300}?-(?P<id>\d{8,16})(?=[/?#"\'\s<>]|$)', re.I)
ALLOW = 'Allow June to use Chrome for Naukri first: Systems → Email & jobs → Allow Chrome.'
STATUSES = ('found', 'applied', 'needs-you', 'not-confirmed', 'skipped', 'replied')

# Deliberately bounded vocabulary: absence of a named technology is not evidence
# that a person lacks experience. Generic job titles remain unscored.
KEYWORDS = {
    'HTML': r'html5?', 'CSS': r'css3?', 'JavaScript': r'javascript|(?<!\.)js',
    'TypeScript': r'typescript', 'React': r'react(?:\.js)?(?!\s+native)',
    'React Native': r'react\s+native', 'Node.js': r'node(?:\.?js|\s+js)?',
    'Vue': r'vue(?:\.js)?', 'Angular': r'angular', 'Python': r'python',
    'Java': r'java', 'Spring': r'spring(?:\s+boot)?', 'C++': r'c\+\+',
    'C#': r'c#', '.NET': r'\.net|dotnet|asp\.net', 'PHP': r'php', 'Ruby': r'ruby',
    'SQL': r'sql', 'PostgreSQL': r'postgres(?:ql)?', 'Docker': r'docker',
    'Kubernetes': r'kubernetes|k8s', 'AWS': r'aws', 'Azure': r'azure',
    'Figma': r'figma', 'Git': r'git', 'Linux': r'linux', 'Bash': r'bash',
    'Cloud deployment': r'cloud\s+deployment',
    'Automation Anywhere': r'automation\s+anywhere',
}


def title_keywords(text):
    found={name for name,pattern in KEYWORDS.items() if re.search(r'(?<!\w)(?:'+pattern+r')(?!\w)',text,re.I)}
    if 'Spring' in found and 'Java' not in found and not re.search(r'\bspring\s+boot\b',text,re.I):found.remove('Spring')
    return found


def resume_keywords(text):
    # Drop negative clauses before matching: "no Java or React Native experience"
    # must never count as positive evidence. Keep explicit positive contrast.
    positive=[]
    for clause in re.split(r'(?<=[.!?])\s+|\n|;|\bbut\b|\bhowever\b',text,flags=re.I):
        positive.append(re.split(r"\b(?:no|without|lack(?:s|ing)?|not|never)\b|don['’]t|doesn['’]t",clause,maxsplit=1,flags=re.I)[0])
    return title_keywords('\n'.join(positive))


def job_id(url):
    match = JOB_URL.match(url or '')
    return match['id'] if match else None


def clean(value, limit):
    return re.sub(r'\s+', ' ', html.unescape(str(value or ''))).strip()[:limit]


def jobs_from_email(source):
    """Job links in a Naukri alert email (raw MIME), with the link text as the title."""
    try:
        message = message_from_string(source, policy=email_policy)
        parts = [p.get_content() for p in message.walk() if p.get_content_type() in ('text/html', 'text/plain')]
    except Exception:
        parts = [source]
    found, seen = [], set()
    for part in parts:
        if not isinstance(part, str):
            continue
        for anchor in re.finditer(r'<a\b[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<text>.*?)</a>', part, re.I | re.S):
            href = html.unescape(anchor['href'])
            match = JOB_URL.search(href)
            if not match or match['id'] in seen:
                continue
            title = clean(re.sub(r'<[^>]+>', ' ', anchor['text']), 200)
            if len(title) < 3:
                continue
            seen.add(match['id'])
            found.append(dict(url=match.group(0).split('?')[0], title=title, company='', location='', experience='', salary=''))
        for match in JOB_URL.finditer(part):
            if match['id'] not in seen:
                seen.add(match['id'])
                slug = match.group(0).split('job-listings-', 1)[1].rsplit('-', 1)[0]
                found.append(dict(url=match.group(0), title=clean(slug.replace('-', ' ').title(), 200), company='', location='', experience='', salary=''))
    return found[:40]


class BrowserNative:
    def __init__(self, binary):
        self.binary = Path(binary)
        self.problem = None

    def ready(self):
        return self.binary.is_file()

    async def call(self, value, timeout=30):
        if not self.binary.is_file():
            self.problem = 'unavailable'
            raise JuneError('browser-unavailable', 'The June Browser helper is not installed. Run npm run mail:setup.', 503)
        process = None
        try:
            process = await asyncio.create_subprocess_exec(str(self.binary), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            output, _ = await asyncio.wait_for(process.communicate(json.dumps(value).encode()), timeout)
            reply = json.loads(output)
            if not isinstance(reply, dict): raise ValueError()
        except (OSError, TimeoutError, ValueError, UnicodeError):
            self.problem = 'unavailable'
            raise JuneError('browser-unavailable', 'Chrome did not answer in time. Check Chrome, then try again.', 503) from None
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                with suppress(ProcessLookupError): await process.wait()
        if reply.get('ok') is not True:
            code = reply.get('code')
            self.problem = code if code in ('automation-permission', 'javascript-off') else 'unavailable' if code=='browser-unavailable' else None
            if code == 'automation-permission':
                raise JuneError(code, 'Allow June Browser to control Google Chrome in System Settings → Privacy & Security → Automation, then try again.', 403)
            if code == 'javascript-off':
                raise JuneError(code, 'In Chrome, open the View menu → Developer → tick “Allow JavaScript from Apple Events”, then try again.', 409)
            if code == 'tab-missing':
                raise JuneError(code, 'The Naukri tab June opened was closed.', 409)
            raise JuneError('browser-unavailable', 'Chrome could not do that. Check Chrome, then try again.', 503)
        self.problem = None
        return reply


class Jobs:
    def __init__(self, data_home, browser=None, clock=time.time):
        self.directory = Path(data_home) / 'tools'
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'jobs.sqlite3'
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600); os.close(fd)
        self.browser = browser
        self.clock = clock
        # Asking the person live (their choice, 21 Nov 2026): June says the question out loud, notifies, shows it in chat,
        # and holds the application open this long for the answer. `announce` and `judge` are wired by the app.
        self.ask_wait, self.ask_poll, self.reminders = 600.0, 2.0, (180.0, 420.0)
        self.announce, self.judge, self._announcing = None, None, set()
        self.receipt_pause, self.receipt_budget = 8.0, 20.0
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS settings(id TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS answered(job TEXT NOT NULL,question TEXT NOT NULL,answer TEXT NOT NULL,at REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,url TEXT NOT NULL,title TEXT NOT NULL,company TEXT NOT NULL,location TEXT NOT NULL,'
                       'experience TEXT NOT NULL,salary TEXT NOT NULL,source TEXT NOT NULL,found REAL NOT NULL,score INTEGER,reason TEXT NOT NULL DEFAULT \'\','
                       'status TEXT NOT NULL,at REAL NOT NULL,detail TEXT NOT NULL DEFAULT \'\')')
            method=db.execute("SELECT value FROM settings WHERE id='ranking-method'").fetchone()
            if method is None or method[0]!='title-keywords-v1':
                db.execute("UPDATE jobs SET score=NULL,reason=''")
                db.execute("INSERT OR REPLACE INTO settings VALUES('ranking-method','title-keywords-v1')")
        # This single-owner service is new; old waiting cards have no live task.
        # Retain the question and all taught answers, but clear the countdown.
        self.profile.recover_waiting()

    def db(self):
        db = sqlite3.connect(self.path, timeout=3); db.row_factory = sqlite3.Row; return db

    def setting(self, key, default=''):
        with self.db() as db:
            row = db.execute('SELECT value FROM settings WHERE id=?', (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        with self.db() as db:
            if key in ('enabled', 'stopped'):
                old = db.execute('SELECT value FROM settings WHERE id=?', (key,)).fetchone()
                if old is None or old[0] != str(value):
                    db.execute("INSERT OR REPLACE INTO settings VALUES('_control-generation',CAST(COALESCE((SELECT value FROM settings WHERE id='_control-generation'),'0') AS INTEGER)+1)")
            db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (key, str(value)))

    def control_generation(self):
        return int(self.setting('_control-generation', '0'))

    def enabled(self):
        return self.setting('enabled') == '1'

    async def enable(self, allowed):
        if type(allowed) is not bool:
            raise JuneError('invalid-jobs', 'Send allowed as true or false.', 400)
        if allowed:
            generation = self.control_generation()
            await self.browser.call({'operation': 'status'})  # macOS asks here; success means consent
            if self.control_generation() != generation:
                raise JuneError('jobs-consent', 'The job setting changed while Chrome was being enabled. Try again.', 409)
        self.set_setting('enabled', '1' if allowed else '0')
        return self.state()

    def daily_limit(self):
        try:
            return max(1, min(int(self.setting('daily', '10')), 25))
        except ValueError:
            return 10

    def applied_today(self):
        start = time.mktime(time.localtime(self.clock())[:3] + (0, 0, 0, 0, 0, -1))
        with self.db() as db:
            return db.execute("SELECT count(*) FROM jobs WHERE status='applied' AND at>=?", (start,)).fetchone()[0]

    def upsert(self, rows, source):
        added = 0
        with self.db() as db:
            for row in rows:
                jid = job_id(row.get('url', ''))
                if not jid:
                    continue
                exists = db.execute('SELECT 1 FROM jobs WHERE id=?', (jid,)).fetchone()
                values = [clean(row.get(k), n) for k, n in (('title', 200), ('company', 200), ('location', 120), ('experience', 60), ('salary', 60))]
                if exists:
                    old=db.execute('SELECT title FROM jobs WHERE id=?',(jid,)).fetchone()
                    if values[0] and values[0]!=old['title']:
                        db.execute("UPDATE jobs SET score=NULL,reason='' WHERE id=?",(jid,))
                    db.execute('UPDATE jobs SET title=CASE WHEN ?<>\'\' THEN ? ELSE title END, company=CASE WHEN ?<>\'\' THEN ? ELSE company END WHERE id=?',
                               (values[0], values[0], values[1], values[1], jid))
                else:
                    db.execute('INSERT INTO jobs(id,url,title,company,location,experience,salary,source,found,status,at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                               (jid, row['url'].split('?')[0], *values, source, self.clock(), 'found', self.clock()))
                    added += 1
        return added

    def list(self, statuses=None, limit=40):
        if statuses is not None and not statuses:return []
        where=' WHERE status IN ('+','.join('?' for _ in statuses)+')' if statuses else ''
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM jobs'+where+' ORDER BY CASE WHEN score IS NULL THEN 1 ELSE 0 END, score DESC, found DESC LIMIT ?',[*(statuses or []),max(0,min(limit,200))])]

    def get(self, jid):
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone() if isinstance(jid, str) else None
        if not row:
            raise JuneError('job-missing', 'That job is not in June’s list. Ask her to find jobs first.', 404)
        return dict(row)

    def mark(self, jid, status, detail=''):
        with self.db() as db:
            db.execute('UPDATE jobs SET status=?,at=?,detail=? WHERE id=?', (status, self.clock(), detail[:300], jid))

    def state(self):
        return dict(version=1, serverNow=round(self.clock() * 1000), enabled=self.enabled(), installed=bool(self.browser and self.browser.ready()),
                    problem=getattr(self.browser, 'problem', None),
                    dailyLimit=self.daily_limit(), appliedToday=self.applied_today(), stopped=self.setting('stopped') == '1',
                    questions=self.profile.pending(), answers=self.profile.saved(), standing=bool(self.profile.standing()),
                    jobs=[dict(id=r['id'], title=r['title'], company=r['company'], location=r['location'], experience=r['experience'], salary=r['salary'],
                               score=r['score'], reason=r['reason'], status=r['status'], detail=r['detail'], at=round(r['at'] * 1000)) for r in self.list(limit=40)])

    # --- Finding jobs ---------------------------------------------------------------------------------
    async def _wait_page(self, tab, key, ready, seconds=25, pause=1.0):
        page = {}
        for _ in range(int(seconds / pause) if pause else 1):
            page = (await self.browser.call({'operation': key, 'tab': tab}))['page']
            if ready(page):
                return page
            await asyncio.sleep(pause)
        return page

    @property
    def profile(self):
        # The person's standing answers (private file) and the answers they taught June (this database).
        return Profile(self.directory / 'job-profile.json', self.db)

    def answered(self, jid):
        with self.db() as db:
            return [dict(question=r[0], answer=r[1]) for r in db.execute('SELECT question,answer FROM answered WHERE job=? ORDER BY at', (jid,))]

    def _say(self, question, options, name, reminder=False):
        """Announce a question (voice, notification) without delaying the application; failures never matter here."""
        if self.announce is None:
            return
        async def run():
            with suppress(Exception):
                await self.announce(question, options, name, reminder)
        task = asyncio.ensure_future(run())
        self._announcing.add(task); task.add_done_callback(self._announcing.discard)
        return task

    async def _similar_answer(self, question, kind, options):
        """A saved answer to a question that asks the same thing in other words; it is then saved for this wording too."""
        profile = self.profile
        for score, other, answer, sure in profile.similar(question, kind, options):
            same = sure
            if not same and self.judge is not None:
                with suppress(Exception):
                    same = await self.judge(question, other) is True
            if same:
                with suppress(ValueError):
                    profile.teach(question, answer, self.clock())
                return answer
        return None

    async def _ask_live(self, chat, jid, name, question, kind, options, blocked):
        """Ask the person and hold the application open for their answer. Returns (outcome, answer): answered, moved
        (the page went on to something else: re-read), changed (wrong page), stopped, or timeout."""
        profile = self.profile
        until = self.clock() + self.ask_wait
        profile.ask(question, options, jid, self.clock(), title=name, waiting=until)
        announcements = [self._say(question, options, name)]
        started, reminded = time.monotonic(), set()
        try:
            while True:
                if blocked():
                    return 'stopped', None
                answer = profile.learned(question)
                if answer is not None:
                    if kind in ('radio', 'checkbox', 'chips') and choose(answer, options, question=question) is None:
                        # Different choices do not revoke the person's saved fact.
                        profile.ask(question, options, jid, self.clock(), title=name, waiting=until)
                    else:
                        return 'answered', answer
                page = (await chat())['page']
                if not page.get('ok'):
                    return 'changed', None
                if not page.get('open') or page.get('question') != question:
                    return 'moved', None
                elapsed = time.monotonic() - started
                for at in self.reminders:
                    if elapsed >= at and at not in reminded and at < self.ask_wait:
                        reminded.add(at); announcements.append(self._say(question, options, name, reminder=True))
                if elapsed >= self.ask_wait:
                    return 'timeout', None
                await asyncio.sleep(self.ask_poll)
        finally:
            profile.stop_waiting(question)  # an unanswered question stays listed for later, no longer "waiting"
            pending = [task for task in announcements if task is not None and not task.done()]
            for task in pending: task.cancel()
            if pending: await asyncio.gather(*pending, return_exceptions=True)

    async def answer_questions(self, tab, jid, name, pause=1.0, limit=20, generation=None):
        """Answer Naukri's recruiter questions for this job from the person's saved answers, one by one, until Naukri
        confirms the application. A question with no saved answer stops it: June records the question for the person
        to answer once (then remembers it), and leaves the page open. Returns (status, detail, message)."""
        profile, standing = self.profile, self.profile.standing()
        chat = lambda mode='read', value='': self.browser.call({'operation': 'chat', 'tab': tab, 'jobId': jid, 'mode': mode, 'value': value})
        count, previous, waiting, attempts = 0, None, 0, 0
        generation = self.control_generation() if generation is None else generation
        def blocked(include_limit=True):
            return (self.control_generation() != generation or not self.enabled() or self.setting('stopped') == '1'
                    or (include_limit and self.applied_today() >= self.daily_limit()) or self.get(jid)['status'] == 'skipped')
        stopped = ('needs-you', 'Applying was stopped, disabled, or reached its daily limit.',
                   f'I stopped answering {name}’s questions because applying was stopped, disabled, or reached its daily limit. Check the open tab; no further answers were entered.')
        while attempts < limit:
            if blocked(False): return stopped
            page = (await chat())['page']
            if blocked(False): return stopped
            if not page.get('ok'):
                self.navigation_diagnostic(page.get('url'), jid, 'recruiter-read')
                return await self.reconciled_answer(jid, name, generation)
            if not page.get('open'):
                facts = await self._wait_page(tab, 'facts', lambda p: p.get('applied') or p.get('confirmation') or job_id(str(p.get('url', ''))) != jid, seconds=10, pause=pause)
                if blocked(False): return stopped
                if job_id(str(facts.get('url', '')).split('?')[0]) != jid:
                    return await self.reconciled_answer(jid, name, generation)
                if facts.get('applied') or facts.get('confirmation'):
                    return 'applied', f'Naukri confirmed the application after June answered {count} recruiter question{"" if count == 1 else "s"}.', \
                        f'Applied to {name}. I answered {count} recruiter question{"" if count == 1 else "s"} from your saved answers, and Naukri confirmed it.'
                return 'not-confirmed', 'The questions closed without a Naukri confirmation.', f'The questions for {name} closed, but Naukri showed no confirmation, so I’m not counting it as applied. Check the open tab.'
            question, kind, options = str(page.get('question') or ''), page.get('kind'), [str(o)[:120] for o in (page.get('options') or [])][:12]
            from .job_answers import STOP
            # Naukri shows its greeting and input before the actual question
            # arrives. Never learn or answer that loading message, even if a
            # legacy saved answer exists. Unknown controls can also settle late.
            greeting = (re.match(r'^(?:hi|hello|dear)\b', question, re.I) and '?' not in question
                        and re.search(r'thank you for (?:showing )?(?:your )?interest|(?:kindly|please) answer\b.*\bquestions\b', question, re.I))
            if not question or greeting or (kind == 'unknown' and not STOP.search(question)):
                waiting += 1
                if waiting >= 12:
                    return 'needs-you', 'The recruiter question was not ready.', f'{name}’s question or answer control did not finish loading. I entered nothing further; check the open tab.'
                await asyncio.sleep(pause)
                continue
            waiting = 0
            attempts += 1
            if question == previous:
                saved = page.get('lastSave') or {}
                if saved.get('question') == question and saved.get('saved') is False:
                    return 'needs-you', f'The answer could not be saved: {question[:150]}', f'I entered an answer for {name}, but could not confirm its Save. I stopped without re-entering it; check the open tab.'
                return 'needs-you', f'Naukri did not accept the answer to: {question[:150]}', f'Naukri didn’t accept my answer to “{question[:150]}” for {name}. The page is open in Chrome for you.'
            if STOP.search(question):
                answer = STOP_ANSWER
            elif len(question) > 300:
                return 'needs-you', 'The recruiter question is too long to match safely.', f'{name} asks a long question I need you to check in the open tab.'
            else:
                answer = profile.learned(question)
            if answer is None:
                answer = standing_answer(question, kind, standing)
            if answer is STOP_ANSWER:
                return 'needs-you', f'Naukri asks something only you can do: {question[:150]}', f'{name} asks “{question[:150]}”. That’s one you do yourself (I never handle OTPs, captchas, tests, sign-ups or ID numbers). The page is open in Chrome.'
            fits = lambda a: a is not None and (kind not in ('radio', 'checkbox', 'chips') or choose(a, options, question=question) is not None)
            if not fits(answer) and kind in ('radio', 'checkbox', 'chips', 'text', 'number'):
                answer = await self._similar_answer(question, kind, options)
            if not fits(answer) and kind in ('radio', 'checkbox', 'chips', 'text', 'number'):
                # Never stuck on a new question: ask the person now and wait for them (their choice, 21 Nov 2026).
                outcome, answer = await self._ask_live(chat, jid, name, question, kind, options, blocked)
                if outcome == 'stopped': return stopped
                if outcome == 'changed':
                    return 'not-confirmed', 'The page changed while waiting for your answer.', f'The page changed while I was waiting for your answer for {name}, so I’m not counting it as applied. Check the open tab.'
                if outcome == 'moved':
                    await asyncio.sleep(pause); continue
                if outcome == 'timeout':
                    minutes = max(1, round(self.ask_wait / 60))
                    return 'needs-you', f'Waited for your answer: {question[:150]}', (f'I waited {minutes} minute{"" if minutes == 1 else "s"} for your answer to “{question[:150]}” for {name}. '
                                                                                         'It’s saved in Systems → Email & jobs: answer it there and approve the job again, and I’ll use it.')
            if kind in ('radio', 'checkbox', 'chips'):
                pick = choose(answer, options, question=question) if answer is not None else None
                if pick is None:
                    profile.ask(question, options, jid, self.clock())
                    return 'needs-you', f'Needs your answer: {question[:150]}', f'{name} asks “{question[:150]}”{" (" + ", ".join(options[:6]) + ")" if options else ""}. I don’t have your answer yet. Add it in Systems → Email & jobs and I’ll use it from now on; the page is open in Chrome.'
                mode, value = 'option', pick
            elif kind in ('text', 'number'):
                if answer is None:
                    profile.ask(question, [], jid, self.clock())
                    return 'needs-you', f'Needs your answer: {question[:150]}', f'{name} asks “{question[:150]}”. I don’t have your answer yet. Add it in Systems → Email & jobs and I’ll use it from now on; the page is open in Chrome.'
                mode, value = 'text', answer
            else:
                return 'needs-you', f'A question June can’t fill in yet: {question[:150]}', f'{name} asks “{question[:150]}” in a form I can’t fill in yet. The page is open in Chrome for you.'
            if blocked(): return stopped
            done = (await self.browser.call({'operation':'chat', 'tab':tab, 'jobId':jid, 'mode':mode,
                                            'value':value, 'expectedQuestion':question}))['page']
            if not done.get('answered'):
                if done.get('reason') == 'question-changed':
                    # Native guarantees it entered nothing. Re-read and select a
                    # fresh answer, bounded by this loop's existing attempt limit.
                    await asyncio.sleep(pause)
                    continue
                return 'needs-you', f'Could not enter the answer to: {question[:150]}', f'I couldn’t enter my answer to “{question[:150]}” for {name}. The page is open in Chrome for you.'
            with self.db() as db:
                db.execute('INSERT INTO answered VALUES(?,?,?,?)', (jid, question, value, self.clock()))
            count, previous = count + 1, question
            for _ in range(int(8 / pause) if pause else 1):  # wait for the next question or the end
                await asyncio.sleep(pause)
                now = (await chat())['page']
                if not now.get('ok') or not now.get('open') or now.get('question') != question:
                    break
        return 'needs-you', 'Too many questions to finish automatically.', f'{name} kept asking questions, so I stopped. The page is open in Chrome for you.'

    def receipt_allowed(self, jid, generation):
        return (self.control_generation() == generation and self.enabled()
                and self.setting('stopped') != '1' and self.get(jid)['status'] != 'skipped')

    def navigation_diagnostic(self, url, jid, stage):
        # Never retain arbitrary path segments (which may contain names/tokens).
        try:
            parsed = urlsplit(str(url))
            host = parsed.hostname if parsed.hostname in ('naukri.com', 'www.naukri.com') else 'other'
            segment = parsed.path.strip('/').split('/')[0]
            shape = '/job-listings-…-N' if parsed.path.startswith('/job-listings-') else '/' + segment + '/…' if segment in ('mnjuser', 'myapply', 'recommendedjobs') else '/…'
            record = dict(scheme=parsed.scheme if parsed.scheme in ('http', 'https') else 'other', host=host,
                          pathShape=shape, sameJob=job_id(str(url)) == jid, stage=stage, at=self.clock())
            directory = self.directory / 'diagnostics'
            directory.mkdir(mode=0o700, exist_ok=True)
            path = directory / 'job-navigation.jsonl'
            fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'w') as out:
                if path.stat().st_size > 32768: out.seek(0); out.truncate()
                out.write(json.dumps(record) + '\n')
        except (OSError, ValueError):
            pass  # Diagnostics must never decide an application's outcome.

    async def reconcile(self, jid, generation, *, pause=None):
        """Bounded receipt reads only. Never click Apply, answer, or adopt the action tab."""
        tab = None
        deadline = time.monotonic() + self.receipt_budget
        pause = self.receipt_pause if pause is None else pause
        async def call(value):
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise TimeoutError()
            return await asyncio.wait_for(self.browser.call(value, timeout=remaining), remaining)
        try:
            if not self.receipt_allowed(jid, generation): return False
            url = self.get(jid)['url']
            if job_id(url) != jid: return False
            tab = (await call({'operation': 'open', 'url': url}))['tab']
            for attempt in range(3):
                if not self.receipt_allowed(jid, generation): return False
                page = (await call({'operation': 'facts', 'tab': tab}))['page']
                if not self.receipt_allowed(jid, generation): return False
                actual = job_id(str(page.get('url', '')))
                if actual is not None and actual != jid and page.get('ready') == 'complete': return False
                if any(page.get(flag) for flag in ('login', 'loggedOut', 'captcha', 'external', 'expired')): return False
                if actual == jid and page.get('ready') == 'complete' and page.get('applied') is True: return True
                if attempt < 2 and pause:
                    await asyncio.sleep(min(pause, max(0, deadline - time.monotonic())))
            return False
        except (JuneError, TimeoutError):
            return False
        finally:
            if tab is not None:
                with suppress(JuneError, TimeoutError):
                    await asyncio.wait_for(self.browser.call({'operation': 'close', 'tab': tab}, timeout=2), 2)

    async def reconciled_answer(self, jid, name, generation):
        if await self.reconcile(jid, generation):
            return 'applied', 'Naukri shows this job as applied on the reviewed job page.', f'Naukri shows {name} as applied on the reviewed job page.'
        return 'not-confirmed', 'The page changed; no receipt confirmed for this job.', f'The page changed for {name}. I could not confirm this job, so I am not counting it as applied. Check the open tab.'

    async def recheck(self, jid, pause=1.0):
        """Read-only: after the person finished an application by hand (recruiter questions, log-in, captcha), look at the
        job page again and record it as applied only if Naukri itself shows it applied. Nothing is clicked or typed."""
        if not self.enabled():
            raise JuneError('jobs-consent', ALLOW, 403)
        if not isinstance(jid, str) or not re.fullmatch(r'\d{8,16}', jid):
            raise JuneError('invalid-jobs', 'Choose a job from June’s list.', 400)
        job = self.get(jid)
        if job['status'] not in ('needs-you', 'not-confirmed'):
            raise JuneError('job-not-waiting', 'Only jobs that were waiting on you can be checked again.', 409)
        generation = self.control_generation()
        if not self.receipt_allowed(jid, generation):
            return dict(message='Applying was stopped or disabled. Nothing changed.')
        tab = (await self.browser.call({'operation': 'open', 'url': job['url']}))['tab']
        try:
            if not self.receipt_allowed(jid, generation):
                return dict(message='Applying was stopped or disabled. Nothing changed.')
            page = await self._wait_page(tab, 'facts', lambda p: p.get('ready') == 'complete' and (p.get('title') or p.get('applied') or p.get('login') or p.get('expired')), pause=pause)
        finally:
            with suppress(JuneError): await self.browser.call({'operation': 'close', 'tab': tab})
        name = f'{job["title"]}{" at " + job["company"] if job["company"] else ""}'
        if not self.receipt_allowed(jid, generation):
            return dict(message='Applying was stopped or disabled. Nothing changed.')
        if page.get('expired') is True:
            self.mark(jid, 'skipped', 'Naukri says this job has expired.')
            return dict(message=f'Naukri says {name} has expired.')
        if job_id(str(page.get('url', '')).split('?')[0]) != jid:
            return dict(message=f'Naukri opened a different page for {name}, so I couldn’t check it. Nothing changed.')
        if page.get('applied') is True and not any(page.get(k) for k in ('login', 'captcha', 'external', 'loggedOut')):
            self.mark(jid, 'applied', 'Naukri shows this job as applied on the reviewed job page.')
            return dict(message=f'Naukri shows {name} as applied. I’ve recorded it.')
        return dict(message=f'Naukri doesn’t show {name} as applied yet. If you haven’t finished it, the job page on Naukri still needs you.')

    async def from_naukri(self, pause=1.0):
        """Your Naukri recommended jobs, read from your logged-in Chrome. Nothing is clicked."""
        if not self.enabled():
            raise JuneError('jobs-consent', ALLOW, 403)
        tab = (await self.browser.call({'operation': 'open', 'url': RECOMMENDED}))['tab']
        try:
            page = await self._wait_page(tab, 'list', lambda p: p.get('ready') == 'complete' and (p.get('jobs') or p.get('loggedOut')), pause=pause)
        finally:
            with suppress(JuneError): await self.browser.call({'operation': 'close', 'tab': tab})
        if page.get('loggedOut') or 'login' in str(page.get('url', '')).lower():
            raise JuneError('naukri-login', 'Log in to Naukri in Chrome first, then ask again.', 409)
        return self.upsert(page.get('jobs') or [], 'naukri')

    async def from_mail(self, mail):
        """Job links in your recent Naukri alert emails."""
        if mail is None or not mail.enabled():
            return 0
        added = 0
        for row in (await mail.search(sender='naukri', limit=5))[:5]:
            with suppress(JuneError):
                added += self.upsert(jobs_from_email((await mail.read(row['id'], source=True))['text']), 'email')
        return added

    # --- Ranking ----------------------------------------------------------------------------------------
    async def rank(self, client, settings, resume, limit=200):
        """Title keyword coverage only; no model-generated suitability claims."""
        evidence=resume[:8000]
        fingerprint=hashlib.sha256(evidence.encode()).hexdigest()
        with self.db() as db:
            previous=db.execute("SELECT value FROM settings WHERE id='ranking-resume'").fetchone()
            if previous is None or previous[0]!=fingerprint:
                db.execute("UPDATE jobs SET score=NULL,reason='' WHERE status='found'")
                db.execute("INSERT OR REPLACE INTO settings VALUES('ranking-resume',?)",(fingerprint,))
            rows=[dict(r) for r in db.execute("SELECT * FROM jobs WHERE status='found' ORDER BY CASE WHEN reason='' THEN 0 ELSE 1 END,found DESC LIMIT ?",(max(0,min(limit,200)),))]
        if not resume.strip():
            with self.db() as db:
                db.execute("UPDATE jobs SET score=NULL,reason='Add a resume to compare title keywords.' WHERE status='found'")
            return 0
        if not rows:
            return 0
        available = resume_keywords(evidence)
        with self.db() as db:
            for row in rows:
                required = title_keywords(row['title'])
                if not required:
                    score, reason = None, 'No specific technology named; read the full job description.'
                else:
                    matched = required & available
                    score = round(100 * len(matched) / len(required))
                    reason = ('Title keywords in resume: ' + ', '.join(sorted(matched)) if matched else 'No title keywords found in resume.')
                    missing = required - available
                    if matched and missing: reason += '; not found: ' + ', '.join(sorted(missing))
                db.execute('UPDATE jobs SET score=?,reason=? WHERE id=?',(score,reason[:140],row['id']))
        return len(rows)

    async def check_replies(self, mail):
        """Mark applied jobs whose company wrote back. June never guesses the outcome itself."""
        if mail is None or not mail.enabled():
            return 0
        marked = 0
        for row in self.list(['applied'], 20):
            words = [w for w in re.findall(r'[A-Za-z0-9]{3,}', row['company']) if w.lower() not in ('pvt', 'ltd', 'private', 'limited', 'india', 'technologies', 'solutions')]
            if not words:
                continue
            with suppress(JuneError):
                found = await mail.search(sender=words[0], limit=3)
                if any(r['date'] and r['date'] > time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(row['at'])) for r in found):
                    self.mark(row['id'], 'replied', 'Email from ' + (found[0]['name'] or found[0]['address']) + ': ' + found[0]['subject'])
                    marked += 1
        return marked


def resume_text(knowledge):
    """The resume in June's library: a ready document whose name says resume or CV."""
    if knowledge is None:
        return ''
    with suppress(Exception):
        for doc in knowledge.db.list()['documents']:
            if doc.get('status') == 'ready' and re.search(r'resume|résumé|\bcv\b|curriculum', doc.get('name', ''), re.I):
                return '\n'.join(p['text'] for p in knowledge.db.get(doc['id'], preview=True).get('passages', []))[:8000]
    return ''


def register(plans, jobs, *, pause=1.0, gap=25.0):
    """Add job-apply: one card for up to five jobs, every job a separate outward step."""
    last = {'at': 0.0}
    application_lock = jobs.application_lock = asyncio.Lock()

    async def apply_one(payload, generation):
        jid = payload['id']
        if jobs.control_generation() != generation:
            return dict(verified=False, failed=True, message='Applying was stopped or disabled while this card waited. Nothing was submitted.')
        if not jobs.enabled():
            return dict(verified=False, failed=True, message=ALLOW + ' Nothing was submitted.')
        if jobs.setting('stopped') == '1':
            return dict(verified=False, failed=True, message='Applying is stopped in Systems → Email & jobs. Nothing was submitted.')
        if jobs.applied_today() >= jobs.daily_limit():
            return dict(verified=False, failed=True, message=f'You reached today’s limit of {jobs.daily_limit()} applications. Nothing more was submitted.')
        try:
            job = jobs.get(jid)
        except JuneError as failure:
            return dict(verified=False, failed=True, message=failure.message)
        if job['url'] != payload['url']:
            return dict(verified=False, failed=True, message='That job changed after you reviewed it, so nothing was submitted.')
        if job['status'] == 'applied':
            return dict(verified=True, message=f'{job["title"]} was already confirmed as applied. Nothing new was submitted.')
        if job['status'] == 'skipped':
            return dict(verified=False, failed=True, message='You skipped that job. Nothing was submitted.')
        wait = gap - (jobs.clock() - last['at'])
        if wait > 0 and pause:
            await asyncio.sleep(wait)  # a natural pause between applications
        if jobs.control_generation() != generation or not jobs.enabled() or jobs.setting('stopped') == '1':
            return dict(verified=False, failed=True, message='Applying was stopped or disabled while this card waited. Nothing was submitted.')
        name = f'{job["title"]}{" at " + job["company"] if job["company"] else ""}'
        tab = (await jobs.browser.call({'operation': 'open', 'url': job['url']}))['tab']
        keep_open = True
        try:
            page = await jobs._wait_page(tab, 'facts', lambda p: p.get('ready') == 'complete' and (p.get('title') or p.get('applied') or p.get('login') or p.get('expired')), pause=pause)
            if page.get('expired') is True:
                # Naukri's own "job you are looking for is expired" page: the job is closed, so it leaves the open list.
                jobs.mark(jid, 'skipped', 'Naukri says this job has expired.')
                return dict(verified=False, message=f'Naukri says {name} has expired, so I didn’t apply. I’ve taken it off your list of open jobs; the tab shows similar jobs.')
            if job_id(str(page.get('url', '')).split('?')[0]) != jid:
                jobs.mark(jid, 'needs-you', 'Naukri opened a different page.')
                return dict(verified=False, message=f'Naukri opened a different page for {name}, so I didn’t apply. The tab is open for you.')
            if page.get('applied'):
                jobs.mark(jid, 'applied', 'Naukri already showed this job as applied.'); keep_open = False
                return dict(verified=True, message=f'Naukri already shows {name} as applied. Nothing new was submitted.')
            for flag, why in (('login', 'Naukri asks you to log in first'), ('captcha', 'Naukri shows a captcha'), ('external', 'this job applies on the company’s own website')):
                if page.get(flag):
                    jobs.mark(jid, 'needs-you', why + '.')
                    return dict(verified=False, message=f'I didn’t apply to {name}: {why}. The page is open in Chrome for you.')
            if not page.get('apply'):
                jobs.mark(jid, 'needs-you', 'No Apply button was on the page.')
                return dict(verified=False, message=f'I couldn’t find Naukri’s Apply button for {name}. The page is open in Chrome for you.')
            # Consent and limits may change while Chrome loads or between jobs.
            if (jobs.control_generation() != generation or not jobs.enabled() or jobs.setting('stopped') == '1'
                    or jobs.applied_today() >= jobs.daily_limit() or jobs.get(jid)['status'] == 'skipped'):
                return dict(verified=False, failed=True, message='Applying was stopped, disabled, or reached its daily limit while the page loaded. Nothing was submitted.')
            clicked = (await jobs.browser.call({'operation': 'click-apply', 'tab': tab, 'jobId': jid}))['page']
            last['at'] = jobs.clock()
            if not clicked.get('clicked'):
                jobs.mark(jid, 'needs-you', 'The Apply button could not be pressed.')
                return dict(verified=False, message=f'The Apply button for {name} could not be pressed. Nothing was confirmed; the page is open for you.')
            after = await jobs._wait_page(tab, 'facts', lambda p: p.get('applied') or p.get('confirmation') or p.get('questions') or p.get('captcha') or p.get('external') or job_id(str(p.get('url', ''))) != jid, seconds=20, pause=pause)
            if not jobs.receipt_allowed(jid, generation):
                return dict(verified=False, message='Applying was stopped or disabled after Apply. Check Naukri before trying again.')
            if job_id(str(after.get('url', '')).split('?')[0]) != jid:
                jobs.navigation_diagnostic(after.get('url'), jid, 'after-apply')
                status, detail, message = await jobs.reconciled_answer(jid, name, generation)
                if jobs.receipt_allowed(jid, generation): jobs.mark(jid, status, detail)
                keep_open = status != 'applied'
                return dict(verified=status == 'applied', message=message)
            if after.get('applied') or after.get('confirmation'):
                jobs.mark(jid, 'applied', 'Naukri confirmed the application.'); keep_open = False
                return dict(verified=True, message=f'Applied to {name}. Naukri’s page confirmed it.')
            if after.get('questions'):
                # The person chose (21 Nov 2026): June answers recruiter questions herself from their saved answers.
                status, detail, message = await jobs.answer_questions(tab, jid, name, pause=pause, generation=generation)
                if status == 'applied' or jobs.get(jid)['status'] != 'skipped':
                    jobs.mark(jid, status, detail)
                if status == 'applied':
                    keep_open = False
                return dict(verified=status == 'applied', message=message)
            jobs.mark(jid, 'not-confirmed', 'Naukri did not show a confirmation.')
            return dict(verified=False, message=f'I pressed Apply for {name}, but Naukri did not show a confirmation, so I’m not counting it as applied. Check the open tab.')
        finally:
            if not keep_open:
                with suppress(JuneError): await jobs.browser.call({'operation': 'close', 'tab': tab})

    async def apply(payload):
        # Different approved cards can name the same job. Serialize the external
        # workflow, then re-read status/limits so they cannot submit it twice.
        generation = jobs.control_generation()
        async with application_lock:
            return await apply_one(payload, generation)

    def steps(value):
        if not isinstance(value, dict) or set(value) != {'ids'} or not isinstance(value['ids'], list) or not 1 <= len(value['ids']) <= 5 \
                or not all(isinstance(i, str) and re.fullmatch(r'\d{8,16}', i) for i in value['ids']) or len(set(value['ids'])) != len(value['ids']):
            raise JuneError('invalid-plan', 'Choose one to five jobs from June’s list.', 400)
        out = []
        for jid in value['ids']:
            job = jobs.get(jid)
            if job['status'] == 'applied':
                raise JuneError('already-applied', f'You already applied to {job["title"]}.', 409)
            name = f'{job["title"]}{" at " + job["company"] if job["company"] else ""}'
            out.append(('jobs.apply', dict(id=jid, url=job['url']),
                        f'Apply to {name} on Naukri ({job["url"]}) with your Naukri profile and resume. June opens the page in your Chrome and presses Naukri’s Apply button; '
                        'it counts as applied only if Naukri’s page confirms it. If the recruiter asks questions, June answers them from your saved answers and submits; '
                        'a question she has no answer for stops it and is asked in Systems → Email & jobs. A log-in, captcha, OTP, test or the company’s own site '
                        'stops it and leaves the page open for you. Contacts naukri.com.', 'Apply: ' + name[:60]))
        return out
    steps.accepts_input = True
    # Outward: reviewed every time, never remembered.
    # Long enough for up to five jobs, each of which may wait up to ask_wait for the person's answer to a new question.
    plans.capabilities['jobs.apply'] = Capability('jobs.apply', 'Apply to a Naukri job in your Chrome', 'naukri', 'outward', False, apply,
                                                  timeout=max(150, int(5 * (jobs.ask_wait + 180))))
    plans.intents['job-apply'] = steps
    plans.naukri = jobs


# --- Chat ---------------------------------------------------------------------------------------------
_LEAD = (r"\s*(?:(?:ok(?:ay)?|so|well|now|and|oh|um|uh|alright|hey|hi)[,.!\s]+)*(?:june[,!:\s]+)?(?:please\s+)?(?:(?:can|could|would)\s+you\s+(?:please\s+)?|i\s+(?:want|need)\s+(?:you\s+)?to\s+)?(?:go\s+ahead\s+and\s+|just\s+)?")
_TAIL = r"(?:\s+(?:please|for\s+me|now|right\s+now|today))*[\s.!?]*"
_NUM = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'a': 1}
FIND = re.compile(_LEAD + r"(?:(?:find|search\s+for|look\s+for|get|show|check|any|fetch|pull|refresh)\s+(?:me\s+)?(?:some\s+|new\s+|the\s+|my\s+|good\s+|matching\s+|recommended\s+)*"
                  r"(?:jobs?|openings?|naukri\s+(?:jobs?|recommendations?)|job\s+(?:recommendations?|matches|alerts?)|naukri)(?:\s+(?:on|from)\s+naukri)?(?:\s+for\s+me)?"
                  r"|check\s+naukri|any\s+new\s+jobs(?:\s+on\s+naukri)?" + r")" + _TAIL, re.I)
APPLY = re.compile(_LEAD + r"apply\s+(?:to|for)\s+(?:the\s+)?(?:(?:top|first|best)\s+(?P<count>\d|one|two|three|four|five)(?:\s+(?:jobs?|ones?))?|(?P<single>top|first|best)\s+(?:one|job)"
                   r"|(?:the\s+)?(?:job\s+at\s+)?(?P<company>[A-Za-z0-9][\w&.' -]{1,60}?)(?:\s+(?:one|job|role|opening))?)(?:\s+on\s+naukri)?" + _TAIL, re.I)
_ORD = {'first': 1, '1st': 1, 'second': 2, '2nd': 2, 'third': 3, '3rd': 3, 'fourth': 4, '4th': 4, 'fifth': 5, '5th': 5, 'last': -1}
_POS = r"(?:first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|last|[1-5])"
# "apply the second job", "apply to job 2", "apply to number 3", "apply to jobs 1 and 3", "apply to the last one", "apply to all of them":
# positions in the list June showed last, in the same order.
PICK = re.compile(_LEAD + r"apply\s+(?:to\s+|for\s+)?(?:(?P<all>all(?:\s+of\s+them|\s+(?:the\s+|these\s+|those\s+)?(?:jobs|ones))?|(?:both|all)\s+of\s+them|them\s+all)"
                  r"|(?:the\s+)?(?:jobs?\s+|numbers?\s+|no\.?\s*|#\s*)?(?P<picks>" + _POS + r"(?:\s*(?:,|and|&|or)\s*(?:the\s+)?(?:#\s*)?" + _POS + r")*)(?:\s+(?:jobs?|ones?|roles?|openings?))?)"
                  r"(?:\s+(?:from|in|on)\s+(?:the\s+|that\s+|this\s+)?(?:list|naukri))?" + _TAIL, re.I)


def positions(text):
    """The list positions a request names ("the second", "jobs 1 and 3", "the last one"), in order, or []."""
    found = PICK.fullmatch(text or '')
    if not found or not found['picks']:
        return []
    out = []
    for word in re.findall(_POS, found['picks'], re.I):
        n = _ORD.get(word.lower()) if not word.isdigit() else int(word)
        if n not in out:
            out.append(n)
    return out


APPLIED = re.compile(_LEAD + r"(?:(?:what|which)\s+jobs?\s+(?:did|have)\s+i\s+appl(?:y|ied)\s+(?:to|for)(?:\s+(?:this\s+week|today|so\s+far))?|show\s+(?:me\s+)?my\s+(?:job\s+)?applications|"
                     r"(?:any|did\s+i\s+get\s+any)\s+(?:replies|responses|calls)\s+from\s+(?:recruiters|companies|naukri)|how\s+are\s+my\s+(?:job\s+)?applications\s+going)" + _TAIL, re.I)


def jobs_request(text):
    if not isinstance(text, str) or len(text) > 200 or re.search(r"\b(?:do not|don['’]?t|never)\b", text, re.I) or re.match(r"\s*(?:how|why|what\s+is)\b", text, re.I):
        return None
    if APPLIED.fullmatch(text):
        return ('applied', {})
    if FIND.fullmatch(text):
        return ('find', {})
    if re.fullmatch(_LEAD + r'apply\s+(?:to\s+)?(?:the\s+)?(?:rest|remaining\s+jobs)' + _TAIL, text, re.I):
        return ('rest', {})
    pick = PICK.fullmatch(text)
    if pick:
        if pick['picks'] and re.search(r'\bor\b', pick['picks'], re.I):
            return ('clarify', {})
        return ('apply', dict(all=True) if pick['all'] else dict(positions=positions(text)))
    match = APPLY.fullmatch(text)
    if match:
        if match['count']:
            n = int(match['count']) if match['count'].isdigit() else _NUM[match['count'].lower()]
            return ('apply', dict(top=n)) if 1 <= n <= 5 else ('clarify', {})
        if match['single']:
            return ('apply', dict(top=1))
        return ('apply', dict(company=match['company'].strip()))
    return None


def summary(rows):
    lines = []
    for n, r in enumerate(rows, 1):
        line = f'{n}. {r["title"]}' + (f' at {r["company"]}' if r['company'] else '')
        if r['score']:
            line += f' ({r["score"]}% title keywords: {r["reason"]})'
        lines.append(line)
    return ' '.join(lines)


def answer_chat(question, plans):
    """A short reply typed in June's chat while she waits on a recruiter question answers that question. With choices it
    must match one of them; otherwise it must be short, not a question, and not one of June's commands. Else None."""
    jobs = getattr(plans, 'naukri', None) if plans is not None else None
    if jobs is None or not isinstance(question, str):
        return None
    if not jobs.enabled() or jobs.setting('stopped') == '1':
        return None
    now = jobs.clock() * 1000
    waiting = [q for q in jobs.profile.pending() if q.get('waitingUntil') and q['waitingUntil'] > now]
    if len(waiting) != 1:
        return None  # none waiting, or more than one: the chat card says which is which
    text, q = question.strip(), waiting[0]
    if re.fullmatch(r'wait[.!]?', text, re.I):
        return dict(reply='Okay, I’m still waiting for your answer. Nothing further has been entered.')
    if re.fullmatch(r"(?:(?:please\s+)?(?:stop|cancel|pause)(?:\s+(?:applying|applications?|it|the application|this application|this job))?|(?:do not|don['’]?t)\s+apply(?:\s+to\s+(?:this|that)\s+job)?)(?:\s+(?:now|please))?[.!]?", text, re.I):
        jobs.set_setting('stopped', '1')
        jobs.profile.stop_waiting(q['question'])
        return dict(reply='I stopped applying and answering recruiter questions. Check the open Naukri tab; no further answers will be entered.')
    if q['options']:
        value = choose(text, q['options'], question=q['question'])
        if value is None:
            return None
    else:
        from .intent_router import routable, _DIRECT
        statement = re.match(r'^(?:yes[, ]+)?open\s+(?:to|for)\b', text, re.I)
        if not 1 <= len(text) <= 100 or '?' in text or '\n' in text or (routable(text) and _DIRECT.match(text) and not statement) or jobs_request(text):
            return None
        value = text
    try:
        jobs.profile.teach(q['question'], value, jobs.clock())
    except ValueError:
        return None
    return dict(reply=f'Saved your answer for “{q["question"][:150]}”: {value}. I’m typing it into Naukri now, and I’ll reuse it for similar questions.')


def shortlist(jobs):
    """The open jobs June lists in chat, in the order she numbers them (best title-keyword score first)."""
    return jobs.list(['found', 'not-confirmed'], 40)[:5]


async def jobs_chat(question, request_key, plans, client, settings, knowledge=None, *, conversation=None):
    jobs = getattr(plans, 'naukri', None) if plans is not None else None
    request = jobs_request(question)
    if jobs is None or request is None:
        return None
    kind, detail = request
    try:
        if kind == 'clarify':
            return dict(reply='Which jobs do you mean? Choose one to five jobs. Say “jobs 1 and 3” to select both, or name just one position.')
        if kind == 'applied':
            await jobs.check_replies(getattr(plans, 'mail', None))
            rows = jobs.list(['applied', 'replied', 'needs-you', 'not-confirmed'], 15)
            if not rows:
                return dict(reply='You haven’t applied to any jobs through June yet.')
            words = {'applied': 'applied, confirmed by Naukri', 'replied': 'reply received', 'needs-you': 'needs you', 'not-confirmed': 'not confirmed'}
            return dict(reply='; '.join(f'{r["title"]}{" at " + r["company"] if r["company"] else ""}: {words[r["status"]]}{" (" + r["detail"] + ")" if r["status"] in ("replied", "needs-you") and r["detail"] else ""}'
                                        for r in rows) + '.')
        if not jobs.enabled():
            return dict(reply=ALLOW)
        if kind == 'find':
            added = await jobs.from_naukri()
            with suppress(JuneError):
                added += await jobs.from_mail(getattr(plans, 'mail', None))
            ranked = await jobs.rank(client, settings, resume_text(knowledge))
            rows = shortlist(jobs)
            if conversation:
                jobs.set_setting('shown:' + conversation, json.dumps([r['id'] for r in rows]))
            if not rows:
                return dict(reply='I didn’t find any open jobs on Naukri just now.')
            note = '' if ranked or any(r['score'] is not None for r in rows) else ' I couldn’t rank them: add your resume in Documents so I can compare.'
            lead = f'I found {added} new job{"" if added == 1 else "s"} on Naukri.' if added else 'No new jobs on Naukri since I last looked.'
            return dict(reply=f'{lead} Your open jobs: {summary(rows)}.{note} Say “apply to the second one”, “apply to jobs 1 and 3” or “apply to the {rows[0]["company"] or "first"} one”, and I’ll show you a card first.')
        if kind == 'rest':
            if plans.active_capability('jobs.apply'):
                return dict(reply='An application card is still running. Wait for its result before continuing the rest.')
            if not conversation:
                return dict(reply='Which batch do you mean? Open its conversation or choose the jobs explicitly.')
            # Retrying a request returns its existing review, never a new execution.
            previous = json.loads(jobs.setting('rest-request:' + conversation, '{}'))
            if previous.get('request') == request_key:
                saved = await plans.get(previous['plan'])
                return dict(plan=saved['plan'], serverNow=saved['serverNow'], reply='Here is the same application review card.')
            batch = json.loads(jobs.setting('batch:' + conversation, '{}'))
            if not isinstance(batch, dict) or not isinstance(batch.get('ids'), list) or not batch.get('plan'):
                return dict(reply='Which batch do you mean? Choose the jobs explicitly or find jobs in this conversation first.')
            old = (await plans.get(batch['plan']))['plan']
            if old['status'] != 'unknown' or len(old['steps']) != len(batch['ids']):
                return dict(reply='There is no stopped, unconfirmed batch to continue here. Choose the jobs you want explicitly.')
            chosen = []
            generation = jobs.control_generation()
            for jid, step in zip(batch['ids'], old['steps']):
                row = jobs.get(jid)
                if step['status'] == 'unknown' and row['status'] in ('needs-you', 'not-confirmed'):
                    async with jobs.application_lock:
                        confirmed = await jobs.reconcile(jid, generation)
                    if confirmed:
                        jobs.mark(jid, 'applied', 'Naukri shows this job as applied on the reviewed job page.')
                elif step['status'] == 'skipped' and step.get('reason') == 'blocked-by-unknown' and row['status'] in ('found', 'not-confirmed'):
                    if row['status'] == 'not-confirmed':
                        continue  # Never offer another Apply for an unresolved prior attempt.
                    chosen.append(row)
            if not jobs.receipt_allowed(batch['ids'][0], generation):
                return dict(reply='Applying was stopped or disabled. No continuation card was prepared.')
        else:
            chosen = None
        open_rows = jobs.list(['found', 'not-confirmed'], 40)
        if kind == 'rest':
            pass
        elif 'positions' in detail or 'all' in detail:
            try:
                raw = json.loads(jobs.setting('shown:' + conversation, '[]')) if conversation else []
                shown = raw if isinstance(raw, list) and len(raw) <= 5 and all(isinstance(i, str) and re.fullmatch(r'\d{8,16}', i) for i in raw) else []
            except ValueError:
                shown = []
            base = []
            for jid in shown:
                try: row = jobs.get(jid)
                except JuneError: row = None
                base.append(row if row and row['status'] in ('found', 'not-confirmed') else None)
            listed = [r for r in base if r]
            if not listed:
                return dict(reply='I haven’t shown you a list of open jobs yet. Say “find me jobs on Naukri” first.')
            if 'all' in detail:
                chosen = listed[:5]
            else:
                wanted = [(len(shown) if n == -1 else n) for n in detail['positions']]
                missing = [n for n in wanted if not 1 <= n <= len(base) or base[n - 1] is None]
                if missing:
                    return dict(reply=f'Job {", ".join(map(str, missing))} isn’t in the list I showed you, or it’s no longer open. Say “find me jobs on Naukri” to see the current list.')
                chosen = [base[n - 1] for n in wanted][:5]
        elif 'top' in detail:
            chosen = shortlist(jobs)[:detail['top']]
        else:
            name = detail['company'].lower()
            chosen = [r for r in open_rows if name in (r['company'] + ' ' + r['title']).lower()][:1]
        if not chosen:
            return dict(reply='I don’t have a matching job in the list. Say “find me jobs on Naukri” first.')
        reply = await plans.propose({'requestId': request_key, 'intent': 'job-apply', 'input': {'ids': [r['id'] for r in chosen]}})
        if conversation:
            if kind == 'rest':
                jobs.set_setting('rest-request:' + conversation, json.dumps(dict(request=request_key, plan=reply['plan']['id'])))
            else:
                jobs.set_setting('batch:' + conversation, json.dumps(dict(plan=reply['plan']['id'], ids=[r['id'] for r in chosen])))
    except JuneError as failure:
        return dict(reply=failure.message)
    count = len(chosen)
    return dict(plan=reply['plan'], serverNow=reply['serverNow'],
                reply=f'I’ve prepared {"an application" if count == 1 else f"{count} applications"} on Naukri. Check the card below: each job is applied to only if you approve it, and only Naukri’s own confirmation counts.')
