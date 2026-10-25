"""Real local files, Git, SQLite and CLI; synthetic consent, not live model E2E."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT/'src/skills/init/scripts'
sys.path.insert(0, str(SCRIPTS))
import mission_state as ledger
from runtime_bridge.controller import prepare, prompt_for, validate_dispatch
from runtime_bridge.store import Store, BridgeError, digest
from test_runtime_bridge import config
from test_mission_state import contract


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.root/'.gitignore').write_text('.dryforge/\n')
        self.git('add', '.gitignore'); self.git('commit', '-qm', 'initial')
        c = contract(); c['workspace'] = str(self.root)
        c['delegated_actions'].append('migration')
        self.state = ledger.init_state(c)
        self.path = self.root/'.dryforge/mission/state.json'
        self.path.parent.mkdir(parents=True)
        self.counter = 0
        self.save()
        self.cfg = config(self.root)
        self.store = Store(self.root/'.dryforge/mission/runtime')
        self.store.create('w', self.cfg); self.store.attach('w', 'owner')
        self.store.bind('w', 'owner', 'sid'); self.store.state('w', 'owner', 'IDLE')

    def tearDown(self):
        self.store.close(); self.tmp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args],
                                       stderr=subprocess.PIPE, text=True).strip()

    def save(self):
        self.path.write_text(json.dumps(self.state))

    def event(self, op, actor='L1', **values):
        self.counter += 1
        e = dict(id=f'e{self.counter}', op=op, actor=actor, mission_id='demo',
                 expected_revision=self.state['revision'])
        if self.state['cycle']:
            e['cycle_id'] = self.state['cycle']['id']
            if actor == 'L2': e['session_id'] = self.state['cycle']['session_id']
        e.update(values)
        self.state = ledger.apply(self.state, e); self.save()
        return e

    def start(self, kind='migration', sid='sid', reuse=False):
        self.event('start', kind=kind, cycle_id=f'c{len(self.state["cycles"])+1}',
                   session_id=sid, reuse=reuse, session_resumable=True, context='sufficient',
                   goal='Prepare existing codebase docs', checkpoint_ref='git:initial',
                   basis='fixture approved preparation', need_ref='fixture existing code inspection',
                   capabilities={k:True for k in ledger.CAPABILITIES})

    def dispatch(self):
        self.start()
        body = prepare(self.cfg, 'sid', 'migration', 'Prepare project docs', self.path, 'c1')
        self.store.enqueue('w', 'm', body); self.store.claim('w', 'owner')
        return body

    def artifacts(self):
        paths = ['AGENTS.md','CLAUDE.md','docs/architecture.md','.dryforge/status.json','.gitignore']
        for name in paths[:-1]:
            p = self.root/name; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('{}\n' if name.endswith('.json') else '# Fixture project\n')
        return paths

    def result(self, paths=None, **overrides):
        paths = paths or self.artifacts()
        values = dict(paths=paths, digest=ledger.migration_digest(self.root, paths),
                      result_ref='fixture:docs', blockers=[], children_quiescent=True,
                      checks=[dict(command='fixture documentation inspection',exit_code=0,observed=True)],
                      review=dict(independent=True,evidence_ref='fixture:independent-review'))
        values.update(overrides)
        self.event('result', 'L2', **values)
        return values['digest']

    def accept_close(self):
        d = self.result()
        self.event('accept', digest=d, basis='fixture read actual docs')
        self.event('close', 'L2', children_quiescent=True, checkpoint_ref='fixture:commit',
                   handoff_ref='fixture:review-and-checkpoint')
        self.event('evaluate', decision='CONTINUE', progress=True, basis='product work remains')

    def grant(self):
        p = dict(version=1,operations=['workspace_edit','git_add','git_commit'],
                 paths=['AGENTS.md','CLAUDE.md','docs','.gitignore','memo_cli'],
                 verification_commands=[],trust_workspace_code=True)
        self.event('runtime_policy', 'human', policy=p, approval_ref='FIXTURE-ONLY',
                   basis='fixture documentation editing and checkpoint',
                   expected_policy_digest=digest(self.state.get('runtime_authority')))

    def request(self, payload, kind='permission'):
        rid = self.store.request('w','owner','m',kind,payload)
        req = next(r for r in self.store.pending('w') if r['id'] == rid)
        answer = dict(principal='L1',action='answer' if kind=='question' else 'allow',
                      basis='fixture grounded decision',session_id='sid',request_digest=req['fingerprint'],
                      policy_digest=digest(self.state.get('runtime_authority')))
        return rid, answer

    def edit(self, path):
        return {'tool':'Write','input':{'file_path':str(self.root/path),'content':'fixture'}}

    def command(self, cmd):
        return {'method':'item/commandExecution/requestApproval',
                'params':{'cwd':str(self.root),'command':cmd}}

    def test_complete_preparation_then_fresh_ready_go(self):
        self.dispatch(); self.accept_close()
        with self.assertRaisesRegex(ledger.ContractError, 'fresh session'):
            self.start('development', reuse=True)
        self.start('development', sid='new-sid')
        for name in ('spec.md','plan.md','handoff.md'):
            (self.root/'.dryforge'/name).write_text(name)
        d = ledger.document_digest(self.root/'.dryforge')
        self.event('ready','L2',digest=d)
        self.event('approve',digest=d,basis='fixture next task')
        body = prepare(self.cfg,'new-sid','go','Implement approved task',self.path,'c2')
        self.assertEqual(body['binding']['docs_digest'],d)
        self.assertEqual(self.state['schema_version'],4)

    def test_draft_and_legacy_contract_do_not_gain_migration(self):
        self.state = ledger.init_state(contract())
        with self.assertRaisesRegex(ledger.ContractError,'outside delegated authority'): self.start()
        c = contract(); c.pop('approved_by'); c.pop('approval_ref')
        c['workspace'] = str(self.root); c['delegated_actions'].append('migration')
        self.state = ledger.draft_state(c); self.save()
        with self.assertRaises(ledger.ContractError): self.start()
        self.event('activate','human',approval_ref='FIXTURE',basis='fixture reviewed',
                   expected_proposal_digest=ledger.proposal_digest(self.state))
        self.assertEqual(self.state['schema_version'],4)
        self.start()

    def test_ready_go_cannot_run_in_migration(self):
        self.dispatch()
        for kind in ('ready','go'):
            with self.subTest(kind=kind), self.assertRaises(BridgeError):
                prepare(self.cfg,'sid',kind,'wrong phase',self.path,'c1')
        with self.assertRaises(ledger.ContractError): self.event('go','L2',digest='a'*64)

    def test_migration_selects_installed_skill_and_preserves_caller_text(self):
        body = self.dispatch(); prompt, skill = prompt_for(self.cfg,body)
        self.assertEqual(skill,{'name':'dryforge:migration'})
        self.assertEqual(prompt,body['text'])
        for private in ('You are L2','L1',str(self.path)):
            self.assertNotIn(private,prompt)

    def test_queued_migration_and_wrong_session_revalidated(self):
        body = self.dispatch()
        with self.assertRaises(BridgeError):
            prepare(self.cfg,'other','migration','wrong session',self.path,'c1')
        self.state['contract']['goal'] = 'changed'; self.save()
        with self.assertRaises(BridgeError): validate_dispatch(self.cfg,body)

    def test_questions_relay_and_pending_decision_blocks_result(self):
        self.dispatch()
        rid, answer = self.request({'method':'item/tool/requestUserInput','params':{}},'question')
        answer['answers'] = {'q':{'answers':['existing policy']}}
        self.store.answer('w',rid,answer)
        self.assertEqual(self.store.take_answer('w','owner',rid),answer)
        self.event('question','L2',request_id='q',question='Existing rule?',scope='answer')
        with self.assertRaises(ledger.ContractError): self.result()
        self.event('answer',request_id='q',answer='Original intent',basis='fixture')
        self.result()

    def test_result_requires_independent_review_and_quiescence(self):
        self.start()
        for changes in ({'review':{'independent':False}}, {'children_quiescent':False},
                        {'checks':[]}, {'blockers':['unresolved']}):
            with self.subTest(changes=changes), self.assertRaises(ledger.ContractError):
                self.result(**changes)

    def test_result_and_accept_recheck_actual_document_bytes(self):
        self.start(); paths = self.artifacts()
        d = ledger.migration_digest(self.root,paths)
        (self.root/'AGENTS.md').write_text('changed')
        with self.assertRaisesRegex(ledger.ContractError,'artifacts changed'):
            self.result(paths,digest=d)
        d = self.result(paths)
        (self.root/'AGENTS.md').write_text('changed again')
        with self.assertRaisesRegex(ledger.ContractError,'review is stale'):
            self.event('accept',digest=d,basis='fixture')
        d = self.result(paths); self.event('accept',digest=d,basis='fixture reread')
        (self.root/'AGENTS.md').write_text('after acceptance')
        with self.assertRaises(ledger.ContractError):
            self.event('close','L2',children_quiescent=True,checkpoint_ref='fixture',handoff_ref='fixture')

    def test_artifact_scope_and_symlinks_rejected(self):
        paths = self.artifacts()
        for extra in ('../outside.md','.dryforge/mission/state.json','memo_cli/app.py'):
            with self.subTest(extra=extra), self.assertRaises(ledger.ContractError):
                ledger.migration_digest(self.root,paths+[extra])
        (self.root/'AGENTS.md').unlink(); (self.root/'AGENTS.md').symlink_to('CLAUDE.md')
        with self.assertRaises(ledger.ContractError): ledger.migration_digest(self.root,paths)

    def test_migration_not_repeated_or_restarted_on_interruption(self):
        self.dispatch()
        self.event('interrupt','host',session_id='sid',reason='fixture disconnect')
        with self.assertRaises(BridgeError): prepare(self.cfg,'sid','migration','retry',self.path,'c1')
        with self.assertRaises(ledger.ContractError):
            self.event('resume',session_id='replacement',reconciled=True,checkpoint_ref='fixture')
        self.event('resume',session_id='sid',reconciled=True,checkpoint_ref='fixture')
        self.accept_close()
        with self.assertRaisesRegex(ledger.ContractError,'already completed'): self.start(sid='next')

    def test_doc_edits_need_policy_and_cannot_write_product_or_private_state(self):
        self.dispatch()
        rid, a = self.request(self.edit('docs/new.md'))
        with self.assertRaises(BridgeError): self.store.answer('w',rid,a)
        self.grant()
        rid, a = self.request(self.edit('docs/new.md'))
        self.store.answer('w',rid,a); self.store.take_answer('w','owner',rid)
        for payload in (self.edit('memo_cli/code.py'),self.edit('.dryforge/status.json'),
                        self.command('git commit -m early')):
            rid,a = self.request(payload)
            with self.assertRaises(BridgeError): self.store.answer('w',rid,a)
        self.assertEqual(self.state['schema_version'],4)

    def test_permission_rechecks_pending_questions_and_revocation(self):
        self.dispatch(); self.grant()
        rid,a = self.request(self.edit('docs/new.md')); self.store.answer('w',rid,a)
        self.event('question','L2',request_id='q',question='Unresolved?',scope='answer')
        with self.assertRaises(BridgeError): self.store.take_answer('w','owner',rid)
        self.event('answer',request_id='q',answer='resolved',basis='fixture')
        rid,a = self.request(self.edit('docs/other.md')); self.store.answer('w',rid,a)
        self.event('runtime_policy','human',policy=None,approval_ref='FIXTURE',basis='revoked',
                   expected_policy_digest=digest(self.state['runtime_authority']))
        with self.assertRaises(BridgeError): self.store.take_answer('w','owner',rid)

    def test_accepted_checkpoint_only_stages_reviewed_docs_and_rechecks_bytes(self):
        self.dispatch(); self.grant()
        d = self.result(); self.event('accept',digest=d,basis='fixture')
        rid,a = self.request(self.command('git add AGENTS.md'))
        self.store.answer('w',rid,a); self.store.take_answer('w','owner',rid)
        self.git('add','AGENTS.md')
        rid,a = self.request(self.command('git commit -m harness'))
        self.store.answer('w',rid,a)
        (self.root/'AGENTS.md').write_text('after decision')
        with self.assertRaises(BridgeError): self.store.take_answer('w','owner',rid)

    def test_real_cli_enqueues_migration_and_computes_digest(self):
        self.start()
        goal = self.root/'goal.txt'; goal.write_text('Prepare existing project')
        run = subprocess.run([sys.executable,'-B',str(SCRIPTS/'worker_runtime.py'),'send',
            '--workspace',str(self.root),'--worker','w','--id','cli-migration','--kind','migration',
            '--text-file',str(goal),'--ledger',str(self.path),'--cycle','c1'],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(self.store.message('w','cli-migration')['body']['kind'],'migration')
        paths = self.artifacts(); p = self.root/'paths.json'; p.write_text(json.dumps(paths))
        run = subprocess.run([sys.executable,'-B',str(SCRIPTS/'mission_state.py'),'migration-digest',
            '--workspace',str(self.root),'--paths-file',str(p)],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(run.stdout.strip(),ledger.migration_digest(self.root,paths))


if __name__ == '__main__': unittest.main()
