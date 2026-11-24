import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
import httpx
from june.errors import JuneError


class DailyHttp(unittest.IsolatedAsyncioTestCase):
    async def test_real_routes_setup_goals_briefing_and_safe_callback_failure(self):
        from june.app import app
        from june.config import Settings
        from june.daily_assistant import DailyAssistant
        from june.memory_service import Coordinator
        with tempfile.TemporaryDirectory() as folder:
            daily=DailyAssistant(Path(folder))
            daily.google=type('Google',(),{'callback':AsyncMock(side_effect=JuneError('google-state','private-provider-code',400))})()
            settings=Settings.from_env()
            with patch.multiple(app.state,settings=settings,coordinator=Coordinator(),daily=daily,create=True):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=settings.backend) as client:
                    response=await client.get('/api/assistant/settings')
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(response.json()['settings']['revision'],1)
                    denied=await client.post('/api/assistant/goals',json={'requestId':'goal-create1','text':'Test'},headers={'Origin':'https://other.example'})
                    self.assertEqual(denied.status_code,403)
                    created=(await client.post('/api/assistant/goals',json={'requestId':'goal-create1','text':'Finish June'})).json()['goal']
                    self.assertEqual(created['text'],'Finish June')
                    brief=(await client.post('/api/assistant/briefing',json={'requestId':'brief-create1'})).json()['briefing']
                    self.assertIn('Finish June',brief['spoken'])
                    failure=await client.get('/api/connections/google/callback?state=expired&code=private-code')
                    self.assertEqual(failure.status_code,400)
                    self.assertIn('text/html',failure.headers['content-type'])
                    self.assertNotIn('private',failure.text)
                    self.assertEqual(failure.headers['referrer-policy'],'no-referrer')
