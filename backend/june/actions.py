"""Fixed Mac actions and saved folders. Approvals are durable and bound to proposals."""
import asyncio,hashlib,json,os,re,sqlite3,time,uuid
from pathlib import Path
from contextlib import suppress
from .errors import JuneError
from .app_info import nonliteral_request
from .action_projects import ProjectsMixin

LABEL='Open Visual Studio Code'
LEGACY_DETAIL='Opens Visual Studio Code (com.microsoft.VSCode) on this Mac. No files, commands or other apps are opened.'
DETAIL='Opens Visual Studio Code (com.microsoft.VSCode), or brings it to the front if already running. No files, commands or other apps are opened.'

def action_intent(question):
    if nonliteral_request(question):return False
    app=r'(?:my |the )?(?:vs\s*code|visual studio code)'
    command=r'(?:(?:open|launch|start)\s+'+app+r'|bring '+app+r'(?: to (?:the )?front| forward)|switch to '+app+r')'
    return bool(re.fullmatch(r'\s*(?:june[,!:\s]+)?(?:please\s+)?(?:(?:can|could|would) you\s+)?(?:please\s+)?'+command+r'(?:\s+please)?[.!?\s]*',question,re.I))

class MacAction:
    def __init__(self,directory):self.binary=Path(directory)/'JuneActions'
    async def _run(self,command,*args):
        if not self.binary.is_file():return None
        try:
            process=await asyncio.create_subprocess_exec(str(self.binary),command,*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        except OSError:return None
        try:
            output,_=await asyncio.wait_for(process.communicate(),12)
            if process.returncode or len(output)>4096:return None
            result=json.loads(output)
            if result.get('protocol')!=1 or result.get('bundleId')!='com.microsoft.VSCode':return None
            return result
        except (TimeoutError,ValueError,AttributeError):return None
        finally:
            if process.returncode is None:
                process.kill()
                with suppress(ProcessLookupError):await process.wait()
    async def inspect(self):
        result=await self._run('--inspect')
        return {'available':bool(result and result.get('installed') is True),'state':result.get('state','unverified') if result else 'unverified'}
    async def execute(self):
        result=await self._run('--open-vscode')
        state=result.get('state') if result else 'unverified'
        if state not in ('active','running','failed'):state='unverified'
        message={'active':'Visual Studio Code is active on this Mac.','running':'Visual Studio Code is running; it may be behind another window.','failed':'The Mac could not open Visual Studio Code.','unverified':'The request was issued, but June could not verify the result. It will not be retried automatically.'}[state]
        return {'state':state,'message':message}

    async def execute_project(self,path,identity):
        device,inode=json.loads(identity)
        result=await self._run('--open-project',path,str(device),str(inode))
        state=result.get('state') if result else 'unverified'
        accepted=bool(result and result.get('folderAccepted') is True)
        if state not in ('active','running','failed') or (state in ('active','running') and not accepted):state='unverified'
        message='macOS accepted the folder request; VS Code is '+('in front.' if state=='active' else 'running.') if state in ('active','running') else 'The folder could not be opened.' if state=='failed' else 'June could not verify the folder request. It will not retry automatically.'
        return {'state':state,'message':message}

class Actions(ProjectsMixin):
    def __init__(self,directory,native=None,clock=time.time):
        self.directory=Path(directory)/'actions';self.directory.mkdir(parents=True,exist_ok=True,mode=0o700);self.directory.chmod(0o700)
        self.path=self.directory/'actions.sqlite3';self.clock=clock;self.native=native or MacAction(self.directory);self.jobs=set();self.inspection=None;self.inspected_at=-float('inf')
        fd=os.open(self.path,os.O_CREAT|os.O_RDWR,0o600);os.close(fd);self.path.chmod(0o600)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, status TEXT NOT NULL, result TEXT, conversation TEXT, turn TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS audit(id TEXT, status TEXT, at REAL)')
            columns={r['name'] for r in db.execute('PRAGMA table_info(actions)')}
            for name in ('label','detail','request_id','mode'):

                if name not in columns:db.execute(f'ALTER TABLE actions ADD COLUMN {name} TEXT')
            db.execute('UPDATE actions SET label=COALESCE(label,?),detail=COALESCE(detail,?)',(LABEL,LEGACY_DETAIL))
            db.execute("UPDATE actions SET mode='approved' WHERE mode IS NULL")
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS action_request ON actions(request_id)')
            self._projects_schema(db)
            db.execute('CREATE TABLE IF NOT EXISTS preferences(key TEXT PRIMARY KEY,value INTEGER NOT NULL)')
            db.execute("UPDATE actions SET status='unverified',result=? WHERE status='executing'",(json.dumps({'state':'unverified','message':'June restarted before the result was recorded. This action will not be retried.'}),))
    def db(self):
        db=sqlite3.connect(self.path,timeout=3);db.row_factory=sqlite3.Row;return db
    def _record(self,row):
        value={'id':row['id'],'action':'open-vscode','label':row['label'],'detail':row['detail'],'fingerprint':row['fingerprint'],'createdAt':round(row['created']*1000),'expiresAt':round(row['expires']*1000),'status':row['status'],'mode':row['mode'] or 'approved'}
        if row['project_id']:value.update(action='open-project',projectId=row['project_id'],projectPath=row['project_path'])
        if row['result']:value['result']=json.loads(row['result'])
        return value
    def _response(self,row):return {'serverNow':round(self.clock()*1000),'action':self._record(row)}
    def _expire(self,db):
        db.execute("UPDATE actions SET status='expired' WHERE status='proposed' AND expires<=?",(self.clock(),))
        # Action history contains fixed capability metadata only, and is retained for 30 days.
        db.execute("DELETE FROM actions WHERE created<? AND status!='executing'",(self.clock()-30*86400,))
        db.execute('DELETE FROM audit WHERE at<?',(self.clock()-30*86400,))
    async def _inspect(self):
        if self.inspection is None or self.clock()-self.inspected_at>=5:
            self.inspection=await self.native.inspect();self.inspected_at=self.clock()
        return self.inspection
    async def state(self):
        observed=await self._inspect()
        with self.db() as db:
            self._expire(db);rows=db.execute('SELECT * FROM actions ORDER BY created DESC,rowid DESC LIMIT 20').fetchall()
        app_state=observed.get('state') if observed['available'] and observed.get('state') in ('active','running','not-running') else 'unverified'
        return {'serverNow':round(self.clock()*1000),'available':observed['available'],'appState':app_state,'observedAt':round(self.inspected_at*1000),'openVSCodeWithoutApproval':self.trusted(),'actions':[self._record(r) for r in rows],'projects':self.project_list()}
    def trusted(self,db=None):
        if db is None:
            with self.db() as saved:return self.trusted(saved)
        row=db.execute("SELECT value FROM preferences WHERE key='open-vscode'").fetchone()
        return bool(row and row[0]==1)
    async def preferences(self,value):
        if not isinstance(value,dict) or set(value)!={'openVSCodeWithoutApproval'} or not isinstance(value['openVSCodeWithoutApproval'],bool):
            raise JuneError('invalid-preference','Choose whether to remember approval for opening VS Code only.',400)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if value['openVSCodeWithoutApproval'] and not db.execute("SELECT 1 FROM actions WHERE mode='approved' AND status='completed' AND project_id IS NULL LIMIT 1").fetchone():
                raise JuneError('approval-required','Review and approve opening VS Code once before remembering that exact action.',409)
            db.execute("INSERT OR REPLACE INTO preferences VALUES('open-vscode',?)",(int(value['openVSCodeWithoutApproval']),))
        return await self.state()
    async def run(self,value,*,conversation=None,turn=None):
        if isinstance(value,dict) and value.get('action')=='open-project':return await self._project_request(value,True,conversation,turn)
        if not isinstance(value,dict) or set(value)!={'action','requestId'} or value['action']!='open-vscode' or not isinstance(value['requestId'],str) or not re.fullmatch(r'[\w-]{8,128}',value['requestId']):
            raise JuneError('unsupported-action','Only the exact VS Code action with a request id is supported.',400)
        with self.db() as db:
            row=db.execute('SELECT * FROM actions WHERE request_id=?',(value['requestId'],)).fetchone()
            if row:return self._response(row)
            if not self.trusted(db):raise JuneError('approval-required','Review this action first, or remember its approval in Hands.',409)
        if not (await self._inspect())['available']:raise JuneError('actions-unavailable','Mac actions are not ready on this Mac. Check Hands.',503)
        aid=uuid.uuid4().hex;created=self.clock();expires=created+300
        fingerprint=hashlib.sha256(json.dumps([aid,'open-vscode',DETAIL,created,expires],separators=(',',':')).encode()).hexdigest()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._expire(db)
            row=db.execute('SELECT * FROM actions WHERE request_id=?',(value['requestId'],)).fetchone()
            if row:return self._response(row)
            if not self.trusted(db):raise JuneError('approval-required','Remembered approval was turned off. Review this action first.',409)
            db.execute('INSERT INTO actions(id,fingerprint,created,expires,status,conversation,turn,label,detail,request_id,mode) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(aid,fingerprint,created,expires,'executing',conversation,turn,LABEL,DETAIL,value['requestId'],'direct'))
            db.execute('INSERT INTO audit VALUES(?,?,?)',(aid,'executing',created))
        task=asyncio.create_task(self._execute(aid));self.jobs.add(task);task.add_done_callback(self.jobs.discard)
        return await asyncio.shield(task)

    async def propose(self,value,*,conversation=None,turn=None):
        if isinstance(value,dict) and value.get('action')=='open-project':return await self._project_request(value,False,conversation,turn)
        if not isinstance(value,dict) or value!={'action':'open-vscode'}:raise JuneError('unsupported-action','Only opening Visual Studio Code is supported; no arguments are accepted.',400)
        if not (await self._inspect())['available']:raise JuneError('actions-unavailable','Mac actions are not ready on this Mac. Open Hands in Systems to check the status.',503)
        aid=uuid.uuid4().hex;created=self.clock();expires=created+300
        fingerprint=hashlib.sha256(json.dumps([aid,'open-vscode',DETAIL,created,expires],separators=(',',':')).encode()).hexdigest()
        with self.db() as db:
            self._expire(db)
            if db.execute("SELECT COUNT(*) FROM actions WHERE status='proposed'").fetchone()[0]>=20:raise JuneError('action-limit','Review or cancel an existing action first.',409)
            db.execute('INSERT INTO actions(id,fingerprint,created,expires,status,result,conversation,turn,label,detail,mode) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(aid,fingerprint,created,expires,'proposed',None,conversation,turn,LABEL,DETAIL,'approved'))
            db.execute('INSERT INTO audit VALUES(?,?,?)',(aid,'proposed',created));row=db.execute('SELECT * FROM actions WHERE id=?',(aid,)).fetchone()
        return self._response(row)
    def unlink(self,cid=None):
        with self.db() as db:
            where='WHERE conversation=?' if cid else ''
            params=(cid,) if cid else ()
            db.execute("UPDATE actions SET status=CASE WHEN status='proposed' THEN 'cancelled' ELSE status END,conversation=NULL,turn=NULL "+where,params)
    def links(self,cid):
        with self.db() as db:return {r['turn']:r['id'] for r in db.execute('SELECT id,turn FROM actions WHERE conversation=? AND turn IS NOT NULL',(cid,))}
    def _bound(self,db,aid,value,remember=False):
        row=db.execute('SELECT * FROM actions WHERE id=?',(aid,)).fetchone()
        if not row:raise JuneError('action-missing','Action not found. Request a new proposal.',404)
        valid=isinstance(value,dict) and set(value) in ({'fingerprint'},{'fingerprint','remember'} if remember else {'fingerprint'})
        if not valid or value.get('fingerprint')!=row['fingerprint'] or ('remember' in value and not isinstance(value['remember'],bool)):raise JuneError('action-mismatch','The approval does not match this action. Refresh Hands.',409)
        return row
    def chat_reply(self,question,conversation,last_turn=None):
        if not conversation or nonliteral_request(question):return None
        status_query=bool(re.fullmatch(r'\s*(?:did you|have you|has june) (?:open(?:ed)?|launch(?:ed)?) (?:vs\s*code|visual studio code)[?!.\s]*',question,re.I))
        approval=bool(re.fullmatch(r'\s*(?:please )?(?:approve|confirm|yes|go ahead|do it)(?: (?:it|that|the action|opening (?:vs\s*code|visual studio code)))?[.!?\s]*',question,re.I))
        if not status_query and not approval:return None
        with self.db() as db:
            self._expire(db)
            row=db.execute('SELECT * FROM actions WHERE conversation=? ORDER BY created DESC,rowid DESC LIMIT 1',(conversation,)).fetchone()
        if approval and (not row or (row['turn']!=last_turn and not re.search(r'approve|confirm|vs\s*code',question,re.I))):return None
        if not row:return 'June has no VS Code action recorded in this conversation. Ask to open VS Code to review a proposal.'
        status=row['status']
        if status=='proposed':return 'Opening VS Code is waiting for your approval. Click Approve on its action card to run it, or Cancel. A spoken or typed confirmation cannot approve it.'
        if status=='executing':return 'The approved VS Code action is executing. June has not verified the result yet.'
        if status=='completed':
            if row['project_id']:return json.loads(row['result'] or '{}').get('message','Check Hands for the folder request outcome.')
            state=json.loads(row['result'] or '{}').get('state')
            return 'Visual Studio Code was observed active on this Mac after the approved action.' if state=='active' else 'Visual Studio Code was observed running after the approved action; it may be behind another window.'
        if status=='failed':return 'The Mac reported that it could not open Visual Studio Code. June will not retry it automatically.'
        if status in ('cancelled','expired'):return 'That VS Code proposal was '+status+'. It did not run. Ask for a new proposal if you still want it.'
        return 'June could not verify that VS Code opened from that action. Check Hands; it will not be retried automatically.'

    async def cancel(self,aid,value):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._expire(db);row=self._bound(db,aid,value)
            if row['status']=='executing':raise JuneError('action-started','The approved action has already started and cannot be cancelled.',409)
            if row['status']=='proposed':
                db.execute("UPDATE actions SET status='cancelled' WHERE id=?",(aid,));db.execute('INSERT INTO audit VALUES(?,?,?)',(aid,'cancelled',self.clock()))
            row=db.execute('SELECT * FROM actions WHERE id=?',(aid,)).fetchone()
        return self._response(row)
    async def approve(self,aid,value):
        expired=False
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._expire(db);row=self._bound(db,aid,value,remember=True)
            expired=row['status']=='expired'
            if row['status']!='proposed':result=self._response(row)
            else:
                if row['project_id']:self._validate_project_action(db,row)
                db.execute("UPDATE actions SET status='executing' WHERE id=?",(aid,));db.execute('INSERT INTO audit VALUES(?,?,?)',(aid,'executing',self.clock()));result=None
                if value.get('remember') is True:
                    if row['project_id']:db.execute('UPDATE projects SET remembered=1 WHERE id=?',(row['project_id'],))
                    else:db.execute("INSERT OR REPLACE INTO preferences VALUES('open-vscode',1)")
        if expired:raise JuneError('action-expired','This action expired. Request a new proposal.',409)
        if result:return result
        task=asyncio.create_task(self._execute(aid));self.jobs.add(task);task.add_done_callback(self.jobs.discard)
        return await asyncio.shield(task)
    async def _execute(self,aid):
        try:
            with self.db() as db:
                row=db.execute('SELECT * FROM actions WHERE id=?',(aid,)).fetchone()
                if row['project_id']:self._validate_project_action(db,row)
            result=await self.native.execute_project(row['project_path'],row['project_identity']) if row['project_id'] else await self.native.execute()
        except Exception:result={'state':'unverified','message':'June could not verify the action result. It will not be retried automatically.'}
        status='completed' if result['state'] in ('active','running') else 'failed' if result['state']=='failed' else 'unverified'
        with self.db() as db:
            db.execute('UPDATE actions SET status=?,result=? WHERE id=? AND status=\'executing\'',(status,json.dumps(result),aid));db.execute('INSERT INTO audit VALUES(?,?,?)',(aid,status,self.clock()));row=db.execute('SELECT * FROM actions WHERE id=?',(aid,)).fetchone()
        return self._response(row)
    async def close(self):
        if self.jobs:await asyncio.gather(*list(self.jobs),return_exceptions=True)
