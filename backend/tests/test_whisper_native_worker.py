"""Compile the real native control loop with a tiny Whisper API double.

No model inference/benchmark: the double polls the real abort callback, which
makes failures in the native reader/compute concurrency observable over pipes.
"""
import asyncio
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from test_whisper_worker import audio

ROOT = Path(__file__).resolve().parents[2]
ENGINE = Path(os.environ.get('JUNE_SPEECH_HOME', str(Path.home() / 'Library/Application Support/June/speech'))) / 'whisper.cpp'
STUB = r'''
#include "whisper.h"
#include <thread>
#include <chrono>
struct whisper_context {};
extern "C" {
void whisper_log_set(ggml_log_callback, void *) {}
whisper_context_params whisper_context_default_params() { return {}; }
whisper_context * whisper_init_from_file_with_params(const char *, whisper_context_params) { return new whisper_context; }
void whisper_free(whisper_context * c) { delete c; }
whisper_full_params whisper_full_default_params(whisper_sampling_strategy) { return {}; }
int whisper_full(whisper_context *, whisper_full_params p, const float * s, int) {
    if (p.n_threads!=2 || p.greedy.best_of!=5 || p.beam_search.beam_size!=5 || p.temperature_inc!=.2f || !p.no_context || p.print_realtime) return 2;
    int count = s[0] > .07f ? 500 : 3;
    for(int i=0;i<count;++i) {
        if(p.abort_callback(p.abort_callback_user_data)) return 1;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    return 0;
}
int whisper_full_n_segments(whisper_context *) { return 1; }
const char * whisper_full_get_segment_text(whisper_context *, int) { return "Hello June"; }
int whisper_full_n_tokens(whisper_context *, int) { return 2; }
whisper_token_data whisper_full_get_token_data(whisper_context *, int, int) { whisper_token_data d={};d.id=10;d.p=.8f;return d; }
whisper_token whisper_token_eot(whisper_context *) { return 100; }
float whisper_full_get_segment_no_speech_prob(whisper_context *, int) { return .05f; }
}
'''


class NativeTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if not (ENGINE / 'include/whisper.h').is_file() or not shutil.which('c++'):
            raise unittest.SkipTest('native tests need the installed Whisper headers and C++ compiler')
        cls.directory = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.directory.name) / 'worker'
        stub = Path(cls.directory.name) / 'stub.cpp'
        stub.write_text(STUB)
        cls.source = ROOT / 'native/whisper-worker.cpp'
        if cls.source.exists():
            result = subprocess.run(['c++', '-std=c++17', '-pthread', '-I' + str(ENGINE / 'include'), '-I' + str(ENGINE / 'ggml/include'), '-I' + str(ENGINE / 'examples'), str(cls.source), str(stub), '-o', str(cls.binary)], capture_output=True, text=True)
            if result.returncode: raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls): cls.directory.cleanup()

    async def asyncSetUp(self):
        self.assertTrue(self.source.exists(), 'native resident control loop must exist')
        self.process = await asyncio.create_subprocess_exec(str(self.binary), '--model', 'unused', stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        self.assertEqual(await self.read(), {'type': 'ready', 'protocol': 1, 'model': 'base.en'})

    async def asyncTearDown(self):
        if self.process.returncode is None:
            self.process.stdin.close()
            await asyncio.wait_for(self.process.wait(), 2)
        self.assertEqual(await self.process.stderr.read(), b'')

    async def read(self): return json.loads(await asyncio.wait_for(self.process.stdout.readline(), 2))

    async def send(self, identity, data=None, kind='transcribe'):
        command = {'type': kind, 'id': identity}
        if data is not None: command['bytes'] = len(data)
        self.process.stdin.write(json.dumps(command).encode() + b'\n' + (data or b''))
        await self.process.stdin.drain()

    async def test_result_and_metadata_and_repeated_job(self):
        for identity in ('one', 'two'):
            await self.send(identity, audio())
            result = await self.read()
            self.assertEqual((result['type'], result['id'], result['text']), ('result', identity, 'Hello June'))
            self.assertAlmostEqual(result['confidence'], .8, places=5)
            self.assertAlmostEqual(result['noSpeechProbability'], .05, places=5)

    async def test_busy_stale_cancel_then_abort_callback_and_reuse(self):
        slow = audio()[:44] + struct.pack('<h', 3000) * 8000
        await self.send('active', slow)
        await self.send('other', audio())
        self.assertEqual((await self.read())['code'], 'busy')
        await self.send('old-id', kind='cancel')
        self.assertEqual((await self.read())['type'], 'cancel-ignored')
        await self.send('active', kind='cancel')
        self.assertEqual(await self.read(), {'type': 'cancelled', 'id': 'active'})
        await self.send('next', audio())
        self.assertEqual((await self.read())['type'], 'result')

    async def test_eof_aborts_active_compute(self):
        await self.send('active', audio()[:44] + struct.pack('<h', 3000) * 8000)
        self.process.stdin.close()
        await asyncio.wait_for(self.process.wait(), 2)
        self.assertEqual(self.process.returncode, 0)

    async def test_bad_wav_does_not_poison_next_job(self):
        await self.send('bad', b'x' * 100)
        self.assertEqual((await self.read())['code'], 'invalid-audio')
        await self.send('good', audio())
        self.assertEqual((await self.read())['type'], 'result')

    async def test_oversized_command_exits_without_buffering_unbounded_input(self):
        self.process.stdin.write(b'x' * 4097 + b'\n')
        await self.process.stdin.drain()
        self.assertEqual((await self.read())['code'], 'protocol')
        await asyncio.wait_for(self.process.wait(), 2)
        self.assertNotEqual(self.process.returncode, 0)
