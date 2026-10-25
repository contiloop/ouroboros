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
    require(state.get('schema_version') in (1,2,3,4,5),'unsupported ledger schema')
    require(state['status'] == 'ACTIVE','execution requires ACTIVE state; approve the draft or reconcile the existing run')
    require(Path(state['contract']['workspace']).resolve() == workspace,'ledger workspace mismatch')
    c = state.get('cycle')
    require(c and c['id'] == cycle and c['session_id'] == sid,'wrong cycle or L2 session')
    return p,state,c


def binding(config,sid,path,cycle,kind):
    import mission_state
    p,state,c = ledger_state(config,sid,path,cycle)
    b = {'ledger':str(p),'cycle_id':cycle,'mission_id':state['contract']['mission_id'],
         'intent_digest':digest(state['contract'])}
    if kind == 'migration':
        require(c.get('kind') == 'migration' and c['stage'] in ('MIGRATION','MIGRATION_REVIEW'),
                'not an assigned migration')
        require('migration' in state['contract']['delegated_actions'] and
                'migration' not in state['contract']['human_only'], 'migration not delegated')
    if kind == 'ready': require(c['stage'] in ('READY','READY_REVIEW','APPROVED'),'not a ready phase')
    if kind == 'go':
        require(c['stage'] == 'APPROVED' and not c['pending'],'go needs explicit ready approval and resolved questions')
        d = mission_state.document_digest(Path(config['workspace'])/'.dryforge')
        require(d == c['digest'] == c['approved_digest'],'documents changed since approval')
        b['docs_digest'] = d
        a = state.get('runtime_authority') or {}
        if (a.get('policy') or {}).get('version') == 4:
            from runtime_cycle import validate_binding
            validate_binding(Path(config['workspace']), a['policy'], c)
            require(c['runtime_binding']['policy_digest'] == digest(a), 'cycle binding uses a stale runtime grant')
            b['runtime_binding_digest'] = digest(c['runtime_binding'])
    return b


def prepare(config,sid,kind,text,ledger=None,cycle=None):
    require(kind in ('probe','ready','go','migration','message'),'unknown input kind')
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
    if kind == 'message':
        return body['text'], None
    # L1 selects a skill; the host loads it using its native invocation mechanism.
    # Never paste bundled procedure text or substitute an Ouroboros copy.
    return body['text'], {'name':'dryforge:'+kind}


def check_answer(store,wid,rid,response):
    """Validate L1 authority at record time AND immediately before host consumption."""
    if response.get('principal') != 'L1' or response.get('action') == 'deny': return None
    raw = store.db.execute('SELECT * FROM requests WHERE worker=? AND id=?',(wid,rid)).fetchone()
    require(raw is not None,'unknown decision request')
    req = dict(raw,body=json.loads(raw['body']))
    if req['state'] == 'CONSUMED': return None  # Store checks exact replay; no host execution.
    require(req['message_id'],'unbound/probe requests require a human')
    message = store.message(wid,req['message_id'])
    require(message['state'] == 'DISPATCHED','request has no live dispatched turn')
    body = message['body']; b = body.get('binding')
    require(b,'probe requests require a human')
    w = store.worker(wid); config = w['config']
    require(not w['stop'] and w['owner'] == req['owner'] and
            w['session_id'] == req['session_id'] == body['session_id'],'stale request owner/session')
    _,s,c = ledger_state(config,body['session_id'],b['ledger'],b['cycle_id'])
    require(digest(s['contract']) == b['intent_digest'],'intent changed while answering')
    if req['kind'] == 'question':
        require('answer' in s['contract']['delegated_actions'] and 'answer' not in s['contract']['human_only'],
                'answer not delegated')
        return None
    require(response.get('action') == 'allow','not a delegated permission allow')
    import runtime_permissions as policy_api
    try:
        authority = s.get('runtime_authority')
        policy_api.require(isinstance(authority,dict) and authority.get('policy') is not None,
                           'no human-approved runtime policy; ask the human')
        policy_api.require(authority.get('approved_by') == 'human' and bool(authority.get('approval_ref')) and
                           authority.get('mission_id') == b['mission_id'] and
                           Path(authority.get('workspace','')).resolve() == Path(config['workspace']),
                           'runtime policy identity/workspace mismatch')
        policy_api.require(response.get('policy_digest') == policy_api.fingerprint(authority),
                           'runtime policy changed or was not explicitly selected')
        policy_api.require('runtime_permissions' not in s['contract']['human_only'], 'runtime permissions are human-only')
        import mission_state
        if authority['policy']['version'] == 4 and c.get('kind') != 'migration':
            policy_api.require((c.get('runtime_binding') or {}).get('policy_digest') == policy_api.fingerprint(authority),
                               'cycle binding uses a stale runtime grant')
        match = policy_api.classify(req['body'],config['workspace'],authority['policy'],cycle=c)
        if c.get('kind') == 'migration':
            from migration_artifacts import documentation_path
            policy_api.require('migration' in s['contract']['delegated_actions'] and
                               'migration' not in s['contract']['human_only'], 'migration not delegated')
            policy_api.require(not c['pending'], 'resolve pending migration decisions first')
            policy_api.require(match.get('worktree') is None, 'migration uses the base workspace')
            if c['stage'] in ('MIGRATION','MIGRATION_REVIEW'):
                policy_api.require(match['operation'] == 'workspace_edit', 'migration only delegates documentation edits')
                current_digest = None  # Approved intent governs preparation; no Ready documents exist yet.
            else:
                policy_api.require(c['stage'] == 'ACCEPTED' and match['operation'] in ('git_add','git_commit'),
                                   'only explicit harness checkpointing follows migration acceptance')
                current_digest = mission_state.migration_digest(Path(config['workspace']),c['result']['paths'])
                policy_api.require(current_digest == c['approved_digest'], 'accepted migration artifacts changed')
                policy_api.require(set(match['paths']) <= set(c['result']['paths']), 'checkpoint includes unreviewed files')
            policy_api.require(all(documentation_path(p) for p in match['paths']), 'outside migration documentation')
        else:
            policy_api.require(c['stage'] in ('GO','ACCEPTED') and not c['pending'],
                               'delegated mutations require Go or accepted cleanup with no pending decision')
            if c['stage'] == 'ACCEPTED':
                policy_api.require(match['operation'] in ('git_checkout','git_merge','git_worktree_remove',
                                                         'git_branch_delete','verify'),
                                   'accepted results allow cleanup/integration/verification, not implementation')
            from runtime_cycle import approved_documents
            current_digest = approved_documents(Path(config['workspace']), c)
            policy_api.require(current_digest == c['digest'] == c['approved_digest'], 'approved documents changed')
        policy_api.require(match['operation'] not in s['contract']['human_only'] and
                           not (match['operation'] == 'git_merge' and
                                'merge' in s['contract']['human_only']),
                           'operation is human-only')
        return dict(match, policy_digest=policy_api.fingerprint(authority),
                    approval_ref=authority['approval_ref'], policy_event=authority['event_id'],
                    mission_id=b['mission_id'], cycle_id=c['id'], intent_digest=b['intent_digest'],
                    docs_digest=current_digest, stage=c['stage'],
                    runtime_binding_digest=digest(c.get('runtime_binding')),
                    decision_digest=digest(c.get('decisions')),
                    result_digest=digest(c.get('result')))
    except (policy_api.PolicyError, OSError, ValueError) as exc:
        raise BridgeError(str(exc)) from exc


def delegation_for(store,wid,request):
    """Read-only eligibility hint for L1; never an automatic approval."""
    if request['kind'] != 'permission': return None
    try:
        msg = store.message(wid,request['message_id'])['body']; b = msg.get('binding')
        require(b,'unbound/probe requests require a human')
        _,s,_ = ledger_state(store.worker(wid)['config'],msg['session_id'],b['ledger'],b['cycle_id'])
        response = {'principal':'L1','action':'allow','policy_digest':digest(s.get('runtime_authority'))}
        return dict(eligible=True,**check_answer(store,wid,request['id'],response))
    except (BridgeError,ValueError,KeyError,OSError,TypeError) as exc:
        return {'eligible':False,'reason':str(exc)}


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
            origin = current
            rid = store.request(wid,owner,origin['id'] if origin else None,kind,payload)
            try:
                while True:
                    try:
                        response = store.take_answer(wid,owner,rid)
                    except BridgeError as exc:
                        # A revoked/stale delegated grant never reaches the host as accept.
                        store.event(wid,'request.authorization_rejected',{'id':rid,'reason':str(exc)})
                        return {'action':'deny','principal':'L1','basis':'Authorization no longer valid: '+str(exc)}
                    if response is not None:
                        if origin and origin['body'].get('binding'):
                            b = origin['body']['binding']
                            _,s,_ = ledger_state(config,origin['body']['session_id'],b['ledger'],b['cycle_id'])
                            require(digest(s['contract']) == b['intent_digest'],'mission changed during callback')
                            # Store.take_answer rechecks L1 authority against the live policy and artifacts.
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
                    if skill:
                        async with asyncio.timeout(max(.01,min(30,config['deadline']-time.time()))):
                            skill = await adapter.resolve_skill(skill['name'])
                    if body['kind'] == 'go': mark_go(config,body,current['id'])
                except (ValueError,KeyError,OSError) as exc:
                    store.finish(wid,owner,current['id'],{'error':str(exc)},'REJECTED')
                    current = None; continue
                async with asyncio.timeout(max(.01,min(config['turn_seconds'],config['deadline']-time.time()))):
                    result = await adapter.run(prompt,skill=skill,probe=body['kind'] == 'probe')
                    # A parent turn may end while an L3 callback remains live.
                    # Preserve message ownership until the host consumes all
                    # outstanding decisions; never extend the original budget.
                    outstanding = store.unresolved(wid,current['id'])
                    if outstanding:
                        store.event(wid,'turn.awaiting_child_callbacks',
                                    {'message_id':current['id'],'count':len(outstanding)})
                    while store.unresolved(wid,current['id']):
                        await asyncio.sleep(.15)
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
