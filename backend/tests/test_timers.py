"""Local timers are durable, model-independent and claimed at most once."""
import asyncio,tempfile,unittest,sqlite3
from pathlib import Path
from june.errors import JuneError

class TimerTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  from june.timers import Timers
  self.tmp=tempfile.TemporaryDirectory();self.now=[1000.0];self.timers=Timers(Path(self.tmp.name),lambda:self.now[0])
 async def asyncTearDown(self):await self.timers.close();self.tmp.cleanup()
 async def create(self,request='request-001',duration=10,label='Tea'):
  return (await self.timers.create({'durationSeconds':duration,'label':label,'requestId':request}))['timer']
 async def test_create_replay_reopen_and_cancel(self):
  from june.timers import Timers
  timer=await self.create();self.assertEqual(timer['endsAt'],1010000)
  self.assertEqual((await self.create())['id'],timer['id'])
  with self.assertRaises(JuneError):await self.create(duration=11)
  reopened=Timers(Path(self.tmp.name),lambda:self.now[0]);self.assertEqual((await reopened.state())['timers'][0]['id'],timer['id'])
  self.assertEqual((await reopened.cancel(timer['id']))['timer']['status'],'cancelled')
  self.now[0]+=20;self.assertFalse((await self.timers.claim(timer['id']))['announce'])
  await reopened.close()
 async def test_scheduler_finishes_without_any_request_and_claim_is_once_across_tabs(self):
  from june.timers import Timers
  timer=await self.create();self.timers.start(interval=.01);self.now[0]+=11
  await asyncio.sleep(.05)
  with sqlite3.connect(self.timers.path) as db:self.assertEqual(db.execute('SELECT status FROM timers WHERE id=?',(timer['id'],)).fetchone()[0],'completed')
  other=Timers(Path(self.tmp.name),lambda:self.now[0])
  claims=await asyncio.gather(self.timers.claim(timer['id']),other.claim(timer['id']))
  self.assertEqual(sum(c['announce'] for c in claims),1)
  self.assertEqual((await self.timers.acknowledge(timer['id']))['timer']['status'],'acknowledged')
  self.assertFalse((await other.claim(timer['id']))['announce']);await other.close()
 async def test_overdue_timer_completes_on_restart_and_active_cannot_be_acknowledged(self):
  from june.timers import Timers
  timer=await self.create()
  with self.assertRaises(JuneError):await self.timers.acknowledge(timer['id'])
  self.now[0]+=30;other=Timers(Path(self.tmp.name),lambda:self.now[0])
  self.assertEqual((await other.state())['timers'][0]['status'],'completed');await other.close()
 async def test_limits_bad_values_and_private_storage(self):
  for duration in (0,-1,86401,True,1.2,'10'):
   with self.assertRaises(JuneError):await self.timers.create({'durationSeconds':duration,'requestId':'invalid-key'})
  with self.assertRaises(JuneError):await self.timers.create({'durationSeconds':10,'requestId':'valid-key','label':'x'*81})
  with self.assertRaises(JuneError):await self.timers.create({'durationSeconds':10,'requestId':'valid-key','endsAt':1})
  for n in range(20):await self.create('request-'+str(n).zfill(4))
  with self.assertRaises(JuneError):await self.create('request-maximum')
  self.assertEqual(self.timers.path.stat().st_mode&0o777,0o600)
  self.assertEqual(self.timers.path.parent.stat().st_mode&0o777,0o700)

class TimerIntents(unittest.TestCase):
 def test_literal_requests_parse_without_hijacking_quotes_or_compound_actions(self):
  from june.timers import timer_intent
  for text,want in [('Set a timer for 10 minutes',600),('Start a timer for one minute and thirty seconds',90),('Set a timer for 2 minutes called tea',120)]:
   result=timer_intent(text);self.assertEqual(result['durationSeconds'],want,text)
  for text in ('Translate "set a timer for 10 minutes"','Do not set a timer','Explain how to set a timer'):
   self.assertIsNone(timer_intent(text),text)
  self.assertEqual(timer_intent('Set a timer for -3 seconds')['operation'],'invalid')
  self.assertEqual(timer_intent('Set a timer for 1 minute and delete my files')['operation'],'invalid')
  self.assertEqual(timer_intent('Cancel my timer')['operation'],'cancel')
  self.assertEqual(timer_intent('How much time is left on my timer?')['operation'],'list')

class TimerChat(unittest.IsolatedAsyncioTestCase):
 async def test_chat_create_cancel_and_list_bypass_model_and_save_live_link(self):
  from june.timers import Timers
  from june.memory import Store
  from june.memory_service import Coordinator,persisted_chat
  from june.config import Settings
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as home:
   timers=Timers(Path(home));store=Store(Path(home));cid=store.create_conversation()['id']
   async def ask(question,tid):
    return [e async for e in persisted_chat(None,Settings.from_env(),store,Coordinator(),{'knowledge':{'mode':'auto'},'conversationId':cid,'turnId':tid},'local',[{'role':'user','content':question}],timers=timers)]
   with patch('june.library_chat.stream_chat',side_effect=AssertionError('Timers must not use a model')):
    started=await ask('Set a timer for ten minutes called tea','start-timer')
    timer=started[-1]['timer'];self.assertEqual(timer['durationSeconds'],600)
    self.assertIn('10 minutes',''.join(e['text'] for e in started if e['type']=='delta'))
    self.assertEqual(timers.links(cid),{'start-timer':timer['id']})
    listed=await ask('How much time is left on my timer?','timer-list')
    self.assertIn('left',''.join(e['text'] for e in listed if e['type']=='delta'))
    stopped=await ask('Cancel my timer','stop-timer');self.assertEqual(stopped[-1]['timer']['status'],'cancelled')
   await timers.close()

class TimerHttp(unittest.IsolatedAsyncioTestCase):
 async def test_http_origin_create_cancel_claim_and_saved_link(self):
  import httpx,json
  from unittest.mock import patch
  from june.app import app
  from june.timers import Timers
  from june.memory import Store
  from june.memory_service import Coordinator
  from june.config import Settings
  with tempfile.TemporaryDirectory() as home:
   now=[1000.0];timers=Timers(Path(home),lambda:now[0]);store=Store(Path(home));cid=store.create_conversation()['id'];settings=Settings.from_env()
   with patch.multiple(app.state,timers=timers,store=store,actions=None,settings=settings,coordinator=Coordinator(),knowledge=None,client=None,create=True):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=settings.backend) as client:
     payload={'durationSeconds':10,'requestId':'http-key-001'}
     self.assertEqual((await client.post('/api/timers',json=payload,headers={'Origin':'https://other.example'})).status_code,403)
     first=(await client.post('/api/timers',json=payload)).json()['timer']
     self.assertEqual((await client.post('/api/timers',json=payload)).json()['timer']['id'],first['id'])
     self.assertEqual((await client.post('/api/timers/'+first['id']+'/claim',json={})).json()['announce'],False)
     now[0]+=11
     self.assertTrue((await client.post('/api/timers/'+first['id']+'/claim',json={})).json()['announce'])
     self.assertFalse((await client.post('/api/timers/'+first['id']+'/claim',json={})).json()['announce'])
     self.assertEqual((await client.post('/api/timers/'+first['id']+'/acknowledge',json={})).json()['timer']['status'],'acknowledged')
     value={'knowledge':{'mode':'auto'},'conversationId':cid,'turnId':'http-timer','messages':[{'role':'user','content':'Set a timer for two minutes'}]}
     response=await client.post('/api/chat',json=value);self.assertEqual(response.status_code,200)
     done=json.loads(response.text.splitlines()[-1]);self.assertEqual(done['timer']['durationSeconds'],120)
     saved=(await client.get('/api/library/conversations/'+cid)).json();self.assertEqual(saved['turns'][0]['timerId'],done['timer']['id'])
     self.assertEqual((await client.post('/api/timers/'+done['timer']['id']+'/cancel',json={})).json()['timer']['status'],'cancelled')
   await timers.close()
