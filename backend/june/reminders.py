"""One-shot local reminders, with explicit wall time and persistent once-only claims."""
import os,re,time,uuid,hashlib,json
from datetime import datetime,date,time as wall_time,timedelta,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from .timers import Timers,ID,timer_intent
from .errors import JuneError
from .app_info import nonliteral_request
from .reminder_series import SeriesMixin

UTC=timezone.utc

def zone(value):
    if not isinstance(value,str) or not 1<=len(value)<=100:raise JuneError('reminder-zone','Choose a valid IANA time zone.',400)
    try:return ZoneInfo(value)
    except (ZoneInfoNotFoundError,ValueError):raise JuneError('reminder-zone','Choose a valid IANA time zone, for example Asia/Kolkata.',400) from None

def local_timestamp(day,clock,where):
    if not isinstance(day,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) or not isinstance(clock,str) or not re.fullmatch(r'\d{2}:\d{2}(?::\d{2})?',clock):
        raise JuneError('reminder-time','Choose a date and a time such as 18:00.',400)
    try:naive=datetime.combine(date.fromisoformat(day),wall_time.fromisoformat(clock))
    except ValueError:raise JuneError('reminder-time','Choose a valid calendar date and time.',400) from None
    tz=zone(where);possibilities=set()
    try:
        for fold in (0,1):
            aware=naive.replace(tzinfo=tz,fold=fold);stamp=aware.timestamp()
            if datetime.fromtimestamp(stamp,tz).replace(tzinfo=None)==naive:possibilities.add(stamp)
    except (ValueError,OverflowError,OSError):
        raise JuneError('reminder-time','Choose a valid future date within 30 days.',400) from None
    if len(possibilities)!=1:raise JuneError('reminder-time','That local time is skipped or repeated by a clock change. Choose an unambiguous time.',400)
    return possibilities.pop()

def due_phrase(stamp,where):return datetime.fromtimestamp(stamp,zone(where)).strftime('%d %b %Y at %I:%M %p')+' ('+where+')'

def reminder_deadline(when,now,where):
    today=datetime.fromtimestamp(now,zone(where)).date()
    relative=re.fullmatch(r'in (.+)',when,flags=re.I)
    if relative:
        intent=timer_intent('Set a timer for '+relative[1])
        if not intent or intent['operation']!='create':raise JuneError('reminder-time','Give a clear duration, such as in ten minutes. No reminder was set.',400)
        due=now+intent['durationSeconds']
    else:
        at=re.fullmatch(r'(?:(today|tomorrow|on \d{4}-\d{2}-\d{2}) )?at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?',when,flags=re.I)
        if not at:raise JuneError('reminder-time','Use a clear time, for example tomorrow at 6 PM. No reminder was set.',400)
        which,hour,minute,period=at.groups();h=int(hour);m=int(minute or '0')
        if period:
            if not 1<=h<=12:raise ValueError()
            h=h%12+(12 if period.lower()=='pm' else 0)
        elif h<13 and (minute is None or len(hour)<2):
            raise JuneError('reminder-time','Do you mean AM or PM? No reminder was set. For example: Remind me at 6 PM to stretch.',400)
        if not 0<=h<=23 or not 0<=m<=59:raise ValueError()
        day=today
        if which:
            if which.lower()=='tomorrow':day+=timedelta(days=1)
            elif which.lower().startswith('on '):day=date.fromisoformat(which[3:])
        clock=f'{h:02}:{m:02}'
        due=local_timestamp(day.isoformat(),clock,where)
        if which is None and due<=now:due=local_timestamp((day+timedelta(days=1)).isoformat(),clock,where)
    return due

class Reminders(SeriesMixin,Timers):
    def __init__(self,directory,clock=time.time,*,time_zone=None):
        self.time_zone=time_zone or os.environ.get('JUNE_TIME_ZONE','Asia/Kolkata');zone(self.time_zone)
        super().__init__(directory,clock,store_name='reminders')
        with self.db() as db:
            if 'time_zone' not in {r[1] for r in db.execute('PRAGMA table_info(timers)')}:
                db.execute("ALTER TABLE timers ADD COLUMN time_zone TEXT NOT NULL DEFAULT 'Asia/Kolkata'")
            if 'intent_fingerprint' not in {r[1] for r in db.execute('PRAGMA table_info(timers)')}:
                db.execute('ALTER TABLE timers ADD COLUMN intent_fingerprint TEXT')
            if 'revision' not in {r[1] for r in db.execute('PRAGMA table_info(timers)')}:
                db.execute('ALTER TABLE timers ADD COLUMN revision INTEGER NOT NULL DEFAULT 1')
            db.execute('CREATE TABLE IF NOT EXISTS reminder_changes(request_id TEXT PRIMARY KEY,reminder_id TEXT NOT NULL,kind TEXT NOT NULL,digest TEXT NOT NULL,response TEXT NOT NULL,created REAL NOT NULL,chat_fingerprint TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS reminder_links(conversation TEXT NOT NULL,turn TEXT NOT NULL,reminder_id TEXT NOT NULL,PRIMARY KEY(conversation,turn))')
            self._series_schema(db)
        # Repeating reminders are settled only once their schema exists; startup first makes everything overdue silent.
        self._series_ready=True
        self._reconcile_series()
    def _settle(self,db):
        if not getattr(self,'_series_ready',False):return super()._settle(db)
        now=self.clock()
        db.execute("UPDATE timers SET status='completed',completed=ends WHERE status='active' AND ends<=?",(now,))
        # Resolved rows are kept 7 days from resolution (one-shot rows fall back to their creation time, as before).
        db.execute("DELETE FROM timers WHERE status IN ('cancelled','acknowledged') AND COALESCE(resolved,created)<?",(now-7*86400,))
        self._settle_series(db,now)
    def _record(self,row):
        v={'id':row['id'],'text':row['label'],'dueAt':round(row['ends']*1000),'timeZone':row['time_zone'],'createdAt':round(row['created']*1000),'status':row['status'],'revision':row['revision']}
        if row['completed'] is not None:v['completedAt']=round(row['completed']*1000)
        if row['announced'] is not None:v['announcedAt']=round(row['announced']*1000)
        if 'series_id' in row.keys() and row['series_id']:
            v.update(seriesId=row['series_id'],occurrenceDate=row['occurrence_date'])
            if row['outcome']:v['outcome']=row['outcome']
            if row['dst_adjusted']:v['dstAdjusted']=True
        return v
    def _reply(self,row,**extra):return {'serverNow':round(self.clock()*1000),'reminder':self._record(row),**extra}
    def _get(self,db,rid):
        row=db.execute('SELECT * FROM timers WHERE id=?',(rid,)).fetchone()
        if not row:raise JuneError('reminder-missing','This reminder is no longer available.',404)
        return row
    async def state(self):
        # Reuse the timer lifecycle and retention, with a separate private database.
        state=await super().state()
        with self.db() as db:series=[self._series_record(dict(r)) for r in db.execute('SELECT * FROM reminder_series ORDER BY created,id').fetchall()]
        return {'serverNow':state['serverNow'],'timeZone':self.time_zone,'reminders':state['timers'],'series':series}
    async def create(self,value,*,conversation=None,turn=None):
        if not isinstance(value,dict) or not {'text','localDate','localTime','requestId'}<=set(value)<={'text','localDate','localTime','timeZone','requestId'}:
            raise JuneError('invalid-reminder','Choose reminder text, date, time and a request id.',400)
        where=value.get('timeZone',self.time_zone)
        due=local_timestamp(value['localDate'],value['localTime'],where)
        return await self._create_at(value['text'],due,where,value['requestId'],conversation,turn)
    async def _create_at(self,text,due,where,key,conversation=None,turn=None,*,fingerprint=None):
        if not isinstance(text,str) or not text.strip() or len(text)>200 or any(ord(c)<32 for c in text) or not isinstance(key,str) or not ID.fullmatch(key):
            raise JuneError('invalid-reminder','Use reminder text from 1 to 200 characters and a valid request id.',400)
        text=text.strip()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._settle(db)
            row=db.execute('SELECT * FROM timers WHERE request_id=?',(key,)).fetchone()
            if row:
                same_due=row['ends']==due if fingerprint is None else row['intent_fingerprint']==fingerprint
                if row['label']!=text or not same_due or row['time_zone']!=where:raise JuneError('reminder-mismatch','This request id already belongs to a different reminder.',409)
                return self._reply(row)
            now=self.clock()
            if not now<due<=now+30*86400:raise JuneError('reminder-time','Choose a future time within the next 30 days. No reminder was set.',400)
            if self._capacity_used(db)>=20:raise JuneError('reminder-limit','June can keep 20 reminders at once (repeating or not). Cancel or dismiss one first.',409)
            rid=uuid.uuid4().hex
            db.execute('INSERT INTO timers(id,request_id,label,duration,created,ends,status,completed,announced,conversation,turn,time_zone,intent_fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,key,text,max(1,round(due-now)),now,due,'active',None,None,conversation,turn,where,fingerprint))
            row=self._get(db,rid)
        return self._reply(row)
    def _link(self,rid,conversation,turn):
        if conversation and turn:
            with self.db() as db:db.execute('INSERT OR REPLACE INTO reminder_links VALUES(?,?,?)',(conversation,turn,rid))
    def links(self,cid):
        result=super().links(cid)
        with self.db() as db:result.update({r['turn']:r['reminder_id'] for r in db.execute('SELECT turn,reminder_id FROM reminder_links WHERE conversation=?',(cid,))})
        return result
    def unlink(self,cid=None):
        super().unlink(cid)
        with self.db() as db:
            db.execute('DELETE FROM reminder_links '+('WHERE conversation=?' if cid else ''),(cid,) if cid else ())
            db.execute('DELETE FROM reminder_series_links '+('WHERE conversation=?' if cid else ''),(cid,) if cid else ())
    def _check_revision(self,row,revision):
        if revision is None and row['revision']==1:return
        if type(revision) is not int or revision<1:raise JuneError('reminder-revision','Refresh this reminder before trying again.',409)
        if row['revision']!=revision:raise JuneError('reminder-conflict','This reminder changed in another request. Refresh it before trying again.',409)
    async def cancel(self,rid,revision=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._settle(db);row=self._get(db,rid);self._check_revision(row,revision)
            if row['series_id']:raise JuneError('series-occurrence','This is one day of a repeating reminder. Use Skip this time, or edit or stop the repeating reminder.',409)
            if row['status']=='active':db.execute("UPDATE timers SET status='cancelled' WHERE id=?",(rid,))
            elif row['status']=='completed':db.execute("UPDATE timers SET status='acknowledged' WHERE id=?",(rid,))
            row=self._get(db,rid)
        return self._reply(row)
    async def acknowledge(self,rid,revision=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._settle(db);row=self._get(db,rid);self._check_revision(row,revision)
            # Dismiss works on a repeating reminder's occurrence even while its series is paused.
            if row['status']=='active' and not row['series_id']:raise JuneError('reminder-active','Cancel a scheduled reminder instead of dismissing it.',409)
            if row['status'] in ('completed','active'):db.execute("UPDATE timers SET status='acknowledged',resolved=? WHERE id=?",(self.clock(),rid))
            row=self._get(db,rid)
        return self._reply(row)
    async def claim(self,rid,revision=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._settle(db);row=self._get(db,rid);self._check_revision(row,revision)
            announce=row['status']=='completed' and row['announced'] is None
            if announce and row['series_id']:
                series=db.execute('SELECT status FROM reminder_series WHERE id=?',(row['series_id'],)).fetchone()
                announce=bool(series and series['status']=='active')   # a paused or stopped series never speaks
            if announce:db.execute('UPDATE timers SET announced=? WHERE id=?',(self.clock(),rid))
            row=self._get(db,rid)
        return self._reply(row,announce=announce)
    async def reschedule(self,rid,value,*,chat_fingerprint=None):
        return await self._change(rid,value,'reschedule',chat_fingerprint)
    async def snooze(self,rid,value,*,chat_fingerprint=None):
        return await self._change(rid,value,'snooze',chat_fingerprint)
    async def _change(self,rid,value,kind,chat_fingerprint):
        required={'revision','requestId','seconds'} if kind=='snooze' else {'revision','requestId','localDate','localTime'}
        allowed=required if kind=='snooze' else required|{'text','timeZone'}
        if not isinstance(value,dict) or not required<=set(value)<=allowed:raise JuneError('invalid-reminder','Send the current revision and complete reminder changes.',400)
        revision,key=value['revision'],value['requestId']
        if type(revision) is not int or revision<1 or not isinstance(key,str) or not ID.fullmatch(key):raise JuneError('invalid-reminder','Send a valid revision and request id.',400)
        try:digest=hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()
        except (ValueError,TypeError):raise JuneError('invalid-reminder','Send valid reminder changes.',400) from None
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._settle(db)
            receipt=db.execute('SELECT * FROM reminder_changes WHERE request_id=?',(key,)).fetchone()
            if receipt:
                if receipt['reminder_id']!=rid or receipt['kind']!=kind or receipt['digest']!=digest or receipt['chat_fingerprint']!=chat_fingerprint:
                    raise JuneError('reminder-mismatch','This request id was already used for a different reminder change.',409)
                result=json.loads(receipt['response']);result['serverNow']=round(self.clock()*1000);return result
            row=self._get(db,rid);self._check_revision(row,revision)
            if row['status'] not in ('active','completed'):raise JuneError('reminder-closed','A cancelled or dismissed reminder cannot be moved or snoozed. Create a new reminder.',409)
            series=None
            if row['series_id']:
                if kind=='reschedule':raise JuneError('series-occurrence','This is one day of a repeating reminder. Edit the repeating reminder to change its time, or snooze this one.',409)
                series=self._series_active(db,row)
            now=self.clock();where=value.get('timeZone',row['time_zone']);text=value.get('text',row['label'])
            if not isinstance(text,str) or not text.strip() or len(text)>200 or any(ord(c)<32 for c in text):raise JuneError('invalid-reminder','Use reminder text from 1 to 200 characters.',400)
            if kind=='snooze':
                seconds=value['seconds']
                if type(seconds) is not int or not 1<=seconds<=86400:raise JuneError('reminder-snooze','Snooze for a whole duration from 1 second to 24 hours.',400)
                due=now+seconds
            else:due=local_timestamp(value['localDate'],value['localTime'],where)
            if not now<due<=now+30*86400:raise JuneError('reminder-time','Choose a future time within the next 30 days. The reminder was not changed.',400)
            if series and series['next_at'] is not None and due>=series['next_at']:
                at=datetime.fromtimestamp(series['next_at'],zone(row['time_zone'])).strftime('%I:%M %p on %d %b')
                raise JuneError('reminder-snooze-overlap',f'That would run into the next regular reminder at {at}. Dismiss this one or snooze for less.',409)
            db.execute("UPDATE timers SET label=?,ends=?,duration=?,time_zone=?,revision=revision+1,status='active',completed=NULL,announced=NULL WHERE id=?",(text.strip(),due,max(1,round(due-now)),where,rid))
            result=self._reply(self._get(db,rid))
            db.execute('INSERT INTO reminder_changes VALUES(?,?,?,?,?,?,?)',(key,rid,kind,digest,json.dumps(result),now,chat_fingerprint))
            db.execute('DELETE FROM reminder_changes WHERE created<?',(now-7*86400,))
        return result
    async def _chat_change(self,q,request_id):
        move=re.fullmatch(r'(?:move|reschedule) (?:my |the )?(?:(.+?) )?reminder to (.+)',q,re.I)
        snooze=re.fullmatch(r'(?:snooze|postpone) (?:my |the )?(?:(.+?) )?reminder(?: for| by)? (.+)',q,re.I)
        again=re.fullmatch(r'remind me again in (.+)',q,re.I)
        if not (move or snooze or again):
            if re.match(r'^(?:move|reschedule|snooze|postpone|edit|change)\b',q,re.I) and re.search(r'\breminder\b',q,re.I):
                return {'reply':'Use a clear time or duration, for example Move my stretch reminder to 7 PM or Snooze my stretch reminder for ten minutes. You can also use Edit in Reminders. Nothing changed.'}
            return None
        fingerprint=hashlib.sha256(re.sub(r'\s+',' ',q).encode()).hexdigest()
        with self.db() as db:receipt=db.execute('SELECT * FROM reminder_changes WHERE request_id=?',(request_id,)).fetchone()
        kind='reschedule' if move else 'snooze'
        try:
            if receipt:
                if receipt['chat_fingerprint']!=fingerprint:raise JuneError('reminder-mismatch','That request id belongs to another reminder change.',409)
                result=json.loads(receipt['response']);result['serverNow']=round(self.clock()*1000)
            else:
                state=await self.state();name=((move or snooze)[1] or '').strip().rstrip('.!?').casefold() if not again else ''
                matches=[r for r in state['reminders'] if r['status'] in (('completed',) if again else ('active','completed')) and (not name or r['text'].strip().rstrip('.!?').casefold()==name)]
                if not matches:return {'reply':'No matching reminder can be changed. Check Reminders for scheduled or due reminders.'}
                if len(matches)>1:return {'reply':'More than one reminder matches. Say its exact text or use its Edit or Snooze button in Reminders.'}
                r=matches[0];value={'revision':r['revision'],'requestId':request_id}
                if move:
                    when=move[2]
                    if re.match(r'^\d',when):when='at '+when
                    due=reminder_deadline(when,self.clock(),r['timeZone']);local=datetime.fromtimestamp(due,zone(r['timeZone']))
                    value.update(localDate=local.strftime('%Y-%m-%d'),localTime=local.strftime('%H:%M:%S'),timeZone=r['timeZone'])
                    result=await self.reschedule(r['id'],value,chat_fingerprint=fingerprint)
                else:
                    duration=again[1] if again else snooze[2]
                    intent=timer_intent('Set a timer for '+duration)
                    if not intent or intent['operation']!='create':return {'reply':'Give a clear snooze duration up to 24 hours, for example ten minutes. The reminder was not changed.'}
                    value['seconds']=intent['durationSeconds'];result=await self.snooze(r['id'],value,chat_fingerprint=fingerprint)
            r=result['reminder'];result['reply']='Reminder '+('moved to ' if kind=='reschedule' else 'snoozed until ')+due_phrase(r['dueAt']/1000,r['timeZone'])+': '+r['text'].rstrip('.!?')+'.'
            return result
        except ValueError:return {'reply':'Choose a valid date and time. The reminder was not changed.'}
        except JuneError as e:
            if e.status>=500:raise
            return {'reply':e.message}
    async def chat(self,question,request_id,*,conversation=None,turn=None):
        if nonliteral_request(question):return None
        q=question.strip();q=re.sub(r'^(?:hey )?june[,!:\s]+','',q,flags=re.I)
        q=re.sub(r'^(?:please )?(?:(?:can|could|would) you )?(?:please )?','',q,flags=re.I)
        repeating=await self._chat_series(q,request_id,conversation,turn)
        if repeating:return repeating
        changed=await self._chat_change(q,request_id)
        if changed:
            if 'reminder' in changed:self._link(changed['reminder']['id'],conversation,turn)
            return changed
        start=re.fullmatch(r'remind me (.+?) to (.+)',q,flags=re.I|re.S)
        inverted=re.fullmatch(r'remind me to (.+?) ((?:(?:today|tomorrow|on \d{4}-\d{2}-\d{2}) )?at \d{1,2}(?::\d{2})?\s*(?:am|pm)?|in .+?)[.!]?',q,flags=re.I|re.S) if not start else None
        if start or inverted:
            when,text=start.groups() if start else (inverted[2],inverted[1])
            now=self.clock();today=datetime.fromtimestamp(now,zone(self.time_zone)).date()
            try:
                due=reminder_deadline(when,now,self.time_zone)
                fingerprint=hashlib.sha256(re.sub(r'\s+',' ',q).encode()).hexdigest()
                result=await self._create_at(text,due,self.time_zone,request_id,conversation,turn,fingerprint=fingerprint)
                due=result['reminder']['dueAt']/1000
                result['reply']='Reminder set for '+due_phrase(due,self.time_zone)+': '+text.strip().rstrip('.!?')+'. June must be running; spoken alerts need this page open and voice ready.'
                return result
            except ValueError:return {'reply':'Choose a valid time and date. No reminder was set.'}
            except JuneError as e:
                if e.status>=500:raise
                return {'reply':e.message}
        if re.match(r'^remind me\b',q,re.I):return {'reply':'Include a time and what to remember, for example: Remind me tomorrow at 6 PM to stretch.'}
        cancel=re.fullmatch(r'(?:cancel|delete|stop|remove) (?:my |the |a )?reminder(?: (?:to |about |for |called |named )?(.+?))?[.!?]?',q,re.I)
        if not cancel:
            # "cancel my drink water reminder": the name comes before the word.
            cancel=re.fullmatch(r'(?:cancel|delete|stop|remove) (?:my |the |a )?((?:[\w’\'-]+ ){1,6}?)reminder[.!?]?',q,re.I)
        listed=re.fullmatch(r'(?:show|list)(?: me)?(?: my| the)? reminders[?.!]?|what reminders do i have[?.!]?|what are my reminders[?.!]?|(?:do i have )?any reminders[?.!]?|when is my next reminder[?.!]?',q,re.I)
        if cancel or listed:
            state=await self.state();active=[r for r in state['reminders'] if r['status']=='active']
            if cancel:
                name=(cancel[1] or '').strip().rstrip('.!?').casefold()
                matches=[r for r in active if not name or r['text'].strip().rstrip('.!?').casefold()==name]
                if not matches:return {'reply':'No matching scheduled reminder was cancelled. Check Reminders for the current list.'}
                if len(matches)>1:return {'reply':'More than one reminder matches. Say its text or use its Cancel button in Reminders.'}
                result=await self.cancel(matches[0]['id'],revision=matches[0]['revision']);result['reply']='That reminder is cancelled.';self._link(result['reminder']['id'],conversation,turn);return result
            if not active:return {'reply':'You have no scheduled reminders. Due reminders stay in Reminders until dismissed.'}
            return {'reply':'; '.join(r['text']+' — '+due_phrase(r['dueAt']/1000,r['timeZone']) for r in sorted(active,key=lambda r:r['dueAt']))+'.'}
        return None
