"""Revision-bound reminder edits and snoozes; old alerts cannot consume a new occurrence."""
import asyncio,tempfile,unittest
from pathlib import Path
from datetime import datetime
from june.errors import JuneError

def stamp(s):return datetime.fromisoformat(s).timestamp()

class ReminderUpdates(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  from june.reminders import Reminders
  self.home=tempfile.TemporaryDirectory();self.now=[stamp('2026-11-14T12:00:00+00:00')]
  self.r=Reminders(self.home.name,clock=lambda:self.now[0]);self.addAsyncCleanup(self.r.close);self.addCleanup(self.home.cleanup)
  self.first=(await self.r.create({'text':'stretch','localDate':'2026-11-14','localTime':'18:00','requestId':'original-request'}))['reminder']
 def edit(self,**extra):return {'revision':1,'requestId':'edit-request-001','localDate':'2026-11-14','localTime':'19:00',**extra}
 async def test_reschedule_moves_same_record_and_old_revision_cannot_claim_cancel_or_dismiss(self):
  result=await self.r.reschedule(self.first['id'],self.edit(text='stand and stretch'))
  new=result['reminder'];self.assertEqual(new['id'],self.first['id']);self.assertEqual(new['revision'],2)
  self.assertEqual(new['text'],'stand and stretch');self.assertEqual(new['status'],'active')
  self.assertEqual(new['dueAt'],stamp('2026-11-14T13:30:00+00:00')*1000)
  self.now[0]+=1900;self.assertEqual((await self.r.state())['reminders'][0]['status'],'active')
  for operation in (self.r.claim,self.r.cancel,self.r.acknowledge):
   with self.assertRaises(JuneError):await operation(new['id'],revision=1)
   with self.assertRaises(JuneError):await operation(new['id'])
  self.now[0]+=4000
  self.assertTrue((await self.r.claim(new['id'],revision=2))['announce'])
  self.assertFalse((await self.r.claim(new['id'],revision=2))['announce'])
 async def test_snooze_claimed_due_reminder_rearms_once_and_replay_keeps_original_result(self):
  self.now[0]+=1900;self.assertTrue((await self.r.claim(self.first['id'],revision=1))['announce'])
  value={'revision':1,'requestId':'snooze-request-001','seconds':600}
  result=await self.r.snooze(self.first['id'],value);new=result['reminder']
  self.assertEqual(new['revision'],2);self.assertEqual(new['dueAt'],(self.now[0]+600)*1000)
  self.assertNotIn('completedAt',new);self.assertNotIn('announcedAt',new)
  self.now[0]+=650
  replay=await self.r.snooze(self.first['id'],value);self.assertEqual(replay['reminder'],new)
  from june.reminders import Reminders
  other=Reminders(self.home.name,clock=lambda:self.now[0]);self.addAsyncCleanup(other.close)
  claims=await asyncio.gather(self.r.claim(new['id'],revision=2),other.claim(new['id'],revision=2))
  self.assertEqual(sum(c['announce'] for c in claims),1)
  self.assertEqual((await self.r.state())['reminders'][0]['revision'],2)
 async def test_stale_concurrent_edits_conflict_and_bad_payloads_never_reschedule(self):
  results=await asyncio.gather(self.r.reschedule(self.first['id'],self.edit()),self.r.reschedule(self.first['id'],self.edit(requestId='edit-request-002',localTime='20:00')),return_exceptions=True)
  self.assertEqual(sum(isinstance(v,JuneError) for v in results),1)
  current=(await self.r.state())['reminders'][0];self.assertEqual(current['revision'],2)
  for bad in ({'revision':True,'requestId':'bad-request-001','seconds':60},{'revision':2,'requestId':'bad-request-001','seconds':0},{'revision':2,'requestId':'bad-request-001','seconds':86401},{'revision':2,'requestId':'bad-request-001','seconds':True},{'revision':2,'requestId':'bad-request-001','seconds':60,'command':'x'}):
   with self.assertRaises(JuneError):await self.r.snooze(current['id'],bad)
  await self.r.cancel(current['id'],revision=2)
  with self.assertRaises(JuneError):await self.r.reschedule(current['id'],self.edit(revision=2))
 async def test_old_claim_does_not_consume_new_announcement_and_changed_retry_is_rejected(self):
  self.now[0]+=1900;await self.r.claim(self.first['id'],revision=1)
  value={'revision':1,'requestId':'snooze-request-001','seconds':20}
  await self.r.snooze(self.first['id'],value)
  with self.assertRaises(JuneError):await self.r.snooze(self.first['id'],{**value,'seconds':30})
  self.now[0]+=21
  with self.assertRaises(JuneError):await self.r.claim(self.first['id'],revision=1)
  self.assertTrue((await self.r.claim(self.first['id'],revision=2))['announce'])
 async def test_chat_move_snooze_retries_and_ambiguous_again_do_not_guess(self):
  moved=await self.r.chat('Move my stretch reminder to 7 PM','chat-edit-001')
  self.assertIn('reminder',moved);self.assertEqual(moved['reminder']['revision'],2)
  self.now[0]+=100
  replay=await self.r.chat('Move my stretch reminder to 7 PM','chat-edit-001');self.assertEqual(replay['reminder']['dueAt'],moved['reminder']['dueAt'])
  snoozed=await self.r.chat('Snooze my stretch reminder for ten minutes','chat-snooze-001')
  self.assertEqual(snoozed['reminder']['revision'],3);self.assertEqual(snoozed['reminder']['dueAt'],(self.now[0]+600)*1000)
  self.now[0]+=700
  again=await self.r.chat('Remind me again in ten minutes','chat-again-001');self.assertEqual(again['reminder']['revision'],4)
  self.now[0]+=700
  await self.r.chat('Remind me in one second to walk','chat-other-001');self.now[0]+=2
  ambiguous=await self.r.chat('Remind me again in ten minutes','chat-again-002');self.assertNotIn('reminder',ambiguous)
  self.assertIsNone(await self.r.chat('Translate "snooze my reminder for ten minutes"','chat-quote-001'))

class ReminderUpdateHttp(unittest.IsolatedAsyncioTestCase):
 async def test_edit_snooze_revision_claims_and_body_guards(self):
  import httpx
  from unittest.mock import patch
  from june.app import app
  from june.reminders import Reminders
  from june.config import Settings
  from june.memory_service import Coordinator
  with tempfile.TemporaryDirectory() as home:
   now=[stamp('2026-11-14T12:00:00+00:00')];r=Reminders(home,clock=lambda:now[0]);settings=Settings.from_env()
   with patch.multiple(app.state,reminders=r,settings=settings,coordinator=Coordinator(),create=True):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=settings.backend) as client:
     first=(await client.post('/api/reminders',json={'text':'stretch','localDate':'2026-11-14','localTime':'18:00','requestId':'http-create-key'})).json()['reminder']
     path='/api/reminders/'+first['id'];edit={'revision':1,'requestId':'http-edit-key','localDate':'2026-11-14','localTime':'19:00'}
     moved=await client.post(path+'/reschedule',json=edit);self.assertEqual(moved.status_code,200)
     self.assertEqual(moved.json()['reminder']['revision'],2)
     self.assertEqual((await client.post(path+'/reschedule',json=edit)).json()['reminder']['revision'],2)
     self.assertEqual((await client.post(path+'/claim',json={'revision':1})).status_code,409)
     self.assertEqual((await client.post(path+'/cancel',json={})).status_code,409)
     self.assertEqual((await client.post(path+'/claim',json={'revision':2,'extra':True})).status_code,400)
     later=await client.post(path+'/snooze',json={'revision':2,'requestId':'http-snooze-key','seconds':10})
     self.assertEqual(later.json()['reminder']['revision'],3);now[0]+=11
     self.assertTrue((await client.post(path+'/claim',json={'revision':3})).json()['announce'])
     self.assertFalse((await client.post(path+'/claim',json={'revision':3})).json()['announce'])
     self.assertEqual((await client.post(path+'/acknowledge',json={'revision':3})).json()['reminder']['status'],'acknowledged')
   await r.close()

class ReminderEditChatLinks(unittest.IsolatedAsyncioTestCase):
 async def test_saved_edit_turn_reopens_the_current_reminder_and_chat_delete_only_unlinks(self):
  import httpx,json
  from unittest.mock import patch
  from june.app import app
  from june.reminders import Reminders
  from june.memory import Store
  from june.memory_service import Coordinator
  from june.config import Settings
  with tempfile.TemporaryDirectory() as home:
   now=[stamp('2026-11-14T12:00:00+00:00')];r=Reminders(home,clock=lambda:now[0]);store=Store(Path(home));cid=store.create_conversation()['id'];settings=Settings.from_env()
   await r.create({'text':'stretch','localDate':'2026-11-14','localTime':'18:00','requestId':'initial-edit-link'})
   with patch.multiple(app.state,reminders=r,store=store,actions=None,timers=None,knowledge=None,client=None,coordinator=Coordinator(),settings=settings,create=True):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=settings.backend) as client:
     response=await client.post('/api/chat',json={'knowledge':{'mode':'auto'},'conversationId':cid,'turnId':'edited-reminder','messages':[{'role':'user','content':'Move my stretch reminder to 7 PM'}]})
     self.assertEqual(response.status_code,200);done=json.loads(response.text.splitlines()[-1])
     saved=(await client.get('/api/library/conversations/'+cid)).json()
     self.assertEqual(saved['turns'][0].get('reminderId'),done['reminder']['id'])
     await client.delete('/api/library/conversations/'+cid)
     self.assertEqual(r.links(cid),{})
     self.assertEqual((await r.state())['reminders'][0]['status'],'active')
   await r.close()
