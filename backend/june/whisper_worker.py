"""Supervise one private resident Whisper process over bounded anonymous pipes.

Protocol 1: <=4096 byte JSON command line; transcribe is immediately followed
by `bytes` bytes of canonical WAV (<=1 MiB). Replies are JSON lines <=64 KiB.
Every job/control message carries an opaque ID. No paths, sockets, or logs.
"""
import asyncio
import json
import math
import re
import uuid

from .errors import JuneError

MAX_AUDIO_BYTES = 1048576
MAX_REPLY_BYTES = 65536
ID = re.compile(r'[A-Za-z0-9_-]{1,64}')


def failed():
    return JuneError('engine-failed', 'The local speech worker stopped. Retry, or run npm run speech:setup.')


async def finish_cleanup(coroutine):
    """Cancellation must not orphan a child or release its slot before cleanup."""
    task = asyncio.create_task(coroutine)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


class WhisperWorker:
    def __init__(self, command, *, startup_timeout=120, cancel_timeout=1):
        self.command = list(map(str, command))
        self.startup_timeout = startup_timeout
        self.cancel_timeout = cancel_timeout
        self.busy = False
        self._process = None
        self._ready = False
        self._closed = False
        self._start_lock = asyncio.Lock()
        self._read_lock = asyncio.Lock()

    @property
    def pid(self):
        return self._process.pid if self._process is not None else None

    @property
    def ready(self):
        return self._ready and self._process is not None and self._process.returncode is None

    async def _stop(self, process=None):
        process = process or self._process
        if process is None:
            return
        if self._process is process:
            self._process = None
            self._ready = False
        if process.stdin is not None:
            process.stdin.close()  # EOF asks the control reader to abort compute.
        async def discard_output():
            # A broken peer may have filled and paused StreamReader's pipe.
            # Drain in bounded chunks while reaping; wait() alone can hang even
            # after SIGKILL if unread output keeps its transport paused.
            async with self._read_lock:
                while await process.stdout.read(8192):
                    pass
        drainer = asyncio.create_task(discard_output())
        try:
            try:
                await asyncio.wait_for(process.wait(), self.cancel_timeout)
            except TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
        finally:
            await drainer

    async def _read(self, process):
        try:
            async with self._read_lock:
                line = await process.stdout.readline()
            if not line.endswith(b'\n') or len(line) > MAX_REPLY_BYTES:
                raise ValueError()
            message = json.loads(line)
            if not isinstance(message, dict) or not isinstance(message.get('type'), str):
                raise ValueError()
            return message
        except (ValueError, UnicodeError, OSError, AttributeError) as error:
            raise failed() from error

    async def warm(self):
        async with self._start_lock:
            if self._closed:
                raise failed()
            if self.ready:
                return
            await self._stop()
            spawn = asyncio.create_task(asyncio.create_subprocess_exec(
                *self.command, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                limit=MAX_REPLY_BYTES))
            process = None
            try:
                process = await asyncio.shield(spawn)
                self._process = process
                if self._closed:
                    raise failed()
                message = await asyncio.wait_for(self._read(process), self.startup_timeout)
                if message != {'type': 'ready', 'protocol': 1, 'model': 'base.en'}:
                    raise failed()
                self._ready = True
            except BaseException as error:
                async def cleanup():
                    nonlocal process
                    if process is None:
                        try:
                            process = await spawn
                        except OSError:
                            return
                    await self._stop(process)
                await finish_cleanup(cleanup())
                if isinstance(error, (OSError, TimeoutError)):
                    raise failed() from error
                raise

    async def _send(self, process, command, data=b''):
        header = json.dumps(command, separators=(',', ':')).encode() + b'\n'
        if len(header) > 4096:
            raise failed()
        try:
            process.stdin.write(header)
            if data:
                process.stdin.write(data)
            await process.stdin.drain()
        except (OSError, RuntimeError, AttributeError) as error:
            raise failed() from error

    async def _result(self, process, identity):
        # A late result/cancel acknowledgement can never become the next turn.
        # Bound even stale-message floods, as well as each individual frame.
        for _ in range(16):
            result = await self._read(process)
            kind, job = result.get('type'), result.get('id')
            if kind not in ('result', 'cancelled', 'cancel-ignored', 'error') or not isinstance(job, str) or not ID.fullmatch(job):
                raise failed()
            if job != identity or kind == 'cancel-ignored':
                continue
            if kind == 'result':
                if not isinstance(result.get('text'), str) or len(result['text']) > 16000:
                    raise failed()
                for name in ('confidence', 'noSpeechProbability'):
                    value = result.get(name)
                    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
                        raise failed()
            return result
        raise failed()

    async def _cancel(self, process, identity, *, restart=False):
        if process is None:
            return
        try:
            async def exchange():
                await self._send(process, {'type': 'cancel', 'id': identity})
                await self._result(process, identity)
            await asyncio.wait_for(exchange(), self.cancel_timeout)
        except (JuneError, TimeoutError):
            restart = True
        if restart:
            await self._stop(process)

    async def transcribe(self, data, *, timeout=120):
        if not 44 <= len(data) <= MAX_AUDIO_BYTES:
            raise JuneError('invalid-audio', 'Invalid or oversized WAV audio.', 400)
        if self.busy:
            raise JuneError('busy', 'June is already transcribing another recording.', 409)
        self.busy = True
        process = None
        identity = uuid.uuid4().hex
        try:
            await self.warm()
            process = self._process
            async def exchange():
                await self._send(process, {'type': 'transcribe', 'id': identity, 'bytes': len(data)}, data)
                return await self._result(process, identity)
            result = await asyncio.wait_for(exchange(), timeout)
            if result['type'] != 'result':
                raise failed()
            return result
        except asyncio.CancelledError:
            await finish_cleanup(self._cancel(process, identity))
            raise
        except TimeoutError as error:
            await finish_cleanup(self._cancel(process, identity, restart=True))
            raise JuneError('timeout', 'Transcription took too long. Try a shorter recording.', 504) from error
        except JuneError:
            await finish_cleanup(self._stop(process))
            raise
        finally:
            self.busy = False

    async def close(self):
        self._closed = True
        await finish_cleanup(self._stop())
        # Also cover close racing the shielded subprocess creation.
        async with self._start_lock:
            await finish_cleanup(self._stop())
