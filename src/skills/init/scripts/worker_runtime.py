#!/usr/bin/env python3
"""Persistent L2 runtime. Python 3.11+, POSIX. No auto-install/login/permission bypass.

Claude uses an explicitly installed claude-agent-sdk; Codex uses installed codex app-server.
Only a trusted local controller/operator may submit messages and decision records.
"""
from __future__ import annotations
import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from runtime_bridge.controller import prepare, serve, check_answer, delegation_for
from runtime_bridge.store import Store, BridgeError, controller_lock, identifier, require

SCRIPTS = Path(__file__).resolve().parent


def doctor(backend):
    sdk = importlib.util.find_spec('claude_agent_sdk') is not None
    exe = shutil.which('codex' if backend == 'codex' else 'claude')
    dependency = sdk if backend == 'claude' else bool(exe)
    return {'backend':backend,'python':sys.version.split()[0],'executable':exe,'dependency_found':dependency,
            'ready_to_attempt':os.name == 'posix' and sys.version_info >= (3,11) and dependency,
            'live_verified':False,'authentication_verified':False,
            'note':'Dependency check only. Claude startup includes a no-tool model bootstrap call.'}


def workspace_path(value):
    p = Path(value).expanduser().resolve()
    require(p.is_dir(),'workspace missing')
    r = subprocess.run(['git','-C',str(p),'rev-parse','--show-toplevel'],capture_output=True,text=True)
    require(r.returncode == 0 and Path(r.stdout.strip()).resolve() == p,'workspace must be a Git repository root')
    r = subprocess.run(['git','-C',str(p),'check-ignore','-q','.dryforge/mission/runtime/mailbox.sqlite3'])
    require(r.returncode == 0,'add .dryforge/ to this project gitignore before creating private state')
    return p


def status(store,wid):
    w = store.worker(wid)
    age = time.time()-w['heartbeat'] if w['heartbeat'] else None
    state = w['state']
    if state not in ('ERROR','STOPPED') and (age is None or age > 10):
        state = 'STARTING' if w['owner'] is None else 'UNREACHABLE'
    pending = store.pending(wid)
    for request in pending:
        request['delegation'] = delegation_for(store,wid,request)
    return {'worker':wid,'backend':w['config']['backend'],'session_id':w['session_id'],
            'state':state,'recorded_state':w['state'],'heartbeat_age_seconds':age,'pid':w['pid'],
            'error':w['error'],'pending':pending,'context_headroom':'unknown',
            'children_quiescent':'unknown','deadline':w['config']['deadline']}


def message_view(m,full=False):
    if full: return m
    result = dict(m['result']) if isinstance(m['result'],dict) else m['result']; clipped = False
    if isinstance(result,dict) and isinstance(result.get('text'),str) and len(result['text']) > 8000:
        result['text'] = result['text'][:8000]; clipped = True
    return {'id':m['id'],'state':m['state'],'kind':m['body']['kind'],'session_id':m['body']['session_id'],
            'result':result,'result_truncated':clipped,'full_record':'result --id '+m['id']+' --full'}


def launch(store,wid,basis=None):
    with controller_lock(store.root): pass
    w = store.worker(wid)
    require(not w['owner'] or basis,'resume needs explicit reconciliation basis')
    log = store.root/(wid+'.controller.log'); require(not log.is_symlink(),'unsafe log path')
    cmd = [sys.executable,'-B',str(Path(__file__).resolve()),'__serve','--workspace',w['config']['workspace'],'--worker',wid]
    if basis: cmd += ['--basis',basis]
    with log.open('ab') as out:
        os.chmod(log,0o600)
        p = subprocess.Popen(cmd,stdin=subprocess.DEVNULL,stdout=out,stderr=out,
                             cwd=w['config']['workspace'],start_new_session=True)
    return {'worker':wid,'controller_pid':p.pid,'state':'STARTING','log':str(log),
            'note':'Observe status; process creation is not session readiness.'}


def parser():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='command',required=True)
    d = sub.add_parser('doctor'); d.add_argument('--backend',choices=('claude','codex'),required=True)
    for name in ('start','resume','stop','status','send','answer','result','wait','events','__serve'):
        s = sub.add_parser(name); s.add_argument('--workspace',required=True); s.add_argument('--worker',required=True)
        if name == 'start':
            s.add_argument('--backend',choices=('claude','codex'),required=True)
            s.add_argument('--model'); s.add_argument('--handoff-ref')
            for k,default in (('turn-seconds',600),('lifetime-seconds',3600),('startup-seconds',120),('max-messages',20),('max-model-turns',50)):
                s.add_argument('--'+k,type=int,default=default)
            s.add_argument('--budget-usd',type=float)
            s.add_argument('--load-settings',action='append',choices=('user','project','local'),default=[])
        if name in ('resume','__serve'): s.add_argument('--basis')
        if name == 'resume': s.add_argument('--reconciled',action='store_true')
        if name == 'send':
            s.add_argument('--id',required=True); s.add_argument('--kind',choices=('probe','ready','go','message'),required=True)
            s.add_argument('--text-file',type=Path,required=True); s.add_argument('--ledger',type=Path); s.add_argument('--cycle')
        if name == 'answer':
            s.add_argument('--request-id',required=True); s.add_argument('--response-file',type=Path,required=True)
        if name in ('wait','result'): s.add_argument('--id',required=True)
        if name in ('wait','result','events'): s.add_argument('--full',action='store_true')
        if name == 'wait': s.add_argument('--timeout',type=int,default=30)
        if name == 'events': s.add_argument('--after',type=int,default=0); s.add_argument('--limit',type=int,default=50)
    return p


def dispatch(a):
    if a.command == 'doctor': return doctor(a.backend)
    require(sys.version_info >= (3,11) and os.name == 'posix','runtime needs Python 3.11+ and macOS/Linux/WSL')
    wid = identifier(a.worker); workspace = workspace_path(a.workspace); root = workspace/'.dryforge/mission/runtime'
    if a.command == '__serve': raise SystemExit(asyncio.run(serve(root,wid,a.basis)))
    if a.command != 'start': require((root/'mailbox.sqlite3').is_file(),'start a worker first')
    store = Store(root)
    try:
        if a.command == 'start':
            require(doctor(a.backend)['ready_to_attempt'],'backend unavailable; run doctor; no install was attempted')
            for k in ('turn_seconds','lifetime_seconds','startup_seconds','max_messages','max_model_turns'):
                require(0 < getattr(a,k) <= 86400,'invalid finite limit: '+k)
            require(a.budget_usd is None or 0 < a.budget_usd < 10000,'invalid USD limit')
            require(a.backend != 'codex' or a.budget_usd is None,'Codex adapter cannot enforce a USD limit')
            config = {k:getattr(a,k) for k in ('backend','model','handoff_ref','turn_seconds','startup_seconds','max_messages','max_model_turns','budget_usd')}
            config.update(workspace=str(workspace),runtime_root=str(root),worker=wid,
                          skills_root=str(SCRIPTS.parent.parent),deadline=time.time()+a.lifetime_seconds,settings=a.load_settings)
            store.create(wid,config); return launch(store,wid)
        if a.command == 'resume':
            require(a.reconciled and a.basis,'--reconciled and --basis are required')
            w = store.worker(wid); require(w['session_id'],'no host ID to resume')
            require(time.time() < w['config']['deadline'],'original lifetime budget exhausted')
            return launch(store,wid,a.basis)
        if a.command == 'stop':
            store.stop(wid); return {'stop_requested':True,'note':'Wait for STOPPED/ERROR; audit children separately.'}
        if a.command == 'status': return status(store,wid)
        if a.command == 'send':
            w = store.worker(wid); text = a.text_file.read_text(encoding='utf-8')
            if store.db.execute('SELECT 1 FROM messages WHERE worker=? AND id=?',(wid,a.id)).fetchone():
                m = store.message(wid,a.id); b = m['body']; ref = b.get('binding',{})
                require(b['kind'] == a.kind and b['text'] == text,'message ID reused with different content')
                require(ref.get('cycle_id') == a.cycle and ref.get('ledger') == (str(a.ledger.resolve()) if a.ledger else None),'message ID reused for another cycle')
            else:
                m = store.enqueue(wid,a.id,prepare(w['config'],w['session_id'],a.kind,text,a.ledger,a.cycle))
            return {'id':a.id,'state':m['state'],'session_id':m['body']['session_id']}
        if a.command == 'answer':
            r = json.loads(a.response_file.read_text(encoding='utf-8'))
            check_answer(store,wid,a.request_id,r); store.answer(wid,a.request_id,r)
            return {'request_id':a.request_id,'stored':True,'note':'An answer receipt is not cycle completion.'}
        if a.command == 'events':
            events = store.events(wid,a.after,a.limit); cursor = events[-1]['seq'] if events else a.after
            if not a.full: events = [{k:e[k] for k in ('seq','worker','time','kind')} for e in events]
            return {'events':events,'next_cursor':cursor,'full_payloads':a.full}
        if a.command == 'result': return message_view(store.message(wid,a.id),a.full)
        if a.command == 'wait':
            require(0 < a.timeout <= 300,'wait timeout must be 1-300 seconds'); end = time.monotonic()+a.timeout
            while True:
                m,w = store.message(wid,a.id),status(store,wid)
                if m['state'] not in ('QUEUED','DISPATCHED') or w['pending'] or w['state'] in ('UNREACHABLE','STOPPED','ERROR'):
                    return {'message':message_view(m,a.full),'worker':w}
                if time.monotonic() >= end: return {'wait_timed_out':True,'message':message_view(m,a.full),'worker':w}
                time.sleep(.2)
        raise BridgeError('unknown command')
    finally: store.close()


def main():
    os.umask(0o077)
    try:
        print(json.dumps(dispatch(parser().parse_args()),ensure_ascii=False,indent=2)); return 0
    except (BridgeError,ValueError,KeyError,OSError,TypeError) as exc:
        print(json.dumps({'status':'BLOCKED','error':str(exc)},ensure_ascii=False),file=sys.stderr); return 2


if __name__ == '__main__': raise SystemExit(main())
