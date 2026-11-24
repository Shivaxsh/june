import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx


class IntegrationsHttp(unittest.IsolatedAsyncioTestCase):
    async def test_real_routes_and_origin_and_request_limits(self):
        from june.app import app
        from june.actions import Actions
        from june.config import Settings
        from june.integrations import create_tools
        from june.memory_service import Coordinator
        from test_actions import Native
        with tempfile.TemporaryDirectory() as folder:
            native = Native()
            actions = Actions(Path(folder), native)
            plans = create_tools(Path(folder), actions)
            settings = Settings.from_env()
            with patch.multiple(app.state, settings=settings, coordinator=Coordinator(), plans=plans, create=True):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=settings.backend) as client:
                    caps = await client.get('/api/capabilities')
                    self.assertEqual(caps.status_code, 200)
                    catalog = caps.json()
                    self.assertEqual(catalog['version'], 1)
                    self.assertTrue(next(c for c in catalog['capabilities'] if c['id'] == 'app.open-vscode')['available'])
                    connections = (await client.get('/api/connections')).json()['connections']
                    self.assertTrue(all(c['state'] != 'connected' for c in connections))
                    self.assertEqual((await client.get('/api/plans?unexpected=1')).status_code, 400)
                    self.assertEqual((await client.post('/api/plans', json={'requestId': 'request-0001', 'intent': 'open-vscode'}, headers={'Origin':'https://evil.example'})).status_code, 403)
                    self.assertEqual((await client.post('/api/plans', content='x' * 33000)).status_code, 413)
                    self.assertEqual((await client.post('/api/plans', content='{}')).status_code, 400)
                    proposed = await client.post('/api/plans', json={'requestId': 'request-0001', 'intent': 'open-vscode'})
                    self.assertEqual(proposed.status_code, 200)
                    plan = proposed.json()['plan']
                    self.assertEqual(native.calls, 0)
                    proof = {'requestId':'approve-0001','revision':plan['revision'],'fingerprint':plan['fingerprint'],'remember':True}
                    self.assertEqual((await client.post(f"/api/plans/{plan['id']}/approve", json={**proof,'revision':2})).json()['code'], 'plan-stale')
                    self.assertEqual((await client.post(f"/api/plans/{plan['id']}/approve", json=proof)).status_code, 200)
                    await __import__('asyncio').gather(*tuple(plans.jobs))
                    result = (await client.get(f"/api/plans/{plan['id']}")).json()['plan']
                    self.assertEqual(result['status'], 'completed')
                    self.assertTrue(actions.trusted())
                    second = (await client.post('/api/plans', json={'requestId': 'request-0002', 'intent': 'open-vscode'})).json()['plan']
                    self.assertNotEqual(second['status'], 'proposed')
                    await __import__('asyncio').gather(*tuple(plans.jobs))
                    self.assertEqual(native.calls, 2)
                    await client.post('/api/plans/forget', json={'requestId':'forget-00001'})
                    self.assertFalse(actions.trusted())
            await plans.close()
            await actions.close()
