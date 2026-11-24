"""Repeating reminders (daily, or weekly on chosen days), due-only.

A series stores its rule, a cursor of handled local dates, and the next deadline. A reminder row
exists only once an occurrence is due, keyed UNIQUE(series_id, occurrence_date), with at most one
unresolved row per series. Deadlines come from local wall time each day: a skipped local time
(DST gap) moves to the first valid minute that day, a repeated one uses the first instance. A
deadline settled more than GRACE seconds late, or found overdue at startup, is never emitted or
spoken: it only updates one quiet `lastMissed` summary. Every mutation is bound to the series
revision and stored as a receipt for idempotent replay.
"""
import hashlib,json,re,uuid
from datetime import datetime,date,time as wall_time,timedelta
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from .errors import JuneError
from .timers import ID

GRACE=120
CLOCK=re.compile(r'(?:[01]\d|2[0-3]):[0-5]\d')
DAY=re.compile(r'\d{4}-\d{2}-\d{2}')
ALL_DAYS=[1,2,3,4,5,6,7]
DAY_WORDS={'mon':1,'tue':2,'wed':3,'thu':4,'fri':5,'sat':6,'sun':7}
DAY_NAMES=['Mon','Tue','Wed','Thu','Fri','Sat','Sun']

def series_zone(value):
    if not isinstance(value,str) or not 1<=len(value)<=100:raise JuneError('reminder-zone','Choose a valid IANA time zone.',400)
    try:return ZoneInfo(value)
    except (ZoneInfoNotFoundError,ValueError):raise JuneError('reminder-zone','Choose a valid IANA time zone, for example Asia/Kolkata.',400) from None

def occurrence_time(day,clock,tz):
    """(timestamp, adjusted) for the wall time on that day, or None if no valid minute remains that day."""
    naive=datetime.combine(day,wall_time.fromisoformat(clock));candidate=naive
    while candidate.date()==day:
        stamp=candidate.replace(tzinfo=tz,fold=0).timestamp()   # fold=0: the first of a repeated time
        if datetime.fromtimestamp(stamp,tz).replace(tzinfo=None)==candidate:return stamp,candidate!=naive
        candidate+=timedelta(minutes=1)
    return None

def describe(rule,weekdays,clock):
    h,m=map(int,clock.split(':'));at=f'{h%12 or 12}:{m:02} {"AM" if h<12 else "PM"}'
    label='every day' if rule=='daily' or weekdays==ALL_DAYS else 'every weekday' if weekdays==[1,2,3,4,5] else 'every '+', '.join(DAY_NAMES[d-1] for d in weekdays)
    return f'{label} at {at}'

def parse_clock(text):
    """'11 PM' → '23:00'; asks for AM/PM when a 12-hour time is ambiguous (same rule as one-shot reminders)."""
    m=re.fullmatch(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?',text.strip(),re.I)
    if not m:raise JuneError('reminder-time','Use a clear time, for example 11 PM. Nothing was set.',400)
    hour,minute,period=m.groups();h=int(hour);mi=int(minute or '0')
    if period:
        if not 1<=h<=12:raise JuneError('reminder-time','Use a valid time. Nothing was set.',400)
        h=h%12+(12 if period.lower().startswith('p') else 0)
    elif h<13 and (minute is None or len(hour)<2):
        raise JuneError('reminder-time','Do you mean AM or PM? Nothing was set. For example: Remind me every day at 11 PM to drink water.',400)
    if not 0<=h<=23 or not 0<=mi<=59:raise JuneError('reminder-time','Use a valid time. Nothing was set.',400)
    return f'{h:02}:{mi:02}'

DAYNAME=r'(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*'
FREQ=rf'(?:every day|daily|each day|every weekday|on weekdays|weekdays|every {DAYNAME}(?:(?:,\s*|\s+and\s+|\s*&\s*|,\s*and\s+){DAYNAME})*)'
def parse_freq(text):
    t=text.lower()
    if t in ('every day','daily','each day'):return 'daily',None
    if t in ('every weekday','on weekdays','weekdays'):return 'weekly',[1,2,3,4,5]
    days=sorted({DAY_WORDS[w[:3]] for w in re.findall(DAYNAME,t)})
    return 'weekly',days

class SeriesMixin:
    # ---- schema and records ----
    def _series_schema(self,db):
        cols={r[1] for r in db.execute('PRAGMA table_info(timers)')}
        for name,kind in (('series_id','TEXT'),('occurrence_date','TEXT'),('outcome','TEXT'),('dst_adjusted','INTEGER NOT NULL DEFAULT 0'),('resolved','REAL')):
            if name not in cols:db.execute(f'ALTER TABLE timers ADD COLUMN {name} {kind}')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS series_occurrence ON timers(series_id,occurrence_date) WHERE series_id IS NOT NULL')
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS series_unresolved ON timers(series_id) WHERE series_id IS NOT NULL AND status IN ('active','completed')")
        db.execute('''CREATE TABLE IF NOT EXISTS reminder_series(id TEXT PRIMARY KEY,request_id TEXT UNIQUE NOT NULL,digest TEXT NOT NULL,text TEXT NOT NULL,rule TEXT NOT NULL,
            weekdays TEXT NOT NULL,local_time TEXT NOT NULL,time_zone TEXT NOT NULL,start_date TEXT NOT NULL,status TEXT NOT NULL,revision INTEGER NOT NULL,created REAL NOT NULL,
            updated REAL NOT NULL,next_at REAL,next_date TEXT,next_adjusted INTEGER NOT NULL DEFAULT 0,last_handled TEXT,missed_date TEXT,missed_count INTEGER NOT NULL DEFAULT 0,missed_at REAL)''')
        db.execute('CREATE TABLE IF NOT EXISTS reminder_series_links(conversation TEXT NOT NULL,turn TEXT NOT NULL,series_id TEXT NOT NULL,PRIMARY KEY(conversation,turn))')
    def _series_record(self,s):
        return {'id':s['id'],'text':s['text'],'rule':s['rule'],'weekdays':json.loads(s['weekdays']),'localTime':s['local_time'],'timeZone':s['time_zone'],
                'startDate':s['start_date'],'status':s['status'],'revision':s['revision'],'createdAt':round(s['created']*1000),
                'nextScheduledAt':None if s['next_at'] is None else round(s['next_at']*1000),'nextOccurrenceDate':s['next_date'],
                'lastMissed':{'occurrenceDate':s['missed_date'],'count':s['missed_count'],'at':round(s['missed_at']*1000)} if s['missed_count'] else None}
    def _series_get(self,db,sid):
        row=db.execute('SELECT * FROM reminder_series WHERE id=?',(sid,)).fetchone()
        if not row:raise JuneError('series-missing','This repeating reminder is no longer available.',404)
        return dict(row)
    def _series_save(self,db,s):
        db.execute('''UPDATE reminder_series SET text=?,rule=?,weekdays=?,local_time=?,time_zone=?,status=?,revision=?,updated=?,next_at=?,next_date=?,next_adjusted=?,
            last_handled=?,missed_date=?,missed_count=?,missed_at=? WHERE id=?''',(s['text'],s['rule'],s['weekdays'],s['local_time'],s['time_zone'],s['status'],s['revision'],
            s['updated'],s['next_at'],s['next_date'],s['next_adjusted'],s['last_handled'],s['missed_date'],s['missed_count'],s['missed_at'],s['id']))
    def _capacity_used(self,db):
        one_shot=db.execute("SELECT COUNT(*) FROM timers WHERE series_id IS NULL AND status IN ('active','completed')").fetchone()[0]
        return one_shot+db.execute("SELECT COUNT(*) FROM reminder_series WHERE status IN ('active','paused')").fetchone()[0]

    # ---- scheduling ----
    def _next_occurrence(self,s,after,not_before=None):
        """First rule date after `after` (and after `not_before`, if given). Returns (date, stamp, adjusted, invalid_dates)."""
        tz=series_zone(s['time_zone']);days=set(json.loads(s['weekdays']));day=max(after+timedelta(days=1),date.fromisoformat(s['start_date']));invalid=[]
        for _ in range(800):
            if s['rule']=='daily' or day.isoweekday() in days:
                found=occurrence_time(day,s['local_time'],tz)
                if found is None:invalid.append(day.isoformat())
                elif not_before is None or found[0]>not_before:return day.isoformat(),found[0],found[1],invalid
            day+=timedelta(days=1)
        raise JuneError('series-schedule','June could not find the next time for this repeating reminder.',500)
    def _cursor(self,s):
        return date.fromisoformat(s['last_handled']) if s['last_handled'] else date.fromisoformat(s['start_date'])-timedelta(days=1)
    def _plan_future(self,s,now):
        d,t,adj,_=self._next_occurrence(s,self._cursor(s),not_before=now)
        s.update(next_date=d,next_at=t,next_adjusted=int(adj))
    def _miss(self,s,day,now):
        s['missed_count']=(s['missed_count'] or 0)+1;s['missed_at']=now
        if not s['missed_date'] or day>s['missed_date']:s['missed_date']=day
    def _archive_unresolved(self,db,sid,now,outcome='missed'):
        db.execute("UPDATE timers SET status='acknowledged',outcome=?,resolved=?,revision=revision+1 WHERE series_id=? AND status IN ('active','completed')",(outcome,now,sid))
    def _emit(self,db,s,day,due,adjusted,now):
        self._archive_unresolved(db,s['id'],now)   # archive before insert: at most one unresolved
        db.execute('''INSERT OR IGNORE INTO timers(id,request_id,label,duration,created,ends,status,completed,announced,conversation,turn,time_zone,revision,series_id,occurrence_date,dst_adjusted)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(uuid.uuid4().hex,f'series:{s["id"]}:{day}',s['text'],0,now,due,'completed',due,None,None,None,s['time_zone'],1,s['id'],day,int(adjusted)))
    def _advance(self,s,day,now):
        """Mark `day` handled and plan the next rule date; DST days with no valid minute become quiet misses."""
        s['last_handled']=day
        nd,nt,adj,invalid=self._next_occurrence(s,date.fromisoformat(day))
        for bad in invalid:self._miss(s,bad,now)
        s.update(next_date=nd,next_at=nt,next_adjusted=int(adj))
    def _settle_series(self,db,now):
        for row in db.execute("SELECT * FROM reminder_series WHERE status='active' AND next_at IS NOT NULL AND next_at<=?",(now,)).fetchall():
            s=dict(row)
            while s['next_at'] is not None and s['next_at']<=now:
                day,due=s['next_date'],s['next_at']
                if now<=due+GRACE:self._emit(db,s,day,due,bool(s['next_adjusted']),now)
                else:
                    self._archive_unresolved(db,s['id'],now)
                    self._miss(s,day,now)   # late: never emitted or spoken
                self._advance(s,day,now)
            self._series_save(db,s)
        db.execute("DELETE FROM reminder_series WHERE status='cancelled' AND updated<?",(now-7*86400,))
    def _reconcile_series(self):
        """Startup: everything overdue is silent. Archive unresolved due rows (even when the next deadline is
        future), fold their dates and any skipped deadlines into one lastMissed, then plan strictly in the future.
        Future snoozed rows survive."""
        now=self.clock()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for row in db.execute('SELECT * FROM reminder_series').fetchall():
                s=dict(row)
                for r in db.execute("SELECT id,occurrence_date FROM timers WHERE series_id=? AND (status='completed' OR (status='active' AND ends<=?))",(s['id'],now)).fetchall():
                    db.execute("UPDATE timers SET status='acknowledged',outcome='missed',resolved=?,revision=revision+1 WHERE id=?",(now,r['id']))
                    self._miss(s,r['occurrence_date'],now)
                if s['status']=='active' and s['next_at'] is not None:
                    while s['next_at']<=now:
                        self._miss(s,s['next_date'],now);self._advance(s,s['next_date'],now)
                self._series_save(db,s)

    # ---- validation, receipts ----
    def _series_text(self,text):
        if not isinstance(text,str) or not text.strip() or len(text)>200 or any(ord(c)<32 for c in text):
            raise JuneError('invalid-reminder','Use reminder text from 1 to 200 characters.',400)
        return text.strip()
    def _series_rule(self,rule,weekdays,given):
        if rule=='daily':
            if given:raise JuneError('invalid-series','A daily reminder takes no weekdays.',400)
            return ALL_DAYS
        if rule!='weekly':raise JuneError('invalid-series','Choose daily or weekly.',400)
        if not isinstance(weekdays,list) or not weekdays or any(type(d) is not int or not 1<=d<=7 for d in weekdays) or len(set(weekdays))!=len(weekdays):
            raise JuneError('invalid-series','Choose at least one weekday (1 = Monday … 7 = Sunday).',400)
        return sorted(weekdays)
    def _digest(self,value):
        try:return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()
        except (ValueError,TypeError):raise JuneError('invalid-series','Send a valid repeating reminder request.',400) from None
    def _receipt(self,db,key,target,kind,digest,fingerprint=None):
        receipt=db.execute('SELECT * FROM reminder_changes WHERE request_id=?',(key,)).fetchone()
        if not receipt:return None
        if receipt['reminder_id']!=target or receipt['kind']!=kind or (receipt['digest']!=digest and (fingerprint is None or receipt['chat_fingerprint']!=fingerprint)):
            raise JuneError('reminder-mismatch','This request id was already used for a different reminder change.',409)
        result=json.loads(receipt['response']);result['serverNow']=round(self.clock()*1000);return result
    def _store(self,db,key,target,kind,digest,result,now,fingerprint=None):
        db.execute('INSERT INTO reminder_changes VALUES(?,?,?,?,?,?,?)',(key,target,kind,digest,json.dumps(result),now,fingerprint))
        db.execute('DELETE FROM reminder_changes WHERE created<?',(now-7*86400,))

    # ---- create and mutate ----
    async def create_series(self,value,*,conversation=None,turn=None,fingerprint=None):
        allowed={'text','rule','weekdays','localTime','startDate','timeZone','requestId'}
        if not isinstance(value,dict) or not {'text','rule','localTime','startDate','requestId'}<=set(value)<=allowed:
            raise JuneError('invalid-series','Choose the reminder text, how it repeats, a time, a start date and a request id.',400)
        key=value['requestId']
        if not isinstance(key,str) or not ID.fullmatch(key):raise JuneError('invalid-series','Send a valid request id.',400)
        text=self._series_text(value['text']);weekdays=self._series_rule(value['rule'],value.get('weekdays'),'weekdays' in value)
        clock,start=value['localTime'],value['startDate']
        if not isinstance(clock,str) or not CLOCK.fullmatch(clock):raise JuneError('reminder-time','Choose a time such as 23:00.',400)
        where=value.get('timeZone',self.time_zone);tz=series_zone(where)
        if not isinstance(start,str) or not DAY.fullmatch(start):raise JuneError('reminder-time','Choose a start date such as 2026-11-14.',400)
        try:first=date.fromisoformat(start)
        except ValueError:raise JuneError('reminder-time','Choose a valid start date.',400) from None
        digest=self._digest(value)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._settle(db)
            existing=db.execute('SELECT * FROM reminder_series WHERE request_id=?',(key,)).fetchone()
            if existing:
                if existing['digest']!=digest:raise JuneError('reminder-mismatch','This request id already belongs to a different repeating reminder.',409)
                return {'serverNow':round(self.clock()*1000),'series':self._series_record(existing)}
            now=self.clock();today=datetime.fromtimestamp(now,tz).date()
            if not today<=first<=today+timedelta(days=30):raise JuneError('reminder-time','Start within the next 30 days. Nothing was set.',400)
            if self._capacity_used(db)>=20:raise JuneError('reminder-limit','June can keep 20 reminders at once (repeating or not). Cancel or dismiss one first.',409)
            s={'id':uuid.uuid4().hex,'text':text,'rule':value['rule'],'weekdays':json.dumps(weekdays),'local_time':clock,'time_zone':where,'start_date':start,'status':'active',
               'revision':1,'created':now,'updated':now,'next_at':None,'next_date':None,'next_adjusted':0,'last_handled':None,'missed_date':None,'missed_count':0,'missed_at':None}
            self._plan_future(s,now)   # first rule date at or after the start, strictly in the future: no catch-up
            db.execute('INSERT INTO reminder_series VALUES(:id,:rule_key,:digest,:text,:rule,:weekdays,:local_time,:time_zone,:start_date,:status,:revision,:created,:updated,:next_at,:next_date,:next_adjusted,:last_handled,:missed_date,:missed_count,:missed_at)',
                       {**s,'rule_key':key,'digest':digest})
            self._series_link(db,s['id'],conversation,turn)
            return {'serverNow':round(now*1000),'series':self._series_record(s)}
    async def _series_change(self,sid,value,kind,extra=frozenset(),fingerprint=None,apply=None):
        if not isinstance(value,dict) or not {'revision','requestId'}<=set(value)<={'revision','requestId',*extra}:
            raise JuneError('invalid-series','Send the current revision, a request id and only supported changes.',400)
        revision,key=value['revision'],value['requestId']
        if type(revision) is not int or revision<1 or not isinstance(key,str) or not ID.fullmatch(key):raise JuneError('invalid-series','Send a valid revision and request id.',400)
        digest=self._digest(value)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._settle(db)
            replay=self._receipt(db,key,sid,'series-'+kind,digest,fingerprint)
            if replay:return replay
            s=self._series_get(db,sid)
            if s['revision']!=revision:raise JuneError('series-conflict','This repeating reminder changed in another request. Refresh it before trying again.',409)
            now=self.clock();reminder=apply(db,s,value,now)
            s['revision']+=1;s['updated']=now;self._series_save(db,s)
            result={'serverNow':round(now*1000),'series':self._series_record(s)}
            if reminder is not None:result['reminder']=self._record(reminder)
            self._store(db,key,sid,'series-'+kind,digest,result,now,fingerprint)
            return result
    def _require(self,s,*statuses):
        if s['status'] not in statuses:
            raise JuneError('series-closed' if s['status']=='cancelled' else 'series-state',
                            'This repeating reminder has stopped. Create a new one.' if s['status']=='cancelled' else 'This repeating reminder is not in a state that allows that. Refresh it first.',409)
    async def update_series(self,sid,value,*,fingerprint=None):
        changes={'text','rule','weekdays','localTime','timeZone'}
        def apply(db,s,v,now):
            self._require(s,'active','paused')
            if not set(v)&changes:raise JuneError('invalid-series','Change the text, time, days or zone.',400)
            if 'text' in v:s['text']=self._series_text(v['text'])
            if 'rule' in v or 'weekdays' in v:
                rule=v.get('rule',s['rule'])
                s['weekdays']=json.dumps(self._series_rule(rule,v.get('weekdays',json.loads(s['weekdays']) if rule=='weekly' else None),'weekdays' in v and rule=='daily'));s['rule']=rule
            if 'localTime' in v:
                if not isinstance(v['localTime'],str) or not CLOCK.fullmatch(v['localTime']):raise JuneError('reminder-time','Choose a time such as 23:00.',400)
                s['local_time']=v['localTime']
            if 'timeZone' in v:series_zone(v['timeZone']);s['time_zone']=v['timeZone']
            # The already-due occurrence keeps its own snapshot; only the future schedule changes.
            if s['status']=='active':self._plan_future(s,now)
            return None
        return await self._series_change(sid,value,'update',changes,fingerprint,apply)
    async def pause_series(self,sid,value,*,fingerprint=None):
        def apply(db,s,v,now):
            self._require(s,'active')
            s.update(status='paused',next_at=None,next_date=None,next_adjusted=0)
            # A future snoozed occurrence is cancelled; a due one stays visible but its queued alert drops.
            db.execute("UPDATE timers SET status='cancelled',outcome='paused',resolved=?,revision=revision+1 WHERE series_id=? AND status='active'",(now,s['id']))
            db.execute("UPDATE timers SET revision=revision+1 WHERE series_id=? AND status='completed'",(s['id'],))
            return None
        return await self._series_change(sid,value,'pause',fingerprint=fingerprint,apply=apply)
    async def resume_series(self,sid,value,*,fingerprint=None):
        def apply(db,s,v,now):
            self._require(s,'paused')
            self._archive_unresolved(db,s['id'],now)
            s['status']='active';self._plan_future(s,now)   # strictly future, no catch-up; the paused slot is kept
            return None
        return await self._series_change(sid,value,'resume',fingerprint=fingerprint,apply=apply)
    async def cancel_series(self,sid,value,*,fingerprint=None):
        def apply(db,s,v,now):
            self._require(s,'active','paused')
            s.update(status='cancelled',next_at=None,next_date=None,next_adjusted=0)
            db.execute("UPDATE timers SET status='cancelled',resolved=?,revision=revision+1 WHERE series_id=? AND status IN ('active','completed')",(now,s['id']))
            return None
        return await self._series_change(sid,value,'cancel',fingerprint=fingerprint,apply=apply)
    async def skip_next(self,sid,value,*,fingerprint=None):
        def apply(db,s,v,now):
            self._require(s,'active')
            if not s['next_date'] or v['occurrenceDate']!=s['next_date']:
                raise JuneError('series-conflict','That day is no longer the next one for this repeating reminder. Refresh it and try again.',409)
            day,due=s['next_date'],s['next_at']
            rid=uuid.uuid4().hex
            db.execute('''INSERT INTO timers(id,request_id,label,duration,created,ends,status,completed,announced,conversation,turn,time_zone,revision,series_id,occurrence_date,dst_adjusted,outcome,resolved)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(rid,f'series:{s["id"]}:{day}',s['text'],0,now,due,'acknowledged',None,None,None,None,s['time_zone'],1,s['id'],day,s['next_adjusted'],'skipped',now))
            self._advance(s,day,now)
            return db.execute('SELECT * FROM timers WHERE id=?',(rid,)).fetchone()
        return await self._series_change(sid,value,'skip-next',{'occurrenceDate'},fingerprint,apply)
    async def skip(self,rid,value):
        """Skip this one due (or snoozed) occurrence of an active series."""
        if not isinstance(value,dict) or set(value)!={'revision','requestId'}:raise JuneError('invalid-reminder','Send the current revision and a request id.',400)
        revision,key=value['revision'],value['requestId']
        if type(revision) is not int or revision<1 or not isinstance(key,str) or not ID.fullmatch(key):raise JuneError('invalid-reminder','Send a valid revision and request id.',400)
        digest=self._digest(value)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._settle(db)
            replay=self._receipt(db,key,rid,'skip',digest)
            if replay:return replay
            row=self._get(db,rid);self._check_revision(row,revision)
            if not row['series_id']:raise JuneError('reminder-not-series','Only a repeating reminder can be skipped. Cancel or dismiss this one instead.',409)
            self._series_active(db,row)
            if row['status'] not in ('active','completed'):raise JuneError('reminder-closed','This reminder is already resolved.',409)
            now=self.clock()
            db.execute("UPDATE timers SET status='acknowledged',outcome='skipped',resolved=?,revision=revision+1 WHERE id=?",(now,rid))
            result=self._reply(self._get(db,rid));self._store(db,key,rid,'skip',digest,result,now)
            return result
    def _series_active(self,db,row):
        s=db.execute('SELECT status,next_at FROM reminder_series WHERE id=?',(row['series_id'],)).fetchone()
        if not s or s['status']!='active':raise JuneError('series-paused','This repeating reminder is paused or stopped. Resume it first, or dismiss this one.',409)
        return s

    # ---- links ----
    def _series_link(self,db,sid,conversation,turn):
        if conversation and turn:db.execute('INSERT OR REPLACE INTO reminder_series_links VALUES(?,?,?)',(conversation,turn,sid))
    def series_links(self,cid):
        with self.db() as db:return {r['turn']:r['series_id'] for r in db.execute('SELECT turn,series_id FROM reminder_series_links WHERE conversation=?',(cid,))}

    # ---- chat (deterministic, no model) ----
    async def _chat_series(self,q,request_id,conversation,turn):
        made=re.fullmatch(rf'remind me ({FREQ}) at (.+?) to (.+)',q,re.I|re.S)
        inverted=re.fullmatch(rf'remind me to (.+?) ({FREQ}) at (\d{{1,2}}(?::\d{{2}})?\s*(?:am|pm|a\.m\.|p\.m\.)?)[.!]?',q,re.I|re.S) if not made else None
        bare=re.fullmatch(rf'remind me ({FREQ})(?: at (.+?))?[.!]?',q,re.I) if not (made or inverted) else None
        if bare:return {'reply':'What should June remind you about? For example: Remind me every day at 11 PM to drink water. Nothing was set.'}
        fingerprint=hashlib.sha256(re.sub(r'\s+',' ',q).encode()).hexdigest()
        try:
            if made or inverted:
                freq,when,text=(made[1],made[2],made[3]) if made else (inverted[2],inverted[3],inverted[1])
                rule,days=parse_freq(freq)
                if rule=='weekly' and not days:return {'reply':'Name the days, for example every Monday and Thursday. Nothing was set.'}
                with self.db() as db:existing=db.execute('SELECT * FROM reminder_series WHERE request_id=?',(request_id,)).fetchone()
                if existing:   # a retried chat turn (same request id) returns the series it already made
                    result={'serverNow':round(self.clock()*1000),'series':self._series_record(existing)}
                else:
                    value={'text':text.strip().rstrip('.!?'),'rule':rule,**({'weekdays':days} if rule=='weekly' else {}),'localTime':parse_clock(when),
                           'startDate':datetime.fromtimestamp(self.clock(),series_zone(self.time_zone)).date().isoformat(),'timeZone':self.time_zone,'requestId':request_id}
                    result=await self.create_series(value,conversation=conversation,turn=turn)
                s=result['series']
                nxt=datetime.fromtimestamp(s['nextScheduledAt']/1000,series_zone(s['timeZone'])).strftime('%d %b %Y at %I:%M %p')
                result['reply']=(f'Repeating reminder set {describe(s["rule"],s["weekdays"],s["localTime"])} ({s["timeZone"]}): {s["text"]}. First on {nxt}. '
                                 'June must be running; spoken alerts need this page open and voice ready.')
                return result
            control=re.fullmatch(r'(pause|resume|unpause|stop|cancel|end)(?: repeating)? (?:my |the )?(.+?) (?:repeating |daily |weekly |recurring )?reminders?[.!]?',q,re.I)
            skipper=re.fullmatch(r'skip (?:the |my )?next (.+?) reminder[.!]?|skip (?:my |the )?(.+?) reminder (?:tonight|today|tomorrow|next time)[.!]?',q,re.I)
            if not (control or skipper):return None
            name=((control[2] if control else (skipper[1] or skipper[2])) or '').strip().rstrip('.!?').casefold()
            verb=control[1].lower() if control else 'skip'
            with self.db() as db:
                receipt=db.execute('SELECT * FROM reminder_changes WHERE request_id=?',(request_id,)).fetchone()
                rows=[dict(r) for r in db.execute("SELECT * FROM reminder_series WHERE status!='cancelled'").fetchall()]
                one_shots=db.execute("SELECT COUNT(*) FROM timers WHERE series_id IS NULL AND status IN ('active','completed') AND lower(trim(label,' .!?'))=?",(name,)).fetchone()[0]
            if receipt and receipt['chat_fingerprint']==fingerprint:
                result=json.loads(receipt['response'])
            else:
                wanted={'pause':('active',),'resume':('paused',),'unpause':('paused',),'skip':('active',)}.get(verb,('active','paused'))
                matches=[r for r in rows if r['text'].strip().rstrip('.!?').casefold()==name and r['status'] in wanted]
                if verb in ('stop','cancel','end') and matches and one_shots:return {'reply':'Both a one-time and a repeating reminder match. Use Stop repeating or Cancel in Reminders. Nothing changed.'}
                if not matches:return None if verb in ('stop','cancel','end') else {'reply':'No matching repeating reminder can be changed. Check Reminders. Nothing changed.'}
                if len(matches)>1:return {'reply':'More than one repeating reminder matches. Say its exact text or use Reminders. Nothing changed.'}
                s=matches[0];value={'revision':s['revision'],'requestId':request_id}
                if verb=='skip':
                    if not s['next_date']:return {'reply':'Nothing is scheduled to skip. Nothing changed.'}
                    result=await self.skip_next(s['id'],{**value,'occurrenceDate':s['next_date']},fingerprint=fingerprint)
                else:
                    action={'pause':self.pause_series,'resume':self.resume_series,'unpause':self.resume_series}.get(verb,self.cancel_series)
                    result=await action(s['id'],value,fingerprint=fingerprint)
            with self.db() as db:self._series_link(db,result['series']['id'],conversation,turn)
            s=result['series']
            words={'paused':'paused: nothing will be said until you resume it','cancelled':'stopped'}
            result['reply']=(f'Your {s["text"]} reminder is {words[s["status"]]}.' if s['status'] in words else
                             f'Skipped. Next {s["text"]} reminder: '+datetime.fromtimestamp(s['nextScheduledAt']/1000,series_zone(s['timeZone'])).strftime('%d %b %Y at %I:%M %p')+'.' if verb=='skip' else
                             f'Your {s["text"]} reminder is back on, '+describe(s['rule'],s['weekdays'],s['localTime'])+'.')
            return result
        except JuneError as e:
            if e.status>=500:raise
            return {'reply':e.message}
