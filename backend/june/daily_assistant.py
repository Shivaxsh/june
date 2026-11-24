"""On-request facts from structured sources; no inference, background fetch or speech."""
import asyncio
from copy import deepcopy
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlencode
import uuid
from zoneinfo import ZoneInfo

from .connector_http import ConnectorHTTP
from .errors import JuneError
from .tool_plans import digest, encoded

WEATHER_HOSTS = ['api.open-meteo.com', 'geocoding-api.open-meteo.com']
GOOGLE_HOSTS = ['accounts.google.com', 'oauth2.googleapis.com', 'www.googleapis.com']


def briefing_intent(text):
    return bool(re.fullmatch(r'\s*(?:june[,!:\s]+)?(?:please\s+)?(?:good morning|brief me|give me my (?:morning |daily )?briefing)(?:\s+please)?[.!?\s]*', text, re.I))


WEATHER = re.compile(r"\s*(?:(?:ok(?:ay)?|so|now|and)[,\s]+)*(?:(?:hey\s+)?june[,!:\s]+)?(?:(?:can|could)\s+you\s+)?(?:tell\s+me\s+)?(?:"
    r"(?:what(?:['’]s|\s+is)|how(?:['’]s|\s+is))\s+the\s+(?:weather|temperature)(?:\s+like)?|weather|"
    r"how\s+(?:hot|cold|warm)\s+is\s+it|is\s+it\s+(?:hot|cold|warm|chilly)(?=\s+(?:outside|today|now|right|in\s+[a-z])|[\s?.!]*$))"
    r"(?:\s+(?:outside|today|now|right\s+now|currently))*(?:\s+in\s+(?P<place>[a-z][a-z .'-]{1,40}?))?(?:\s+(?:today|now|right\s+now))?[\s?.!]*", re.I)
_NOT_A_CITY = {'space', 'general', 'summer', 'winter', 'the sun', 'the world', 'here'}


def weather_intent(text):
    """'' for the current weather, a lower-case place when one is named, None when it is not a weather question."""
    if not isinstance(text, str) or len(text) > 200:
        return None
    match = WEATHER.fullmatch(text)
    if not match:
        return None
    place = (match['place'] or '').strip().lower()
    return None if place in _NOT_A_CITY and place != 'here' else '' if place == 'here' else place


_WHEN = r"(?:(?:for |on |scheduled (?:for )?)?(?P<{0}>today|tomorrow)|on (?:my|the) calendar|in (?:my|the) calendar|scheduled|coming up|planned)"
_EVENT = r"(?:events?|meetings?|appointments?|reminders?)"
AGENDA = tuple(re.compile(pattern.format(*'abcdef'), re.I) for pattern in (
    r"(?:what(?: is|s)|whats|show me|tell me|check|read(?: me)?) (?:on |in )?(?:my|the) (?:calendar|schedule|agenda)(?: look like)?(?: " + _WHEN + r")?",
    r"(?:what(?: is|s)|whats|show me|tell me|check|read(?: me)?) (?P<a>today|tomorrow)s (?:schedule|agenda|calendar|events|meetings)",
    r"(?:what(?: is|s)|whats|what do i have|what have i got) (?:there )?(?:for )?(?P<a>today|tomorrow) (?:on|in) (?:my|the) (?:calendar|schedule|agenda)",
    r"(?:what(?: is|s)|whats) (?:happening|planned|scheduled|on)(?: for| on)? (?P<a>today|tomorrow)",
    r"(?:(?:do i have|are there|is there|have i got|got) )?(?:any|anything)(?: (?:upcoming|other))?(?: " + _EVENT + r"(?: (?:or|and) " + _EVENT + r")?)?(?: " + _WHEN + r")(?: " + _WHEN.replace('{0}', '{1}') + r")?",
    r"what (?:" + _EVENT + r"(?: (?:or|and) " + _EVENT + r")? )?do i have(?: " + _WHEN + r")(?: " + _WHEN.replace('{0}', '{1}') + r")?",
    r"what(?: is| are|s) (?:my|the) " + _EVENT + r"(?: (?:or|and) " + _EVENT + r")?(?: " + _WHEN + r")?",
))


def agenda_intent(text):
    """(day offset, include reminders) for a question about today's or tomorrow's calendar, else None."""
    if not isinstance(text, str) or len(text) > 200:
        return None
    q = re.sub(r"[^\w\s]", '', text.lower().replace('’', '').replace("'", ''))
    q = re.sub(r"\s+", ' ', q).strip()
    q = re.sub(r"^(?:(?:ok(?:ay)?|so|now|and|hey|june|please|well|um|uh)\s+)+", '', q)
    q = re.sub(r"^(?:can|could) you (?:please )?", '', q)
    for pattern in AGENDA:
        match = pattern.fullmatch(q)
        if match:
            days = [value for value in match.groupdict().values() if value]
            generic = not re.search(r"\b(?:events?|meetings?|appointments?|calendar|schedule|agenda)\b", q)
            wants_reminders = bool(re.search(r"\breminders?\b", q)) or generic
            if wants_reminders and not generic and not re.search(r"\b(?:events?|meetings?|appointments?|calendar)\b", q):
                return None  # "what reminders do I have" belongs to the reminder service
            if generic and not days:
                return None
            return (1 if 'tomorrow' in days else 0, wants_reminders)
    return None


_FILLER = r"(?:(?:ok(?:ay)?|so|well|no|yes|yeah|now|and|then|alright|right|oh|uh|um|hmm)[,.!\s]+)*"
_MUSIC_LEAD = r"\s*" + _FILLER + r"(?:(?:hey\s+)?june[,!:\s]+)?" + _FILLER + r"(?:just\s+(?:to\s+)?)?(?:(?:can|could|would|will)\s+you\s+|please\s+)?(?:just\s+)?"
_MUSIC_TAIL = r"(?:\s+(?:from|in|on)\s+(?:apple\s+)?music)?(?:\s+(?:please|for me|now))?[\s.!?]*"
_OPEN_MUSIC = r"(?:(?:open|launch|start)\s+(?:my\s+|the\s+)?(?:apple\s+)?music(?:\s+app)?\s+and\s+)?"
# "Play my Drive playlist", "Can you play the music?", "Put on some music".
_PLAY = r"(?:play|start|put\s+on|(?:i\s+(?:want|would\s+like)|i['’]d\s+like)\s+to\s+(?:listen\s+to|hear))"
MUSIC_REQUEST = re.compile(_MUSIC_LEAD + _OPEN_MUSIC + _PLAY + r"\s+(?:(?:some|my|the|a)\s+)?"
    r"(?:(?P<name>[\w’'-]+(?:\s+[\w’'-]+){0,3}?)\s+)?(?P<noun>music|songs|playlist)" + _MUSIC_TAIL, re.I)
_NAME = r"(?P<name>[\w’'&.+-]+(?:\s+[\w’'&.+-]+){0,5})"
MUSIC_KIND = re.compile(_MUSIC_LEAD + r"play\s+(?:(?:the|my)\s+)?(?:(?P<what>album|song|track|artist)\s+|(?:(?:some\s+)?(?:songs|music|tracks)|something|anything)\s+(?P<by>by|from)\s+)" + _NAME + _MUSIC_TAIL, re.I)
MUSIC_BARE = re.compile(_MUSIC_LEAD + r"(?:play|put\s+on|(?:i\s+(?:want|would\s+like)|i['’]d\s+like)\s+to\s+(?:listen\s+to|hear))\s+(?:some\s+)?" + _NAME + _MUSIC_TAIL, re.I)
_SONG = r"(?:\s+(?:the\s+|this\s+|that\s+|a\s+)?(?:music|song|track|one|playback))"
MUSIC_CONTROLS = (
    ('pause', re.compile(_MUSIC_LEAD + r"(?:(?:stop|pause|hold)" + _SONG + r"|pause(?:\s+it)?|stop\s+playing(?:\s+music)?|stop\s+music|music\s+off"
        r"|(?:turn|switch)\s+off\s+the\s+music|(?:turn|switch)\s+the\s+music\s+off)" + _MUSIC_TAIL, re.I)),
    ('resume', re.compile(_MUSIC_LEAD + r"(?:(?:resume|continue|unpause)" + _SONG + r"|resume(?:\s+it|\s+playback)?|unpause(?:\s+it)?|(?:resume|continue|keep)\s+playing"
        r"|play\s+(?:it|that)(?:\s+again)?|play\s+(?:the\s+)?(?:music|song)\s+again|play\s+again|start\s+(?:it|the\s+music|the\s+song)\s+again"
        r"|music\s+on|(?:turn|switch)\s+the\s+music\s+(?:back\s+)?on|(?:turn|switch)\s+(?:back\s+)?on\s+the\s+music)" + _MUSIC_TAIL, re.I)),
    ('previous', re.compile(_MUSIC_LEAD + r"(?:(?:previous|last)\s+(?:song|track|one)|previous|go\s+back\s+(?:a|one)\s+(?:song|track)"
        r"|go\s+back\s+to\s+(?:the\s+)?(?:previous|last)\s+(?:song|track|one)|play\s+(?:the\s+)?(?:previous|last)(?:\s+(?:song|track|one))?(?:\s+again)?)" + _MUSIC_TAIL, re.I)),
    ('next', re.compile(_MUSIC_LEAD + r"(?:(?:next|skip|change|switch)" + _SONG + r"|skip(?:\s+it)?|next|play\s+(?:the\s+)?next(?:\s+(?:song|track|one))?"
        r"|(?:play\s+)?(?:a\s+)?(?:another|different)(?:\s+(?:song|track|one))?|another\s+song|play\s+something\s+else)" + _MUSIC_TAIL, re.I)),
)
MUSIC_STATUS = re.compile(_MUSIC_LEAD + r"(?:tell\s+me\s+)?(?:what(?:['’]s|\s+is)\s+(?:playing|this\s+song|that\s+song|the\s+name\s+of\s+this\s+song)|(?:what|which)\s+(?:song|track|music)\s+is\s+(?:this|that|playing|it)"
    r"|what\s+am\s+i\s+listening\s+to|who\s+(?:sings|is\s+singing)\s+this(?:\s+song)?|is\s+(?:the\s+)?music\s+playing)(?:\s+(?:right\s+now|now|currently))?[\s.!?]*", re.I)
GENERIC_MUSIC_NAMES = {'', 'focus', 'my', 'some', 'the', 'favourite', 'favorite'}
# "Play a game", "play with me", "play guitar": not requests for music.
NOT_MUSIC = re.compile(r"^(?:a|an|with|games?|chess|guitar|piano|video|videos|it|this|that|along|around|fair|you|your|me|us|him|her|them|"
                       r"something|anything|nothing|everything)\b", re.I)


def music_command(text):
    """A direct music request: ('control', op) | ('playlist', name, explicit) | ('library', query, what). Else None."""
    if not isinstance(text, str) or len(text) > 300 or re.search(r"\b(?:do not|don['’]?t|never)\b", text, re.I):
        return None
    for op, pattern in MUSIC_CONTROLS:
        if pattern.fullmatch(text):
            return ('control', op)
    if MUSIC_STATUS.fullmatch(text):
        return ('status',)
    match = MUSIC_REQUEST.fullmatch(text)
    if match:
        name = (match['name'] or '').strip().casefold()
        if match['noun'].lower() == 'playlist' or name in GENERIC_MUSIC_NAMES:
            return ('playlist', name, True)
        return None if NOT_MUSIC.match(name) else ('library', name, 'any')
    match = MUSIC_KIND.fullmatch(text)
    if match:
        what = 'artist' if match['by'] or (match['what'] or '').lower() == 'artist' else 'song' if match['what'].lower() in ('song', 'track') else 'album'
        return ('library', match['name'].strip().casefold(), what)
    match = MUSIC_BARE.fullmatch(text)
    if match and re.fullmatch(r"(?:some\s+|a\s+few\s+|my\s+)?(?:tunes|songs|music|jams|beats|bangers)", match['name'].strip(), re.I):
        return ('playlist', '', True)  # "put on some tunes" is their music, not a song called "some tunes"
    if match and not NOT_MUSIC.match(match['name']):
        return ('library', match['name'].strip().casefold(), 'any')
    return None


def music_intent(text):
    """The name asked for in a play request ('' for "the music"), or None when it is not one."""
    command = music_command(text)
    return command[1] if command and command[0] in ('playlist', 'library') else None


def clean_text(value, limit):
    return isinstance(value, str) and 1 <= len(value.strip()) <= limit and not re.search(r'[\x00-\x1f\x7f]', value)


class DailyAssistant:
    def __init__(self, directory, *, clock=time.time, music=None, google=None, calendar=None):
        self.directory = Path(directory) / 'tools'
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / 'assistant.sqlite3'
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600); os.close(fd)
        self.path.chmod(0o600)
        self.clock, self.music, self.google, self.calendar = clock, music, google, calendar
        self.place_cache = {}
        self.weather_cache = None
        self.connection_lock = asyncio.Lock()
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY,document TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS goals(id TEXT PRIMARY KEY,document TEXT NOT NULL,deleted INTEGER NOT NULL DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,signature TEXT NOT NULL,response TEXT NOT NULL,created REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS metadata(id TEXT PRIMARY KEY,document TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO settings VALUES(1,?)', (encoded(dict(revision=1,
                weather=dict(place=None, units='metric'), music=dict(playlist=None),
                briefing=dict(sections=['weather', 'calendar', 'goals']))),))
        self.weather_http = ConnectorHTTP('open-meteo', WEATHER_HOSTS, enabled=lambda: self.enabled('open-meteo'))

    def db(self):
        db = sqlite3.connect(self.path, timeout=3); db.row_factory = sqlite3.Row; return db

    def envelope(self, **values):
        return dict(version=1, serverNow=round(self.clock()*1000), **values)

    def meta(self, key):
        with self.db() as db:
            row = db.execute('SELECT document FROM metadata WHERE id=?', (key,)).fetchone()
        return json.loads(row[0]) if row else {}

    def set_meta(self, key, value):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', (key, encoded(value)))

    def enabled(self, key):
        return self.meta(key).get('enabled') is True

    def connection(self, key):
        meta = self.meta(key)
        label = {'open-meteo':'Weather', 'google':'Google Calendar', 'apple-music':'Apple Music', 'apple-calendar':'Apple Calendar'}[key]
        active = meta.get('enabled') is True
        state = meta.get('state', 'not-configured')
        return dict(id=key, label=label, state=state, enabled=active, hosts=WEATHER_HOSTS if key == 'open-meteo' else GOOGLE_HOSTS if key == 'google' else [],
            scopes=['https://www.googleapis.com/auth/calendar.events.readonly'] if key == 'google' and state == 'connected' else [],
            checkedAt=meta.get('checkedAt'), message=meta.get('message', 'Set up this connection in Systems → Daily.'))

    def _request(self, db, value, operation, effect):
        if not isinstance(value, dict) or not isinstance(value.get('requestId'), str) or not re.fullmatch(r'[\w-]{8,128}', value['requestId'], re.ASCII):
            raise JuneError('invalid-assistant', 'A valid request id is required.', 400)
        signature = digest([operation, value])
        old = db.execute('SELECT * FROM requests WHERE id=?', (value['requestId'],)).fetchone()
        if old:
            if old['signature'] != signature:
                raise JuneError('request-conflict', 'This request id was already used.', 409)
            return json.loads(old['response'])
        result = effect()
        db.execute('INSERT INTO requests VALUES(?,?,?,?)', (value['requestId'], signature, encoded(result), self.clock()))
        db.execute('DELETE FROM requests WHERE created<?', (self.clock()-30*86400,))
        return result

    def _replay(self, value, operation):
        if not isinstance(value,dict) or not isinstance(value.get('requestId'),str) or not re.fullmatch(r'[\w-]{8,128}',value['requestId'],re.ASCII):
            raise JuneError('invalid-assistant','A valid request id is required.',400)
        with self.db() as db:
            old=db.execute('SELECT * FROM requests WHERE id=?',(value['requestId'],)).fetchone()
        if old:
            if old['signature']!=digest([operation,value]):raise JuneError('request-conflict','This request id was already used.',409)
            return json.loads(old['response'])
        return None

    def settings(self):
        with self.db() as db:
            return self.envelope(settings=json.loads(db.execute('SELECT document FROM settings WHERE id=1').fetchone()[0]))

    async def settings_update(self, value):
        if not isinstance(value, dict) or set(value)-{'requestId','revision','weather','music','briefing'}:
            raise JuneError('invalid-assistant', 'Send only the settings shown in Daily.', 400)
        replay=self._replay(value,'settings')
        if replay is not None:return self.envelope(**replay)
        playlist = None
        if 'music' in value:
            part = value['music']
            if not isinstance(part, dict) or set(part) != {'playlistId'}:
                raise JuneError('invalid-assistant', 'Choose a playlist from Apple Music.', 400)
            if part['playlistId'] is not None:
                items = (await self.playlists())['playlists']
                playlist = next((p for p in items if p['id'] == part['playlistId']), None)
                if playlist is None:
                    raise JuneError('invalid-assistant', 'That playlist is no longer available.', 409)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            def update():
                settings = json.loads(db.execute('SELECT document FROM settings WHERE id=1').fetchone()[0])
                if type(value.get('revision')) is not int or value['revision'] != settings['revision']:
                    raise JuneError('assistant-stale', 'Settings changed. Refresh and review them again.', 409)
                if 'weather' in value:
                    part = value['weather']
                    if not isinstance(part, dict) or not part or set(part)-{'placeId','units'}:
                        raise JuneError('invalid-assistant', 'Choose a city and temperature units.', 400)
                    if 'units' in part:
                        if part['units'] not in ('metric','imperial'):
                            raise JuneError('invalid-assistant', 'Choose metric or imperial units.', 400)
                        settings['weather']['units'] = part['units']
                    if 'placeId' in part:
                        saved = self.place_cache.get(part['placeId']) if isinstance(part['placeId'],str) else None
                        if not saved or saved[0] <= self.clock():
                            raise JuneError('invalid-assistant', 'Search for the city again before saving it.', 409)
                        settings['weather']['place'] = {k:v for k,v in saved[1].items() if k != 'id'}
                if 'music' in value:
                    settings['music']['playlist'] = playlist
                if 'briefing' in value:
                    part = value['briefing']
                    sections = part.get('sections') if isinstance(part,dict) else None
                    if not isinstance(part,dict) or set(part) != {'sections'} or not isinstance(sections,list) or not 1 <= len(sections) <= 3 or any(s not in ('weather','calendar','goals') for s in sections) or len(set(sections)) != len(sections):
                        raise JuneError('invalid-assistant', 'Choose weather, calendar or goals once each.', 400)
                    settings['briefing']['sections'] = sections
                settings['revision'] += 1
                db.execute('UPDATE settings SET document=? WHERE id=1', (encoded(settings),))
                return dict(settings=settings)
            result = self._request(db, value, 'settings', update)
        self.weather_cache = None
        return self.envelope(**result)

    async def enable(self, key, active, value):
        if key not in ('open-meteo','apple-music','apple-calendar') or set(value) != {'requestId'}:
            raise JuneError('invalid-assistant', 'Use this service’s setup controls.', 400)
        async with self.connection_lock:
            if self._replay(value,['connection',key,active]) is not None:
                return self.envelope(connection=self.connection(key))
            if key == 'apple-music' and active:
                if self.music is None:
                    raise JuneError('music-unavailable', 'The Apple Music helper is not ready.', 503)
                await self.music.permission()
            if key == 'apple-calendar' and active:
                if self.calendar is None:
                    raise JuneError('calendar-unavailable', 'The Apple Calendar helper is not ready.', 503)
                await self.calendar.permission()
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                def change():
                    local = key in ('apple-music','apple-calendar')
                    meta = dict(enabled=active, state='connected' if active and local else 'not-configured',
                        checkedAt=round(self.clock()*1000) if active and local else None,
                        message='Apple Music permission verified. Choose a playlist.' if active and key == 'apple-music'
                            else 'Calendar permission verified. June reads today’s events only when you ask for a briefing.' if active and key == 'apple-calendar'
                            else 'Weather access enabled. Choose a city.' if active else 'Service access is disabled.')
                    db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)', (key, encoded(meta)))
                    return {'connection': meta}
                self._request(db, value, ['connection',key,active], change)
        if not active:
            self.weather_cache = None; self.place_cache.clear()
        return self.envelope(connection=self.connection(key))

    def goals(self):
        with self.db() as db:
            items = [json.loads(r[0]) for r in db.execute('SELECT document FROM goals WHERE deleted=0 ORDER BY rowid DESC LIMIT 200')]
        return self.envelope(goals=items)

    def goal_create(self, value):
        if not isinstance(value,dict) or set(value) != {'requestId','text'} or not clean_text(value.get('text'),200):
            raise JuneError('invalid-goal', 'Write a goal of 1 to 200 characters.', 400)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            def create():
                items = [json.loads(r[0]) for r in db.execute('SELECT document FROM goals WHERE deleted=0')]
                if sum(g['status']=='active' for g in items) >= 20 or len(items) >= 100:
                    raise JuneError('goal-limit', 'Complete or remove an existing goal first.', 409)
                goal = dict(id=uuid.uuid4().hex,text=value['text'].strip(),status='active',revision=1,createdAt=round(self.clock()*1000),doneAt=None)
                db.execute('INSERT INTO goals(id,document) VALUES(?,?)', (goal['id'],encoded(goal)))
                return dict(goal=goal)
            result = self._request(db,value,'goal-create',create)
        return self.envelope(**result)

    def goal_change(self, gid, operation, value):
        expected = {'requestId','revision'} | ({'text'} if operation=='update' else set())
        if not isinstance(value,dict) or set(value) != expected or operation not in ('update','complete','reopen','delete'):
            raise JuneError('invalid-goal', 'Use the goal’s current edit controls.', 400)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            def change():
                row = db.execute('SELECT * FROM goals WHERE id=? AND deleted=0',(gid,)).fetchone()
                if not row:raise JuneError('goal-missing','This goal is no longer available.',404)
                goal = json.loads(row['document'])
                if type(value.get('revision')) is not int or value['revision'] != goal['revision']:
                    raise JuneError('goal-stale','This goal changed. Refresh before editing.',409)
                if operation=='delete':
                    db.execute('UPDATE goals SET deleted=1 WHERE id=?',(gid,));return dict(deleted=True)
                if operation=='update':
                    if not clean_text(value.get('text'),200):raise JuneError('invalid-goal','Write a goal of 1 to 200 characters.',400)
                    goal['text']=value['text'].strip()
                elif operation=='complete':goal.update(status='done',doneAt=round(self.clock()*1000))
                else:
                    count=sum(json.loads(r[0])['status']=='active' for r in db.execute('SELECT document FROM goals WHERE deleted=0'))
                    if goal['status']!='active' and count>=20:raise JuneError('goal-limit','Complete another goal first.',409)
                    goal.update(status='active',doneAt=None)
                goal['revision']+=1
                db.execute('UPDATE goals SET document=? WHERE id=?',(encoded(goal),gid));return dict(goal=goal)
            result=self._request(db,value,['goal',gid,operation],change)
        return self.envelope(**result)

    async def places(self, value):
        if not self.enabled('open-meteo'):raise JuneError('connector-disabled','Enable Weather before searching for a city.',403)
        if not isinstance(value,dict) or set(value) != {'requestId','query'} or not clean_text(value.get('query'),80) or len(value['query'].strip())<2:
            raise JuneError('invalid-place','Enter a city name of 2 to 80 characters.',400)
        result = await self.weather_http.json('GET','https://geocoding-api.open-meteo.com/v1/search?'+urlencode(dict(name=value['query'].strip(),count=8,language='en',format='json')))
        if not self.enabled('open-meteo'):raise JuneError('connector-disabled','Weather was disabled.',403)
        items=[]
        rows=result.get('results',[]) if isinstance(result,dict) else None
        if not isinstance(rows,list):raise JuneError('weather-invalid','The city service returned an invalid list.',502)
        for row in rows[:8]:
            if not isinstance(row,dict) or not clean_text(row.get('name'),100):continue
            lat,lon=row.get('latitude'),row.get('longitude')
            if type(lat) not in (int,float) or type(lon) not in (int,float) or not -90<=lat<=90 or not -180<=lon<=180:continue
            try:ZoneInfo(row['timezone'])
            except (KeyError,ValueError,TypeError):continue
            if not clean_text(row.get('country'),80):continue
            place=dict(id=uuid.uuid4().hex,name=row['name'],region=str(row.get('admin1',''))[:100],country=row['country'],latitude=lat,longitude=lon,timeZone=row['timezone'])
            items.append(place)
        self.place_cache={k:v for k,v in self.place_cache.items() if v[0]>self.clock()}
        if len(self.place_cache)>128:self.place_cache.clear()
        self.place_cache.update({p['id']:(self.clock()+600,p) for p in items})
        self.set_meta('open-meteo',dict(enabled=True,state='connected',checkedAt=round(self.clock()*1000),message='Weather service verified. Forecasts use your selected city.'))
        return self.envelope(places=items)

    def music_voice(self):
        """Whether the person approved music controls and library playback without a card."""
        return self.meta('apple-music').get('voice') is True and self.enabled('apple-music')

    def set_music_voice(self, value):
        meta = self.meta('apple-music')
        if meta:
            self.set_meta('apple-music', {**meta, 'voice': bool(value)})

    async def weather_chat(self, question):
        """The current temperature for the chosen city, from the weather source. Never a model guess."""
        place = weather_intent(question)
        if place is None:
            return None
        settings = self.settings()['settings']
        chosen = settings['weather']['place']
        if not chosen or not self.enabled('open-meteo'):
            return dict(reply='Weather isn’t set up yet. Open Systems → Daily → Weather, enable it and choose your city.')
        if place and place not in chosen['name'].lower():
            return dict(reply=f'I can only check the weather for your chosen city, {chosen["name"]}. Change the city in Systems → Daily → Weather to check {place.title()}.')
        try:
            section = await self._weather(settings)
        except JuneError as failure:
            return dict(reply=failure.message)
        if section.get('status') != 'ok' or not section.get('items'):
            return dict(reply=section.get('message') or 'The weather could not be checked just now.')
        return dict(reply=section['items'][0]['text'] + ' That is the current temperature; I don’t have a forecast.')

    async def music_chat(self, question, request_key):
        """An app-owned reply to a music request, always through a reviewed plan and a checked result.
        Returns None when the words are not a request about music."""
        command = music_command(question)
        if command is None:
            return None
        if not self.enabled('apple-music') or self.music is None:
            return dict(reply='Apple Music isn’t set up yet. Open Systems → Daily → Apple Music, click Allow June to control Music, then choose your playlist. Nothing was played or changed.')
        plans = getattr(self, 'plans', None)
        if plans is None:
            return dict(reply='June’s plan service is unavailable, so nothing was played or changed.')
        if command[0] == 'status':
            # A read: nothing is changed, so no plan is needed.
            try:
                now = await self.music.control('status')
            except JuneError as failure:
                return dict(reply=failure.message)
            song = now['track'] + (' by ' + now['artist'] if now['artist'] else '') if now['track'] else ''
            if now['state'] == 'playing' and song:
                return dict(reply=f'Music is playing {song}.')
            if now['state'] == 'paused' and song:
                return dict(reply=f'Music is paused on {song}.')
            return dict(reply='Nothing is playing in Music right now.')
        playlist = self.settings()['settings']['music']['playlist']
        saved = playlist['name'].strip().casefold() if playlist else None
        if command[0] == 'library' and command[1] == saved:
            command = ('playlist', command[1], True)
        if command[0] == 'playlist':
            name = command[1]
            if not playlist:
                return dict(reply='Choose your playlist first in Systems → Daily → Apple Music. Nothing was played.')
            if name not in GENERIC_MUSIC_NAMES and name != saved:
                return dict(reply=f'Your chosen playlist is {playlist["name"]}. To play {name.title()}, choose it in Systems → Daily → Apple Music first. Nothing was played.')
            request = {'requestId': request_key, 'intent': 'play-playlist'}
            waiting = f'I’ve prepared a plan to play {playlist["name"]} in Apple Music. Approve it on the card below. Tick “Don’t ask again” if you’d like me to play it by voice next time.'
            unsure = f'I couldn’t confirm that Music is playing {playlist["name"]}. Check Music before asking again.'
        elif command[0] == 'control':
            request = {'requestId': request_key, 'intent': 'music-control', 'input': {'op': command[1]}}
            waiting = 'I’ve prepared that music control. Approve it on the card below. Tick “Don’t ask again” to let me control music and play from your library by voice.'
            unsure = 'I couldn’t confirm what Music did. Check Music before asking again.'
        else:
            _, query, what = command
            from .music_tools import valid_query
            if not valid_query(query):
                return None
            try:
                found = await self.music.find(query, what)
            except JuneError as failure:
                return dict(reply=failure.message + ' Nothing was played.')
            if not found:
                return dict(reply=f'{query.title()} isn’t in your Music library or playlists. Add it in the Music app first. Nothing was played.')
            request = {'requestId': request_key, 'intent': 'music-library', 'input': {'query': query, 'what': found['kind']}}
            name = query.title() if found['kind'] == 'artist' else found['label']
            waiting = f'I found {found["count"]} song{"" if found["count"] == 1 else "s"} for {name} in your music. Approve the card below to play. Tick “Don’t ask again” to let me control music and play from your library by voice.'
            unsure = f'I couldn’t confirm that Music is playing {name}. Check Music before asking again.'
        await plans.readiness()
        try:
            reply = await plans.propose(request)
        except JuneError as failure:
            return dict(reply=failure.message + ' Nothing was played or changed.')
        plan = reply['plan']
        if plan['status'] == 'proposed':
            return dict(plan=plan, serverNow=reply['serverNow'], reply=waiting)
        # A remembered approval runs straight away: report the checked outcome, never a guess.
        for _ in range(62):
            if plan['status'] not in ('approved', 'running'):
                break
            await asyncio.sleep(0.5)
            reply = await plans.get(plan['id']); plan = reply['plan']
        results = [s.get('result') for s in plan['steps'] if s.get('result')]
        text = results[-1]['message'] if results and (plan['status'] == 'completed' or not results[-1]['verified']) else unsure
        return dict(plan=plan, serverNow=reply['serverNow'], reply=text)

    async def playlists(self):
        if not self.enabled('apple-music') or self.music is None:
            raise JuneError('automation-permission','Enable Apple Music in Daily before reading playlists.',403)
        return self.envelope(playlists=await self.music.playlists())

    async def _weather(self, settings):
        place=settings['weather']['place']
        if not place or not self.enabled('open-meteo'):
            return dict(kind='weather',title='Weather',status='not-configured',message='Enable Weather and choose a city in Daily.',items=[])
        key=digest(settings['weather'])
        if self.weather_cache and self.weather_cache[0]>self.clock() and self.weather_cache[1]==key:
            return deepcopy(self.weather_cache[2])
        units=settings['weather']['units']
        result=await self.weather_http.json('GET','https://api.open-meteo.com/v1/forecast?'+urlencode(dict(latitude=place['latitude'],longitude=place['longitude'],current='temperature_2m,weather_code',temperature_unit='celsius' if units=='metric' else 'fahrenheit',timezone=place['timeZone'])))
        if not self.enabled('open-meteo'):raise JuneError('connector-disabled','Weather was disabled.',403)
        current=result.get('current') if isinstance(result,dict) else None
        temperature=current.get('temperature_2m') if isinstance(current,dict) else None
        if type(temperature) not in (int,float) or not math.isfinite(temperature) or not -150<=temperature<=200:
            raise JuneError('weather-invalid','Weather returned an invalid temperature.',502)
        text=f"{place['name']}: {temperature:g} degrees {'Celsius' if units=='metric' else 'Fahrenheit'}."
        section=dict(kind='weather',title='Weather',status='ok',items=[dict(text=text)])
        self.weather_cache=(self.clock()+600,key,section)
        self.set_meta('open-meteo',dict(enabled=True,state='connected',checkedAt=round(self.clock()*1000),message='Weather verified for your selected city.'))
        return section

    async def today(self):
        """Today's Calendar events for the notice shown when the page opens. Reads only; never prompts."""
        day = datetime.fromtimestamp(self.clock(), ZoneInfo(self.zone_name())).date().isoformat()
        if not self.enabled('apple-calendar') or self.calendar is None:
            return self.envelope(today=dict(date=day, status='not-configured', items=[]))
        try:
            items = await self._apple_events(self.settings()['settings'])
        except JuneError:
            return self.envelope(today=dict(date=day, status='unavailable', items=[]))
        return self.envelope(today=dict(date=day, status='ok', items=[item['text'] for item in items][:20]))

    def calendar_lost(self):
        """macOS withdrew the Calendar grant (it does after the helper is rebuilt). Say so, and let Daily offer Allow again."""
        self.set_meta('apple-calendar', dict(enabled=False, state='not-configured', checkedAt=round(self.clock()*1000),
            message='macOS no longer allows June Calendar. Click Allow June to read Calendar again.'))

    def zone_name(self):
        place = self.settings()['settings']['weather']['place']
        return place['timeZone'] if place else 'Asia/Kolkata'

    async def event_chat(self, question, request_key):
        """"Add an event tomorrow at 5 PM called Dentist": one reviewed plan, or one question. Never adds by itself."""
        from .calendar_events import event_request, when_phrase
        event = event_request(question, self.clock(), self.zone_name())
        if event is None:
            return None
        if 'ask' in event:
            return dict(reply=event['ask'])
        if not self.enabled('apple-calendar') or self.calendar is None:
            return dict(reply='Calendar isn’t allowed yet. Open Systems → Daily → Calendar and click Allow June to read Calendar. Nothing was added.')
        plans = getattr(self, 'plans', None)
        if plans is None:
            return dict(reply='June’s plan service is unavailable, so nothing was added.')
        await plans.readiness()
        try:
            reply = await plans.propose({'requestId': request_key, 'intent': 'calendar-add', 'input': event})
        except JuneError as failure:
            return dict(reply=failure.message + ' Nothing was added.')
        return dict(plan=reply['plan'], serverNow=reply['serverNow'],
                    reply=f'I’ve prepared “{event["title"]}” for {when_phrase(event, self.zone_name())}. Check the card below and approve it to add it to your Calendar.')

    async def agenda_chat(self, question, reminders=None):
        """Today's or tomorrow's Calendar events (and June's reminders when asked), read from their sources."""
        intent = agenda_intent(question)
        if intent is None:
            return None
        day, with_reminders = intent
        word = 'tomorrow' if day else 'today'
        settings = self.settings()['settings']
        parts = []
        if not self.enabled('apple-calendar') or self.calendar is None:
            parts.append('Calendar isn’t allowed yet. Open Systems → Daily → Calendar and click Allow June to read Calendar.')
        else:
            try:
                items = await self._apple_events(settings, day)
                parts.append(f'On your calendar {word}: ' + ' '.join(item['text'] for item in items) if items else f'Nothing is on your calendar {word}.')
            except JuneError as failure:
                parts.append(failure.message)
        if with_reminders and reminders is not None:
            place = settings['weather']['place']
            zone = ZoneInfo(place['timeZone'] if place else 'Asia/Kolkata')
            start = datetime.fromtimestamp(self.clock(), zone).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() + day * 86400
            due = sorted((r for r in (await reminders.state())['reminders'] if r['status'] == 'active' and start <= r['dueAt'] / 1000 < start + 86400), key=lambda r: r['dueAt'])
            if due:
                parts.append(f'Reminders {word}: ' + '; '.join(r['text'] + ' at ' + datetime.fromtimestamp(r['dueAt'] / 1000, zone).strftime('%I:%M %p').lstrip('0') for r in due[:10]) + '.')
            else:
                parts.append(f'No reminders are scheduled for {word}.')
        return dict(reply=' '.join(parts))

    async def _apple_events(self, settings, day=0):
        """One day's events from the Mac's Calendar, as app-built lines; unsafe titles are dropped."""
        place = settings['weather']['place']
        zone = ZoneInfo(place['timeZone'] if place else 'Asia/Kolkata')
        start = datetime.fromtimestamp(self.clock(), zone).replace(hour=0, minute=0, second=0, microsecond=0)
        start = datetime.fromtimestamp(start.timestamp() + day * 86400, zone)
        try:
            rows = await self.calendar.events(start.timestamp(), start.timestamp() + 86400)
        except JuneError as failure:
            if failure.code == 'calendar-permission': self.calendar_lost()
            raise
        items = []
        for row in sorted(rows, key=lambda r: (not r['allDay'], r['start']))[:20]:
            title = row['title'].strip()
            if not clean_text(title, 300): continue
            if len(title) > 260: title = title[:259] + '…'
            if row['allDay']:
                items.append(dict(text='All day: ' + title + '.', allDay=True))
            else:
                moment = datetime.fromtimestamp(row['start'], zone)
                items.append(dict(text=f"{moment.strftime('%H:%M')}: {title}.", at=round(row['start'] * 1000), allDay=False))
        self.set_meta('apple-calendar', dict(enabled=True, state='connected', checkedAt=round(self.clock()*1000), message='Calendar read for your briefing. Nothing left this Mac.'))
        return items

    async def briefing(self):
        settings=self.settings()['settings'];sections=[]
        for kind in settings['briefing']['sections']:
            try:
                if kind=='weather':section=await self._weather(settings)
                elif kind=='calendar':
                    if self.enabled('apple-calendar') and self.calendar is not None:
                        section=dict(kind=kind,title='Calendar',status='ok',items=await self._apple_events(settings))
                    elif self.google is not None and self.meta('google').get('state')=='connected':
                        section=dict(kind=kind,title='Calendar',status='ok',items=await self.google.events())
                    else:
                        section=dict(kind=kind,title='Calendar',status='not-configured',message='Allow June to read Calendar in Daily.',items=[])
                else:
                    goals=[g for g in self.goals()['goals'] if g['status']=='active']
                    section=dict(kind=kind,title='Goals',status='ok',items=[dict(text=g['text']) for g in goals[:20]])
            except (JuneError,ValueError,KeyError,TypeError):
                section=dict(kind=kind,title=kind.title(),status='unavailable',message=f'{kind.title()} is unavailable. Check its connection in Daily.',items=[])
            sections.append(section)
        sentences=['Here is your briefing.']
        for section in sections:
            if section['status']!='ok':sentences.append(section['message'])
            elif not section['items']:sentences.append('No active goals.' if section['kind']=='goals' else 'No calendar events today.')
            else:
                sentences.append(section['title']+'.')
                for item in section['items'][:3]:
                    sentence=item['text']
                    if len(' '.join(sentences))+len(sentence)<1100:sentences.append(sentence)
        return self.envelope(briefing=dict(id=uuid.uuid4().hex,generatedAt=round(self.clock()*1000),sections=sections,spoken=' '.join(sentences)[:1200]))
