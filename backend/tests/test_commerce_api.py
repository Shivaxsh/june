"""Bounded commerce HTTP contract and the real chat route with temporary storage."""
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import httpx
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
from june.errors import JuneError
from june.integrations import create_tools
from june.commerce import Commerce,register
from june.commerce_api import router
from june.integrations_api import router as plan_router


class CommerceAPI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.plans=create_tools(self.root,None);self.commerce=Commerce(self.root,self.plans);register(self.plans,self.commerce)
        self.app=FastAPI();self.app.state.plans=self.plans
        self.app.include_router(router);self.app.include_router(plan_router)
        @self.app.exception_handler(JuneError)
        async def error(request:Request,e:JuneError):return JSONResponse({'code':e.code,'message':e.message},status_code=e.status)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://testserver')

    async def asyncTearDown(self):await self.client.aclose();await self.plans.close();self.tmp.cleanup()

    async def test_respond_wire_shape_three_domains_and_no_credential_fields(self):
        for i,text in enumerate(('buy milk','Noida','1000','tomorrow')):
            r=await self.client.post('/api/transactions/respond',json={'requestId':f'wire-{i:08}','conversationId':'wire-chat','text':text})
            self.assertEqual(r.status_code,200,r.text)
        offer=r.json()['transaction']['offers'][0]['id']
        r=await self.client.post('/api/transactions/respond',json={'requestId':'wire-select-0001','conversationId':'wire-chat','select':{'offerId':offer}})
        data=r.json();self.assertEqual(r.status_code,200,r.text);self.assertEqual(data['plan']['status'],'proposed')
        for extra in ({'cardNumber':'4111111111111111'},{'paymentRef':'live-wallet'},{'approve':True}):
            r=await self.client.post('/api/transactions/respond',json={'requestId':'wire-secret-0001','conversationId':'wire-chat','text':'I approve',**extra})
            self.assertEqual(r.status_code,400)
        state=(await self.client.get('/api/transactions')).json();self.assertEqual(len(state['transactions']),1)
        self.assertIsNone(state['transactions'][0]['receipt'])

    async def test_voice_route_never_trusts_a_client_voice_flag(self):
        r=await self.client.post('/api/plans/fake/voice-approve',json={'voice':True})
        self.assertEqual(r.status_code,400)
        r=await self.client.post('/api/transactions/respond',json={'requestId':'wire-pan-0001','conversationId':'wire-chat','text':'my card number is 4111 1111 1111 1111'})
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.commerce.state()['transactions'],[])

    async def test_saved_chat_pipeline_returns_app_owned_transaction_without_model(self):
        from june.chat import validate_chat
        from june.memory import Store
        from june.memory_service import Coordinator,persisted_chat
        store=Store(self.root/'memory');coordinator=Coordinator()
        daily=SimpleNamespace(plans=self.plans,creations=None,**{name:AsyncMock(return_value=None) for name in ('event_chat','agenda_chat','weather_chat','music_chat')})
        request={'mode':'local','temporary':True,'transactionSessionId':'temp-commerce-01','knowledge':{'mode':'auto'},'messages':[{'role':'user','content':'buy milk'}]}
        mode,messages=validate_chat(request)
        settings=SimpleNamespace(model='synthetic',ollama='http://unused.invalid')
        with patch('june.intent_router.route',AsyncMock(side_effect=AssertionError('Commerce must route before model'))):
            events=[e async for e in persisted_chat(self.client,settings,store,coordinator,request,mode,messages,None,daily=daily)]
        done=next(e for e in events if e['type']=='done')
        self.assertEqual(done['transaction']['domain'],'retail')
        self.assertIn('city',''.join(e['text'] for e in events if e['type']=='delta'))

    async def test_shared_chat_ingress_rejects_secrets_before_storing_a_turn(self):
        from june.memory import Store
        from june.memory_service import Coordinator,persisted_chat
        from june.chat import validate_chat
        store=Store(self.root/'private-memory');daily=SimpleNamespace(plans=self.plans)
        req={'mode':'local','temporary':True,'knowledge':{'mode':'auto'},'messages':[{'role':'user','content':'my card number is 4111 1111 1111 1111'}]}
        mode,messages=validate_chat(req)
        with self.assertRaises(JuneError):
            _=[e async for e in persisted_chat(self.client,SimpleNamespace(),store,Coordinator(),req,mode,messages,None,daily=daily)]
        self.assertEqual(self.commerce.state()['transactions'],[])

    async def test_missing_optional_commerce_store_does_not_break_unrelated_chat(self):
        self.commerce.path.unlink()
        self.assertIsNone(self.commerce.current('saved-conversation'))
        self.assertFalse(self.commerce.handles('what is the weather','saved-conversation'))
