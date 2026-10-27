"""Run-record rules and refusals of ouroboros_cli.py against real temp git repos. No live host."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'src/skills/init/scripts'
CLI = SCRIPTS / 'ouroboros_cli.py'
sys.path.insert(0, str(SCRIPTS))
from ouroboros import core, store  # noqa: E402

SCENARIO = """# Scenarios

## Scenarios

### First run
1. The user installs the tool — step: install
2. The user runs `tool init` and answers the prompts — step: configure
3. The user runs `tool build` and sees the output file — step: build

### Rebuild
- The user edits the config -- step: configure
- The user runs `tool build` again - step: build

## Workflow
- install: put the tool on the PATH
- configure: write the config file from the answers
- build: produce the output from the config
"""

VALIDATION = """# Validation

## Items

### V1 Build produces the output
**Behavior:** `tool build` writes out/result.txt with the configured name.
**Environment:** macOS or Linux, Python 3.11, no services.
**Evidence:** `python3 -m tool build && cat out/result.txt` prints the name.
**Cost:** fast
covers: build

### V2 Install works on a clean machine
- Behavior: the tool is on PATH after install.
- Environment: a fresh container with Python 3.11.
- Evidence: `which tool` prints a path and `tool --version` exits 0.
- Cost: slow/hard, needs a clean container.
covers: install
"""

SPEC = """# Spec

## Users
Developers who build the thing locally.

## UI references
none

## Outline
- cli: parses commands and dispatches
- builder: turns the config into the output

## Efficient checks
- V2: run the install script in a temp venv instead of a container.
"""

DELEGATION = """# Delegation

## Delegated judgment
Everything after approval.

## Models
- L2: {l2}
- L3: {l3}

## Limits
- max cycles: {cycles}
- max stalled cycles: {stalled}
- budget usd: {budget}

## Workspace
/tmp/project
"""

NAMES = ('scenario.md', 'validation.md', 'spec.md', 'delegation.md')


def proposal_set(cycles=3, stalled=2, budget='10', l2='default', l3='default', **override):
    """The four valid proposal texts; `override` replaces whole files by name (scenario=..., spec=...)."""
    parts = {'scenario.md': SCENARIO, 'validation.md': VALIDATION, 'spec.md': SPEC,
             'delegation.md': DELEGATION.format(cycles=cycles, stalled=stalled, budget=budget, l2=l2, l3=l3)}
    for key, text in override.items():
        parts[key + '.md'] = text
    return parts


def with_limits(limits_text, **kw):
    """The set with delegation.md's `## Limits` body replaced verbatim."""
    parts = proposal_set(**kw)
    head, rest = parts['delegation.md'].split('## Limits\n')
    tail = rest[rest.index('## Workspace'):]
    parts['delegation.md'] = head + '## Limits\n' + limits_text + '\n\n' + tail
    return parts


def set_sha(parts):
    return core.set_digest([(name, parts[name].encode()) for name in NAMES])


class Workspace:
    """A real git repo in a temp dir with `.dryforge/` ignored, plus CLI helpers."""

    def __init__(self, ignore=True, git=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name).resolve()
        if git:
            subprocess.run(['git', 'init', '-q', str(self.path)], check=True)
        if ignore:
            (self.path / '.gitignore').write_text('.dryforge/\n')
        self.owner = os.getpid()
        self.files = 0

    def cleanup(self):
        self.tmp.cleanup()

    def file(self, text, suffix='.md'):
        self.files += 1
        p = self.path / f'input-{self.files}{suffix}'
        p.write_bytes(text if isinstance(text, bytes) else text.encode())
        return str(p)

    def run(self, *args, owner=None, workspace=None):
        cmd = [sys.executable, '-B', str(CLI), '--workspace', workspace or str(self.path),
               '--owner', str(owner or self.owner), *args]
        r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        out = json.loads(r.stdout) if r.stdout.strip() else None
        return r.returncode, out

    def ok(self, *args, **kw):
        code, out = self.run(*args, **kw)
        self.assert_code(code, 0, out)
        return out

    def blocked(self, *args, **kw):
        code, out = self.run(*args, **kw)
        self.assert_code(code, 2, out)
        assert out['status'] == 'BLOCKED', out
        return out

    @staticmethod
    def assert_code(code, want, out):
        if code != want:
            raise AssertionError(f'exit {code} != {want}: {out}')

    # convenience
    def draft_args(self, parts):
        args = []
        for name, text in parts.items():
            args += ['--' + name.removesuffix('.md'), self.file(text)]
        return args

    def draft(self, parts=None, **kw):
        """Draft the whole set (default: the valid fixture) or, with a partial dict, revise that subset."""
        return self.ok('draft', *self.draft_args(parts or proposal_set()), **kw)

    def approve_fresh(self, parts=None):
        self.draft(parts)
        self.ok('shown')
        return self.ok('approve')

    def make_legacy(self, status='DRAFT'):
        """Turn the current record into a cycles 001-002 single-file record with the given status."""
        for name in NAMES:
            (self.private / name).unlink()
        (self.private / 'proposal.md').write_text('# Proposal\n\n## Goal\nold\n')
        run = self.record()
        run['status'] = status
        run.pop('models', None)
        run.pop('beta_cycles', None)
        (self.private / 'run.json').write_text(json.dumps(run))
        return run

    @property
    def private(self):
        return self.path / '.dryforge' / 'ouroboros'

    def record(self):
        return json.loads((self.private / 'run.json').read_text())

    def events(self):
        p = self.private / 'events.jsonl'
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]

    def kinds(self):
        return [e['kind'] for e in self.events()]

    def start_cycle(self, kind='development', checkpoint='a' * 40):
        return self.ok('cycle-start', '--kind', kind, '--goal', self.file('cycle goal'), '--checkpoint', checkpoint)

    def evaluate(self, decision):
        return self.ok('evaluate', '--decision', decision, '--basis', self.file('because'))


class Base(unittest.TestCase):
    def setUp(self):
        self.ws = Workspace()
        self.addCleanup(self.ws.cleanup)


class DraftTests(Base):
    def test_draft_creates_private_dir_with_modes_and_draft_record(self):
        out = self.ws.draft()
        self.assertEqual(out['status'], 'DRAFT')
        priv = self.ws.private
        self.assertEqual(stat.S_IMODE(priv.stat().st_mode), 0o700)
        for name in ('run.json', 'events.jsonl', 'owner.json', *NAMES):
            self.assertEqual(stat.S_IMODE((priv / name).stat().st_mode), 0o600, name)
        run = self.ws.record()
        self.assertEqual(set(run), {'run_id', 'workspace', 'status', 'proposal_digest_shown', 'approvals', 'limits',
                                    'spent_usd', 'stalled_cycles', 'host', 'session', 'cycles', 'stopped_reason',
                                    'stopped_at', 'models', 'beta_cycles'})
        self.assertEqual(run['status'], 'DRAFT')
        self.assertEqual(run['workspace'], str(self.ws.path))
        self.assertIsNone(run['proposal_digest_shown'])
        self.assertEqual(run['approvals'], [])
        self.assertEqual(run['host'], 'claude')
        self.assertEqual(run['session'], dict(id=None, started=None, reason=None, cost_total_usd=0))
        self.assertEqual(run['spent_usd'], 0)
        self.assertEqual(run['models'], dict(l2='default', l3='default'))
        self.assertEqual(run['beta_cycles'], 0)
        for name in NAMES:
            self.assertEqual((priv / name).read_text(), proposal_set()[name], name)
        self.assertFalse((priv / 'proposal.md').exists())
        self.assertEqual(self.ws.kinds(), ['draft'])
        ev = self.ws.events()[0]
        self.assertEqual(ev['data']['proposal_digest'], set_sha(proposal_set()))
        self.assertEqual(set(ev['data']['files']), set(NAMES))
        owner = json.loads((priv / 'owner.json').read_text())
        self.assertEqual(owner['pid'], os.getpid())
        self.assertEqual(set(owner), {'pid', 'session_id', 'started'})
        self.assertIsNone(owner['session_id'])
        self.assertNotIn('schema', json.dumps(run))
        self.assertEqual(out['proposal_digest'], set_sha(proposal_set()))
        self.assertFalse(out['legacy'])

    def test_new_draft_needs_all_four_files(self):
        parts = proposal_set()
        del parts['spec.md']
        out = self.ws.blocked('draft', *self.ws.draft_args(parts))
        self.assertIn('spec', out['error'])
        self.assertFalse((self.ws.path / '.dryforge' / 'ouroboros' / 'run.json').exists())
        out = self.ws.blocked('draft', '--scenario', str(self.ws.path / 'missing.md'),
                              *self.ws.draft_args({k: v for k, v in proposal_set().items() if k != 'scenario.md'}))
        self.assertIn('missing.md', out['error'])

    def test_redraft_replaces_set_and_clears_shown(self):
        self.ws.draft()
        first = self.ws.record()['run_id']
        self.ws.ok('shown')
        self.assertIsNotNone(self.ws.record()['proposal_digest_shown'])
        self.assertTrue((self.ws.private / 'shown' / 'scenario.md').is_file())
        self.ws.draft(proposal_set(cycles=9))
        run = self.ws.record()
        self.assertEqual(run['run_id'], first)
        self.assertIsNone(run['proposal_digest_shown'])
        self.assertEqual((self.ws.private / 'delegation.md').read_text(), proposal_set(cycles=9)['delegation.md'])
        self.assertFalse((self.ws.private / 'shown' / 'scenario.md').exists())
        self.assertEqual(self.ws.kinds(), ['draft', 'shown', 'draft'])

    def test_revising_a_subset_keeps_the_other_files(self):
        self.ws.draft()
        self.ws.ok('shown')
        out = self.ws.draft({'delegation.md': proposal_set(cycles=9)['delegation.md']})
        self.assertIsNone(out['proposal_digest_shown'])
        self.assertEqual(out['proposal_digest'], set_sha(proposal_set(cycles=9)))
        for name in ('scenario.md', 'validation.md', 'spec.md'):
            self.assertEqual((self.ws.private / name).read_text(), proposal_set()[name], name)
        self.assertEqual((self.ws.private / 'delegation.md').read_text(), proposal_set(cycles=9)['delegation.md'])
        ev = self.ws.events()[-1]
        self.assertEqual(ev['kind'], 'draft')
        self.assertEqual(set(ev['data']['files']), set(NAMES))

    def test_draft_refused_when_dryforge_not_ignored(self):
        ws = Workspace(ignore=False)
        self.addCleanup(ws.cleanup)
        out = ws.blocked('draft', *ws.draft_args(proposal_set()))
        self.assertIn('.dryforge/', out['error'])
        self.assertFalse((ws.path / '.dryforge').exists())

    def test_draft_refused_when_only_json_is_ignored(self):
        ws = Workspace(ignore=False)
        self.addCleanup(ws.cleanup)
        (ws.path / '.gitignore').write_text('*.json\n')
        out = ws.blocked('draft', *ws.draft_args(proposal_set()))
        self.assertIn('.dryforge/', out['error'])
        self.assertFalse((ws.path / '.dryforge').exists())

    def test_draft_refused_outside_git_root(self):
        ws = Workspace(git=False)
        self.addCleanup(ws.cleanup)
        out = ws.blocked('draft', *ws.draft_args(proposal_set()))
        self.assertIn('git', out['error'])
        self.assertFalse((ws.path / '.dryforge').exists())
        sub = self.ws.path / 'sub'
        sub.mkdir()
        out = self.ws.blocked('draft', *self.ws.draft_args(proposal_set()), workspace=str(sub))
        self.assertIn('git', out['error'])

    def test_draft_revises_active_run(self):
        self.ws.approve_fresh()
        before = self.ws.record()
        out = self.ws.draft(proposal_set(cycles=5))
        self.assertEqual(out['status'], 'ACTIVE')
        self.assertIsNone(out['proposal_digest_shown'])
        self.assertEqual(out['proposal_digest'], set_sha(proposal_set(cycles=5)))
        run = self.ws.record()
        self.assertEqual((run['run_id'], run['status'], run['limits']), (before['run_id'], 'ACTIVE', before['limits']))
        self.assertEqual(run['approvals'], before['approvals'])
        self.assertEqual((self.ws.private / 'delegation.md').read_text(), proposal_set(cycles=5)['delegation.md'])
        self.assertFalse((self.ws.private / 'shown').exists())
        self.assertEqual(self.ws.kinds(), ['draft', 'shown', 'approve', 'draft'])
        self.assertFalse((self.ws.private / 'archive').exists())
        out = self.ws.blocked('approve')  # the revision must be shown first
        self.assertIn('shown', out['error'])

    def test_draft_revises_stopped_run_so_approve_can_resume_it(self):
        self.ws.approve_fresh()
        self.ws.ok('stop', '--reason', 'abort')
        old = self.ws.record()
        out = self.ws.draft(proposal_set(cycles=4))
        self.assertEqual(out['status'], 'STOPPED')
        run = self.ws.record()
        self.assertEqual((run['run_id'], run['status'], run['stopped_reason']), (old['run_id'], 'STOPPED', 'abort'))
        self.assertIsNone(run['proposal_digest_shown'])
        self.assertFalse((self.ws.private / 'archive').exists())
        self.ws.ok('shown')
        out = self.ws.ok('approve')
        self.assertEqual((out['status'], out['approval']), ('ACTIVE', 'amended'))
        self.assertEqual(self.ws.record()['limits']['max_cycles'], 4)

    def test_draft_archives_complete_run_and_starts_a_new_one(self):
        self.ws.approve_fresh()
        self.ws.start_cycle()
        self.ws.evaluate('COMPLETE')
        old = self.ws.record()
        (self.ws.private / 'workgraph.yaml').write_text('nodes: []\n')
        self.ws.draft(proposal_set(cycles=4))
        run = self.ws.record()
        self.assertNotEqual(run['run_id'], old['run_id'])
        self.assertEqual(run['status'], 'DRAFT')
        archived = self.ws.private / 'archive' / old['run_id']
        self.assertEqual(json.loads((archived / 'run.json').read_text())['status'], 'COMPLETE')
        for name in NAMES:
            self.assertEqual((archived / name).read_text(), proposal_set()[name], name)
            self.assertTrue((archived / 'shown' / name).is_file(), name)
            self.assertTrue((archived / 'approved' / name).is_file(), name)
        self.assertTrue((archived / 'workgraph.yaml').is_file())
        self.assertFalse((self.ws.private / 'workgraph.yaml').exists())
        kinds = [json.loads(l)['kind'] for l in (archived / 'events.jsonl').read_text().splitlines()]
        self.assertEqual(kinds[-1], 'archive')
        self.assertEqual(self.ws.kinds(), ['draft'])

    def test_archive_then_draft_starts_a_different_goal_after_a_stop(self):
        self.ws.approve_fresh()
        self.ws.ok('stop', '--reason', 'abort')
        old = self.ws.record()['run_id']
        self.ws.ok('archive')
        self.ws.draft(proposal_set(cycles=4))
        run = self.ws.record()
        self.assertNotEqual(run['run_id'], old)
        self.assertEqual((run['status'], run['approvals']), ('DRAFT', []))
        self.assertEqual(json.loads((self.ws.private / 'archive' / old / 'run.json').read_text())['status'], 'STOPPED')


class LegacyTests(Base):
    """Records from cycles 001-002 carry a single proposal.md; they are reported, archived or refused, never converted."""

    def test_show_reports_legacy_and_defaults_models(self):
        self.ws.draft()
        self.ws.make_legacy('DRAFT')
        out = self.ws.ok('show')
        self.assertTrue(out['legacy'])
        self.assertEqual(out['models'], dict(l2='default', l3='default'))
        self.assertEqual(out['beta_cycles'], 0)
        self.assertIsNone(out['proposal_digest'])
        out = self.ws.blocked('shown')
        self.assertIn('legacy', out['error'])
        out = self.ws.blocked('approve')
        self.assertIn('legacy', out['error'])

    def test_draft_archives_a_legacy_draft_complete_or_stopped_record(self):
        for status in ('DRAFT', 'COMPLETE', 'STOPPED'):
            with self.subTest(status=status):
                ws = Workspace()
                self.addCleanup(ws.cleanup)
                ws.draft()
                old = ws.make_legacy(status)
                out = ws.draft(proposal_set(cycles=4))
                self.assertEqual(out['status'], 'DRAFT')
                self.assertFalse(out['legacy'])
                run = ws.record()
                self.assertNotEqual(run['run_id'], old['run_id'])
                self.assertEqual(run['models'], dict(l2='default', l3='default'))
                archived = ws.private / 'archive' / old['run_id']
                self.assertEqual((archived / 'proposal.md').read_text(), '# Proposal\n\n## Goal\nold\n')
                self.assertEqual(json.loads((archived / 'run.json').read_text())['status'], status)
                self.assertFalse((ws.private / 'proposal.md').exists())
                self.assertEqual(ws.kinds(), ['draft'])
                ws.ok('shown'); ws.ok('approve')
                self.assertEqual(ws.record()['status'], 'ACTIVE')

    def test_legacy_active_record_is_refused_until_stopped(self):
        self.ws.draft()
        old = self.ws.make_legacy('ACTIVE')
        out = self.ws.blocked('draft', *self.ws.draft_args(proposal_set()))
        self.assertIn('legacy', out['error'])
        self.assertIn('stop --reason abort', out['error'])
        run = self.ws.record()
        self.assertEqual((run['run_id'], run['status']), (old['run_id'], 'ACTIVE'))
        self.assertTrue((self.ws.private / 'proposal.md').is_file())
        self.assertFalse((self.ws.private / 'archive').exists())
        self.ws.ok('stop', '--reason', 'abort')
        self.ws.draft()
        self.assertNotEqual(self.ws.record()['run_id'], old['run_id'])
        self.assertTrue((self.ws.private / 'archive' / old['run_id'] / 'proposal.md').is_file())

    def test_archive_accepts_a_legacy_draft(self):
        self.ws.draft()
        old = self.ws.make_legacy('DRAFT')
        out = self.ws.ok('archive')
        self.assertEqual(out['archived'], old['run_id'])
        self.assertTrue((self.ws.private / 'archive' / old['run_id'] / 'proposal.md').is_file())
        self.assertFalse((self.ws.private / 'run.json').exists())
        self.ws.draft()
        self.ws.blocked('archive')  # a four-file DRAFT is still not archivable


class ShownAndShowTests(Base):
    def test_shown_records_digest_and_copies(self):
        self.ws.draft()
        out = self.ws.ok('shown')
        self.assertEqual(out['proposal_digest_shown'], set_sha(proposal_set()))
        self.assertEqual(self.ws.record()['proposal_digest_shown'], set_sha(proposal_set()))
        shown = self.ws.private / 'shown'
        self.assertEqual(stat.S_IMODE(shown.stat().st_mode), 0o700)
        for name in NAMES:
            self.assertEqual((shown / name).read_text(), proposal_set()[name], name)
            self.assertEqual(stat.S_IMODE((shown / name).stat().st_mode), 0o600, name)
        self.assertEqual(self.ws.kinds(), ['draft', 'shown'])
        self.assertEqual(self.ws.events()[-1]['data']['digest'], set_sha(proposal_set()))

    def test_set_digest_layout(self):
        parts = [(name, proposal_set()[name].encode()) for name in NAMES]
        blob = b''.join(f'{name}\n{len(data)}\n'.encode() + data for name, data in parts)
        self.assertEqual(core.set_digest(parts), hashlib.sha256(blob).hexdigest())
        self.assertEqual(core.set_digest(list(reversed(parts))), core.set_digest(parts))  # fixed order
        with self.assertRaises(core.RecordError):
            core.set_digest(parts[:3])

    def test_show_summary(self):
        self.ws.draft()
        out = self.ws.ok('show')
        self.assertEqual(out['status'], 'DRAFT')
        self.assertEqual(out['proposal_digest'], set_sha(proposal_set()))
        self.assertIsNone(out['proposal_digest_shown'])
        self.assertIsNone(out['cycle'])
        self.assertEqual(out['counts'], dict(cycles=0, approvals=0, events=1))
        self.assertEqual(out['models'], dict(l2='default', l3='default'))
        self.assertFalse(out['legacy'])
        self.assertEqual(out['beta_cycles'], 0)
        self.assertIn('limits', out)
        self.assertIn('spent_usd', out)
        self.assertIn('session', out)
        self.assertIn('run_id', out)

    def test_show_without_run_is_blocked(self):
        self.ws.blocked('show')
        self.ws.blocked('shown')


class ApproveTests(Base):
    def test_nothing_proposed(self):
        out = self.ws.blocked('approve')
        self.assertIn('nothing proposed', out['error'])
        self.assertFalse((self.ws.path / '.dryforge').exists())
        self.ws.draft()
        (self.ws.private / 'spec.md').unlink()
        out = self.ws.blocked('shown')
        self.assertIn('nothing proposed', out['error'])
        out = self.ws.blocked('approve')
        self.assertIn('nothing proposed', out['error'])

    def test_never_shown_is_blocked(self):
        self.ws.draft()
        out = self.ws.blocked('approve')
        self.assertIn('shown', out['error'])
        self.assertEqual(self.ws.record()['status'], 'DRAFT')

    def test_changed_since_shown_prints_both_digests_and_per_file_diff(self):
        self.ws.draft()
        self.ws.ok('shown')
        (self.ws.private / 'delegation.md').write_text(proposal_set(cycles=7)['delegation.md'])
        out = self.ws.blocked('approve')
        self.assertEqual(out['shown_digest'], set_sha(proposal_set()))
        self.assertEqual(out['current_digest'], set_sha(proposal_set(cycles=7)))
        self.assertEqual(out['changed'], ['delegation.md'])
        self.assertEqual(list(out['diff']), ['delegation.md'])
        self.assertIn('-- max cycles: 3', out['diff']['delegation.md'])
        self.assertIn('+- max cycles: 7', out['diff']['delegation.md'])
        self.assertIn('shown/delegation.md', out['diff']['delegation.md'])
        self.assertEqual(self.ws.record()['status'], 'DRAFT')
        self.assertEqual(self.ws.kinds(), ['draft', 'shown'])
        (self.ws.private / 'spec.md').write_text(SPEC + '\n- extra: block\n')
        out = self.ws.blocked('approve')
        self.assertEqual(out['changed'], ['spec.md', 'delegation.md'])
        self.assertIn('+- extra: block', out['diff']['spec.md'])

    def test_draft_equal_activates(self):
        self.ws.draft()
        self.ws.ok('shown')
        out = self.ws.ok('approve')
        self.assertEqual(out['status'], 'ACTIVE')
        self.assertEqual(out['approval'], 'activated')
        run = self.ws.record()
        self.assertEqual(run['status'], 'ACTIVE')
        self.assertEqual(len(run['approvals']), 1)
        self.assertEqual(run['approvals'][0]['digest'], set_sha(proposal_set()))
        self.assertIn('time', run['approvals'][0])
        self.assertTrue(run['approvals'][0]['applied'])
        self.assertEqual(run['limits'], dict(max_cycles=3, max_stalled_cycles=2, budget_usd=10))
        self.assertEqual(run['models'], dict(l2='default', l3='default'))
        ev = self.ws.events()[-1]
        self.assertEqual((ev['kind'], ev['actor']), ('approve', 'human'))
        self.assertEqual(ev['data']['models'], dict(l2='default', l3='default'))

    def test_active_same_digest_is_noop_with_show_summary(self):
        self.ws.approve_fresh()
        before = self.ws.record()
        show = self.ws.ok('show')
        out = self.ws.ok('approve')
        self.assertEqual(out, show)
        self.assertEqual(self.ws.record(), before)
        self.assertEqual(self.ws.kinds().count('approve'), 1)

    def test_amendment_on_active_and_stopped(self):
        self.ws.approve_fresh()
        self.ws.draft({'delegation.md': proposal_set(cycles=5)['delegation.md']})
        self.ws.blocked('approve')  # revised but not re-shown
        self.ws.ok('shown')
        out = self.ws.ok('approve')
        self.assertEqual(out['approval'], 'amended')
        run = self.ws.record()
        self.assertEqual(run['status'], 'ACTIVE')
        self.assertEqual([a['digest'] for a in run['approvals']], [set_sha(proposal_set()), set_sha(proposal_set(cycles=5))])
        self.assertEqual(run['limits']['max_cycles'], 5)
        self.assertFalse(run['approvals'][-1]['applied'])
        self.assertEqual(self.ws.kinds()[-1], 'amend')
        self.assertEqual(self.ws.events()[-1]['actor'], 'human')
        self.ws.ok('stop', '--reason', 'abort')
        self.assertEqual(self.ws.record()['status'], 'STOPPED')
        self.ws.draft(proposal_set(cycles=6, l2='opus'))
        self.ws.ok('shown')
        out = self.ws.ok('approve')
        self.assertEqual(out['approval'], 'amended')
        run = self.ws.record()
        self.assertEqual(run['status'], 'ACTIVE')
        self.assertIsNone(run['stopped_reason'])
        self.assertEqual(len(run['approvals']), 3)
        self.assertEqual(run['limits']['max_cycles'], 6)
        self.assertEqual(run['models'], dict(l2='opus', l3='default'))

    def test_approve_on_stopped_with_same_digest_resumes(self):
        self.ws.approve_fresh()
        self.ws.start_cycle()
        self.ws.ok('stop', '--reason', 'abort')
        stopped = self.ws.record()
        self.assertEqual(stopped['status'], 'STOPPED')
        self.assertIsNotNone(stopped['stopped_at'])
        out = self.ws.ok('approve')
        self.assertEqual((out['status'], out['approval']), ('ACTIVE', 'resumed'))
        run = self.ws.record()
        self.assertEqual(run['status'], 'ACTIVE')
        self.assertIsNone(run['stopped_reason'])
        self.assertIsNone(run['stopped_at'])
        self.assertEqual([a['digest'] for a in run['approvals']], [set_sha(proposal_set())] * 2)
        self.assertTrue(run['approvals'][-1]['applied'])
        self.assertEqual(run['limits'], stopped['limits'])
        ev = self.ws.events()[-1]
        self.assertEqual((ev['kind'], ev['actor'], ev['data']['action']), ('approve', 'human', 'resumed'))
        self.assertIsNone(run['cycles'][0]['evaluation'])  # the aborted cycle is still open
        self.assertEqual(self.ws.ok('approve'), self.ws.ok('show'))  # ACTIVE + same digest stays a no-op
        self.assertEqual(self.ws.kinds().count('approve'), 2)

    def test_approve_writes_the_governing_set(self):
        self.ws.approve_fresh()
        approved = self.ws.private / 'approved'
        self.assertEqual(stat.S_IMODE(approved.stat().st_mode), 0o700)
        for name in NAMES:
            self.assertEqual((approved / name).read_text(), proposal_set()[name], name)
            self.assertEqual((approved / name).stat().st_mode & 0o777, 0o600, name)
        self.ws.draft({'spec.md': SPEC + '\nrevised\n'})
        self.assertEqual((approved / 'spec.md').read_text(), SPEC)  # a pending revision does not touch it
        self.ws.ok('shown')
        self.ws.ok('approve')
        self.assertEqual((approved / 'spec.md').read_text(), SPEC + '\nrevised\n')

    def test_complete_run_cannot_be_approved(self):
        self.ws.approve_fresh()
        self.ws.start_cycle()
        self.ws.evaluate('COMPLETE')
        self.assertEqual(self.ws.record()['status'], 'COMPLETE')
        self.ws.ok('shown')
        self.ws.blocked('approve')
        self.assertEqual(self.ws.record()['status'], 'COMPLETE')

    def test_section_headings_are_case_insensitive(self):
        parts = proposal_set(spec=SPEC.replace('## UI references', '## UI REFERENCES').replace('## Users', '## users'))
        self.ws.approve_fresh(parts)
        self.assertEqual(self.ws.record()['status'], 'ACTIVE')

    def test_models_parsing(self):
        cases = {
            ('default', 'default'): dict(l2='default', l3='default'),
            ('Default', 'claude-opus-4-1'): dict(l2='default', l3='claude-opus-4-1'),
            ('`sonnet`', 'haiku'): dict(l2='sonnet', l3='haiku'),
        }
        for (l2, l3), want in cases.items():
            with self.subTest(l2=l2, l3=l3):
                ws = Workspace()
                self.addCleanup(ws.cleanup)
                ws.approve_fresh(proposal_set(l2=l2, l3=l3))
                self.assertEqual(ws.record()['models'], want)
                self.assertEqual(ws.ok('show')['models'], want)

    def test_limits_parsing(self):
        cases = {
            'max cycles: 3\nmax stalled cycles: 2\nbudget usd: no cap': dict(max_cycles=3, max_stalled_cycles=2, budget_usd=None),
            '- Max cycles: 12\n- Max stalled cycles: 4\n- Budget USD: 2.5': dict(max_cycles=12, max_stalled_cycles=4, budget_usd=2.5),
            'Max cycles 3, max stalled cycles 1, budget (USD) $40': dict(max_cycles=3, max_stalled_cycles=1, budget_usd=40),
        }
        for limits, want in cases.items():
            with self.subTest(limits=limits):
                ws = Workspace()
                self.addCleanup(ws.cleanup)
                ws.approve_fresh(with_limits(limits))
                self.assertEqual(ws.record()['limits'], want)
        for limits in ('max cycles: 3\nbudget usd: 5', 'max stalled cycles: 1\nbudget usd: 5',
                       'max cycles: 3\nmax stalled cycles: 1', 'max cycles: three\nmax stalled cycles: 1\nbudget usd: 5'):
            with self.subTest(limits=limits):
                ws = Workspace()
                self.addCleanup(ws.cleanup)
                ws.draft(with_limits(limits))
                ws.ok('shown')
                out = ws.blocked('approve')
                self.assertIn('delegation.md', out['error'])
                self.assertIn('limits', out['error'].lower())
                self.assertEqual(ws.record()['status'], 'DRAFT')


class CompletenessTests(Base):
    """Every completeness rule refuses `approve` with a BLOCKED naming the file and the item; nothing changes."""

    def check(self, parts, file, *items):
        ws = Workspace()
        self.addCleanup(ws.cleanup)
        ws.draft(parts)
        ws.ok('shown')
        out = ws.blocked('approve')
        self.assertTrue(out['error'].startswith(file + ':'), out['error'])
        for item in items:
            self.assertIn(item, out['error'])
        run = ws.record()
        self.assertEqual((run['status'], run['approvals'], run['limits']), ('DRAFT', [], None))
        self.assertFalse((ws.private / 'approved').exists())
        return out

    def test_scenario_rules(self):
        self.check(proposal_set(scenario=SCENARIO.replace('## Scenarios', '## Stories')), 'scenario.md', 'Scenarios')
        self.check(proposal_set(scenario=SCENARIO.replace('## Workflow', '## Flow')), 'scenario.md', 'Workflow')
        no_scenarios = SCENARIO.replace('### First run', '').replace('### Rebuild', '')
        self.check(proposal_set(scenario=no_scenarios), 'scenario.md', 'Scenarios')
        no_label = SCENARIO.replace('answers the prompts — step: configure', 'answers the prompts')
        self.check(proposal_set(scenario=no_label), 'scenario.md', 'step 2', 'First run', 'step:')
        no_steps = SCENARIO.replace('- The user edits the config -- step: configure\n- The user runs `tool build` again - step: build\n', '')
        self.check(proposal_set(scenario=no_steps), 'scenario.md', 'Rebuild', 'no steps')
        unknown = SCENARIO.replace('sees the output file — step: build', 'sees the output file — step: inspect')
        self.check(proposal_set(scenario=unknown), 'scenario.md', 'inspect', 'Workflow')
        empty_workflow = SCENARIO.split('## Workflow')[0] + '## Workflow\n'
        self.check(proposal_set(scenario=empty_workflow), 'scenario.md', 'Workflow')
        bad_bullet = SCENARIO.replace('- build: produce the output from the config', '- build produces the output')
        self.check(proposal_set(scenario=bad_bullet), 'scenario.md', 'Workflow', 'build')

    def test_validation_rules(self):
        self.check(proposal_set(validation=VALIDATION.replace('## Items', '## Checks')), 'validation.md', 'Items')
        no_items = VALIDATION.split('### V1')[0]
        self.check(proposal_set(validation=no_items), 'validation.md', 'Items')
        self.check(proposal_set(validation=VALIDATION.replace('### V2 Install', '### Install')), 'validation.md', 'V<n>')
        for field in ('Behavior', 'Environment', 'Evidence', 'Cost'):
            with self.subTest(field=field):
                missing = VALIDATION.replace(f'- {field}:', f'- {field}less:')
                self.check(proposal_set(validation=missing), 'validation.md', 'V2', field)
                empty = re.sub(rf'\*\*{field}:\*\* .*\n', f'**{field}:**\n', VALIDATION)
                self.check(proposal_set(validation=empty), 'validation.md', 'V1', field)
                wrapped = VALIDATION.replace(f'**{field}:** ', f'**{field}:**\n')  # a value on the next line is still a value
                core.parse_validation(wrapped)
        bad_cost = VALIDATION.replace('**Cost:** fast', '**Cost:** cheap')
        self.check(proposal_set(validation=bad_cost), 'validation.md', 'V1', 'Cost', 'slow/hard')
        dup = VALIDATION.replace('### V2 Install', '### V1 Install')
        self.check(proposal_set(validation=dup), 'validation.md', 'V1')

    def test_spec_rules(self):
        for section in ('Users', 'UI references', 'Outline', 'Efficient checks'):
            with self.subTest(section=section):
                self.check(proposal_set(spec=SPEC.replace(f'## {section}', f'## Other {section}')), 'spec.md', section)
        self.check(proposal_set(spec=SPEC.replace('Developers who build the thing locally.\n', '')), 'spec.md', 'Users')
        self.check(proposal_set(spec=SPEC.replace('## UI references\nnone', '## UI references')), 'spec.md', 'UI references')
        self.check(proposal_set(spec=SPEC.replace('- cli: parses commands and dispatches\n- builder: turns the config into the output\n',
                                                  'prose without bullets\n')), 'spec.md', 'Outline')
        self.check(proposal_set(spec=SPEC.replace('- V2: run the install script in a temp venv instead of a container.', 'none')),
                   'spec.md', 'Efficient checks', 'V2')
        self.check(proposal_set(spec=SPEC.replace('- V2: run', '- V3: run')), 'spec.md', 'Efficient checks', 'V2')
        # `none` is fine when nothing is slow/hard.
        ws = Workspace()
        self.addCleanup(ws.cleanup)
        ws.approve_fresh(proposal_set(validation=VALIDATION.replace('slow/hard, needs a clean container', 'fast'),
                                      spec=SPEC.replace('- V2: run the install script in a temp venv instead of a container.', 'none')))
        self.assertEqual(ws.record()['status'], 'ACTIVE')

    def test_delegation_rules(self):
        for section in ('Delegated judgment', 'Models', 'Limits', 'Workspace'):
            with self.subTest(section=section):
                parts = proposal_set()
                parts['delegation.md'] = parts['delegation.md'].replace(f'## {section}', f'## Other {section}')
                self.check(parts, 'delegation.md', section)
        parts = proposal_set()
        parts['delegation.md'] = parts['delegation.md'].replace('- L3: default\n', '')
        self.check(parts, 'delegation.md', 'Models', 'L3')
        parts = proposal_set()
        parts['delegation.md'] = parts['delegation.md'].replace('- L2: default\n', '- L2:\n')
        self.check(parts, 'delegation.md', 'Models', 'L2')
        parts = proposal_set()
        parts['delegation.md'] = parts['delegation.md'].replace('/tmp/project', 'relative/path')
        self.check(parts, 'delegation.md', 'Workspace', 'absolute')
        parts = proposal_set()
        parts['delegation.md'] = parts['delegation.md'].replace('Everything after approval.\n', '')
        self.check(parts, 'delegation.md', 'Delegated judgment')
        self.check(with_limits('max cycles: 3\nmax stalled cycles: 1'), 'delegation.md', 'limits', 'budget')

    def test_check_set_returns_limits_and_models(self):
        out = core.check_set(proposal_set(cycles=4, l3='haiku'))
        self.assertEqual(out, dict(limits=dict(max_cycles=4, max_stalled_cycles=2, budget_usd=10),
                                   models=dict(l2='default', l3='haiku')))
        with self.assertRaises(core.RecordError) as cm:
            core.check_set({k: v for k, v in proposal_set().items() if k != 'validation.md'})
        self.assertIn('validation.md', str(cm.exception))

    def test_parsers_expose_structure(self):
        sc = core.parse_scenario(SCENARIO)
        self.assertEqual([s['title'] for s in sc['scenarios']], ['First run', 'Rebuild'])
        self.assertEqual([st['label'] for st in sc['scenarios'][0]['steps']], ['install', 'configure', 'build'])
        self.assertEqual([st['label'] for st in sc['scenarios'][1]['steps']], ['configure', 'build'])
        self.assertEqual([w['label'] for w in sc['workflow']], ['install', 'configure', 'build'])
        va = core.parse_validation(VALIDATION)
        self.assertEqual([i['id'] for i in va['items']], ['V1', 'V2'])
        self.assertEqual([i['cost'] for i in va['items']], ['fast', 'slow/hard'])
        self.assertEqual(va['items'][1]['covers'], ['install'])
        self.assertEqual(va['items'][0]['fields']['evidence'], '`python3 -m tool build && cat out/result.txt` prints the name.')
        sp = core.parse_spec(SPEC)
        self.assertEqual(sp['ui_references'], 'none')
        self.assertEqual(len(sp['outline']), 2)
        self.assertEqual(list(sp['efficient_checks']), ['V2'])
        de = core.parse_delegation(DELEGATION.format(cycles=1, stalled=1, budget='no cap', l2='a', l3='b'))
        self.assertEqual((de['models'], de['workspace'], de['limits']['budget_usd']), (dict(l2='a', l3='b'), '/tmp/project', None))


class CycleTests(Base):
    def setUp(self):
        super().setUp()
        self.ws.approve_fresh()

    def test_cycle_start_opens_cycle(self):
        out = self.ws.start_cycle(checkpoint='b' * 40)
        self.assertEqual(out['cycle'], dict(id='c1', stage='ready', kind='development'))
        cycle = self.ws.record()['cycles'][0]
        self.assertEqual(cycle, dict(id='c1', goal='cycle goal', kind='development', started=cycle['started'],
                                     session_id=None, stage='ready', checkpoint_before='b' * 40,
                                     checkpoint_after=None, ready_digest=None, evaluation=None))
        self.assertEqual(self.ws.kinds()[-1], 'cycle_start')
        self.assertEqual(self.ws.events()[-1]['cycle_id'], 'c1')

    def test_cycle_start_refusals(self):
        self.ws.blocked('cycle-start', '--kind', 'other', '--goal', self.ws.file('x'), '--checkpoint', 'c' * 40)
        self.ws.start_cycle()
        out = self.ws.blocked('cycle-start', '--kind', 'migration', '--goal', self.ws.file('x'), '--checkpoint', 'c' * 40)
        self.assertIn('open', out['error'])
        self.assertEqual(len(self.ws.record()['cycles']), 1)
        self.ws.ok('stop', '--reason', 'abort')
        out = self.ws.blocked('cycle-start', '--kind', 'migration', '--goal', self.ws.file('x'), '--checkpoint', 'c' * 40)
        self.assertIn('STOPPED', out['error'])
        ws = Workspace()
        self.addCleanup(ws.cleanup)
        ws.draft()
        ws.blocked('cycle-start', '--kind', 'development', '--goal', ws.file('x'), '--checkpoint', 'c' * 40)

    def test_cycle_start_refuses_when_limit_already_exceeded(self):
        ws = Workspace()
        self.addCleanup(ws.cleanup)
        ws.approve_fresh(proposal_set(cycles=2, stalled=5))
        ws.start_cycle(); ws.evaluate('CONTINUE')
        ws.start_cycle(); ws.evaluate('REPLAN')
        self.assertEqual(ws.record()['status'], 'STOPPED')
        ws.blocked('cycle-start', '--kind', 'development', '--goal', ws.file('x'), '--checkpoint', 'c' * 40)
        # Raise the limit through an amendment, but keep a budget that is already overspent.
        ws.draft(proposal_set(cycles=9, stalled=5, budget='0.5'))
        ws.ok('shown')
        ws.ok('approve')
        run = ws.record()
        run['spent_usd'] = 1.0
        (ws.private / 'run.json').write_text(json.dumps(run))
        out = ws.blocked('cycle-start', '--kind', 'development', '--goal', ws.file('x'), '--checkpoint', 'c' * 40)
        self.assertIn('budget', out['error'])

    def test_cycle_stage_and_ready_digest_rule(self):
        self.ws.start_cycle()
        out = self.ws.blocked('cycle-stage', '--stage', 'go')
        self.assertIn('ready_digest', out['error'])
        self.assertEqual(self.ws.record()['cycles'][0]['stage'], 'ready')
        self.ws.blocked('cycle-stage', '--stage', 'ready', '--ready-digest', 'not-hex')
        self.ws.ok('cycle-stage', '--stage', 'ready', '--ready-digest', 'd' * 64)
        out = self.ws.ok('cycle-stage', '--stage', 'go')
        self.assertEqual(out['cycle']['stage'], 'go')
        self.ws.ok('cycle-stage', '--stage', 'review', '--checkpoint', 'e' * 40)
        cycle = self.ws.record()['cycles'][0]
        self.assertEqual((cycle['stage'], cycle['ready_digest'], cycle['checkpoint_after']), ('review', 'd' * 64, 'e' * 40))
        self.ws.ok('cycle-stage', '--stage', 'done')
        self.assertEqual(self.ws.kinds().count('cycle_stage'), 4)
        self.ws.blocked('cycle-stage', '--stage', 'later')

    def test_cycle_stage_without_open_cycle(self):
        self.ws.blocked('cycle-stage', '--stage', 'ready')

    def test_evaluate_closes_cycle_and_counts_stalled(self):
        self.ws.blocked('evaluate', '--decision', 'CONTINUE', '--basis', self.ws.file('b'))
        self.ws.start_cycle()
        self.ws.blocked('evaluate', '--decision', 'MAYBE', '--basis', self.ws.file('b'))
        out = self.ws.evaluate('CONTINUE')
        self.assertIsNone(out['cycle'])
        run = self.ws.record()
        self.assertEqual((run['cycles'][0]['stage'], run['cycles'][0]['evaluation']), ('done', 'CONTINUE'))
        self.assertEqual(run['stalled_cycles'], 0)
        self.assertEqual(run['status'], 'ACTIVE')
        ev = self.ws.events()[-1]
        self.assertEqual((ev['kind'], ev['actor'], ev['cycle_id']), ('evaluate', 'L1', 'c1'))
        self.assertEqual(ev['data']['decision'], 'CONTINUE')
        self.assertEqual(ev['data']['basis'], 'because')
        self.ws.start_cycle()
        self.ws.evaluate('REPLAN')
        self.assertEqual(self.ws.record()['stalled_cycles'], 1)
        self.assertEqual(self.ws.record()['status'], 'ACTIVE')

    def test_complete_sets_run_complete(self):
        self.ws.start_cycle()
        out = self.ws.blocked('evaluate', '--decision', 'COMPLETE', '--basis', self.ws.file('  \n'))
        self.assertIn('basis', out['error'])
        self.assertEqual(self.ws.record()['status'], 'ACTIVE')
        self.ws.ok('evaluate', '--decision', 'CONTINUE', '--basis', self.ws.file(''))  # empty basis only blocks COMPLETE
        self.ws.start_cycle()
        self.ws.evaluate('COMPLETE')
        run = self.ws.record()
        self.assertEqual(run['status'], 'COMPLETE')
        self.assertIsNone(run['stopped_reason'])

    def test_large_basis_goes_to_turns(self):
        self.ws.start_cycle()
        self.ws.ok('evaluate', '--decision', 'CONTINUE', '--basis', self.ws.file('x' * 9000, '.md'))
        ev = self.ws.events()[-1]
        self.assertEqual(ev['kind'], 'evaluate')
        self.assertEqual(ev['data']['basis']['file'], 'turns/event-1.md')
        self.assertEqual((self.ws.private / 'turns/event-1.md').read_text(), 'x' * 9000)

    def test_stalled_limit_stops(self):
        self.ws.start_cycle(); self.ws.evaluate('REPLAN')
        self.ws.start_cycle(); self.ws.evaluate('ESCALATE')
        run = self.ws.record()
        self.assertEqual(run['stalled_cycles'], 2)
        self.assertEqual((run['status'], run['stopped_reason']), ('STOPPED', 'limit:stalled'))
        self.assertEqual(self.ws.kinds()[-1], 'stop')

    def test_cycle_limit_stops_when_more_development_is_asked_for(self):
        for _ in range(2):
            self.ws.start_cycle(); self.ws.evaluate('CONTINUE')
        self.ws.start_cycle(); self.ws.evaluate('REPLAN')
        run = self.ws.record()
        self.assertEqual((run['status'], run['stopped_reason']), ('STOPPED', 'limit:cycles'))
        self.assertEqual(self.ws.kinds()[-1], 'stop')

    def test_cycle_limit_reached_by_continue_leaves_only_beta_open(self):
        for _ in range(3):
            self.ws.start_cycle(); self.ws.evaluate('CONTINUE')
        run = self.ws.record()
        self.assertEqual((run['status'], run['stopped_reason']), ('ACTIVE', None))
        out = self.ws.blocked('cycle-start', '--kind', 'development', '--goal', self.ws.file('x'), '--checkpoint', 'c' * 40)
        self.assertIn('cycles', out['error'])
        self.ws.start_cycle(kind='beta')
        self.assertEqual(self.ws.record()['cycles'][-1]['kind'], 'beta')

    def test_budget_limit_stops(self):
        self.ws.start_cycle()
        run = self.ws.record()
        run['spent_usd'] = 10.5
        (self.ws.private / 'run.json').write_text(json.dumps(run))
        self.ws.evaluate('CONTINUE')
        run = self.ws.record()
        self.assertEqual((run['status'], run['stopped_reason']), ('STOPPED', 'limit:budget'))

    def test_no_cap_budget_never_stops(self):
        ws = Workspace()
        self.addCleanup(ws.cleanup)
        ws.approve_fresh(proposal_set(budget='no cap'))
        ws.start_cycle()
        run = ws.record()
        run['spent_usd'] = 1e6
        (ws.private / 'run.json').write_text(json.dumps(run))
        ws.evaluate('CONTINUE')
        self.assertEqual(ws.record()['status'], 'ACTIVE')

    def test_pending_amendment_applied_at_evaluate(self):
        self.ws.start_cycle()
        self.ws.draft(proposal_set(cycles=8))
        self.ws.ok('shown')
        self.ws.ok('approve')
        self.ws.evaluate('CONTINUE')
        kinds = self.ws.kinds()
        self.assertIn('amend_applied', kinds)
        self.assertLess(kinds.index('amend'), kinds.index('amend_applied'))
        self.ws.start_cycle()
        self.ws.evaluate('CONTINUE')
        self.assertEqual(self.ws.kinds().count('amend_applied'), 1)
        self.assertTrue(all(a['applied'] for a in self.ws.record()['approvals']))

    def test_amendment_between_cycles_applied_at_next_cycle_start(self):
        self.ws.start_cycle(); self.ws.evaluate('CONTINUE')
        self.ws.draft(proposal_set(cycles=8))
        self.ws.ok('shown'); self.ws.ok('approve')
        self.assertNotIn('amend_applied', self.ws.kinds())
        self.ws.start_cycle()
        kinds = self.ws.kinds()
        self.assertEqual(kinds[-2:], ['cycle_start', 'amend_applied'])
        self.assertEqual(self.ws.events()[-1]['cycle_id'], 'c2')
        self.ws.evaluate('CONTINUE')
        self.assertEqual(self.ws.kinds().count('amend_applied'), 1)


class BetaCycleTests(Base):
    """The beta cycle: L1 runs the scenarios itself; no worker turns, exempt from max cycles."""

    def setUp(self):
        super().setUp()
        self.ws.approve_fresh(proposal_set(cycles=1, stalled=2))
        self.ws.start_cycle(); self.ws.evaluate('CONTINUE')
        self.assertEqual(self.ws.record()['status'], 'ACTIVE')

    def test_beta_is_exempt_from_max_cycles_and_counted_separately(self):
        out = self.ws.blocked('cycle-start', '--kind', 'development', '--goal', self.ws.file('x'), '--checkpoint', 'c' * 40)
        self.assertIn('cycles', out['error'])
        out = self.ws.start_cycle(kind='beta')
        self.assertEqual(out['cycle'], dict(id='c2', stage='ready', kind='beta'))
        self.assertEqual(out['beta_cycles'], 1)
        run = self.ws.record()
        self.assertEqual((run['beta_cycles'], run['cycles'][-1]['kind'], run['status']), (1, 'beta', 'ACTIVE'))
        self.assertEqual(self.ws.events()[-1]['data']['kind'], 'beta')
        out = self.ws.blocked('cycle-start', '--kind', 'beta', '--goal', self.ws.file('x'), '--checkpoint', 'c' * 40)
        self.assertIn('open', out['error'])

    def test_beta_refused_when_not_active_or_stalled(self):
        ws = Workspace()
        self.addCleanup(ws.cleanup)
        ws.draft()
        ws.blocked('cycle-start', '--kind', 'beta', '--goal', ws.file('x'), '--checkpoint', 'c' * 40)
        run = self.ws.record()
        run['stalled_cycles'] = 2
        (self.ws.private / 'run.json').write_text(json.dumps(run))
        out = self.ws.blocked('cycle-start', '--kind', 'beta', '--goal', self.ws.file('x'), '--checkpoint', 'c' * 40)
        self.assertIn('stalled', out['error'])

    def test_escalate_on_beta_is_not_stalled_and_keeps_the_run_active(self):
        self.ws.start_cycle(kind='beta')
        self.ws.ok('event', '--actor', 'L1', '--kind', 'beta', '--cycle', 'c2',
                   '--data', self.ws.file('{"item": "V1", "verdict": "pass"}', '.json'))
        self.ws.evaluate('ESCALATE')
        run = self.ws.record()
        self.assertEqual((run['status'], run['stalled_cycles'], run['cycles'][-1]['evaluation']), ('ACTIVE', 0, 'ESCALATE'))
        self.ws.ok('event', '--actor', 'human', '--kind', 'verified', '--data', self.ws.file('{"item": "V2", "words": "it works"}', '.json'))
        self.ws.start_cycle(kind='beta')
        self.assertEqual(self.ws.record()['beta_cycles'], 2)
        self.ws.evaluate('CONTINUE')
        self.assertEqual((self.ws.record()['status'], self.ws.record()['stalled_cycles']), ('ACTIVE', 0))

    def test_replan_on_beta_counts_stalled(self):
        self.ws.start_cycle(kind='beta')
        self.ws.evaluate('REPLAN')
        run = self.ws.record()
        self.assertEqual(run['stalled_cycles'], 1)
        # max cycles is 1 and more development is asked for: the cycles limit stops the run.
        self.assertEqual((run['status'], run['stopped_reason']), ('STOPPED', 'limit:cycles'))

    def test_replan_on_beta_reopens_development_under_a_larger_limit(self):
        ws = Workspace()
        self.addCleanup(ws.cleanup)
        ws.approve_fresh(proposal_set(cycles=3, stalled=3))
        ws.start_cycle(); ws.evaluate('CONTINUE')
        ws.start_cycle(kind='beta'); ws.evaluate('REPLAN')
        run = ws.record()
        self.assertEqual((run['status'], run['stalled_cycles']), ('ACTIVE', 1))
        ws.start_cycle(); ws.evaluate('CONTINUE')
        ws.start_cycle(kind='beta'); ws.evaluate('COMPLETE')
        run = ws.record()
        self.assertEqual((run['status'], len(run['cycles']), run['beta_cycles']), ('COMPLETE', 4, 2))

    def test_complete_on_beta_completes_the_run(self):
        self.ws.start_cycle(kind='beta')
        self.ws.evaluate('COMPLETE')
        run = self.ws.record()
        self.assertEqual((run['status'], run['beta_cycles'], run['cycles'][-1]['evaluation']), ('COMPLETE', 1, 'COMPLETE'))

    def test_session_commands_refuse_while_beta_is_open(self):
        self.ws.start_cycle(kind='beta')
        out = self.ws.blocked('session-start', '--skill', 'ready', '--message', self.ws.file('x'))
        self.assertIn('beta cycle runs no worker turns', out['error'])
        out = self.ws.blocked('session-send', '--message', self.ws.file('x'))
        self.assertIn('beta cycle runs no worker turns', out['error'])
        self.assertNotIn('turn', self.ws.record())
        self.assertNotIn('turn_count', self.ws.record())


class EventTests(Base):
    def test_small_json_is_embedded(self):
        self.ws.draft()
        out = self.ws.ok('event', '--actor', 'L2', '--kind', 'question', '--data', self.ws.file('{"q": "which?"}', '.json'))
        ev = self.ws.events()[-1]
        self.assertEqual((ev['actor'], ev['kind'], ev['cycle_id'], ev['data']), ('L2', 'question', None, {'q': 'which?'}))
        self.assertIn('time', ev)
        self.assertEqual(out['counts']['events'], 2)

    def test_large_or_non_json_goes_to_turns(self):
        self.ws.draft()
        self.ws.ok('event', '--actor', 'host', '--kind', 'turn', '--data', self.ws.file('not json', '.log'))
        self.ws.ok('event', '--actor', 'host', '--kind', 'turn', '--data', self.ws.file(json.dumps({'big': 'x' * 9000}), '.json'))
        first, second = self.ws.events()[-2:]
        self.assertEqual(first['data']['file'], 'turns/event-1.log')
        self.assertEqual(second['data']['file'], 'turns/event-2.json')
        self.assertEqual(first['data']['sha256'], hashlib.sha256(b'not json').hexdigest())
        p = self.ws.private / 'turns' / 'event-1.log'
        self.assertEqual(p.read_text(), 'not json')
        self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(p.parent.stat().st_mode), 0o700)

    def test_event_validation(self):
        self.ws.draft()
        self.ws.blocked('event', '--actor', 'me', '--kind', 'x', '--data', self.ws.file('{}'))
        self.ws.blocked('event', '--actor', 'L1', '--kind', 'x', '--cycle', 'c9', '--data', self.ws.file('{}'))
        self.ws.blocked('event', '--actor', 'L1', '--kind', 'x', '--data', str(self.ws.path / 'missing'))
        self.assertEqual(len(self.ws.events()), 1)
        self.ws.ok('shown'); self.ws.ok('approve'); self.ws.start_cycle()
        self.ws.ok('event', '--actor', 'L1', '--kind', 'answer', '--cycle', 'c1', '--data', self.ws.file('{"a": 1}'))
        self.assertEqual(self.ws.events()[-1]['cycle_id'], 'c1')


class StopAndArchiveTests(Base):
    def test_stop_abort(self):
        self.ws.draft()
        self.ws.blocked('stop', '--reason', 'abort')
        self.ws.ok('shown'); self.ws.ok('approve')
        self.ws.blocked('stop', '--reason', 'whatever')
        out = self.ws.ok('stop', '--reason', 'abort')
        self.assertEqual(out['status'], 'STOPPED')
        run = self.ws.record()
        self.assertEqual(run['stopped_reason'], 'abort')
        self.assertIsNone(run['stopped_at'])
        ev = self.ws.events()[-1]
        self.assertEqual((ev['kind'], ev['actor'], ev['data']['reason']), ('stop', 'human', 'abort'))
        self.ws.blocked('stop', '--reason', 'abort')

    def test_stop_records_open_cycle_checkpoint_and_stage(self):
        self.ws.approve_fresh()
        self.ws.start_cycle(checkpoint='a' * 40)
        self.ws.ok('cycle-stage', '--stage', 'ready', '--ready-digest', 'd' * 64)
        self.ws.ok('cycle-stage', '--stage', 'go')
        self.ws.ok('stop', '--reason', 'abort')
        run = self.ws.record()
        self.assertEqual(run['stopped_at'], dict(cycle_id='c1', stage='go', checkpoint='a' * 40))
        self.assertEqual(self.ws.events()[-1]['data']['stopped_at'], run['stopped_at'])
        self.assertIsNone(run['cycles'][0]['evaluation'])  # abort leaves the cycle open
        self.ws.draft(proposal_set(cycles=9))
        self.ws.ok('shown'); self.ws.ok('approve')
        self.assertIsNone(self.ws.record()['stopped_at'])
        self.ws.ok('cycle-stage', '--stage', 'review', '--checkpoint', 'b' * 40)
        self.ws.ok('stop', '--reason', 'abort')
        self.assertEqual(self.ws.record()['stopped_at']['checkpoint'], 'b' * 40)

    def test_stop_limit_reason(self):
        self.ws.approve_fresh()
        self.ws.ok('stop', '--reason', 'limit:budget')
        run = self.ws.record()
        self.assertEqual(run['stopped_reason'], 'limit:budget')
        self.assertEqual(self.ws.events()[-1]['actor'], 'L1')

    def test_archive(self):
        self.ws.draft()
        self.ws.blocked('archive')
        self.ws.ok('shown'); self.ws.ok('approve')
        self.ws.blocked('archive')
        self.ws.ok('event', '--actor', 'host', '--kind', 'turn', '--data', self.ws.file('raw', '.log'))
        (self.ws.private / 'workgraph.yaml').write_text('nodes: []\n')
        self.ws.ok('stop', '--reason', 'abort')
        run_id = self.ws.record()['run_id']
        out = self.ws.ok('archive')
        self.assertEqual(out['archived'], run_id)
        dest = self.ws.private / 'archive' / run_id
        for name in (*NAMES, *('shown/' + n for n in NAMES), *('approved/' + n for n in NAMES),
                     'run.json', 'events.jsonl', 'turns/event-1.log', 'workgraph.yaml'):
            self.assertTrue((dest / name).is_file(), name)
            self.assertFalse((self.ws.private / name).exists(), name)
        self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o700)
        self.assertTrue((self.ws.private / 'owner.json').is_file())
        self.ws.blocked('archive')
        self.ws.blocked('show')


class OwnerAndLockTests(Base):
    def test_live_other_owner_blocks_draft_and_approve(self):
        self.ws.draft()
        other = subprocess.Popen(['sleep', '30'])
        self.addCleanup(other.kill)
        (self.ws.private / 'owner.json').write_text(json.dumps(dict(pid=other.pid, started='x')))
        out = self.ws.blocked('draft', *self.ws.draft_args(proposal_set()))
        self.assertIn(str(other.pid), out['error'])
        self.ws.ok('shown', owner=os.getpid())  # not an owner-checked command
        out = self.ws.blocked('approve')
        self.assertIn(str(other.pid), out['error'])
        self.assertEqual(self.ws.record()['status'], 'DRAFT')
        self.ws.ok('approve', owner=other.pid)
        self.assertEqual(json.loads((self.ws.private / 'owner.json').read_text())['pid'], other.pid)

    def test_dead_owner_is_replaced(self):
        self.ws.draft()
        dead = subprocess.Popen(['true'])
        dead.wait()
        (self.ws.private / 'owner.json').write_text(json.dumps(dict(pid=dead.pid, started='x')))
        self.ws.ok('shown')
        self.ws.ok('approve')
        self.assertEqual(json.loads((self.ws.private / 'owner.json').read_text())['pid'], os.getpid())

    def test_check_owner_helper(self):
        self.ws.draft()
        st = store.Store(self.ws.path)
        other = subprocess.Popen(['sleep', '30'])
        self.addCleanup(other.kill)
        st.write_owner(other.pid, session_id='s-1')
        self.assertEqual(st.read_owner()['session_id'], 's-1')
        with self.assertRaises(core.RecordError):
            store.check_owner(st, os.getpid())
        store.check_owner(st, other.pid)
        other.kill(); other.wait()
        store.check_owner(st, os.getpid())

    def test_lock_refusal_and_serialization(self):
        self.ws.draft()
        st = store.Store(self.ws.path)
        fd = os.open(st.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        with self.assertRaises(core.RecordError):
            with st.transaction(timeout=0):
                pass
        holder = subprocess.Popen([sys.executable, '-c', f'''
import fcntl, os, time
fd = os.open({str(st.lock_path)!r}, os.O_RDWR)
fcntl.flock(fd, fcntl.LOCK_EX)
time.sleep(1.0)
'''])
        self.addCleanup(holder.kill)
        fcntl.flock(fd, fcntl.LOCK_UN)
        time.sleep(0.3)
        t = time.monotonic()
        self.ws.ok('shown')
        self.assertGreater(time.monotonic() - t, 0.4)
        self.assertEqual(self.ws.record()['proposal_digest_shown'], set_sha(proposal_set()))


class HelperTests(Base):
    def test_private_dir_and_spent(self):
        self.assertEqual(store.private_dir(self.ws.path), self.ws.path / '.dryforge' / 'ouroboros')
        self.ws.approve_fresh()
        st = store.Store(self.ws.path)
        with st.transaction():
            run = st.read_run()
            st.write_run(core.add_spent(run, 0.25))
        self.assertEqual(self.ws.record()['spent_usd'], 0.25)
        with self.assertRaises(core.RecordError):
            core.add_spent(run, -1)

    def test_store_set_helpers(self):
        self.ws.draft()
        st = store.Store(self.ws.path)
        self.assertEqual(store.PROPOSAL_FILES, NAMES)
        self.assertEqual({k: v.decode() for k, v in st.read_set().items()}, proposal_set())
        self.assertFalse(st.is_legacy())
        self.assertEqual(st.read_shown(), {name: None for name in NAMES})
        self.assertIn('workgraph.yaml', store.RUN_FILES)
        for legacy in ('proposal.md', 'proposal.shown.md', 'proposal.approved.md'):
            self.assertIn(legacy, store.RUN_FILES)

    def test_doctor_reports_claude_on_path(self):
        out = self.ws.ok('doctor')
        self.assertEqual(out['host'], 'claude')
        self.assertIn('claude', out)

    def test_port_is_abstract(self):
        from ouroboros import ports
        self.assertTrue(hasattr(ports, 'HostSession'))
        for name in ('start', 'send', 'terminate', 'result'):
            self.assertTrue(callable(getattr(ports.HostSession, name)), name)


if __name__ == '__main__':
    unittest.main()
