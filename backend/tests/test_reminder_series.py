"""Repeating reminders: due-only occurrences, missed handling, DST, pause/resume, receipts, chat. No model inference."""
import tempfile,unittest
from datetime import datetime
from pathlib import Path
from june.errors import JuneError

def stamp(value):return datetime.fromisoformat(value).timestamp()
NOON_UTC='2026-11-14T12:00:00+00:00'   # 17:30 in Asia/Kolkata

class SeriesTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  from june.reminders import Reminders
  self.tmp=tempfile.TemporaryDirectory();self.now=[stamp(NOON_UTC)]
  self.service=self.make()
 def make(self,zone='Asia/Kolkata'):
  from june.reminders import Reminders
  return Reminders(Path(self.tmp.name),clock=lambda:self.now[0],time_zone=zone)
 async def asyncTearDown(self):await self.service.close();self.tmp.cleanup()
 def daily(self,**changes):return {'text':'Drink water','rule':'daily','localTime':'23:00','startDate':'2026-11-14','timeZone':'Asia/Kolkata','requestId':'series-key-0001',**changes}
 def change(self,s,**extra):return {'revision':s['revision'],'requestId':extra.pop('requestId','series-change-01'),**extra}

 async def test_create_validates_and_schedules_first_future_occurrence(self):
  s=(await self.service.create_series(self.daily()))['series']
  self.assertEqual((s['rule'],s['weekdays'],s['status'],s['revision']),('daily',[1,2,3,4,5,6,7],'active',1))
  self.assertEqual(s['nextOccurrenceDate'],'2026-11-14');self.assertEqual(s['nextScheduledAt'],stamp('2026-11-14T23:00:00+05:30')*1000)
  self.assertIsNone(s['lastMissed'])
  self.assertEqual((await self.service.create_series(self.daily()))['series']['id'],s['id'],'same request id replays')
  with self.assertRaises(JuneError) as caught:await self.service.create_series(self.daily(text='Other'))
  self.assertEqual(caught.exception.status,409)
  early=(await self.service.create_series(self.daily(requestId='series-key-0002',localTime='09:00')))['series']
  self.assertEqual(early['nextOccurrenceDate'],'2026-11-15','09:00 today already passed: no catch-up')
  weekly=(await self.service.create_series(self.daily(requestId='series-key-0003',rule='weekly',weekdays=[4,1],localTime='09:00')))['series']
  self.assertEqual(weekly['weekdays'],[1,4]);self.assertEqual(weekly['nextOccurrenceDate'],'2026-11-16','next Monday')
  for bad in ({'rule':'monthly'},{'rule':'weekly'},{'rule':'weekly','weekdays':[]},{'rule':'weekly','weekdays':[0]},{'weekdays':[1]},{'localTime':'24:00'},{'localTime':'9:00'},
              {'startDate':'2026-11-13'},{'startDate':'2026-12-20'},{'text':''},{'text':'x'*201},{'timeZone':'No/Zone'},{'extra':1}):
   with self.subTest(bad=bad),self.assertRaises(JuneError):await self.service.create_series(self.daily(requestId='series-key-0099',**bad))
  self.assertEqual(len((await self.service.state())['series']),3)

 async def test_shared_capacity_counts_series_once_and_paused_series(self):
  for i in range(19):await self.service.create({'text':f'One {i}','localDate':'2026-11-15','localTime':'10:00','requestId':f'reminder-key-{i:04}'})
  s=(await self.service.create_series(self.daily()))['series']
  with self.assertRaises(JuneError) as caught:await self.service.create({'text':'One more','localDate':'2026-11-15','localTime':'10:00','requestId':'reminder-key-9999'})
  self.assertEqual(caught.exception.status,409)
  paused=(await self.service.pause_series(s['id'],self.change(s)))['series']
  with self.assertRaises(JuneError):await self.service.create_series(self.daily(requestId='series-key-0002'))
  self.assertEqual((await self.service.resume_series(s['id'],self.change(paused,requestId='series-change-02')))['series']['status'],'active','resume never fails on capacity')

 async def test_due_within_grace_emits_once_claims_once_and_advances_without_revision_bump(self):
  s=(await self.service.create_series(self.daily()))['series']
  self.now[0]=stamp('2026-11-14T23:00:30+05:30')
  state=await self.service.state();occ=[r for r in state['reminders'] if r.get('seriesId')==s['id']]
  self.assertEqual(len(occ),1);r=occ[0]
  self.assertEqual((r['status'],r['occurrenceDate'],r['text']),('completed','2026-11-14','Drink water'))
  after=state['series'][0];self.assertEqual(after['revision'],1);self.assertEqual(after['nextOccurrenceDate'],'2026-11-15')
  self.assertTrue((await self.service.claim(r['id'],revision=r['revision']))['announce'])
  self.assertFalse((await self.service.claim(r['id'],revision=r['revision']))['announce'])
  # Next day's deadline archives the undismissed one as missed and emits the new one.
  self.now[0]=stamp('2026-11-15T23:00:10+05:30')
  rows={x['occurrenceDate']:x for x in (await self.service.state())['reminders'] if x.get('seriesId')}
  self.assertEqual((rows['2026-11-14']['status'],rows['2026-11-14']['outcome']),('acknowledged','missed'))
  self.assertEqual(rows['2026-11-15']['status'],'completed')

 async def test_late_next_deadline_archives_previous_due_occurrence(self):
  s=(await self.service.create_series(self.daily()))['series']
  self.now[0]=stamp('2026-11-14T23:00:05+05:30')
  old=[r for r in (await self.service.state())['reminders'] if r.get('seriesId')==s['id']][0]
  self.now[0]=stamp('2026-11-15T23:03:00+05:30')
  state=await self.service.state()
  rows=[r for r in state['reminders'] if r.get('seriesId')==s['id']]
  self.assertEqual(len(rows),1,'late deadlines must not emit an alert')
  self.assertEqual((rows[0]['status'],rows[0].get('outcome')),('acknowledged','missed'))
  self.assertEqual(state['series'][0]['nextOccurrenceDate'],'2026-11-16')
  self.assertFalse((await self.service.claim(old['id'],revision=rows[0]['revision']))['announce'])

 async def test_late_settle_and_downtime_are_silent_with_one_missed_summary(self):
  s=(await self.service.create_series(self.daily()))['series']
  self.now[0]=stamp('2026-11-17T08:00:00+05:30')   # three deadlines passed while nothing settled
  state=await self.service.state()
  self.assertEqual([r for r in state['reminders'] if r.get('seriesId')],[],'nothing emitted late')
  after=state['series'][0]
  self.assertEqual(after['lastMissed']['count'],3);self.assertEqual(after['lastMissed']['occurrenceDate'],'2026-11-16')
  self.assertEqual(after['nextOccurrenceDate'],'2026-11-17')

 async def test_startup_archives_overdue_rows_even_with_future_schedule_and_keeps_future_snooze(self):
  s=(await self.service.create_series(self.daily()))['series']
  self.now[0]=stamp('2026-11-14T23:00:20+05:30')
  r=[x for x in (await self.service.state())['reminders'] if x.get('seriesId')][0]
  await self.service.close()
  self.now[0]=stamp('2026-11-15T09:00:00+05:30')   # next is tonight (future), but last night's due row is unresolved
  self.service=self.make()
  state=await self.service.state();row=[x for x in state['reminders'] if x['id']==r['id']][0]
  self.assertEqual((row['status'],row['outcome']),('acknowledged','missed'))
  self.assertEqual(state['series'][0]['lastMissed']['count'],1)
  self.assertFalse((await self.service.claim(r['id'],revision=row['revision']))['announce'])
  # A future snoozed occurrence survives a restart.
  self.now[0]=stamp('2026-11-15T23:00:05+05:30')
  r2=[x for x in (await self.service.state())['reminders'] if x.get('occurrenceDate')=='2026-11-15'][0]
  snoozed=(await self.service.snooze(r2['id'],{'revision':r2['revision'],'requestId':'snooze-key-0001','seconds':600}))['reminder']
  await self.service.close();self.service=self.make()
  kept=[x for x in (await self.service.state())['reminders'] if x['id']==snoozed['id']][0]
  self.assertEqual((kept['status'],kept['revision']),('active',snoozed['revision']))

 async def test_snooze_overlap_generic_routes_and_skip(self):
  s=(await self.service.create_series(self.daily()))['series']
  self.now[0]=stamp('2026-11-14T23:00:05+05:30')
  r=[x for x in (await self.service.state())['reminders'] if x.get('seriesId')][0]
  with self.assertRaises(JuneError) as caught:await self.service.snooze(r['id'],{'revision':r['revision'],'requestId':'snooze-key-0001','seconds':86400})
  self.assertEqual(caught.exception.code,'reminder-snooze-overlap')
  for call in (self.service.cancel(r['id'],revision=r['revision']),self.service.reschedule(r['id'],{'revision':r['revision'],'requestId':'move-key-00001','localDate':'2026-11-15','localTime':'10:00'})):
   with self.assertRaises(JuneError) as caught:await call
   self.assertEqual(caught.exception.code,'series-occurrence')
  skipped=(await self.service.skip(r['id'],{'revision':r['revision'],'requestId':'skip-key-00001'}))['reminder']
  self.assertEqual((skipped['status'],skipped['outcome']),('acknowledged','skipped'))
  self.assertEqual((await self.service.skip(r['id'],{'revision':r['revision'],'requestId':'skip-key-00001'}))['reminder']['id'],r['id'],'receipt replay')

 async def test_skip_next_binds_revision_and_date(self):
  s=(await self.service.create_series(self.daily()))['series']
  with self.assertRaises(JuneError) as caught:await self.service.skip_next(s['id'],self.change(s,occurrenceDate='2026-11-15'))
  self.assertEqual(caught.exception.status,409,'a stale displayed date never skips another slot')
  after=(await self.service.skip_next(s['id'],self.change(s,occurrenceDate='2026-11-14')))
  self.assertEqual(after['series']['nextOccurrenceDate'],'2026-11-15');self.assertEqual(after['series']['revision'],2)
  self.assertEqual((after['reminder']['outcome'],after['reminder']['status']),('skipped','acknowledged'))
  self.now[0]=stamp('2026-11-14T23:00:05+05:30')
  self.assertEqual([x for x in (await self.service.state())['reminders'] if x.get('seriesId') and x['status']=='completed'],[],'the skipped date is never emitted')

 async def test_pause_silences_due_cancels_future_snooze_and_resume_has_no_catch_up(self):
  s=(await self.service.create_series(self.daily()))['series']
  self.now[0]=stamp('2026-11-14T23:00:05+05:30')
  r=[x for x in (await self.service.state())['reminders'] if x.get('seriesId')][0]
  paused=await self.service.pause_series(s['id'],self.change(s))
  self.assertEqual((paused['series']['status'],paused['series']['nextScheduledAt']),('paused',None))
  due=[x for x in (await self.service.state())['reminders'] if x['id']==r['id']][0]
  self.assertEqual(due['status'],'completed','the due card stays visible');self.assertGreater(due['revision'],r['revision'])
  self.assertFalse((await self.service.claim(r['id'],revision=due['revision']))['announce'],'paused: never spoken')
  for call in (self.service.snooze(r['id'],{'revision':due['revision'],'requestId':'snooze-key-0002','seconds':300}),self.service.skip(r['id'],{'revision':due['revision'],'requestId':'skip-key-00002'})):
   with self.assertRaises(JuneError) as caught:await call
   self.assertEqual(caught.exception.code,'series-paused')
  self.now[0]=stamp('2026-11-17T12:00:00+05:30')
  self.assertEqual(len([x for x in (await self.service.state())['reminders'] if x.get('seriesId')]),1,'nothing emitted while paused')
  resumed=await self.service.resume_series(s['id'],self.change(paused['series'],requestId='series-change-02'))
  self.assertEqual(resumed['series']['nextOccurrenceDate'],'2026-11-17','strictly future, no catch-up')
  archived=[x for x in (await self.service.state())['reminders'] if x['id']==r['id']][0]
  self.assertEqual((archived['status'],archived['outcome']),('acknowledged','missed'))
  self.assertEqual((await self.service.acknowledge(r['id'],revision=archived['revision']))['reminder']['status'],'acknowledged')

 async def test_pause_cancels_future_snoozed_occurrence_and_dismiss_works_while_paused(self):
  s=(await self.service.create_series(self.daily()))['series']
  self.now[0]=stamp('2026-11-14T23:00:05+05:30')
  r=[x for x in (await self.service.state())['reminders'] if x.get('seriesId')][0]
  snoozed=(await self.service.snooze(r['id'],{'revision':r['revision'],'requestId':'snooze-key-0003','seconds':600}))['reminder']
  await self.service.pause_series(s['id'],self.change(s))
  row=[x for x in (await self.service.state())['reminders'] if x['id']==r['id']][0]
  self.assertEqual((row['status'],row['outcome']),('cancelled','paused'))
  self.now[0]+=900
  self.assertNotIn('completed',[x['status'] for x in (await self.service.state())['reminders'] if x.get('seriesId')])

 async def test_update_keeps_due_snapshot_and_never_reemits_a_handled_date(self):
  s=(await self.service.create_series(self.daily()))['series']
  self.now[0]=stamp('2026-11-14T23:00:05+05:30')
  r=[x for x in (await self.service.state())['reminders'] if x.get('seriesId')][0]
  updated=(await self.service.update_series(s['id'],self.change(s,localTime='23:30',text='Water')))['series']
  self.assertEqual((updated['revision'],updated['localTime'],updated['text']),(2,'23:30','Water'))
  self.assertEqual(updated['nextOccurrenceDate'],'2026-11-15','today was already handled')
  due=[x for x in (await self.service.state())['reminders'] if x['id']==r['id']][0]
  self.assertEqual((due['text'],due['dueAt']),(r['text'],r['dueAt']),'the due occurrence keeps its snapshot')
  with self.assertRaises(JuneError) as caught:await self.service.update_series(s['id'],self.change(s,requestId='series-change-03',localTime='22:00'))
  self.assertEqual(caught.exception.status,409,'stale revision')
  replay=await self.service.update_series(s['id'],self.change(s,localTime='23:30',text='Water'))
  self.assertEqual(replay['series']['revision'],2,'same request id replays the stored result')

 async def test_cancel_is_terminal(self):
  s=(await self.service.create_series(self.daily()))['series']
  stopped=(await self.service.cancel_series(s['id'],self.change(s)))['series']
  self.assertEqual((stopped['status'],stopped['nextScheduledAt']),('cancelled',None))
  for call in (self.service.resume_series(s['id'],self.change(stopped,requestId='series-change-02')),self.service.pause_series(s['id'],self.change(stopped,requestId='series-change-03'))):
   with self.assertRaises(JuneError) as caught:await call
   self.assertEqual(caught.exception.status,409)

 async def test_dst_gap_uses_first_valid_minute_and_fold_uses_first_instance(self):
  await self.service.close()
  self.now[0]=stamp('2027-03-13T12:00:00-05:00');self.service=self.make('America/New_York')
  s=(await self.service.create_series(self.daily(localTime='02:30',startDate='2027-03-14',timeZone='America/New_York')))['series']
  self.assertEqual(s['nextScheduledAt'],stamp('2027-03-14T03:00:00-04:00')*1000,'02:30 does not exist: 03:00 that day')
  self.now[0]=stamp('2027-03-14T03:00:05-04:00')
  occ=[x for x in (await self.service.state())['reminders'] if x.get('seriesId')][0]
  self.assertTrue(occ['dstAdjusted']);self.assertEqual(occ['occurrenceDate'],'2027-03-14')
  await self.service.close()
  self.now[0]=stamp('2027-11-06T12:00:00-04:00');self.service=self.make('America/New_York')
  f=(await self.service.create_series(self.daily(requestId='series-key-0002',localTime='01:30',startDate='2027-11-07',timeZone='America/New_York')))['series']
  self.assertEqual(f['nextScheduledAt'],stamp('2027-11-07T01:30:00-04:00')*1000,'repeated 01:30: the first (EDT) instance')

 async def test_chat_creates_controls_and_asks_when_unclear(self):
  made=await self.service.chat('Remind me every day at 11 PM to drink water','chat-turn-0001',conversation='conv-00000001',turn='turn-00000001')
  self.assertEqual((made['series']['rule'],made['series']['localTime'],made['series']['text']),('daily','23:00','drink water'))
  self.assertIn('Repeating reminder set',made['reply'])
  self.assertEqual((await self.service.chat('Remind me every day at 11 PM to drink water','chat-turn-0001'))['series']['id'],made['series']['id'],'retry replays')
  weekly=await self.service.chat('Remind me every Monday and Thursday at 9 AM to stretch','chat-turn-0002')
  self.assertEqual(weekly['series']['weekdays'],[1,4])
  inverted=await self.service.chat('Remind me to read every weekday at 7:30 PM','chat-turn-0003')
  self.assertEqual((inverted['series']['weekdays'],inverted['series']['localTime']),([1,2,3,4,5],'19:30'))
  self.assertIn('What should June remind you about',(await self.service.chat('Remind me every day at 11 PM','chat-turn-0004'))['reply'])
  self.assertIn('AM or PM',(await self.service.chat('Remind me every day at 11 to drink water','chat-turn-0005'))['reply'])
  paused=await self.service.chat('Pause my drink water reminder','chat-turn-0006')
  self.assertEqual(paused['series']['status'],'paused')
  self.assertEqual((await self.service.chat('Resume my drink water reminder','chat-turn-0007'))['series']['status'],'active')
  skipped=await self.service.chat('Skip the next drink water reminder','chat-turn-0008')
  self.assertEqual(skipped['series']['nextOccurrenceDate'],'2026-11-15')
  self.assertEqual((await self.service.chat('Stop my drink water reminder','chat-turn-0009'))['series']['status'],'cancelled')
  self.assertEqual(self.service.series_links('conv-00000001'),{'turn-00000001':made['series']['id']})
  self.assertIsNone(await self.service.chat('What is a reminder?','chat-turn-0010'))
  self.assertIn('Reminder set',(await self.service.chat('Remind me tomorrow at 6 PM to stretch','chat-turn-0011'))['reply'],'one-shot grammar unchanged')

 async def test_http_routes_chat_done_saved_link_and_delete_only_unlinks(self):
  import httpx,json
  from unittest.mock import patch
  from june.app import app
  from june.reminders import Reminders
  from june.memory import Store
  from june.memory_service import Coordinator
  from june.config import Settings
  with tempfile.TemporaryDirectory() as home:
   now=[stamp(NOON_UTC)];reminders=Reminders(home,clock=lambda:now[0]);store=Store(Path(home));cid=store.create_conversation()['id']
   with patch.multiple(app.state,reminders=reminders,store=store,actions=None,timers=None,settings=Settings.from_env(),coordinator=Coordinator(),knowledge=None,client=None,create=True):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=Settings.from_env().backend) as client:
     value=self.daily(requestId='http-series-key')
     self.assertEqual((await client.post('/api/reminders/series',json=value,headers={'Origin':'https://other.example'})).status_code,403)
     made=await client.post('/api/reminders/series',json=value);self.assertEqual(made.status_code,200)
     s=made.json()['series'];self.assertEqual((await client.post('/api/reminders/series',json=value)).json()['series']['id'],s['id'])
     stale=await client.post(f'/api/reminders/series/{s["id"]}/skip-next',json={'revision':1,'requestId':'http-skip-key','occurrenceDate':'2026-11-20'})
     self.assertEqual(stale.status_code,409)
     self.assertEqual((await client.post(f'/api/reminders/series/{s["id"]}/pause',json={'revision':1,'requestId':'http-pause-key'})).json()['series']['status'],'paused')
     self.assertEqual((await client.post(f'/api/reminders/series/{s["id"]}/explode',json={})).status_code,404)
     state=(await client.get('/api/reminders')).json();self.assertEqual(state['series'][0]['status'],'paused')
     with patch('june.library_chat.stream_chat',side_effect=AssertionError('Repeating reminders must not call Qwen')):
      chat=await client.post('/api/chat',json={'knowledge':{'mode':'auto'},'conversationId':cid,'turnId':'series-chat','messages':[{'role':'user','content':'Remind me every day at 9 PM to stretch'}]})
     self.assertEqual(chat.status_code,200)
     done=json.loads(chat.text.splitlines()[-1]);self.assertEqual((done['series']['text'],done['series']['localTime']),('stretch','21:00'))
     saved=(await client.get('/api/library/conversations/'+cid)).json();self.assertEqual(saved['turns'][0]['reminderSeriesId'],done['series']['id'])
     await client.delete('/api/library/conversations/'+cid)
     self.assertEqual(reminders.series_links(cid),{})
     self.assertEqual([x['status'] for x in (await reminders.state())['series'] if x['id']==done['series']['id']],['active'],'deleting a chat does not stop a repeating reminder')
   await reminders.close()
