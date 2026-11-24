"""Strict WAV validation and one supervised resident CPU-only Whisper worker."""
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
import time

from .errors import JuneError
from .speech_text import clean_transcript
from .whisper_worker import WhisperWorker

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


# The listening engine June uses. Parakeet (NVIDIA TDT 0.6B, int8) heard the user's real voice best on 2026-11-22 and
# doesn't invent words; Whisper stays installed as the fallback (set ENGINE = 'whisper'). scripts/speech.mjs must match.
ENGINE = 'parakeet'
PARAKEET_ID, PARAKEET_DIR = 'parakeet-tdt-0.6b-v2-int8', 'parakeet/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8'
WHISPER_ID, WHISPER_NAME = 'small.en-q5_1', 'small.en'
ENGINES = {'parakeet': (PARAKEET_ID, 'Parakeet', 'parakeet'), 'whisper': (WHISPER_ID, WHISPER_NAME, 'whisper.cpp')}
MODEL_ID, MODEL_NAME, ENGINE_NAME = ENGINES[ENGINE]


class SpeechService:
    def __init__(self, settings, engine=None):
        self.home = settings.speech_home
        self.binary = self.home / 'whisper.cpp/build/bin/whisper-cli'
        self._default_cli = self.binary
        self.engine = engine or ENGINE
        self.model_id, self.model_name, self.engine_name = ENGINES[self.engine]
        if self.engine == 'parakeet':
            # Same resident-worker protocol, a separate process (its ONNX runtime never shares June's).
            self.worker_binary = Path(sys.executable)
            self.model_dir = self.home / PARAKEET_DIR
            self.model = self.model_dir / 'encoder.int8.onnx'
            command = [self.worker_binary, str(Path(__file__).with_name('parakeet_worker.py')), '--model', self.model_dir]
        else:
            self.worker_binary = self.home / 'worker/build/bin/june-whisper-worker'
            self.model = self.home / f'ggml-{self.model_id}.bin'
            command = [self.worker_binary, '--model', self.model]
        self.busy = False
        self.verified = None
        self._verify_lock = asyncio.Lock()
        self.timeout = 120
        self.worker = WhisperWorker(command, model=self.model_id)

    async def status(self):
        result = {'engine': self.engine_name, 'model': self.model_name,
                  'workerReady': self.worker.ready, 'warm': self.worker.ready, 'workerProtocol': 1,
                  'decoder': 'conservative-beam', 'threads': 4, 'fastDecoderReleased': False}
        binary = self.binary if self.binary != self._default_cli else self.worker_binary
        if not os.access(binary, os.X_OK):
            return {**result, 'state': 'runtime-missing', 'message': 'Local speech needs setup. Run npm run speech:setup, then refresh speech.'}
        if not self.model.is_file():
            return {**result, 'state': 'model-missing', 'message': f'The {self.model_name} speech model is missing. Run npm run speech:setup, then refresh speech.'}
        try:
            self._model_identity()
            return {**result, 'state': 'ready', 'message': f'Local English transcription · {self.model_name} · ready on this Mac'}
        except (OSError, ValueError, TypeError, AttributeError):
            return {**result, 'state': 'error', 'message': 'Speech installation has not passed its transcription check. Run npm run speech:setup.'}

    def _model_identity(self):
        # Status only inspects small metadata. Heavy integrity verification is
        # cached at warm/transcribe time, never performed by a GET status poll.
        marker = self.home / 'ready.json'
        if marker.stat().st_size > 4096:
            raise ValueError('Invalid readiness marker')
        ready = json.loads(marker.read_text())
        info = self.model.stat()
        digest = ready.get('sha256', '')
        if (ready.get('version') != 'v1.9.5' or ready.get('model') != self.model_id
                or not re.fullmatch('[a-f0-9]{64}', digest) or info.st_size < 100000000):
            raise ValueError('Invalid speech installation')
        return (str(self.model), info.st_size, info.st_mtime_ns, digest)

    async def _verify_installation(self):
        async with self._verify_lock:
            try:
                identity = self._model_identity()
                if self.verified != identity:
                    if await asyncio.to_thread(self._hash) != identity[-1]:
                        raise ValueError('Invalid model checksum')
                    # A replacement during hashing must not become trusted.
                    if self._model_identity() != identity:
                        raise ValueError('Model changed during verification')
                    self.verified = identity
            except (OSError, ValueError, TypeError, AttributeError) as error:
                raise JuneError('error', 'Speech integrity check failed. Run npm run speech:setup.') from error

    def _hash(self):
        with self.model.open('rb') as file:
            return hashlib.file_digest(file, 'sha256').hexdigest()

    async def warm(self):
        """Load and retain the speech model; parent owns when to warm and close."""
        status = await self.status()
        if status['state'] != 'ready':
            raise JuneError(status['state'], status['message'])
        await self._verify_installation()
        await self.worker.warm()
        return {**status, 'workerReady': self.worker.ready, 'warm': self.worker.ready}

    async def close(self):
        await self.worker.close()

    async def transcribe(self, data):
        # A user-authorised diagnostic records one existing utterance, never ambient capture.
        diagnostic=getattr(self,'_audit_capture',None)
        if diagnostic is None:
            from .speech_diagnostic import OneShotSpeechDiagnostic
            diagnostic=self._audit_capture=OneShotSpeechDiagnostic()
        validate_wav(data)
        diagnostic.capture(data)
        # Preserve explicit legacy CLI binary overrides for downstream diagnostic
        # callers and CLI lifecycle tests. Normal execution never falls back to
        # per-WAV spawning when the resident worker fails.
        if self.binary != self._default_cli:
            return await self._transcribe_cli(data)
        validate_wav(data)
        if self.busy:
            raise JuneError('busy', 'June is already transcribing another recording. Wait, then try again.', 409)
        self.busy = True
        started = time.perf_counter()
        try:
            status = await self.status()
            if status['state'] != 'ready':
                raise JuneError(status['state'], status['message'])
            await self._verify_installation()
            result = await self.worker.transcribe(data, timeout=self.timeout)
            text = clean_transcript(result['text'])
            # Token probabilities are decoder confidence, not calibrated word
            # accuracy. Fail closed on weak or silent output instead of letting
            # automatic turns turn it into a model prompt.
            if (not text or result['confidence'] < .35 or result['noSpeechProbability'] > .6
                    or re.fullmatch(r'\s*[\[(].*[\])]\s*', text)):
                raise JuneError('no-speech', 'No clear words were recognised. Try a clear, short sentence.', 422)
            return {'text': text, 'engine': self.engine_name, 'model': self.model_name,
                    'durationMs': round((time.perf_counter() - started) * 1000),
                    'confidence': result['confidence'],
                    'noSpeechProbability': result['noSpeechProbability']}
        finally:
            self.busy = False

    async def _transcribe_cli(self, data):
        """Explicit legacy CLI override only; never used by the resident path."""
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
                str(self.binary), '-m', str(self.model), '-f', str(source), '-t', '4', '-ng', '-bo', '1', '-nf',
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
            text = clean_transcript(text)
            if not text or re.fullmatch(r'\s*[\[(].*[\])]\s*', text):
                raise JuneError('no-speech', 'No words were recognised. Try a clear, short sentence.', 422)
            return {'text': text, 'engine': 'whisper.cpp', 'model': self.model_name, 'durationMs': round((time.perf_counter() - started) * 1000)}
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
