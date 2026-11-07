"""External PCM owns the same native playback/cancellation graph as capture."""
import asyncio
from pathlib import Path
import unittest
from june.native_audio import NativeAudioService
from june.voice_identity import JUNE_VOICE_ID
from june.errors import JuneError

VALUE={'ownerId':'owner','requestId':'request','segmentId':'segment','voiceId':JUNE_VOICE_ID,'rate':.98,'text':'Hello June.'}

class FakePCM(NativeAudioService):
    def __init__(self):
        super().__init__(Path('/not-installed'));self.sent=[]
    async def ensure_started(self):pass
    async def send(self,value):self.sent.append(value)
    async def _pcm_command(self,kind,sid,**values):
        self.sent.append({'type':kind,'id':sid,**values})
        if kind=='pcm-end':await self.receive({'type':'playback','id':sid,'phase':'end'})

class PCMTests(unittest.IsolatedAsyncioTestCase):
    async def test_pcm_is_queued_without_local_synthesis(self):
        audio=FakePCM()
        async def source():yield b'\0'*640;yield b'\0'*800
        events=[e async for e in audio.speak_pcm(VALUE,source())]
        self.assertEqual([e['type'] for e in events],['accepted','end'])
        self.assertEqual([v['type'] for v in audio.sent],['pcm-start','pcm-chunk','pcm-chunk','pcm-end'])
        self.assertEqual(audio.jobs,{})

    async def test_stop_cancels_pending_cloud_source_and_late_audio(self):
        audio=FakePCM();entered=asyncio.Event();closed=asyncio.Event()
        async def source():
            try:
                entered.set();yield b'\0'*640
                await asyncio.sleep(30)
            finally:closed.set()
        stream=audio.speak_pcm(VALUE,source())
        self.assertEqual((await anext(stream))['type'],'accepted')
        await entered.wait()
        await audio.stop('owner','request')
        self.assertEqual((await anext(stream))['type'],'cancelled')
        await stream.aclose()
        self.assertTrue(closed.is_set())
        self.assertEqual(audio.jobs,{})
        self.assertNotIn('pcm-end',[v['type'] for v in audio.sent])

    async def test_provider_failure_cleans_up_and_never_starts_other_voice(self):
        audio=FakePCM()
        async def source():
            raise JuneError('voice-provider','Cloud unavailable.')
            yield b''
        events=[e async for e in audio.speak_pcm(VALUE,source())]
        self.assertEqual(events[-1]['type'],'error')
        self.assertEqual(audio.jobs,{})
        self.assertFalse(any(v['type']=='speak' for v in audio.sent))

    async def test_stale_and_competing_owners_are_rejected(self):
        audio=FakePCM();audio.capture_owner='other'
        async def source():yield b'\0'*640
        with self.assertRaises(JuneError):await anext(audio.speak_pcm(VALUE,source()))
        self.assertEqual(audio.sent,[])
