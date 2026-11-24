"""Ephemeral voice consent from server-observed native playback and captured turns.

This establishes a fresh interaction, NOT speaker identity. Nothing here authorises
real payments. A process restart intentionally loses every armed nonce.
"""
import asyncio
import re
import time
import uuid
from .commerce import APPROVAL
from .app_info import nonliteral_request
from .errors import JuneError
from .commerce_merchants import fingerprint


def normal(text):return re.sub(r'\s+',' ',str(text)).strip().casefold()


def approval_text(text):
    cleaned=re.sub(r'^\s*(?:hey\s+)?june[,!:\s]*','',str(text),flags=re.I)
    return re.sub(r'\s+',' ',cleaned).strip().rstrip('.!')


class VoiceConsent:
    def __init__(self,commerce,native,clock=time.monotonic):
        self.commerce,self.native,self.clock=commerce,native,clock
        self.playbacks={};self.turns={};self.armed={};self.replays={};self.sessions={};self.lock=asyncio.Lock()
        commerce.voice=self;native.commerce_consent=self

    def session(self,sid,turn):
        self.sessions[sid]=turn

    def close(self,sid):
        self.sessions.pop(sid,None);self.armed.pop(sid,None)
        self.playbacks={k:v for k,v in self.playbacks.items() if k[0]!=sid}
        self.turns={k:v for k,v in self.turns.items() if k[0]!=sid}

    def disarm_transaction(self,tid):
        self.armed={k:v for k,v in self.armed.items() if v['transaction']!=tid}

    def playback(self,job,phase,segment):
        sid=job.get('voiceSessionId')
        if not sid or sid not in self.sessions:return
        key=(sid,job['request']);record=self.playbacks.setdefault(key,{'segments':{},'started':self.clock()})
        if phase=='start':
            self.armed.pop(sid,None)
            record['segments'][segment]=dict(text=job.get('text',''),done=False)
        elif phase=='end':
            if segment not in record['segments']:return
            record['segments'][segment]['done']=True;record['ended']=self.clock()
        elif phase in ('cancelled','error'):
            record['failed']=True;self.armed.pop(sid,None)
        while len(self.playbacks)>32:self.playbacks.pop(next(iter(self.playbacks)))

    def observe(self,sid,event,started):
        if sid not in self.sessions:return
        number=event.get('turn')
        if type(number) is not int:return
        if event.get('type')=='transcript':
            phrase=approval_text(event.get('text',''))
            if sid in self.armed and (nonliteral_request(phrase) or not APPROVAL.fullmatch(phrase)):
                self.armed.pop(sid,None)
            self.turns[(sid,number)]=dict(text=str(event.get('text','')),started=started,at=self.clock(),used=False)
            while len(self.turns)>32:self.turns.pop(next(iter(self.turns)))

    def healthy(self,sid):
        return (sid in self.sessions and self.native.capture_session==sid and self.native.capture_flowing()
                and self.native.output_error is None)

    async def arm(self,tid,value):
        async with self.lock:
            sid=value['sessionId'];request=value['requestId'];t=self.commerce.get(tid)
            self.armed.pop(sid,None)
            plan=(await self.commerce.plans.get(value['planId']))['plan']
            if t['planId']!=plan['id'] or plan['status']!='proposed' or plan['revision']!=value['revision'] or plan['fingerprint']!=value['fingerprint']:
                raise JuneError('voice-review','Review the exact current simulated quote first.',409)
            record=self.playbacks.get((sid,request));expected=normal(plan['steps'][0]['preview'])
            if not self.healthy(sid) or not record or record.get('failed') or not record.get('ended') or not record['segments'] or not all(s['done'] for s in record['segments'].values()):
                raise JuneError('voice-review','Native playback and echo protection must be healthy and the full review must finish first. Typed or button approval remains available.',409)
            if any(key[0]==sid and turn['at']>record['ended'] for key,turn in self.turns.items()):
                raise JuneError('voice-review','The conversation moved on before voice approval was armed. Read the current quote again.',409)
            heard=normal(' '.join(s['text'] for s in record['segments'].values()))
            if expected not in heard or self.clock()-record['ended']>15:
                raise JuneError('voice-review','June has not finished this exact review recently. Ask her to read it again.',409)
            expiry=min(plan['expiresAt'], t['quote']['expiresAt'] if t['quote'] and plan['steps'][0]['capability']=='commerce.commit' else plan['expiresAt'],round((self.commerce.clock()+60)*1000))
            if expiry<=self.commerce.clock()*1000:raise JuneError('voice-review','That quote expired. Review a fresh one.',409)
            token=uuid.uuid4().hex
            self.armed[sid]=dict(token=token,transaction=tid,plan=plan['id'],revision=plan['revision'],fingerprint=plan['fingerprint'],ended=record['ended'],expiresAt=expiry)
            # Existing follow-up capture listens without another wake phrase.
            turn=self.sessions[sid]
            if turn.phase not in ('followup','listening'):
                await turn.activity(turn.number,'complete')
            if turn.phase=='followup':turn.deadline=turn.clock()+min(60,(expiry-self.commerce.clock()*1000)/1000)
            t['status']='awaiting-approval';self.commerce.save(t)
            return self.commerce.plans.envelope(reviewToken=token,expiresAt=expiry)

    async def approve(self,pid,value):
        async with self.lock:
            signature=fingerprint([pid,value])
            old=self.replays.get(value['requestId'])
            if old:
                if old['signature']!=signature:raise JuneError('request-conflict','This approval request changed.',409)
                return await self.commerce.plans.get(pid)
            sid=value['sessionId'];armed=self.armed.get(sid);turn=self.turns.get((sid,value['turnId']))
            if not armed or armed['token']!=value['reviewToken'] or armed['plan']!=pid or value['revision']!=armed['revision'] or value['fingerprint']!=armed['fingerprint']:
                raise JuneError('voice-approval','No matching current voice review is armed.',409)
            if not self.healthy(sid) or armed['expiresAt']<=self.commerce.clock()*1000:
                self.armed.pop(sid,None);raise JuneError('voice-approval','Voice approval expired or audio is unhealthy. Review again.',409)
            if not turn or turn['used'] or turn['started']<armed['ended'] or turn['at']<armed['ended']:
                raise JuneError('voice-approval','Only a fresh captured reply after the full review can approve.',409)
            text=approval_text(turn['text'])
            if nonliteral_request(text) or not APPROVAL.fullmatch(text):
                self.armed.pop(sid,None)
                raise JuneError('voice-approval','That was not an explicit go-ahead for this quote. No action was executed; review again.',409)
            turn['used']=True;self.armed.pop(sid,None)
            result=await self.commerce.plans.approve(pid,{k:value[k] for k in ('requestId','revision','fingerprint')})
            self.replays[value['requestId']]=dict(signature=signature)
            while len(self.replays)>64:self.replays.pop(next(iter(self.replays)))
            return result
