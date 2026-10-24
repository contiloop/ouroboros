"""Durable local mailbox. Trusted same-user controller, not an authentication boundary."""
from __future__ import annotations
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid


class BridgeError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise BridgeError(message)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', value), 'invalid identifier')
    return value


def private_directory(path):
    path = Path(path).absolute()
    for p in [path, *path.parents]:
        require(not p.is_symlink(), f'unsafe symlink in runtime path: {p}')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


class Store:
    def __init__(self, root):
        self.root = private_directory(root)
        self.path = self.root / 'mailbox.sqlite3'
        for suffix in ('', '-wal', '-shm'):
            require(not Path(str(self.path) + suffix).is_symlink(), 'unsafe database path')
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        os.chmod(self.path, 0o600)
        self.db.execute('PRAGMA busy_timeout=10000')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        require(self.db.execute('PRAGMA user_version').fetchone()[0] in (0, 1), 'unsupported runtime schema')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS workers (
            id TEXT PRIMARY KEY, config TEXT NOT NULL, session_id TEXT, owner TEXT,
            state TEXT NOT NULL, heartbeat REAL, pid INTEGER, stop INTEGER DEFAULT 0, error TEXT);
          CREATE TABLE IF NOT EXISTS messages (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, worker TEXT, id TEXT, fingerprint TEXT,
            body TEXT, state TEXT, owner TEXT, result TEXT, UNIQUE(worker,id));
          CREATE TABLE IF NOT EXISTS requests (
            id TEXT PRIMARY KEY, worker TEXT, message_id TEXT, owner TEXT, session_id TEXT,
            kind TEXT, body TEXT, fingerprint TEXT, state TEXT, response TEXT, response_digest TEXT);
          CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, worker TEXT, time REAL, kind TEXT, body TEXT);
          PRAGMA user_version=1;
        ''')

    def close(self):
        self.db.close()

    @contextlib.contextmanager
    def tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def event(self, wid, kind, body):
        raw = dumps(body).encode()
        if len(raw) > 131072:
            p = self.root / ('evidence-' + uuid.uuid4().hex + '.json')
            with p.open('xb') as f:
                os.chmod(p, 0o600); f.write(raw); f.flush(); os.fsync(f.fileno())
            body = {'artifact': str(p), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        self.db.execute('INSERT INTO events(worker,time,kind,body) VALUES(?,?,?,?)',
                        (wid, time.time(), kind, dumps(body)))

    def worker(self, wid):
        r = self.db.execute('SELECT * FROM workers WHERE id=?', (wid,)).fetchone()
        require(r is not None, 'unknown worker')
        return dict(r, config=json.loads(r['config']))

    def create(self, wid, config):
        identifier(wid)
        with self.tx():
            require(not self.db.execute('SELECT 1 FROM workers WHERE id=?', (wid,)).fetchone(), 'worker already exists')
            require(not self.db.execute("SELECT 1 FROM workers WHERE state NOT IN ('STOPPED','ERROR')").fetchone(),
                    'active or uncertain worker must be reconciled first')
            if self.db.execute('SELECT 1 FROM workers').fetchone():
                require(bool(config.get('handoff_ref')), 'replacement requires a reconciled handoff reference')
            self.db.execute("INSERT INTO workers(id,config,state) VALUES(?,?,'STARTING')", (wid,dumps(config)))
            self.event(wid, 'worker.created', {'backend': config['backend']})

    def own(self, wid, owner):
        w = self.worker(wid)
        require(w['owner'] == owner, 'controller ownership changed')
        return w

    def invalidate(self, wid):
        self.db.execute("UPDATE messages SET state='UNCERTAIN' WHERE worker=? AND state='DISPATCHED'", (wid,))
        self.db.execute("UPDATE messages SET state='CANCELLED' WHERE worker=? AND state='QUEUED'", (wid,))
        self.db.execute("UPDATE requests SET state='EXPIRED' WHERE worker=? AND state IN ('PENDING','ANSWERED')", (wid,))

    def attach(self, wid, owner, basis=None):
        # Caller holds the OS lock: a heartbeat timeout never authorizes stealing a live writer.
        with self.tx():
            w = self.worker(wid)
            if w['owner']:
                require(bool(basis), 'explicit reconciliation required')
                self.invalidate(wid)
                self.event(wid, 'worker.reconciled', {'basis': basis, 'session_id': w['session_id']})
            self.db.execute("UPDATE workers SET owner=?,heartbeat=?,pid=?,state='STARTING',stop=0,error=NULL WHERE id=?",
                            (owner,time.time(),os.getpid(),wid))

    def bind(self, wid, owner, sid):
        require(isinstance(sid,str) and bool(sid), 'host session ID missing')
        with self.tx():
            w = self.own(wid,owner)
            require(w['session_id'] in (None,sid), 'host replaced the recorded session')
            if w['session_id'] != sid:
                self.db.execute('UPDATE workers SET session_id=? WHERE id=?',(sid,wid))
                self.event(wid,'session.bound',{'session_id':sid})

    def state(self, wid, owner, state, error=None):
        self.own(wid,owner)
        self.db.execute('UPDATE workers SET state=?,error=?,heartbeat=? WHERE id=?',(state,error,time.time(),wid))

    def heartbeat(self, wid, owner):
        self.own(wid,owner)
        self.db.execute('UPDATE workers SET heartbeat=? WHERE id=?',(time.time(),wid))

    def message(self, wid, mid):
        r = self.db.execute('SELECT * FROM messages WHERE worker=? AND id=?',(wid,mid)).fetchone()
        require(r is not None,'unknown message')
        return dict(r,body=json.loads(r['body']),result=json.loads(r['result']) if r['result'] else None)

    def enqueue(self, wid, mid, body):
        identifier(mid)
        require(len(dumps(body).encode()) <= 262144,'input too large; reference protected artifacts')
        fp = digest(body)
        with self.tx():
            old = self.db.execute('SELECT fingerprint FROM messages WHERE worker=? AND id=?',(wid,mid)).fetchone()
            if old:
                require(old['fingerprint'] == fp,'message ID reused with different content')
                return self.message(wid,mid)
            w = self.worker(wid)
            require(w['state'] in ('IDLE','RUNNING','WAITING') and not w['stop'],'worker not accepting input')
            require(w['session_id'] and body['session_id'] == w['session_id'],'wrong recipient session')
            require(self.db.execute('SELECT COUNT(*) FROM messages WHERE worker=?',(wid,)).fetchone()[0] < 1000,'mailbox input bound exceeded')
            self.db.execute("INSERT INTO messages(worker,id,fingerprint,body,state) VALUES(?,?,?,?,'QUEUED')",(wid,mid,fp,dumps(body)))
            self.event(wid,'message.stored',{'id':mid,'digest':fp,'session_id':w['session_id']})
            return self.message(wid,mid)

    def claim(self, wid, owner):
        with self.tx():
            w = self.own(wid,owner)
            if w['stop']: return None
            require(not self.db.execute("SELECT 1 FROM messages WHERE worker=? AND state='DISPATCHED'",(wid,)).fetchone(),'another turn is in flight')
            r = self.db.execute("SELECT id FROM messages WHERE worker=? AND state='QUEUED' ORDER BY seq LIMIT 1",(wid,)).fetchone()
            if not r: return None
            self.db.execute("UPDATE messages SET state='DISPATCHED',owner=? WHERE worker=? AND id=?",(owner,wid,r['id']))
            self.db.execute("UPDATE workers SET state='RUNNING' WHERE id=?",(wid,))
            self.event(wid,'message.dispatched',{'id':r['id'],'session_id':w['session_id']})
            return self.message(wid,r['id'])

    def finish(self, wid, owner, mid, result, state='TURN_COMPLETE'):
        require(state in ('TURN_COMPLETE','TURN_FAILED','REJECTED'),'invalid terminal receipt')
        with self.tx():
            self.own(wid,owner); m = self.message(wid,mid)
            require(m['owner'] == owner and m['state'] == 'DISPATCHED','stale result')
            # Child callbacks can outlive their parent's host turn. Never expire
            # a still-live L3 permission/question as a side effect of L2 yielding.
            require(not self.unresolved(wid,mid),
                    'cannot settle parent turn while child requests remain unresolved')
            self.db.execute('UPDATE messages SET state=?,result=? WHERE worker=? AND id=?',(state,dumps(result),wid,mid))
            self.db.execute("UPDATE workers SET state='IDLE' WHERE id=?",(wid,))
            self.event(wid,'turn.settled',{'id':mid,'state':state,'digest':digest(result)})

    def unresolved(self, wid, mid):
        """Callbacks still live for a dispatched parent, including ANSWERED
        callbacks whose decision has not been consumed by the actual host."""
        return [r['id'] for r in self.db.execute(
            "SELECT id FROM requests WHERE worker=? AND message_id=? AND state IN ('PENDING','ANSWERED')",
            (wid,mid))]

    def request(self, wid, owner, mid, kind, body):
        require(kind in ('question','permission'),'invalid request kind')
        with self.tx():
            w = self.own(wid,owner); require(w['session_id'],'no session for request')
            rid = uuid.uuid4().hex
            self.db.execute("INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,'PENDING',NULL,NULL)",
                            (rid,wid,mid,owner,w['session_id'],kind,dumps(body),digest(body)))
            self.db.execute("UPDATE workers SET state='WAITING' WHERE id=?",(wid,))
            self.event(wid,'request.pending',{'id':rid,'kind':kind,'message_id':mid,'digest':digest(body)})
            return rid

    def pending(self, wid):
        return [dict(r,body=json.loads(r['body'])) for r in self.db.execute("SELECT * FROM requests WHERE worker=? AND state='PENDING' ORDER BY rowid",(wid,))]

    def answer(self, wid, rid, response):
        require(isinstance(response,dict),'answer must be an object')
        require(response.get('principal') in ('human','L1'),'unknown decision principal')
        require(isinstance(response.get('basis'),str) and response['basis'].strip(),'decision basis required')
        with self.tx():
            r = self.db.execute('SELECT * FROM requests WHERE worker=? AND id=?',(wid,rid)).fetchone()
            require(r is not None,'request does not belong to worker')
            if r['state'] in ('ANSWERED','CONSUMED'):
                require(r['response_digest'] == digest(response),'request answered with different content')
                return
            w = self.worker(wid)
            require(r['state'] == 'PENDING' and r['owner'] == w['owner'] and not w['stop'],'stale request')
            require(response.get('session_id') == r['session_id'] == w['session_id'],'wrong response session')
            require(response.get('request_digest') == r['fingerprint'],'wrong response fingerprint')
            action = response.get('action')
            if r['kind'] == 'permission':
                require(action in ('allow','deny'),'invalid permission response')
                # A generic ready approval is still insufficient: validate the separate grant.
                if action == 'allow' and response['principal'] == 'L1':
                    from .controller import check_answer
                    authorization = check_answer(self,wid,rid,response)
                    self.event(wid,'request.delegation_checked',dict(authorization,request_id=rid,phase='record'))
            else:
                require(action in ('answer','deny'),'invalid question response')
                if action == 'answer':
                    require(isinstance(response.get('answers'),dict) and response['answers'],'answers required')
                    if response['principal'] == 'L1':
                        from .controller import check_answer
                        check_answer(self,wid,rid,response)
            self.db.execute("UPDATE requests SET state='ANSWERED',response=?,response_digest=? WHERE id=?",(dumps(response),digest(response),rid))
            self.event(wid,'request.answered',{'id':rid,'principal':response['principal'],'basis':response['basis']})

    def take_answer(self, wid, owner, rid):
        with self.tx():
            self.own(wid,owner)
            r = self.db.execute('SELECT * FROM requests WHERE id=? AND worker=?',(rid,wid)).fetchone()
            require(r and r['owner'] == owner,'request ownership changed')
            if r['state'] == 'PENDING': return None
            require(r['state'] == 'ANSWERED','request expired or consumed')
            response = json.loads(r['response'])
            if response.get('principal') == 'L1' and response.get('action') != 'deny':
                from .controller import check_answer
                authorization = check_answer(self,wid,rid,response)
                if authorization is not None:
                    # The permission must still describe the SAME observed action
                    # and Git index that L1 reviewed. Revalidating scope alone is
                    # insufficient if a different in-scope file was staged later.
                    prior = None
                    for row in self.db.execute("SELECT body FROM events WHERE worker=? AND kind='request.delegation_checked' ORDER BY seq DESC",
                                               (wid,)):
                        value = json.loads(row['body'])
                        if value.get('request_id') == rid and value.get('phase') == 'record':
                            prior = {k:v for k,v in value.items() if k not in ('request_id','phase')}
                            break
                    require(prior is not None and prior == authorization,
                            'delegated operation/index changed since L1 approved it')
                    self.event(wid,'request.delegation_checked',dict(authorization,request_id=rid,phase='consume'))
            self.db.execute("UPDATE requests SET state='CONSUMED' WHERE id=?",(rid,))
            if not self.db.execute("SELECT 1 FROM requests WHERE worker=? AND state IN ('PENDING','ANSWERED')",(wid,)).fetchone():
                self.db.execute("UPDATE workers SET state='RUNNING' WHERE id=?",(wid,))
            self.event(wid,'request.consumed',{'id':rid})
            return json.loads(r['response'])

    def stop(self,wid):
        self.worker(wid)
        self.db.execute('UPDATE workers SET stop=1 WHERE id=?',(wid,))
        self.event(wid,'worker.stop_requested',{})

    def detach(self,wid,owner,error=None):
        with self.tx():
            self.own(wid,owner); self.invalidate(wid)
            self.db.execute('UPDATE workers SET state=?,heartbeat=?,error=? WHERE id=?',('ERROR' if error else 'STOPPED',time.time(),error,wid))
            self.event(wid,'worker.detached',{'error':error,'children_quiescent':'unknown'})

    def events(self,wid,after=0,limit=50):
        require(after >= 0 and 1 <= limit <= 200,'invalid cursor or page size')
        return [dict(r,body=json.loads(r['body'])) for r in self.db.execute('SELECT * FROM events WHERE worker=? AND seq>? ORDER BY seq LIMIT ?',(wid,after,limit))]


@contextlib.contextmanager
def controller_lock(root):
    import fcntl
    p = private_directory(root) / 'controller.lock'
    require(not p.is_symlink(),'unsafe lock path')
    fd = os.open(p,os.O_CREAT | os.O_RDWR,0o600)
    try:
        try: fcntl.flock(fd,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc: raise BridgeError('another controller owns this workspace') from exc
        yield
    finally:
        os.close(fd)
