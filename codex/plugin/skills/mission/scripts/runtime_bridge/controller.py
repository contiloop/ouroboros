"""Bounded single-worker runtime, existing ledger gates and exact-session question relay."""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
import signal
import time
import uuid
from .adapters import ClaudeAdapter, CodexAdapter
from .store import BridgeError, Store, controller_lock, digest, require


def ledger_state(config, sid, path, cycle):
    p = Path(path).resolve()
    workspace = Path(config['workspace'])
    require(p.is_relative_to(workspace/'.dryforge/mission'),'ledger belongs outside this workspace')
    state = json.loads(p.read_text(encoding='utf-8'))
    require(state.get('schema_version') in (1,2),'unsupported ledger schema')
    require(state['status'] == 'ACTIVE','mission is paused or complete')
    require(Path(state['contract']['workspace']).resolve() == workspace,'ledger workspace mismatch')
    c = state.get('cycle')
    require(c and c['id'] == cycle and c['session_id'] == sid,'wrong cycle or L2 session')
    return p,state,c


def binding(config,sid,path,cycle,kind):
    import mission_state
    p,state,c = ledger_state(config,sid,path,cycle)
    b = {'ledger':str(p),'cycle_id':cycle,'mission_id':state['contract']['mission_id'],
         'intent_digest':digest(state['contract'])}
    if kind == 'ready': require(c['stage'] in ('READY','READY_REVIEW','APPROVED'),'not a ready phase')
    if kind == 'go':
        require(c['stage'] == 'APPROVED' and not c['pending'],'go needs explicit ready approval and resolved questions')
        d = mission_state.document_digest(Path(config['workspace'])/'.dryforge')
        require(d == c['digest'] == c['approved_digest'],'documents changed since approval')
        b['docs_digest'] = d
    return b


def prepare(config,sid,kind,text,ledger=None,cycle=None):
    require(kind in ('probe','ready','go','message'),'unknown input kind')
    require(isinstance(text,str) and bool(text.strip()),'nonempty text required')
    body = {'kind':kind,'text':text,'session_id':sid}
    if kind != 'probe':
        require(ledger and cycle,'cycle work needs its mission ledger and cycle ID')
        body['binding'] = binding(config,sid,ledger,cycle,kind)
    return body


def validate_dispatch(config,body):
    b = body.get('binding')
    if b:
        require(binding(config,body['session_id'],b['ledger'],b['cycle_id'],body['kind']) == b,'queued input has stale intent or approval')


def mark_go(config,body,message_id):
    """Record execution start of this explicit approved command, never create an approval."""
    import mission_state
    b = body['binding']
    _,s,_ = ledger_state(config,body['session_id'],b['ledger'],b['cycle_id'])
    validate_dispatch(config,body)
    event = {'id':'runtime-go-'+message_id, 'op':'go','actor':'L2',
             'mission_id':b['mission_id'],'cycle_id':b['cycle_id'],'session_id':body['session_id'],
             'expected_revision':s['revision'],'digest':b['docs_digest']}
    mission_state.save_event(Path(b['ledger']),event)


def prompt_for(config,body):
    kind = body['kind']
    if kind == 'probe':
        return ('Read-only capability probe, not mission work. Do not implement, install or approve anything. '
                'Report only observed host behavior.\n'+body['text'],None)
    b = body['binding']; root = Path(config['skills_root'])
    prompt = (f'Authorized cycle dispatch. Actual host session: {body["session_id"]}.\n'
              f'Mission: {b["mission_id"]}; cycle: {b["cycle_id"]}; ledger: {b["ledger"]}.\n'
              f'Workspace: {config["workspace"]}.\n'
              f'Read the original approved intent/decisions and {root/"mission/references/cycle-contract.md"}.\n'
              'Do not invent human approval. Do not write runtime/mission approval records yourself.\n'
              'Ask clarifying questions through the available host tool or yield them in your response. '
              'The caller will answer in this same session. A prose answer is not go approval.\n')
    skill = None
    if kind in ('ready','go'):
        entry = root/kind/'SKILL.md'; workflow = root/kind/'references/workflow.md'
        require(entry.is_file() and workflow.is_file(),'authorized procedure files missing')
        prompt += (f'Execute the full authorized {kind} procedure below, including required references. '
                   f'Relative paths resolve from {entry.parent}, not the current working directory. '
                   'Procedure loading is not proof of a native slash-command invocation.\n\n'
                   +entry.read_text()+'\n\n'+workflow.read_text()+'\n')
        skill = {'name':kind,'path':str(entry)}
        if kind == 'ready': prompt += '\nStop at READY_REVIEW; return document paths and digest. Do not run go in this turn.\n'
        else: prompt += f'Check document digest {b["docs_digest"]} before implementing. The controller recorded execution start, not completion.\n'
    else:
        prompt += '\nContinue only the current phase. Do not start go or another cycle from this message.\n'
    return prompt+'\nCaller input:\n'+body['text'],skill


def check_answer(store,wid,rid,response):
    if response.get('principal') != 'L1' or response.get('action') == 'deny': return
    req = next((r for r in store.pending(wid) if r['id'] == rid),None)
    if not req: return  # Store.answer validates exact terminal retries.
    require(req['kind'] == 'question' and req['message_id'],'L1 may not grant runtime permissions')
    body = store.message(wid,req['message_id'])['body']; b = body.get('binding')
    require(b,'probe questions require a human answer')
    config = store.worker(wid)['config']
    _,s,_ = ledger_state(config,body['session_id'],b['ledger'],b['cycle_id'])
    require(digest(s['contract']) == b['intent_digest'],'intent changed while answering')
    require('answer' in s['contract']['delegated_actions'] and 'answer' not in s['contract']['human_only'],'answer not delegated')


async def serve(root,wid,basis=None,adapter_factory=None):
    with controller_lock(root):
        store = Store(root); owner = uuid.uuid4().hex
        store.attach(wid,owner,basis)
        config = store.worker(wid)['config']
        adapter = None; pulse = None; current = None; error = None
        main = asyncio.current_task(); loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM,signal.SIGINT): loop.add_signal_handler(sig,store.stop,wid)

        def emit(kind,data):
            store.event(wid,kind,{'message_id':current['id'] if current else None,'data':data})

        def bind(sid): store.bind(wid,owner,sid)

        async def relay(kind,payload):
            rid = store.request(wid,owner,current['id'] if current else None,kind,payload)
            try:
                while True:
                    row = next((x for x in store.pending(wid) if x['id'] == rid),None)
                    response = store.take_answer(wid,owner,rid)
                    if response is not None:
                        if current and current['body'].get('binding'):
                            b = current['body']['binding']
                            _,s,_ = ledger_state(config,current['body']['session_id'],b['ledger'],b['cycle_id'])
                            require(digest(s['contract']) == b['intent_digest'],'mission changed during callback')
                            if response['principal'] == 'L1' and response['action'] != 'deny':
                                require(kind == 'question' and 'answer' in s['contract']['delegated_actions'] and
                                        'answer' not in s['contract']['human_only'],'answer delegation changed')
                        return response
                    await asyncio.sleep(.15)
            finally:
                store.db.execute("UPDATE requests SET state='EXPIRED' WHERE id=? AND state IN ('PENDING','ANSWERED')",(rid,))

        async def heartbeat():
            while True:
                store.heartbeat(wid,owner)
                if store.worker(wid)['stop']:
                    main.cancel(); return
                await asyncio.sleep(.2)

        try:
            pulse = asyncio.create_task(heartbeat())
            require(time.time() < config['deadline'],'worker lifetime budget exhausted')
            factory = adapter_factory or (ClaudeAdapter if config['backend'] == 'claude' else CodexAdapter)
            adapter = factory(config,store.worker(wid)['session_id'],emit,bind,relay)
            async with asyncio.timeout(min(config['startup_seconds'],config['deadline']-time.time())):
                await adapter.connect()
            require(store.worker(wid)['session_id'],'host never supplied a session identity')
            store.state(wid,owner,'IDLE')
            while time.time() < config['deadline']:
                n = store.db.execute("SELECT COUNT(*) FROM messages WHERE worker=? AND state IN ('DISPATCHED','TURN_COMPLETE','TURN_FAILED','UNCERTAIN')",(wid,)).fetchone()[0]
                if n >= config['max_messages']:
                    error = 'worker message budget exhausted'; break
                current = store.claim(wid,owner)
                if not current:
                    await asyncio.sleep(.15); continue
                body = current['body']
                require(body['session_id'] == store.worker(wid)['session_id'],'dispatch session mismatch')
                try:
                    validate_dispatch(config,body)
                    prompt,skill = prompt_for(config,body)
                    if body['kind'] == 'go': mark_go(config,body,current['id'])
                except (ValueError,KeyError,OSError) as exc:
                    store.finish(wid,owner,current['id'],{'error':str(exc)},'REJECTED')
                    current = None; continue
                async with asyncio.timeout(max(.01,min(config['turn_seconds'],config['deadline']-time.time()))):
                    result = await adapter.run(prompt,skill=skill,probe=body['kind'] == 'probe')
                require(result.get('session_id') == body['session_id'],'result from a different session')
                store.finish(wid,owner,current['id'],result,'TURN_COMPLETE' if result['ok'] else 'TURN_FAILED')
                current = None
            else: error = 'worker lifetime budget exhausted'
        except asyncio.CancelledError:
            error = 'stopped with in-flight work; reconcile effects' if current else None
        except Exception as exc:
            error = type(exc).__name__+': '+str(exc)
        finally:
            if pulse:
                pulse.cancel(); await asyncio.gather(pulse,return_exceptions=True)
            if adapter:
                try:
                    async with asyncio.timeout(10): await adapter.close()
                except BaseException as exc:
                    error = error or 'host shutdown not confirmed: '+type(exc).__name__
            store.detach(wid,owner,error); store.close()
            for sig in (signal.SIGTERM,signal.SIGINT): loop.remove_signal_handler(sig)
        return 2 if error else 0
