import importlib.util
from pathlib import Path
import unittest
from types import SimpleNamespace
import httpx

spec=importlib.util.spec_from_file_location('acceptance',Path(__file__).resolve().parents[2]/'scripts/check-reliability.py')
acceptance=importlib.util.module_from_spec(spec);spec.loader.exec_module(acceptance)

class AcceptanceJudges(unittest.TestCase):
    def test_data_copying_answer_is_not_a_correct_async_explanation(self):
        self.assertFalse(acceptance.spoken_async_correct('Async moves do not automatically transfer data across threads; they only move control flow between threads. The actual data must be explicitly copied using Array.copyTo().'))
    def test_clear_javascript_answer_and_known_false_claim(self):
        self.assertTrue(acceptance.spoken_async_correct('No, async/await does not move CPU work to another thread. A CPU loop still blocks the main thread; use a Web Worker.'))
        self.assertFalse(acceptance.spoken_async_correct('Yes, async methods move work to a thread pool thread.'))


class ModelPreflight(unittest.IsolatedAsyncioTestCase):
    async def test_thinking_only_candidate_is_rejected_before_voice_acceptance(self):
        def reply(request):
            return httpx.Response(200,json={'models':[{'name':'candidate'}]} if request.url.path=='/api/tags' else {'thinking':{'values':[True],'default':True}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            with self.assertRaisesRegex(RuntimeError,'thinking-only'):
                await acceptance.require_model(client,SimpleNamespace(ollama='http://127.0.0.1:11434',model='candidate'))

    async def test_missing_model_aborts_instead_of_producing_a_misleading_score(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'models':[]}))) as client:
            with self.assertRaisesRegex(RuntimeError,'not installed'):
                await acceptance.require_model(client,SimpleNamespace(ollama='http://127.0.0.1:11434',model='candidate'))

    async def test_installed_candidate_can_be_evaluated(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'models':[{'name':'candidate'}]}))) as client:
            await acceptance.require_model(client,SimpleNamespace(ollama='http://127.0.0.1:11434',model='candidate'))
