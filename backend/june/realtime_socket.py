"""Bounded browser transport and one microphone owner for this local backend."""
import asyncio
from contextlib import suppress
import importlib
import json
import time
import uuid

from fastapi import WebSocketDisconnect

from .realtime_state import VoiceTurn, PAUSES


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


async def voice_socket(socket, assets, slots, speech):
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
        await emit({'type': 'metrics', 'vad': round(probability, 3)})

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
        detectors = await startup(asyncio.to_thread(engine.Detectors, assets.model))
        turn = VoiceTurn(emit, speech.transcribe, config.get('pause', 'normal'))
        pipeline, runner = engine.make_pipeline(detectors, turn, consumed, fail, ready, metrics)
        runner_task = asyncio.create_task(runner.run(pipeline))
        await startup(ready.wait())
        startup_receiver.cancel()
        with suppress(asyncio.CancelledError):
            await startup_receiver
        startup_receiver = None
        await emit({'type': 'ready', 'turn': 0})
        await turn.state('waiting')

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
            for task in (watcher, receiver, failure_wait):
                if task is not None:
                    task.cancel()
                    with suppress(asyncio.CancelledError, WebSocketDisconnect):
                        await task
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        await fail('The voice connection received an invalid message. Enable hands-free again.')
    except Exception:
        await fail('Local hands-free could not start. Run npm run realtime:setup and restart June.')
    finally:
        alive = False
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
