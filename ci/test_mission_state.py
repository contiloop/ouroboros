"""Behavior tests for the local ledger, not a live agent/SDK compliance test."""
from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'src/skills/init/scripts/mission_state.py'
spec = importlib.util.spec_from_file_location('mission_state', MODULE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def contract():
    return dict(mission_id='demo', goal='Two evidenced outcomes', workspace='/tmp/demo',
                success_criteria=['notes', 'highlights'], constraints=['preserve intent'],
                delegated_actions=['answer', 'approve_ready', 'accept_result', 'complete'],
                human_only=['deploy'], max_cycles=3, max_stalled_cycles=2,
                approved_by='human', approval_ref='transcript:1')


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.s = m.init_state(contract())
        self.counter = 0

    def event(self, op, actor='L1', **data):
        self.counter += 1
        e = dict(id=f'e{self.counter}', op=op, actor=actor,
                 expected_revision=self.s['revision'], **data)
        e.setdefault('mission_id', self.s['contract']['mission_id'])
        if self.s['cycle'] is not None and op not in {'start','observe'}:
            e.setdefault('cycle_id', self.s['cycle']['id'])
        self.s = m.apply(self.s, e)
        return e

    def start(self, session='w1', reuse=False):
        self.event('start', cycle_id=f'c{len(self.s["cycles"])+1}', session_id=session,
                   goal='This cycle', checkpoint_ref='git:abc', reuse=reuse, session_resumable=True,
                   context='sufficient' if reuse else 'unknown',
                   capabilities=dict(persistent_session=True, decision_relay=True,
                                     nested_agents=True, explicit_procedure_loading=True))

    def ready(self):
        self.event('ready', 'L2', session_id=self.s['cycle']['session_id'], digest='a'*64)

    def approve(self):
        self.event('approve', digest='a'*64, basis='contract:goal')

    def go(self):
        self.event('go', 'L2', session_id=self.s['cycle']['session_id'], digest='a'*64)

    def result(self, **extra):
        d=dict(session_id=self.s['cycle']['session_id'], digest='a'*64, result_ref='evidence:result',
               commit='b'*40, checks=[dict(command='test', exit_code=0, observed=True)],
               review=dict(independent=True, evidence_ref='review:1'), blockers=[],
               children_quiescent=True)
        d.update(extra)
        self.event('result', 'L2', **d)

    def close(self):
        self.event('accept', basis='evidence:result')
        self.event('close', 'L2', session_id=self.s['cycle']['session_id'],
                   archive_ref='.dryforge/001', checkpoint_ref='git:'+'b'*40,
                   children_quiescent=True)

    def cycle(self, session='w1', reuse=False, decision='CONTINUE', progress=True):
        self.start(session, reuse); self.ready(); self.approve(); self.go(); self.result(); self.close()
        self.event('evaluate', decision=decision, progress=progress, basis='evidence:result',
                   success_evidence={'notes': 'test:notes', 'highlights': 'test:highlight'}
                   if decision=='COMPLETE' else {})

    def test_requires_real_user_contract_record(self):
        c=contract();c['approved_by']='L1'
        with self.assertRaises(m.ContractError): m.init_state(c)

    def test_two_cycles_same_worker_and_fresh_worker(self):
        self.cycle();self.cycle('w1', True);self.cycle('w2', decision='COMPLETE')
        self.assertEqual(['w1','w1','w2'], [c['session_id'] for c in self.s['cycles']])
        self.assertEqual(self.s['status'], 'COMPLETE')

    def test_cannot_replace_l2_between_ready_and_go(self):
        self.start();self.ready();self.approve()
        with self.assertRaises(m.ContractError):
            self.event('go','L2',session_id='w2',digest='a'*64)

    def test_same_session_but_stale_approval_rejected(self):
        self.start();self.ready();self.approve()
        with self.assertRaises(m.ContractError):
            self.event('go','L2',session_id='w1',digest='b'*64)
        self.event('ready','L2',session_id='w1',digest='b'*64)
        with self.assertRaises(m.ContractError): self.go()

    def test_l2_cannot_approve_itself(self):
        self.start();self.ready()
        with self.assertRaises(m.ContractError):
            self.event('approve','L2',digest='a'*64,basis='self')

    def test_question_answer_uses_same_cycle_and_scope(self):
        self.start()
        self.event('question','L2',session_id='w1',request_id='q1',question='Policy?',scope='answer')
        self.event('answer',request_id='q1',answer='approved policy',basis='transcript:2')
        self.assertFalse(self.s['cycle']['pending'])
        self.ready();self.approve();self.go()

    def test_pending_question_blocks_approval(self):
        self.start();self.ready()
        self.event('question','L2',session_id='w1',request_id='q1',question='Policy?',scope='answer')
        with self.assertRaises(m.ContractError): self.approve()

    def test_human_only_decision_cannot_be_made_by_l1(self):
        self.start()
        self.event('question','L2',session_id='w1',request_id='q1',question='Deploy?',scope='deploy')
        with self.assertRaises(m.ContractError):
            self.event('answer',request_id='q1',answer='yes',basis='contract:goal')
        self.event('answer','human',request_id='q1',answer='no',basis='human:3')

    def test_missing_delegated_permission(self):
        self.s['contract']['delegated_actions']=[]
        self.start();self.ready()
        with self.assertRaises(m.ContractError): self.approve()

    def test_capability_preflight_fails_closed(self):
        with self.assertRaises(m.ContractError):
            self.event('start',cycle_id='c1',session_id='w1',goal='goal',checkpoint_ref='git:a',
                       reuse=False,context='unknown',capabilities={'persistent_session':True})

    def test_new_cycle_requires_prior_evaluation(self):
        self.start();self.ready();self.approve();self.go();self.result();self.close()
        with self.assertRaises(m.ContractError): self.start('w2')

    def test_reuse_requires_known_headroom(self):
        self.cycle()
        with self.assertRaises(m.ContractError):
            self.event('start',cycle_id='c2',session_id='w1',goal='goal',checkpoint_ref='git:b',
                       reuse=True,context='unknown',capabilities={k:True for k in m.CAPABILITIES})

    def test_negative_or_inconclusive_verification_not_done(self):
        self.start();self.ready();self.approve();self.go()
        for check in (dict(command='test',exit_code=1,observed=True),
                      dict(command='test',exit_code=0,observed=False)):
            with self.subTest(check=check), self.assertRaises(m.ContractError): self.result(checks=[check])

    def test_missing_independent_review_blocks_result(self):
        self.start();self.ready();self.approve();self.go()
        with self.assertRaises(m.ContractError): self.result(review={'independent':False,'evidence_ref':'self'})

    def test_live_children_block_result(self):
        self.start();self.ready();self.approve();self.go()
        with self.assertRaises(m.ContractError): self.result(children_quiescent=False)

    def test_cycle_limit_and_no_progress_limit(self):
        self.s['contract']['max_cycles']=1;self.cycle()
        with self.assertRaises(m.ContractError): self.start('w2')
        self.s=m.init_state(contract());self.cycle(progress=False);self.cycle('w2',progress=False)
        self.assertEqual(self.s['status'],'PAUSED')

    def test_mission_completion_requires_all_success_evidence(self):
        self.start();self.ready();self.approve();self.go();self.result();self.close()
        with self.assertRaises(m.ContractError):
            self.event('evaluate',decision='COMPLETE',progress=True,basis='tests',success_evidence={'notes':'x'})

    def test_hook_stop_is_only_observation(self):
        self.start(); self.event('observe','host',event='SubagentStop',reference='hook:1')
        self.assertEqual(self.s['cycle']['stage'],'READY')
        with self.assertRaises(m.ContractError): self.event('approve','host',digest='a'*64,basis='hook')

    def test_interrupt_resume_same_id(self):
        self.start();self.ready();self.approve();self.go()
        self.event('interrupt','host',session_id='w1',reason='connection lost')
        with self.assertRaises(m.ContractError): self.result()
        with self.assertRaises(m.ContractError):
            self.event('resume',session_id='w2',reconciled=True,checkpoint_ref='git:a')
        self.event('resume',session_id='w1',reconciled=True,checkpoint_ref='git:a')
        self.assertEqual(self.s['cycle']['stage'],'GO')

    def test_abort_requires_human_and_stopped_writers(self):
        self.start()
        with self.assertRaises(m.ContractError): self.event('abort',basis='x',children_quiescent=True)
        self.event('abort','human',basis='human:stop',children_quiescent=True,checkpoint_ref='git:a')
        self.assertIsNone(self.s['cycle'])

    def test_duplicate_id_is_idempotent_but_conflict_is_not(self):
        e=self.event('observe','host',event='start',reference='hook:1')
        self.assertEqual(self.s,m.apply(self.s,e))
        e['event']='other'
        with self.assertRaises(m.ContractError): m.apply(self.s,e)

    def test_stale_revision_no_partial_mutation(self):
        before=copy.deepcopy(self.s)
        with self.assertRaises(m.ContractError):
            m.apply(self.s,dict(id='x',op='observe',actor='host',expected_revision=999,event='start',reference='hook:1'))
        self.assertEqual(self.s,before)

    def test_atomic_store_and_writer_lock(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';m.initialize(path,contract())
            event=dict(mission_id='demo',id='x',op='observe',actor='host',expected_revision=0,event='start',reference='hook:1')
            m.save_event(path,event)
            self.assertEqual(json.loads(path.read_text())['revision'],1)
            path.with_suffix('.json.lock').write_text('other controller')
            with self.assertRaises(m.ContractError): m.save_event(path,event)
            self.assertEqual(json.loads(path.read_text())['revision'],1)

    def test_digest_detects_document_edit(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            for f in ('handoff.md','spec.md','plan.md'): (p/f).write_text(f)
            a=m.document_digest(p);(p/'spec.md').write_text('different')
            self.assertNotEqual(a,m.document_digest(p))

    def test_cross_mission_event_rejected(self):
        with self.assertRaises(m.ContractError):
            self.event('observe','host',mission_id='other',event='start',reference='hook:1')

    def test_cross_cycle_request_rejected(self):
        self.start()
        with self.assertRaises(m.ContractError):
            self.event('question','L2',cycle_id='old',session_id='w1',request_id='q1',question='Stale?',scope='answer')

    def test_human_can_complete_when_not_delegated(self):
        self.s['contract']['delegated_actions'].remove('complete')
        self.start();self.ready();self.approve();self.go();self.result();self.close()
        self.event('evaluate','human',decision='COMPLETE',progress=True,basis='human:final',
                   success_evidence={'notes':'test:n','highlights':'test:h'})
        self.assertEqual(self.s['status'],'COMPLETE')

    def test_failed_transaction_preserves_disk_state(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';m.initialize(path,contract());before=path.read_bytes()
            with self.assertRaises(m.ContractError):
                m.save_event(path,dict(id='x',op='go',actor='L2',session_id='w1',expected_revision=0))
            self.assertEqual(path.read_bytes(),before)
            self.assertFalse(path.with_suffix('.json.lock').exists())

    def test_cli_persists_between_processes(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'contract.json';state=root/'state.json'
            source.write_text(json.dumps(contract()))
            result=subprocess.run([sys.executable,str(MODULE),'init','--state',str(state),'--contract',str(source)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([sys.executable,str(MODULE),'show','--state',str(state)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['revision'],0)

    def test_stale_result_contract_is_not_accepted(self):
        self.start();self.ready();self.approve();self.go()
        with self.assertRaises(m.ContractError):self.result(digest='c'*64)

    def test_invalid_types_rejected(self):
        for key,value in [('max_cycles',True),('max_stalled_cycles',0),('success_criteria',[]),
                          ('goal',''),('workspace','relative/path')]:
            c=contract();c[key]=value
            with self.subTest(key=key), self.assertRaises(m.ContractError):m.init_state(c)


if __name__=='__main__':unittest.main()
