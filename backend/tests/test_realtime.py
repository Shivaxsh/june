"""Hands-free state invariants, using deterministic audio detector results."""
import asyncio
import unittest

from june.realtime_state import VoiceTurn, pcm_wav, remove_wake_phrase


class Turns(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events, self.clips = [], []
        async def emit(event):
            self.events.append(event)
        async def transcribe(data):
            self.clips.append(data)
            return {'text': 'Hey June, what is Python?', 'durationMs': 10}
        self.clock = 0.
        self.turn = VoiceTurn(emit, transcribe, clock=lambda: self.clock)

    async def packet(self, voiced=False, wake=False, seconds=.1):
        self.clock += seconds
        await self.turn.audio(b'\x00\x10' * int(16000 * seconds), voiced, wake)

    async def test_does_not_send_room_audio_before_wake(self):
        for _ in range(60):
            await self.packet(True)
        self.assertEqual(self.clips, [])
        self.assertEqual(self.turn.phase, 'waiting')

    async def test_one_transcript_after_wake_and_silence(self):
        await self.packet(True, True)
        for _ in range(7):
            await self.packet(True)
        for _ in range(16):
            await self.packet()
        await self.turn.flush()
        self.assertEqual(len(self.clips), 1)
        transcripts = [e for e in self.events if e['type'] == 'transcript']
        self.assertEqual(transcripts[0]['text'], 'what is Python?')
        self.assertEqual(transcripts[0]['turn'], 1)
        self.assertEqual(self.turn.phase, 'generating')
        await self.turn.close()

    async def test_pause_and_empty_wake_do_not_send(self):
        await self.packet(True, True)
        for _ in range(3):
            await self.packet(True)
        for _ in range(12):
            await self.packet()
        self.assertEqual(self.clips, [])
        self.clock += 11
        await self.turn.tick()
        self.assertEqual(self.turn.phase, 'waiting')
        await self.turn.close()

    async def test_followup_starts_after_playback_and_expires(self):
        await self.packet(True, True)
        self.turn.phase = 'generating'
        await self.turn.activity(1, 'speaking')
        self.clock += 40
        await self.turn.tick()
        self.assertEqual(self.turn.phase, 'speaking')
        await self.turn.activity(1, 'complete')
        self.assertEqual(self.turn.phase, 'followup')
        self.clock += 29
        await self.turn.tick()
        self.assertEqual(self.turn.phase, 'followup')
        self.clock += 2
        await self.turn.tick()
        self.assertEqual(self.turn.phase, 'waiting')
        await self.turn.close()

    async def test_interruption_invalidates_slow_transcription_and_old_playback(self):
        started = asyncio.Event()
        async def slow(_):
            started.set()
            await asyncio.sleep(10)
            return {'text': 'old words', 'durationMs': 1}
        self.turn.transcribe = slow
        await self.packet(True, True)
        for _ in range(7):
            await self.packet(True)
        for _ in range(16):
            await self.packet()
        await started.wait()
        await self.packet(True, True)
        self.assertEqual(self.turn.number, 2)
        await self.turn.activity(1, 'complete')
        self.assertEqual(self.turn.phase, 'listening')
        self.assertFalse(any(e['type'] == 'transcript' for e in self.events))
        await self.turn.close()

    def test_wake_stripping_and_wav_contract(self):
        self.assertEqual(remove_wake_phrase('Hey, June! How are you?'), 'How are you?')
        self.assertEqual(remove_wake_phrase('I enjoy June weather.'), 'I enjoy June weather.')
        self.assertEqual(remove_wake_phrase('Hey June'), '')
        self.assertEqual(len(pcm_wav(b'\x00\x10' * 16000)), 32044)
    async def test_thinking_pause_and_patient_mode(self):
        self.turn.pause = 2.5
        await self.packet(True, True)
        for _ in range(7): await self.packet(True)
        for _ in range(20): await self.packet()
        self.assertEqual(self.clips, [])
        for _ in range(6): await self.packet()
        await self.turn.flush()
        self.assertEqual(len(self.clips), 1)
        await self.turn.close()

    async def test_followup_without_wake_sends_a_new_number(self):
        self.turn.number, self.turn.phase = 1, 'speaking'
        await self.turn.activity(1, 'complete')
        for _ in range(8): await self.packet(True)
        for _ in range(16): await self.packet()
        await self.turn.flush()
        self.assertEqual(self.turn.number, 2)
        self.assertEqual(len(self.clips), 1)
        await self.turn.close()

    async def test_recording_is_capped_at_thirty_seconds(self):
        await self.packet(True, True)
        for _ in range(320): await self.packet(True)
        await self.turn.flush()
        self.assertEqual(len(self.clips), 1)
        self.assertLessEqual(len(self.clips[0]), 960044)
        await self.turn.close()

    async def test_empty_transcript_returns_to_wake_without_message(self):
        async def empty(_): return {'text': 'Hey June', 'durationMs': 2}
        self.turn.transcribe = empty
        await self.packet(True, True)
        for _ in range(7): await self.packet(True)
        for _ in range(16): await self.packet()
        await self.turn.flush()
        self.assertEqual(self.turn.phase, 'listening')
        self.clock += 11
        await self.turn.tick()
        self.assertEqual(self.turn.phase, 'waiting')
        self.assertFalse(any(e['type'] == 'transcript' for e in self.events))
        await self.turn.close()

    async def test_close_terminates_pending_transcription(self):
        cancelled = asyncio.Event()
        async def pending(_):
            try: await asyncio.sleep(10)
            finally: cancelled.set()
        self.turn.transcribe = pending
        await self.packet(True, True)
        for _ in range(7): await self.packet(True)
        for _ in range(16): await self.packet()
        await asyncio.sleep(0)
        await self.turn.close()
        self.assertTrue(cancelled.is_set())
        self.assertEqual(self.turn.buffer, b'')
        self.assertEqual(self.turn.preroll, b'')


class Transport(unittest.IsolatedAsyncioTestCase):
    async def test_competing_session_and_invalid_packet_cleanup(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from june.realtime_socket import VoiceSlots, voice_socket
        slots = VoiceSlots()
        class Socket:
            def __init__(self): self.incoming, self.outgoing = asyncio.Queue(), asyncio.Queue(); self.closed = False
            async def accept(self): pass
            async def receive(self): return await self.incoming.get()
            async def send_json(self, event): await self.outgoing.put(event)
            async def close(self, **_): self.closed = True
        async def ready(): return {'state': 'ready'}
        assets = SimpleNamespace(status=ready, model='test')
        speech = SimpleNamespace(status=ready, transcribe=None)
        def make_pipeline(detectors, turn, consumed, fail, ready_event, metrics):
            stop = asyncio.Event()
            class Pipeline:
                async def queue_frame(self, frame): consumed(len(frame))
                async def cancel(self): stop.set()
            class Runner:
                async def run(self, pipeline): ready_event.set(); await stop.wait()
            return Pipeline(), Runner()
        engine = SimpleNamespace(Detectors=lambda _: object(), make_pipeline=make_pipeline, PCMFrame=lambda data:data)
        first = Socket(); await first.incoming.put({'type': 'websocket.receive', 'text': '{"type":"start"}'})
        with patch('june.realtime_socket.importlib.import_module', return_value=engine):
            running = asyncio.create_task(voice_socket(first, assets, slots, speech))
            event = await asyncio.wait_for(first.outgoing.get(), 2)
            self.assertEqual(event['type'], 'ready')
            await first.outgoing.get()  # initial waiting state
            second = Socket(); await voice_socket(second, assets, slots, speech)
            self.assertIn('another tab', (await second.outgoing.get())['message'])
            self.assertTrue(second.closed)
            await first.incoming.put({'type':'websocket.receive', 'bytes':b'x' * 4098})
            error = await asyncio.wait_for(first.outgoing.get(), 2)
            self.assertTrue(error['fatal'])
            await asyncio.wait_for(running, 2)
        self.assertIsNone(slots.owner)
        self.assertTrue(first.closed)

    async def test_missing_assets_release_slot(self):
        from types import SimpleNamespace
        from june.realtime_socket import VoiceSlots, voice_socket
        slots = VoiceSlots(); events=[]
        class Socket:
            async def accept(self): pass
            async def receive(self):
                if not hasattr(self, 'started'):
                    self.started = True
                    return {'type':'websocket.receive','text':'{"type":"start"}'}
                await asyncio.Future()
            async def send_json(self, event): events.append(event)
            async def close(self, **_): pass
        async def status(): return {'state':'setup-required','message':'Install local model'}
        await voice_socket(Socket(), SimpleNamespace(status=status), slots, None)
        self.assertIsNone(slots.owner)
        self.assertEqual(events[0]['message'], 'Install local model')


class VoiceOrigins(unittest.TestCase):
    def test_foreign_and_missing_origins_cannot_open_microphone_service(self):
        from fastapi.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect
        from june.app import app
        with TestClient(app, base_url='http://127.0.0.1:8001') as client:
            for headers in ({}, {'Origin':'https://example.com'}):
                with self.subTest(headers=headers), self.assertRaises(WebSocketDisconnect):
                    with client.websocket_connect('/ws/voice', headers=headers): pass

class ReviewedRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_delayed_wake_keeps_voiced_question_in_preroll(self):
        events=[];clips=[]
        async def emit(event): events.append(event)
        async def transcribe(data): clips.append(data); return {'text':'Hey June, why?', 'durationMs':1}
        turn=VoiceTurn(emit, transcribe)
        for i in range(10): await turn.audio(bytes(3200), True, wake=i==9)
        for _ in range(16): await turn.audio(bytes(3200), False)
        await turn.flush()
        self.assertEqual(len(clips),1)
        self.assertEqual([e['text'] for e in events if e['type']=='transcript'], ['why?'])
        await turn.close()

    async def test_exception_from_delivery_cannot_escape_close(self):
        async def emit(event): pass
        async def fail(): raise RuntimeError('Socket closed during transcript delivery')
        turn=VoiceTurn(emit, None)
        turn.job=asyncio.create_task(fail());await asyncio.sleep(0)
        turn.buffer.extend(b'xx')
        await turn.close()
        self.assertEqual(turn.buffer,b'')

    async def test_disconnect_during_engine_startup_releases_session_without_pipeline(self):
        import threading
        from types import SimpleNamespace
        from unittest.mock import patch
        from june.realtime_socket import VoiceSlots, voice_socket
        entered,release=threading.Event(),threading.Event();slots=VoiceSlots();started=[]
        class Socket:
            def __init__(self): self.incoming=asyncio.Queue()
            async def accept(self): pass
            async def receive(self): return await self.incoming.get()
            async def send_json(self,event): pass
            async def close(self,**_): pass
        async def ready(): return {'state':'ready'}
        def detector(_): entered.set();release.wait(3);return object()
        engine=SimpleNamespace(Detectors=detector,make_pipeline=lambda *_:started.append(True))
        socket=Socket();await socket.incoming.put({'type':'websocket.receive','text':'{"type":"start"}'})
        with patch('june.realtime_socket.importlib.import_module', return_value=engine):
            task=asyncio.create_task(voice_socket(socket,SimpleNamespace(status=ready,model='test'),slots,SimpleNamespace(status=ready)))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait,1))
                await socket.incoming.put({'type':'websocket.disconnect'})
                done, _ = await asyncio.wait([task], timeout=.3)
                self.assertIn(task, done)
                self.assertIsNone(slots.owner)
                self.assertEqual(started,[])
            finally:
                release.set();await task

class WakeWindow(unittest.IsolatedAsyncioTestCase):
    async def test_wake_only_transcript_preserves_original_question_window(self):
        now=0.;events=[];calls=0
        async def emit(e): events.append(e)
        async def transcribe(_):
            nonlocal calls
            calls+=1
            return {'text':'Hey June' if calls==1 else 'What time is it?', 'durationMs':1}
        turn=VoiceTurn(emit,transcribe,clock=lambda:now)
        for i in range(8):
            now+=.1;await turn.audio(bytes(3200),True,wake=i==7)
        for _ in range(16): now+=.1;await turn.audio(bytes(3200),False)
        await turn.flush()
        self.assertEqual(turn.phase,'listening')
        self.assertLess(turn.deadline,11)
        for _ in range(8): now+=.1;await turn.audio(bytes(3200),True)
        for _ in range(16): now+=.1;await turn.audio(bytes(3200),False)
        await turn.flush()
        self.assertEqual([e['text'] for e in events if e['type']=='transcript'],['What time is it?'])
        await turn.close()

class SpeechDuringDecode(unittest.IsolatedAsyncioTestCase):
    async def scenario(self, question_at, decode_at):
        now=0.;events=[];gate=asyncio.Event();started=asyncio.Event();calls=0
        async def emit(e): events.append(e)
        async def transcribe(_):
            nonlocal calls
            calls+=1
            if calls==1:
                started.set();await gate.wait();return {'text':'Hey June','durationMs':1}
            return {'text':'What is Python?','durationMs':1}
        turn=VoiceTurn(emit,transcribe,clock=lambda:now)
        async def packet(voiced=False,wake=False):
            nonlocal now
            now+=.1;await turn.audio(bytes(3200),voiced,wake)
        for i in range(8): await packet(True,i==7)
        for _ in range(16): await packet()
        await started.wait()
        while now<question_at: await packet()
        for _ in range(10): await packet(True)
        while now<decode_at: await packet()
        gate.set();await turn.flush()
        for _ in range(16): await packet()
        await turn.flush()
        self.assertEqual([e['text'] for e in events if e['type']=='transcript'],['What is Python?'])
        await turn.close()

    async def test_question_during_slow_wake_decode_is_not_overwritten(self):
        await self.scenario(3,8)

    async def test_question_onset_before_deadline_survives_late_wake_decode(self):
        await self.scenario(9,11)


if __name__ == '__main__':
    unittest.main()

class NaturalInterruption(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.now = 0.
        async def emit(event): self.events.append(event)
        async def transcribe(_): return {'text': 'Wait, I meant five zero six zero.', 'durationMs': 10}
        self.turn = VoiceTurn(emit, transcribe, clock=lambda: self.now)
        self.turn.number = 1
        self.turn.phase = 'generating'

    async def asyncTearDown(self): await self.turn.close()

    async def audio(self, voiced, seconds=.02):
        self.now += seconds
        await self.turn.audio(b'\x00\x10' * int(16000 * seconds), voiced)

    async def test_sustained_speech_interrupts_generation_without_wake(self):
        for _ in range(15): await self.audio(True)
        self.assertEqual(self.turn.number, 2)
        self.assertEqual(self.turn.phase, 'listening')
        self.assertEqual(len([e for e in self.events if e['type']=='interrupt']), 1)
        await self.turn.activity(1, 'speaking')
        self.assertEqual(self.turn.phase, 'listening')
        for _ in range(80): await self.audio(False)
        await self.turn.flush()
        self.assertEqual([e['turn'] for e in self.events if e['type']=='transcript'], [2])

    async def test_short_noise_does_not_interrupt(self):
        for _ in range(4): await self.audio(True)
        for _ in range(20): await self.audio(False)
        self.assertEqual(self.turn.number, 1)
        self.assertFalse(any(e['type']=='interrupt' for e in self.events))

    async def probe(self):
        self.turn.phase = 'speaking'
        for _ in range(8): await self.audio(True)
        event = next(e for e in self.events if e['type']=='probe')
        await self.turn.probe_paused(1, event['probe'])
        return event['probe']

    async def test_speaker_echo_stops_with_pause_and_resumes_without_new_turn(self):
        async def no_words(_): return {'text': '[silence]', 'durationMs': 1}
        self.turn.transcribe = no_words
        probe = await self.probe()
        for _ in range(50): await self.audio(False)
        await self.turn.flush()
        self.assertEqual(self.turn.number, 1)
        self.assertFalse(any(e['type']=='interrupt' for e in self.events))
        self.assertTrue(any(e['type']=='resume' and e['probe']==probe for e in self.events))

    async def test_real_speech_after_playback_pause_owns_a_new_turn(self):
        await self.probe()
        for _ in range(30): await self.audio(True)
        self.assertEqual(self.turn.phase, 'listening')
        self.assertEqual(self.turn.number, 2)
        for _ in range(80): await self.audio(False)
        await self.turn.flush()
        self.assertEqual(len([e for e in self.events if e['type']=='transcript']), 1)
        self.assertFalse(any(e['type']=='resume' for e in self.events))

    async def test_stale_pause_ack_and_timeout_cannot_leave_playback_paused(self):
        self.turn.phase = 'speaking'
        for _ in range(8): await self.audio(True)
        probe = next(e for e in self.events if e['type']=='probe')['probe']
        await self.turn.probe_paused(0, probe)
        self.now += 3
        await self.turn.tick()
        self.assertTrue(any(e['type']=='error' and e['fatal'] for e in self.events))

class InterruptionReview(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events=[];self.now=0.
        async def emit(e): self.events.append(e)
        async def transcribe(_): return {'text':'Wait.', 'durationMs':15}
        self.turn=VoiceTurn(emit,transcribe,clock=lambda:self.now)
        self.turn.number=1;self.turn.phase='speaking'

    async def asyncTearDown(self): await self.turn.close()

    async def packet(self,voiced):
        self.now+=.020017
        await self.turn.audio(b'\x00\x10'*320,voiced)

    async def start_probe(self):
        for _ in range(8): await self.packet(True)
        probe=next(e for e in self.events if e['type']=='probe')
        await self.turn.probe_paused(1,probe['probe'])
        return probe

    async def test_interruption_retains_whole_pcm_samples_under_clock_jitter(self):
        await self.start_probe()
        for _ in range(25): await self.packet(True)
        self.assertEqual(len(self.turn.buffer)%2,0)
        import struct
        self.assertTrue(all(sample[0]==4096 for sample in struct.iter_unpack('<h',self.turn.buffer)))

    async def test_sentence_end_generating_feedback_cannot_release_probe(self):
        await self.start_probe()
        await self.turn.activity(1,'generating')
        self.assertIsNotNone(self.turn.probe)
        self.assertFalse(any(e['type']=='resume' for e in self.events))

    async def test_short_wait_is_validated_and_sent_without_another_wake(self):
        await self.start_probe()
        for _ in range(7): await self.packet(True)
        for _ in range(50): await self.packet(False)
        await self.turn.flush()
        self.assertTrue(any(e['type']=='interrupt' for e in self.events))
        self.assertEqual([e['text'] for e in self.events if e['type']=='transcript'],['Wait.'])

    async def test_short_spoken_echo_is_not_sent_as_a_question(self):
        async def echo(_): return {'text':'A graphics card.', 'durationMs':15}
        self.turn.transcribe=echo
        await self.turn.activity(1,'speaking','A graphics card helps render pictures.')
        await self.start_probe()
        for _ in range(50): await self.packet(False)
        await self.turn.flush()
        self.assertFalse(any(e['type']=='interrupt' for e in self.events))
        self.assertTrue(any(e['type']=='resume' for e in self.events))

class ShortProbeRaces(unittest.IsolatedAsyncioTestCase):
    async def test_new_wake_cancels_accepted_probe_before_transcript_delivery(self):
        events=[];now=0.;blocked=asyncio.Event();release=asyncio.Event()
        async def emit(e):
            events.append(e)
            if e['type']=='state' and e.get('phase')=='generating' and e['turn']==2:
                blocked.set();await release.wait()
        async def transcribe(_):return {'text':'Wait.', 'durationMs':1}
        turn=VoiceTurn(emit,transcribe,clock=lambda:now);turn.number=1;turn.phase='speaking'
        for i in range(60):
            now+=.02;await turn.audio(b'\x00\x10'*320,i<15)
            if turn.probe and turn.probe['paused'] is None:await turn.probe_paused(1,turn.probe['id'])
        await blocked.wait()
        await turn.wake();release.set();await asyncio.sleep(0)
        self.assertEqual(turn.number,3)
        self.assertFalse(any(e['type']=='transcript' for e in events))
        await turn.close()

    async def test_spoken_digit_echo_uses_same_normalization_as_transcript(self):
        async def ignore(_):pass
        turn=VoiceTurn(ignore,ignore)
        self.assertFalse(turn.is_new_short_speech('5060','five zero six zero'))
        self.assertFalse(turn.is_new_short_speech('The code is 7294.','The code is seven two nine four.'))
        self.assertTrue(turn.is_new_short_speech('5060','three zero six zero'))
        await turn.close()

class FeedbackOwnership(unittest.IsolatedAsyncioTestCase):
    async def test_old_completion_cannot_overwrite_a_wake_during_probe_cleanup(self):
        async def ignore(_):pass
        turn=VoiceTurn(ignore,ignore);turn.number=1;turn.phase='speaking'
        async def superseded(*args,**kwargs):
            turn.number=2;turn.phase='listening'
        turn.clear_probe=superseded
        await turn.activity(1,'complete')
        self.assertEqual(turn.phase,'listening')
        await turn.close()
