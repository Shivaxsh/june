"""Local Heart synthesis; no network, credentials, quota or alternate voices."""
import asyncio
import base64
from contextlib import aclosing, suppress, nullcontext
import json
import os
from pathlib import Path
import uuid

from .errors import JuneError
from .native_audio import validate_speak, finish_cleanup
from .voice_identity import JUNE_VOICE, JUNE_VOICE_ID

class HeartVoice:
    def __init__(self, audio, home=None, coordinator=None):
        self.audio = audio
        self.coordinator = coordinator
        self.home = Path(home or os.environ.get('JUNE_VOICE_HOME', str(Path.home() / 'Library/Application Support/June/voice-lab')))
        self.python = self.home / '.venv/bin/python'
        self.script = Path(__file__).resolve().parents[2] / 'native/heart-worker.py'
        self.process = None
        self.start_lock = asyncio.Lock()
        self.lock = asyncio.Lock()
        self.closed = False

    def info(self):
        return {'provider': 'kokoro', 'voiceId': JUNE_VOICE_ID, 'voiceName': 'June',
                'ttsModel': 'kokoro-v1.0', 'cloudText': False, 'trainingRequired': False}

    async def _retire(self, process):
        if self.process is process:
            self.process = None
        if process.returncode is None:
            with suppress(ProcessLookupError): process.terminate()
            try: await asyncio.wait_for(process.wait(), 2)
            except TimeoutError:
                with suppress(ProcessLookupError): process.kill()
                await process.wait()

    async def ensure_started(self):
        async with self.start_lock:
            if self.closed: raise JuneError('voice-offline', 'June’s local voice is shutting down.', 503)
            if self.process is not None and self.process.returncode is None:
                return self.process
            if not all(p.is_file() for p in (self.python, self.script, self.home/'kokoro-v1.0.onnx', self.home/'voices-v1.0.bin')):
                raise JuneError('voice-setup', 'Heart voice files are missing. Run npm run voice:setup, restart June and refresh audio.', 503)
            spawn = asyncio.create_task(asyncio.create_subprocess_exec(str(self.python), str(self.script), str(self.home),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, limit=20000))
            try:
                process = await asyncio.shield(spawn)
            except BaseException:
                async def reap_spawn():
                    with suppress(OSError): await self._retire(await spawn)
                await finish_cleanup(reap_spawn())
                raise
            try:
                ready = json.loads(await asyncio.wait_for(process.stdout.readline(), 60))
                if ready != {'type':'ready','voice':'af_heart','sampleRate':24000}:
                    raise ValueError('Invalid worker')
                if self.closed: raise ValueError('Voice closed')
                self.process = process
                return process
            except BaseException:
                await finish_cleanup(self._retire(process))
                raise

    async def status(self, force=False):
        try:
            await self.ensure_started()
            return {**self.info(), 'state':'ready', 'message':'June · Heart · American English · local speech · no API credits.'}
        except JuneError as error:
            return {**self.info(), 'state':'setup-required', 'message':error.message}
        except (OSError, ValueError, TimeoutError):
            return {**self.info(), 'state':'error', 'message':'June’s local Heart voice could not start. Run npm run voice:setup and refresh audio.'}

    async def voices(self):
        return {**await self.status(), 'voices':[dict(JUNE_VOICE)]}

    async def pcm(self, value):
        value = validate_speak(value, [JUNE_VOICE])
        async with self.lock, self.coordinator.voice_slot() if self.coordinator else nullcontext():
            process = await self.ensure_started()
            identity = uuid.uuid4().hex
            complete = False
            try:
                speed = {.98:.96, .92:.90, 1.04:1.02}[value['rate']]
                process.stdin.write((json.dumps({'id':identity,'text':value['text'],'speed':speed})+'\n').encode())
                await process.stdin.drain()
                total = 0
                async with asyncio.timeout(120):
                    while True:
                        event = json.loads(await process.stdout.readline())
                        if not isinstance(event,dict): raise ValueError('Invalid voice frame')
                        if event.get('id') != identity: raise ValueError('Stale voice result')
                        if event.get('type') == 'done':
                            if not total: raise ValueError('Empty audio')
                            complete = True
                            return
                        if 'audio' not in event: raise ValueError('Synthesis failed')
                        if not isinstance(event['audio'],str): raise ValueError('Invalid PCM encoding')
                        data = base64.b64decode(event['audio'], validate=True)
                        total += len(data)
                        if not data or len(data)>8192 or len(data)%2 or total>8640000:
                            raise ValueError('Invalid PCM')
                        yield data
            except (OSError, ValueError, TimeoutError):
                raise JuneError('voice-local', 'Local Heart synthesis stopped. Refresh audio and retry a shorter reply.', 503) from None
            finally:
                if not complete: await finish_cleanup(self._retire(process))

    async def speak(self, value):
        value = validate_speak(value, [JUNE_VOICE])
        async with aclosing(self.audio.speak_pcm(value, self.pcm(value))) as source:
            async for event in source: yield event

    async def close(self):
        self.closed = True
        async with self.start_lock:
            if self.process is not None: await self._retire(self.process)
