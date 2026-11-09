"""Versioned private knowledge storage. Originals never enter ordinary exports."""
import json
import os
import re
import sqlite3
import uuid
from .errors import JuneError

MODEL = 'all-minilm:22m'
MAX_DOCUMENTS = 50
MAX_PASSAGES = 5000


def error(message, status=400):
    return JuneError('knowledge', message, status)


def migrate_phase_seven(store, version):
    if version >= 2:
        return
    # SQLite backup gives a consistent pre-migration snapshot, including WAL.
    backup = store.directory / 'june.pre-phase7.sqlite3'
    fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600) if not backup.exists() else None
    if fd is not None:
        os.close(fd)
        with sqlite3.connect(store.path) as source, sqlite3.connect(backup) as target:
            source.backup(target)
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        for statement in (
            'CREATE TABLE knowledge_meta (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL)',
            'INSERT INTO knowledge_meta VALUES(1,0)',
            "CREATE TABLE documents (id TEXT PRIMARY KEY,name TEXT NOT NULL,hash TEXT UNIQUE NOT NULL,status TEXT NOT NULL,message TEXT NOT NULL,progress REAL NOT NULL DEFAULT 0,pages INTEGER NOT NULL DEFAULT 0,warning TEXT NOT NULL DEFAULT '',generation TEXT NOT NULL)",
            'CREATE TABLE passages (id TEXT PRIMARY KEY,document TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,text TEXT NOT NULL,page INTEGER,lineStart INTEGER,lineEnd INTEGER,vector TEXT NOT NULL)',
            'CREATE INDEX passages_document ON passages(document)',
            'CREATE VIRTUAL TABLE passage_fts USING fts5(id UNINDEXED,text)',
            'CREATE TABLE conversation_knowledge (conversation TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,documentIds TEXT NOT NULL,revision INTEGER NOT NULL)',
            "ALTER TABLE turns ADD COLUMN citations TEXT NOT NULL DEFAULT '[]'",
            'ALTER TABLE turns ADD COLUMN knowledgeRevision INTEGER',
            'PRAGMA user_version=2',
        ):
            db.execute(statement)


def migrate(store, version):
    migrate_phase_seven(store, version)
    if version >= 3:
        return
    if version == 2:
        backup = store.directory / 'june.pre-library-chat.sqlite3'
        if not backup.exists():
            fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            with sqlite3.connect(store.path) as source, sqlite3.connect(backup) as target:
                source.backup(target)
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("ALTER TABLE conversation_knowledge ADD COLUMN mode TEXT NOT NULL DEFAULT 'selected' CHECK(mode IN ('selected','auto'))")
        db.execute('ALTER TABLE turns ADD COLUMN provenance TEXT')
        db.execute('PRAGMA user_version=3')


class KnowledgeStore:
    def __init__(self, store):
        self.store = store
        self.directory = store.directory / 'documents'
        self.directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(self.directory, 0o700)
        with store.db() as db:
            db.execute("UPDATE documents SET status='interrupted',message='Indexing interrupted. Retry explicitly.',generation=? WHERE status IN ('queued','extracting','indexing')", (str(uuid.uuid4()),))
        # Recover only app-owned orphan originals after a crash; no auto-indexing.
        with store.db() as db:
            ids = {r[0] for r in db.execute('SELECT id FROM documents')}
        for path in self.directory.iterdir():
            if re.fullmatch(r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}',path.name) and path.name not in ids and path.is_file():
                path.unlink()

    def revision(self):
        with self.store.db() as db:
            return db.execute('SELECT revision FROM knowledge_meta').fetchone()[0]

    def _public(self, row):
        return {k: row[k] for k in ('id','name','status','message','progress','pages','warning')}

    def list(self):
        with self.store.db() as db:
            return {'documents':[self._public(r) for r in db.execute('SELECT * FROM documents ORDER BY rowid')], 'revision':self.revision()}

    def get(self, did, preview=False):
        with self.store.db() as db:
            row = db.execute('SELECT * FROM documents WHERE id=?', (did,)).fetchone()
            if row is None:
                raise error('Document not found.',404)
            result = self._public(row)
            if preview:
                result['passages'] = [dict(r) for r in db.execute('SELECT id,text,page,lineStart,lineEnd FROM passages WHERE document=? ORDER BY rowid', (did,))]
            return result

    def add(self, name, data, digest):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT * FROM documents WHERE hash=?',(digest,)).fetchone()
            if existing:
                return self._public(existing), False
            if db.execute('SELECT count(*) FROM documents').fetchone()[0] >= MAX_DOCUMENTS:
                raise error('Keep at most 50 documents. Delete one before importing.',413)
            did = str(uuid.uuid4())
            path = self.directory / did
            try:
                fd = os.open(path,os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as file:
                    file.write(data)
                    file.flush()
                    os.fsync(file.fileno())
                db.execute("INSERT INTO documents(id,name,hash,status,message,generation) VALUES(?,?,?,'queued','Waiting to index.',?)",(did,name,digest,str(uuid.uuid4())))
            except BaseException:
                path.unlink(missing_ok=True)
                raise
        return self.get(did), True

    def own(self, did, status='queued', message='Waiting to index.'):
        token = str(uuid.uuid4())
        with self.store.db() as db:
            if not db.execute('UPDATE documents SET generation=?,status=?,message=?,progress=0 WHERE id=?',(token,status,message,did)).rowcount:
                raise error('Document not found.',404)
            db.execute('DELETE FROM passage_fts WHERE id IN (SELECT id FROM passages WHERE document=?)',(did,))
            db.execute('DELETE FROM passages WHERE document=?',(did,))
        return token

    def update(self, did, token, **fields):
        allowed = {'status','message','progress','pages','warning'}
        if not fields or set(fields)-allowed:
            raise ValueError('Invalid indexing update')
        with self.store.db() as db:
            return bool(db.execute('UPDATE documents SET '+','.join(k+'=?' for k in fields)+' WHERE id=? AND generation=?',(*fields.values(),did,token)).rowcount)

    def publish(self, did, token, passages, pages, warning):
        with self.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT generation FROM documents WHERE id=?',(did,)).fetchone()
            if row is None or row[0] != token:
                return False
            if db.execute('SELECT count(*) FROM passages').fetchone()[0]+len(passages)>MAX_PASSAGES:
                raise error('The library limit is 5000 passages. Delete documents before retrying.',413)
            for p in passages:
                db.execute('INSERT INTO passages VALUES(?,?,?,?,?,?,?)',(p['id'],did,p['text'],p['page'],p['lineStart'],p['lineEnd'],json.dumps(p['vector'])))
                db.execute('INSERT INTO passage_fts VALUES(?,?)',(p['id'],p['text']))
            db.execute("UPDATE documents SET status='ready',message='Ready to ask.',progress=1,pages=?,warning=? WHERE id=?",(pages,warning,did))
            db.execute('UPDATE knowledge_meta SET revision=revision+1')
        return True

    def select(self, ids):
        if (not isinstance(ids,list) or not 1<=len(ids)<=MAX_DOCUMENTS or
                any(not isinstance(x,str) or len(x)>80 for x in ids) or len(set(ids))!=len(ids)):
            raise error('Select one or more ready documents.',400)
        ids = sorted(ids)
        with self.store.db() as db:
            rows = db.execute('SELECT id,status FROM documents WHERE id IN ('+','.join('?' for _ in ids)+')',ids).fetchall()
            if len(rows)!=len(ids) or any(r['status']!='ready' for r in rows):
                raise error('The selected documents are missing or not ready. Review Documents.',409)
        return ids

    def bind(self, cid, ids):
        self.store.conversation(cid)
        with self.store.db() as db:
            row = db.execute('SELECT documentIds,mode FROM conversation_knowledge WHERE conversation=?',(cid,)).fetchone()
            if row:
                if row['mode'] != 'selected' or json.loads(row['documentIds']) != ids:
                    raise error('Document scope changed. Start a new conversation.',409)
            elif db.execute('SELECT 1 FROM turns WHERE conversation=?',(cid,)).fetchone():
                raise error('Document scope changed. Start a new conversation.',409)
            else:
                db.execute('INSERT INTO conversation_knowledge(conversation,documentIds,revision) VALUES(?,?,?)',(cid,json.dumps(ids),self.revision()))

    def delete(self, did):
        self.get(did)
        with self.store.db() as db:
            db.execute('DELETE FROM passage_fts WHERE id IN (SELECT id FROM passages WHERE document=?)',(did,))
            db.execute('DELETE FROM documents WHERE id=?',(did,))
            db.execute('UPDATE knowledge_meta SET revision=revision+1')
            # All tabs must rebuild inference context; transcript remains visible.
            self.store.reset(db)
        (self.directory / did).unlink(missing_ok=True)
