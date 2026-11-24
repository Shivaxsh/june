"""Bounded workflows execute exactly reviewed payloads, at most once."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from june.errors import JuneError


class ToolPlans(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from june.tool_plans import ToolPlans, Capability
        self.tmp = tempfile.TemporaryDirectory()
        self.now = [1000.0]
        self.calls = []
        self.gate = None
        self.result = {"message": "Observed app running.", "verified": True}

        async def execute(payload):
            self.calls.append(payload)
            if self.gate:
                await self.gate.wait()
            return self.result

        self.cap = Capability("app.open", "Open app", "local", "local", True, execute)
        self.service = ToolPlans(Path(self.tmp.name), capabilities=[self.cap],
            intents={"open": lambda value: [("app.open", {"app": "fixed"}, "Open fixed app")]},
            clock=lambda: self.now[0])

    async def asyncTearDown(self):
        if self.gate:
            self.gate.set()
        await self.service.close()
        self.tmp.cleanup()

    async def propose(self, rid="request-0001"):
        return (await self.service.propose({"requestId": rid, "intent": "open"}))["plan"]

    def proof(self, plan, rid="approve-0001", **extra):
        return {"requestId": rid, "revision": plan["revision"], "fingerprint": plan["fingerprint"], **extra}

    async def finish(self):
        if self.service.jobs:
            await asyncio.gather(*tuple(self.service.jobs))

    async def test_proposal_does_not_execute_and_does_not_expose_internal_payload(self):
        plan = await self.propose()
        self.assertEqual(plan["status"], "proposed")
        self.assertEqual(plan["steps"][0]["preview"], "Open fixed app")
        self.assertNotIn("payload", plan["steps"][0])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.service.path.stat().st_mode & 0o777, 0o600)

    async def test_only_registered_intents_accept_strict_inputs(self):
        for value in ({"requestId": "request-0001", "intent": "shell"},
                      {"requestId": "request-0001", "intent": "open", "steps": []},
                      {"requestId": "request-0001", "intent": "open", "input": {"shell": "oops"}},
                      {"requestId": "x", "intent": "open"}):
            with self.assertRaises(JuneError):
                await self.service.propose(value)
        self.assertFalse(self.calls)

    async def test_bound_approval_runs_stored_payload_once(self):
        plan = await self.propose()
        for bad in ({"fingerprint": "wrong"}, {"revision": 2}, {"revision": True}):
            with self.assertRaises(JuneError):
                await self.service.approve(plan["id"], self.proof(plan, **bad))
        await self.service.approve(plan["id"], self.proof(plan))
        await self.service.approve(plan["id"], self.proof(plan))
        await self.finish()
        self.assertEqual(self.calls, [{"app": "fixed"}])
        self.assertEqual((await self.service.get(plan["id"]))["plan"]["status"], "completed")

    async def test_duplicate_proposal_and_conflicting_request(self):
        plan = await self.propose()
        self.assertEqual((await self.propose())["id"], plan["id"])
        with self.assertRaises(JuneError):
            await self.service.propose({"requestId": "request-0001", "intent": "open", "input": {}})

    async def test_mutation_request_ids_cannot_be_reused_for_different_operations(self):
        plan = await self.propose()
        await self.service.cancel(plan["id"], self.proof(plan))
        with self.assertRaises(JuneError):
            await self.service.approve(plan["id"], self.proof(plan))
        self.assertEqual(self.calls, [])

    async def test_expired_or_cancelled_plan_never_executes(self):
        plan = await self.propose()
        await self.service.cancel(plan["id"], self.proof(plan))
        await self.service.approve(plan["id"], self.proof(plan, "approve-0002"))
        plan = await self.propose("request-0002")
        self.now[0] += 301
        with self.assertRaises(JuneError):
            await self.service.approve(plan["id"], self.proof(plan, "approve-0003"))
        self.assertFalse(self.calls)

    async def test_cancel_running_plan_finishes_current_step_and_skips_later_steps(self):
        self.service.intents["open"] = lambda value: [("app.open", {"n": n}, str(n)) for n in (1, 2)]
        self.gate = asyncio.Event()
        plan = await self.propose()
        await self.service.approve(plan["id"], self.proof(plan))
        await asyncio.sleep(0)
        await self.service.cancel(plan["id"], self.proof(plan, "cancel-00001"))
        self.gate.set()
        await self.finish()
        result = (await self.service.get(plan["id"]))["plan"]
        self.assertEqual(self.calls, [{"n": 1}])
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["steps"][1]["status"], "cancelled")

    async def test_failed_or_unknown_step_stops_the_workflow(self):
        self.service.intents["open"] = lambda value: [("app.open", {"n": n}, str(n)) for n in (1, 2)]
        self.result = {"message": "Request outcome cannot be verified.", "verified": False}
        plan = await self.propose()
        await self.service.approve(plan["id"], self.proof(plan))
        await self.finish()
        result = (await self.service.get(plan["id"]))["plan"]
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["steps"][1]["status"], "skipped")
        self.assertEqual(len(self.calls), 1)
        await self.service.approve(plan["id"], self.proof(plan, "approve-0002"))
        self.assertEqual(len(self.calls), 1)

    async def test_remember_is_exact_and_revocable(self):
        plan = await self.propose()
        await self.service.approve(plan["id"], self.proof(plan, remember=True))
        await self.finish()
        second = await self.propose("request-0002")
        await self.finish()
        self.assertEqual(len(self.calls), 2)
        self.service.forget()
        third = await self.propose("request-0003")
        self.assertEqual(third["status"], "proposed")
        self.assertNotEqual(second["id"], third["id"])

    async def test_a_plan_mixing_a_tool_with_its_own_switch_and_a_plain_tool_can_be_remembered(self):
        from june.tool_plans import Capability
        switch = {"on": False}
        async def other(payload):
            return {"message": "done", "verified": True}
        self.service.capabilities["music.x"] = Capability("music.x", "Music", "local", "local", True, other,
            trusted=lambda payload: switch["on"], remember=lambda payload, value: switch.update(on=value))
        self.service.intents["mixed"] = lambda value: [("app.open", {"app": "fixed"}, "Open fixed app"), ("music.x", {}, "Play")]
        first = (await self.service.propose({"requestId": "request-mix-1", "intent": "mixed"}))["plan"]
        self.assertEqual(first["status"], "proposed")
        await self.service.approve(first["id"], self.proof(first, "approve-mix-1", remember=True))
        await self.finish()
        self.assertTrue(switch["on"])
        again = (await self.service.propose({"requestId": "request-mix-2", "intent": "mixed"}))["plan"]
        self.assertNotEqual(again["status"], "proposed", "both the plan and the tool's own switch were remembered")
        await self.finish()
        switch["on"] = False
        self.assertEqual((await self.service.propose({"requestId": "request-mix-3", "intent": "mixed"}))["plan"]["status"], "proposed", "turning the tool's switch off asks again")

    async def test_outward_capability_cannot_be_remembered(self):
        self.cap.risk = "outward"
        plan = await self.propose()
        self.assertFalse(plan["rememberable"])
        with self.assertRaises(JuneError):
            await self.service.approve(plan["id"], self.proof(plan, remember=True))
        self.assertFalse(self.calls)

    async def test_replayed_forget_cannot_revoke_a_newer_explicit_approval(self):
        request={'requestId':'forget-00001'}
        self.service.forget(request)
        plan=await self.propose()
        await self.service.approve(plan['id'],self.proof(plan,remember=True))
        await self.finish()
        self.service.forget(request)
        self.assertNotEqual((await self.propose('request-0002'))['status'],'proposed')

    async def test_reopen_marks_inflight_unknown_without_retry(self):
        from june.tool_plans import ToolPlans
        plan = await self.propose()
        with self.service.db() as db:
            row = db.execute('SELECT document FROM plans WHERE id=?', (plan['id'],)).fetchone()
            doc = json.loads(row[0]); doc['steps'][0]['status'] = 'running'
            db.execute("UPDATE plans SET status='running',document=? WHERE id=?", (json.dumps(doc), plan['id']))
        reopened = ToolPlans(Path(self.tmp.name), capabilities=[self.cap], intents=self.service.intents, clock=lambda: self.now[0])
        self.assertEqual((await reopened.get(plan["id"]))["plan"]["status"], "unknown")
        await reopened.approve(plan["id"], self.proof(plan))
        self.assertFalse(self.calls)
        await reopened.close()

    async def test_shutdown_before_dispatch_is_cancelled_not_unknown(self):
        from june.tool_plans import ToolPlans
        plan = await self.propose()
        await self.service.approve(plan['id'], self.proof(plan))
        await self.service.close()
        reopened = ToolPlans(Path(self.tmp.name), capabilities=[self.cap], intents=self.service.intents, clock=lambda: self.now[0])
        result = (await reopened.get(plan['id']))['plan']
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(self.calls, [])
        await reopened.close()

    async def test_unavailable_before_dispatch_is_failed_not_unknown(self):
        plan = await self.propose()
        await self.service.approve(plan['id'], self.proof(plan))
        self.cap.available = False
        await self.finish()
        self.assertEqual((await self.service.get(plan['id']))['plan']['status'], 'failed')
        self.assertEqual(self.calls, [])

    async def test_running_cancel_request_visible_to_other_tabs(self):
        self.gate = asyncio.Event()
        plan = await self.propose()
        await self.service.approve(plan['id'], self.proof(plan))
        await asyncio.sleep(0)
        await self.service.cancel(plan['id'], self.proof(plan, 'cancel-00001'))
        self.assertTrue((await self.service.get(plan['id']))['plan']['cancelRequested'])

    async def test_registry_policy_change_invalidates_review_before_dispatch(self):
        plan = await self.propose()
        self.cap.risk = 'outward'
        with self.assertRaises(JuneError):
            await self.service.approve(plan['id'], self.proof(plan))
        self.assertEqual(self.calls, [])

    async def test_forget_during_execution_cannot_restore_trust(self):
        self.gate = asyncio.Event()
        plan = await self.propose()
        await self.service.approve(plan['id'], self.proof(plan, remember=True))
        await asyncio.sleep(0)
        self.service.forget()
        self.gate.set()
        await self.finish()
        self.assertEqual((await self.propose('request-0002'))['status'], 'proposed')

    async def test_tampered_stored_payload_fails_closed(self):
        plan = await self.propose()
        with self.service.db() as db:
            raw = json.loads(db.execute("SELECT document FROM plans WHERE id=?", (plan["id"],)).fetchone()[0])
            raw["steps"][0]["payload"] = {"app": "other"}
            db.execute("UPDATE plans SET document=? WHERE id=?", (json.dumps(raw), plan["id"]))
        with self.assertRaises(JuneError):
            await self.service.approve(plan["id"], self.proof(plan))
        self.assertFalse(self.calls)

    async def test_adapter_exception_does_not_leak_private_error(self):
        async def failing(payload):
            raise RuntimeError("private credential or fetched mail")
        self.cap.execute = failing
        plan = await self.propose()
        await self.service.approve(plan["id"], self.proof(plan))
        await self.finish()
        result = await self.service.get(plan["id"])
        self.assertNotIn("private credential", json.dumps(result))
        self.assertEqual(result["plan"]["status"], "unknown")
