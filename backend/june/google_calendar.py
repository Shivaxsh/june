"""Personal desktop OAuth/PKCE for read-only primary-calendar access."""
import asyncio
import base64
from datetime import datetime, timedelta
import hashlib
import json
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit
from zoneinfo import ZoneInfo

from .connector_http import ConnectorHTTP
from .daily_assistant import GOOGLE_HOSTS, clean_text
from .errors import JuneError
from .tool_plans import digest

SCOPE = 'https://www.googleapis.com/auth/calendar.events.readonly'


def calendar_items(value, zone):
    if not isinstance(value,dict) or not isinstance(value.get('items',[]),list):
        raise JuneError('calendar-invalid','Calendar returned an invalid event list.',502)
    result=[]
    for event in value.get('items',[])[:20]:
        if not isinstance(event,dict) or event.get('status')=='cancelled':continue
        title=event.get('summary','Untitled event')
        if not clean_text(title,1000):title='Untitled event'
        if len(title)>260:title=title[:259]+'…'
        start=event.get('start',{})
        if not isinstance(start,dict):continue
        try:
            if 'dateTime' in start:
                moment=datetime.fromisoformat(start['dateTime'].replace('Z','+00:00'))
                if moment.tzinfo is None:continue
                at=round(moment.timestamp()*1000)
                text=f"{moment.astimezone(ZoneInfo(zone)).strftime('%H:%M')}: {title}."
                result.append(dict(text=text,at=at,allDay=False))
            elif 'date' in start:
                datetime.strptime(start['date'],'%Y-%m-%d')
                result.append(dict(text='All day: '+title+'.',allDay=True))
        except (ValueError,TypeError,KeyError):continue
    return result


class GoogleCalendar:
    def __init__(self, daily, keychain, backend, *, clock=time.time):
        origin=urlsplit(backend)
        if origin.scheme!='http' or origin.hostname not in ('127.0.0.1','localhost','::1') or origin.username or origin.password or origin.path not in ('','/') or origin.query or origin.fragment:
            raise ValueError('Google callback requires the local June backend origin')
        self.daily,self.keychain,self.clock=daily,keychain,clock
        self.redirect=backend.rstrip('/')+'/api/connections/google/callback'
        self.pending=None
        self.lock=asyncio.Lock()
        self.requests={}
        self.revoking=False
        self.http=ConnectorHTTP('google',GOOGLE_HOSTS,enabled=lambda: daily.enabled('google') or self.revoking)

    def _request(self,value,operation,allowed):
        if not isinstance(value,dict) or set(value)!=allowed or not isinstance(value.get('requestId'),str) or not re.fullmatch(r'[\w-]{8,128}',value['requestId'],re.ASCII):
            raise JuneError('invalid-google','Use Google’s setup controls in Daily.',400)
        key=value['requestId'];signature=digest([operation,value]);old=self.requests.get(key)
        if old and old[0]>self.clock():
            if old[1]!=signature:raise JuneError('request-conflict','This request id was already used.',409)
            return signature,old[2]
        return signature,None

    def _save_request(self,value,signature,result):
        self.requests={k:v for k,v in self.requests.items() if v[0]>self.clock()}
        if len(self.requests)>50:self.requests.clear()
        self.requests[value['requestId']]=(self.clock()+600,signature,result)
        return result

    async def configure(self,value):
        async with self.lock:
            signature,old=self._request(value,'configure',{'requestId','clientId','clientSecret'})
            if old:return old
            cid,secret=value['clientId'],value['clientSecret']
            if not isinstance(cid,str) or len(cid)>250 or not re.fullmatch(r'[\w-]+\.apps\.googleusercontent\.com',cid,re.ASCII) or not clean_text(secret,256):
                raise JuneError('invalid-google','Upload a Google Desktop OAuth client configuration.',400)
            if self.daily.meta('google').get('state')=='connected':
                raise JuneError('google-connected','Disconnect Google before replacing its client setup.',409)
            await self.keychain.put('google.client',json.dumps(dict(clientId=cid,clientSecret=secret)))
            self.pending=None
            self.daily.set_meta('google',dict(enabled=False,state='needs-consent',checkedAt=None,message='Desktop OAuth client saved in Keychain. Connect Calendar to review Google’s permission screen. Testing-mode authorisation may expire after seven days.'))
            result=self.daily.envelope(connection=self.daily.connection('google'))
            return self._save_request(value,signature,result)

    async def authorize(self,value):
        async with self.lock:
            signature,old=self._request(value,'authorize',{'requestId','scopes'})
            if old:return old
            if value['scopes']!=['calendar.events.readonly']:
                raise JuneError('invalid-google','Only read-only calendar event access is supported.',400)
            raw=await self.keychain.get('google.client')
            if not raw:raise JuneError('google-not-configured','Upload Google Desktop OAuth client configuration first.',409)
            client=json.loads(raw)
            state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
            challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            expires=self.clock()+600
            self.pending=dict(state=state,verifier=verifier,expires=expires)
            self.daily.set_meta('google',dict(enabled=True,state='needs-consent',checkedAt=None,message='Finish Google’s read-only Calendar authorisation in the opened tab.'))
            auth='https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(dict(client_id=client['clientId'],redirect_uri=self.redirect,response_type='code',scope=SCOPE,state=state,code_challenge=challenge,code_challenge_method='S256',access_type='offline',prompt='consent',include_granted_scopes='false'))
            return self._save_request(value,signature,self.daily.envelope(authUrl=auth,expiresAt=round(expires*1000)))

    async def callback(self,query):
        async with self.lock:
            pending=self.pending
            if not pending or pending['expires']<=self.clock() or not isinstance(query.get('state'),str) or not secrets.compare_digest(query['state'],pending['state']):
                raise JuneError('google-state','This Google sign-in expired or does not match June. Start again from Daily.',400)
            self.pending=None
            if query.get('error') or not isinstance(query.get('code'),str) or not 1<=len(query['code'])<=4096:
                raise JuneError('google-denied','Google access was not granted. Nothing was connected.',400)
            raw=await self.keychain.get('google.client')
            if not raw:raise JuneError('google-not-configured','Google setup is no longer available.',409)
            client=json.loads(raw)
            try:
                token=await self.http.json('POST','https://oauth2.googleapis.com/token',form=dict(client_id=client['clientId'],client_secret=client['clientSecret'],code=query['code'],code_verifier=pending['verifier'],redirect_uri=self.redirect,grant_type='authorization_code'))
                if not isinstance(token,dict) or not isinstance(token.get('access_token'),str) or not isinstance(token.get('refresh_token'),str) or set(str(token.get('scope','')).split())!={SCOPE}:
                    raise JuneError('google-scope','Google did not grant the exact requested calendar permission.',403)
                probe=await self.http.json('GET','https://www.googleapis.com/calendar/v3/calendars/primary/events?maxResults=1&fields=items(id)',headers={'Authorization':'Bearer '+token['access_token']})
                if not isinstance(probe,dict):raise JuneError('calendar-invalid','Calendar access could not be verified.',502)
                expiry=token.get('expires_in',3600)
                if type(expiry) not in (int,float) or not 1<=expiry<=86400:raise JuneError('google-token','Google returned an invalid token lifetime.',502)
                saved={k:token[k] for k in ('access_token','refresh_token')}
                saved.update(expiresAt=self.clock()+expiry,scope=SCOPE)
                await self.keychain.put('google.calendar',json.dumps(saved))
            except JuneError:
                self.daily.set_meta('google',dict(enabled=False,state='error',checkedAt=None,message='Google connection could not be verified. Connect again from Daily.'))
                raise
            self.daily.set_meta('google',dict(enabled=True,state='connected',checkedAt=round(self.clock()*1000),message='Read-only primary Calendar access verified. Testing-mode grants may expire after seven days.'))
            return self.daily.envelope(connection=self.daily.connection('google'))

    async def _token(self):
        raw=await self.keychain.get('google.calendar')
        if not raw:raise JuneError('google-expired','Reconnect Google Calendar.',401)
        token=json.loads(raw)
        if token.get('expiresAt',0)<=self.clock()+30:
            client=json.loads(await self.keychain.get('google.client') or '{}')
            fresh=await self.http.json('POST','https://oauth2.googleapis.com/token',form=dict(client_id=client['clientId'],client_secret=client['clientSecret'],refresh_token=token['refresh_token'],grant_type='refresh_token'))
            if not isinstance(fresh,dict) or not isinstance(fresh.get('access_token'),str):raise JuneError('google-expired','Reconnect Google Calendar.',401)
            expiry=fresh.get('expires_in',3600)
            if type(expiry) not in (int,float) or not 1<=expiry<=86400:raise JuneError('google-expired','Reconnect Google Calendar.',401)
            token.update(access_token=fresh['access_token'],expiresAt=self.clock()+expiry)
            await self.keychain.put('google.calendar',json.dumps(token))
        return token['access_token']

    async def events(self):
        async with self.lock:
            if not self.daily.enabled('google'):raise JuneError('google-disabled','Connect Google Calendar first.',403)
            try:
                token=await self._token()
                place=self.daily.settings()['settings']['weather']['place']
                zone=place['timeZone'] if place else 'Asia/Kolkata'
                start=datetime.fromtimestamp(self.clock(),ZoneInfo(zone)).replace(hour=0,minute=0,second=0,microsecond=0)
                query=urlencode(dict(timeMin=start.isoformat(),timeMax=(start+timedelta(days=1)).isoformat(),singleEvents='true',orderBy='startTime',maxResults=20,timeZone=zone,fields='items(summary,start,status),nextPageToken'))
                reply=await self.http.json('GET','https://www.googleapis.com/calendar/v3/calendars/primary/events?'+query,headers={'Authorization':'Bearer '+token})
                items=calendar_items(reply,zone)
                if reply.get('nextPageToken'):items=items[:19]+[dict(text='More calendar events are available in Google Calendar.')]
                self.daily.set_meta('google',dict(enabled=True,state='connected',checkedAt=round(self.clock()*1000),message='Read-only primary Calendar access verified.'))
                return items
            except (JuneError,ValueError,KeyError,TypeError) as error:
                expired=not isinstance(error,JuneError) or error.code in ('connector-auth','google-expired')
                if expired:
                    self.daily.set_meta('google',dict(enabled=False,state='expired',checkedAt=None,message='Calendar access expired or was refused. Reconnect Google; testing grants can expire after seven days.'))
                else:
                    meta=self.daily.meta('google');meta['message']='The last Calendar read failed temporarily. Try your briefing again.'
                    self.daily.set_meta('google',meta)
                raise JuneError('google-expired' if expired else 'calendar-unavailable','Reconnect Google Calendar in Daily.' if expired else 'Google Calendar is temporarily unavailable. Try the briefing again.',401 if expired else 503) from None

    async def revoke(self,value):
        async with self.lock:
            signature,old=self._request(value,'revoke',{'requestId'})
            if old:return old
            self.pending=None
            remote=False
            removed=False
            self.daily.set_meta('google',dict(enabled=False,state='revoked',checkedAt=None,message='Calendar access is disabled. Removing saved credentials.'))
            try:
                raw=await self.keychain.get('google.calendar')
                if raw:
                    token=json.loads(raw)
                    self.revoking=True
                    await self.http.json('POST','https://oauth2.googleapis.com/revoke',form={'token':token.get('refresh_token',token.get('access_token',''))},allow_empty=True)
                    remote=True
            except (JuneError,ValueError):pass
            finally:self.revoking=False
            try:
                await self.keychain.delete('google.calendar');removed=True
            except JuneError:pass
            message='June’s Calendar access is disabled.'
            message+=' Saved Calendar credentials were removed.' if removed else ' Keychain removal could not be verified; unlock Keychain and disconnect again.'
            message+=' Google revocation confirmed.' if remote else ' Remote revocation was not verified; remove June in your Google Account too.'
            self.daily.set_meta('google',dict(enabled=False,state='revoked',checkedAt=None,message=message))
            return self._save_request(value,signature,self.daily.envelope(connection=self.daily.connection('google')))
