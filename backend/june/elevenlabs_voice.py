"""One saved voice, verified free allowance, and no credential/audio logging."""
import asyncio
from contextlib import aclosing
import json
import math
import os
from pathlib import Path
import time

import httpx

from .errors import JuneError
from .native_audio import validate_speak

JUNE_VOICE_ID='ZYufQennDT5PFsid8v3E'
TTS_MODEL='eleven_v4'
API='https://api.elevenlabs.io'
JUNE_VOICE={'id':JUNE_VOICE_ID,'name':'June','lang':'en','gender':'female','localService':False,'provider':'elevenlabs'}

class ElevenLabsVoice:
    def __init__(self,client,home,key='',audio=None):
        self.client,self.key,self.audio=client,key.strip(),audio
        self.path=Path(home)/'voice-usage.json'
        self.lock=asyncio.Lock();self.check_lock=asyncio.Lock()
        self.cache=None;self.checked=0.;self.rate=1.;self.period=None;self.high=0;self.char_total=0
        self.validation_limit=int(os.environ.get('JUNE_VOICE_VALIDATION_CHAR_LIMIT','0'))
        try:
            saved=json.loads(self.path.read_text())
            if isinstance(saved,dict) and type(saved.get('used')) is int and saved['used']>=0:
                self.period=saved.get('period');self.high=saved['used']
                self.char_total=saved.get('inputCharacters',0) if type(saved.get('inputCharacters',0)) is int else 0
        except (OSError,ValueError):pass

    def info(self):
        return {'provider':'elevenlabs','voiceId':JUNE_VOICE_ID,'voiceName':'June','ttsModel':TTS_MODEL,
                'cloudText':True,'trainingRequired':False}

    async def get(self,path):
        response=await self.client.get(API+path,headers={'xi-api-key':self.key},timeout=10)
        if response.status_code in (401,403):raise JuneError('voice-auth','ElevenLabs rejected access. Check the API key and its Voices, Models and User read permissions; text chat remains available.',503)
        response.raise_for_status()
        return response.json()

    async def check(self,force=False):
        if not self.key:raise JuneError('voice-setup','June’s ElevenLabs API key is missing. Configure ELEVENLABS_API_KEY privately, restart June and refresh audio. Text chat remains available.',503)
        async with self.check_lock:
            if not force and self.cache is not None and time.monotonic()-self.checked<20:
                if self.cache['quota']['remaining']<=0:raise JuneError('voice-quota','The verified free speech allowance is exhausted. June stays text-only until renewal.',429)
                return dict(self.cache)
            self.cache=None
            # Read-only checks never warm speech or consume synthesis credits.
            subscription,models,voice=await asyncio.gather(self.get('/v1/user/subscription'),self.get('/v1/models'),self.get('/v1/voices/'+JUNE_VOICE_ID))
            if (not isinstance(subscription,dict) or subscription.get('tier')!='free'
                or subscription.get('can_extend_character_limit') is not False
                or subscription.get('allowed_to_extend_character_limit') is not False):
                raise JuneError('voice-billing','Free-only speech is paused: the account must be on Free with usage extensions disabled and verifiable. No upgrade or billing setting was changed.',503)
            used,limit=subscription.get('character_count'),subscription.get('character_limit')
            if type(used) is not int or type(limit) is not int or used<0 or limit<0:
                raise JuneError('voice-billing','Could not verify the free allowance. Speech stays off; text chat is available.',503)
            if not isinstance(voice,dict) or voice.get('voice_id')!=JUNE_VOICE_ID or voice.get('category')!='generated':
                raise JuneError('voice-missing','The saved custom June voice is not accessible with this key. Check the account and Voices read permission.',503)
            model=next((m for m in models if isinstance(m,dict) and m.get('model_id')==TTS_MODEL and m.get('can_do_text_to_speech') is True),None) if isinstance(models,list) else None
            if model is None:raise JuneError('voice-model','The expressive eleven_v4 model is not available to this API account. Speech stays off; no paid or alternate model was selected.',503)
            factor=model.get('model_rates',{}).get('character_cost_multiplier',model.get('token_cost_factor',1))
            if type(factor) not in (int,float) or not math.isfinite(factor) or factor<=0:
                raise JuneError('voice-billing','Could not verify this speech model’s usage rate. Speech stays off.',503)
            self.rate=max(1.,factor)
            period=subscription.get('next_character_count_reset_unix')
            if type(period) is not int or period<=0:
                raise JuneError('voice-billing','Could not verify the allowance renewal period. Speech stays off.',503)
            if period!=self.period:self.period=period;self.high=used
            effective=max(used,self.high)
            state={**self.info(),'state':'ready','message':'June · ElevenLabs expressive voice · free allowance verified.',
                   'quota':{'used':effective,'limit':limit,'remaining':max(0,limit-effective),'resetAt':period}}
            self.cache=state;self.checked=time.monotonic()
            if effective>=limit:raise JuneError('voice-quota','The verified free speech allowance is exhausted. June stays text-only until renewal; no other voice will be used.',429)
            return dict(state)

    async def status(self,force=False):
        try:return await self.check(force)
        except JuneError as error:
            state='setup-required' if error.code=='voice-setup' else 'quota-exhausted' if error.code=='voice-quota' else 'error'
            return {**self.info(),'state':state,'message':error.message,**({'quota':self.cache['quota']} if error.code=='voice-quota' and self.cache else {})}
        except (httpx.HTTPError,ValueError,TypeError,AttributeError):
            return {**self.info(),'state':'error','message':'Could not verify ElevenLabs voice access or allowance. Check your connection and key permissions, then refresh. Text chat remains available.'}

    async def voices(self):
        return {**await self.status(),'voices':[dict(JUNE_VOICE)]}

    def reserve(self,used,characters=0):
        temporary=self.path.with_suffix('.tmp')
        try:
            self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            with open(temporary,'w',encoding='utf-8',opener=lambda p,f:os.open(p,f,0o600)) as output:
                os.chmod(temporary,0o600);json.dump({'period':self.period,'used':used,'inputCharacters':self.char_total+characters},output)
            os.replace(temporary,self.path)
        except OSError:
            try:temporary.unlink(missing_ok=True)
            except OSError:pass
            raise JuneError('voice-storage','Could not save the private speech-usage reservation. Speech stays off to protect the free allowance.',503) from None
        self.high=used;self.char_total+=characters
        self.cache=None

    async def pcm(self,value):
        value=validate_speak(value,[JUNE_VOICE])
        cue={.98:'',.92:'[calm] ',1.04:'[cheerful] '}[value['rate']]
        # Tags guide only the cloud audio; written replies/captions remain exact.
        text=cue+value['text']
        async with self.lock:
            try:
                state=await self.check(force=True)
                if self.validation_limit and self.char_total+len(text)>self.validation_limit:
                    raise JuneError('voice-validation','The initial 1,500-character speech-validation budget is reached. Further preview or replay needs a deliberate validation-limit change; text chat remains available.',429)
                cost=math.ceil(len(text)*self.rate)
                if cost>state['quota']['remaining']:raise JuneError('voice-quota','This speech segment exceeds the remaining verified free allowance. June stays text-only.',429)
                self.reserve(state['quota']['used']+cost,len(text))
                async with self.client.stream('POST',API+'/v1/text-to-speech/'+JUNE_VOICE_ID+'/stream',
                    params={'output_format':'pcm_24000'},headers={'xi-api-key':self.key},
                    json={'text':text,'model_id':TTS_MODEL},timeout=httpx.Timeout(60,connect=10)) as response:
                    if response.status_code in (401,403):
                        try:
                            detail=json.loads((await response.aread()).decode('utf-8')).get('detail',{})
                        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError):
                            detail={}
                        if isinstance(detail,dict) and detail.get('code')=='quota_exceeded':
                            raise JuneError('voice-key-quota','This ElevenLabs API key reached its separate API-key quota. Increase the key’s allowed quota or replace it with another restricted key, then restart June. Your account allowance is separate; no fallback voice was used.',429)
                        raise JuneError('voice-auth','ElevenLabs did not authorise synthesis with June’s saved voice and this model. Check the key’s Text to Speech permission; no fallback voice was used.',503)
                    if response.status_code in (402,429):raise JuneError('voice-quota','ElevenLabs refused the free speech request. Check allowance and rate limits; text remains available.',429)
                    if response.status_code!=200:raise JuneError('voice-provider','ElevenLabs could not generate this segment. Retry manually; no credits are automatically purchased and no other voice is used.',503)
                    total=0
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if not chunk:continue
                        total+=len(chunk)
                        if total>8*1024*1024:raise JuneError('voice-audio','Speech audio exceeded its safe size. Use a shorter reply.',503)
                        yield chunk
                    if not total or total%2:raise JuneError('voice-audio','ElevenLabs returned empty or incomplete PCM audio. Retry manually.',503)
            except JuneError:raise
            except (httpx.HTTPError,ValueError,TypeError,AttributeError):
                raise JuneError('voice-provider','The ElevenLabs connection failed. June stays text-only; refresh audio and retry manually.',503) from None

    async def speak(self,value):
        if self.audio is None:raise JuneError('audio-missing','Native June playback is unavailable.',503)
        value=validate_speak(value,[JUNE_VOICE])
        state=await self.status()
        if state['state']!='ready':raise JuneError('voice-unavailable',state['message'],503)
        async with aclosing(self.audio.speak_pcm(value,self.pcm(value))) as stream:
            async for event in stream:yield event
