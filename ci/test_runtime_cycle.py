"""Real Git/SQLite cycle regression tests with synthetic host requests and consent.

These tests exercise record AND consume checks. They are not live L2/L3 E2E.
"""
import copy
import shlex
import unittest
from ci import test_runtime_permissions as fixtures
from ci import test_runtime_go_permissions as go_fixtures

ledger = fixtures.ledger
policy = fixtures.policy
BridgeError = fixtures.BridgeError


class CycleRuntimeTests(unittest.TestCase):
    setUp = fixtures.DelegationTests.setUp
    tearDown = fixtures.DelegationTests.tearDown
    save = fixtures.DelegationTests.save
    event = fixtures.DelegationTests.event
    host_request = fixtures.DelegationTests.host_request
    allow = fixtures.DelegationTests.allow
    git = go_fixtures.GoDelegationTests.git
    reject = go_fixtures.GoDelegationTests.reject

    def transition(self, op, actor='L1', **kw):
        e = dict(id='cycle-'+str(self.s['revision']), op=op, actor=actor, mission_id='fixture',
                 expected_revision=self.s['revision'], cycle_id=self.s['cycle']['id'], session_id='sid')
        e.update(kw)
        self.s = ledger.apply(self.s, e); self.save()

    def setup_cycle(self, *, bind=True, greenfield=False):
        self.git('config', 'user.name', 'Fixture'); self.git('config', 'user.email', 'fixture@example.invalid')
        (self.root/'.gitignore').write_text('.dryforge/\n')
        self.git('add', '.gitignore', 'memo_cli/__init__.py', 'tests/__init__.py')
        self.git('commit', '-qm', 'baseline'); self.git('branch', '-M', 'main')
        self.initial = self.git('rev-parse', 'HEAD')
        g = dict(fixtures.worktree_grant(), version=4,
                 go_workflow=dict(integration_branch='main',cycle_branch_prefix='dryforge/',task_branch_prefix='dryforge/task-'))
        g['operations'] += ['git_checkout','git_worktree_add','git_merge','git_worktree_remove','git_branch_delete']
        # Altering fixture intent needs a fresh message; a live queued message
        # must never acquire a different intent after dispatch.
        self.s['contract']['delegated_actions'] += ['accept_result', 'complete']
        self.s['workers'] = ['sid']; self.s['cycle']['decisions'] = []; self.save()
        self.store.finish('w','owner','m',{'ok':True})
        body = fixtures.prepare(self.config,'sid','message','cycle fixture',self.path,'c1')
        self.store.enqueue('w','cycle',body); self.store.claim('w','owner')
        self.event(g)
        self.targets = dict(cycle_branch='main' if greenfield else 'dryforge/statistics',
                            tasks={'T1':'dryforge/task-words','T2':'dryforge/task-lines'},archive_dir='.dryforge/001')
        if bind: self.bind()
        return g

    def request(self, command='git add memo_cli/__init__.py', payload=None):
        payload = payload or self.host_request(self.root, command)
        rid = self.store.request('w','owner','cycle','permission',payload)
        r = next(x for x in self.store.pending('w') if x['id'] == rid)
        response = dict(principal='L1',action='allow',basis='synthetic approved cycle',session_id='sid',
                        request_digest=r['fingerprint'],policy_digest=policy.fingerprint(self.s.get('runtime_authority')))
        return rid,r,response

    def bind(self, **kw):
        self.transition('bind_runtime',basis='reviewed Ready task graph',targets=kw.pop('targets',self.targets),
                        policy_digest=kw.pop('policy_digest',policy.fingerprint(self.s['runtime_authority'])),**kw)

    def execute(self, command, cwd=None):
        self.allow(payload=self.host_request(cwd or self.root,command))
        argv = shlex.split(command)
        return self.git(*argv[1:],cwd=cwd)

    def feature(self):
        self.execute('git checkout -b dryforge/statistics')

    def task(self, tid='T1'):
        name = self.targets['tasks'][tid]; feature = self.targets['cycle_branch']
        self.execute(f'git worktree add -b {name} .dryforge/worktrees/{tid} {feature}')
        wt = self.root/'.dryforge/worktrees'/tid
        path = 'tests/' + tid.lower() + '.py'
        (wt/path).write_text('value = 1\n')
        self.execute('git add '+path,cwd=wt)
        self.execute('git commit -m "Implement task"',cwd=wt)
        return wt

    def report(self):
        self.transition('result','L2',digest=self.s['cycle']['approved_digest'],commit=self.git('rev-parse','HEAD'),
                        result_ref='synthetic-evidence',checks=[dict(command='fixture check',exit_code=0,observed=True)],
                        review=dict(independent=True,evidence_ref='synthetic-review'),blockers=[],children_quiescent=True)

    def archive(self):
        archive = self.root/self.targets['archive_dir']; archive.mkdir()
        for name in ('handoff.md','spec.md','plan.md'):
            (self.root/'.dryforge'/name).rename(archive/name)

    def test_real_existing_project_full_cycle_then_next_ready(self):
        self.setup_cycle(); self.feature(); self.task('T1'); self.task('T2')
        for tid in ('T1','T2'):
            self.execute(f'git merge --no-ff {self.targets["tasks"][tid]} -m "Integrate task"')
        self.report()
        self.transition('rework',basis='specific correction',feedback_ref='review:correction',digest=self.s['cycle']['digest'])
        (self.root/'tests/t1.py').write_text('value = 2\n')
        self.execute('git add tests/t1.py'); self.execute('git commit -m "Address review"')
        self.report(); self.transition('accept',basis='new review and checks')
        accepted = self.s['cycle']['result']['commit']
        self.archive()
        for tid in ('T1','T2'):
            self.execute(f'git worktree remove .dryforge/worktrees/{tid}')
            self.execute(f'git branch -d {self.targets["tasks"][tid]}')
        self.execute('git checkout main')
        self.execute('git merge --no-ff dryforge/statistics -m "Accept cycle"')
        self.execute('git branch -d dryforge/statistics')
        self.assertEqual(self.git('branch','--show-current'),'main')
        self.assertEqual((self.root/'tests/t1.py').read_text(),'value = 2\n')
        self.git('merge-base','--is-ancestor',accepted,'HEAD')
        self.assertEqual(self.git('status','--porcelain'),'')
        self.transition('close','L2',archive_ref='.dryforge/001',checkpoint_ref='git:'+self.git('rev-parse','HEAD'),children_quiescent=True)
        self.transition('evaluate',basis='first feature done',decision='CONTINUE',progress=True)
        self.s = ledger.apply(self.s,dict(id='next-ready',op='start',actor='L1',mission_id='fixture',expected_revision=self.s['revision'],
            cycle_id='c2',session_id='sid',reuse=True,context='sufficient',session_resumable=True,
            goal='next feature',checkpoint_ref='previous accepted checkpoint',capabilities={k:True for k in ledger.CAPABILITIES}))
        self.assertEqual(self.s['cycle']['stage'],'READY')
        self.assertNotIn('runtime_binding',self.s['cycle'])
        self.assertEqual(self.s['cycle']['session_id'],'sid')

    def test_binding_is_l1_narrowing_not_a_new_grant(self):
        self.setup_cycle(bind=False)
        original = copy.deepcopy(self.s['runtime_authority'])
        with self.assertRaises(ledger.ContractError): self.bind(actor='L2')
        for changes in (dict(cycle_branch='unrelated'),dict(tasks={'T1':'main'}),dict(archive_dir='.dryforge/../elsewhere')):
            with self.assertRaises(ledger.ContractError): self.bind(targets=dict(self.targets,**changes))
        self.bind()
        self.assertEqual(self.s['runtime_authority'],original)
        self.assertEqual(self.s['schema_version'],5)
        with self.assertRaises(ledger.ContractError): self.bind()

    def test_old_policy_cannot_be_reinterpreted_as_cycle_grant(self):
        self.setup_cycle(bind=False)
        g=dict(fixtures.worktree_grant(),version=3,go_workflow={'base_branch':'main','branch_prefix':'dryforge/'})
        g['operations']+=['git_worktree_add']; self.event(g)
        with self.assertRaises(ledger.ContractError): self.bind()
        self.reject('git checkout -b dryforge/statistics')

    def test_l1_can_assign_repair_task_without_changing_grant_or_existing_targets(self):
        self.setup_cycle();self.feature()
        authority=copy.deepcopy(self.s['runtime_authority'])
        args=dict(basis='in-scope review correction',policy_digest=policy.fingerprint(authority))
        with self.assertRaises(ledger.ContractError):
            self.transition('bind_tasks',tasks={'T1':'dryforge/task-replacement'},**args)
        with self.assertRaises(ledger.ContractError):
            self.transition('bind_tasks',tasks={'FIX':'outside/fix'},**args)
        self.transition('bind_tasks',tasks={'FIX':'dryforge/task-fix'},**args)
        self.assertEqual(self.s['runtime_authority'],authority)
        self.execute('git worktree add -b dryforge/task-fix .dryforge/worktrees/FIX dryforge/statistics')

    def test_missing_binding_or_changed_authority_blocks_requests(self):
        g=self.setup_cycle(bind=False)
        self.reject('git checkout -b dryforge/statistics')
        self.bind(); self.event(g)
        self.reject('git checkout -b dryforge/statistics')

    def test_worktree_creation_uses_feature_not_main(self):
        self.setup_cycle(); self.feature()
        self.reject('git worktree add -b dryforge/task-words .dryforge/worktrees/T1 main')
        self.reject('git worktree add -b dryforge/task-other .dryforge/worktrees/T1 dryforge/statistics')
        self.reject('git worktree add -b dryforge/task-words .dryforge/worktrees/OTHER dryforge/statistics')
        self.task()

    def test_foreign_registered_worktree_does_not_inherit_cycle_authority(self):
        self.setup_cycle(); self.feature()
        wt=self.root/'.dryforge/worktrees/FOREIGN'
        self.git('worktree','add','-b','dryforge/task-other',str(wt),'HEAD')
        rid,_,answer=self.request(payload=self.host_request(wt,'git add tests/__init__.py'))
        with self.assertRaises(BridgeError):self.store.answer('w',rid,answer)

    def test_binding_and_git_state_rechecked_before_consumption(self):
        self.setup_cycle(); self.feature()
        rid,_,answer=self.request(command='git worktree add -b dryforge/task-words .dryforge/worktrees/T1 dryforge/statistics')
        self.store.answer('w',rid,answer)
        self.s['cycle']['runtime_binding']['tasks']['T1']='dryforge/task-changed';self.save()
        with self.assertRaises(BridgeError):self.store.take_answer('w','owner',rid)

    def test_result_review_requires_rework_before_writing(self):
        self.setup_cycle(); self.feature()
        (self.root/'tests/new.py').write_text('value = 1\n')
        self.execute('git add tests/new.py');self.execute('git commit -m implement')
        self.report(); self.reject('git add tests/new.py')
        with self.assertRaises(ledger.ContractError):
            self.transition('rework',basis='bad contract',feedback_ref='review',digest='0'*64)
        self.transition('rework',basis='fix result',feedback_ref='review',digest=self.s['cycle']['digest'])
        self.assertNotIn('result',self.s['cycle'])
        self.allow('git add tests/new.py')
        with self.assertRaises(ledger.ContractError):self.transition('accept',basis='stale result')

    def test_accepted_result_cannot_be_edited_and_archive_must_match(self):
        self.setup_cycle();self.feature();self.task()
        self.execute('git merge --no-ff dryforge/task-words -m integrate')
        self.report();self.transition('accept',basis='reviewed')
        self.reject('git add tests/t1.py')
        self.archive();self.allow('git worktree remove .dryforge/worktrees/T1')
        (self.root/'.dryforge/001/spec.md').write_text('changed')
        self.reject('git worktree remove .dryforge/worktrees/T1')

    def test_final_integration_requires_accepted_commit_and_unchanged_main(self):
        self.setup_cycle();self.feature();self.task()
        self.execute('git merge --no-ff dryforge/task-words -m integrate')
        self.reject('git checkout main')
        self.report();self.transition('accept',basis='reviewed');self.execute('git checkout main')
        (self.root/'tests/unreviewed.py').write_text('x=1\n')
        self.git('add','tests/unreviewed.py');self.git('commit','-qm','main moved')
        self.reject('git merge --no-ff dryforge/statistics -m integrate')

    def test_archive_cannot_hide_changed_active_documents(self):
        self.setup_cycle();self.feature();self.task()
        self.execute('git merge --no-ff dryforge/task-words -m integrate')
        self.report();self.transition('accept',basis='reviewed');self.archive()
        (self.root/'.dryforge/spec.md').write_text('stale active replacement')
        self.reject('git worktree remove .dryforge/worktrees/T1')

    def test_phase_change_invalidates_queued_approval(self):
        self.setup_cycle();self.feature()
        rid,_,answer=self.request(command='git add tests/__init__.py');self.store.answer('w',rid,answer)
        self.report()
        with self.assertRaises(BridgeError):self.store.take_answer('w','owner',rid)

    def test_return_to_go_after_rework_does_not_revive_old_allow(self):
        self.setup_cycle();self.feature()
        rid,_,answer=self.request(command='git add tests/__init__.py');self.store.answer('w',rid,answer)
        self.report()
        self.transition('rework',basis='review correction',feedback_ref='review',digest=self.s['cycle']['digest'])
        with self.assertRaises(BridgeError):self.store.take_answer('w','owner',rid)

    def test_queued_go_rechecks_binding_and_rejects_other_session(self):
        self.setup_cycle();self.s['cycle']['stage']='APPROVED';self.save()
        from runtime_bridge.controller import validate_dispatch
        body=fixtures.prepare(self.config,'sid','go','approved Go',self.path,'c1')
        with self.assertRaises(BridgeError):fixtures.prepare(self.config,'other','go','wrong',self.path,'c1')
        self.s['cycle']['runtime_binding']['tasks']['T2']='dryforge/task-another';self.save()
        with self.assertRaises(BridgeError):validate_dispatch(self.config,body)

    def test_changed_feature_after_acceptance_blocks_cleanup(self):
        self.setup_cycle();self.feature();self.task()
        self.execute('git merge --no-ff dryforge/task-words -m integrate')
        self.report();self.transition('accept',basis='reviewed')
        (self.root/'tests/later.py').write_text('x=1\n');self.git('add','tests/later.py');self.git('commit','-qm','later')
        self.reject('git worktree remove .dryforge/worktrees/T1')

    def test_v4_migration_keeps_document_only_scope_without_cycle_binding(self):
        # Exercise the policy adapter boundary; full Migration stage gates are
        # covered by test_migration_orchestration.
        g=self.setup_cycle(bind=False);g['paths']+=['docs']
        payload={'tool':'Write','input':{'file_path':str(self.root/'docs/architecture.md')}}
        result=policy.classify(payload,self.root,g,cycle={'kind':'migration'})
        self.assertEqual(result['operation'],'workspace_edit')
        with self.assertRaises(policy.PolicyError):
            policy.classify(self.host_request(self.root,'git checkout -b dryforge/statistics'),self.root,g,cycle={'kind':'migration'})

    def test_greenfield_uses_main_as_cycle_without_feature_checkout(self):
        self.setup_cycle(greenfield=True);self.task()
        self.execute('git merge --no-ff dryforge/task-words -m integrate')
        self.report();self.transition('accept',basis='reviewed');self.archive()
        self.execute('git worktree remove .dryforge/worktrees/T1');self.execute('git branch -d dryforge/task-words')
        self.assertEqual(self.git('branch','--show-current'),'main')


if __name__ == '__main__':unittest.main()
