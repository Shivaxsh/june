"""User-maintained folder registry. Chat and execution accept opaque ids, never paths."""
import asyncio,hashlib,json,re,uuid
from pathlib import Path
from .errors import JuneError
from .app_info import nonliteral_request

class ProjectsMixin:
    def _projects_schema(self,db):
        columns={r['name'] for r in db.execute('PRAGMA table_info(actions)')}
        for name in ('project_id','project_path','project_identity'):
            if name not in columns:db.execute(f'ALTER TABLE actions ADD COLUMN {name} TEXT')
        db.execute('CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL COLLATE NOCASE UNIQUE,path TEXT UNIQUE NOT NULL,identity TEXT NOT NULL,remembered INTEGER NOT NULL DEFAULT 0)')
    def _folder(self,value):
        if not isinstance(value,str) or len(value)>1024 or not value.startswith('/') or any(ord(c)<32 for c in value):
            raise JuneError('project-folder','Use an existing absolute folder path.',400)
        try:
            path=Path(value).resolve(strict=True)
            if not path.is_dir():raise ValueError()
            info=path.stat()
            return str(path),json.dumps([info.st_dev,info.st_ino])
        except (OSError,ValueError,RuntimeError):raise JuneError('project-folder','That folder is unavailable. Check its path.',400) from None
    def _project(self,db,pid,validate=True):
        p=db.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
        if not p:raise JuneError('project-missing','This project is not in Hands. Add it there first.',404)
        if validate:
            try:path,identity=self._folder(p['path'])
            except JuneError:raise JuneError('project-changed','This folder is unavailable or changed. Remove it and add it again in Hands.',409) from None
            if path!=p['path'] or identity!=p['identity']:
                raise JuneError('project-changed','This folder changed. Remove it and add it again in Hands before approving.',409)
        return p
    def project_list(self):
        with self.db() as db:
            return [{'id':r['id'],'name':r['name'],'folderPath':r['path'],'remembered':bool(r['remembered'])} for r in db.execute('SELECT * FROM projects ORDER BY name')]
    async def add_project(self,value):
        if not isinstance(value,dict) or set(value)!={'name','path'} or not isinstance(value['name'],str) or not re.fullmatch(r'[\w][\w .-]{0,59}',value['name'].strip()):
            raise JuneError('project-name','Give the project a short name using letters, numbers, spaces, dots or hyphens.',400)
        path,identity=self._folder(value['path']);name=value['name'].strip()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM projects WHERE name=? OR path=?',(name,path)).fetchone():raise JuneError('project-duplicate','That name or folder is already saved in Hands.',409)
            if db.execute('SELECT COUNT(*) FROM projects').fetchone()[0]>=10:raise JuneError('project-limit','Keep up to 10 projects in Hands. Remove one first.',409)
            db.execute('INSERT INTO projects(id,name,path,identity) VALUES(?,?,?,?)',(uuid.uuid4().hex,name,path,identity))
        return await self.state()
    async def remove_project(self,pid):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._project(db,pid,False)
            db.execute("UPDATE actions SET status='cancelled' WHERE project_id=? AND status='proposed'",(pid,))
            db.execute('DELETE FROM projects WHERE id=?',(pid,))
        return await self.state()
    async def forget_project(self,pid):
        with self.db() as db:
            self._project(db,pid,False);db.execute('UPDATE projects SET remembered=0 WHERE id=?',(pid,))
        return await self.state()
    def project_trusted(self,pid):
        with self.db() as db:return bool(self._project(db,pid)['remembered'])
    def project_intent(self,question):
        if nonliteral_request(question):return None
        match=re.fullmatch(r'\s*(?:june[,!:\s]+)?(?:please\s+)?(?:(?:can|could|would) you\s+)?(?:please\s+)?open (?:my |the )?([\w .-]+?) project(?: in (?:vs\s*code|visual studio code))?(?: please)?[.!?\s]*',question,re.I)
        if not match:return None
        with self.db() as db:p=db.execute('SELECT id FROM projects WHERE name=?',(match[1].strip(),)).fetchone()
        return {'action':'open-project','projectId':p['id']} if p else {'missingProject':True}
    async def _project_request(self,value,direct=False,conversation=None,turn=None):
        allowed={'action','projectId','requestId'} if direct else {'action','projectId'}
        if set(value)!=allowed or not isinstance(value.get('projectId'),str) or (direct and (not isinstance(value['requestId'],str) or not re.fullmatch(r'[\w-]{8,128}',value['requestId']))):
            raise JuneError('unsupported-action','Select a saved project id; no paths or arguments are accepted.',400)
        if not (await self._inspect())['available']:raise JuneError('actions-unavailable','Mac actions are not ready. Check Hands.',503)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE');self._expire(db)
            if direct:
                prior=db.execute('SELECT * FROM actions WHERE request_id=?',(value['requestId'],)).fetchone()
                if prior:
                    if prior['project_id']!=value['projectId']:raise JuneError('action-mismatch','This request id belongs to another action.',409)
                    return self._response(prior)
            p=self._project(db,value['projectId'])
            if direct and not p['remembered']:raise JuneError('approval-required','Approve this exact project folder first.',409)
            if not direct and db.execute("SELECT COUNT(*) FROM actions WHERE status='proposed'").fetchone()[0]>=20:raise JuneError('action-limit','Review or cancel an existing proposal first.',409)
            aid=uuid.uuid4().hex;now=self.clock();expires=now+300
            detail='Opens the saved folder in Visual Studio Code. No commands run. Folder: '+p['path']
            fingerprint=hashlib.sha256(json.dumps([aid,p['id'],p['path'],p['identity'],now,expires]).encode()).hexdigest()
            db.execute('INSERT INTO actions(id,fingerprint,created,expires,status,conversation,turn,label,detail,mode,request_id,project_id,project_path,project_identity) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (aid,fingerprint,now,expires,'executing' if direct else 'proposed',conversation,turn,'Open '+p['name']+' project',detail,'direct' if direct else 'approved',value.get('requestId'),p['id'],p['path'],p['identity']))
            db.execute('INSERT INTO audit VALUES(?,?,?)',(aid,'executing' if direct else 'proposed',now))
            row=db.execute('SELECT * FROM actions WHERE id=?',(aid,)).fetchone()
        if not direct:return self._response(row)
        task=asyncio.create_task(self._execute(aid));self.jobs.add(task);task.add_done_callback(self.jobs.discard)
        return await asyncio.shield(task)
    def _validate_project_action(self,db,row):
        p=self._project(db,row['project_id'])
        if p['path']!=row['project_path'] or p['identity']!=row['project_identity']:raise JuneError('action-mismatch','The folder no longer matches this proposal.',409)
        return p
