"""Durable transport tests. Protocol fixtures and SDK doubles are NOT live agent E2E."""
import asyncio
import dataclasses
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'src/skills/mission/scripts'
sys.dont_write_bytecode=True
sys.path.insert(0,str(SCRIPTS))
from runtime_bridge.store import Store,BridgeError,controller_lock,digest
from runtime_bridge.controller import prepare,validate_dispatch,prompt_for,mark_go,serve
from runtime_bridge.adapters import ClaudeAdapter,CodexAdapter,observable
import worker_runtime as cli
import mission_state


def config(root,**kw):
    c=dict(backend='codex',workspace=str(root),runtime_root=str(root/'.dryforge/mission/runtime'),
           skills_root=str(SCRIPTS.parent.parent),worker='w',settings=[],deadline=time.time()+120,
           turn_seconds=10,startup_seconds=5,max_messages=20,max_model_turns=20)
    c.update(kw);return c


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.s=Store(self.root/'runtime');self.c=config(self.root)
        self.s.create('w',self.c);self.s.attach('w','owner');self.s.bind('w','owner','sid');self.s.state('w','owner','IDLE')
        self.body={'kind':'probe','text':'hello','session_id':'sid'}
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def queue(self):return self.s.enqueue('w','m',self.body)
    def test_idempotent_send(self):
        self.queue();self.queue();self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM messages').fetchone()[0],1)
    def test_changed_content_same_id_rejected(self):
        self.queue()
        with self.assertRaises(BridgeError):self.s.enqueue('w','m',dict(self.body,text='other'))
    def test_wrong_session_rejected(self):
        with self.assertRaises(BridgeError):self.s.enqueue('w','m',dict(self.body,session_id='other'))
    def test_claim_is_serial(self):
        self.queue();self.s.claim('w','owner')
        with self.assertRaises(BridgeError):self.s.claim('w','owner')
    def test_wrong_owner_rejected(self):
        self.queue();self.s.claim('w','owner')
        with self.assertRaises(BridgeError):self.s.finish('w','other','m',{})
    def test_done_retry_does_not_execute(self):
        self.queue();self.s.claim('w','owner');self.s.finish('w','owner','m',{'ok':True})
        self.assertEqual(self.queue()['state'],'TURN_COMPLETE');self.assertIsNone(self.s.claim('w','owner'))
    def test_bind_cannot_replace_identity(self):
        with self.assertRaises(BridgeError):self.s.bind('w','owner','different')
    def test_crash_reconcile_never_replays_inflight(self):
        self.queue();self.s.claim('w','owner');self.s.attach('w','new','fixture reconciled')
        self.assertEqual(self.s.message('w','m')['state'],'UNCERTAIN');self.assertIsNone(self.s.claim('w','new'))
    def test_recovery_requires_basis(self):
        with self.assertRaises(BridgeError):self.s.attach('w','new')
    def request(self,kind='permission'):
        rid=self.s.request('w','owner',None,kind,{'tool':'example'})
        r=self.s.pending('w')[0]
        return rid,dict(principal='human',basis='fixture ONLY',session_id='sid',request_digest=r['fingerprint'],action='allow')
    def test_request_is_persisted_before_answer(self):
        rid,r=self.request();self.assertEqual(self.s.pending('w')[0]['id'],rid)
    def test_l1_cannot_allow_permission(self):
        rid,r=self.request();r['principal']='L1'
        with self.assertRaises(BridgeError):self.s.answer('w',rid,r)
    def test_answer_bound_to_request(self):
        rid,r=self.request();r['request_digest']='wrong'
        with self.assertRaises(BridgeError):self.s.answer('w',rid,r)
    def test_answer_bound_to_session(self):
        rid,r=self.request();r['session_id']='wrong'
        with self.assertRaises(BridgeError):self.s.answer('w',rid,r)
    def test_answer_once_and_exact_retries(self):
        rid,r=self.request();self.s.answer('w',rid,r);self.s.answer('w',rid,r)
        self.assertEqual(self.s.take_answer('w','owner',rid),r)
        self.s.answer('w',rid,r)
        with self.assertRaises(BridgeError):self.s.take_answer('w','owner',rid)
    def test_answer_cannot_change(self):
        rid,r=self.request();self.s.answer('w',rid,r)
        with self.assertRaises(BridgeError):self.s.answer('w',rid,dict(r,action='deny'))
    def test_stale_callback_expires(self):
        rid,r=self.request();self.s.attach('w','new','fixture recovered')
        with self.assertRaises(BridgeError):self.s.answer('w',rid,r)
    def test_stop_cancels_queued(self):
        self.queue();self.s.stop('w');self.s.detach('w','owner')
        self.assertEqual(self.s.message('w','m')['state'],'CANCELLED')
    def test_two_controller_locks_rejected(self):
        with controller_lock(self.s.root):
            with self.assertRaises(BridgeError):
                with controller_lock(self.s.root):pass
    def test_fresh_worker_needs_handoff(self):
        self.s.detach('w','owner')
        with self.assertRaises(BridgeError):self.s.create('w2',self.c)
        self.s.create('w2',dict(self.c,handoff_ref='fixture stopped children'))
    def test_private_database_permissions(self):
        self.assertEqual(self.s.root.stat().st_mode&0o777,0o700);self.assertEqual(self.s.path.stat().st_mode&0o777,0o600)
    def test_symlink_database_rejected(self):
        p=self.root/'bad';p.mkdir();(p/'mailbox.sqlite3').symlink_to(self.s.path)
        with self.assertRaises(BridgeError):Store(p)
    def test_large_event_stored_as_artifact(self):
        self.s.event('w','big',{'data':'x'*140000});r=self.s.events('w')[-1]['body']
        self.assertEqual(Path(r['artifact']).stat().st_size,r['bytes'])


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.c=config(self.root)
        self.docs=self.root/'.dryforge';self.docs.mkdir()
        for n in ('spec.md','plan.md','handoff.md'):(self.docs/n).write_text(n)
        self.ledger=self.docs/'mission/state.json';self.ledger.parent.mkdir()
        contract=dict(mission_id='fixture',goal='fixture',workspace=str(self.root),success_criteria=['fixture'],
          constraints=[],human_only=[],delegated_actions=['answer','approve_ready'],max_cycles=2,max_stalled_cycles=2,
          approved_by='human',approval_ref='fixture-NOT-REAL-APPROVAL')
        self.state=mission_state.init_state(contract)
        d=mission_state.document_digest(self.docs)
        self.state['cycle']=dict(id='c1',session_id='sid',stage='APPROVED',pending={},digest=d,approved_digest=d)
        self.save()
    def tearDown(self):self.tmp.cleanup()
    def save(self):self.ledger.write_text(json.dumps(self.state))
    def body(self,kind='go'):return prepare(self.c,'sid',kind,'fixture',self.ledger,'c1')
    def test_approved_go_binds_docs(self):validate_dispatch(self.c,self.body())
    def test_go_before_approval_denied(self):
        self.state['cycle']['stage']='READY';self.save()
        with self.assertRaises(BridgeError):self.body()
    def test_queued_go_rechecks_changed_docs(self):
        body=self.body();(self.docs/'spec.md').write_text('changed')
        with self.assertRaises(BridgeError):validate_dispatch(self.c,body)
    def test_queued_ready_rechecks_intent(self):
        body=self.body('ready');self.state['contract']['goal']='other';self.save()
        with self.assertRaises(BridgeError):validate_dispatch(self.c,body)
    def test_other_session_not_approved(self):
        with self.assertRaises(BridgeError):prepare(self.c,'other','go','x',self.ledger,'c1')
    def test_pending_question_blocks_go(self):
        self.state['cycle']['pending']={'q':{}};self.save()
        with self.assertRaises(BridgeError):self.body()
    def test_paused_mission_blocks_work(self):
        self.state['status']='PAUSED';self.save()
        with self.assertRaises(BridgeError):self.body('message')
    def test_full_workflow_loaded_not_summarized(self):
        p,skill=prompt_for(self.c,self.body())
        self.assertIn((SCRIPTS.parent.parent/'go/references/workflow.md').read_text(),p)
        self.assertEqual(skill['name'],'go')
    def test_worker_prompt_does_not_expose_decision_provider(self):
        from runtime_bridge.adapters import ROLE
        prompt, _ = prompt_for(self.c,self.body())
        for private in ('You are L2', 'L1', 'Decision provider', str(self.ledger), 'Mission: fixture'):
            self.assertNotIn(private, ROLE + prompt)
        self.assertNotIn('cycle-contract.md', prompt)
    def test_message_never_grants_go(self):
        p,skill=prompt_for(self.c,self.body('message'));self.assertIsNone(skill);self.assertIn('Do not start go',p)
    def test_explicit_go_records_start_not_success(self):
        mark_go(self.c,self.body(),'m1');s=json.loads(self.ledger.read_text())
        self.assertEqual(s['cycle']['stage'],'GO');self.assertEqual(s['status'],'ACTIVE')
    def test_started_go_cannot_be_newly_replayed(self):
        b=self.body();mark_go(self.c,b,'m1')
        with self.assertRaises(BridgeError):mark_go(self.c,b,'m2')


class CodexTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.c=config(self.root)
        Path(self.c['runtime_root']).mkdir(parents=True);self.events=[];self.ids=[];self.replies=[]
        self.env=patch.dict(os.environ,{'OUROBOROS_FIXTURE_STATE':str(self.root/'host.json')});self.env.start()
        async def relay(kind,payload):
            self.replies.append((kind,payload));return {'action':'answer' if kind == 'question' else 'allow','answers':{'q1':'A'}}
        self.relay=relay;self.a=self.make();await self.a.connect()
    def make(self,sid=None):return CodexAdapter(self.c,sid,lambda k,d:self.events.append((k,d)),self.ids.append,self.relay,
                 command=[sys.executable,'-B',str(ROOT/'ci/fixtures/fake_app_server.py')])
    async def asyncTearDown(self):await self.a.close();self.env.stop();self.tmp.cleanup()
    async def test_two_turns_same_host_thread(self):
        a=await self.a.run('first');b=await self.a.run('second')
        self.assertEqual(a['session_id'],b['session_id']);self.assertNotEqual(a['turn_id'],b['turn_id'])
    async def test_permission_request_is_correlated(self):
        self.assertTrue((await self.a.run('FIXTURE_PERMISSION'))['ok'])
        self.assertEqual(self.replies[0][1]['params']['threadId'],self.a.sid)
    async def test_structured_question_uses_the_ordinary_question_interface(self):
        self.assertTrue((await self.a.run('FIXTURE_QUESTION'))['ok']);self.assertEqual(self.replies[0][0],'question')
    async def test_parent_result_waits_for_live_child_callback(self):
        entered, answer = asyncio.Event(), asyncio.Event()
        async def delayed(kind, payload):
            entered.set()
            await answer.wait()
            return {'principal':'L1','action':'allow','basis':'fixture'}
        self.a.relay = delayed
        task = asyncio.create_task(self.a.run('FIXTURE_CHILD_AFTER_PARENT'))
        try:
            await asyncio.wait_for(entered.wait(), 3)
            await asyncio.sleep(.05)
            self.assertFalse(task.done(), 'parent completion must not settle live child work')
            self.assertEqual(json.loads((self.root/'host.json').read_text())['turns'][0]['status'],'completed')
            answer.set()
            result = await asyncio.wait_for(task, 5)
            self.assertTrue(result['ok'])
            response = json.loads((self.root/'host.json').read_text())['child_response']['result']
            self.assertEqual(response, {'decision':'accept'})
        finally:
            answer.set()
            if not task.done(): task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async def test_missing_notice_recovered_from_state(self):
        self.assertTrue((await asyncio.wait_for(self.a.run('FIXTURE_DROP_NOTICE'),5))['ok'])
    async def test_disconnect_not_success_or_replayed(self):
        with self.assertRaises(BridgeError):await self.a.run('FIXTURE_DISCONNECT')
        self.assertEqual(len(json.loads((self.root/'host.json').read_text())['turns']),1)
    async def test_failed_turn(self):self.assertFalse((await self.a.run('FIXTURE_FAILURE'))['ok'])
    async def test_resume_same_id(self):
        first=await self.a.run('first');await self.a.close();self.a=self.make(first['session_id']);await self.a.connect()
        self.assertEqual((await self.a.run('second'))['session_id'],first['session_id'])
    async def test_replaced_host_thread_rejected(self):
        sid=self.a.sid;await self.a.close();self.a=self.make(sid)
        with patch.dict(os.environ,{'FIXTURE_WRONG_ID':'1'}):
            with self.assertRaises(BridgeError):await self.a.connect()
    async def test_unrelated_request_rejected(self):
        with self.assertRaises(BridgeError):await self.a.request({'id':'x','method':'item/fileChange/requestApproval','params':{'threadId':'other'}})
        self.assertEqual(self.replies,[])


@dataclasses.dataclass
class FakeSystem:
    subtype:str
    data:dict
@dataclasses.dataclass
class FakeResult:
    session_id:str='fixture-claude'
    subtype:str='success'
    is_error:bool=False
    result:str='fixture response'
    usage:dict=dataclasses.field(default_factory=dict)
    total_cost_usd:float=0.0
class FakeClient:
    def __init__(self,options):self.options=options;self.inputs=[]
    async def connect(self):pass
    async def query(self,text):self.inputs.append(text)
    async def receive_response(self):
        yield FakeSystem('init',{'session_id':'fixture-claude'})
        yield FakeResult()
    async def disconnect(self):pass


class ClaudeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.ids=[]
        sdk=types.SimpleNamespace(ClaudeAgentOptions=lambda **k:types.SimpleNamespace(**k),ClaudeSDKClient=FakeClient,
            SystemMessage=FakeSystem,ResultMessage=FakeResult,HookMatcher=lambda **k:k,
            PermissionResultAllow=lambda **k:dict(behavior='allow',**k),PermissionResultDeny=lambda **k:dict(behavior='deny',**k))
        self.patch=patch.dict(sys.modules,{'claude_agent_sdk':sdk});self.patch.start()
        async def relay(kind,payload):return {'action':'answer','answers':{'Why?':'Because'},'basis':'fixture'}
        self.a=ClaudeAdapter(config(self.root),None,lambda *x:None,self.ids.append,relay);await self.a.connect()
    async def asyncTearDown(self):await self.a.close();self.patch.stop();self.tmp.cleanup()
    async def test_one_client_same_session_multiple_turns(self):
        client=self.a.client;await self.a.run('ready');await self.a.run('go')
        self.assertIs(client,self.a.client);self.assertEqual(len(client.inputs),3);self.assertEqual(set(self.ids),{'fixture-claude'})
    async def test_no_permission_bypass(self):
        self.assertEqual(self.a.client.options.permission_mode,'default');self.assertFalse(hasattr(self.a.client.options,'allowed_tools'))
    async def test_no_implicit_resume_or_fork(self):
        self.assertFalse(self.a.client.options.fork_session);self.assertFalse(hasattr(self.a.client.options,'continue_conversation'))
    async def test_question_response(self):
        r=await self.a.client.options.can_use_tool('AskUserQuestion',{'questions':[{'question':'Why?'}]},None)
        self.assertEqual(r['updated_input']['answers'],{'Why?':'Because'})
    async def test_fresh_session_rejected(self):
        with self.assertRaises(BridgeError):self.a.identity('other')
    async def test_probe_blocks_writes(self):
        self.a.probe=True;hook=self.a.client.options.hooks['PreToolUse'][0]['hooks'][0]
        r=await hook({'hook_event_name':'PreToolUse','tool_name':'Write'},'t',None)
        self.assertEqual(r['hookSpecificOutput']['permissionDecision'],'deny')
    async def test_observer_never_grants_permissions(self):
        self.a.probe=False;hook=self.a.client.options.hooks['PreToolUse'][0]['hooks'][0]
        self.assertEqual(await hook({'tool_name':'Bash'},'t',None),{'continue_':True})
    async def test_raw_thinking_not_logged(self):
        r=observable({'content':[{'type':'thinking','thinking':'secret','signature':'sig'},{'type':'tool_use','name':'Read'}]})
        self.assertNotIn('secret',json.dumps(r));self.assertIn('Read',json.dumps(r))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.project=self.root/'project';self.project.mkdir()
        subprocess.run(['git','init','-q',str(self.project)],check=True)
        (self.project/'.gitignore').write_text('.dryforge/\n')
        bin=self.root/'bin';bin.mkdir();exe=bin/'codex'
        exe.write_text('#!'+sys.executable+'\nimport os,sys\nos.execv(sys.executable,[sys.executable,"-B",'+repr(str(ROOT/'ci/fixtures/fake_app_server.py'))+'])\n');exe.chmod(0o700)
        self.env={**os.environ,'PATH':str(bin)+os.pathsep+os.environ.get('PATH',''),'OUROBOROS_FIXTURE_STATE':str(self.root/'host.json'),'PYTHONDONTWRITEBYTECODE':'1'}
        self.pids=[]
    def tearDown(self):
        for pid in self.pids:
            try:os.killpg(pid,signal.SIGTERM)
            except ProcessLookupError:pass
        time.sleep(.3);self.tmp.cleanup()
    def call(self,op,*args,ok=True):
        r=subprocess.run([sys.executable,'-B',str(SCRIPTS/'worker_runtime.py'),op,'--workspace',str(self.project),'--worker','w',*args],
                         env=self.env,capture_output=True,text=True,timeout=10)
        if ok:self.assertEqual(r.returncode,0,r.stderr)
        else:self.assertNotEqual(r.returncode,0)
        return json.loads(r.stdout if ok else r.stderr)
    def state(self,want):
        end=time.monotonic()+10
        while time.monotonic()<end:
            s=self.call('status')
            if s['state'] in want:return s
            time.sleep(.1)
        self.fail(str(s))
    def start(self,*args):
        r=self.call('start','--backend','codex',*args);self.pids.append(r['controller_pid']);return self.state({'IDLE'})
    def send(self,mid,text):
        p=self.root/(mid+'.txt');p.write_text(text);return self.call('send','--id',mid,'--kind','probe','--text-file',str(p))
    def test_real_process_lifecycle_resume_same_thread(self):
        a=self.start();self.send('m1','first');r=self.call('wait','--id','m1','--timeout','5');self.assertEqual(r['message']['state'],'TURN_COMPLETE')
        self.call('stop');self.state({'STOPPED'})
        r=self.call('resume','--reconciled','--basis','fixture inspected children and side effects');self.pids.append(r['controller_pid']);self.state({'IDLE'})
        self.send('m2','second');r=self.call('wait','--id','m2','--timeout','5');self.assertEqual(r['message']['session_id'],a['session_id'])
        self.call('stop');self.state({'STOPPED'})
    def test_timeout_uncertain_not_replayed(self):
        self.start('--turn-seconds','1');self.send('m','FIXTURE_HANG');self.state({'ERROR'})
        self.assertEqual(self.call('result','--id','m')['state'],'UNCERTAIN')
        self.assertEqual(len(json.loads((self.root/'host.json').read_text())['turns']),1)
    def test_permission_roundtrip(self):
        s=self.start();self.send('m','FIXTURE_PERMISSION');r=self.state({'WAITING'})['pending'][0]
        answer={'principal':'L1','action':'allow','basis':'fixture','session_id':s['session_id'],'request_digest':r['fingerprint']}
        p=self.root/'answer.json';p.write_text(json.dumps(answer))
        self.call('answer','--request-id',r['id'],'--response-file',str(p),ok=False)
        answer['principal']='human';p.write_text(json.dumps(answer));self.call('answer','--request-id',r['id'],'--response-file',str(p))
        self.assertEqual(self.call('wait','--id','m','--timeout','5')['message']['state'],'TURN_COMPLETE')
        self.call('stop');self.state({'STOPPED'})
    def test_delegated_git_callback_real_cli_roundtrip(self):
        self.delegated_roundtrip('FIXTURE_GIT_ADD')

    def test_completed_parent_keeps_child_delegation_live_through_controller(self):
        self.delegated_roundtrip('FIXTURE_CHILD_AFTER_PARENT')

    def delegated_roundtrip(self, fixture):
        # Real controller/SQLite/CLI, deterministic non-model host; consent is a fixture.
        sid=self.start()['session_id']
        target=self.project/'tests/__init__.py';target.parent.mkdir();target.write_text('')
        docs=self.project/'.dryforge'
        for name in ('spec.md','plan.md','handoff.md'):(docs/name).write_text(name)
        state_path=docs/'mission/state.json'
        contract=dict(mission_id='delegate-fixture',goal='fixture',workspace=str(self.project),
                      success_criteria=['fixture'],constraints=[],human_only=[],delegated_actions=['answer'],
                      max_cycles=2,max_stalled_cycles=2,approved_by='human',approval_ref='FIXTURE-NOT-REAL-CONSENT')
        s=mission_state.init_state(contract);d=mission_state.document_digest(docs)
        s['cycle']=dict(id='c1',session_id=sid,stage='GO',pending={},digest=d,approved_digest=d)
        policy=dict(version=1,operations=['git_add'],paths=['tests'],verification_commands=[],trust_workspace_code=True)
        s=mission_state.apply(s,dict(id='grant',op='runtime_policy',actor='human',mission_id='delegate-fixture',
             cycle_id='c1',expected_revision=0,expected_policy_digest=digest(None),policy=policy,
             approval_ref='FIXTURE-GRANT',basis='fixture local Git delegation'))
        state_path.write_text(json.dumps(s));prompt=self.root/'task.txt';prompt.write_text(fixture)
        self.call('send','--id','delegated','--kind','message','--ledger',str(state_path),'--cycle','c1','--text-file',str(prompt))
        req=self.state({'WAITING'})['pending'][0]
        self.assertTrue(req['delegation']['eligible'])
        if fixture == 'FIXTURE_CHILD_AFTER_PARENT':
            self.assertEqual(json.loads((self.root/'host.json').read_text())['turns'][0]['status'], 'completed')
            self.assertEqual(self.call('result','--id','delegated')['state'], 'DISPATCHED')
        response=dict(principal='L1',action='allow',basis='fixture approved scope',session_id=sid,
                      request_digest=req['fingerprint'],policy_digest=req['delegation']['policy_digest'])
        response_path=self.root/'response.json';response_path.write_text(json.dumps(response))
        self.call('answer','--request-id',req['id'],'--response-file',str(response_path))
        result=self.call('wait','--id','delegated','--timeout','5')['message']
        self.assertEqual(result['state'],'TURN_COMPLETE')
        self.assertEqual(result['session_id'],sid)
        if fixture == 'FIXTURE_GIT_ADD':
            self.assertIn('accept',result['result']['text'])
        else:
            self.assertEqual(json.loads((self.root/'host.json').read_text())['child_response']['result'], {'decision':'accept'})
        events=self.call('events','--full')['events']
        self.assertTrue(any(e['kind']=='request.delegation_checked' and e['body']['phase']=='consume' for e in events))
        self.call('stop');self.state({'STOPPED'})

    def test_cli_idempotent_after_result(self):
        self.start();self.send('m','hello');self.call('wait','--id','m','--timeout','5')
        self.assertEqual(self.send('m','hello')['state'],'TURN_COMPLETE')
        self.assertEqual(len(json.loads((self.root/'host.json').read_text())['turns']),1)
        self.call('stop');self.state({'STOPPED'})


class CompactTests(unittest.TestCase):
    def test_output_does_not_repeat_full_prompt(self):
        m={'id':'m','state':'TURN_COMPLETE','body':{'kind':'ready','session_id':'s','text':'private'},'result':{'text':'x'*10000}}
        r=cli.message_view(m);self.assertTrue(r['result_truncated']);self.assertNotIn('body',r)
        self.assertEqual(len(cli.message_view(m,True)['result']['text']),10000)

if __name__=='__main__':unittest.main()
