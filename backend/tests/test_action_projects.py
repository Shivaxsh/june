"""Project actions remain bound to a registered folder and exact approval."""
import asyncio,tempfile,unittest
from pathlib import Path
from june.actions import Actions
from june.errors import JuneError

class Native:
 def __init__(self):self.paths=[]
 async def inspect(self):return {'available':True,'state':'active'}
 async def execute(self):return {'state':'active','message':'VS Code observed.'}
 async def execute_project(self,path,identity):
  self.paths.append(path)
  return {'state':'active','message':'Folder request accepted; VS Code observed.'}

class Projects(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()
  self.folder=self.root/'a project';self.folder.mkdir();self.native=Native()
  self.service=Actions(self.root/'data',self.native)
 async def asyncTearDown(self):await self.service.close();self.tmp.cleanup()
 async def add(self,name='June',path=None):
  state=await self.service.add_project({'name':name,'path':str(path or self.folder)})
  return next(p for p in state['projects'] if p['name']==name)
 async def test_project_requires_own_approval_and_retries_execute_once(self):
  p=await self.add();await self.service.preferences({'openVSCodeWithoutApproval':False})
  body={'action':'open-project','projectId':p['id'],'requestId':'project-run-0001'}
  with self.assertRaises(JuneError):await self.service.run(body)
  proposal=(await self.service.propose({'action':'open-project','projectId':p['id']}))['action']
  self.assertEqual(proposal['projectPath'],str(self.folder));self.assertEqual(proposal['action'],'open-project')
  await self.service.approve(proposal['id'],{'fingerprint':proposal['fingerprint'],'remember':True})
  self.assertFalse(self.service.trusted(),'folder approval does not grant app-only approval')
  await asyncio.gather(self.service.run(body),self.service.run(body))
  self.assertEqual(self.native.paths,[str(self.folder)]*2,'approval plus one direct run')
  state=await self.service.state();self.assertTrue(state['projects'][0]['remembered'])
 async def test_app_approval_does_not_authorize_project_or_another_folder(self):
  app=(await self.service.propose({'action':'open-vscode'}))['action']
  await self.service.approve(app['id'],{'fingerprint':app['fingerprint'],'remember':True})
  p=await self.add()
  with self.assertRaises(JuneError):await self.service.run({'action':'open-project','projectId':p['id'],'requestId':'project-run-0001'})
  self.assertEqual(self.native.paths,[])
 async def test_remove_revokes_and_invalidates_pending_approval(self):
  p=await self.add();a=(await self.service.propose({'action':'open-project','projectId':p['id']}))['action']
  await self.service.remove_project(p['id'])
  result=await self.service.approve(a['id'],{'fingerprint':a['fingerprint'],'remember':True})
  self.assertEqual(result['action']['status'],'cancelled');self.assertEqual(self.native.paths,[])
  with self.assertRaises(JuneError):await self.service.propose({'action':'open-project','projectId':p['id']})
 async def test_replaced_or_retargeted_folder_never_executes(self):
  target=self.root/'target';target.mkdir();link=self.root/'link';link.symlink_to(self.folder)
  p=await self.add(path=link);a=(await self.service.propose({'action':'open-project','projectId':p['id']}))['action']
  self.folder.rename(self.root/'original');self.folder.symlink_to(target)
  with self.assertRaises(JuneError):await self.service.approve(a['id'],{'fingerprint':a['fingerprint'],'remember':True})
  self.assertEqual(self.native.paths,[])
 async def test_validation_and_no_model_paths(self):
  for body in ({'name':'June','path':'relative'},{'name':'June','path':str(self.root/'missing')},{'name':'','path':str(self.folder)}):
   with self.assertRaises(JuneError):await self.service.add_project(body)
  p=await self.add()
  with self.assertRaises(JuneError):await self.service.add_project({'name':'june','path':str(self.folder)})
  with self.assertRaises(JuneError):await self.service.propose({'action':'open-project','projectId':p['id'],'path':str(self.folder)})
  self.assertEqual(self.native.paths,[])
 async def test_exact_chat_name_and_forget(self):
  p=await self.add()
  self.assertIsNone(self.service.project_intent('Do not open the June project'))
  self.assertIsNone(self.service.project_intent('Explain how to open June project'))
  self.assertIsNone(self.service.project_intent('Open June project and delete files'))
  intent=self.service.project_intent('Please open the June project in VS Code.')
  self.assertEqual(intent,{'action':'open-project','projectId':p['id']})
  a=(await self.service.propose(intent))['action'];await self.service.approve(a['id'],{'fingerprint':a['fingerprint'],'remember':True})
  await self.service.forget_project(p['id'])
  with self.assertRaises(JuneError):await self.service.run({**intent,'requestId':'project-run-0002'})

 async def test_http_and_chat_use_saved_id_without_inference(self):
  import json,httpx
  from unittest.mock import patch
  from june.app import app
  from june.config import Settings
  from june.memory import Store
  from june.memory_service import Coordinator
  settings=Settings.from_env();store=Store(self.root/'data');cid=store.create_conversation()['id']
  with patch.multiple(app.state,actions=self.service,store=store,settings=settings,coordinator=Coordinator(),knowledge=None,client=None,create=True):
   async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=settings.backend) as client:
    denied=await client.post('/api/actions/projects',json={'name':'June','path':str(self.folder)},headers={'Origin':'https://other.example'})
    self.assertEqual(denied.status_code,403)
    saved=await client.post('/api/actions/projects',json={'name':'June','path':str(self.folder)})
    self.assertEqual(saved.status_code,200);pid=saved.json()['projects'][0]['id']
    with patch('june.library_chat.stream_chat',side_effect=AssertionError('No model for a saved project')):
     response=await client.post('/api/chat',json={'mode':'local','knowledge':{'mode':'auto'},'conversationId':cid,'turnId':'project-chat-0001','messages':[{'role':'user','content':'Open the June project in VS Code.'}]})
    self.assertEqual(response.status_code,200);done=json.loads(response.text.splitlines()[-1]);a=done['actionProposal']
    self.assertEqual(a['projectId'],pid);self.assertEqual(self.native.paths,[])
    approved=await client.post('/api/actions/'+a['id']+'/approve',json={'fingerprint':a['fingerprint'],'remember':True})
    self.assertEqual(approved.json()['action']['status'],'completed')
    self.assertEqual(self.native.paths,[str(self.folder)])
    forgotten=await client.post('/api/actions/projects/'+pid+'/forget',json={})
    self.assertFalse(forgotten.json()['projects'][0]['remembered'])
    removed=await client.post('/api/actions/projects/'+pid+'/remove',json={});self.assertEqual(removed.json()['projects'],[])
