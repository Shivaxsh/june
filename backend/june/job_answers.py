"""Answers to Naukri recruiter questions, from the person's own standing answers.

The person chose (21 Nov 2026) that June answers recruiter questions herself and submits, fully automatically,
after they approve the job card. Answers come only from:
  1. answers the person gave before for the same question (remembered), then
  2. their standing profile (salary, notice period, experience rules, locations …), with their truthfulness rules:
     never more than 1 year with any skill, 0 / No for anything they have not used.
Anything else returns None: June stops, asks the person, remembers the answer, and uses it next time.
Hard stops (OTP, captcha, tests, account sign-up, ID or bank numbers) always return a stop, never an answer.

The profile is private data in June's data folder (tools/job-profile.json, 0600), never in source or git.
Question text comes from a web page: it is matched against known questions only, never followed as an instruction.
"""
import json
import math
import os
import re
from pathlib import Path

STOP = re.compile(r"\b(?:otp|one[- ]time password|captcha|verify you are human|aadhaar|aadhar|pan\s*(?:card|number|no)|passport\s*(?:number|no)|"
                  r"bank|ifsc|account number|credit card|debit card|card number|password|sign ?up|create (?:an )?account|"
                  r"online test|assessment|coding (?:test|round|challenge)|video (?:interview|screening)|voice screening)\b", re.I)


def key(question):
    """A question's identity for remembering: lower case words only."""
    return ' '.join(re.findall(r"[a-z0-9+#.]+", (question or '').lower()))[:300]


def _norm(text):
    return ' '.join(re.findall(r"[a-z0-9+#.]+", (text or '').lower()))


def _number(value):
    return f'{value:g}'


class Profile:
    """The person's standing answers (private JSON) plus answers they taught June (sqlite, same jobs database)."""
    def __init__(self, path, db):
        self.path, self.db = Path(path), db
        with self.db() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS answers(key TEXT PRIMARY KEY,question TEXT NOT NULL,answer TEXT NOT NULL,updated REAL NOT NULL)')
            connection.execute('CREATE TABLE IF NOT EXISTS asked(key TEXT PRIMARY KEY,question TEXT NOT NULL,options TEXT NOT NULL,job TEXT NOT NULL,at REAL NOT NULL)')
            columns = [r[1] for r in connection.execute('PRAGMA table_info(asked)')]
            if 'title' not in columns:
                connection.execute("ALTER TABLE asked ADD COLUMN title TEXT NOT NULL DEFAULT ''")  # the job, for the chat card
            if 'waiting' not in columns:
                connection.execute('ALTER TABLE asked ADD COLUMN waiting REAL')  # while June holds the application open for the answer

    def standing(self):
        try:
            value = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def learned(self, question):
        with self.db() as connection:
            row = connection.execute('SELECT answer FROM answers WHERE key=?', (key(question),)).fetchone()
        return row[0] if row else None

    def teach(self, question, answer, clock):
        k = key(question)
        if not k or len(question) > 300 or STOP.search(question) or not isinstance(answer, str) or not answer.strip() or len(answer) > 300 or re.search(r'[\x00-\x1f\x7f]', answer):
            raise ValueError('answer')
        with self.db() as connection:
            connection.execute('INSERT OR REPLACE INTO answers VALUES(?,?,?,?)', (k, question[:300], answer.strip(), clock))
            connection.execute('DELETE FROM asked WHERE key=?', (k,))

    def forget(self, k):
        with self.db() as connection:
            connection.execute('DELETE FROM answers WHERE key=?', (k,))

    def ask(self, question, options, job, clock, title='', waiting=None):
        """Record a question for the person. `waiting` is when June stops holding the application open for it."""
        with self.db() as connection:
            connection.execute('INSERT OR REPLACE INTO asked(key,question,options,job,at,title,waiting) VALUES(?,?,?,?,?,?,?)',
                               (key(question), question[:300], json.dumps(options[:12]), job, clock, (title or '')[:200], waiting))

    def stop_waiting(self, question):
        with self.db() as connection:
            connection.execute('UPDATE asked SET waiting=NULL WHERE key=?', (key(question),))

    def recover_waiting(self):
        """A new service cannot resume an old in-memory browser workflow."""
        with self.db() as connection:
            connection.execute('UPDATE asked SET waiting=NULL WHERE waiting IS NOT NULL')

    def pending(self):
        with self.db() as connection:
            rows = connection.execute('SELECT * FROM asked ORDER BY at DESC LIMIT 20').fetchall()
        return [dict(key=r['key'], question=r['question'], options=json.loads(r['options']), job=r['job'], title=r['title'] or '',
                     waitingUntil=round(r['waiting'] * 1000) if r['waiting'] else None) for r in rows]

    def saved(self):
        with self.db() as connection:
            rows = connection.execute('SELECT key,question,answer FROM answers ORDER BY updated DESC LIMIT 100').fetchall()
        return [dict(key=r['key'], question=r['question'], answer=r['answer']) for r in rows]

    def similar(self, question, kind, options):
        """Saved answers to questions that may ask the same thing in other words: [(score, saved question, answer, sure)].
        Never across different named things (Noida vs Bangalore, React vs Vue) or units, and the answer must fit this
        question's choices. `sure` means reuse directly: same named things and content gist. Otherwise (one
        question lists extra examples, or a middling score) a second opinion must confirm before reuse."""
        words, names, units = _gist(question)
        if not words:
            return []
        out = []
        for row in self.saved():
            other_words, other_names, other_units = _gist(row['question'])
            if not other_words or units != other_units or not (names <= other_names or other_names <= names) or _answer_scope(question) != _answer_scope(row['question']):
                continue
            score = len(words & other_words) / len(words | other_words)
            if score < SIMILAR_MAYBE:
                continue
            if options and choose(row['answer'], options, question=question) is None:
                continue
            if kind == 'number' and not re.fullmatch(r'\d+(?:\.\d+)?', row['answer'].strip()):
                continue
            out.append((score, row['question'], row['answer'], names == other_names and words == other_words))
        return sorted(out, key=lambda c: -c[0])[:3]


SIMILAR_MAYBE = 0.35


def _answer_scope(text):
    # Negation and factual scope cannot be decided by word-overlap or a model
    # vote: "no experience" and "experience" need opposite answers.
    words = set(re.findall(r'[a-z]+', text.lower()))
    scope = words & {'no', 'not', 'never', 'without', 'unwilling', 'unable', 'uncomfortable', 'unavailable',
                     'dislike', 'avoid', 'refuse', 'against', 'opposed', 'cannot', 'professional', 'commercial',
                     'paid', 'production', 'total', 'relevant', 'current', 'expected', 'previous', 'minimum', 'maximum'}
    if re.search(r"\b(?:can|won|don|doesn|isn|aren|haven|hasn)['’]t\b", text, re.I): scope.add('not')
    return scope
_FILLER = set('''a an the and or of to in on at for with from by as is are am was were be been being do does did you your yours we our us
i me my it its this that these those there here if yes no please kindly briefly mention share tell describe explain answer question
have has had any some how what which who whom when where why can could would will shall should may might much many any
currently current daily day work working use using used also only just like such etc e.g eg ever'''.split())
_UNITS = {'lpa', 'lakh', 'lakhs', 'lac', 'lacs', 'month', 'months', 'monthly', 'year', 'years', 'yearly', 'annum', 'annual', 'day', 'days',
          'week', 'weeks', 'hour', 'hours', 'k', 'thousand', 'thousands', 'inr', 'usd', 'percent', 'percentage', 'cgpa', 'gpa'}


def _gist(text):
    """(content words, named things, units) of a question. Named things are capitalised words after the first word,
    tokens with digits or dots (Node.js, 2025) — two questions about different places, companies or skills never match."""
    raw = re.findall(r"[A-Za-z0-9+#.]+", text or '')
    names = {w.lower().rstrip('.') for n, w in enumerate(raw) if (n and w[:1].isupper() and not w.isupper() or len(w) > 1 and w.isupper())
             or re.search(r'\d|\w\.\w', w)}
    words, units = set(), set()
    for w in (w.lower().rstrip('.') for w in raw):
        if w in _UNITS:
            units.add({'months': 'month', 'monthly': 'month', 'years': 'year', 'yearly': 'year', 'annum': 'year', 'annual': 'year',
                       'lakh': 'lpa', 'lakhs': 'lpa', 'lac': 'lpa', 'lacs': 'lpa', 'days': 'day', 'weeks': 'week', 'hours': 'hour',
                       'thousand': 'k', 'thousands': 'k', 'percentage': 'percent'}.get(w, w))
            continue
        if w in _FILLER or len(w) < 2:
            continue
        for end in ('ing', 'ed', 'es', 's'):  # fold simple plurals and tenses: tools/tool, integrating/integrate
            if len(w) > len(end) + 3 and w.endswith(end) and not w.endswith('ss'):
                w = w[:-len(end)]
                break
        words.add(w)
    return words, names, units



def _money(q, lpa, kind):
    if type(lpa) not in (int, float) or not math.isfinite(lpa) or lpa < 0:
        return None
    monthly = bool(re.search(r'\b(?:month|monthly|pm)\b', q))
    if re.search(r'\b(?:usd|dollars?|eur|euros?|gbp|pounds?)\b', q):
        return None  # the stored INR amount does not establish another currency
    if monthly and re.search(r'\blpa\b', q):
        return None  # conflicting annual and monthly units need the person's answer
    if re.search(r'\b(?:lakh|lakhs|lac|lacs|lpa)\b', q):
        return _number(lpa / 12 if monthly else lpa)
    if re.search(r'\b(?:thousands?|k)\b', q):
        return _number(lpa * 100 / 12 if monthly else lpa * 100)
    if monthly:
        return str(round(lpa * 100000 / 12))
    if kind == 'number' or re.search(r'\b(?:inr|rupees|annum|annual|yearly|in numbers?)\b', q):
        return str(round(lpa * 100000))
    return f'{_number(lpa)} LPA'


def _skill(q, profile):
    """The skill a 'years with X' / 'experience with X' question is about, and whether the person has it."""
    known = [_norm(s) for s in profile.get('skills', []) if isinstance(s, str)]
    unknown = [_norm(s) for s in profile.get('skillsAsk', []) if isinstance(s, str)]
    def matches(s):
        pattern = re.escape(s).replace(r'\.', r'[.\s-]?')
        if s == 'react': pattern += r'(?!\s+native\b)'
        return bool(s and re.search(r'(?<![a-z0-9.])' + pattern + r'(?![a-z0-9])', q))
    found = [s for s in known if matches(s)]
    ask = [s for s in unknown if matches(s)]
    return found, ask


def standing_answer(question, kind, profile):
    """The answer from the standing profile, None when the profile doesn't cover it, or STOP_ANSWER for a hard stop."""
    q = _norm(question)
    if '₹' in question:
        q += ' rupees'
    p = profile
    if not q:
        return None
    if STOP.search(question):
        return STOP_ANSWER
    yes, no = 'Yes', 'No'
    # money
    if re.search(r'\b(?:expected|expectation)\b.*\b(?:ctc|salary|package|compensation)\b|\b(?:ctc|salary|package)\b.*\bexpect', q):
        return _money(q, p.get('expectedCtcLpa'), kind)
    if re.search(r'\b(?:current|present|last drawn|last|existing)\b.*\b(?:ctc|salary|package|compensation)\b|^(?:ctc|salary)\b', q):
        return _money(q, p.get('currentCtcLpa'), kind)
    # notice / joining
    if re.search(r'\bnotice period\b|\bhow soon can you join\b|\bwhen can you join\b|\bearliest (?:joining|start)', q):
        days = p.get('noticeDays')
        if days is None:
            return None
        if re.search(r'\bdays?\b', q) or kind == 'number':
            return str(days)
        return 'Immediate joiner' if days == 0 else f'{days} days'
    if re.search(r'\b(?:join|start)\b.*\b(?:immediately|immediate|asap|within|in \d+|1 2 weeks|15 days|next week)\b|\bimmediate joiner\b', q):
        return yes if p.get('noticeDays') == 0 else None
    # A resume upload inside the questions: Naukri sends the profile resume instead (the person's own rule).
    if re.search(r'\bupload\b.*\b(?:resume|cv)\b|\b(?:resume|cv)\b.*\bupload', q):
        return "I'll do it later"
    if re.search(r'\bcareer gap\b|\bgap in (?:your )?(?:career|education)', q) and re.fullmatch(r'\d{4}-\d{2}', str(p.get('careerGapSince', ''))):
        import datetime
        year, month = map(int, p['careerGapSince'].split('-'))
        today = datetime.date.today()
        months = (today.year - year) * 12 + today.month - month
        return f'{months} months - {p.get("careerGapReason", "gap")}' if months > 0 else None
    # stops that need judgement the profile cannot give
    if re.search(r'\bwalk ?in\b', q):
        return None
    # experience: per skill
    if re.search(r'\b(?:years?|yrs|months?)\b.*\b(?:experience|exp|worked|working|hands on)\b|\b(?:experience|exp)\b.*\b(?:years?|yrs|months?)\b|\bhow (?:many|much) (?:years|experience)\b', q):
        if re.search(r'\b(?:and|or)\b|&', question, re.I):
            return None  # one scalar cannot safely describe different skills
        found, ask = _skill(q, p)
        if found and not ask:
            if re.search(r'\bmonths?\b', q) and not re.search(r'\byears?\b', q):
                return '12' if kind == 'number' or re.search(r'\bin months?\b', q) else '12 months'
            return '1' if kind == 'number' or re.search(r'\bin (?:years|numbers?)\b|\byears\b', q) else '1 year'
        if ask:
            return None
        if re.search(r'\btotal\b|\boverall\b|\brelevant\b|\bprofessional\b|\bwork experience\b|\bhow many years of experience do you have\b$', q):
            years = p.get('relevantExperienceYears' if 'relevant' in q else 'totalExperienceYears')
            if years is not None and re.search(r'\bmonths?\b', q) and not re.search(r'\byears?\b', q):
                return _number(years * 12) if kind == 'number' or re.search(r'\bin months?\b', q) else f'{_number(years * 12)} months'
            return None if years is None else (_number(years) if kind == 'number' or 'years' in q else f'{_number(years)} year')
        tools = re.search(r'\b(?:in|with|on|using)\s+([a-z0-9+#. ]{2,40})', q)
        if tools and p.get('zeroForOtherSkills'):
            return '0'
        return None
    if re.search(r'^rate\b|\brating\b|\bproficiency\b|\b(?:skill|expertise) level\b|\bhow (?:good|proficient|comfortable) are you\b', q):
        found, ask = _skill(q, p)
        # A tool they have not used gets the lowest level; a level for one they use is theirs to choose.
        return 'Beginner' if not found and not ask and p.get('zeroForOtherSkills') else None
    if re.search(r'^(?:do|have|are) you (?:have )?(?:any )?(?:hands on |prior |working |practical )?(?:experience|worked|used|familiar|knowledge|exposure)\b|\bexperience (?:with|in|on)\b.*\?*$', q):
        if re.search(r'\b(?:and|or)\b|&', question, re.I):
            return None
        found, ask = _skill(q, p)
        if found or ask:
            return yes
        return no if p.get('zeroForOtherSkills') else None
    # location
    if re.search(r'\b(?:relocat|travel|commut|work from office|wfo|onsite|on site|in office|hybrid'
                 r'|work(?:ing)? (?:from|at|in) (?:our|the|their|your|client|office)'
                 r'|(?:ok|okay|fine|comfortable|happy|willing|able|open|ready)\b.{0,25}\b(?:work(?:ing)?|join(?:ing)?|report(?:ing)?|based)\b.{0,20}\b(?:from|in|at)\b)', q):
        # Every place word must be somewhere the person said is fine; any other place (or an unclear one) is asked.
        nearby = {w for place in p.get('nearbyPlaces', []) for w in _norm(place).split()}
        filler = {'our', 'the', 'their', 'your', 'a', 'an', 'office', 'offices', 'site', 'location', 'locations', 'city', 'client', 'clients', 'work', 'working',
                  'shift', 'shifts', 'any', 'extension', 'sector', 'greater', 'new', 'region', 'area', 'campus', 'branch', 'hq', 'headquarters', 'days', 'day',
                  'week', 'a week', 'per', 'all', 'from', 'in', 'at', 'to', 'with', 'for', 'and', 'only', 'onsite', 'hybrid', 'mode', 'model', 'basis', 'full', 'time',
                  'monday', 'friday', 'saturday', 'is', 'it', 'okay', 'ok', 'you', 'be', 'if', 'required', 'needed',
                  'relocate', 'relocating', 'relocation', 'travel', 'travelling', 'traveling', 'commute', 'commuting', 'join', 'joining',
                  'report', 'reporting', 'move', 'moving', 'based', 'come', 'go'}
        named = re.findall(r'\b(?:in|to|at|from)\s+([a-z][a-z0-9 .]{2,40})', q)
        for phrase in named:
            words = [w for w in re.findall(r'[a-z]+', phrase) if w not in filler]
            if 'or' in words or any(w not in nearby for w in words):
                return None
        return yes if p.get('openAcrossNcr') else None
    if re.search(r'\bcurrent (?:location|city)\b|\bwhere (?:are you|do you) (?:currently )?(?:based|live|stay)', q):
        return p.get('currentLocation')
    if re.search(r'\bpreferred (?:location|city)\b', q):
        return p.get('preferredLocation')
    employment = re.search(r'\b(?:previously|ever) (?:been )?(?:employed|worked) (?:by|with|at|for)\s+(.+)', q)
    if employment:
        target = re.sub(r'\s+(?:before|previously|earlier)[ .]*$', '', employment[1]).strip(' .')
        if re.fullmatch(r'(?:us|our company|this company|the company|here)', target):
            value = p.get('previouslyEmployed')
            return (yes if value else no) if type(value) is bool else None
        employer = _norm(str(p.get('lastEmployer') or '').split('(')[0]).strip(' .')
        return yes if employer and target == employer else None
    # yes/no habits and facts from the profile
    for pattern, field in ((r'\bown (?:a )?laptop\b|\bhave (?:a |your own )?laptop\b', 'ownLaptop'), (r'\bwhich laptop\b|\blaptop (?:brand|model|do you)', 'laptop'),
                           (r'\b6 days?\b|\bsix days?\b', 'sixDayWeek'), (r'\bstart ?up\b', 'startup'), (r'\bnight shift|\brotational|\b24 ?x ?7\b|\bshifts?\b', 'shifts'),
                           (r'\bhandled (?:a )?team|\bteam lead|\bled a team', 'team'), (r'\b(?:family|relative)\b.*\bpolitically exposed\b|\bpolitically exposed\b.*\b(?:family|relative)', 'pepFamily'),
                           (r'\bpolitically exposed\b', 'pepSelf'), (r'\bauthori[sz]ed to work in the (?:us|united states)', 'usWorkAuth'),
                           (r'\b(?:require|need)\b.*\bsponsorship\b.*\b(?:us|united states|h ?1b)\b|\bh ?1b\b', 'usSponsorship'),
                           (r'\bsponsorship\b.*\bindia\b|\bvisa\b.*\bindia\b', 'indiaSponsorship'),
                           (r'\bwhere did you (?:hear|find)\b|\bhow did you (?:hear|find)\b', 'heardAbout'), (r'\bsalutation\b|\btitle mr\b', 'salutation'),
                           (r'\bgender\b|\bdisabilit|\bdiversity\b|\bcaste\b', 'voluntary'), (r'\blinked ?in\b', 'linkedin'), (r'\bportfolio\b', 'portfolio'),
                           (r'\bgit ?hub\b', 'github'), (r'\bhighest (?:qualification|education|degree)\b|\bpost ?graduat', 'qualification'),
                           (r'\bgraduat|\bbachelor', 'graduation'), (r'\b(?:current|last|previous) (?:company|employer|organi[sz]ation)\b', 'lastEmployer'),
                           (r'\b(?:current|last|previous) (?:designation|role|title|job title)\b', 'designation'), (r'\bcareer gap\b|\bgap in (?:your )?(?:career|education)', 'careerGap'),
                           (r'^(?:(?:what is|please (?:enter|provide)|enter|provide) )?(?:your )?(?:phone|mobile|contact)(?: number)?[ .]*$', 'phone'),
                           (r'^(?:(?:what is|please (?:enter|provide)|enter|provide) )?(?:your )?e ?mail(?: address)?[ .]*$', 'email'),
                           (r'^(?:(?:what is|please (?:enter|provide)|enter|provide) )?(?:your )?(?:full )?name[ .]*$', 'name')):
        if re.search(pattern, q):
            value = p.get(field)
            if isinstance(value, bool):
                return yes if value else no
            return value if isinstance(value, str) and value else None
    if re.search(r'\bdate of birth\b|\bdob\b', q):
        return p.get('dob') or None
    if re.search(r'\bcurrently employed\b|\bcurrently working\b', q):
        return no
    return None


STOP_ANSWER = object()


def choose(answer, options, *, question=''):
    """The option to pick for an answer, or None when no option clearly matches."""
    if not options:
        return None
    norm = [(o, _norm(o)) for o in options]
    raw = [(o, ' '.join(o.lower().split())) for o in options]  # keeps '-', '+' and '<' for ranges
    a = _norm(answer)
    for o, n in norm:
        if n == a:
            return o
    if a in ('yes', 'no'):
        for o, n in norm:
            if n.split(' ')[0] == a:
                return o
        return None
    if 'immediate' in a or a == '0':
        for o, n in norm:
            if re.search(r'\bimmediate|\b0 days?\b|\bless than 15 days\b|\b15 days or less\b|\bwithin 15 days\b', n):
                return o
    number = re.fullmatch(r'(\d+(?:\.\d+)?)(?: years?| months?| weeks?| lpa| days?| thousands?| k)?', a)
    if number:
        value = float(number.group(1))
        money = bool(re.search(r'\b(?:ctc|salary|package|compensation|lpa|lakh|lac|rupees?|inr)\b', _norm(question) + ' ' + a))
        def units(text):
            patterns = ((r'\b(?:lpa|lakhs?|lacs?)\b', 'lakh'), (r'\b(?:thousands?|k)\b', 'thousand'),
                        (r'\b(?:inr|rupees?|rs)\b|₹', 'rupee')) if money else (
                        (r'\b(?:years?|yrs?)\b', 'year'), (r'\bmonths?\b', 'month'),
                        (r'\bweeks?\b', 'week'), (r'\bdays?\b', 'day'))
            return {name for pattern,name in patterns if re.search(pattern, text, re.I)}
        source_units = units(a) or units(question) or ({'rupee'} if money else set())
        def period(text):
            if re.search(r'\b(?:months?|monthly|pm)\b', text, re.I): return 'month'
            if re.search(r'\b(?:annual|annum|yearly|lpa)\b', text, re.I): return 'year'
            return None
        source_period = period(question) or ('year' if money else None)
        for o, n in raw:
            option_units = units(n)
            if option_units and (len(option_units) != 1 or (source_units != option_units and value != 0)):
                continue
            if money and period(n) and source_period != period(n):
                continue
            low_high = re.search(r'(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)', n)
            if low_high and float(low_high.group(1)) <= value <= float(low_high.group(2)):
                return o
            plus = re.search(r'(\d+(?:\.\d+)?)\s*\+', n)
            if plus and value >= float(plus.group(1)):
                return o
            less = re.search(r'(?:less than|below|under|<)\s*(\d+(?:\.\d+)?)', n)
            if less and value < float(less.group(1)):
                return o
            scalar = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:years?|yrs?|months?|weeks?|days?|lpa|lakhs?|lacs?|thousands?|k|inr|rupees?)?', n)
            if scalar and value == float(scalar[1]):
                return o
        return None  # "1" must never prefix-match "10 years" or a different amount
    for o, n in norm:
        if a and (n.startswith(a + ' ') or a.startswith(n + ' ')) and len(n) > 1:
            return o
    return None


def private_profile_path(directory):
    path = Path(directory) / 'job-profile.json'
    return path


def write_profile(path, value):
    path = Path(path)
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(value, handle, indent=1)
    os.chmod(path, 0o600)
