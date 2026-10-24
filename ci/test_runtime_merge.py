"""Bounded exact-commit Go integration: real Git worktrees, no authenticated models."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'src/skills/mission/scripts'
sys.path.insert(0, str(SCRIPTS))
from runtime_merge import inspect_merge
from runtime_permissions import git_read, scoped_path, require, PolicyError


class MergeBoundaryTests(unittest.TestCase):
    def git(self, root, *argv):
        return subprocess.run(['git', '-C', str(root), *argv], check=True,
                              capture_output=True).stdout.decode().strip()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name) / 'repo'
        self.base.mkdir()
        self.git(self.base, 'init', '-q', '-b', 'main')
        self.git(self.base, 'config', 'user.name', 'Fixture')
        self.git(self.base, 'config', 'user.email', 'fixture@example.invalid')
        (self.base / '.gitignore').write_text('.dryforge/\n')
        self.git(self.base, 'add', '.gitignore')
        self.git(self.base, 'commit', '-qm', 'initial')
        self.wt = self.base / '.dryforge/worktrees/T1'
        self.wt.parent.mkdir(parents=True)
        self.git(self.base, 'worktree', 'add', '-q', '-b', 'dryforge/c1-T1',
                 str(self.wt), 'HEAD')
        (self.wt / 'memo_cli').mkdir()
        (self.wt / 'memo_cli/domain.py').write_text('value = 1\n')
        self.git(self.wt, 'add', 'memo_cli/domain.py')
        self.git(self.wt, 'commit', '-qm', 'T1 implementation')
        self.sha = self.git(self.wt, 'rev-parse', 'HEAD')
        self.policy = dict(version=3, go_worktrees=True, operations=['git_merge'],
                           paths=['memo_cli', 'tests'], integration_branch='main')

    def tearDown(self):
        self.temp.cleanup()

    def registered(self, base, wt, policy):
        data = git_read(base, 'worktree', 'list', '--porcelain', '-z')
        require(b'worktree ' + str(wt).encode() + b'\0' in data,
                'unregistered worktree')
        return {'root': str(wt)}

    def classify(self, source=None, policy=None):
        return inspect_merge(
            self.base, ['git', 'merge', '--no-ff', source or self.sha, '-m', 'Merge T1'],
            policy or self.policy, git_read, self.registered, scoped_path, require)

    def test_registered_go_task_commit_passes_only_with_v3_grant(self):
        result = self.classify()
        self.assertEqual(result['operation'], 'git_merge')
        self.assertEqual(result['paths'], ['memo_cli/domain.py'])
        self.assertEqual(result['merge_task_worktree'], str(self.wt))
        self.assertEqual(result['merge_source'], self.sha)

    def test_dirty_destination_blocks(self):
        (self.base / 'untracked').write_text('dirty')
        with self.assertRaisesRegex(PolicyError, 'clean destination'):
            self.classify()

    def test_destination_branch_is_exact(self):
        with self.assertRaisesRegex(PolicyError, 'destination branch'):
            self.classify(policy=dict(self.policy, integration_branch='other'))

    def test_only_dryforge_task_branches(self):
        self.git(self.wt, 'branch', '-m', 'outside/T1')
        with self.assertRaisesRegex(PolicyError, 'Dryforge task branch'):
            self.classify()

    def test_out_of_scope_file_blocks(self):
        (self.wt / 'outside.py').write_text('secret = 1\n')
        self.git(self.wt, 'add', 'outside.py')
        self.git(self.wt, 'commit', '-qm', 'outside scope')
        self.sha = self.git(self.wt, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(PolicyError, 'outside delegated paths'):
            self.classify()

    def test_symlink_entries_blocked(self):
        (self.wt / 'memo_cli/link').symlink_to('/etc/passwd')
        self.git(self.wt, 'add', 'memo_cli/link')
        self.git(self.wt, 'commit', '-qm', 'symlink')
        self.sha = self.git(self.wt, 'rev-parse', 'HEAD')
        with self.assertRaises(PolicyError):
            self.classify()

    def test_unregistered_or_wrong_source_blocked(self):
        with self.assertRaises(PolicyError):
            self.classify(source='0' * 40)
        self.git(self.base, 'worktree', 'remove', '--force', str(self.wt))
        with self.assertRaises(PolicyError):
            self.classify()

    def test_previous_v2_grant_does_not_gain_merge(self):
        with self.assertRaisesRegex(PolicyError, 'separately approved v3'):
            self.classify(policy=dict(self.policy, version=2))


if __name__ == '__main__':
    unittest.main()
