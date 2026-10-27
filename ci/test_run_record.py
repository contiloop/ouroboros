"""Run-record rules and refusals of ouroboros_cli.py against real temp git repos. No live host."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
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

PROPOSAL = """# Proposal

## Goal
Ship the thing.

## Completion criteria
- tests pass

## Constraints
- stdlib only

## Priorities
1. correctness

## Non-goals
- a release

## Delegated judgment
Everything after approval.

## Workspace
/tmp/project

## Limits
- max cycles: {cycles}
- max stalled cycles: {stalled}
- budget usd: {budget}
"""


def proposal(cycles=3, stalled=2, budget='10'):
    return PROPOSAL.format(cycles=cycles, stalled=stalled, budget=budget)


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


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
    def draft(self, text=None, **kw):
        return self.ok('draft', '--proposal', self.file(text or proposal()), **kw)

    def approve_fresh(self, text=None):
        self.draft(text)
        self.ok('shown')
        return self.ok('approve')

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
        for name in ('run.json', 'proposal.md', 'events.jsonl', 'owner.json'):
            self.assertEqual(stat.S_IMODE((priv / name).stat().st_mode), 0o600, name)
        run = self.ws.record()
        self.assertEqual(set(run), {'run_id', 'workspace', 'status', 'proposal_digest_shown', 'approvals', 'limits',
                                    'spent_usd', 'stalled_cycles', 'host', 'session', 'cycles', 'stopped_reason',
                                    'stopped_at'})
        self.assertEqual(run['status'], 'DRAFT')
        self.assertEqual(run['workspace'], str(self.ws.path))
        self.assertIsNone(run['proposal_digest_shown'])
        self.assertEqual(run['approvals'], [])
        self.assertEqual(run['host'], 'claude')
        self.assertEqual(run['session'], dict(id=None, started=None, reason=None))
        self.assertEqual(run['spent_usd'], 0)
        self.assertEqual((priv / 'proposal.md').read_text(), proposal())
        self.assertEqual(self.ws.kinds(), ['draft'])
        owner = json.loads((priv / 'owner.json').read_text())
        self.assertEqual(owner['pid'], os.getpid())
        self.assertEqual(set(owner), {'pid', 'session_id', 'started'})
        self.assertIsNone(owner['session_id'])
        self.assertNotIn('schema', json.dumps(run))

    def test_redraft_replaces_proposal_and_clears_shown(self):
        self.ws.draft()
        first = self.ws.record()['run_id']
        self.ws.ok('shown')
        self.assertIsNotNone(self.ws.record()['proposal_digest_shown'])
        self.ws.draft(proposal(cycles=9))
        run = self.ws.record()
        self.assertEqual(run['run_id'], first)
        self.assertIsNone(run['proposal_digest_shown'])
        self.assertEqual((self.ws.private / 'proposal.md').read_text(), proposal(cycles=9))
        self.assertEqual(self.ws.kinds(), ['draft', 'shown', 'draft'])

    def test_draft_refused_when_dryforge_not_ignored(self):
        ws = Workspace(ignore=False)
        self.addCleanup(ws.cleanup)
        out = ws.blocked('draft', '--proposal', ws.file(proposal()))
        self.assertIn('.dryforge/', out['error'])
        self.assertFalse((ws.path / '.dryforge').exists())

    def test_draft_refused_when_only_json_is_ignored(self):
        ws = Workspace(ignore=False)
        self.addCleanup(ws.cleanup)
        (ws.path / '.gitignore').write_text('*.json\n')
        out = ws.blocked('draft', '--proposal', ws.file(proposal()))
        self.assertIn('.dryforge/', out['error'])
        self.assertFalse((ws.path / '.dryforge').exists())

    def test_draft_refused_outside_git_root(self):
        ws = Workspace(git=False)
        self.addCleanup(ws.cleanup)
        out = ws.blocked('draft', '--proposal', ws.file(proposal()))
        self.assertIn('git', out['error'])
        self.assertFalse((ws.path / '.dryforge').exists())
        sub = self.ws.path / 'sub'
        sub.mkdir()
        out = self.ws.blocked('draft', '--proposal', self.ws.file(proposal()), workspace=str(sub))
        self.assertIn('git', out['error'])

    def test_draft_revises_active_run(self):
        self.ws.approve_fresh()
        before = self.ws.record()
        out = self.ws.ok('draft', '--proposal', self.ws.file(proposal(cycles=5)))
        self.assertEqual(out['status'], 'ACTIVE')
        self.assertIsNone(out['proposal_digest_shown'])
        self.assertEqual(out['proposal_digest'], sha(proposal(cycles=5)))
        run = self.ws.record()
        self.assertEqual((run['run_id'], run['status'], run['limits']), (before['run_id'], 'ACTIVE', before['limits']))
        self.assertEqual(run['approvals'], before['approvals'])
        self.assertEqual((self.ws.private / 'proposal.md').read_text(), proposal(cycles=5))
        self.assertFalse((self.ws.private / 'proposal.shown.md').exists())
        self.assertEqual(self.ws.kinds(), ['draft', 'shown', 'approve', 'draft'])
        self.assertFalse((self.ws.private / 'archive').exists())
        out = self.ws.blocked('approve')  # the revision must be shown first
        self.assertIn('shown', out['error'])

    def test_draft_revises_stopped_run_so_approve_can_resume_it(self):
        self.ws.approve_fresh()
        self.ws.ok('stop', '--reason', 'abort')
        old = self.ws.record()
        out = self.ws.ok('draft', '--proposal', self.ws.file(proposal(cycles=4)))
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
        self.ws.draft(proposal(cycles=4))
        run = self.ws.record()
        self.assertNotEqual(run['run_id'], old['run_id'])
        self.assertEqual(run['status'], 'DRAFT')
        archived = self.ws.private / 'archive' / old['run_id']
        self.assertEqual(json.loads((archived / 'run.json').read_text())['status'], 'COMPLETE')
        self.assertEqual((archived / 'proposal.md').read_text(), proposal())
        self.assertTrue((archived / 'proposal.shown.md').is_file())
        kinds = [json.loads(l)['kind'] for l in (archived / 'events.jsonl').read_text().splitlines()]
        self.assertEqual(kinds[-1], 'archive')
        self.assertEqual(self.ws.kinds(), ['draft'])

    def test_archive_then_draft_starts_a_different_goal_after_a_stop(self):
        self.ws.approve_fresh()
        self.ws.ok('stop', '--reason', 'abort')
        old = self.ws.record()['run_id']
        self.ws.ok('archive')
        self.ws.draft(proposal(cycles=4))
        run = self.ws.record()
        self.assertNotEqual(run['run_id'], old)
        self.assertEqual((run['status'], run['approvals']), ('DRAFT', []))
        self.assertEqual(json.loads((self.ws.private / 'archive' / old / 'run.json').read_text())['status'], 'STOPPED')


class ShownAndShowTests(Base):
    def test_shown_records_digest_and_copy(self):
        self.ws.draft()
        out = self.ws.ok('shown')
        self.assertEqual(out['proposal_digest_shown'], sha(proposal()))
        self.assertEqual(self.ws.record()['proposal_digest_shown'], sha(proposal()))
        self.assertEqual((self.ws.private / 'proposal.shown.md').read_text(), proposal())
        self.assertEqual(self.ws.kinds(), ['draft', 'shown'])

    def test_show_summary(self):
        self.ws.draft()
        out = self.ws.ok('show')
        self.assertEqual(out['status'], 'DRAFT')
        self.assertEqual(out['proposal_digest'], sha(proposal()))
        self.assertIsNone(out['proposal_digest_shown'])
        self.assertIsNone(out['cycle'])
        self.assertEqual(out['counts'], dict(cycles=0, approvals=0, events=1))
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

    def test_never_shown_is_blocked(self):
        self.ws.draft()
        out = self.ws.blocked('approve')
        self.assertIn('shown', out['error'])
        self.assertEqual(self.ws.record()['status'], 'DRAFT')

    def test_changed_since_shown_prints_both_digests_and_diff(self):
        self.ws.draft()
        self.ws.ok('shown')
        (self.ws.private / 'proposal.md').write_text(proposal(cycles=7))
        out = self.ws.blocked('approve')
        self.assertEqual(out['shown_digest'], sha(proposal()))
        self.assertEqual(out['current_digest'], sha(proposal(cycles=7)))
        self.assertIn('-- max cycles: 3', out['diff'])
        self.assertIn('+- max cycles: 7', out['diff'])
        self.assertEqual(self.ws.record()['status'], 'DRAFT')
        self.assertEqual(self.ws.kinds(), ['draft', 'shown'])

    def test_draft_equal_activates(self):
        self.ws.draft()
        self.ws.ok('shown')
        out = self.ws.ok('approve')
        self.assertEqual(out['status'], 'ACTIVE')
        run = self.ws.record()
        self.assertEqual(run['status'], 'ACTIVE')
        self.assertEqual(len(run['approvals']), 1)
        self.assertEqual(run['approvals'][0]['digest'], sha(proposal()))
        self.assertIn('time', run['approvals'][0])
        self.assertTrue(run['approvals'][0]['applied'])
        self.assertEqual(run['limits'], dict(max_cycles=3, max_stalled_cycles=2, budget_usd=10))
        ev = self.ws.events()[-1]
        self.assertEqual((ev['kind'], ev['actor']), ('approve', 'human'))

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
        self.ws.draft(proposal(cycles=5))
        self.ws.blocked('approve')  # revised but not re-shown
        self.ws.ok('shown')
        out = self.ws.ok('approve')
        self.assertEqual(out['approval'], 'amended')
        run = self.ws.record()
        self.assertEqual(run['status'], 'ACTIVE')
        self.assertEqual([a['digest'] for a in run['approvals']], [sha(proposal()), sha(proposal(cycles=5))])
        self.assertEqual(run['limits']['max_cycles'], 5)
        self.assertFalse(run['approvals'][-1]['applied'])
        self.assertEqual(self.ws.kinds()[-1], 'amend')
        self.assertEqual(self.ws.events()[-1]['actor'], 'human')
        self.ws.ok('stop', '--reason', 'abort')
        self.assertEqual(self.ws.record()['status'], 'STOPPED')
        self.ws.draft(proposal(cycles=6))
        self.ws.ok('shown')
        out = self.ws.ok('approve')
        self.assertEqual(out['approval'], 'amended')
        run = self.ws.record()
        self.assertEqual(run['status'], 'ACTIVE')
        self.assertIsNone(run['stopped_reason'])
        self.assertEqual(len(run['approvals']), 3)
        self.assertEqual(run['limits']['max_cycles'], 6)

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
        self.assertEqual([a['digest'] for a in run['approvals']], [sha(proposal())] * 2)
        self.assertTrue(run['approvals'][-1]['applied'])
        self.assertEqual(run['limits'], stopped['limits'])
        ev = self.ws.events()[-1]
        self.assertEqual((ev['kind'], ev['actor'], ev['data']['action']), ('approve', 'human', 'resumed'))
        self.assertIsNone(run['cycles'][0]['evaluation'])  # the aborted cycle is still open
        self.assertEqual(self.ws.ok('approve'), self.ws.ok('show'))  # ACTIVE + same digest stays a no-op
        self.assertEqual(self.ws.kinds().count('approve'), 2)

    def test_approve_writes_the_governing_text(self):
        self.ws.approve_fresh()
        approved = self.ws.private / 'proposal.approved.md'
        self.assertTrue(approved.is_file())
        self.assertEqual(approved.read_text(), proposal())
        self.assertEqual(approved.stat().st_mode & 0o777, 0o600)
        self.ws.draft(proposal() + '\nrevised\n')
        self.assertEqual(approved.read_text(), proposal())  # a pending revision does not touch it
        self.ws.ok('shown')
        self.ws.ok('approve')
        self.assertEqual(approved.read_text(), proposal() + '\nrevised\n')

    def test_complete_run_cannot_be_approved(self):
        self.ws.approve_fresh()
        self.ws.start_cycle()
        self.ws.evaluate('COMPLETE')
        self.assertEqual(self.ws.record()['status'], 'COMPLETE')
        self.ws.ok('shown')
        self.ws.blocked('approve')
        self.assertEqual(self.ws.record()['status'], 'COMPLETE')

    def test_required_sections(self):
        for section in ('Goal', 'Completion criteria', 'Constraints', 'Priorities', 'Non-goals',
                        'Delegated judgment', 'Workspace', 'Limits'):
            with self.subTest(section=section):
                ws = Workspace()
                self.addCleanup(ws.cleanup)
                text = proposal().replace(f'## {section}\n', f'## Other {section}\n')
                ws.draft(text)
                ws.ok('shown')
                out = ws.blocked('approve')
                self.assertIn(section.lower(), out['error'].lower())
                self.assertEqual(ws.record()['status'], 'DRAFT')

    def test_section_headings_are_case_insensitive(self):
        self.ws.approve_fresh(proposal().replace('## Non-goals', '## NON-GOALS').replace('## Goal', '## goal'))
        self.assertEqual(self.ws.record()['status'], 'ACTIVE')

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
                ws.approve_fresh(proposal().split('## Limits')[0] + '## Limits\n' + limits + '\n')
                self.assertEqual(ws.record()['limits'], want)
        for limits in ('max cycles: 3\nbudget usd: 5', 'max stalled cycles: 1\nbudget usd: 5',
                       'max cycles: 3\nmax stalled cycles: 1', 'max cycles: three\nmax stalled cycles: 1\nbudget usd: 5'):
            with self.subTest(limits=limits):
                ws = Workspace()
                self.addCleanup(ws.cleanup)
                ws.draft(proposal().split('## Limits')[0] + '## Limits\n' + limits + '\n')
                ws.ok('shown')
                out = ws.blocked('approve')
                self.assertIn('limits', out['error'].lower())


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
        ws.approve_fresh(proposal(cycles=2, stalled=5))
        ws.start_cycle(); ws.evaluate('CONTINUE')
        ws.start_cycle(); ws.evaluate('CONTINUE')
        self.assertEqual(ws.record()['status'], 'STOPPED')
        ws.blocked('cycle-start', '--kind', 'development', '--goal', ws.file('x'), '--checkpoint', 'c' * 40)
        # Raise the limit through an amendment, but keep a budget that is already overspent.
        ws.draft(proposal(cycles=9, stalled=5, budget='0.5'))
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

    def test_cycle_limit_stops(self):
        for _ in range(3):
            self.ws.start_cycle(); self.ws.evaluate('CONTINUE')
        run = self.ws.record()
        self.assertEqual((run['status'], run['stopped_reason']), ('STOPPED', 'limit:cycles'))

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
        ws.approve_fresh(proposal(budget='no cap'))
        ws.start_cycle()
        run = ws.record()
        run['spent_usd'] = 1e6
        (ws.private / 'run.json').write_text(json.dumps(run))
        ws.evaluate('CONTINUE')
        self.assertEqual(ws.record()['status'], 'ACTIVE')

    def test_pending_amendment_applied_at_evaluate(self):
        self.ws.start_cycle()
        self.ws.draft(proposal(cycles=8))
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
        self.ws.draft(proposal(cycles=8))
        self.ws.ok('shown'); self.ws.ok('approve')
        self.assertNotIn('amend_applied', self.ws.kinds())
        self.ws.start_cycle()
        kinds = self.ws.kinds()
        self.assertEqual(kinds[-2:], ['cycle_start', 'amend_applied'])
        self.assertEqual(self.ws.events()[-1]['cycle_id'], 'c2')
        self.ws.evaluate('CONTINUE')
        self.assertEqual(self.ws.kinds().count('amend_applied'), 1)


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
        self.ws.draft(proposal(cycles=9))
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
        self.ws.ok('stop', '--reason', 'abort')
        run_id = self.ws.record()['run_id']
        out = self.ws.ok('archive')
        self.assertEqual(out['archived'], run_id)
        dest = self.ws.private / 'archive' / run_id
        for name in ('proposal.md', 'proposal.shown.md', 'run.json', 'events.jsonl', 'turns/event-1.log'):
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
        out = self.ws.blocked('draft', '--proposal', self.ws.file(proposal()))
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
        self.assertEqual(self.ws.record()['proposal_digest_shown'], sha(proposal()))


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
