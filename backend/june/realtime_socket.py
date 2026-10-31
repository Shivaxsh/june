"""Bounded browser transport and one microphone owner for this local backend."""
import asyncio
import statistics
import logging
import traceback
from contextlib import suppress
import importlib
import json
import time
import uuid

from fastapi import WebSocketDisconnect

from .realtime_state import VoiceTurn, PAUSES
from .errors import JuneError


class VoiceSlots:
    def __init__(self):
        self.owner = None

    def claim(self):
        if self.owner is not None:
            return None
        self.owner = uuid.uuid4().hex
        return self.owner

    def release(self, owner):
        if self.owner == owner:
            self.owner = None


async def voice_socket(socket, assets, slots, speech, native_audio=None, runtime=None):
    await socket.accept()
    owner = slots.claim()
    if owner is None:
        await socket.send_json({'type': 'error', 'fatal': True, 'message': 'Hands-free is active in another tab. Disable it there first.'})
        await socket.close(code=1008)
        return
    turn = pipeline = runner_task = None
    ready = asyncio.Event()
    failed = asyncio.Event()
    send_lock = asyncio.Lock()
    pending = 0
    alive = True
    startup_receiver = None
    native_source=False;client_owner=None;native_feeder=None;native_level=0.;noise_floor=.001

    async def startup(operation):
        # Keep reading disconnects while imports/model construction run off the
        # event loop. Cancelled thread results are discarded before pipeline use.
        work = asyncio.create_task(operation)
        try:
            done, _ = await asyncio.wait((work, startup_receiver), timeout=40, return_when=asyncio.FIRST_COMPLETED)
            if startup_receiver in done:
                packet = await startup_receiver
                if packet['type'] == 'websocket.disconnect':
                    raise WebSocketDisconnect()
                raise ValueError('Audio arrived before voice readiness')
            if work not in done:
                raise TimeoutError('Voice initialization timed out')
            return await work
        finally:
            if not work.done():
                work.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await work

    async def emit(event):
        if not alive:
            return
        if native_source and client_owner and type(event.get('turn')) is int:
            await native_audio.update_turn(client_owner,owner,event['turn'],interrupted=event.get('type') in ('wake','interrupt'))
        async with send_lock:
            await asyncio.wait_for(socket.send_json({**event, 'session': owner}), 3)

    async def fail(message):
        if not failed.is_set():
            failed.set()
            with suppress(Exception):
                await emit({'type': 'error', 'fatal': True, 'message': message})

    def consumed(size):
        nonlocal pending
        pending = max(0, pending - size)

    async def metrics(probability):
        await emit({'type': 'metrics', 'vad': round(probability, 3), **({'level':min(1,native_level*5),'audioEngine':'mac-native'} if native_source else {})})

    async def read_control():
        packet = await asyncio.wait_for(socket.receive(), 15)
        if packet['type'] == 'websocket.disconnect':
            raise WebSocketDisconnect()
        text = packet.get('text')
        if not isinstance(text, str) or len(text.encode()) > 32000:
            raise ValueError('Invalid voice control')
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError('Invalid voice control')
        return value

    try:
        config = await read_control()
        if config.get('type') != 'start' or config.get('pause', 'normal') not in PAUSES:
            raise ValueError('Invalid voice start')
        native_source=config.get('audioSource')=='native'
        if native_source:
            from .native_audio import identifier
            client_owner=config.get('ownerId')
            if native_audio is None or not identifier(client_owner):raise ValueError('Invalid native capture owner')
        startup_receiver = asyncio.create_task(socket.receive())
        status = await startup(assets.status())
        if status['state'] != 'ready':
            await fail(status['message'])
            return
        status = await startup(speech.status())
        if status['state'] != 'ready':
            await fail(status['message'])
            return
        engine = await startup(asyncio.to_thread(importlib.import_module, 'june.realtime_engine'))
        detectors = await startup(runtime.detector(engine) if runtime and native_source else asyncio.to_thread(engine.Detectors, assets.model))
        native_queue=None
        if native_source:
            native_queue=await startup(native_audio.capture(client_owner,owner))
            # Measure one second of processed room audio before announcing ready.
            async def calibrate():
                values=[]
                for _ in range(50):
                    packet=await asyncio.wait_for(native_queue.get(),3)
                    if packet.get('error'):raise ValueError('Capture stopped')
                    _,_,probability=await asyncio.to_thread(detectors.analyse,packet['pcm'])
                    if probability<.35:values.append(packet['rms'])
                return max(.0005,statistics.median(values) if values else .001)
            noise_floor=await startup(calibrate())
        turn = VoiceTurn(emit, speech.transcribe, config.get('pause', 'normal'),processed_input=native_source)
        pipeline, runner = engine.make_pipeline(detectors, turn, consumed, fail, ready, metrics)
        runner_task = asyncio.create_task(runner.run(pipeline))
        await startup(ready.wait())
        startup_receiver.cancel()
        with suppress(asyncio.CancelledError):
            await startup_receiver
        startup_receiver = None
        await emit({'type': 'ready', 'turn': 0})
        await turn.state('waiting')

        async def feed_native():
            nonlocal pending,native_level,noise_floor
            try:
                while True:
                    packet=await asyncio.wait_for(native_queue.get(),3)
                    if packet.get('error'):
                        await fail(packet['error']);return
                    pcm=packet['pcm'];native_level=packet['rms']
                    if pending+len(pcm)>64000:
                        await fail('Native speech processing fell behind. Enable hands-free again.');return
                    pending+=len(pcm)
                    await pipeline.queue_frame(engine.PCMFrame(pcm,processed=True,rms=native_level,noise_floor=noise_floor))
            except asyncio.CancelledError:raise
            except (TimeoutError,JuneError,ValueError):await fail('Native microphone capture stopped. Check the audio device and enable hands-free again.')
        if native_source:native_feeder=asyncio.create_task(feed_native())

        async def watchdog():
            while not failed.is_set():
                await asyncio.sleep(.25)
                await turn.tick()

        watcher = asyncio.create_task(watchdog())
        receiver = None
        failure_wait = asyncio.create_task(failed.wait())
        try:
            while not failed.is_set():
                receiver = asyncio.create_task(socket.receive())
                done, _ = await asyncio.wait((receiver, failure_wait, runner_task), timeout=15, return_when=asyncio.FIRST_COMPLETED)
                if receiver not in done:
                    await fail('The microphone connection stopped responding. Enable hands-free again.')
                    break
                packet = await receiver
                if packet['type'] == 'websocket.disconnect':
                    break
                if packet.get('bytes') is not None:
                    if native_source:raise ValueError('Browser PCM is not accepted during native capture')
                    data = packet['bytes']
                    if not data or len(data) > 4096 or len(data) % 2:
                        raise ValueError('Invalid PCM packet')
                    if pending + len(data) > 64000:
                        await fail('Speech processing fell behind. Try again after closing other busy apps.')
                        break
                    pending += len(data)
                    await pipeline.queue_frame(engine.PCMFrame(data))
                else:
                    text = packet.get('text', '')
                    if len(text.encode()) > 32000:
                        raise ValueError('Oversized control')
                    control = json.loads(text)
                    if not isinstance(control, dict) or control.get('session') != owner:
                        raise ValueError('Invalid voice session')
                    kind = control.get('type')
                    if kind == 'ping':
                        await emit({'type': 'pong'})
                    elif kind == 'activity' and type(control.get('turn')) is int and control.get('phase') in ('generating', 'speaking', 'complete', 'failed', 'cancel'):
                        spoken = control.get('text', '')
                        if not isinstance(spoken, str) or len(spoken) > 4000:
                            raise ValueError('Invalid playback reference')
                        await turn.activity(control['turn'], control['phase'], spoken)
                    elif kind == 'probe-paused' and type(control.get('turn')) is int and type(control.get('probe')) is int:
                        await turn.probe_paused(control['turn'], control['probe'])
                    elif kind == 'probe-cancelled' and type(control.get('turn')) is int and type(control.get('probe')) is int:
                        await turn.probe_cancelled(control['turn'], control['probe'])
                    else:
                        raise ValueError('Invalid voice control')
        finally:
            for task in (watcher, receiver, failure_wait, native_feeder):
                if task is not None:
                    task.cancel()
                    with suppress(asyncio.CancelledError, WebSocketDisconnect):
                        await task
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except JuneError as error:
        await fail(error.message)
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        await fail('The voice connection received an invalid message. Enable hands-free again.')
    except Exception as error:
        frame=traceback.extract_tb(error.__traceback__)[-1]
        logging.getLogger('june.voice').warning('Voice startup failure type=%s location=%s:%s session=%s',type(error).__name__,frame.name,frame.lineno,owner)
        await fail('Local hands-free could not start. Run npm run realtime:setup and restart June.')
    finally:
        alive = False
        if native_source and native_audio is not None:
            with suppress(Exception):await native_audio.release(owner)
        if native_feeder:
            native_feeder.cancel()
            with suppress(asyncio.CancelledError,Exception):await native_feeder
        try:
            if startup_receiver is not None:
                startup_receiver.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await startup_receiver
            if turn is not None:
                with suppress(Exception):
                    await turn.close()
            if pipeline is not None:
                with suppress(Exception):
                    await pipeline.cancel()
            if runner_task is not None:
                with suppress(asyncio.CancelledError, Exception):
                    await asyncio.wait_for(runner_task, 5)
        finally:
            slots.release(owner)
            with suppress(Exception):
                await socket.close()
