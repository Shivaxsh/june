"""Private application memory. SQLite is authoritative; model output never approves it."""
from contextlib import contextmanager
from pathlib import Path
import json
import os
import re
import sqlite3
import time
import uuid
from .errors import JuneError
from .app_info import recall_field, recall_fields, fact_fields, nonliteral_request

FIELDS = ('who', 'values', 'speech', 'humour', 'quirks', 'taste', 'never', 'address', 'mood', 'growth')
EXPRESSIONS = {'steady': .98, 'calm': .92, 'bright': 1.04}
RETENTION = 30 * 86400
SECRET = re.compile(r'\b(password|passcode|api.?key|secret|token|otp|cvv|pin|pin code|credit card|bank account)\b|sk-[\w-]+|\b\d{12,19}\b', re.I)
FICTION = re.compile(r'\b(fictional|pretend|role.?play|hypothetical|imagine|made.up|for (?:a |an )?(?:story|exercise|scenario))\b', re.I)
PROPOSAL_OPT_OUT = re.compile(
    r'(?:^|[.!?;:,\n]|\b(?:and|but))\s*(?:please\s+)?'
    r'(?:(?:do\s+not|don[\'’]t|never)\s+(?:save|store|remember)\b|forget\s+(?:this|that|it)\b)', re.I)
PROPOSAL_ATTRIBUTION = re.compile(
    r'\b(?:said|says|wrote|writes|told me|quoted)(?:\s+the following)?\s*[:"\'“‘]'
    r'|\b(?:example|sample|quote|quotation|excerpt|transcript|message|email|note|text)\s*:'
    r'|^\s*(?:>|```|["\'“‘])', re.I | re.M)
TRANSIENT_QUESTION = re.compile(r'^I am (?:currently )?asking\b', re.I)


def exclude_proposals(user_text):
    """Conservatively exclude a whole message before either extraction path.

    Quoted or attributed prose has ambiguous ownership even across newlines.
    Opt-outs are commands, not a blanket ban on ordinary contractions.
    """
    return bool(SECRET.search(user_text) or FICTION.search(user_text)
                or PROPOSAL_OPT_OUT.search(user_text) or PROPOSAL_ATTRIBUTION.search(user_text)
                or re.search(r'\b(?:ignore|disregard|override)\b', user_text, re.I))

def invalid(message='This data is invalid. Review it before saving.', status=400):
    return JuneError('invalid-data', message, status)

def text(value, maximum=500):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise invalid()
    try: value.encode("utf-8")
    except UnicodeError: raise invalid("Text contains invalid Unicode.")
    return value.strip()

def fingerprint(value):
    return ' '.join(re.findall(r'\w+', value.casefold()))

def key(value):
    # Conservative conflicts for explicit "my X is Y" and preference statements.
    match = re.match(r'((?:my|our) .{1,60}?) (?:is|are|uses?|=)\s+|((?:i|we) (?:prefer|live in|work at|use))\s+', value.casefold())
    return (match.group(1) or match.group(2)) if match else None

def profile_defaults():
    return {'fields': dict(zip(FIELDS, (
        'June, a personal assistant with honest capability limits.',
        'Accuracy, privacy, useful help and user control.',
        'Warm, concise and practical. Usually one or two short sentences.',
        'Light humour when welcome; never at the user’s expense.',
        '', '', 'Never invent user facts or claim actions that did not happen.',
        '', 'Steady and attentive.', 'Improve through reviewed feedback; do not claim to learn permanently from a chat.'))), 'expression': 'steady'}

def validate_profile(value):
    if not isinstance(value, dict) or value.get('expression', 'steady') not in ('steady','calm','bright') or not isinstance(value.get('fields'), dict):
        raise invalid('Choose a valid expression and ten character fields.')
    if set(value['fields']) - set(FIELDS): raise invalid('Unknown character field.')
    fields = {}
    for name in FIELDS:
        item = value['fields'].get(name, '')
        if not isinstance(item, str) or len(item) > 500: raise invalid('Each character field must contain at most 500 characters.')
        if item: text(item, 500)
        fields[name] = item.strip()
    return {'fields': fields, 'expression': value.get('expression', 'steady')}

def validate_candidates(items, user_text):
    if not isinstance(items, list) or exclude_proposals(user_text): return []
    valid = []
    for item in items[:3]:
        try:
            fact, quote = text(item['text']), text(item['quote'], 1000)
            # Exact clauses only: no inference from job titles, assistant text or paraphrase.
            if quote not in user_text or fact not in quote or SECRET.search(fact + ' ' + quote) or FICTION.search(fact): continue
            if TRANSIENT_QUESTION.search(fact): continue
            if not re.search(r'\b(?:my|i|we|our)\b', fact, re.I): continue
            if not re.search(r'\b(?:is|am|are|prefer|like|live|work|use|want|need|building|learning|name)\b', fact, re.I): continue
            valid.append({'text': fact, 'quote': quote})
        except (KeyError, TypeError, JuneError): continue
    return valid


def _explicit_sentences(user_text):
    start = 0
    for boundary in re.finditer(r'(?<=[.!?])\s+|\n|;\s*', user_text):
        sentence = user_text[start:boundary.start()]
        # Keep honorifics, place abbreviations and initials inside the exact
        # source slice. Never rewrite punctuation to shield it from splitting.
        if ('\n' not in boundary.group() and sentence.endswith('.')
                and not re.match(r'(?:my|I)\b', user_text[boundary.end():], re.I)):
            token = sentence.rsplit(None, 1)[-1]
            if re.fullmatch(r'(?:Dr|Mr|Mrs|Ms|Prof|St|Jr|Sr)\.', token, re.I) or re.fullmatch(r'(?:[A-Z]\.)+', token):
                continue
        yield sentence
        start = boundary.end()
    yield user_text[start:]


def explicit_candidates(user_text):
    """Quote clear first-person facts without waiting for an inference job.

    These are pending proposals, never automatic approvals. Ambiguous prose
    remains the model extractor's job and is still subject to quote validation.
    """
    if exclude_proposals(user_text):
        return []
    candidates = []
    for sentence in _explicit_sentences(user_text):
        if '?' in sentence:
            continue
        for part in re.split(r'\s+and\s+(?=(?:my|I)\b)|,\s*(?=(?:my|I)\b)', sentence, flags=re.I):
            clause = re.sub(r'^(?:(?:okay|ok|so|well|also|please|remember(?: that)?)\b[\s,:]*)+', '', part.strip(), flags=re.I).strip(' ,.;:')
            if re.search(r'\b(?:if|maybe|might|would|could|should|not)\b', clause, re.I):
                continue
            if re.match(r'(?:my (?:name|background|project|favourite colou?r|favorite colou?r) (?:is|are)\b|I (?:am|live in|work at|work as|prefer|like|use)\b)', clause, re.I):
                candidates.append({'text': clause, 'quote': clause})
    return validate_candidates(candidates, user_text)

def validate_import(value):
    if not isinstance(value, dict) or value.get('version') != 1: raise invalid('Unsupported June export version.')
    if value.get('format') == 'building-june-backup':
        character = value.get('character')
        if not isinstance(character, dict): raise invalid('This progress export has no workshop answers.')
        return {'memories': [], 'profile': validate_profile({'fields': {k:v for k,v in character.items() if k in FIELDS}, 'expression':'steady'}), 'conversations': []}
    if value.get('format') != 'june-data': raise invalid('Choose a June data or progress export.')
    facts = value.get('memories', [])
    if not isinstance(facts, list) or len(facts) > 500: raise invalid('Import at most 500 memories.')
    if not all(isinstance(x,dict) for x in facts): raise invalid()
    facts = [{'text': text(x.get('text')), 'pinned': x.get('pinned') is True} for x in facts]
    profile = validate_profile(value['profile']) if value.get('profile') is not None else None
    chats = value.get('conversations', [])
    if not isinstance(chats, list) or len(chats) > 500: raise invalid('Import at most 500 conversations at a time.')
    checked = []
    for chat in chats:
        if not isinstance(chat, dict) or not isinstance(chat.get('turns'), list) or len(chat['turns']) > 500: raise invalid()
        turns = []
        for turn in chat['turns']:
            if not isinstance(turn, dict) or turn.get('status') not in ('complete','stopped','failed'): raise invalid()
            turns.append({'user':text(turn.get('user'),2000), 'assistant':text(turn.get('assistant') or '(No reply)',10000), 'status':turn['status']})
        checked.append({'title':text(chat.get('title'),100), 'turns': turns})
    return {'memories':facts, 'profile':profile, 'conversations':checked}

class Store:
    def __init__(self, directory, clock=time.time):
        self.directory, self.clock = Path(directory).expanduser(), clock
        self.path = self.directory / 'june.sqlite3'
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.directory, 0o700)
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            os.chmod(self.path, 0o600)
            with self.db() as db:
                version = db.execute('PRAGMA user_version').fetchone()[0]
                if version > 1: raise invalid('This database needs a newer June version.', 503)
                if version == 0:
                    db.executescript('''
CREATE TABLE meta (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL);
INSERT INTO meta VALUES (1,0);
CREATE TABLE conversations (id TEXT PRIMARY KEY,title TEXT NOT NULL,updated REAL NOT NULL);
CREATE TABLE turns (id TEXT PRIMARY KEY,conversation TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,user TEXT NOT NULL,assistant TEXT NOT NULL DEFAULT '',status TEXT NOT NULL,revision INTEGER NOT NULL,created REAL NOT NULL,memories TEXT NOT NULL DEFAULT '[]');
CREATE INDEX turns_chat ON turns(conversation,created);
CREATE TABLE memories (id TEXT PRIMARY KEY,text TEXT NOT NULL,fingerprint TEXT NOT NULL UNIQUE,pinned INTEGER NOT NULL,source TEXT REFERENCES conversations(id) ON DELETE SET NULL,created REAL NOT NULL);
CREATE TABLE suggestions (id TEXT PRIMARY KEY,conversation TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,turn TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,text TEXT NOT NULL,quote TEXT NOT NULL,fingerprint TEXT NOT NULL,status TEXT NOT NULL,UNIQUE(conversation,fingerprint));
CREATE TABLE profile (id INTEGER PRIMARY KEY CHECK(id=1),value TEXT NOT NULL);
PRAGMA user_version=1;
''')
                    db.execute('INSERT INTO profile VALUES(1,?)', (json.dumps(profile_defaults()),))
                # A process restart cannot complete a previously running reply.
                db.execute("UPDATE turns SET status='stopped' WHERE status='pending'")
            self.cleanup()
        except (OSError, sqlite3.Error) as e:
            raise JuneError('storage', 'June cannot open private storage. Check the data folder permissions or choose temporary chat.', 503) from e

    @contextmanager
    def db(self):
        try:
            with sqlite3.connect(self.path, timeout=3) as db:
                db.row_factory = sqlite3.Row
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('PRAGMA secure_delete=ON')
                yield db
        except sqlite3.Error as e:
            raise JuneError('storage', 'Private storage failed. Nothing was confirmed saved. Retry or explicitly choose temporary chat.', 503) from e

    def cleanup(self):
        with self.db() as db: db.execute('DELETE FROM conversations WHERE updated<=?', (self.clock()-RETENTION,))
    def revision(self):
        with self.db() as db: return db.execute('SELECT revision FROM meta').fetchone()[0]
    def reset(self, db):
        db.execute('UPDATE meta SET revision=revision+1')
        db.execute("UPDATE suggestions SET status='cancelled' WHERE status='pending'")
    def create_conversation(self, title='New conversation'):
        c = {'id':str(uuid.uuid4()), 'title':text(title,100), 'updated':self.clock()}
        with self.db() as db: db.execute('INSERT INTO conversations VALUES(:id,:title,:updated)', c)
        return c
    def conversation(self, cid):
        self.cleanup()
        with self.db() as db:
            c = db.execute('SELECT * FROM conversations WHERE id=?',(cid,)).fetchone()
            if not c: raise invalid('This chat was deleted or expired.',404)
            return {**dict(c), 'turns':[dict(x) for x in db.execute('SELECT * FROM turns WHERE conversation=? ORDER BY created,rowid',(cid,))]}
    def delete_conversation(self, cid=None):
        with self.db() as db:
            if cid: db.execute('DELETE FROM conversations WHERE id=?',(cid,))
            else: db.execute('DELETE FROM conversations')
            self.reset(db)
    def start_turn(self, cid, tid, content, revision, memories=()):
        self.conversation(cid)
        with self.db() as db:
            if revision != db.execute('SELECT revision FROM meta').fetchone()[0]: raise invalid('Memory changed. Please send this question again.',409)
            if db.execute('SELECT 1 FROM turns WHERE id=?',(tid,)).fetchone(): raise invalid('This turn was already submitted. Reopen the saved chat.',409)
            db.execute('INSERT INTO turns(id,conversation,user,status,revision,created,memories) VALUES(?,?,?,?,?,?,?)',(tid,cid,text(content,2000),'pending',revision,self.clock(),json.dumps([x['id'] for x in memories])))
            db.execute("UPDATE conversations SET title=CASE WHEN title='New conversation' THEN ? ELSE title END,updated=? WHERE id=?",(content[:90],self.clock(),cid))
    def finish_turn(self, tid, content, status, propose=False):
        with self.db() as db:
            changed=db.execute("UPDATE turns SET assistant=?,status=? WHERE id=? AND status='pending'",(content,status,tid)).rowcount
            db.execute('UPDATE conversations SET updated=? WHERE id=(SELECT conversation FROM turns WHERE id=?)',(self.clock(),tid))
            if changed and status=='complete' and propose:
                turn=db.execute('SELECT * FROM turns WHERE id=?',(tid,)).fetchone()
                sources=' '.join(r[0] for r in db.execute('SELECT user FROM turns WHERE conversation=?',(turn['conversation'],)))
                if not FICTION.search(sources):
                    # Reply and pending proposals commit together. A disk error
                    # cannot leave UI failure paired with a saved complete turn.
                    self._suggest(db,turn['conversation'],tid,explicit_candidates(turn['user']),turn['revision'])
            return bool(changed)
    def context(self,cid):
        chat = self.conversation(cid)
        revision = self.revision()
        turns = [t for t in chat['turns'] if t['status']=='complete' and t['revision']==revision]
        result=[]; size=0
        for t in reversed(turns):
            pair=[{'role':'user','content':t['user']}, {'role':'assistant','content':t['assistant'][:2000]}]
            count=sum(len(x['content'].encode('utf-16-le'))//2 for x in pair)
            if len(result)>=18 or size+count>4000: break
            result=pair+result;size+=count
        # Sliding one pair on every long-chat request changes the start of the
        # prompt every time, defeating the CPU model's reusable prefix cache.
        # Advance in four-turn blocks instead, still within the same hard
        # message/character limits. Between advances, new turns append to an
        # unchanged prefix. Saved history is never removed or summarised.
        earliest = len(turns) - len(result)//2
        start = ((earliest + 3)//4)*4
        if start >= len(turns): start = earliest
        return result[(start-earliest)*2:]
    def snapshot(self, search=''):
        self.cleanup()
        with self.db() as db:
            chats=[dict(x) for x in db.execute('SELECT * FROM conversations WHERE title LIKE ? OR id IN (SELECT conversation FROM turns WHERE user LIKE ? OR assistant LIKE ?) ORDER BY updated DESC LIMIT 100',tuple('%'+search+'%' for _ in range(3)))]
            return {'revision': self.revision(), 'retentionDays':30, 'conversations':chats,
                    'memories':[dict(x) for x in db.execute('SELECT * FROM memories ORDER BY pinned DESC,created DESC')],
                    'suggestions':[dict(x) for x in db.execute("SELECT * FROM suggestions WHERE status='pending' ORDER BY rowid")],
                    'profile':json.loads(db.execute('SELECT value FROM profile WHERE id=1').fetchone()[0])}
    def add_memory(self, fact, pinned=False, source=None, replace=None):
        fact=text(fact)
        if SECRET.search(fact): raise invalid('Do not store credentials or payment details in June memory.')
        with self.db() as db: return self._add(db,fact,pinned,source,replace)
    def _add(self,db,fact,pinned=False,source=None,replace=None):
        existing=db.execute('SELECT * FROM memories WHERE fingerprint=?',(fingerprint(fact),)).fetchone()
        if existing: return dict(existing)
        conflict=next((dict(x) for x in db.execute('SELECT * FROM memories') if key(fact) and key(fact)==key(x['text'])),None)
        if conflict and replace!=conflict['id']: raise invalid('A saved fact may conflict. Review it and explicitly choose the memory to replace.',409)
        if replace:
            if not db.execute('SELECT 1 FROM memories WHERE id=?',(replace,)).fetchone(): raise invalid('The selected memory no longer exists.',409)
            db.execute('DELETE FROM memories WHERE id=?',(replace,));self.reset(db)
        row={'id':str(uuid.uuid4()),'text':fact,'fingerprint':fingerprint(fact),'pinned':int(pinned),'source':source,'created':self.clock()}
        db.execute('INSERT INTO memories VALUES(:id,:text,:fingerprint,:pinned,:source,:created)',row)
        return row
    def edit_memory(self,mid,fact,pinned):
        fact=text(fact)
        if SECRET.search(fact): raise invalid('Do not store credentials.')
        with self.db() as db:
            old=db.execute('SELECT * FROM memories WHERE id=?',(mid,)).fetchone()
            if not old: raise invalid('Memory not found.',404)
            duplicate=db.execute('SELECT id FROM memories WHERE fingerprint=? AND id!=?',(fingerprint(fact),mid)).fetchone()
            if duplicate: raise invalid('That fact is already saved.',409)
            db.execute('UPDATE memories SET text=?,fingerprint=?,pinned=? WHERE id=?',(fact,fingerprint(fact),int(pinned),mid))
            self.reset(db)
    def delete_memory(self,mid):
        with self.db() as db:
            db.execute('DELETE FROM memories WHERE id=?',(mid,));self.reset(db)
    def retrieve(self,query):
        field = recall_field(query)
        # Literal/fictional examples cannot cause personal-data retrieval.
        if nonliteral_request(query):
            return []
        stop = {'what','the','my','is','i','a','an','and','do','you','about','me',
                'can','could','would','will','please','tell','explain','how','to',
                'of','in','it','that','this','for','with','have','am','are'}
        tokens = set(re.findall(r'\w+',query.casefold())) - stop
        facts = self.snapshot()['memories']
        if field and field not in ('details', 'source'):
            requested = set(recall_fields(query))
            facts = [f for f in facts if requested & fact_fields(f['text'])]
        elif field != 'details':
            # Field words in general questions ("name of the capital") are not
            # personal recall. Other topical facts still use lexical relevance.
            reserved = {'name','age','location','city','gender','favorite','favourite','color','colour'}
            tokens -= reserved
            facts = [f for f in facts if tokens & (set(re.findall(r'\w+',f['text'].casefold())) - stop - reserved)]
        facts.sort(key=lambda x:(bool(x['pinned']),len(tokens & set(re.findall(r'\w+',x['text'].casefold()))),x['created']),reverse=True)
        result=[];size=0
        for f in facts:
            if len(result)==8: break
            if size+len(f['text'])<=1600: result.append(f);size+=len(f['text'])
        return result
    def suggest(self,cid,tid,items,revision):
        with self.db() as db:
            self._suggest(db,cid,tid,items,revision)
    def _suggest(self,db,cid,tid,items,revision):
        if revision != db.execute('SELECT revision FROM meta').fetchone()[0]: return
        turn=db.execute("SELECT user FROM turns WHERE id=? AND conversation=? AND status='complete'",(tid,cid)).fetchone()
        if not turn: return
        for item in validate_candidates(items,turn['user']):
            fp=fingerprint(item['text'])
            if db.execute('SELECT 1 FROM memories WHERE fingerprint=?',(fp,)).fetchone():continue
            db.execute("INSERT OR IGNORE INTO suggestions VALUES(?,?,?,?,?,?,'pending')",(str(uuid.uuid4()),cid,tid,item['text'],item['quote'],fp))
    def decide(self,sid,action,fact=None,pinned=False,replace=None):
        with self.db() as db:
            s=db.execute("SELECT * FROM suggestions WHERE id=? AND status='pending'",(sid,)).fetchone()
            if not s: raise invalid('This suggestion is no longer pending.',409)
            if action=='approve':
                fact=text(fact or s['text'])
                if SECRET.search(fact):raise invalid('Do not store credentials.')
                self._add(db,fact,pinned,s['conversation'],replace)
            elif action!='reject': raise invalid()
            db.execute('UPDATE suggestions SET status=? WHERE id=?',(action,sid))
    def save_profile(self,profile):
        value=validate_profile(profile)
        with self.db() as db:
            db.execute('UPDATE profile SET value=? WHERE id=1',(json.dumps(value),));self.reset(db)
    def export(self,chats=False):
        s=self.snapshot()
        with self.db() as db:
            ids=[x[0] for x in db.execute('SELECT id FROM conversations ORDER BY updated DESC')] if chats else []
        conversations=[self.conversation(cid) for cid in ids]
        for chat in conversations:
            for turn in chat['turns']:
                if turn['status']=='pending':turn['status']='stopped'
        return {'format':'june-data','version':1,'memories':s['memories'],'profile':s['profile'], 'conversations':conversations}
    def apply_import(self,value):
        checked=validate_import(value)
        # One transaction: conflicts cannot leave a half-imported database.
        with self.db() as db:
            for f in checked['memories']:
                if SECRET.search(f['text']):raise invalid('Import contains credentials.')
                self._add(db,f['text'],f['pinned'])
            if checked['profile']:db.execute('UPDATE profile SET value=? WHERE id=1',(json.dumps(checked['profile']),))
            for chat in checked['conversations']:
                cid=str(uuid.uuid4())
                db.execute('INSERT INTO conversations VALUES(?,?,?)',(cid,chat['title'],self.clock()))
                for t in chat['turns']:
                    # Imported chats are viewable, never silently admitted as inference history.
                    db.execute('INSERT INTO turns(id,conversation,user,assistant,status,revision,created) VALUES(?,?,?,?,?,-1,?)',(str(uuid.uuid4()),cid,t['user'],t['assistant'],t['status'],self.clock()))
            self.reset(db)
        return checked
