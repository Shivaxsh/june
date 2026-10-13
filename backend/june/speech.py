"""Strict WAV validation and one cancellable CPU-only Whisper job at a time."""
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile
import time

from .errors import JuneError

MAX_AUDIO_BYTES = 1048576


def validate_wav(data):
    if len(data) > MAX_AUDIO_BYTES:
        raise JuneError('too-large', 'Audio is too large. Record at most 30 seconds.', 413)
    if len(data) < 44 or (data[:4], data[8:16], data[36:40]) != (b'RIFF', b'WAVEfmt ', b'data'):
        raise JuneError('invalid-audio', 'Invalid WAV audio. Try recording again.', 400)
    riff_size, = struct.unpack_from('<I', data, 4)
    size, = struct.unpack_from('<I', data, 40)
    if riff_size != len(data) - 8 or size != len(data) - 44 or size % 2:
        raise JuneError('invalid-audio', 'WAV size does not match its data.', 400)
    if struct.unpack_from('<IHHIIHH', data, 16) != (16, 1, 1, 16000, 32000, 2, 16):
        raise JuneError('invalid-audio', 'Use mono 16 kHz 16-bit PCM WAV format.', 400)
    duration = size / 32
    if not 500 <= duration <= 30000:
        raise JuneError('invalid-audio', 'Record between half a second and 30 seconds.', 400)
    rms = math.sqrt(sum((sample[0] / 32768) ** 2 for sample in struct.iter_unpack('<h', data[44:])) / (size / 2))
    if rms < .001:
        raise JuneError('invalid-audio', 'Recording is too quiet to recognise speech. Check the microphone and try again.', 400)
    return {'durationMs': duration, 'rms': rms}


class SpeechService:
    def __init__(self, settings):
        self.home = settings.speech_home
        self.binary = self.home / 'whisper.cpp/build/bin/whisper-cli'
        self.model = self.home / 'ggml-base.en.bin'
        self.busy = False
        self.verified = None
        self.timeout = 120

    async def status(self):
        result = {'engine': 'whisper.cpp', 'model': 'base.en'}
        if not os.access(self.binary, os.X_OK):
            return {**result, 'state': 'runtime-missing', 'message': 'Local speech needs setup. Run npm run speech:setup, then refresh speech.'}
        if not self.model.is_file():
            return {**result, 'state': 'model-missing', 'message': 'Whisper base.en is missing. Run npm run speech:setup, then refresh speech.'}
        try:
            ready = json.loads((self.home / 'ready.json').read_text())
            info = self.model.stat()
            digest = ready.get('sha256', '')
            if ready.get('version') != 'v1.9.5' or ready.get('model') != 'base.en' or not re.fullmatch('[a-f0-9]{64}', digest) or info.st_size < 100000000:
                raise ValueError()
            identity = (str(self.model), info.st_size, info.st_mtime_ns, digest)
            if self.verified != identity:
                actual = await asyncio.to_thread(self._hash)
                if actual != digest:
                    raise ValueError()
                self.verified = identity
            return {**result, 'state': 'ready', 'message': 'Local English transcription · Whisper base.en · ready on this Mac'}
        except (OSError, ValueError, TypeError, AttributeError):
            return {**result, 'state': 'error', 'message': 'Speech installation has not passed its transcription check. Run npm run speech:setup.'}

    def _hash(self):
        with self.model.open('rb') as file:
            return hashlib.file_digest(file, 'sha256').hexdigest()

    async def transcribe(self, data):
        validate_wav(data)
        if self.busy:
            raise JuneError('busy', 'June is already transcribing another recording. Wait, then try again.', 409)
        # There is no await between checking and claiming this single-worker slot.
        self.busy = True
        directory = None
        spawn_task = None
        process = None
        started = time.perf_counter()
        try:
            status = await self.status()
            if status['state'] != 'ready':
                raise JuneError(status['state'], status['message'])
            directory = Path(tempfile.mkdtemp(prefix='june-speech-'))
            source, output = directory / 'input.wav', directory / 'result'
            source.write_bytes(data)
            source.chmod(0o600)
            spawn_task = asyncio.create_task(asyncio.create_subprocess_exec(
                str(self.binary), '-m', str(self.model), '-f', str(source), '-t', '2', '-ng',
                '-l', 'en', '-oj', '-of', str(output), '-np', '-nt',
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL))
            # Shield creation so cancellation cannot orphan a process before assignment.
            process = await asyncio.shield(spawn_task)
            try:
                await asyncio.wait_for(process.wait(), self.timeout)
            except TimeoutError:
                raise JuneError('timeout', 'Transcription took too long. Try a shorter recording.', 504)
            if process.returncode != 0:
                raise JuneError('engine-failed', 'The local speech engine failed. Run npm run speech:check, then retry.')
            result_path = output.with_suffix('.json')
            if result_path.stat().st_size > 262144:
                raise ValueError('Oversized result')
            result = json.loads(result_path.read_text())
            parts = result.get('transcription')
            if not isinstance(parts, list):
                raise ValueError('Invalid transcript')
            text = ' '.join(' '.join(x.get('text', '') for x in parts if isinstance(x, dict) and isinstance(x.get('text'), str)).split())
            if not text or re.fullmatch(r'\s*[\[(].*[\])]\s*', text):
                raise JuneError('no-speech', 'No words were recognised. Try a clear, short sentence.', 422)
            return {'text': text, 'engine': 'whisper.cpp', 'model': 'base.en', 'durationMs': round((time.perf_counter() - started) * 1000)}
        except (OSError, ValueError, AttributeError) as error:
            raise JuneError('engine-failed', 'June could not transcribe this recording. Run npm run speech:check, then retry.') from error
        finally:
            async def cleanup():
                nonlocal process
                try:
                    if spawn_task is not None and process is None:
                        try:
                            process = await spawn_task
                        except OSError:
                            pass
                    if process is not None and process.returncode is None:
                        try:
                            process.terminate()
                        except ProcessLookupError:
                            pass
                        try:
                            await asyncio.wait_for(process.wait(), 1)
                        except TimeoutError:
                            try:
                                process.kill()
                            except ProcessLookupError:
                                pass
                            await process.wait()
                finally:
                    try:
                        if directory is not None:
                            shutil.rmtree(directory)
                    finally:
                        self.busy = False
            task = asyncio.create_task(cleanup())
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                raise
