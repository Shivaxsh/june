"""One-shot reminders: wall-clock correctness, durable claims, no model inference."""
import asyncio,tempfile,unittest,sqlite3
from datetime import datetime,timezone
from pathlib import Path
from june.errors import JuneError

def stamp(value):return datetime.fromisoformat(value).timestamp()

class ReminderTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  from june.reminders import Reminders
  self.tmp=tempfile.TemporaryDirectory();self.now=[stamp('2026-11-14T12:00:00+00:00')]
  self.service=Reminders(Path(self.tmp.name),clock=lambda:self.now[0],time_zone='Asia/Kolkata')
 async def asyncTearDown(self):await self.service.close();self.tmp.cleanup()
 def value(self,**changes):return {'text':'Stretch','localDate':'2026-11-14','localTime':'18:00','timeZone':'Asia/Kolkata','requestId':'reminder-key-001',**changes}
 async def test_wall_time_idempotence_restart_and_claim_once(self):
  from june.reminders import Reminders
  first=(await self.service.create(self.value()))['reminder']
  self.assertEqual(first['dueAt'],stamp('2026-11-14T12:30:00+00:00')*1000)
  self.assertEqual(first['text'],'Stretch');self.assertEqual(first['timeZone'],'Asia/Kolkata')
  self.now[0]+=1900
  other=Reminders(Path(self.tmp.name),clock=lambda:self.now[0],time_zone='Asia/Kolkata')
  self.addAsyncCleanup(other.close)
  self.assertEqual((await other.create(self.value()))['reminder']['id'],first['id'],'A replay after due still returns original')
  self.assertEqual((await other.state())['reminders'][0]['status'],'completed')
  claims=await asyncio.gather(self.service.claim(first['id']),other.claim(first['id']))
  self.assertEqual(sum(c['announce'] for c in claims),1)
  self.assertEqual((await other.acknowledge(first['id']))['reminder']['status'],'acknowledged')
  self.assertFalse((await self.service.claim(first['id']))['announce'])
 async def test_cancelled_reminder_never_announces_and_scheduler_does_not_need_model(self):
  first=(await self.service.create(self.value()))['reminder']
  self.assertEqual((await self.service.cancel(first['id']))['reminder']['status'],'cancelled')
  second=(await self.service.create(self.value(requestId='reminder-key-002',localTime='18:01')))['reminder']
  self.service.start(interval=.01);self.now[0]+=2000;await asyncio.sleep(.05)
  with self.service.db() as db:self.assertEqual(db.execute('SELECT status FROM timers WHERE id=?',(second['id'],)).fetchone()[0],'completed')
  self.assertFalse((await self.service.claim(first['id']))['announce'])
  self.assertTrue((await self.service.claim(second['id']))['announce'])
 async def test_limits_past_invalid_zones_and_request_mismatch(self):
  for changes in ({'localDate':'9999-12-31','localTime':'23:59','timeZone':'America/New_York'},{'localTime':'17:00'},{'localDate':'2026-12-16'},{'localDate':'2026-02-30'},{'timeZone':'No/Zone'},{'text':''},{'text':'x'*201},{'text':'x\ny'},{'dueAt':0},{'localTime':'25:00'}):
   with self.subTest(changes=changes),self.assertRaises(JuneError):await self.service.create(self.value(**changes))
  await self.service.create(self.value())
  with self.assertRaises(JuneError):await self.service.create(self.value(text='Different'))
  for n in range(1,20):await self.service.create(self.value(requestId='reminder-extra-'+str(n).zfill(3)))
  with self.assertRaises(JuneError):await self.service.create(self.value(requestId='reminder-too-many'))
  self.assertEqual(self.service.path.stat().st_mode&0o777,0o600)
 async def test_chat_retries_keep_original_due_time_even_after_it_passes(self):
  original=await self.service.chat('Remind me in ten minutes to Rest','retry-chat-001')
  self.now[0]+=700
  replay=await self.service.chat('Remind me in ten minutes to Rest','retry-chat-001')
  self.assertIn('reminder',replay,'A repeated chat request must return its original reminder')
  self.assertEqual(replay['reminder']['id'],original['reminder']['id'])
  self.assertEqual(replay['reminder']['dueAt'],original['reminder']['dueAt'])
  changed=await self.service.chat('Remind me in five minutes to Rest','retry-chat-001')
  self.assertNotIn('reminder',changed)
 async def test_chat_cancellation_ignores_sentence_ending_punctuation(self):
  await self.service.chat('Remind me at 6 PM to Stretch.','punct-chat-001')
  result=await self.service.chat('Cancel my reminder to stretch','punct-chat-002')
  self.assertIn('reminder',result)
  self.assertEqual(result['reminder']['status'],'cancelled')
 async def test_time_after_reminder_text_keeps_tomorrow_and_relative_meaning(self):
  for question,key,want in [('Remind me to call Mom at 6 PM','inverted-key-001',stamp('2026-11-14T12:30:00+00:00')),('Remind me to call Mom tomorrow at 6 PM','inverted-key-002',stamp('2026-11-15T12:30:00+00:00')),('Remind me to call Mom in ten minutes','inverted-key-003',self.now[0]+600)]:
   result=await self.service.chat(question,key)
   self.assertIn('reminder',result,question)
   self.assertEqual(result['reminder']['text'],'call Mom')
   self.assertEqual(result['reminder']['dueAt'],want*1000)
 async def test_dst_gap_and_fold_are_rejected_instead_of_guessed(self):
  self.now[0]=stamp('2026-03-01T00:00:00+00:00')
  with self.assertRaises(JuneError):await self.service.create(self.value(localDate='2026-03-08',localTime='02:30',timeZone='America/New_York'))
  self.now[0]=stamp('2026-10-15T00:00:00+00:00')
  with self.assertRaises(JuneError):await self.service.create(self.value(localDate='2026-11-01',localTime='01:30',timeZone='America/New_York'))
 async def test_chat_next_occurrence_explicit_past_relative_and_ambiguity(self):
  at=await self.service.chat('Remind me at 6 PM to Stretch','chat-key-001')
  self.assertEqual(at['reminder']['text'],'Stretch');self.assertIn('14 Nov 2026',at['reply']);self.assertIn('Asia/Kolkata',at['reply'])
  ambiguous=await self.service.chat('Remind me at 6 to stretch','chat-key-002')
  self.assertNotIn('reminder',ambiguous);self.assertIn('AM',ambiguous['reply'])
  past=await self.service.chat('Remind me today at 5 PM to walk','chat-key-003');self.assertNotIn('reminder',past)
  tomorrow=await self.service.chat('Remind me tomorrow at 6 PM to Walk','chat-key-004')
  self.assertEqual(tomorrow['reminder']['dueAt'],stamp('2026-11-15T12:30:00+00:00')*1000)
  rel=await self.service.chat('Remind me in ten minutes to Rest','chat-key-005')
  self.assertEqual(rel['reminder']['dueAt'],(self.now[0]+600)*1000)
  self.assertIsNone(await self.service.chat('Translate "remind me at 6 PM to stretch"','chat-key-006'))
  stopped=await self.service.chat('Cancel my reminder to Stretch','chat-key-007');self.assertEqual(stopped['reminder']['status'],'cancelled')
  no_guess=await self.service.chat('Cancel my reminder','chat-key-008');self.assertNotIn('reminder',no_guess)
  state=await self.service.chat('Show my reminders','chat-key-009');self.assertIn('Walk',state['reply'])

class ReminderHttp(unittest.IsolatedAsyncioTestCase):
 async def test_http_saved_chat_links_and_reminder_requests_bypass_model(self):
  import httpx,json
  from unittest.mock import patch
  from june.app import app
  from june.reminders import Reminders
  from june.memory import Store
  from june.memory_service import Coordinator
  from june.config import Settings
  with tempfile.TemporaryDirectory() as home:
   now=[stamp('2026-11-14T12:00:00+00:00')];reminders=Reminders(home,clock=lambda:now[0]);store=Store(Path(home));cid=store.create_conversation()['id']
   with patch.multiple(app.state,reminders=reminders,store=store,actions=None,timers=None,settings=Settings.from_env(),coordinator=Coordinator(),knowledge=None,client=None,create=True):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=Settings.from_env().backend) as client:
     value={'text':'Stretch','localDate':'2026-11-14','localTime':'18:00','requestId':'http-reminder-key'}
     self.assertEqual((await client.post('/api/reminders',json=value,headers={'Origin':'https://other.example'})).status_code,403)
     first=await client.post('/api/reminders',json=value);self.assertEqual(first.status_code,200)
     rid=first.json()['reminder']['id']
     self.assertEqual((await client.post('/api/reminders',json=value)).json()['reminder']['id'],rid)
     self.assertEqual((await client.post('/api/reminders/'+rid+'/claim',json={'extra':True})).status_code,400)
     now[0]+=1900
     self.assertTrue((await client.post('/api/reminders/'+rid+'/claim',json={})).json()['announce'])
     self.assertFalse((await client.post('/api/reminders/'+rid+'/claim',json={})).json()['announce'])
     self.assertEqual((await client.post('/api/reminders/'+rid+'/acknowledge',json={})).json()['reminder']['status'],'acknowledged')
     with patch('june.library_chat.stream_chat',side_effect=AssertionError('Reminder must not call Qwen')):
      chat=await client.post('/api/chat',json={'knowledge':{'mode':'auto'},'conversationId':cid,'turnId':'reminder-chat','messages':[{'role':'user','content':'Remind me in ten minutes to Rest'}]})
     self.assertEqual(chat.status_code,200)
     done=json.loads(chat.text.splitlines()[-1]);self.assertEqual(done['reminder']['text'],'Rest')
     saved=(await client.get('/api/library/conversations/'+cid)).json();self.assertEqual(saved['turns'][0]['reminderId'],done['reminder']['id'])
     await client.delete('/api/library/conversations/'+cid)
     self.assertEqual(reminders.links(cid),{})
     self.assertEqual((await reminders.state())['reminders'][0]['status'],'active','Deleting a chat must not cancel an independent reminder')
   await reminders.close()
