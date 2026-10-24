"""Real local Git operations with synthetic grants; not live model acceptance."""
import subprocess
import unittest
from ci import test_runtime_permissions as fixtures

policy = fixtures.policy
BridgeError = fixtures.BridgeError


class GoDelegationTests(unittest.TestCase):
    setUp = fixtures.DelegationTests.setUp
    tearDown = fixtures.DelegationTests.tearDown
    save = fixtures.DelegationTests.save
    event = fixtures.DelegationTests.event
    request = fixtures.DelegationTests.request
    host_request = fixtures.DelegationTests.host_request
    allow = fixtures.DelegationTests.allow

    def git(self, *args, cwd=None):
        return subprocess.check_output(['git', '-C', str(cwd or self.root), *args],
                                       stderr=subprocess.PIPE, text=True).strip()

    def setup_go(self):
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.root/'.gitignore').write_text('.dryforge/\n')
        self.git('add', '.gitignore', 'memo_cli/__init__.py', 'tests/__init__.py')
        self.git('commit', '-qm', 'base')
        self.git('branch', '-M', 'main')
        g = dict(fixtures.worktree_grant(), version=3,
                 go_workflow={'base_branch':'main', 'branch_prefix':'dryforge/'})
        g['operations'] = g['operations'] + ['git_worktree_add', 'git_merge',
                                            'git_worktree_remove', 'git_branch_delete']
        self.event(g)
        return g

    def task(self):
        wt = self.root/'.dryforge/worktrees/T1'
        self.git('worktree', 'add', '-b', 'dryforge/T1', str(wt), 'main')
        (wt/'tests/new.py').write_text('value = 1\n')
        self.git('add', 'tests/new.py', cwd=wt)
        self.git('commit', '-qm', 'task', cwd=wt)
        return wt, self.git('rev-parse', 'HEAD', cwd=wt)

    def reject(self, cmd):
        rid, _, answer = self.request(command=cmd)
        with self.assertRaises(BridgeError):
            self.store.answer('w', rid, answer)

    def test_actual_create_integrate_remove_and_branch_cleanup(self):
        self.setup_go()
        wt = self.root/'.dryforge/worktrees/T1'
        self.allow(f'git worktree add -b dryforge/T1 {wt} main')
        wt, head = self.task()
        self.allow(f'git merge --no-ff {head} -m "Integrate T1"')
        self.git('merge', '--no-ff', head, '-m', 'Integrate T1')
        self.assertEqual((self.root/'tests/new.py').read_text(), 'value = 1\n')
        self.allow(f'git worktree remove {wt}')
        self.git('worktree', 'remove', str(wt))
        self.allow('git branch -d dryforge/T1')
        self.git('branch', '-d', 'dryforge/T1')

    def test_old_grant_does_not_gain_go_lifecycle_rights(self):
        self.setup_go(); self.event(fixtures.worktree_grant())
        self.reject(f'git worktree add -b dryforge/T1 {self.root}/.dryforge/worktrees/T1 main')

    def test_merge_requires_registered_task_allowed_files_and_regular_modes(self):
        self.setup_go(); wt, head = self.task()
        self.reject('git merge --no-ff main -m no-op')
        (wt/'outside.txt').write_text('outside grant')
        self.git('add', 'outside.txt', cwd=wt); self.git('commit', '-qm', 'outside', cwd=wt)
        self.reject(f'git merge --no-ff {self.git("rev-parse", "HEAD", cwd=wt)} -m bad')
        self.git('reset', '--hard', head, cwd=wt)
        (wt/'tests/link').symlink_to('/tmp')
        self.git('add', 'tests/link', cwd=wt); self.git('commit', '-qm', 'link', cwd=wt)
        self.reject(f'git merge --no-ff {self.git("rev-parse", "HEAD", cwd=wt)} -m bad')

    def test_merge_target_cannot_move_after_allow(self):
        self.setup_go(); wt, _ = self.task()
        rid, _, answer = self.request(command='git merge --no-ff dryforge/T1 -m integrate')
        self.store.answer('w', rid, answer)
        (wt/'tests/new.py').write_text('value = 2\n')
        self.git('add', 'tests/new.py', cwd=wt); self.git('commit', '-qm', 'changed', cwd=wt)
        with self.assertRaises(BridgeError): self.store.take_answer('w', 'owner', rid)

    def test_base_cannot_move_between_review_and_execution(self):
        self.setup_go()
        wt = self.root/'.dryforge/worktrees/T1'
        rid, _, answer = self.request(command=f'git worktree add -b dryforge/T1 {wt} main')
        self.store.answer('w', rid, answer)
        (self.root/'tests/base.py').write_text('changed = True\n')
        self.git('add', 'tests/base.py'); self.git('commit', '-qm', 'changed base')
        with self.assertRaises(BridgeError): self.store.take_answer('w', 'owner', rid)

    def test_remove_retains_unmerged_dirty_untracked_and_ignored_data(self):
        self.setup_go(); wt, head = self.task()
        self.reject(f'git worktree remove {wt}')
        self.git('merge', '--no-ff', head, '-m', 'integrate')
        for path in ('tests/new.py', 'valuable.txt', '.dryforge/evidence.json'):
            p = wt/path; p.parent.mkdir(parents=True, exist_ok=True)
            before = p.read_bytes() if p.exists() else None
            p.write_text('preserve me')
            self.reject(f'git worktree remove {wt}')
            if before is None: p.unlink()
            else: p.write_bytes(before)
        self.reject(f'git worktree remove --force {wt}')
        self.reject('git branch -D dryforge/T1')
        self.reject('git branch -d dryforge/T1')  # still checked out

    def test_add_rejects_outside_paths_wrong_base_and_existing_branches(self):
        self.setup_go()
        for cmd in (f'git worktree add -b dryforge/T1 {self.root}/other main',
                    f'git worktree add -b unrelated {self.root}/.dryforge/worktrees/T1 main',
                    f'git worktree add -b dryforge/T1 {self.root}/.dryforge/worktrees/T1 HEAD~1',
                    f'git worktree add -B dryforge/T1 {self.root}/.dryforge/worktrees/T1 main'):
            self.reject(cmd)
        self.git('branch', 'dryforge/T1')
        self.reject(f'git worktree add -b dryforge/T1 {self.root}/.dryforge/worktrees/T1 main')

    def test_python_bytecode_flag_remains_an_exact_argv_grant(self):
        g = fixtures.worktree_grant()
        g['verification_commands'] = [['python3', '-B', '-m', 'unittest', 'discover', '-s', 'tests']]
        self.event(g)
        self.allow('python3 -B -m unittest discover -s tests')
        self.reject('python3 -m unittest discover -s tests')
        self.reject('python3 -B -c print(1)')


if __name__ == '__main__': unittest.main()
