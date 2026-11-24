"""Consent provenance is observed on the server, not claimed by a client flag."""
import time
import unittest
from types import SimpleNamespace
import test_commerce as fixtures


class VoiceConsentTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.CommerceTests.asyncSetUp
    asyncTearDown=fixtures.CommerceTests.asyncTearDown
    ready=fixtures.CommerceTests.ready
    say=fixtures.CommerceTests.say

    async def review(self):
        from june.commerce_voice import VoiceConsent
        quote=await self.ready();self.quote=quote
        self.native=SimpleNamespace(capture_session='native-session-01',capture_flowing=lambda:True,output_error=None)
        self.voice=VoiceConsent(self.service,self.native)
        async def activity(n,p):self.turn.phase='followup'
        self.turn=SimpleNamespace(number=1,phase='speaking',clock=time.monotonic,activity=activity)
        self.voice.session('native-session-01',self.turn)
        return quote

    async def arm(self):
        q=self.quote;p=q['plan'];sid='native-session-01'
        job=dict(voiceSessionId=sid,request='native-request-01',text=q['transaction']['quote']['summary'])
        self.voice.playback(job,'start','segment-1');self.voice.playback(job,'end','segment-1')
        token=await self.voice.arm(q['transaction']['id'],dict(planId=p['id'],revision=p['revision'],fingerprint=p['fingerprint'],sessionId=sid,requestId='native-request-01'))
        return dict(requestId='voice-approve-0001',revision=p['revision'],fingerprint=p['fingerprint'],reviewToken=token['reviewToken'],sessionId=sid,turnId=2)

    async def test_fresh_explicit_go_ahead_commits_once_and_replay_is_idempotent(self):
        await self.review();v=await self.arm()
        self.voice.observe(v['sessionId'],dict(type='transcript',turn=2,text='I approve'),time.monotonic())
        p=await self.voice.approve(self.quote['plan']['id'],v)
        again=await self.voice.approve(self.quote['plan']['id'],v)
        self.assertEqual(p['plan']['id'],again['plan']['id'])
        for _ in range(100):
            if self.service.get(self.quote['transaction']['id'])['receipt']:break
            import asyncio;await asyncio.sleep(.01)
        self.assertIsNotNone(self.service.get(self.quote['transaction']['id'])['receipt'])

    async def test_unread_review_and_forged_turn_cannot_approve(self):
        from june.errors import JuneError
        await self.review();q=self.quote;p=q['plan']
        with self.assertRaises(JuneError):await self.voice.arm(q['transaction']['id'],dict(planId=p['id'],revision=1,fingerprint=p['fingerprint'],sessionId='native-session-01',requestId='native-request-01'))
        v=await self.arm()
        with self.assertRaises(JuneError):await self.voice.approve(p['id'],v)

    async def test_ambiguous_quoted_negative_overlap_old_session_and_unhealthy_are_rejected(self):
        from june.errors import JuneError
        for text in ('yes','okay','she said go ahead','go ahead but make it 3','do not book it','I approve'):
            await self.review();v=await self.arm()
            onset=time.monotonic()-60 if text=='I approve' else time.monotonic()
            self.voice.observe(v['sessionId'],dict(type='transcript',turn=2,text=text),onset)
            with self.assertRaises(JuneError,msg=text):await self.voice.approve(self.quote['plan']['id'],v)
            self.assertIsNone(self.service.get(self.quote['transaction']['id'])['receipt'])
        await self.review();v=await self.arm();self.voice.close(v['sessionId'])
        with self.assertRaises(JuneError):await self.voice.approve(self.quote['plan']['id'],v)
        await self.review();v=await self.arm();self.native.output_error='broken'
        with self.assertRaises(JuneError):await self.voice.approve(self.quote['plan']['id'],v)

    async def test_real_native_playback_events_provide_provenance(self):
        import asyncio
        from june.native_audio import NativeAudioService
        from june.commerce_voice import VoiceConsent
        q=await self.ready();native=NativeAudioService(self.root if hasattr(self,'root') else self.service.path.parent)
        native.capture_session='native-session-01';native.capture_owner='native-owner-01';native.captures[native.capture_session]=asyncio.Queue();native.last_capture_frame=time.monotonic()
        voice=VoiceConsent(self.service,native)
        async def activity(n,p):turn.phase='followup'
        turn=SimpleNamespace(number=1,phase='speaking',clock=time.monotonic,activity=activity)
        voice.session(native.capture_session,turn)
        native.jobs['segment-1']=dict(owner=native.capture_owner,request='native-request-01',queue=asyncio.Queue(),voiceSessionId=native.capture_session,text=q['transaction']['quote']['summary'])
        await native.receive(dict(type='playback',id='segment-1',phase='start'))
        await native.receive(dict(type='playback',id='segment-1',phase='end'))
        p=q['plan'];armed=await voice.arm(q['transaction']['id'],dict(planId=p['id'],revision=p['revision'],fingerprint=p['fingerprint'],sessionId=native.capture_session,requestId='native-request-01'))
        self.assertTrue(armed['reviewToken']);self.assertEqual(turn.phase,'followup')
        self.assertEqual(native.jobs['segment-1']['queue'].qsize(),2)

    async def test_expiry_quote_change_and_simultaneous_approvals(self):
        import asyncio
        from june.errors import JuneError
        await self.review();v=await self.arm()
        self.voice.observe(v['sessionId'],dict(type='transcript',turn=2,text='go ahead'),time.monotonic())
        original=self.service.clock;self.service.clock=lambda:original()+61
        with self.assertRaises(JuneError):await self.voice.approve(self.quote['plan']['id'],v)
        self.service.clock=original
        await self.review();v=await self.arm()
        self.voice.observe(v['sessionId'],dict(type='transcript',turn=2,text='go ahead'),time.monotonic())
        await self.say('change area to Delhi')
        with self.assertRaises(JuneError):await self.voice.approve(self.quote['plan']['id'],v)
        await self.review();v=await self.arm()
        self.voice.observe(v['sessionId'],dict(type='transcript',turn=2,text='go ahead'),time.monotonic())
        result=await asyncio.gather(self.voice.approve(self.quote['plan']['id'],v),self.voice.approve(self.quote['plan']['id'],dict(v,requestId='voice-other-0001')),return_exceptions=True)
        self.assertEqual(sum(isinstance(r,dict) for r in result),1)
        self.assertEqual(sum(isinstance(r,JuneError) for r in result),1)

    async def test_a_reply_before_arm_requires_another_review(self):
        from june.errors import JuneError
        await self.review();q=self.quote;p=q['plan'];sid='native-session-01'
        job=dict(voiceSessionId=sid,request='native-request-01',text=q['transaction']['quote']['summary'])
        self.voice.playback(job,'start','seg');self.voice.playback(job,'end','seg')
        self.voice.observe(sid,dict(type='transcript',turn=2,text='what is the weather'),time.monotonic())
        with self.assertRaises(JuneError):await self.voice.arm(q['transaction']['id'],dict(planId=p['id'],revision=p['revision'],fingerprint=p['fingerprint'],sessionId=sid,requestId='native-request-01'))

    async def test_completed_order_cancellation_can_be_reviewed_and_approved_by_voice(self):
        import asyncio
        await self.review()
        await fixtures.CommerceTests.approve(self,self.quote)
        tid=self.quote['transaction']['id'];original=self.service.get(tid)['receipt']['id']
        # The original purchase hold may expire long before a cancellation is requested.
        current=self.service.get(tid);current['quote']['expiresAt']=1;self.service.save(current)
        cancel=await self.say('cancel the order')
        self.assertEqual(cancel['transaction']['status'],'completed')
        self.assertEqual(cancel['transaction']['receipt']['status'],'confirmed')
        self.quote=cancel
        p=cancel['plan'];sid='native-session-01'
        job=dict(voiceSessionId=sid,request='cancel-review-01',text=p['steps'][0]['preview'])
        self.voice.playback(job,'start','cancel-segment');self.voice.playback(job,'end','cancel-segment')
        armed=await self.voice.arm(tid,dict(planId=p['id'],revision=p['revision'],fingerprint=p['fingerprint'],sessionId=sid,requestId='cancel-review-01'))
        self.assertEqual(self.service.get(tid)['receipt']['status'],'confirmed','reading the cancellation must not execute it')
        self.voice.observe(sid,dict(type='transcript',turn=2,text='go ahead'),time.monotonic())
        await self.voice.approve(p['id'],dict(requestId='cancel-voice-approval',revision=p['revision'],fingerprint=p['fingerprint'],sessionId=sid,reviewToken=armed['reviewToken'],turnId=2))
        for _ in range(100):
            if self.service.get(tid)['status']=='cancelled':break
            await asyncio.sleep(.01)
        self.assertEqual(self.service.get(tid)['status'],'cancelled')
        self.assertEqual(self.service.get(tid)['receipt']['id'],original)

    async def test_natural_explicit_go_aheads_and_wake_punctuation_are_accepted(self):
        for phrase in ('Yes, go ahead','yeah go ahead','Okay, go ahead','Go ahead please','Go ahead and book it','June: go ahead','I approve it'):
            with self.subTest(phrase=phrase):
                await self.review();v=await self.arm()
                v['requestId']=f'natural-approval-{self.n:08}'
                self.voice.observe(v['sessionId'],dict(type='transcript',turn=2,text=phrase),time.monotonic())
                result=await self.voice.approve(self.quote['plan']['id'],v)
                self.assertIn(result['plan']['status'],('approved','running','completed'))
