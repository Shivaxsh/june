"""Free-only remote synthesis checks. No real account or billable calls."""
import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
import httpx
from june.errors import JuneError
from june.elevenlabs_voice import ElevenLabsVoice, JUNE_VOICE_ID

class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.sent=[];self.used=0;self.tier='free';self.extensions=False;self.model=True;self.voice=True
        def respond(request):
            self.sent.append(request)
            if request.url.path=='/v1/user/subscription':return httpx.Response(200,json={'tier':self.tier,'character_count':self.used,'character_limit':10000,'can_extend_character_limit':self.extensions,'allowed_to_extend_character_limit':False,'next_character_count_reset_unix':9999999999})
            if request.url.path=='/v1/models':return httpx.Response(200,json=[{'model_id':'eleven_v4','can_do_text_to_speech':True,'model_rates':{'character_cost_multiplier':1}}] if self.model else [])
            if request.url.path==f'/v1/voices/{JUNE_VOICE_ID}':return httpx.Response(200,json={'voice_id':JUNE_VOICE_ID,'category':'generated','name':'June'} if self.voice else {'voice_id':'another'})
            return httpx.Response(200,content=b'\x01\x00'*2400,headers={'content-type':'audio/pcm'})
        self.client=httpx.AsyncClient(transport=httpx.MockTransport(respond));self.addAsyncCleanup(self.client.aclose)
        self.service=ElevenLabsVoice(self.client,Path(self.temp.name),'private-key')
        self.value={'ownerId':'owner','requestId':'request','segmentId':'segment','voiceId':JUNE_VOICE_ID,'rate':.98,'text':'Hello June.'}

    async def test_missing_key_stays_text_only_without_requests(self):
        service=ElevenLabsVoice(self.client,Path(self.temp.name),'')
        state=await service.status()
        self.assertEqual(state['state'],'setup-required');self.assertIn('API key',state['message'])
        self.assertEqual(self.sent,[])

    async def test_status_reads_only_and_identifies_fixed_voice(self):
        state=await self.service.status()
        self.assertEqual(state['state'],'ready');self.assertEqual(state['voiceId'],JUNE_VOICE_ID)
        self.assertEqual(state['quota']['remaining'],10000)
        self.assertTrue(all(r.method=='GET' for r in self.sent))

    async def test_paid_or_unverified_billing_never_generates(self):
        for tier,extensions in [('starter',False),('free',True)]:
            self.tier=tier;self.extensions=extensions
            with self.assertRaises(JuneError):
                async for _ in self.service.pcm(self.value):pass
        self.assertTrue(all(r.method=='GET' for r in self.sent))

    async def test_model_voice_and_quota_fail_closed(self):
        for name in ('model','voice','quota'):
            self.model=name!='model';self.voice=name!='voice';self.used=10000 if name=='quota' else 0
            with self.assertRaises(JuneError):
                async for _ in self.service.pcm(self.value):pass
        self.assertTrue(all(r.method=='GET' for r in self.sent))

    async def test_emotions_use_one_voice_and_never_modify_display_text(self):
        for rate,tag in [(.98,None),(.92,'[calm]'),(1.04,'[cheerful]')]:
            value={**self.value,'rate':rate}
            self.assertTrue(b''.join([b async for b in self.service.pcm(value)]))
            request=next(r for r in reversed(self.sent) if r.method=='POST')
            data=json.loads(request.content)
            self.assertEqual(request.url.path,f'/v1/text-to-speech/{JUNE_VOICE_ID}/stream')
            self.assertEqual(data['model_id'],'eleven_v4')
            self.assertEqual(value['text'],'Hello June.')
            self.assertEqual(data['text'],(tag+' ' if tag else '')+value['text'])

    async def test_stale_usage_counters_cannot_respend_reserved_quota(self):
        self.used=9990
        with self.assertRaises(JuneError):
            async for _ in self.service.pcm(self.value):pass
        self.assertFalse(any(r.method=='POST' for r in self.sent))
        self.used=9980
        self.service=ElevenLabsVoice(self.client,Path(self.temp.name),'private-key')
        async for _ in self.service.pcm(self.value):pass
        with self.assertRaises(JuneError):
            async for _ in self.service.pcm(self.value):pass
        self.assertEqual(len([r for r in self.sent if r.method=='POST']),1)
        self.assertEqual(self.service.path.stat().st_mode & 0o777,0o600)

    async def test_changed_voice_is_rejected_before_network(self):
        with self.assertRaises(JuneError):
            async for _ in self.service.pcm({**self.value,'voiceId':'Nicky'}):pass
        self.assertEqual(self.sent,[])

    async def test_api_failures_never_expose_credentials(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(401,text='private-key secret details'))) as client:
            service=ElevenLabsVoice(client,Path(self.temp.name),'private-key')
            state=await service.status()
            self.assertEqual(state['state'],'error');self.assertNotIn('private-key',json.dumps(state))

    async def test_initial_validation_cap_is_checked_before_synthesis(self):
        self.service.validation_limit=5
        with self.assertRaises(JuneError):
            async for _ in self.service.pcm(self.value):pass
        self.assertFalse(any(r.method=='POST' for r in self.sent))

    async def test_reservations_survive_restart_without_refunding_cancelled_work(self):
        async for _ in self.service.pcm(self.value):pass
        previous=self.service.high
        service=ElevenLabsVoice(self.client,Path(self.temp.name),'private-key')
        self.assertEqual(service.high,previous)
        self.assertEqual(service.char_total,len(self.value['text']))
        self.assertEqual((await service.status())['quota']['used'],previous)

    async def test_generation_is_serial_and_cancel_closes_the_stream(self):
        entered=asyncio.Event();closed=asyncio.Event()
        class Slow(httpx.AsyncByteStream):
            async def __aiter__(self):
                entered.set();yield b'\0'*8192
                await asyncio.sleep(30)
            async def aclose(self):closed.set()
        original=self.client
        async def response(request):
            if request.method=='POST':return httpx.Response(200,stream=Slow())
            # Reuse the fixture's metadata transport without a real network.
            return await original.send(original.build_request(request.method,str(request.url)))
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            service=ElevenLabsVoice(client,Path(self.temp.name),'private-key')
            first=service.pcm(self.value);second=service.pcm(self.value)
            await anext(first);await entered.wait()
            waiting=asyncio.create_task(anext(second));await asyncio.sleep(.01)
            self.assertFalse(waiting.done())
            await first.aclose();self.assertTrue(closed.is_set())
            await asyncio.wait_for(waiting,1)
            await second.aclose()

    async def test_cached_empty_quota_never_becomes_ready(self):
        self.used=10000
        for _ in range(2):
            self.assertEqual((await self.service.status())['state'],'quota-exhausted')
