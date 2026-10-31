"""Native audio protocol ownership tests; never request a real microphone."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from june.errors import JuneError
from june.native_audio import NativeAudioService, validate_speak

VOICE={'id':'com.apple.ttsbundle.siri_nicky_en-US_compact','name':'Nicky','lang':'en-US','gender':'female','localService':True}
VALUE={'ownerId':'owner-1','requestId':'request-1','segmentId':'segment-1','text':'Hello June.','voiceId':VOICE['id'],'rate':.98}

class FakeAudio(NativeAudioService):
    def __init__(self):
        super().__init__(Path('/not-installed'))
        self.sent=[];self.available_voices=[VOICE];self.permission='granted'
    async def ensure_started(self):pass
    async def send(self,value):self.sent.append(value)

class NativeValidation(unittest.TestCase):
    def test_valid_and_invalid_speech(self):
        self.assertEqual(validate_speak(VALUE,[VOICE])['text'],'Hello June.')
        for change in ({'text':''},{'text':'a'*2001},{'rate':5},{'voiceId':'not-installed'},{'segmentId':'../../file'},{'ownerId':[]},{'turnId':True}):
            with self.subTest(change=change),self.assertRaises(JuneError):validate_speak({**VALUE,**change},[VOICE])

class NativeOwnership(unittest.IsolatedAsyncioTestCase):
    async def test_releasing_native_session_does_not_stop_new_manual_playback(self):
        service=FakeAudio()
        service.capture_owner='owner-1';service.capture_session='session-1';service.capture_turn=1
        native=service.speak({**VALUE,'voiceSessionId':'session-1','turnId':1})
        manual=service.speak({**VALUE,'requestId':'manual-request','segmentId':'manual-segment'})
        await anext(native)
        self.addAsyncCleanup(native.aclose)
        self.addAsyncCleanup(manual.aclose)
        await service.release('session-1')
        await anext(manual)
        self.assertIsNone(service.capture_owner)
        self.assertEqual((await anext(native))['type'],'cancelled')
        self.assertIn('manual-segment',service.jobs)
        self.assertNotIn(('owner-1','manual-request'),service.revoked)
        self.assertEqual([c['requestId'] for c in service.sent if c['type']=='stop'],['request-1'])
        await service.receive({'type':'playback','id':'manual-segment','phase':'end'})
        self.assertEqual((await anext(manual))['type'],'end')
        late=service.speak({**VALUE,'segmentId':'late-native','voiceSessionId':'session-1','turnId':1})
        with self.assertRaises(JuneError):await anext(late)

    async def test_late_release_does_not_touch_replacement_session(self):
        service=FakeAudio()
        service.capture_owner='owner-1';service.capture_session='session-2';service.capture_turn=2
        stream=service.speak({**VALUE,'voiceSessionId':'session-2','turnId':2})
        await anext(stream)
        self.addAsyncCleanup(stream.aclose)
        await service.release('session-1')
        self.assertEqual(service.capture_session,'session-2')
        self.assertIn('segment-1',service.jobs)
        self.assertEqual([c for c in service.sent if c['type']=='stop'],[])

    async def test_missing_helper_is_explicit_and_does_not_capture(self):
        with tempfile.TemporaryDirectory() as d:
            service=NativeAudioService(Path(d))
            self.assertEqual((await service.status())['state'],'missing')
            self.assertIsNone(service.capture_owner)
            await service.close()
    async def test_cancelled_request_cannot_start_late_or_stop_a_new_request(self):
        service=FakeAudio()
        await service.stop('owner-1','request-1')
        old=service.speak(VALUE)
        with self.assertRaises(JuneError):await anext(old)
        stream=service.speak({**VALUE,'requestId':'request-2'})
        self.assertEqual((await anext(stream))['type'],'accepted')
        await service.stop('owner-1','request-1')
        self.assertIn('segment-1',service.jobs)
        await stream.aclose()
        self.assertNotIn('segment-1',service.jobs)
    async def test_stale_native_turn_is_rejected_and_second_tab_cannot_speak(self):
        service=FakeAudio();service.capture_owner='owner-1';service.capture_session='session-1';service.capture_turn=3
        for change in ({'ownerId':'owner-2'},{'voiceSessionId':'old','turnId':3},{'voiceSessionId':'session-1','turnId':2}):
            stream=service.speak({**VALUE,**change})
            with self.subTest(change=change),self.assertRaises(JuneError):await anext(stream)
    async def test_native_audio_packets_are_bounded_and_late_sessions_ignored(self):
        import base64
        service=FakeAudio();q=asyncio.Queue(4);service.captures['session-1']=q
        await service.receive({'type':'audio','session':'old','pcm':base64.b64encode(b'\0'*640).decode()})
        self.assertTrue(q.empty())
        await service.receive({'type':'audio','session':'session-1','pcm':base64.b64encode(b'\0'*640).decode(),'rms':.1})
        self.assertEqual(len((await q.get())['pcm']),640)
        with self.assertRaises(ValueError):await service.receive({'type':'audio','session':'session-1','pcm':base64.b64encode(b'\0'*641).decode()})


class NativeInputHardening(unittest.IsolatedAsyncioTestCase):
    async def test_surrogate_text_and_unhashable_voice_are_readable_request_errors(self):
        for change in ({'text': '\ud800'}, {'text': 'hello\udfff'}, {'voiceId': []}):
            with self.subTest(change=repr(change)):
                try:
                    validate_speak({**VALUE, **change}, [VOICE])
                except JuneError as error:
                    self.assertEqual(error.status, 400)
                except Exception as error:
                    self.fail('Validation leaked ' + type(error).__name__)
                else:
                    self.fail('Malformed speech request was accepted')

    async def test_boundary_level_must_be_finite_numeric(self):
        service = FakeAudio()
        stream = service.speak(VALUE)
        await anext(stream)
        self.addAsyncCleanup(stream.aclose)
        for level in (float('nan'), float('inf'), -float('inf'), None, {}, True, '0.5'):
            with self.subTest(level=repr(level)):
                try:
                    await service.receive({'type': 'playback', 'id': 'segment-1', 'phase': 'boundary', 'level': level})
                except ValueError:
                    pass
                except Exception as error:
                    self.fail('Malformed IPC leaked ' + type(error).__name__)
                else:
                    self.fail('Invalid boundary level was accepted')

    async def test_valid_optional_timings_are_forwarded_and_absent_values_stay_absent(self):
        service = FakeAudio()
        stream = service.speak(VALUE)
        await anext(stream)
        self.addAsyncCleanup(stream.aclose)
        await service.receive({'type': 'playback', 'id': 'segment-1', 'phase': 'start', 'firstAudioMs': 0})
        start = await anext(stream)
        self.assertIn('firstAudioMs', start)
        self.assertEqual(start['firstAudioMs'], 0)
        await service.receive({'type': 'playback', 'id': 'segment-1', 'phase': 'boundary', 'level': .25})
        boundary = await anext(stream)
        self.assertEqual(boundary['level'], .25)
        self.assertNotIn('playbackMs', boundary)
        await service.receive({'type': 'playback', 'id': 'segment-1', 'phase': 'end', 'playbackMs': 180000})
        self.assertEqual((await anext(stream))['playbackMs'], 180000)
        await stream.aclose()
        self.assertFalse(any(c['type'] == 'stop' for c in service.sent), 'Normal segment completion must not revoke prefetched speech')

    async def test_invalid_timings_and_ipc_types_are_validation_errors(self):
        service = FakeAudio()
        stream = service.speak(VALUE)
        await anext(stream)
        self.addAsyncCleanup(stream.aclose)
        frames = [None, [], {'type': []}, {'type': 'ready', 'voices': None},
                  {'type': 'result', 'id': []}, {'type': 'playback', 'id': []},
                  {'type': 'audio', 'session': []}, {'type': 'capture-error', 'session': []}]
        frames += [{'type': 'playback', 'id': 'segment-1', 'phase': 'start', key: value}
                   for key in ('firstAudioMs', 'playbackMs')
                   for value in (float('nan'), float('inf'), -1, 180001, True, '1', None, {})]
        for frame in frames:
            with self.subTest(frame=repr(frame)):
                try:
                    await service.receive(frame)
                except ValueError:
                    pass
                except Exception as error:
                    self.fail('Malformed IPC leaked ' + type(error).__name__)
                else:
                    self.fail('Malformed IPC was accepted')

    async def test_command_timeout_is_an_explicit_audio_error(self):
        service = FakeAudio()
        try:
            await service.command('prepare', timeout=.01, voiceId=VOICE['id'])
        except JuneError as error:
            self.assertEqual(error.status, 503)
            self.assertIn('tim', error.message.lower())
        except Exception as error:
            self.fail('Warm command leaked ' + type(error).__name__)
        else:
            self.fail('A missing command response was accepted')


class NativeCancellation(unittest.IsolatedAsyncioTestCase):
    async def test_manual_release_wait_is_bounded_but_native_speech_does_not_wait(self):
        from unittest.mock import patch
        service=FakeAudio()
        service.capture_owner='owner-1';service.capture_session='session-1';service.capture_turn=1
        # A capture owns the graph until its release command is on the pipe.
        service.capture_released.clear()
        native=service.speak({**VALUE,'voiceSessionId':'session-1','turnId':1})
        self.assertEqual((await anext(native))['type'],'accepted')
        self.addAsyncCleanup(native.aclose)
        manual=service.speak({**VALUE,'segmentId':'manual','requestId':'manual'})
        with patch('june.native_audio.RELEASE_WAIT_SECONDS',.01):
            with self.assertRaises(JuneError) as busy:await anext(manual)
        self.assertEqual(busy.exception.status,409)
        self.assertEqual([c['id'] for c in service.sent if c['type']=='speak'],['segment-1'])

    async def test_manual_speech_waits_for_release_pipe_order_and_rechecks_revocation(self):
        class Releasing(FakeAudio):
            async def send(self,value):
                if value['type']=='release':
                    entered.set()
                    await release.wait()
                await super().send(value)
        for revoke in (False,True):
            with self.subTest(revoke=revoke):
                entered,release=asyncio.Event(),asyncio.Event()
                service=Releasing()
                # Exercise capture's real lifecycle (including its release barrier).
                async def capture_command(*args,**kwargs):return {}
                service.command=capture_command
                await service.capture('owner-1','session-1')
                stream=service.speak(VALUE)
                manual=asyncio.create_task(anext(stream))
                closing=asyncio.create_task(service.release('session-1'))
                try:
                    await asyncio.wait_for(entered.wait(),.2)
                    await asyncio.sleep(0)
                    self.assertFalse(manual.done(),'Manual speech raced the pending native release')
                    self.assertFalse(any(c['type']=='speak' for c in service.sent))
                    other=service.speak({**VALUE,'ownerId':'owner-2'})
                    with self.assertRaises(JuneError):await anext(other)
                    if revoke:await service.stop('owner-1','request-1')
                finally:
                    release.set()
                    await closing
                if revoke:
                    with self.assertRaises(JuneError):await manual
                    self.assertFalse(any(c['type']=='speak' for c in service.sent))
                else:
                    self.assertEqual((await manual)['type'],'accepted')
                    self.assertEqual([c['type'] for c in service.sent],['release','speak'])
                await stream.aclose()

    async def test_disconnect_keeps_owner_until_stop_is_written(self):
        class BlockStop(FakeAudio):
            async def send(self, value):
                if value['type'] == 'stop':
                    stopping.set()
                    await release.wait()
                await super().send(value)
        stopping, release = asyncio.Event(), asyncio.Event()
        service = BlockStop()
        stream = service.speak(VALUE)
        await anext(stream)
        closing = asyncio.create_task(stream.aclose())
        self.addAsyncCleanup(stream.aclose)
        try:
            await asyncio.wait_for(stopping.wait(), .2)
            self.assertIn('segment-1', service.jobs)
            other = service.speak({**VALUE, 'ownerId': 'owner-2', 'requestId': 'new'})
            with self.assertRaises(JuneError):
                await anext(other)
            closing.cancel()
            await asyncio.sleep(0)
            self.assertFalse(closing.done(), 'Task cancellation abandoned the stop write')
        finally:
            release.set()
            await asyncio.gather(closing, return_exceptions=True)
        self.assertNotIn('segment-1', service.jobs)
        self.assertTrue(any(c['type'] == 'stop' for c in service.sent))

    async def test_anyio_disconnect_with_contended_writer_stops_whole_request(self):
        import anyio
        class Contended(FakeAudio):
            def __init__(self):
                super().__init__()
                self.lock = asyncio.Lock()
            async def send(self, value):
                async with self.lock:
                    self.sent.append(value)
        service = Contended()
        first = service.speak(VALUE)
        second = service.speak({**VALUE, 'segmentId': 'segment-2'})
        await anext(first)
        await anext(second)
        self.addAsyncCleanup(first.aclose)
        self.addAsyncCleanup(second.aclose)
        await service.lock.acquire()
        async def release_writer():
            await asyncio.sleep(.02)
            service.lock.release()
        release = asyncio.create_task(release_writer())
        with anyio.CancelScope() as scope:
            scope.cancel()
            await first.aclose()
        await release
        stops = [c for c in service.sent if c['type'] == 'stop']
        self.assertEqual(stops, [{'type': 'stop', 'ownerId': 'owner-1', 'requestId': 'request-1'}])
        self.assertNotIn('segment-1', service.jobs)
        self.assertNotIn('segment-2', service.jobs)
        self.assertEqual((await anext(second))['type'], 'cancelled')
        late = service.speak({**VALUE, 'segmentId': 'late'})
        with self.assertRaises(JuneError):
            await anext(late)
        self.assertFalse(any(c['type'] == 'cancel' for c in service.sent), 'Disconnect must not pump the next revoked segment')

    async def test_normal_end_does_not_stop_the_next_prefetched_segment(self):
        service = FakeAudio()
        first = service.speak(VALUE)
        second = service.speak({**VALUE, 'segmentId': 'segment-2'})
        await anext(first)
        await anext(second)
        self.addAsyncCleanup(second.aclose)
        await service.receive({'type': 'playback', 'id': 'segment-1', 'phase': 'end'})
        self.assertEqual((await anext(first))['type'], 'end')
        await first.aclose()
        self.assertIn('segment-2', service.jobs)
        self.assertNotIn(('owner-1', 'request-1'), service.revoked)
        self.assertFalse(any(c['type'] == 'stop' for c in service.sent))


class WorkerPipe:
    def __init__(self):
        self.writes = []
        self.block = None
    def write(self, data):
        self.writes.append(data)
    async def drain(self):
        if self.block:
            await self.block.wait()


class WorkerProcess:
    """In-memory subprocess boundary: no helper execution or microphone access."""
    def __init__(self):
        import json
        self.stdout = asyncio.StreamReader()
        self.stdin = WorkerPipe()
        self.returncode = None
        self.exited = asyncio.Event()
        self.wait_release = None
        self.stdout.feed_data((json.dumps({'type': 'ready', 'voices': [VOICE], 'permission': 'granted'}) + '\n').encode())
    def terminate(self):
        self.exit(-15)
    def kill(self):
        self.exit(-9)
    def exit(self, code):
        if self.returncode is None:
            self.returncode = code
            self.stdout.feed_eof()
            self.exited.set()
    async def wait(self):
        await self.exited.wait()
        if self.wait_release:
            await self.wait_release.wait()
        return self.returncode


class NativeLifecycle(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from unittest.mock import patch
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.service = NativeAudioService(directory.name)
        self.service.binary.parent.mkdir(parents=True)
        self.service.binary.touch()
        self.workers = []
        async def spawn(*args, **kwargs):
            worker = WorkerProcess()
            self.workers.append(worker)
            return worker
        patcher = patch('june.native_audio.asyncio.create_subprocess_exec', side_effect=spawn)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addAsyncCleanup(self.service.close)

    async def test_restart_retires_old_reader_and_heartbeat_before_replacement(self):
        await self.service.ensure_started()
        old_reader, old_heartbeat = self.service.reader, self.service.heartbeat
        old = self.workers[0]
        old.returncode = 1
        old.exited.set()
        # Keep stdout open to force the stale reader/heartbeat retirement path.
        await self.service.ensure_started()
        self.assertTrue(old_reader.done(), 'Old reader survives a worker replacement')
        self.assertTrue(old_heartbeat.done(), 'Old heartbeat survives a worker replacement')
        self.assertIs(self.service.process, self.workers[1])
        self.assertTrue(self.service.ready.result())

    async def test_shutdown_rechecks_closed_after_waiting_for_start_lock(self):
        await self.service.start_lock.acquire()
        waiting = asyncio.create_task(self.service.ensure_started())
        await asyncio.sleep(0)
        self.service.closed = True
        self.service.start_lock.release()
        try:
            await waiting
        except JuneError:
            pass
        else:
            self.fail('A queued startup spawned a helper after shutdown')
        self.assertEqual(self.workers, [])

    async def test_termination_cannot_clear_a_concurrent_replacement(self):
        await self.service.ensure_started()
        old = self.workers[0]
        old.wait_release = asyncio.Event()
        stopping = asyncio.create_task(self.service.terminate())
        await old.exited.wait()
        restarting = asyncio.create_task(self.service.ensure_started())
        await asyncio.sleep(.01)
        self.assertEqual(len(self.workers), 1, 'Replacement spawned before old termination finished')
        old.wait_release.set()
        await stopping
        await restarting
        self.assertIs(self.service.process, self.workers[1])
        self.assertIsNone(self.workers[1].returncode)

    async def test_malformed_ipc_fails_pending_commands_and_reaps_the_worker(self):
        await self.service.ensure_started()
        worker = self.workers[0]
        pending = asyncio.create_task(self.service.command('status'))
        await asyncio.sleep(.01)
        worker.stdout.feed_data(b'{"type":"result","id":[]}\n')
        try:
            await asyncio.wait_for(pending, .5)
        except JuneError as error:
            self.assertEqual(error.code, 'audio-offline')
        except Exception as error:
            self.fail('Malformed IPC did not fail the command cleanly: ' + type(error).__name__)
        self.assertIsNotNone(worker.returncode, 'Malformed IPC left its child alive')

    async def test_cancelled_spawn_is_reaped_before_startup_returns(self):
        from unittest.mock import patch
        entered, release = asyncio.Event(), asyncio.Event()
        worker = WorkerProcess()
        async def delayed_spawn(*args, **kwargs):
            entered.set()
            await release.wait()
            return worker
        with patch('june.native_audio.asyncio.create_subprocess_exec', side_effect=delayed_spawn):
            starting = asyncio.create_task(self.service.ensure_started())
            await entered.wait()
            starting.cancel()
            await asyncio.sleep(0)
            starting.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await starting
        self.assertIsNotNone(worker.returncode, 'Cancelled spawn leaked its child')
        self.assertIsNone(self.service.process)

    async def test_cancelled_termination_finishes_reaping_before_unlocking(self):
        await self.service.ensure_started()
        worker = self.workers[0]
        worker.wait_release = asyncio.Event()
        stopping = asyncio.create_task(self.service.terminate())
        await worker.exited.wait()
        stopping.cancel()
        await asyncio.sleep(0)
        self.assertFalse(stopping.done(), 'Cancellation abandoned child reaping')
        worker.wait_release.set()
        with self.assertRaises(asyncio.CancelledError):
            await stopping
        self.assertIsNone(self.service.process)
        await self.service.ensure_started()
        self.assertIs(self.service.process, self.workers[1])

    async def test_cancelled_ready_wait_reaps_the_unready_child(self):
        from unittest.mock import patch
        worker = WorkerProcess()
        worker.stdout = asyncio.StreamReader()
        with patch('june.native_audio.asyncio.create_subprocess_exec', return_value=worker):
            starting = asyncio.create_task(self.service.ensure_started())
            while self.service.process is None:
                await asyncio.sleep(0)
            starting.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await starting
        self.assertIsNotNone(worker.returncode)
        self.assertIsNone(self.service.process)

    async def test_prepare_timeout_reaps_latent_work_and_status_restarts(self):
        from unittest.mock import patch
        import json
        await self.service.ensure_started()
        old=self.workers[0]
        old_ready=self.service.ready
        self.service.voice_warm=True
        with self.assertRaises(JuneError) as failed:
            await self.service.command('prepare',timeout=.01,voiceId=VOICE['id'])
        self.assertEqual(failed.exception.code,'audio-timeout')
        self.assertIsNotNone(old.returncode)
        self.assertFalse(self.service.voice_warm)
        self.assertEqual(self.service.commands,{})
        self.assertEqual((await self.service.status())['state'],'ready')
        self.assertIs(self.service.process,self.workers[1])
        await self.service.terminate(old,old_ready)
        self.assertIs(self.service.process,self.workers[1])
        self.assertTrue(self.service.ready.result())
        self.assertFalse(self.service.voice_warm)
        self.assertTrue(any(json.loads(line)['type']=='prepare' for line in old.stdin.writes))
        original_command=self.service.command
        async def short_command(kind,**values):
            values['timeout']=.01
            return await original_command(kind,**values)
        with patch.object(self.service,'command',short_command):
            with self.assertRaises(JuneError):await self.service.warm()
        self.assertFalse(self.service.voice_warm)
        self.assertIsNotNone(self.workers[1].returncode)
        self.assertEqual((await self.service.status())['state'],'ready')

    async def test_cancelled_retirement_waiting_for_lock_still_reaps_child(self):
        await self.service.ensure_started()
        worker=self.workers[0]
        await self.service.start_lock.acquire()
        stopping=asyncio.create_task(self.service.terminate())
        await asyncio.sleep(0)
        stopping.cancel()
        await asyncio.sleep(0)
        stopping.cancel()
        self.service.start_lock.release()
        with self.assertRaises(asyncio.CancelledError):await stopping
        self.assertIsNotNone(worker.returncode)
        self.assertIsNone(self.service.process)

    async def test_prepare_timeout_includes_a_contended_pipe(self):
        await self.service.ensure_started()
        worker=self.workers[0]
        await self.service.write_lock.acquire()
        pending=asyncio.create_task(self.service.command('prepare',timeout=.01,voiceId=VOICE['id']))
        try:
            with self.assertRaises(JuneError) as failed:await asyncio.wait_for(pending,.2)
            self.assertEqual(failed.exception.code,'audio-timeout')
            self.assertIsNotNone(worker.returncode)
        finally:self.service.write_lock.release()

    async def test_blocked_disconnect_stop_reaps_worker_before_releasing_job(self):
        from unittest.mock import patch
        stream=self.service.speak(VALUE)
        await anext(stream)
        worker=self.workers[0]
        await self.service.write_lock.acquire()
        try:
            with patch('june.native_audio.CLEANUP_WRITE_SECONDS',.01):
                await asyncio.wait_for(stream.aclose(),.5)
        finally:self.service.write_lock.release()
        self.assertIsNotNone(worker.returncode)
        self.assertEqual(self.service.jobs,{})
        self.assertIn(('owner-1','request-1'),self.service.revoked)
        self.assertIsNone(self.service.process)

    async def test_old_release_finally_cannot_clear_new_capture_generation(self):
        from unittest.mock import patch
        retired,finish_release=asyncio.Event(),asyncio.Event()
        original_send=self.service.send
        original_terminate=self.service.terminate
        async def command(*args,**kwargs):return {}
        async def send(value):
            if value['type']=='release':raise JuneError('audio-offline','Disconnected',503)
            await original_send(value)
        async def terminate(process=None,ready=None):
            await original_terminate(process,ready)
            retired.set()
            await finish_release.wait()
        with patch.object(self.service,'command',command),patch.object(self.service,'send',send),patch.object(self.service,'terminate',terminate):
            await self.service.capture('owner-1','session-1')
            releasing=asyncio.create_task(self.service.release('session-1'))
            try:
                await asyncio.wait_for(retired.wait(),.5)
                await self.service.capture('owner-2','session-2')
            finally:
                finish_release.set()
                await releasing
            self.assertEqual(self.service.capture_owner,'owner-2')
            self.assertEqual(self.service.capture_session,'session-2')
            self.assertFalse(self.service.capture_released.is_set())
