"""Local simulated commerce. Only approved, immutable plans can commit a fixture."""
import asyncio
import difflib
from datetime import datetime,timedelta
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
from zoneinfo import ZoneInfo
from .errors import JuneError
from .tool_plans import Capability
from .commerce_merchants import SimMerchants,fingerprint,rupees
from .app_info import nonliteral_request

DOMAINS=('retail','tickets','dining')
NUMBER_WORD=r'(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|lakh|and)'
NUMBER_PHRASE=NUMBER_WORD+r'(?:[ -]+'+NUMBER_WORD+r'){0,10}'
# Changes the choosing/quoted flow already understands ("cheaper", "different venue", "option 2", "make it 3").
CHOICE_CHANGE=re.compile(r'^(?:choose|select|option|make it \d|change (?:the )?(?:area|city|location|cinema|venue|restaurant|date|time|budget|quantity)|cheaper|later (?:show|time)|different (?:cinema|venue|restaurant|time)|under|budget|up to|maximum)\b|\b(?:headphones|milk|wheelchair|accessible seats|aisle)\b')
QUESTION_OR_COMMAND=re.compile(r'^(?:what|who|why|how|when|where|which|is|are|was|were|do|does|did|will|would|can|could|should|shall|tell me|play|pause|resume|open|launch|remind|set|show|find|apply|send|read|search|call|text|email|turn|stop|cancel|change)\b')


def low_information_choice(text):
    """A short reply to the options that says nothing usable ("Television.", "Hmm.", a misheard word): ask again.
    Questions, commands and anything the choosing flow understands are left to their normal handlers."""
    low=text.casefold().strip().rstrip('.!')  # the caller's original text: a question mark must survive
    if not low or low.endswith('?') or len(low)>40 or len(low.split())>4:return False
    if QUESTION_OR_COMMAND.match(low) or CHOICE_CHANGE.search(low) or selection_number(low) is not None or domain_for(low):return False
    return not re.search(r'choos(?:e|ing)|you choose|for me',low)


# "Proceed", "okay", "yes, go ahead"… said before there is a quote: a request to continue, never an approval.
CONTINUE=re.compile(r"(?:(?:yes|yeah|yep|ok|okay|sure|alright|all right|please|so|then|now)[,\s]+)*"
                    r"(?:proceed|continue|go on|go ahead|carry on|next|do it|book it|place the order|confirm|i approve|let'?s go|let'?s do it|sounds good|"
                    r"fine|ok|okay|yes|yeah|yep|sure|alright|all right|done|go)(?:[,\s]+(?:please|then|now))*")
# A spoken answer to "How many people?": "two", "i said two", "we are 4", "just two of us", "three people please".
PARTY_ANSWER=re.compile(r"(?:(?:i said|i told you|i meant|we are|we're|it's|it is|just|only|for|um|uh|so|no|like)[,\s]+)*(\d{1,2}|"+NUMBER_PHRASE+r")(?:\s+(?:people|persons?|guests?|of us|adults?))?(?:[,\s]+please)?")
APPROVAL=re.compile(r'(?:(?:yes|yeah|okay|ok)[, ]+)?(?:please[, ]+)?(?:i approve(?: (?:it|this|the (?:purchase|booking|order)))?|go ahead(?: and (?:book it|place the order))?|book it|place the order|confirm (?:the )?(?:purchase|booking|order|reservation))(?:[, ]+please)?',re.I)
REQUIRED={'retail':('item','area','budgetMinor','delivery'),'tickets':('event','area','date','time','partySize','budgetMinor','venue'),'dining':('area','date','time','partySize','venue')}
APPROVAL_LIKE=re.compile(r'(?:(?:yes|okay|ok|please)[, ]+)*(?:i approve|go ahead|book it|place the order|confirm)\b',re.I)
ACKNOWLEDGEMENT=re.compile(r'(?:yes|yeah|yep|yup|ok|okay|sure|fine|alright|all right|do it|right|correct|sounds good|perfect(?:[, ]+thanks)?|great(?:[, ]+thanks)?|thanks|(?:yeah[, ]+)?go for it)',re.I)
APPROVAL_WORDS=re.compile(r'\b(?:approv(?:e|al)|go ahead|go for it|book it|place the order|confirm)\b',re.I)
QUESTIONS={'item':'Which fixture product: milk, a book, or headphones?','event':'Which movie or event title should I use for the simulation?','area':'Which city and locality should this simulation use? I do not have your GPS location.','budgetMinor':'What is your maximum total budget in rupees, including fees?','delivery':'Which delivery date should I use?','date':'Which date?','time':'What time, including AM or PM?','partySize':'How many people?','venue':'Which simulated venue do you prefer, or should I choose for you?'}
SECRET=re.compile(r'\b(?:cvv|cvc|otp|upi\s*pin|card\s*(?:number|details)|bank\s*(?:password|pin)|payment\s*pin)\b',re.I)


def selection_number(text):
    clean=re.sub(r'\s+',' ',text.lower()).strip().rstrip('.!?')
    match=re.fullmatch(r'(?:(?:choose|select|option)\s+)?(?:the\s+)?(first|second|third|one|two|three|[1-9])(?:\s+(?:one|option))?',clean)
    if not match:return None
    return int(match[1]) if match[1].isdigit() else {'first':1,'one':1,'second':2,'two':2,'third':3,'three':3}[match[1]]


# "Choose for me" as people say it, including how speech recognition commonly mishears it ("choose from me").
DELEGATE=re.compile(r"\b(?:(?:choos(?:e|ing)|chose|choice|pick|decide|select)\s+(?:for|from|on behalf of)\s+(?:me|us)|you (?:choose|pick|decide|select)|"
                    r"(?:your|any) (?:choice|pick)|no preference|(?:doesn'?t|does not) matter|surprise me|up to you|"
                    r"(?:^|\s)(?:any|anything|whatever|whichever|either)(?: one| venue| restaurant| cinema| place)?(?: is| works)?(?: fine| okay| ok| good)?\s*$)",re.I)


def valid_venue(domain,value):
    if DELEGATE.search(value.strip().rstrip('.!')) or value.lower() in ('choose for me','any','no preference','you choose'):return 'choose for me'
    names={'tickets':('Sim Cinema Centre','Sim Cinema Park'),'dining':('Sim Table Garden','Sim Table Central')}.get(domain,())
    clean=re.sub(r'^(?:the|at|i said|i want|let.?s go (?:to|with))\s+','',value.strip().rstrip('.!').casefold())
    # "table garden", "the garden one", "central": a unique part of one venue's name is enough.
    matches=[name for name in names if clean==name.casefold() or (len(clean)>=4 and all(w in name.casefold() for w in re.findall(r'[a-z]{4,}',clean)) and re.findall(r'[a-z]{4,}',clean))]
    return matches[0] if len(matches)==1 else None


KNOWN_PLACES=('Noida','Greater Noida','Delhi','New Delhi','Gurgaon','Gurugram','Ghaziabad','Faridabad','Kanpur','Lucknow','Mumbai','Bengaluru',
              'Bangalore','Hyderabad','Chennai','Kolkata','Pune','Jaipur','Chandigarh','Ahmedabad','Indore','Bhopal','Patna','Varanasi','Agra',
              'Meerut','Dehradun','Surat','Nagpur','Kochi','Goa','Mohali','Allahabad','Prayagraj','Amritsar','Ludhiana','Mysuru','Coimbatore')
_COMMON=None


def common_words():
    """Ordinary lower-case English words (the system word list); place names are not in it."""
    global _COMMON
    if _COMMON is None:
        try:_COMMON=frozenset(w.strip() for w in open('/usr/share/dict/words',encoding='utf-8') if w.strip().islower())
        except OSError:_COMMON=frozenset()
    return _COMMON


def place_answer(text):
    """An answer to "Which city?": (place, None) when it is usable, (None, heard) when June should ask again."""
    clean=re.sub(r"^\s*(?:hey\s+ju\w*[,\s]+)?(?:(?:i said|i told you|it'?s|it is|in|at|the city is|city is|near)[,\s]+)*",'',text.strip(),flags=re.I).strip().rstrip('.!?,')
    if not clean:return None,text.strip()
    known=difflib.get_close_matches(clean.title(),KNOWN_PLACES,n=1,cutoff=.8)
    if known:return known[0],None
    words=clean.split()
    if len(words)==1 and (words[0].lower() in common_words() or len(words[0])<3):return None,clean  # "Night", "Yes", "T"
    return clean,None


def protect(text):
    # Contextual guards, not a claim to recognise arbitrary secrets or every PIN.
    if SECRET.search(text) or re.search(r'(?<!\d)(?:\d[ -]?){13,19}(?!\d)',text):
        raise JuneError('payment-secret','Do not share card numbers, CVV, PIN or OTP with June. This simulation uses no payment credentials.',400)


def domain_for(text):
    low=text.strip().rstrip('.!?')
    if APPROVAL.fullmatch(low) or re.match(r'^(?:cancel|stop|check|status|remember|forget)\b',low,re.I):return None
    if re.search(r'\b(?:book|reserve)\b.*\b(?:restaurant|table|dining)\b',text,re.I):return 'dining'
    if re.search(r'^\W*(?:(?:hey\s+)?ju\w*\W+)?(?:a\s+)?table\s+for\s+\w+',text,re.I):return 'dining'  # "table for two in Noida tomorrow" 
    if re.search(r'\b(?:book|buy|reserve)\b.*\b(?:movie|cinema|tickets?|theatre)\b',text,re.I):return 'tickets'
    if re.search(r'\b(?:buy|purchase|order)\b',text,re.I) and not re.search(r'\b(?:job|apply|email|pizza|stocks?|shares?)\b',text,re.I):return 'retail'


def cancellation_review(t):
    q=t.get('quote') or {};selection=q.get('selection') or {}
    title=selection.get('title',t['domain']+' order');merchant=q.get('merchant','the simulated merchant')
    refund='No charge and no cancellation fee.' if t['domain']=='dining' else f'Full simulated refund {rupees(t["receipt"]["totalMinor"])}. No cancellation fee.'
    return f'Simulation: cancel {title} with {merchant}. {refund} No real money moves.'


class Commerce:
    def __init__(self,directory,plans,clock=time.time):
        self._clarify=None  # one turn's "which city is that?" question, set by extract()
        self.plans,self.clock=plans,clock;self.merchant=SimMerchants();self.lock=asyncio.Lock()
        folder=Path(directory)/'tools';folder.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.path=folder/'commerce.sqlite3';fd=os.open(self.path,os.O_CREAT|os.O_RDWR,0o600);os.close(fd);self.path.chmod(0o600)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS transactions(id TEXT PRIMARY KEY,conversation TEXT NOT NULL,document TEXT NOT NULL,at REAL NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,signature TEXT NOT NULL,response TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS inventory(key TEXT PRIMARY KEY,transaction_id TEXT NOT NULL)')
            for row in db.execute('SELECT document FROM transactions').fetchall():
                t=json.loads(row[0])
                if t['status']=='executing':t['status']='unknown';self.save(t,db)
                elif t['status']=='awaiting-approval':t['status']='quoted';self.save(t,db)
        self.voice=None

    def db(self):
        db=sqlite3.connect(self.path,timeout=3);db.row_factory=sqlite3.Row;return db

    def save(self,t,db=None):
        if db is None:
            with self.db() as store:self.save(t,store)
        else:db.execute('INSERT OR REPLACE INTO transactions VALUES(?,?,?,?)',(t['id'],t['conversationId'],json.dumps(t,ensure_ascii=False),self.clock()))

    def get(self,tid):
        with self.db() as db:row=db.execute('SELECT document FROM transactions WHERE id=?',(tid,)).fetchone()
        if row is None:raise JuneError('transaction-missing','That simulation was not found.',404)
        return json.loads(row[0])

    def current(self,conversation):
        try:
            with self.db() as db:row=db.execute('SELECT document FROM transactions WHERE conversation=? ORDER BY at DESC,rowid DESC LIMIT 1',(conversation,)).fetchone()
        except sqlite3.Error:
            return None  # An unavailable optional commerce store must not break unrelated chat.
        return json.loads(row[0]) if row else None

    def state(self):
        with self.db() as db:
            rows=db.execute('SELECT document FROM transactions ORDER BY at DESC,rowid DESC LIMIT 20').fetchall()
            prefs=dict(db.execute('SELECT key,value FROM preferences'))
        return self.plans.envelope(transactions=[json.loads(r[0]) for r in rows],preferences=prefs)

    def occupied(self,t,db=None):
        if t['domain']=='retail':
            if db is None:
                with self.db() as store:return self.occupied(t,store)
            return [r[0] for r in db.execute('SELECT key FROM inventory WHERE key LIKE ?',('retail|'+t['slots'].get('item','')+'|%',))]
        key=f'{t["slots"].get("area")}|{t["slots"].get("date")}|{t["slots"].get("time")}|'
        if db is None:
            with self.db() as store:return self.occupied(t,store)
        return [r[0][len(key):] for r in db.execute('SELECT key FROM inventory WHERE key LIKE ?',(key+'%',))]

    def handles(self,text,conversation):
        if domain_for(text):return True
        t=self.current(conversation)
        low=text.lower().strip().rstrip('.!?')
        if re.match(r'^(?:remember|forget) (?:my )?(?:area|venue|seat preference)\b',low):return True
        if t is None:return False
        if re.fullmatch(r'(?:status|check (?:the )?(?:receipt|booking|order)|cancel(?: (?:the |my |that )?(?:booking|order|reservation|purchase))?|stop|never mind|nevermind)',low):return True
        if t['status'] in ('collecting','choosing') and CONTINUE.fullmatch(low):return True  # answered by commerce, never the model
        if t.get('planId') and (APPROVAL_WORDS.search(low) or ACKNOWLEDGEMENT.fullmatch(low) or re.fullmatch(r'(?:read|repeat|reread)(?: the)?(?: current)? quote(?: again)?',low)):
            return t['status'] in ('quoted','awaiting-approval','completed')
        if re.match(r'^(?:what|who|why|how|tell me|can you|could you|play|pause|resume|open|launch|remind|set a|show|find|apply|send|read|search|change (?:the )?(?:song|music|playlist))\b',low):return False
        if t['status']=='choosing' and (selection_number(low) is not None or low in ('choose for me','you choose','just choose for me','choose best')):return True
        if t['status']=='collecting':
            target=next((k for k in REQUIRED[t['domain']] if k not in t['slots']),None)
            if target in ('area','venue','event'):return len(text)<=100
            if target=='item':return bool(re.search(r'\b(?:milk|books?|headphones)\b',low))
            if target in ('date','delivery'):return bool(re.search(r'\b(?:today|tomorrow|\d{4}-\d{2}-\d{2})\b',low))
            if target=='time':return bool(re.search(r'\d.*(?:am|pm|:)',low))
            if target in ('partySize','budgetMinor'):return bool(re.search(r'\d',low) or self.spoken_number(low) is not None or (target=='partySize' and PARTY_ANSWER.fullmatch(low)))
        if t['status']=='choosing' and low_information_choice(text):return True  # "Television.": ask which option, never the model
        return t['status'] in ('choosing','quoted','awaiting-approval') and bool(CHOICE_CHANGE.search(low))

    @staticmethod
    def spoken_number(text):
        values={'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}
        words=re.sub(r'\b(?:rupees?|and|only)\b','',text.lower()).replace('-',' ').split()
        total=current=0
        if not words:return None
        for word in words:
            if word in values:current+=values[word]
            elif word=='hundred':current=max(1,current)*100
            elif word in ('thousand','lakh'):total+=max(1,current)*(1000 if word=='thousand' else 100000);current=0
            else:return None
        return total+current

    def extract(self,text,t,starting=False):
        slots=t['slots'];low=text.lower().strip().rstrip('.!?');low=re.sub(r'\b([ap])\s*\.\s*m\s*\.?',r'\1m',low);missing=[k for k in REQUIRED[t['domain']] if k not in slots]
        target=missing[0] if missing else None
        if t['domain']=='tickets' and 'event' not in slots:
            named=re.search(r'(?:tickets? for|movie tickets? for|book (?:a |the )?movie)\s+(.+?)(?=\s+(?:in|on|at|tomorrow|today|under|with|for \d)\b|$)',text,re.I)
            if named and named[1].lower() not in ('tickets','ticket') and not APPROVAL.search(named[1]):slots['event']=re.sub(r'^tickets? for\s+','',named[1].strip(),flags=re.I)[:100]
        products=[item for item in ('headphones','milk','book') if re.search(r'\b'+item+r's?\b',low)]
        if t['domain']=='retail' and len(products)>1:raise JuneError('multiple-products','This offline fixture supports one product per cart. Choose milk, a book, or headphones; I will not silently drop an item.',400)
        for item in ('headphones','milk','book'):
            if t['domain']=='retail' and re.search(r'\b'+item+r's?\b',low):slots['item']=item
        area=re.search(r'\bin\s+([a-zA-Z][a-zA-Z ,.-]{1,60}?)(?=\s+(?:tomorrow|today|on|at|for|under|with)\b|$)',text,re.I)
        if area:slots['area']=area[1].strip()
        changed_area=re.search(r'(?:area|city|location)\s+(?:to|is)\s+(.{1,80})$',text,re.I)
        if changed_area:slots['area']=changed_area[1].strip()
        changed_venue=re.search(r'(?:cinema|venue|restaurant)\s+(?:to|is)\s+(.{1,80})$',text,re.I)
        if changed_venue:slots['venue']=changed_venue[1].strip()
        budget=re.search(r'(?:under|budget(?:\s+is)?|up to|max(?:imum)?)\s*[₹]?\s*(\d+(?:\.\d{1,2})?)',low)
        if budget:slots['budgetMinor']=self.money(budget[1])
        else:
            spoken_budget=re.search(r'(?:under|budget(?:\s+is)?|up to|max(?:imum)?)\s+('+NUMBER_PHRASE+r')\b',low)
            if spoken_budget:
                amount=self.spoken_number(spoken_budget[1])
                if amount is not None:slots['budgetMinor']=self.money(str(amount))
        people=re.search(r'(?:for\s+)?(\d{1,3}|'+NUMBER_PHRASE+r')\s+(?:people|persons?|guests?|adults?|tickets?|seats?|of us)\b',low)
        # "a table for two", "party of four" (never "a table for 8 pm": a time is not a party size).
        if not people and t['domain']=='dining':
            people=re.search(r'\b(?:table|reservation|booking|party)\s+(?:for|of)\s+(\d{1,2}|'+NUMBER_PHRASE+r')\b(?!\s*(?:pm|am|p\.?m|a\.?m|:|o.?clock))',low)
        if people:slots['partySize']=int(people[1]) if people[1].isdigit() else self.spoken_number(people[1])
        correction=re.fullmatch(r'make it (\d{1,2})',low)
        if correction and t['domain']!='retail':slots['partySize']=int(correction[1])
        if 'wheelchair' in low or 'accessible seats' in low:slots['accessibility']='wheelchair'
        if 'aisle' in low:slots['seatPreference']='aisle'
        qty=re.search(r'(?:buy|order|quantity|make it)\s+(\d{1,3}|'+NUMBER_PHRASE+r')\b',low)
        if qty and t['domain']=='retail':slots['quantity']=int(qty[1]) if qty[1].isdigit() else self.spoken_number(qty[1])
        today=datetime.fromtimestamp(self.clock(),ZoneInfo('Asia/Kolkata')).date()
        date=None
        if re.search(r'\btomorrow\b',low):date=(today+timedelta(days=1)).isoformat()
        elif re.search(r'\btoday\b',low):date=today.isoformat()
        else:
            match=re.search(r'\b(\d{4}-\d{2}-\d{2})\b',low)
            if match:
                try:date=datetime.strptime(match[1],'%Y-%m-%d').date().isoformat()
                except ValueError:raise JuneError('invalid-date','Use a valid date, for example 2026-12-01.',400)
        if date:
            if date<today.isoformat():raise JuneError('invalid-date','Choose today or a future date.',400)
            slots['delivery' if t['domain']=='retail' else 'date']=date
        tm=re.search(r'\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)(?::(\d{2}))?\s*(am|pm)\b',low)
        if tm:
            hour,minute=(int(tm[1]) if tm[1].isdigit() else self.spoken_number(tm[1])),int(tm[2] or 0)
            if not 1<=hour<=12 or minute>59:raise JuneError('invalid-time','Choose a valid time including AM or PM.',400)
            slots['time']=f'{hour%12+(12 if tm[3]=="pm" else 0):02}:{minute:02}'
        if re.search(r'choos(?:e|ing) for me|you choose|no preference|any venue',low) or (target=='venue' and DELEGATE.search(low.rstrip('.!'))):slots['venue']='choose for me'
        if target=='budgetMinor' and not budget:
            amount=self.spoken_number(low)
            if amount is not None:slots['budgetMinor']=self.money(str(amount))
        if target=='partySize' and not low.isdigit() and 'partySize' not in slots:
            answer=PARTY_ANSWER.fullmatch(low)
            number=self.spoken_number(answer[1]) if answer and not answer[1].isdigit() else int(answer[1]) if answer else self.spoken_number(low)
            if number is not None:slots['partySize']=number
        if target=='time' and not tm:
            clock24=re.fullmatch(r'(?:at )?([01]?\d|2[0-3]):([0-5]\d)',low)
            if clock24:slots['time']=f'{int(clock24[1]):02}:{clock24[2]}'
        if not starting and target=='area' and not area and len(text)<=80 and not date and not tm:
            place,heard=place_answer(text)
            if place:slots['area']=place
            else:self._clarify=f'I heard “{heard}”. Which city or locality is that?'  # no example places: the echo matcher would reject them
        elif not starting and target=='event' and not re.search(r'\b(?:book|ticket)\b',low):
            if APPROVAL.search(text):raise JuneError('invalid-event','Use a neutral event title; approval words cannot be part of the spoken review.',400)
            slots['event']=text.strip()[:100]
        elif target=='budgetMinor' and re.fullmatch(r'[₹]?\s*\d+(?:\.\d{1,2})?',low):slots['budgetMinor']=self.money(low.replace('₹','').strip())
        elif target=='partySize' and low.isdigit():slots['partySize']=int(low)
        elif not starting and target=='venue' and not tm and not date and 'venue' not in slots:slots['venue']=text.strip()[:80]
        if 'venue' in slots and t['domain'] in ('tickets','dining'):
            venue=valid_venue(t['domain'],str(slots['venue']))
            if venue is None:slots.pop('venue',None)
            else:slots['venue']=venue
        if 'partySize' in slots and not 1<=slots['partySize']<=8:raise JuneError('invalid-party','Choose between 1 and 8 people for this fixture.',400)
        if not 1<=slots.get('quantity',1)<=10:raise JuneError('invalid-quantity','Choose 1 to 10 items.',400)

    @staticmethod
    def money(value):
        whole,_,fraction=value.partition('.')
        n=int(whole)*100+int((fraction+'00')[:2])
        if not 0<n<=10000000:raise JuneError('invalid-budget','Use a budget above zero and at most ₹100,000.',400)
        return n

    def result(self,t,reply,plan=None):
        t['lastReply']=reply;self.save(t)
        return self.plans.envelope(reply=reply,transaction=t,**({'plan':plan} if plan else {}))

    async def respond(self,request_id,conversation,text=None,select=None):
        if select is not None:
            if text is not None or not isinstance(select,dict) or set(select)!={'offerId'} or not isinstance(select['offerId'],str):
                raise JuneError('invalid-commerce','Select one current offer without free text.',400)
            text='select:'+select['offerId']
        if not isinstance(text,str) or not 1<=len(text.strip())<=2000:raise JuneError('invalid-commerce','Use a short shopping or booking request.',400)
        if not isinstance(conversation,str) or not re.fullmatch(r'[\w-]{1,128}',conversation):raise JuneError('invalid-commerce','Use a valid conversation id.',400)
        if not isinstance(request_id,str) or not re.fullmatch(r'[\w-]{8,128}',request_id):raise JuneError('invalid-commerce','Use a valid request id.',400)
        protect(text)
        async with self.lock:
            signature=fingerprint([conversation,text])
            with self.db() as db:old=db.execute('SELECT * FROM requests WHERE id=?',(request_id,)).fetchone()
            if old:
                if old['signature']!=signature:raise JuneError('request-conflict','This request id already belongs to another request.',409)
                return json.loads(old['response'])
            if select is not None:
                current=self.current(conversation)
                n=next((i for i,o in enumerate(current['offers'],1) if o['id']==select['offerId']),None) if current else None
                if n is None or current['status']!='choosing':raise JuneError('stale-offer','That offer is no longer current. Read the latest options.',409)
                effective='choose '+str(n)
            else:effective=text
            reply=await self._respond(conversation,effective)
            with self.db() as db:db.execute('INSERT INTO requests VALUES(?,?,?)',(request_id,signature,json.dumps(reply)))
            return reply

    async def _respond(self,conversation,text):
        low=text.lower().strip().rstrip('.!?');t=self.current(conversation);domain=domain_for(text)
        if (nonliteral_request(text) and not re.match(r'^(?:please )?(?:buy|purchase|order|book|reserve)\b',low)) or re.match(r'^(?:how|why|what is|write|quote|imagine|suppose)\b',low):return self.plans.envelope(reply='Simulation: ask me to buy a fixture product, book movie tickets, or reserve a restaurant table. No real purchases are available.')
        if low.startswith(('remember ','forget ')):
            m=re.fullmatch(r'(remember|forget) (?:my )?(area|venue|seat preference)(?: is| as|:)?\s*(.*)',text,re.I)
            if not m or (m[1].lower()=='remember' and not m[3].strip()):return self.plans.envelope(reply='Simulation: say “remember my area as Noida” or “forget my area”.')
            prefkey='seatPreference' if m[2].lower()=='seat preference' else m[2].lower()
            with self.db() as db:
                if m[1].lower()=='forget':db.execute('DELETE FROM preferences WHERE key=?',(prefkey,))
                else:db.execute('INSERT OR REPLACE INTO preferences VALUES(?,?)',(prefkey,m[3].strip()[:100]))
            return self.plans.envelope(reply='Simulation: preference '+('forgotten.' if m[1].lower()=='forget' else 'remembered at your request.'))
        if domain:
            t=dict(id=uuid.uuid4().hex,conversationId=conversation,domain=domain,status='collecting',simulated=True,slots={},missing=[],offers=[],quote=None,planId=None,receipt=None,lastReply='')
            with self.db() as db:prefs=dict(db.execute('SELECT key,value FROM preferences'))
            for k in ('area','venue','seatPreference'):
                if k in prefs:t['slots'][k]=prefs[k]
        if t is None:return self.plans.envelope(reply='Simulation: start a product purchase, movie ticket booking, or restaurant reservation first.')
        if re.search(r"\b(?:do not|don't|never)\s+(?:buy|book|purchase|order|proceed)\b",low):
            if t['status'] not in ('completed','unknown','cancelled'):
                await self.invalidate(t);t['status']='cancelled'
            return self.result(t,'Simulation: no further action will be taken. Completed orders need a separate cancellation.')
        if low in ('status','check receipt','check the receipt','check booking','check order'):
            if t['receipt'] and t['status']=='unknown':t['status']='completed' if t['receipt']['status']=='confirmed' else 'cancelled'
            return self.result(t,'Simulation: '+(t['receipt']['detail'] if t['receipt'] else 'No confirmed receipt exists. Nothing will be retried.'))
        if re.fullmatch(r'(?:stop|never mind|nevermind|cancel)',low):
            if t['status'] in ('completed','unknown','cancelled'):return self.result(t,'Simulation: a completed or uncertain order is not undone by Stop. Ask to cancel the booking or check its receipt.')
            await self.invalidate(t);t['status']='cancelled'
            return self.result(t,'Simulation: stopped. No purchase or booking was made.')
        if re.fullmatch(r'cancel (?:the |my |that )?(?:booking|order|reservation|purchase)',low):
            if not t['receipt']:
                if t['quote']:
                    await self.invalidate(t);t['status']='cancelled'
                    return self.result(t,'Simulation: unexecuted quote cancelled. No purchase was made.')
                return self.result(t,'Simulation: there is no confirmed order to cancel. Check an uncertain receipt first.')
            reply=await self.plans.propose(dict(requestId=uuid.uuid4().hex,intent='commerce-cancel',input={'id':t['id']}))
            t['planId']=reply['plan']['id']
            return self.result(t,reply['plan']['steps'][0]['preview']+' Shall I proceed?',reply['plan'])
        if t['status'] in ('collecting','choosing') and not domain and CONTINUE.fullmatch(low):
            # Nothing to approve yet: say what is still needed (no plan exists, nothing can commit).
            if t['status']=='choosing':return self.result(t,'Simulation: Tell me the number of the option you want.')
            missing=[k for k in REQUIRED[t['domain']] if k not in t['slots']]
            return self.result(t,'Simulation: '+(QUESTIONS[missing[0]] if missing else 'Tell me the number of the option you want.'))
        if t.get('planId') and (APPROVAL_WORDS.search(low) or ACKNOWLEDGEMENT.fullmatch(low) or re.fullmatch(r'(?:read|repeat|reread)(?: the)?(?: current)? quote(?: again)?',low)):
            active_plan=(await self.plans.get(t['planId']))['plan']
            conditional=bool(re.search(r"\b(?:but|if|with|make it|later|instead|cheaper|change|different|tomorrow|not|never)\b|don['’]?t",low))
            if conditional and APPROVAL_WORDS.search(low) and active_plan['status']=='proposed':
                await self.invalidate(t);t['status']='choosing'
                return self.result(t,'Simulation: I did not treat that as approval. The previous review is cancelled. Tell me what to change, then review the new quote; no action was executed.')
            if active_plan['status']=='proposed':
                return self.result(t,'Simulation: nothing new was executed. Here is the exact review again. '+active_plan['steps'][0]['preview'],active_plan)
            return self.result(t,'Simulation: that review is no longer awaiting approval. Check the receipt or request a fresh quote; nothing was retried.')
        if t['status']=='choosing' and not domain and low_information_choice(text):
            # Clarify only: nothing is selected, quoted or approved from a reply that named no option.
            return self.result(t,'Simulation: I didn’t catch which option. Tell me the number of the option you want.')
        if t['status']=='choosing' and t['offers'] and low in ('choose best','choose for me','you choose','just choose for me'):low='choose 1'
        pick=selection_number(low) if t['status']=='choosing' else None
        if pick is not None:
            n=pick-1
            if t['status']!='choosing' or n>=len(t['offers']):return self.result(t,'Simulation: choose an available option from the current list.')
            offer=t['offers'][n];t['quote']=self.merchant.quote(t['domain'],t['slots'],offer,self.clock);t['status']='quoted';self.save(t)
            reply=await self.plans.propose(dict(requestId=uuid.uuid4().hex,intent='commerce-commit',input={'id':t['id']}));t['planId']=reply['plan']['id']
            return self.result(t,t['quote']['summary'],reply['plan'])
        if t['status'] in ('completed','unknown','cancelled'):
            return self.result(t,'Simulation: start a new shopping or booking request, check the receipt, or ask to cancel this order. An uncertain commit is never retried.')
        if t['quote'] and low=='cheaper':t['slots']['budgetMinor']=max(1,t['quote']['totalMinor']-100)
        if low in ('later show','later time','different time'):t['slots'].pop('time',None)
        if low in ('different cinema','different venue','different restaurant'):t['slots'].pop('venue',None)
        if t['quote']:await self.invalidate(t)
        self._clarify=None
        if low not in ('later show','later time','different time','different cinema','different venue','different restaurant','cheaper'):self.extract(text,t,starting=bool(domain))
        t['missing']=[k for k in REQUIRED[t['domain']] if k not in t['slots']]
        if t['missing']:
            t['status']='collecting';return self.result(t,'Simulation: '+(self._clarify or QUESTIONS[t['missing'][0]]))
        t['offers']=self.merchant.search(t['domain'],t['slots'],self.occupied(t));t['status']='choosing'
        if not t['offers']:return self.result(t,'Simulation: no fixture option meets those choices and budget. Change the budget or venue; I will not substitute or split a group silently.')
        options=' '.join(f'{i}. {o["title"]} — {o["merchant"]}, {('no charge' if t['domain']=='dining' else rupees(o['totalMinor']))}. {o["description"]}' for i,o in enumerate(t['offers'],1))
        # Never quote the user's expected answer words: the realtime echo matcher rejects a reply that repeats them.
        return self.result(t,'Simulation: '+options+' Tell me the number of the option you want.')

    async def invalidate(self,t):
        if self.voice:self.voice.disarm_transaction(t['id'])
        if t.get('planId'):
            plan=(await self.plans.get(t['planId']))['plan']
            if plan['status']=='proposed':await self.plans.cancel(plan['id'],dict(requestId=uuid.uuid4().hex,revision=plan['revision'],fingerprint=plan['fingerprint']))
        t.update(quote=None,planId=None,status='collecting')

    async def commit(self,tid,quote_fingerprint,cancel=False):
        async with self.lock:
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE');t=self.get(tid);q=t['quote']
                if cancel:
                    if t['receipt'] and t['receipt']['status']=='cancelled':return dict(verified=True,message='Simulation: already cancelled. No second refund was issued.')
                    if not t['receipt'] or fingerprint(t['receipt'])!=quote_fingerprint:return dict(verified=False,failed=True,message='Simulation: cancellation details changed; review again.')
                    t['receipt'].update(status='cancelled',detail='Simulated cancellation confirmed. Simulated full refund; no real funds moved.');t['status']='cancelled'
                    db.execute('DELETE FROM inventory WHERE transaction_id=?',(tid,));self.save(t,db)
                    return dict(verified=True,message=t['receipt']['detail'])
                if not q or q['fingerprint']!=quote_fingerprint:return dict(verified=False,failed=True,message='Simulation: this quote was replaced. Review the current selection.')
                if t['receipt']:return dict(verified=True,message='Simulation: existing receipt '+t['receipt']['id']+'. Nothing was purchased again.')
                if t['status']=='unknown':return dict(verified=False,message='Simulation: outcome unknown; receipt check only, no retry.')
                if q['expiresAt']<=self.clock()*1000:
                    t['status']='expired';self.save(t,db);return dict(verified=False,failed=True,message='Simulation: quote expired. Review a fresh quote.')
                fresh=self.merchant.search(t['domain'],t['slots'],self.occupied(t,db));offer=next((o for o in fresh if o['id']==q['selection']['offerId']),None)
                new=self.merchant.quote(t['domain'],t['slots'],offer,self.clock) if offer else None
                if new is None or new['fingerprint']!=q['fingerprint']:
                    t.update(status='choosing',offers=fresh,quote=None,planId=None,lastReply='Simulation: price, seats or availability changed. Choose and review again.');self.save(t,db)
                    return dict(verified=False,failed=True,message=t['lastReply'])
                if t['domain']=='retail':
                    for _ in range(int(t['slots'].get('quantity',1))):db.execute('INSERT INTO inventory VALUES(?,?)',('retail|'+t['slots']['item']+'|'+uuid.uuid4().hex,tid))
                for seat in offer.get('seats',[]):
                    key=f'{t["slots"]["area"]}|{t["slots"]["date"]}|{t["slots"]["time"]}|{offer["merchant"]}|{seat}'
                    db.execute('INSERT INTO inventory VALUES(?,?)',(key,tid))
                receipt=dict(id='sim-'+uuid.uuid4().hex,transactionId=tid,status='confirmed',simulated=True,totalMinor=q['totalMinor'],currency='INR',createdAt=round(self.clock()*1000),detail='Simulation: '+('reservation confirmed; no payment was made.' if t['domain']=='dining' else f'purchase confirmed for {rupees(q["totalMinor"])} using a simulated wallet. No real money moved.'))
                t.update(receipt=receipt,status='unknown' if self.merchant.unknown_after_commit else 'completed');self.save(t,db)
                return dict(verified=not self.merchant.unknown_after_commit,message='Simulation: receipt temporarily unavailable. Check status; do not retry.' if self.merchant.unknown_after_commit else receipt['detail'])


def register(plans,service):
    plans.commerce=service
    for cancel in (False,True):
        cid='commerce.cancel' if cancel else 'commerce.commit';intent='commerce-cancel' if cancel else 'commerce-commit'
        async def execute(payload,cancel=cancel):return await service.commit(payload['id'],payload['fingerprint'],cancel)
        plans.capabilities[cid]=Capability(cid,'Cancel a simulated booking' if cancel else 'Complete a simulated purchase or reservation','simulated-commerce','financial',False,execute)
        def steps(value,cancel=cancel,cid=cid):
            if not isinstance(value,dict) or set(value)!={'id'}:raise JuneError('invalid-commerce','Choose the current simulation.',400)
            t=service.get(value['id']);q=t['quote']
            if cancel:
                if not t['receipt']:raise JuneError('invalid-commerce','No confirmed order to cancel.',409)
                bound=fingerprint(t['receipt']);summary=cancellation_review(t)
            else:
                if not q or t['status'] not in ('quoted','awaiting-approval'):raise JuneError('invalid-commerce','Prepare a current quote first.',409)
                bound=q['fingerprint'];summary=q['summary']
            return [(cid,dict(id=t['id'],fingerprint=bound),summary,'Simulated cancellation' if cancel else 'Simulated '+t['domain'])]
        steps.accepts_input=True;plans.intents[intent]=steps
