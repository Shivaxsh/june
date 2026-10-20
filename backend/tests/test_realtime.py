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
        import tempfile, os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as data_directory, patch.dict(os.environ, {'JUNE_DATA_HOME': data_directory}), TestClient(app, base_url='http://127.0.0.1:8001') as client:
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
        self.assertEqual(self.turn.number, 1)
        self.assertFalse(any(e['type'] == 'probe' for e in self.events))
        for _ in range(45): await self.audio(True)
        await asyncio.sleep(0)
        for _ in range(10): await self.audio(True)
        await asyncio.sleep(0)
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
        return self.turn.probe['id']

    async def test_speaker_echo_does_not_pause_or_start_a_new_turn(self):
        async def no_words(_): return {'text': '[silence]', 'durationMs': 1}
        self.turn.transcribe = no_words
        probe = await self.probe()
        for _ in range(50): await self.audio(False)
        await self.turn.flush()
        self.assertEqual(self.turn.number, 1)
        self.assertFalse(any(e['type']=='interrupt' for e in self.events))
        self.assertFalse(any(e['type']=='probe' for e in self.events))

    async def test_verified_real_speech_owns_a_new_turn(self):
        await self.probe()
        for _ in range(45): await self.audio(True)
        await asyncio.sleep(0)
        for _ in range(10): await self.audio(True)
        await asyncio.sleep(0)
        self.assertEqual(self.turn.phase, 'listening')
        self.assertEqual(self.turn.number, 2)
        for _ in range(80): await self.audio(False)
        await self.turn.flush()
        self.assertEqual(len([e for e in self.events if e['type']=='transcript']), 1)
        self.assertFalse(any(e['type']=='resume' for e in self.events))

    async def test_failed_word_verification_keeps_playback_running(self):
        async def timeout(_): raise TimeoutError()
        self.turn.transcribe = timeout
        self.turn.phase = 'speaking'
        for _ in range(55): await self.audio(True)
        await self.turn.flush()
        self.assertEqual(self.turn.phase, 'speaking')
        self.assertEqual(self.turn.number, 1)
        self.assertFalse(any(e['type'] in ('probe', 'interrupt', 'transcript') for e in self.events))

class InterruptionReview(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events=[];self.now=0.;self.clips=[]
        async def emit(e): self.events.append(e)
        async def transcribe(data):
            self.clips.append(data)
            return {'text':'Wait.', 'durationMs':15}
        self.turn=VoiceTurn(emit,transcribe,clock=lambda:self.now)
        self.turn.number=1;self.turn.phase='speaking'

    async def asyncTearDown(self): await self.turn.close()

    async def packet(self,voiced):
        self.now+=.020017
        await self.turn.audio(b'\x00\x10'*320,voiced)

    async def start_probe(self):
        for _ in range(8): await self.packet(True)
        return self.turn.probe

    async def test_interruption_retains_whole_pcm_samples_under_clock_jitter(self):
        await self.start_probe()
        for _ in range(50): await self.packet(True)
        await self.turn.flush()
        self.assertTrue(self.clips)
        clip=self.clips[0]
        from june.speech import validate_wav
        self.assertGreater(validate_wav(clip)['durationMs'],500)
        import struct
        self.assertTrue(all(sample[0]==4096 for sample in struct.iter_unpack('<h',clip[44:])))

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
        self.assertFalse(any(e['type']=='probe' for e in self.events))

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
        self.assertTrue(turn.is_playback_echo('5060','five zero six zero'))
        self.assertTrue(turn.is_playback_echo('The code is 7294.','The code is seven two nine four.'))
        self.assertFalse(turn.is_playback_echo('5060','three zero six zero'))
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

class CaptureOwnership(unittest.IsolatedAsyncioTestCase):
    async def test_capture_does_not_spawn_transcription_after_close_during_state_send(self):
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def emit(event):
            if event.get('phase') == 'transcribing':
                entered.set()
                await release.wait()
        async def transcribe(data):
            calls.append(True)
            return {'text': 'stale words', 'durationMs': 1}
        turn = VoiceTurn(emit, transcribe)
        turn.number = 1
        turn.buffer = bytearray(b'\x00\x10' * 16000)
        finishing = asyncio.create_task(turn.finish_capture())
        try:
            await asyncio.wait_for(entered.wait(), 1)
            await turn.close()
            release.set()
            await finishing
            await asyncio.sleep(0)
            self.assertEqual(calls, [])
            self.assertIsNone(turn.job)
        finally:
            release.set()
            await finishing
            await turn.close()

    async def test_capture_does_not_replace_new_turn_after_state_send_resumes(self):
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def emit(event):
            if event.get('phase') == 'transcribing':
                entered.set()
                await release.wait()
        async def transcribe(data):
            calls.append(True)
            return {'text': 'stale words', 'durationMs': 1}
        turn = VoiceTurn(emit, transcribe)
        turn.number = 1
        turn.buffer = bytearray(b'\x00\x10' * 16000)
        finishing = asyncio.create_task(turn.finish_capture())
        try:
            await asyncio.wait_for(entered.wait(), 1)
            await turn.wake()
            release.set()
            await finishing
            await asyncio.sleep(0)
            self.assertEqual(calls, [])
            self.assertEqual(turn.phase, 'listening')
            self.assertIsNone(turn.job)
        finally:
            release.set()
            await finishing
            await turn.close()

class PauseMatrix(unittest.IsolatedAsyncioTestCase):
    async def test_each_pause_setting_sends_once_after_its_silence_boundary(self):
        for pause, seconds in [('short', .8), ('normal', 1.5), ('patient', 2.5)]:
            with self.subTest(pause=pause):
                events, clips = [], []
                async def emit(event):
                    events.append(event)
                async def transcribe(data):
                    clips.append(data)
                    return {'text': 'What is Python?', 'durationMs': 1}
                turn = VoiceTurn(emit, transcribe, pause=pause)
                turn.number, turn.phase = 1, 'followup'
                try:
                    for _ in range(6):
                        await turn.audio(b'\x00\x10' * 1600, True)
                    for _ in range(round(seconds * 10) - 1):
                        await turn.audio(bytes(3200), False)
                    self.assertEqual(turn.phase, 'listening')
                    self.assertEqual(len(clips), 0)
                    await turn.audio(bytes(3200), False)
                    await turn.flush()
                    self.assertEqual(len(clips), 1)
                    self.assertEqual(len([e for e in events if e['type'] == 'transcript']), 1)
                    self.assertEqual(turn.phase, 'generating')
                finally:
                    await turn.close()

class FalseInterruptions(unittest.IsolatedAsyncioTestCase):
    """VAD is evidence of sound, never proof that the user took a turn."""
    async def asyncSetUp(self):
        self.now = 0.
        self.events = []
        self.result = '[noise]'
        async def emit(event): self.events.append(event)
        async def transcribe(_): return {'text': self.result, 'durationMs': 1}
        self.turn = VoiceTurn(emit, transcribe, clock=lambda: self.now)
        self.turn.number = 1
        self.turn.phase = 'generating'
        await self.turn.activity(1, 'speaking', 'A graphics card helps render pictures.')
        self.turn.phase = 'speaking'
        self.turn.spoken = 'A graphics card helps render pictures.'

    async def asyncTearDown(self): await self.turn.close()

    async def packet(self, voiced=True, elapsed=.02):
        self.now += elapsed
        await self.turn.audio(b'\x00\x10' * 320, voiced)
        if self.turn.probe and self.turn.probe['paused'] is None:
            await self.turn.probe_paused(1, self.turn.probe['id'])
        await asyncio.sleep(0)

    async def test_sustained_noise_never_cancels_reply_before_text_confirmation(self):
        blocked = asyncio.Event()
        async def slow(_):
            await blocked.wait()
            return {'text': '[noise]', 'durationMs': 1}
        self.turn.transcribe = slow
        for _ in range(70): await self.packet()
        self.assertEqual(self.turn.number, 1)
        self.assertFalse(any(e['type'] == 'interrupt' for e in self.events))
        blocked.set()
        await self.turn.flush()
        self.assertFalse(any(e['type'] == 'probe' for e in self.events))

    async def test_sustained_own_speech_is_rejected_without_audible_pause(self):
        self.result = 'A graphics card helps render pictures.'
        for _ in range(70): await self.packet()
        await self.turn.flush()
        self.assertEqual(self.turn.number, 1)
        self.assertFalse(any(e['type'] in ('interrupt', 'transcript') for e in self.events))
        self.assertFalse(any(e['type'] == 'probe' for e in self.events))

    async def test_sentence_gap_echo_cannot_use_unverified_generating_path(self):
        await self.turn.activity(1, 'generating')
        self.result = 'A graphics card helps render pictures.'
        for _ in range(70): await self.packet()
        await self.turn.flush()
        self.assertEqual(self.turn.number, 1)
        self.assertFalse(any(e['type'] == 'interrupt' for e in self.events))

    async def test_previous_sentence_echo_remains_known_after_next_sentence_starts(self):
        await self.turn.activity(1, 'speaking', 'The monitor displays the image.')
        self.result = 'A graphics card helps render pictures.'
        for _ in range(8): await self.packet()
        for _ in range(55): await self.packet(False)
        await self.turn.flush()
        self.assertFalse(any(e['type'] in ('interrupt', 'transcript') for e in self.events))

    async def test_wall_clock_stall_does_not_count_queued_echo_as_post_pause_speech(self):
        for _ in range(8): await self.packet()
        # Only 40 ms of audio arrived, even though this busy CPU took a second.
        await self.packet(elapsed=1.)
        await self.packet()
        self.assertEqual(self.turn.number, 1)
        self.assertFalse(any(e['type'] == 'interrupt' for e in self.events))

    async def test_wake_detector_echo_during_reply_still_requires_confirmation(self):
        self.result = 'A graphics card helps render pictures.'
        self.now += .02
        await self.turn.audio(b'\x00\x10' * 320, True, wake=True)
        self.assertEqual(self.turn.number, 1)
        self.assertFalse(any(e['type'] == 'wake' for e in self.events))

    async def test_followup_echo_is_not_sent_as_a_new_question(self):
        self.result = 'A graphics card helps render pictures.'
        await self.turn.activity(1, 'complete')
        for _ in range(35): await self.packet()
        for _ in range(80): await self.packet(False)
        await self.turn.flush()
        self.assertFalse(any(e['type'] == 'transcript' for e in self.events))

    async def test_generating_without_playback_accepts_a_different_question(self):
        self.turn.playback.clear()
        self.turn.spoken = ''
        self.turn.phase = 'generating'
        self.result = 'Tell me something else.'
        for _ in range(15): await self.packet()
        for _ in range(55): await self.packet(False)
        await self.turn.flush()
        self.assertEqual([e['text'] for e in self.events if e['type'] == 'transcript'], ['Tell me something else.'])

    async def test_completion_during_noise_probe_is_not_lost(self):
        for _ in range(8): await self.packet()
        await self.turn.activity(1, 'complete')
        for _ in range(55): await self.packet(False)
        await self.turn.flush()
        self.assertEqual(self.turn.phase, 'followup')
        self.assertIsNotNone(self.turn.deadline)
        self.assertFalse(any(e['type'] == 'interrupt' for e in self.events))

    async def test_continued_question_keeps_start_during_slow_confirmation(self):
        started, release = asyncio.Event(), asyncio.Event()
        clips = []
        async def slow(data):
            clips.append(data)
            if len(clips) == 1:
                started.set()
                await release.wait()
                return {'text': 'Wait, explain', 'durationMs': 1}
            return {'text': 'Wait, explain workers instead.', 'durationMs': 1}
        self.turn.transcribe = slow
        for _ in range(55): await self.packet()
        await started.wait()
        for _ in range(130): await self.packet()
        release.set()
        await self.turn.flush()
        self.assertEqual(self.turn.number, 2)
        # Over 2s elapsed during the decoder: an ordinary 2s pre-roll would
        # have discarded the beginning. The owned capture must keep it all.
        self.assertGreater(len(self.turn.buffer), 96000)
        for _ in range(80): await self.packet(False)
        await self.turn.flush()
        self.assertEqual([e['text'] for e in self.events if e['type'] == 'transcript'], ['Wait, explain workers instead.'])

    async def test_non_speech_hallucination_without_post_pause_voice_is_not_a_turn(self):
        self.result = 'Thank you for watching.'
        for _ in range(8): await self.packet()
        for _ in range(55): await self.packet(False)
        await self.turn.flush()
        self.assertEqual(self.turn.number, 1)
        self.assertFalse(any(e['type'] == 'transcript' for e in self.events))

    async def test_verified_wake_only_interruption_listens_for_the_question(self):
        self.result = 'Hey June.'
        for _ in range(15): await self.packet()
        for _ in range(55): await self.packet(False)
        await self.turn.flush()
        self.assertEqual(self.turn.number, 2)
        self.assertEqual(self.turn.phase, 'listening')
        self.assertFalse(any(e['type'] == 'transcript' for e in self.events))

    async def test_cancelled_pause_cannot_overwrite_deferred_completion(self):
        for _ in range(8): await self.packet()
        probe = self.turn.probe['id']
        await self.turn.activity(1, 'complete')
        await self.turn.probe_cancelled(1, probe)
        self.assertEqual(self.turn.phase, 'followup')

    async def test_one_word_followup_is_not_confused_with_echo(self):
        self.result = 'Linux.'
        await self.turn.activity(1, 'complete')
        for _ in range(35): await self.packet()
        for _ in range(80): await self.packet(False)
        await self.turn.flush()
        self.assertEqual([e['text'] for e in self.events if e['type'] == 'transcript'], ['Linux.'])

    async def test_caption_arriving_during_probe_is_still_an_echo_reference(self):
        self.turn.phase = 'generating'; self.turn.playback.clear(); self.turn.spoken = ''
        for _ in range(15): await self.packet()
        self.result = 'The monitor displays the image.'
        await self.turn.activity(1, 'speaking', self.result)
        for _ in range(55): await self.packet(False)
        await self.turn.flush()
        self.assertEqual(self.turn.number, 1)
        self.assertFalse(any(e['type'] == 'transcript' for e in self.events))

    async def test_user_question_during_noise_decode_is_checked_before_resuming(self):
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def slow(data):
            calls.append(data)
            if len(calls) == 1:
                started.set(); await release.wait()
                return {'text': '[noise]', 'durationMs': 1}
            return {'text': 'Wait, explain workers instead.', 'durationMs': 1}
        self.turn.transcribe = slow
        for _ in range(8): await self.packet()
        for _ in range(50): await self.packet(False)
        await started.wait()
        for _ in range(40): await self.packet()
        for _ in range(30): await self.packet(False)
        release.set()
        # A second owned probe check may be created as the first finishes.
        for _ in range(10):
            await asyncio.sleep(0)
        await self.turn.flush()
        self.assertEqual([e['text'] for e in self.events if e['type'] == 'transcript'], ['Wait, explain workers instead.'])
        self.assertFalse(any(e['type'] == 'resume' for e in self.events))

    async def test_unverified_noise_never_pauses_browser_playback(self):
        for _ in range(70): await self.packet()
        await self.turn.flush()
        self.assertFalse(any(e['type'] in ('probe', 'interrupt', 'transcript') for e in self.events))

    async def test_wake_only_decode_retains_question_spoken_during_the_check(self):
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def slow(data):
            calls.append(data)
            if len(calls) == 1:
                started.set(); await release.wait()
                return {'text': 'Hey June.', 'durationMs': 1}
            return {'text': 'Hey June, explain workers.', 'durationMs': 1}
        self.turn.transcribe = slow
        for _ in range(55): await self.packet()
        await started.wait()
        for _ in range(45): await self.packet()
        release.set(); await self.turn.flush()
        for _ in range(80): await self.packet(False)
        await self.turn.flush()
        self.assertEqual([e['text'] for e in self.events if e['type'] == 'transcript'], ['explain workers.'])

    async def test_wake_only_can_interrupt_before_first_spoken_sentence(self):
        self.turn.phase = 'generating'; self.turn.playback.clear(); self.turn.spoken = ''
        self.result = 'Hey June.'
        for _ in range(15): await self.packet()
        for _ in range(55): await self.packet(False)
        await self.turn.flush()
        self.assertEqual(self.turn.number, 2)
        self.assertEqual(self.turn.phase, 'listening')

    async def test_contextual_followup_question_is_not_echo(self):
        self.result = 'How does a graphics card render pictures?'
        await self.turn.activity(1, 'complete')
        for _ in range(35): await self.packet()
        for _ in range(80): await self.packet(False)
        await self.turn.flush()
        self.assertEqual([e['text'] for e in self.events if e['type'] == 'transcript'], ['How does a graphics card render pictures?'])

    async def test_clipped_echo_with_an_asr_word_error_is_not_a_question(self):
        self.result = 'Eating the page.'
        await self.turn.activity(1, 'speaking', 'It allows tasks such as fetching data from a server, updating the page, or managing user sessions.')
        for _ in range(65): await self.packet()
        await self.turn.flush()
        self.assertFalse(any(e['type'] in ('interrupt', 'transcript') for e in self.events))

    async def test_real_playback_state_updates_while_quiet_verification_runs(self):
        self.turn.phase = 'generating'
        for _ in range(15): await self.packet()
        await self.turn.activity(1, 'speaking', 'A graphics card helps render pictures.')
        self.assertEqual(self.turn.phase, 'speaking')
        await self.turn.activity(1, 'complete')
        self.assertEqual(self.turn.phase, 'followup')
        self.assertIsNotNone(self.turn.probe)

    async def test_echo_fuzziness_never_drops_a_corrected_number(self):
        self.assertFalse(self.turn.is_playback_echo('The code is 5060.', 'The code is 3060.'))
        self.assertFalse(self.turn.is_playback_echo('The RTX 5070 Ti.', 'The RTX 5070.'))

    async def test_echo_prefix_is_removed_from_the_real_interruption(self):
        self.result = 'A graphics card helps render pictures. Wait, keep it short.'
        for _ in range(65): await self.packet()
        for _ in range(80): await self.packet(False)
        await self.turn.flush()
        self.assertEqual([e['text'] for e in self.events if e['type'] == 'transcript'], ['Wait, keep it short.'])

    async def test_echo_prefix_is_removed_from_a_followup_question(self):
        self.result = 'A graphics card helps render pictures. How about you explain workers?'
        await self.turn.activity(1, 'complete')
        for _ in range(35): await self.packet()
        for _ in range(80): await self.packet(False)
        await self.turn.flush()
        self.assertEqual([e['text'] for e in self.events if e['type'] == 'transcript'], ['How about you explain workers?'])
