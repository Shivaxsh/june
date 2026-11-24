"""Upstream timing metadata stays numeric, optional, and visible through auto chat."""
import json,math,unittest
from unittest.mock import patch
import httpx
from june.chat import stream_chat
from june.config import Settings
from june.memory_service import persisted_chat
import test_knowledge as fixtures

class ModelTimings(unittest.IsolatedAsyncioTestCase):
 async def test_done_exposes_upstream_durations_without_releasing_private_fields(self):
  frames=[{'message':{'content':'A short reply.'}}, {'done':True,'message':{'content':''},
   'load_duration':12000000,'prompt_eval_duration':34000000,'eval_duration':56000000,'private':'do not forward'}]
  async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,text='\n'.join(map(json.dumps,frames))))) as client:
   events=[e async for e in stream_chat(client,Settings.from_env(),'local',[{'role':'user','content':'Explain a closure briefly.'}])]
  self.assertEqual(''.join(e['text'] for e in events if e['type']=='delta'),'A short reply.')
  times=events[-1]['timings']
  for key,value in {'load':12,'prompt':34,'eval':56}.items():self.assertEqual(times[key],value)
  self.assertGreaterEqual(times['first_token'],0)
  self.assertNotIn('private',events[-1])

 def test_invalid_durations_do_not_enter_telemetry(self):
  from june.model_metrics import model_timings
  for value in (True,-1,'12',float('nan'),float('inf'),10**1000,None):
   self.assertEqual(model_timings({'load_duration':value}),{})
  self.assertEqual(model_timings({'load_duration':0,'prompt_eval_duration':1500000,'eval_duration':2000000}),{'load':0,'prompt':1.5,'eval':2})

class SuffixTiming(unittest.IsolatedAsyncioTestCase):
 async def test_echo_is_not_first_new_text_and_missing_upstream_metrics_keep_measured_time(self):
  now=[100];prefix='The first step is'
  async def lines(response):
   now[0]=101;yield {'message':{'content':prefix}}
   now[0]=105;yield {'message':{'content':' to measure.'}}
   now[0]=106;yield {'message':{'content':''},'done':True}
  with patch('june.chat.model_lines',new=lines),patch('june.chat.perf_counter',new=lambda:now[0]):
   async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(200,text='unused'))) as client:
    events=[e async for e in stream_chat(client,Settings.from_env(),'local',[{'role':'user','content':'Continue.'}],continuation={'question':'Explain the steps.','prefix':prefix})]
  self.assertEqual([e['text'] for e in events if e['type']=='delta'],[' to measure.'])
  self.assertEqual(events[-1]['timings'],{'first_token':5000})

class TimingFlow(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=fixtures.KnowledgeTests.asyncSetUp
 asyncTearDown=fixtures.KnowledgeTests.asyncTearDown
 async def test_auto_chat_forwards_model_timing_and_reports_real_slot_wait(self):
  cid=self.store.create_conversation()['id'];value={'knowledge':{'mode':'auto'},'conversationId':cid,'turnId':'timed'}
  async def model(*args,**kwargs):
   yield {'type':'delta','text':'A short explanation.'}
   yield {'type':'done','model':'fixture','timings':{'load':12,'prompt':34,'eval':56,'first_token':45}}
  source=persisted_chat(self.client,self.settings,self.store,self.coordinator,value,'local',[{'role':'user','content':'Explain a closure briefly.'}],None)
  await self.coordinator.lock.acquire()
  try:
   import asyncio
   with patch('june.library_chat.stream_chat',new=model):
    event=await asyncio.wait_for(anext(source),1)
    self.assertEqual(event,{'type':'stage','stage':'queued'})
    self.coordinator.lock.release()
    rest=[e async for e in source]
   self.assertEqual({e['stage']:e['durationMs'] for e in rest if e['type']=='timing' and e['stage'] in ('load','prompt','eval','first_token')},{'load':12,'prompt':34,'eval':56,'first_token':45})
   self.assertEqual(rest[0],{'type':'stage','stage':'answering'},'slot acquisition clears queued before routing')
   self.assertEqual(rest[-1]['type'],'done')
  finally:
   if self.coordinator.lock.locked():self.coordinator.lock.release()
   await source.aclose()
