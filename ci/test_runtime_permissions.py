"""Scoped delegation tests. Synthetic consent, real Git/SQLite, no authenticated models."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'src/skills/mission/scripts'
sys.path.insert(0, str(SCRIPTS))
import mission_state as ledger
import runtime_permissions as policy
from runtime_bridge.store import Store, BridgeError, digest
from runtime_bridge.controller import prepare, delegation_for


def grant():
    return {'version': 1, 'operations': ['git_add', 'git_commit', 'workspace_edit', 'verify'],
            'paths': ['memo_cli', 'tests'], 'verification_commands': [['python3', '-m', 'unittest', 'discover', '-s', 'tests']],
            'trust_workspace_code': True}


def worktree_grant():
    # Version 1 grants intentionally DO NOT gain worktree rights on upgrade.
    return dict(grant(), version=2, go_worktrees=True)


class DelegationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        for path in ('memo_cli/__init__.py', 'tests/__init__.py'):
            p = self.root/path; p.parent.mkdir(exist_ok=True); p.write_text('')
        for name in ('spec', 'plan', 'handoff'):
            p = self.root/f'.dryforge/{name}.md'; p.parent.mkdir(exist_ok=True); p.write_text(name)
        self.path = self.root/'.dryforge/mission/state.json'; self.path.parent.mkdir()
        contract = dict(mission_id='fixture', goal='fixture', workspace=str(self.root),
                        success_criteria=['local files'], constraints=['no upload'], human_only=['deploy'],
                        delegated_actions=['answer','approve_ready'], max_cycles=4, max_stalled_cycles=2,
                        approved_by='human', approval_ref='FIXTURE-NOT-REAL-APPROVAL')
        self.s = ledger.init_state(contract)
        d = ledger.document_digest(self.root/'.dryforge')
        self.s['cycle'] = dict(id='c1',session_id='sid',stage='GO',pending={},digest=d,approved_digest=d)
        self.save()
        self.config = dict(workspace=str(self.root),backend='codex')
        self.store = Store(self.root/'.dryforge/mission/runtime')
        self.store.create('w', self.config); self.store.attach('w','owner'); self.store.bind('w','owner','sid')
        self.store.state('w','owner','IDLE')
        body = prepare(self.config,'sid','message','fixture continuation',self.path,'c1')
        self.store.enqueue('w','m',body); self.store.claim('w','owner')

    def tearDown(self):
        self.store.close(); self.tmp.cleanup()

    def save(self): self.path.write_text(json.dumps(self.s))

    def event(self, value, actor='human', **kwargs):
        e = dict(id='policy-'+str(self.s['revision']), op='runtime_policy', actor=actor,
                 expected_revision=self.s['revision'],mission_id='fixture',cycle_id='c1',
                 expected_policy_digest=policy.fingerprint(self.s.get('runtime_authority')),
                 approval_ref='FIXTURE-APPROVED-LOCAL-DEV',basis='synthetic consent',policy=value)
        e.update(kwargs)
        self.s = ledger.apply(self.s,e); self.save(); return e

    def request(self, command='git add memo_cli/__init__.py tests/__init__.py', payload=None):
        payload = payload or {'method':'item/commandExecution/requestApproval',
                              'params':{'cwd':str(self.root),'command':command,'threadId':'sid','turnId':'turn-1','itemId':'item-1'}}
        rid = self.store.request('w','owner','m','permission',payload)
        r = next(x for x in self.store.pending('w') if x['id'] == rid)
        response = dict(principal='L1',action='allow',basis='fixture task implements approved spec',session_id='sid',
                        request_digest=r['fingerprint'],policy_digest=policy.fingerprint(self.s.get('runtime_authority')))
        return rid,r,response

    def allow(self, command=None, payload=None):
        rid,r,a = self.request(**({'command':command} if command else {}),payload=payload)
        self.store.answer('w',rid,a)
        self.assertEqual(self.store.take_answer('w','owner',rid)['principal'],'L1')
        return rid

    def worktree(self, name='T1'):
        subprocess.run(['git','-C',str(self.root),'add','memo_cli/__init__.py','tests/__init__.py'],
                       check=True, capture_output=True)
        subprocess.run(['git','-C',str(self.root),'-c','user.name=Fixture',
                        '-c','user.email=fixture@example.invalid','commit','-qm','test base'],
                       check=True,capture_output=True)
        wt = self.root/'.dryforge/worktrees'/name
        wt.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git','-C',str(self.root),'worktree','add','-q','-b','task-'+name,
                        str(wt),'HEAD'],check=True,capture_output=True)
        return wt

    def host_request(self, cwd, command):
        return {'method':'item/commandExecution/requestApproval',
                'params':{'cwd':str(cwd),'command':command,'threadId':'sid',
                          'turnId':'turn-1','itemId':'item-1'}}

    def test_question_answer_requires_live_delegated_intent_at_record_and_consume(self):
        payload = {'method':'item/tool/requestUserInput', 'params':{'questions':[{'id':'q','question':'Format?'}]}}
        rid = self.store.request('w','owner','m','question',payload)
        req = next(x for x in self.store.pending('w') if x['id'] == rid)
        response = dict(principal='L1', action='answer', answers={'q':'plain text'},
                        basis='fixture intent', session_id='sid', request_digest=req['fingerprint'])
        self.store.answer('w', rid, response)
        self.s['contract']['delegated_actions'].remove('answer'); self.save()
        with self.assertRaises(BridgeError): self.store.take_answer('w','owner',rid)
        rid = self.store.request('w','owner','m','question',payload)
        req = next(x for x in self.store.pending('w') if x['id'] == rid)
        response['request_digest'] = req['fingerprint']
        with self.assertRaises(BridgeError): self.store.answer('w',rid,response)

    def test_v1_or_v2_disabled_does_not_silently_gain_worktree_rights(self):
        wt=self.worktree()
        (wt/'tests/new.py').write_text('test = 1\n')
        payload=self.host_request(wt,'git add tests/new.py')
        for g in (grant(),dict(worktree_grant(),go_worktrees=False)):
            with self.subTest(version=g['version']):
                self.event(g)
                rid,r,a=self.request(payload=payload)
                with self.assertRaises(BridgeError): self.store.answer('w',rid,a)

    def test_real_t1_worktree_add_commit_and_same_id_audit(self):
        wt=self.worktree()
        for name in ('memo_cli/domain.py','memo_cli/repository.py','memo_cli/storage.py',
                     'tests/test_storage.py'):
            (wt/name).write_text('verified_fixture = True\n')
        self.event(worktree_grant())
        cmd='git add memo_cli/domain.py memo_cli/repository.py memo_cli/storage.py tests/test_storage.py'
        payload=self.host_request(wt,"/bin/zsh -lc '"+cmd+"'")
        rid,r,a=self.request(payload=payload)
        self.assertEqual(delegation_for(self.store,'w',r)['worktree'],str(wt))
        self.store.answer('w',rid,a)
        self.store.take_answer('w','owner',rid)
        self.assertEqual(self.store.events('w')[-1]['kind'],'request.consumed')
        self.assertEqual([x['body']['worktree'] for x in self.store.events('w')
                          if x['kind']=='request.delegation_checked'][-2:], [str(wt),str(wt)])
        # A real host would execute the approved command; the policy never runs it itself.
        subprocess.run(['git','-C',str(wt),'add','memo_cli/domain.py','memo_cli/repository.py',
                        'memo_cli/storage.py','tests/test_storage.py'],check=True)
        rid,r,a=self.request(payload=self.host_request(wt,'git commit -m "Implement T1"'))
        self.store.answer('w',rid,a)
        commit_audit=[x['body'] for x in self.store.events('w')
                      if x['kind']=='request.delegation_checked' and x['body']['operation']=='git_commit']
        self.assertEqual(commit_audit[-1]['worktree'],str(wt))
        self.assertIsNotNone(commit_audit[-1]['index_digest'])
        self.store.take_answer('w','owner',rid)
        self.assertNotEqual(policy._git_path(wt,'index'),self.root/'.git/index')

    def test_go_worktree_file_write_and_verification(self):
        wt=self.worktree();self.event(worktree_grant())
        self.allow(payload={'tool':'Write','input':{'file_path':str(wt/'tests/new.py'),'content':'x'}})
        self.allow(payload={'method':'item/fileChange/requestApproval',
                    'observed_changes':[{'kind':{'type':'add'},'path':str(wt/'memo_cli/new.py')}],
                    'params':{}})
        self.allow(payload=self.host_request(wt,'python3 -m unittest discover -s tests'))
        self.allow(payload={'tool':'Bash','input':{'command':f'git -C {wt} add tests/__init__.py'}})

    def test_worktree_scope_escape_and_unknown_git_commands_rejected(self):
        wt=self.worktree();self.event(worktree_grant())
        (wt/'tests/link').symlink_to(self.root)
        (wt/'secret.txt').write_text('secret')
        for cmd in ('git add .','git add -A','git add ../tests/__init__.py',
                    'git add tests/link/out','git add secret.txt',
                    'git push origin main','git merge main','git worktree remove T1',
                    'git add tests/__init__.py && git push origin main'):
            with self.subTest(cmd=cmd):
                rid,r,a=self.request(payload=self.host_request(wt,cmd))
                with self.assertRaises(BridgeError):self.store.answer('w',rid,a)
        for bad in (wt/'tests',self.root/'.dryforge/worktrees',self.root/'.git'):
            with self.subTest(cwd=str(bad)):
                rid,r,a=self.request(payload=self.host_request(bad,'git add tests/__init__.py'))
                with self.assertRaises(BridgeError):self.store.answer('w',rid,a)

    def test_fake_worktree_or_other_repo_not_delegated(self):
        self.event(worktree_grant())
        fake=self.root/'.dryforge/worktrees/FAKE'
        fake.mkdir(parents=True)
        (fake/'.git').write_text('gitdir: /tmp/another/.git/worktrees/FAKE\n')
        rid,r,a=self.request(payload=self.host_request(fake,'git add tests/__init__.py'))
        with self.assertRaises(BridgeError):self.store.answer('w',rid,a)
        other=self.root/'independent'
        subprocess.run(['git','init','-q',str(other)],check=True)
        rid,r,a=self.request(payload=self.host_request(other,'git add tests/__init__.py'))
        with self.assertRaises(BridgeError):self.store.answer('w',rid,a)

    def test_worktree_git_pointer_change_rejected_before_callback_consumption(self):
        wt=self.worktree();self.event(worktree_grant())
        (wt/'tests/new.py').write_text('x')
        rid,r,a=self.request(payload=self.host_request(wt,'git add tests/new.py'))
        self.store.answer('w',rid,a)
        original=(wt/'.git').read_text()
        (wt/'.git').write_text('gitdir: /tmp/impostor/.git/worktrees/T1\n')
        with self.assertRaises(BridgeError):self.store.take_answer('w','owner',rid)
        (wt/'.git').write_text(original)

    def test_worktree_commit_index_revalidated_at_consumption(self):
        wt=self.worktree();self.event(worktree_grant())
        (wt/'tests/new.py').write_text('x')
        subprocess.run(['git','-C',str(wt),'add','tests/new.py'],check=True)
        rid,r,a=self.request(payload=self.host_request(wt,'git commit -m "T1"'))
        self.store.answer('w',rid,a)
        (wt/'memo_cli/domain.py').write_text('more')
        subprocess.run(['git','-C',str(wt),'add','memo_cli/domain.py'],check=True)
        with self.assertRaises(BridgeError):self.store.take_answer('w','owner',rid)

    def test_old_mission_does_not_gain_authority(self):
        rid,r,a=self.request()
        with self.assertRaises(BridgeError): self.store.answer('w',rid,a)
        self.assertEqual(self.s['schema_version'],1)

    def test_l1_cannot_grant_itself_permission(self):
        for who in ('L1','L2','host'):
            with self.subTest(who=who), self.assertRaises(ledger.ContractError): self.event(grant(),actor=who)

    def test_l1_git_add_preserves_actual_principal(self):
        self.event(grant());rid=self.allow()
        checks=[x for x in self.store.events('w') if x['kind']=='request.delegation_checked']
        self.assertEqual([x['body']['phase'] for x in checks],['record','consume'])
        self.assertTrue(all(x['body']['operation']=='git_add' for x in checks))
        self.assertEqual(checks[-1]['body']['approval_ref'],'FIXTURE-APPROVED-LOCAL-DEV')
        self.assertFalse((self.root/'.git/index').exists()) # validator did not execute requested add

    def test_status_hint_is_not_an_approval(self):
        self.event(grant());rid,r,a=self.request()
        info=delegation_for(self.store,'w',r)
        self.assertTrue(info['eligible']); self.assertEqual(info['operation'],'git_add')
        self.assertEqual(self.store.pending('w')[0]['id'],rid)

    def test_human_can_grant_while_request_is_waiting(self):
        rid,r,a=self.request(); self.event(grant())
        a['policy_digest']=policy.fingerprint(self.s['runtime_authority'])
        self.store.answer('w',rid,a); self.store.take_answer('w','owner',rid)
        self.assertEqual(self.s['cycle']['stage'],'GO')

    def test_grant_preserves_intent_docs_budget_and_worker(self):
        before=copy.deepcopy(self.s); self.event(grant())
        for key in ('contract','cycle','cycles','workers','stalled','status'):
            self.assertEqual(before[key],self.s[key])
        self.assertEqual(self.s['schema_version'],3)

    def test_revocation_between_record_and_consume_blocks(self):
        self.event(grant());rid,r,a=self.request();self.store.answer('w',rid,a);self.event(None)
        with self.assertRaises(BridgeError): self.store.take_answer('w','owner',rid)

    def test_regrant_same_policy_does_not_revive_old_approval(self):
        self.event(grant());rid,r,a=self.request();self.store.answer('w',rid,a)
        self.event(None);self.event(grant())
        with self.assertRaises(BridgeError):self.store.take_answer('w','owner',rid)

    def test_changed_docs_block_at_consumption(self):
        self.event(grant());rid,r,a=self.request();self.store.answer('w',rid,a)
        (self.root/'.dryforge/spec.md').write_text('other scope')
        with self.assertRaises(BridgeError):self.store.take_answer('w','owner',rid)

    def test_pause_human_only_pending_and_wrong_session_block(self):
        for kind in ('pause','human-only','pending','session','intent'):
            with self.subTest(kind=kind):
                self.event(grant());rid,r,a=self.request();self.store.answer('w',rid,a)
                saved=copy.deepcopy(self.s)
                if kind=='pause':self.s['status']='PAUSED'
                if kind=='human-only':self.s['contract']['human_only'].append('git_add')
                if kind=='pending':self.s['cycle']['pending']={'q':{}}
                if kind=='session':self.s['cycle']['session_id']='other'
                if kind=='intent':self.s['contract']['goal']='different'
                self.save()
                with self.assertRaises(BridgeError):self.store.take_answer('w','owner',rid)
                self.s=saved;self.save()

    def test_ready_is_not_write_authority(self):
        self.event(grant());self.s['cycle']['stage']='READY';self.save()
        rid,r,a=self.request()
        with self.assertRaises(BridgeError):self.store.answer('w',rid,a)

    def test_policy_digest_required_and_bound(self):
        self.event(grant());rid,r,a=self.request();a['policy_digest']='wrong'
        with self.assertRaises(BridgeError):self.store.answer('w',rid,a)

    def test_exact_answer_retry_is_idempotent(self):
        self.event(grant());rid,r,a=self.request();self.store.answer('w',rid,a);self.store.answer('w',rid,a)
        self.store.take_answer('w','owner',rid);self.store.answer('w',rid,a)
        self.store.finish('w','owner','m',{'ok':True})
        from runtime_bridge.controller import check_answer
        check_answer(self.store,'w',rid,a);self.store.answer('w',rid,a)
        self.assertEqual(len([x for x in self.store.events('w') if x['kind']=='request.answered']),1)

    def test_out_of_scope_git_or_shell_needs_human(self):
        self.event(grant())
        for command in ('git push origin main','git reset --hard','git clean -fd','git add .','git add -A',
                        'git add --force .env','git add ../outside','git add :(top)*',
                        'git add tests/__init__.py && git push','git add tests/__init__.py; rm -rf tests',
                        'git add $(cat bad)','GIT_INDEX_FILE=/tmp/other git add tests/__init__.py',
                        'git -c core.hooksPath=/tmp/h commit -m x','git commit --amend -m x'):
            with self.subTest(command=command):
                rid,r,a=self.request(command)
                with self.assertRaises(BridgeError):self.store.answer('w',rid,a)

    def test_workspace_symlink_escape_blocked(self):
        self.event(grant());(self.root/'tests/link').symlink_to('/tmp')
        rid,r,a=self.request('git add tests/link/anything')
        with self.assertRaises(BridgeError):self.store.answer('w',rid,a)

    def test_file_edit_and_protected_metadata(self):
        self.event(grant())
        self.allow(payload={'tool':'Write','input':{'file_path':str(self.root/'memo_cli/new.py'),'content':'x'}})
        for p in (self.root/'.dryforge/mission/state.json',self.root/'.git/config',self.root/'.codex/config.toml',Path('/tmp/outside')):
            rid,r,a=self.request(payload={'tool':'Write','input':{'file_path':str(p),'content':'x'}})
            with self.assertRaises(BridgeError):self.store.answer('w',rid,a)

    def test_codex_files_require_observed_paths_no_deletions(self):
        self.event(grant())
        body={'method':'item/fileChange/requestApproval','params':{'threadId':'sid','itemId':'i'}}
        rid,r,a=self.request(payload=body)
        with self.assertRaises(BridgeError):self.store.answer('w',rid,a)
        body['observed_changes']=[{'path':str(self.root/'memo_cli/new.py'),'kind':{'type':'add'}}]
        self.allow(payload=body)
        body['observed_changes'][0]['kind']={'type':'delete'}
        rid,r,a=self.request(payload=body)
        with self.assertRaises(BridgeError):self.store.answer('w',rid,a)

    def test_command_cwd_and_explicit_claude_git_root(self):
        self.event(grant())
        body={'tool':'Bash','input':{'command':'git add tests/__init__.py'}}
        rid,r,a=self.request(payload=body)
        with self.assertRaises(BridgeError):self.store.answer('w',rid,a)
        body['input']['command']=f'git -C {self.root} add tests/__init__.py'
        self.allow(payload=body)

    def test_common_shell_wrapper(self):
        self.event(grant());self.allow('/bin/zsh -lc "git add tests/__init__.py"')

    def test_git_commit_checks_all_staged_files(self):
        self.event(grant())
        subprocess.run(['git','-C',str(self.root),'add','tests/__init__.py'],check=True)
        self.allow('git commit -m "Add tests"')
        (self.root/'outside.txt').write_text('no')
        subprocess.run(['git','-C',str(self.root),'add','outside.txt'],check=True)
        rid,r,a=self.request('git commit -m "Too broad"')
        with self.assertRaises(BridgeError):self.store.answer('w',rid,a)

    def test_verification_requires_exact_human_approved_argv(self):
        self.event(grant());self.allow('python3 -m unittest discover -s tests')
        for cmd in ('python3 -c print(1)','python3 -m pip install x','npm install','npm publish','python3 -m pytest'):
            rid,r,a=self.request(cmd)
            with self.assertRaises(BridgeError):self.store.answer('w',rid,a)

    def test_network_and_permission_expansion_not_delegated(self):
        self.event(grant())
        for method in ('item/tool/requestUserInput','item/permissions/requestApproval','mcpServer/elicitation/request'):
            rid,r,a=self.request(payload={'method':method,'params':{}})
            with self.assertRaises(BridgeError):self.store.answer('w',rid,a)
        body={'method':'item/commandExecution/requestApproval','params':{'command':'git add tests/__init__.py',
               'cwd':str(self.root),'networkApprovalContext':{'host':'example.com'}}}
        rid,r,a=self.request(payload=body)
        with self.assertRaises(BridgeError):self.store.answer('w',rid,a)

    def test_malformed_policy_and_missing_project_trust(self):
        for p in (dict(grant(),operations=['all']),dict(grant(),paths=['../']),dict(grant(),trust_workspace_code=False),
                  dict(grant(),verification_commands=[['sh','-c','echo ok']]),dict(grant(),version=99)):
            with self.assertRaises(ledger.ContractError):self.event(p)

    def test_schema3_survives_skill_event_and_cannot_downgrade(self):
        self.event(grant());self.s['cycle']=None; self.save()
        request={'schema_version':1,'request_id':'x','mission_id':'fixture','skill':'future',
                 'intent_digest':digest(self.s['contract']),'purpose':'fixture','input':{}}
        e={'id':'extension','op':'skill_request','actor':'L1','mission_id':'fixture',
           'expected_revision':self.s['revision'],'request':request}
        nxt=ledger.apply(self.s,e);self.assertEqual(nxt['schema_version'],3)
        nxt['schema_version']=2
        with self.assertRaises(ledger.ContractError):ledger.apply(nxt,dict(e,id='x2',expected_revision=nxt['revision']))

    def test_wrong_cycle_cannot_grant(self):
        with self.assertRaises(ledger.ContractError):self.event(grant(),cycle_id='other')

    def test_old_grant_edit_requires_human_event_not_skill_patch(self):
        import skill_contract
        req={'schema_version':1,'request_id':'a','mission_id':'fixture','skill':'interview',
             'intent_digest':digest(self.s['contract']),'purpose':'fixture','input':{}}
        result={k:req[k] for k in skill_contract.IDENTITY}
        result.update(status='completed',payload={},evidence=[{'id':'e','claim':'fixture','reference':'fixture',
                      'kind':'dialogue','disposition':'VERIFIED'}],unresolved=[],next_action='review',
                      proposal={'reason':'fixture','intent_patch':{'runtime_policy':grant()}})
        with self.assertRaises(skill_contract.ContractError):skill_contract.validate_result(req,result)


if __name__ == '__main__': unittest.main()
