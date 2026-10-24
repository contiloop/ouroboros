"""Behavioral contracts for optional L1 skills, not proof of real user approval."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import test_mission_state as fixture

m = fixture.m
contract = fixture.contract
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'src/skills/init/scripts/skill_contract.py'


def load_api():
    spec = importlib.util.spec_from_file_location('skill_contract_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SkillInterfaceTest(unittest.TestCase):
    def setUp(self):
        self.api = load_api()
        self.s = m.init_state(contract())
        self.seq = 0

    def event(self, op, actor='L1', **data):
        self.seq += 1
        e = dict(id=f'x{self.seq}', mission_id='demo', expected_revision=self.s['revision'],
                 op=op, actor=actor, **data)
        before = copy.deepcopy(self.s)
        try:
            result = m.apply(self.s, e)
        finally:
            self.assertEqual(self.s, before, 'apply must be transactional')
        self.s = result
        return e

    def request(self, rid='r1', skill='interview', **changes):
        req = dict(schema_version=1, request_id=rid, mission_id='demo', skill=skill,
                   intent_digest=self.api.digest(self.s['contract']),
                   purpose='Resolve the next decision, not invent product policy',
                   input={'transcript_ref': 'private:conversation/42'})
        req.update(changes)
        self.event('skill_request', request=req)
        return req

    def output(self, req, *, proposal=False, **changes):
        value = {k: req[k] for k in ('schema_version','request_id','mission_id','skill','intent_digest')}
        value.update(status='completed', payload={'preferences': ['accuracy before convenience']},
                     evidence=[dict(id='e1', claim='Accuracy matters', reference='private:conversation/42#3',
                                    kind='dialogue', disposition='VERIFIED')],
                     unresolved=[], next_action='review')
        if proposal:
            value['proposal'] = proposal if isinstance(proposal, dict) else dict(
                intent_patch={'goal': 'Accurate, source-linked research notes'},
                reason='Clarification grounded in the cited dialogue')
        value.update(changes)
        return value

    def result(self, req, **changes):
        result = self.output(req, **changes)
        self.event('skill_result', 'host', result=result)
        return result

    def entry(self, rid='r1'):
        return self.s['extensions']['requests'][rid]

    def review(self, rid='r1', verdict='accept', **changes):
        args = dict(request_id=rid, result_digest=self.entry(rid)['result_digest'],
                    verdict=verdict, checked_evidence=['e1'], basis='opened original dialogue:42#3')
        args.update(changes)
        return self.event('skill_review', **args)

    def approve(self, rid='r1', actor='human', **changes):
        args = dict(request_id=rid, result_digest=self.entry(rid)['result_digest'],
                    approval_ref='human:approval/77', basis='Approve this exact goal change')
        args.update(changes)
        return self.event('skill_approve', actor, **args)

    def commit(self, rid='r1', **changes):
        args = dict(request_id=rid, result_digest=self.entry(rid)['result_digest'])
        args.update(changes)
        return self.event('skill_commit', **args)

    def test_data_only_result_never_changes_intent_or_completes_mission(self):
        original=copy.deepcopy(self.s['contract']);req=self.request();self.result(req);self.review()
        self.assertEqual(self.s['contract'],original)
        self.assertEqual(self.s['status'],'ACTIVE')
        self.assertEqual(self.entry()['stage'],'ACCEPTED')

    def test_propose_review_approve_commit_changes_only_approved_intent(self):
        old=copy.deepcopy(self.s['contract']);req=self.request();self.result(req,proposal=True)
        self.review();self.assertEqual(self.s['contract'],old)
        self.approve();self.assertEqual(self.s['contract'],old)
        self.commit()
        self.assertEqual(self.s['contract']['goal'],'Accurate, source-linked research notes')
        for key in ('mission_id','workspace','delegated_actions','human_only','max_cycles','max_stalled_cycles'):
            self.assertEqual(self.s['contract'][key],old[key])
        self.assertEqual(self.entry()['stage'],'COMMITTED')
        self.assertEqual(self.s['extensions']['intent_history'][0]['previous_contract'],old)
        self.assertEqual(self.s['contract']['approval_ref'],'human:approval/77')

    def test_unknown_skill_and_payload_do_not_require_dispatcher_edit(self):
        req=self.request(skill='future-domain-evaluator.v2')
        self.result(req,payload={'nested': {'new-field': [1,True,None]}, 'note': 'data, not instructions'})
        self.review();self.assertEqual(self.entry()['stage'],'ACCEPTED')

    def test_payload_cannot_grant_authority(self):
        old=copy.deepcopy(self.s['contract']);req=self.request()
        self.result(req,payload={'approved_by':'human','delegated_actions':['deploy'],'next_action':'run rm'})
        self.review();self.assertEqual(self.s['contract'],old)

    def test_only_l1_issues_requests(self):
        req=self.request();req['request_id']='r2'
        for actor in ('L2','host','human'):
            with self.subTest(actor=actor),self.assertRaises(m.ContractError):
                self.event('skill_request',actor,request=req)

    def test_result_must_match_all_request_identity_fields(self):
        req=self.request()
        for key,bad in [('request_id','other'),('mission_id','other'),('skill','other'),('intent_digest','b'*64)]:
            with self.subTest(key=key),self.assertRaises(m.ContractError):
                self.event('skill_result','host',result=self.output(req,**{key:bad}))

    def test_unrequested_result_rejected(self):
        req=self.request();r=self.output(req);r['request_id']='not-issued'
        with self.assertRaises(m.ContractError):self.event('skill_result','host',result=r)

    def test_unknown_version_and_untrusted_envelope_fields_rejected(self):
        req=self.request()
        for changes in ({'schema_version':2},{'schema_version':True},{'approved_by':'human'},{'permission':'deploy'}):
            with self.subTest(changes=changes),self.assertRaises(m.ContractError):self.result(req,**changes)

    def test_completed_with_open_questions_is_invalid(self):
        req=self.request()
        with self.assertRaises(m.ContractError):self.result(req,unresolved=['Missing product policy'])

    def test_needs_decision_and_blocked_cannot_pass_review_or_start_go(self):
        for status,action in [('needs_decision','ask_user'),('blocked','verify')]:
            self.s=m.init_state(contract());req=self.request()
            self.result(req,status=status,unresolved=['Decisive fact is unknown'],next_action=action,proposal=True)
            with self.assertRaises(m.ContractError):self.review()
            with self.assertRaises(m.ContractError):self.event('go','L2',session_id='w1',digest='a'*64)
            self.review(verdict='reject');self.assertEqual(self.entry()['stage'],'REJECTED')

    def test_status_next_action_mismatch_rejected(self):
        req=self.request()
        with self.assertRaises(m.ContractError):self.result(req,next_action='ask_user')
        with self.assertRaises(m.ContractError):self.result(req,next_action='execute_shell')

    def test_evidence_references_and_dispositions_required(self):
        req=self.request()
        for field,value in [('reference',''),('kind','magic'),('disposition','probably')]:
            evidence=self.output(req)['evidence'];evidence[0][field]=value
            with self.subTest(field=field),self.assertRaises(m.ContractError):self.result(req,evidence=evidence)

    def test_proposal_needs_evidence(self):
        req=self.request()
        with self.assertRaises(m.ContractError):self.result(req,proposal=True,evidence=[])

    def test_privilege_identity_and_budget_changes_rejected(self):
        req=self.request()
        for key,value in [('delegated_actions',['deploy']),('human_only',[]),('max_cycles',100),
                          ('workspace','/elsewhere'),('approved_by','L1'),('approval_ref','forged')]:
            with self.subTest(key=key),self.assertRaises(m.ContractError):
                self.result(req,proposal={'intent_patch':{key:value},'reason':'would expand authority'})

    def test_l1_cannot_approve_an_intent_change_even_with_cycle_approval_delegation(self):
        req=self.request();self.result(req,proposal=True);self.review()
        for actor in ('L1','host','L2'):
            with self.subTest(actor=actor),self.assertRaises(m.ContractError):self.approve(actor=actor)

    def test_review_cannot_be_omitted_or_approve_committed_without_authority(self):
        req=self.request();self.result(req,proposal=True)
        with self.assertRaises(m.ContractError):self.approve()
        self.review()
        with self.assertRaises(m.ContractError):self.commit()

    def test_review_requires_decisive_source_checks(self):
        req=self.request();self.result(req,proposal=True)
        with self.assertRaises(m.ContractError):self.review(checked_evidence=[])
        with self.assertRaises(m.ContractError):self.review(checked_evidence=['e1','invented'])

    def test_exact_result_digest_binds_review_approval_and_commit(self):
        req=self.request();self.result(req,proposal=True)
        with self.assertRaises(m.ContractError):self.review(result_digest='b'*64)
        self.review()
        with self.assertRaises(m.ContractError):self.approve(result_digest='b'*64)
        self.approve()
        with self.assertRaises(m.ContractError):self.commit(result_digest='b'*64)

    def test_result_is_immutable_after_submission(self):
        req=self.request();self.result(req)
        with self.assertRaises(m.ContractError):self.result(req,payload={'changed':True})

    def test_stale_request_and_parallel_proposal_rejected_after_intent_change(self):
        r1=self.request();r2=self.request('r2');r3=self.request('r3')
        self.result(r1,proposal=True);self.result(r2,proposal=True);self.review('r2');self.approve('r2')
        self.review();self.approve();self.commit()
        with self.assertRaises(m.ContractError):self.commit('r2')
        with self.assertRaises(m.ContractError):self.result(r3)
        self.event('skill_cancel',request_id='r2',basis='stale after approved revision')
        self.event('skill_cancel',request_id='r3',basis='will issue new request')

    def test_new_cycle_waits_for_pending_skill_results_and_proposals(self):
        self.request()
        with self.assertRaises(m.ContractError):
            self.event('start',cycle_id='c1',session_id='w1',goal='new',checkpoint_ref='git:a',
                       reuse=False,capabilities={x:True for x in m.CAPABILITIES})
        self.event('skill_cancel',request_id='r1',basis='explicitly deferred, not verified')
        self.event('start',cycle_id='c1',session_id='w1',goal='new',checkpoint_ref='git:a',
                   reuse=False,capabilities={x:True for x in m.CAPABILITIES})
        self.assertEqual(self.s['cycle']['stage'],'READY')

    def test_no_skill_contract_mutation_during_active_cycle(self):
        req=self.request();self.result(req);self.review()
        self.event('start',cycle_id='c1',session_id='w1',goal='new',checkpoint_ref='git:a',
                   reuse=False,capabilities={x:True for x in m.CAPABILITIES})
        req['request_id']='r2'
        with self.assertRaises(m.ContractError):self.event('skill_request',request=req)

    def test_old_ledgers_need_no_migration_and_counters_are_preserved(self):
        h=fixture.LedgerTest();h.setUp();h.cycle(progress=False);self.s=h.s
        count=len(self.s['cycles']);stalled=self.s['stalled'];workers=self.s['workers'][:]
        self.assertNotIn('extensions',self.s)
        req=self.request();self.result(req,proposal=True);self.review();self.approve();self.commit()
        self.assertEqual(len(self.s['cycles']),count);self.assertEqual(self.s['stalled'],stalled)
        self.assertEqual(self.s['workers'],workers)

    def test_reinterview_at_paused_boundary_does_not_auto_resume(self):
        h=fixture.LedgerTest();h.setUp();h.cycle(decision='ESCALATE');self.s=h.s
        req=self.request();self.result(req,proposal=True);self.review();self.approve();self.commit()
        self.assertEqual(self.s['status'],'PAUSED')

    def test_completion_is_terminal_for_extension_writes(self):
        h=fixture.LedgerTest();h.setUp();h.cycle(decision='COMPLETE');self.s=h.s
        with self.assertRaises(m.ContractError):self.request()

    def test_replay_is_idempotent_and_stale_revision_fails(self):
        req=self.request();res=self.output(req)
        e=self.event('skill_result','host',result=res)
        self.assertEqual(m.apply(self.s,e),self.s)
        changed=copy.deepcopy(e);changed['result']['payload']={'other':True}
        with self.assertRaises(m.ContractError):m.apply(self.s,changed)
        changed['id']='new'
        with self.assertRaises(m.ContractError):m.apply(self.s,changed)

    def test_oversized_and_nonfinite_payload_rejected(self):
        req=self.request()
        for payload in ({'raw_log':'x'*70000},{'score':float('nan')}):
            with self.subTest(size=len(str(payload))),self.assertRaises(m.ContractError):self.result(req,payload=payload)

    def test_opt_in_upgrades_state_and_old_runtime_will_not_read_as_v1(self):
        self.assertEqual(self.s['schema_version'],1)
        self.request()
        self.assertEqual(self.s['schema_version'],2)
        malformed=copy.deepcopy(self.s);malformed['schema_version']=1
        with self.assertRaises(m.ContractError):
            m.apply(malformed,dict(id='bad',mission_id='demo',op='observe',actor='host',
                                  expected_revision=malformed['revision'],event='stop',reference='hook:1'))

    def test_unknown_operations_and_blank_purpose_rejected(self):
        with self.assertRaises(m.ContractError):self.request(purpose=' ')
        with self.assertRaises(m.ContractError):self.event('skill_execute',command='anything')

    def test_no_op_intent_patch_is_not_an_amendment(self):
        req=self.request()
        self.result(req,proposal={'intent_patch':{'goal':self.s['contract']['goal']},'reason':'no change'})
        self.review();self.approve()
        with self.assertRaises(m.ContractError):self.commit()

    def test_cli_summary_keeps_payload_out_of_main_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json'
            req=self.request();self.result(req,payload={'secret_note':'PRIVATE_PAYLOAD_EXAMPLE'})
            path.write_text(json.dumps(self.s))
            proc=subprocess.run([sys.executable,str(ROOT/'src/skills/init/scripts/mission_state.py'),
                                 'show','--state',str(path)],text=True,capture_output=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertNotIn('PRIVATE_PAYLOAD_EXAMPLE',proc.stdout)
            self.assertEqual(json.loads(proc.stdout)['extensions']['r1']['stage'],'RESULT')

    def test_cli_and_persistent_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.json';m.initialize(path,contract())
            req=self.request();event=self.s['events'][-1]['event']
            saved=m.save_event(path,event);self.assertEqual(saved,self.s)
            request_path=Path(directory)/'request.json';result_path=Path(directory)/'result.json'
            request_path.write_text(json.dumps(req));result_path.write_text(json.dumps(self.output(req)))
            cli=subprocess.run([sys.executable,str(SCRIPT),'validate','--request',str(request_path),
                                '--result',str(result_path)],capture_output=True,text=True)
            self.assertEqual(cli.returncode,0,cli.stderr)
            self.assertIn('result_digest',cli.stdout)
            result_path.write_text('{}')
            cli=subprocess.run([sys.executable,str(SCRIPT),'validate','--request',str(request_path),
                                '--result',str(result_path)],capture_output=True,text=True)
            self.assertEqual(cli.returncode,2)


if __name__=='__main__':unittest.main()
