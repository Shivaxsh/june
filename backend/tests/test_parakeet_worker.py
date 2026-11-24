"""Parakeet worker: June's Protocol 1 around a stand-in sherpa-onnx recognizer (no model, no audio device)."""
import asyncio, json, os, struct, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace

from june.errors import JuneError
from june.whisper_worker import WhisperWorker

WORKER = Path(__file__).resolve().parents[1] / 'june' / 'parakeet_worker.py'
FAKE = '''
import math
class _Result:
    def __init__(self, text, logs): self.text, self.ys_log_probs = text, logs
class _Stream:
    def accept_waveform(self, rate, samples): self.n = len(samples); self.loud = float(abs(samples).max()) if len(samples) else 0.
    @property
    def result(self): return _Result('Book a table for two.', [math.log(.9)] * 6) if self.loud > .01 else _Result('', [])
class OfflineRecognizer:
    @staticmethod
    def from_transducer(**kw):
        assert kw['model_type'] == 'nemo_transducer' and kw['num_threads'] == 4
        if 'missing' in kw['encoder']: raise RuntimeError('no model')
        return OfflineRecognizer()
    def create_stream(self): return _Stream()
    def decode_stream(self, stream): pass
'''


def wav(loud=True, seconds=1.):
    n = int(16000 * seconds)
    pcm = struct.pack('<%dh' % n, *([8000, -8000] * (n // 2))) if loud else bytes(n * 2)
    return struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', len(pcm) + 36, b'WAVE', b'fmt ', 16, 1, 1, 16000, 32000, 2, 16, b'data', len(pcm)) + pcm


class ParakeetProtocol(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        (Path(self.tmp.name) / 'sherpa_onnx').mkdir()
        (Path(self.tmp.name) / 'sherpa_onnx' / '__init__.py').write_text(FAKE)
        self.env = {**os.environ, 'PYTHONPATH': self.tmp.name}

    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def start(self, model='/fixture/model'):
        return await asyncio.create_subprocess_exec(sys.executable, str(WORKER), '--model', model, env=self.env,
                                                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)

    async def line(self, process):
        return json.loads(await asyncio.wait_for(process.stdout.readline(), 15))

    async def test_ready_result_confidence_silence_and_cancel(self):
        p = await self.start()
        self.assertEqual(await self.line(p), {'type': 'ready', 'protocol': 1, 'model': 'parakeet-tdt-0.6b-v2-int8'})
        audio = wav()
        p.stdin.write(json.dumps({'type': 'transcribe', 'id': 'one', 'bytes': len(audio)}).encode() + b'\n' + audio)
        result = await self.line(p)
        self.assertEqual((result['type'], result['id'], result['text']), ('result', 'one', 'Book a table for two.'))
        self.assertAlmostEqual(result['confidence'], .9, places=6)
        self.assertEqual(result['noSpeechProbability'], 0.)
        quiet = wav(loud=False)
        p.stdin.write(json.dumps({'type': 'transcribe', 'id': 'two', 'bytes': len(quiet)}).encode() + b'\n' + quiet)
        silent = await self.line(p)
        self.assertEqual((silent['text'], silent['confidence'], silent['noSpeechProbability']), ('', 0., 1.), 'nothing heard, nothing invented')
        p.stdin.write(b'{"type":"cancel","id":"two"}\n')
        self.assertEqual(await self.line(p), {'type': 'cancel-ignored', 'id': 'two'})
        p.stdin.write(b'not json\n'); await p.stdin.drain()
        self.assertEqual(await asyncio.wait_for(p.wait(), 15), 3, 'malformed input ends the worker; the supervisor restarts it')

    async def test_missing_model_reports_load_failure(self):
        p = await self.start('/missing/model')
        self.assertEqual((await self.line(p))['code'], 'model-load-failed')
        self.assertEqual(await asyncio.wait_for(p.wait(), 15), 2)

    async def test_june_supervisor_runs_it_unchanged(self):
        worker = WhisperWorker([sys.executable, str(WORKER), '--model', '/fixture/model'], model='parakeet-tdt-0.6b-v2-int8')
        old = os.environ.get('PYTHONPATH'); os.environ['PYTHONPATH'] = self.tmp.name
        try:
            for _ in range(2):
                result = await worker.transcribe(wav())
                self.assertEqual(result['text'], 'Book a table for two.')
            self.assertTrue(worker.ready)
        finally:
            await worker.close()
            if old is None: os.environ.pop('PYTHONPATH', None)
            else: os.environ['PYTHONPATH'] = old


class ParakeetService(unittest.IsolatedAsyncioTestCase):
    async def test_parakeet_service_uses_the_worker_script_and_never_touches_the_interpreter(self):
        from june.speech import SpeechService, PARAKEET_ID
        with tempfile.TemporaryDirectory() as directory:
            service = SpeechService(SimpleNamespace(speech_home=Path(directory)), engine='parakeet')
            self.assertEqual(service.worker_binary, Path(sys.executable))
            self.assertEqual(service.worker.command[1], str(WORKER))
            self.assertEqual(service.worker.model, PARAKEET_ID)
            self.assertEqual(service.model.name, 'encoder.int8.onnx')
            status = await service.status()
            self.assertEqual((status['state'], status['engine'], status['model']), ('model-missing', 'parakeet', 'Parakeet'))
            service.model.parent.mkdir(parents=True)
            with service.model.open('wb') as model: model.truncate(100000001)
            (Path(directory) / 'ready.json').write_text(json.dumps({'version': 'v1.9.5', 'model': PARAKEET_ID, 'sha256': '0' * 64}))
            self.assertEqual((await service.status())['state'], 'ready')
            (Path(directory) / 'ready.json').write_text(json.dumps({'version': 'v1.9.5', 'model': 'small.en-q5_1', 'sha256': '0' * 64}))
            self.assertEqual((await service.status())['state'], 'error', 'a Whisper marker never vouches for the Parakeet model')
            await service.close()
