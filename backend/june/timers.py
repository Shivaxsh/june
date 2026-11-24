"""Private, persistent local timers; no model or external account is involved."""
import asyncio,os,re,sqlite3,time,uuid
from pathlib import Path
from contextlib import suppress
from .errors import JuneError
from .app_info import nonliteral_request

ID=re.compile(r'[\w-]{8,128}')
SMALL={'a':1,'an':1,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}

def number(text):
    if text.isdigit():return int(text) if len(text)<7 else 10**6
    words=text.replace('-',' ').split()
    if len(words)==1:return SMALL.get(words[0])
    if len(words)==2 and words[0] in SMALL and SMALL[words[0]]>=20 and words[1] in SMALL and SMALL[words[1]]<10:return SMALL[words[0]]+SMALL[words[1]]
    return None

def duration_phrase(seconds):
    parts=[]
    for size,name in ((3600,'hour'),(60,'minute'),(1,'second')):
        count,seconds=divmod(seconds,size)
        if count:parts.append(f"{count} {name}"+('s' if count!=1 else ''))
    return ' and '.join(parts) or '0 seconds'

TIMER_ASK='I didn’t catch how long. How long should the timer be? For example, say “ten seconds”. No timer was set yet.'
# What speech recognition writes for a spoken number in a noisy room. Used only inside a timer request.
HEARD={'it in':'ten','a tin':'ten','tin':'ten','attend':'ten','tan':'ten','then':'ten','to':'two','too':'two','for':'four','fore':'four',
       'ate':'eight','free':'three','tree':'three','fife':'five','won':'one','sex':'six','nein':'nine'}
_UNIT=r'(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)'

def _heard(duration):
    """Replace a sound-alike that stands where a number belongs: directly before a unit."""
    def fix(match):
        return HEARD[match[1]]+' '+match[2]
    return re.sub(r'\b('+'|'.join(sorted(map(re.escape,HEARD),key=len,reverse=True))+r') ('+_UNIT+r')\b',fix,duration)

def timer_followup(messages):
    """"ten seconds" after June asked how long: the full request to run, else None."""
    if len(messages)<3 or messages[-2].get('role')!='assistant' or messages[-2].get('content')!=TIMER_ASK:return None
    q=messages[-1]['content'].strip().lower().rstrip('.!? ')
    q=re.sub(r' please$','',q)
    q=re.sub(r'^(?:(?:for|make it|set it (?:for|to)|it should be|about) )+','',q)
    if not re.fullmatch(r'[\w -]{1,40} '+_UNIT+r'(?: and [\w -]{1,20} '+_UNIT+r')?',q):return None
    return 'set a timer for '+q

def timer_intent(question):
    if nonliteral_request(question):return None
    q=question.strip().lower().rstrip('.!? ')
    q=re.sub(r'^(?:hey )?june[,!:\s]+','',q)
    q=re.sub(r'^(?:please )?(?:(?:can|could|would) you )?(?:please )?','',q)
    q=re.sub(r'^(?:(?:ok(?:ay)?|so|now|alright)[, ]+)+','',q)
    q=re.sub(r'^(?:hey )?june[,!:\s]+','',q)
    q=re.sub(r' please$','',q).replace('countdown','timer')
    unit=r'(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)'
    # "start a 10 second timer", "15 minute timer", "timer for 2 minutes", "a timer of 90 seconds".
    before=re.fullmatch(r'(?:(?:set|start|create|make|give me|put on) )?(?:me )?(?:a |an |the )?([\w -]*?'+unit+r')[ -]timer(?: for (?:the |my )?([a-z][a-z0-9 _-]{0,40}))?',q)
    after=re.fullmatch(r'(?:(?:set|start|create|make|give me|put on) )?(?:me )?(?:a |an |the )?timer (?:for|of) (.+)',q)
    # "set an alarm for 30 minutes from now", "count down 3 minutes", "time 20 minutes": a countdown timer
    alarm=re.fullmatch(r'(?:set|start) (?:me )?(?:an |a )?alarm (?:for|in) (.+?)(?: from now)?',q) or re.fullmatch(r'count ?down (?:for )?(.+)',q) or re.fullmatch(r'time (\d.*|(?:a|an|one|two|three|four|five|ten|fifteen|twenty|thirty) .+)',q)
    if alarm and re.search(r'\b(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)$',alarm[1]):before=None;after=None;q='set a timer for '+_heard(alarm[1])
    if before:q='set a timer for '+_heard(before[1].replace('-',' '))+(' called '+before[2].strip() if before[2] else '')
    elif after:q='set a timer for '+_heard(after[1])
    start=re.fullmatch(r'(?:set|start|create) (?:a |an |the )?timer(?: for)? (.+)',q)
    if start:
        duration=start[1];label=''
        named=re.fullmatch(r'(.+?) (?:called|named) ([a-z0-9][a-z0-9 _-]{0,79})',duration)
        if named:duration,label=named.groups()
        numeric=r'(?:\d+|(?:'+ '|'.join(sorted(SMALL,key=len,reverse=True))+r')(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?)'
        units=re.finditer('('+numeric+r')\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b',duration)
        total=0;position=0;seen=False
        for match in units:
            if duration[position:match.start()].strip(' ,') not in ('','and'):break
            n=number(match[1])
            if n is None:break
            unit=match[2];total+=n*(3600 if unit.startswith('h') else 60 if unit.startswith('m') else 1)
            position=match.end();seen=True
        if seen and not duration[position:].strip() and 1<=total<=86400:return {'operation':'create','durationSeconds':total,'label':label}
        return {'operation':'invalid','message':TIMER_ASK}
    if re.match(r'^(?:set|start|create) (?:a |an |the )?timer\b',q):return {'operation':'invalid','message':'No timer was set. Include its duration, for example: Set a timer for 10 minutes.'}
    cancel=re.fullmatch(r'(?:cancel|stop|delete) (?:my |the |a )?timer(?: (?:called |named )?([a-z0-9][a-z0-9 _-]{0,79}))?',q)
    alternate=re.fullmatch(r'(?:cancel|stop) (?:my |the )?([a-z0-9][a-z0-9 _-]{0,79}) timer',q)
    if cancel or alternate:return {'operation':'cancel','label':((cancel or alternate)[1] or '').strip()}
    if re.fullmatch(r'(?:(?:show|list)(?: my| the)? timers|what timers (?:are running|do i have)|how (?:much time|long) is left(?: on (?:my|the) timer)?|time left on (?:my|the) timer|is there a timer running|(?:do i have|are there) (?:a timer|any timers)(?: running)?)',q):return {'operation':'list'}
    return None

class Timers:
    def __init__(self,directory,clock=time.time,*,store_name='timers'):
        self.directory=Path(directory)/store_name;self.directory.mkdir(parents=True,exist_ok=True,mode=0o700);self.directory.chmod(0o700)
        self.path=self.directory/(store_name+'.sqlite3');self.clock=clock;self.task=None
        fd=os.open(self.path,os.O_CREAT|os.O_RDWR,0o600);os.close(fd);self.path.chmod(0o600)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS timers(id TEXT PRIMARY KEY,request_id TEXT UNIQUE NOT NULL,label TEXT NOT NULL,duration INTEGER NOT NULL,created REAL NOT NULL,ends REAL NOT NULL,status TEXT NOT NULL,completed REAL,announced REAL,conversation TEXT,turn TEXT)')
            self._settle(db)
    def db(self):
        db=sqlite3.connect(self.path,timeout=3);db.row_factory=sqlite3.Row;return db
    def _settle(self,db):
        now=self.clock()
        db.execute("UPDATE timers SET status='completed',completed=ends WHERE status='active' AND ends<=?",(now,))
        db.execute("DELETE FROM timers WHERE status IN ('cancelled','acknowledged') AND created<?",(now-7*86400,))
    def start(self,interval=1):
        if self.task is not None:return
        async def loop():
            while True:
                try:
                    with self.db() as db:self._settle(db)
                except (sqlite3.Error,OSError):pass  # Next API read reports storage failure; no invented result.
                await asyncio.sleep(interval)
        self.task=asyncio.create_task(loop())
    async def close(self):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):await self.task
            self.task=None
    def _record(self,row):
        value={'id':row['id'],'label':row['label'],'durationSeconds':row['duration'],'createdAt':round(row['created']*1000),'endsAt':round(row['ends']*1000),'status':row['status']}
        if row['completed'] is not None:value['completedAt']=round(row['completed']*1000)
        if row['announced'] is not None:value['announcedAt']=round(row['announced']*1000)
        return value
    def _reply(self,row,**extra):return {'serverNow':round(self.clock()*1000),'timer':self._record(row),**extra}
    def _get(self,db,tid):
        row=db.execute('SELECT * FROM timers WHERE id=?',(tid,)).fetchone()
        if not row:raise JuneError('timer-missing','This timer is no longer available.',404)
        return row
    async def state(self):
        with self.db() as db:
            self._settle(db)
            pending=db.execute("SELECT * FROM timers WHERE status IN ('active','completed')").fetchall()
            recent=db.execute("SELECT * FROM timers WHERE status NOT IN ('active','completed') ORDER BY created DESC,rowid DESC LIMIT 10").fetchall()
        rows=sorted([*pending,*recent],key=lambda r:(r['created'],r['id']),reverse=True)
        return {'serverNow':round(self.clock()*1000),'timers':[self._record(row) for row in rows]}
    async def create(self,value,*,conversation=None,turn=None):
        if not isinstance(value,dict) or not {'durationSeconds','requestId'}<=set(value)<= {'durationSeconds','requestId','label'}:
            raise JuneError('invalid-timer','Choose a duration and a timer request id.',400)
        seconds=value['durationSeconds'];label=value.get('label','');key=value['requestId']
        if not isinstance(seconds,int) or isinstance(seconds,bool) or not 1<=seconds<=86400 or not isinstance(label,str) or len(label)>80 or any(ord(c)<32 for c in label) or not isinstance(key,str) or not ID.fullmatch(key):
            raise JuneError('invalid-timer','Use a whole duration from 1 second to 24 hours and a name up to 80 characters.',400)
        label=label.strip()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._settle(db)
            row=db.execute('SELECT * FROM timers WHERE request_id=?',(key,)).fetchone()
            if row:
                if row['duration']!=seconds or row['label']!=label:raise JuneError('timer-mismatch','This timer request was already used with different details.',409)
                return self._reply(row)
            if db.execute("SELECT COUNT(*) FROM timers WHERE status IN ('active','completed')").fetchone()[0]>=20:raise JuneError('timer-limit','Keep at most 20 active or undismissed timers. Cancel or dismiss one first.',409)
            tid=uuid.uuid4().hex;now=self.clock()
            db.execute('INSERT INTO timers VALUES(?,?,?,?,?,?,?,?,?,?,?)',(tid,key,label,seconds,now,now+seconds,'active',None,None,conversation,turn))
            row=self._get(db,tid)
        return self._reply(row)
    async def cancel(self,tid):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._settle(db);row=self._get(db,tid)
            if row['status']=='active':db.execute("UPDATE timers SET status='cancelled' WHERE id=?",(tid,))
            elif row['status']=='completed':db.execute("UPDATE timers SET status='acknowledged' WHERE id=?",(tid,))
            row=self._get(db,tid)
        return self._reply(row)
    async def acknowledge(self,tid):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._settle(db);row=self._get(db,tid)
            if row['status']=='active':raise JuneError('timer-active','Cancel an active timer instead of dismissing it.',409)
            if row['status']=='completed':db.execute("UPDATE timers SET status='acknowledged' WHERE id=?",(tid,))
            row=self._get(db,tid)
        return self._reply(row)
    async def claim(self,tid):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._settle(db);row=self._get(db,tid)
            announce=row['status']=='completed' and row['announced'] is None
            if announce:db.execute('UPDATE timers SET announced=? WHERE id=?',(self.clock(),tid))
            row=self._get(db,tid)
        return self._reply(row,announce=announce)
    def links(self,cid):
        with self.db() as db:return {r['turn']:r['id'] for r in db.execute('SELECT id,turn FROM timers WHERE conversation=? AND turn IS NOT NULL',(cid,))}
    def unlink(self,cid=None):
        with self.db() as db:db.execute('UPDATE timers SET conversation=NULL,turn=NULL '+('WHERE conversation=?' if cid else ''),(cid,) if cid else ())
    async def chat(self,question,request_id,*,conversation=None,turn=None):
        intent=timer_intent(question)
        if not intent:return None
        op=intent['operation']
        if op=='invalid':return {'reply':intent['message']}
        if op=='create':
            result=await self.create({'durationSeconds':intent['durationSeconds'],'label':intent['label'],'requestId':request_id},conversation=conversation,turn=turn)
            timer=result['timer'];name=(timer['label']+' timer') if timer['label'] else 'timer'
            result['reply']=f"Your {name} is set for {duration_phrase(timer['durationSeconds'])}. It runs locally; the timer panel shows the countdown."
            return result
        state=await self.state();active=[t for t in state['timers'] if t['status']=='active']
        if op=='cancel':
            label=intent['label'];matches=[t for t in active if not label or t['label'].casefold()==label.casefold()]
            if not matches:return {'reply':'No matching active timer was cancelled. Check Timers for the current list.'}
            if len(matches)>1:return {'reply':'More than one timer matches. Name the timer you want to cancel, or use its Cancel button in Timers.'}
            result=await self.cancel(matches[0]['id']);result['reply']='That timer is cancelled.';return result
        if not active:return {'reply':'You have no active timers. Finished timers are shown in Timers until you dismiss them.'}
        summaries=[]
        for t in active:
            seconds=max(0,int((t['endsAt']-state['serverNow']+999)//1000));summaries.append(f"{t['label'] or 'Timer'}: {duration_phrase(seconds)} left")
        return {'reply':'; '.join(summaries)+'.'}
