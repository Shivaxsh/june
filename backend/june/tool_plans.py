"""Application-owned bounded workflows. No model-generated executable instructions."""
import asyncio
from contextlib import suppress
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

from .errors import JuneError


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


@dataclass
class Capability:
    id: str
    label: str
    connector: str
    risk: str
    rememberable: bool
    execute: object = None
    available: bool = True
    unavailable_reason: str = 'This tool is not configured yet.'
    trusted: object = None
    remember: object = None
    # Seconds one step may take. Only a tool that runs a long job (tests, a push) declares more.
    timeout: int = 30

    def public(self):
        result = dict(id=self.id, label=self.label, connector=self.connector, risk=self.risk,
                      rememberable=self.safe_to_remember, available=self.available)
        if not result['available']:
            result['unavailableReason'] = self.unavailable_reason
        return result

    @property
    def safe_to_remember(self):
        return self.rememberable and self.risk in ('read', 'local')


class ToolPlans:
    def __init__(self, directory, *, capabilities, intents, clock=time.time):
        self.directory = Path(directory) / 'tools'
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        self.path = self.directory / 'plans.sqlite3'
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        self.path.chmod(0o600)
        self.clock = clock
        self.capabilities = {c.id: c for c in capabilities}
        self.intents = intents
        self.jobs = set()
        self.closing = False
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY,document TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,expires REAL NOT NULL,cancel INTEGER NOT NULL DEFAULT 0,remember INTEGER NOT NULL DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,signature TEXT NOT NULL,plan TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS trust(signature TEXT PRIMARY KEY)')
            db.execute('CREATE TABLE IF NOT EXISTS revocations(id TEXT PRIMARY KEY,created REAL NOT NULL)')
            # A process restart cannot establish whether a dispatched effect happened.
            for row in db.execute("SELECT * FROM plans WHERE status IN ('approved','running')").fetchall():
                doc = json.loads(row['document'])
                state = self._interrupted(doc, shutdown=True)
                db.execute('UPDATE plans SET status=?,document=? WHERE id=?', (state, encoded(doc), row['id']))

    def db(self):
        db = sqlite3.connect(self.path, timeout=3)
        db.row_factory = sqlite3.Row
        return db

    def envelope(self, **values):
        return dict(version=1, serverNow=round(self.clock() * 1000), **values)

    def _expire(self, db):
        db.execute("UPDATE plans SET status='expired' WHERE status='proposed' AND expires<=?", (self.clock(),))
        # Bound durable metadata; request ids outlive their executable proposals.
        old = self.clock() - 30 * 86400
        db.execute('DELETE FROM requests WHERE id IN (SELECT id FROM revocations WHERE created<?)', (old,))
        db.execute('DELETE FROM revocations WHERE created<?', (old,))
        db.execute("DELETE FROM requests WHERE plan IN (SELECT id FROM plans WHERE created<? AND status NOT IN ('running','approved'))", (old,))
        db.execute("DELETE FROM plans WHERE created<? AND status NOT IN ('running','approved')", (old,))

    def _row(self, db, pid):
        row = db.execute('SELECT * FROM plans WHERE id=?', (pid,)).fetchone()
        if row is None:
            raise JuneError('plan-missing', 'This plan is no longer available.', 404)
        return row

    def _immutable(self, doc):
        return {key: doc[key] for key in ('id', 'revision', 'title', 'createdAt', 'expiresAt')} | {
            'steps': [{key: s[key] for key in ('id', 'capability', 'label', 'preview', 'payload', 'policy')} for s in doc['steps']]}

    def _policy(self, cap):
        return dict(connector=cap.connector, risk=cap.risk, rememberable=cap.safe_to_remember)

    def _check_policy(self, doc):
        if any(s['capability'] not in self.capabilities or s['policy'] != self._policy(self.capabilities[s['capability']]) for s in doc['steps']):
            raise JuneError('plan-stale', 'A tool’s permissions changed. Request a new review.', 409)

    def _checked(self, row):
        doc = json.loads(row['document'])
        if digest(self._immutable(doc)) != doc['fingerprint']:
            raise JuneError('plan-stale', 'The stored plan changed. Request a new review.', 409)
        return doc

    def _public(self, row):
        doc = self._checked(row)
        return {key: doc[key] for key in ('id', 'revision', 'fingerprint', 'title', 'createdAt', 'expiresAt', 'rememberable')} | {
            'status': row['status'],
            **({'cancelRequested': True} if row['cancel'] and row['status'] in ('approved', 'running') else {}),
            'steps': [{key: value for key, value in s.items() if key not in ('payload', 'policy')} for s in doc['steps']]}

    def active_capability(self, name):
        with self.db() as db:
            rows = db.execute("SELECT document FROM plans WHERE status IN ('approved','running')").fetchall()
        return any(any(s['capability'] == name for s in json.loads(row[0])['steps']) for row in rows)

    async def state(self):
        with self.db() as db:
            self._expire(db)
            rows = db.execute('SELECT * FROM plans ORDER BY created DESC,rowid DESC LIMIT 20').fetchall()
            return self.envelope(plans=[self._public(r) for r in rows])

    async def get(self, pid):
        with self.db() as db:
            self._expire(db)
            return self.envelope(plan=self._public(self._row(db, pid)))

    def _request(self, db, value, operation):
        rid = value.get('requestId') if isinstance(value, dict) else None
        if not isinstance(rid, str) or not re.fullmatch(r'[\w-]{8,128}', rid, re.ASCII):
            raise JuneError('invalid-plan', 'A valid request id is required.', 400)
        signature = digest([operation, value])
        row = db.execute('SELECT * FROM requests WHERE id=?', (rid,)).fetchone()
        if row and row['signature'] != signature:
            raise JuneError('request-conflict', 'This request id was already used for another request.', 409)
        return rid, signature, row

    def _signature(self, doc):
        return digest([[s['capability'], s['payload']] for s in doc['steps']])

    async def propose(self, value):
        if not isinstance(value, dict) or set(value) - {'requestId', 'intent', 'input'}:
            raise JuneError('invalid-plan', 'Send a registered intent and its reviewed inputs.', 400)
        if not isinstance(value.get('input', {}), dict):
            raise JuneError('invalid-plan', 'This intent accepts no additional arguments.', 400)
        if not isinstance(value.get('intent'), str) or value['intent'] not in self.intents:
            raise JuneError('unsupported-intent', 'This workflow is not available yet.', 400)
        # Arguments are refused unless the intent explicitly validates them itself.
        if value.get('input', {}) != {} and getattr(self.intents[value['intent']], 'accepts_input', False) is not True:
            raise JuneError('invalid-plan', 'This intent accepts no additional arguments.', 400)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self._expire(db)
            rid, signature, existing = self._request(db, value, 'propose')
            if existing:
                return self.envelope(plan=self._public(self._row(db, existing['plan'])))
            if db.execute("SELECT COUNT(*) FROM plans WHERE status IN ('proposed','approved','running')").fetchone()[0] >= 20:
                raise JuneError('plan-limit', 'Review or cancel an existing plan first.', 409)
            pid = uuid.uuid4().hex
            created = self.clock()
            steps = []
            # Each intent validates its own input against app-owned registries; a step may name itself.
            for cid, payload, preview, *named in self.intents[value['intent']](value.get('input', {})):
                cap = self.capabilities.get(cid)
                if cap is None or not cap.available or cap.execute is None:
                    raise JuneError('tool-unavailable', 'A required tool is not available. Check Integrations.', 503)
                if not isinstance(preview, str) or not 1 <= len(preview) <= 4000:
                    raise JuneError('invalid-plan', 'The tool did not provide a valid review.', 400)
                steps.append(dict(id=uuid.uuid4().hex, capability=cid, label=named[0] if named and isinstance(named[0], str) and 1 <= len(named[0]) <= 120 else cap.label,
                                  preview=preview, payload=json.loads(encoded(payload)), policy=self._policy(cap), status='pending'))
            if not 1 <= len(steps) <= 12:
                raise JuneError('invalid-plan', 'A workflow needs between one and twelve steps.', 400)
            doc = dict(id=pid, revision=1, title=' → '.join(s['label'] for s in steps)[:120],
                       createdAt=round(created * 1000), expiresAt=round((created + 300) * 1000),
                       rememberable=all(self.capabilities[s['capability']].safe_to_remember for s in steps), steps=steps)
            doc['fingerprint'] = digest(self._immutable(doc))
            callbacks = [self.capabilities[s['capability']].trusted for s in steps]
            # A tool with its own remembered switch (callback) answers for its step; the other steps need
            # this exact plan to have been approved with "Don't ask again". A mixed plan needs both.
            trusted = doc['rememberable'] and all(callback(s['payload']) for callback, s in zip(callbacks, steps) if callback) and (
                all(callbacks) or db.execute('SELECT 1 FROM trust WHERE signature=?', (self._signature(doc),)).fetchone() is not None)
            db.execute('INSERT INTO plans(id,document,status,created,expires) VALUES(?,?,?,?,?)',
                       (pid, encoded(doc), 'approved' if trusted else 'proposed', created, created + 300))
            db.execute('INSERT INTO requests VALUES(?,?,?)', (rid, signature, pid))
        if trusted:
            self._start(pid)
        return await self.get(pid)

    def _bound(self, db, pid, value, approve):
        allowed = {'requestId', 'revision', 'fingerprint'} | ({'remember'} if approve else set())
        if not isinstance(value, dict) or set(value) - allowed or not {'requestId', 'revision', 'fingerprint'} <= set(value):
            raise JuneError('invalid-plan', 'Review the current plan before changing it.', 400)
        if 'remember' in value and type(value['remember']) is not bool:
            raise JuneError('invalid-plan', 'Remember must be true or false.', 400)
        row = self._row(db, pid)
        doc = self._checked(row)
        if type(value['revision']) is not int or value['revision'] != doc['revision'] or value['fingerprint'] != doc['fingerprint']:
            raise JuneError('plan-stale', 'The review does not match this plan. Refresh and review it again.', 409)
        return row, doc

    async def approve(self, pid, value):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self._expire(db)
            row, doc = self._bound(db, pid, value, True)
            if row['status'] == 'proposed':
                self._check_policy(doc)
            rid, signature, existing = self._request(db, value, ['approve', pid])
            if row['status'] == 'expired':
                raise JuneError('plan-expired', 'This plan expired. Request a new review.', 409)
            if value.get('remember') and (not doc['rememberable'] or not all(self.capabilities[s['capability']].safe_to_remember for s in doc['steps'])):
                raise JuneError('approval-required', 'Approval cannot be remembered for this workflow.', 400)
            start = not existing and row['status'] == 'proposed'
            if not existing:
                db.execute('INSERT INTO requests VALUES(?,?,?)', (rid, signature, pid))
            if start:
                db.execute("UPDATE plans SET status='approved',remember=? WHERE id=?", (int(value.get('remember', False)), pid))
        if start:
            self._start(pid)
        return await self.get(pid)

    async def cancel(self, pid, value):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self._expire(db)
            row, doc = self._bound(db, pid, value, False)
            rid, signature, existing = self._request(db, value, ['cancel', pid])
            if not existing:
                db.execute('INSERT INTO requests VALUES(?,?,?)', (rid, signature, pid))
                if row['status'] in ('proposed', 'approved'):
                    for step in doc['steps']:
                        step['status'] = 'cancelled'
                    db.execute("UPDATE plans SET status='cancelled',cancel=1,document=? WHERE id=?", (encoded(doc), pid))
                elif row['status'] == 'running':
                    db.execute('UPDATE plans SET cancel=1 WHERE id=?', (pid,))
        return await self.get(pid)

    def forget(self, value=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self._expire(db)
            if value is not None:
                rid,signature,existing=self._request(db,value,'forget')
                if existing:return
                db.execute('INSERT INTO requests VALUES(?,?,?)',(rid,signature,''))
                db.execute('INSERT INTO revocations VALUES(?,?)',(rid,self.clock()))
            for cap in self.capabilities.values():
                if cap.remember:
                    cap.remember(None, False)
            db.execute('DELETE FROM trust')
            db.execute('UPDATE plans SET remember=0')
            # Revocation wins over work approved but not yet dispatched.
            for row in db.execute("SELECT * FROM plans WHERE status='approved'").fetchall():
                doc = self._checked(row)
                for step in doc['steps']:
                    step['status'] = 'cancelled'
                db.execute("UPDATE plans SET status='cancelled',cancel=1,document=? WHERE id=?", (encoded(doc), row['id']))

    def _start(self, pid):
        if self.closing:
            return
        task = asyncio.create_task(self._execute(pid))
        self.jobs.add(task)
        task.add_done_callback(self.jobs.discard)

    async def _execute(self, pid):
        try:
            await self._steps(pid)
        except (Exception, asyncio.CancelledError) as error:
            # Never retain exception text: a provider may include credentials/content.
            with self.db() as db:
                row = self._row(db, pid)
                doc = json.loads(row['document'])
                state = self._interrupted(doc, shutdown=isinstance(error, asyncio.CancelledError))
                db.execute('UPDATE plans SET status=?,document=? WHERE id=?', (state, encoded(doc), pid))

    def _interrupted(self, doc, *, shutdown):
        uncertain = any(s['status'] == 'running' for s in doc['steps'])
        completed = any(s['status'] == 'completed' for s in doc['steps'])
        first = True
        for step in doc['steps']:
            if step['status'] == 'running':
                step['status'] = 'unknown'
                step['result'] = dict(message='The outcome could not be verified. Check before retrying.', verified=False, at=round(self.clock() * 1000))
            elif step['status'] == 'pending':
                step['status'] = 'cancelled' if shutdown else 'failed' if first and not uncertain else 'skipped'
                if uncertain and step['status'] == 'skipped': step['reason'] = 'blocked-by-unknown'
                if first:
                    step['result'] = dict(message='June stopped before this step started. It did not run.' if shutdown else 'A required tool became unavailable before this step started. It did not run.', verified=False, at=round(self.clock() * 1000))
                    first = False
        return 'unknown' if uncertain else 'partial' if completed else 'cancelled' if shutdown else 'failed'

    async def _steps(self, pid):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._row(db, pid)
            if row['status'] != 'approved':
                return
            self._check_policy(self._checked(row))
            db.execute("UPDATE plans SET status='running' WHERE id=?", (pid,))
        while True:
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                row = self._row(db, pid)
                doc = self._checked(row)
                self._check_policy(doc)
                step = next((s for s in doc['steps'] if s['status'] == 'pending'), None)
                if row['cancel']:
                    for s in doc['steps']:
                        if s['status'] == 'pending':
                            s['status'] = 'cancelled'
                    db.execute("UPDATE plans SET status='cancelled',document=? WHERE id=?", (encoded(doc), pid))
                    return
                if step is None:
                    db.execute("UPDATE plans SET status='completed' WHERE id=?", (pid,))
                    if row['remember'] and all(self.capabilities[s['capability']].safe_to_remember for s in doc['steps']):
                        db.execute('INSERT OR IGNORE INTO trust VALUES(?)', (self._signature(doc),))
                        for s in doc['steps']:
                            cap = self.capabilities[s['capability']]
                            if cap.remember:
                                cap.remember(s['payload'], True)
                    return
                cap = self.capabilities[step['capability']]
                if not cap.available or cap.execute is None:
                    raise JuneError('tool-unavailable', 'Tool unavailable.', 503)
                step['status'] = 'running'
                db.execute('UPDATE plans SET document=? WHERE id=?', (encoded(doc), pid))
                payload = json.loads(encoded(step['payload']))
            # Explicit timeout, no retries; cancellation does not pretend to undo effects.
            result = await asyncio.wait_for(cap.execute(payload), timeout=cap.timeout)
            if not isinstance(result, dict) or type(result.get('verified')) is not bool or not isinstance(result.get('message'), str):
                raise ValueError('Invalid adapter result')
            state = 'completed' if result['verified'] else 'failed' if result.get('failed') is True else 'unknown'
            with self.db() as db:
                db.execute('BEGIN IMMEDIATE')
                row = self._row(db, pid)
                doc = self._checked(row)
                current = next(s for s in doc['steps'] if s['id'] == step['id'])
                current['status'] = state
                current['result'] = dict(message=result['message'][:600], verified=result['verified'], at=round(self.clock() * 1000))
                if state != 'completed':
                    for s in doc['steps']:
                        if s['status'] == 'pending':
                            s['status'] = 'skipped'
                            if state == 'unknown': s['reason'] = 'blocked-by-unknown'
                    db.execute('UPDATE plans SET status=?,document=? WHERE id=?', (state, encoded(doc), pid))
                    return
                db.execute('UPDATE plans SET document=? WHERE id=?', (encoded(doc), pid))

    async def close(self):
        self.closing = True
        for task in tuple(self.jobs):
            task.cancel()
        for task in tuple(self.jobs):
            with suppress(asyncio.CancelledError):
                await task
        with self.db() as db:
            for row in db.execute("SELECT * FROM plans WHERE status IN ('approved','running')").fetchall():
                doc = json.loads(row['document'])
                state = self._interrupted(doc, shutdown=True)
                db.execute('UPDATE plans SET status=?,document=? WHERE id=?', (state, encoded(doc), row['id']))
