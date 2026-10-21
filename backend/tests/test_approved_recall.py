import json
import tempfile
import unittest
import httpx
from june.memory import Store
from june.memory_service import Coordinator,persisted_chat
from june.config import Settings

class ApprovedRecall(unittest.IsolatedAsyncioTestCase):
    async def test_new_chat_reads_the_exact_approved_fact_and_reports_only_its_id(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);name=store.add_memory('My name is Mira-X.');color=store.add_memory('My favorite color is black.')
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:self.fail('An exact saved-fact lookup needs no inference'))) as client:
                for i,(question,fact,answer) in enumerate((('Can you do you remember what my name is?',name,'Your name is Mira-X.'),('What is my favorite color?',color,'Your favorite color is black.'))):
                    cid=store.create_conversation()['id']
                    events=[x async for x in persisted_chat(client,Settings.from_env(),store,Coordinator(),{'conversationId':cid,'turnId':str(i)},'local',[{'role':'user','content':question}])]
                    self.assertEqual(''.join(e.get('text','') for e in events),'Saved memory:\n'+answer)
                    self.assertEqual(events[-1]['source'],'application')
                    self.assertEqual(events[-1]['memoryIds'],[fact['id']])
                    self.assertEqual(store.conversation(cid)['turns'][0]['status'],'complete')
    async def test_recent_user_context_and_ambiguous_saved_facts_stay_model_backed(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);store.add_memory('My name is Mira.');cid=store.create_conversation()['id']
            store.start_turn(cid,'old','Call me Meera instead.',0);store.finish_turn('old','Understood.','complete')
            calls=[]
            def model(r):calls.append(json.loads(r.content));return httpx.Response(200,text='{"message":{"content":"Meera."},"done":true}\n')
            async with httpx.AsyncClient(transport=httpx.MockTransport(model)) as client:
                events=[x async for x in persisted_chat(client,Settings.from_env(),store,Coordinator(),{'conversationId':cid,'turnId':'new'},'local',[{'role':'user','content':'What is my name?'}])]
            self.assertEqual(len(calls),1);self.assertEqual(events[-1]['model'],Settings.from_env().model)
            self.assertIn('Call me Meera instead.',str(calls[0]['messages']))
