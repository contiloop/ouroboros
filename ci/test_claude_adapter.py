"""Claude Code host adapter and the session-* commands against ci/fixtures/fake_claude.py. Never the real host."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCRIPTS = ROOT / 'src/skills/init/scripts'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SCRIPTS))
from test_run_record import Workspace, proposal as proposal_text  # noqa: E402
from ouroboros import adapters, ports  # noqa: E402
from ouroboros.adapters import claude as claude_adapter  # noqa: E402

FAKE = HERE / 'fixtures' / 'fake_claude.py'
BYPASS = ('--dangerously-skip-permissions', 'bypassPermissions')


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class HostWorkspace(Workspace):
    """Workspace whose CLI calls see a temp `bin/claude` (the fake) first on PATH plus per-call env."""

    def __init__(self):
        super().__init__()
        self.bin = self.path.parent / f'fakebin-{self.path.name}'
        self.bin.mkdir()
        target = self.bin / 'claude'
        shutil.copy(FAKE, target)
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.log = self.path.parent / f'fakelog-{self.path.name}.json'
        self.env = dict(FAKE_CLAUDE_LOG=str(self.log))

    def cleanup(self):
        turn = self.record().get('turn') if (self.private / 'run.json').is_file() else None
        if turn and turn.get('state') in ('RUNNING', 'QUESTION'):
            try:
                os.killpg(turn['pid'], 9)
            except OSError:
                pass
        shutil.rmtree(self.bin, ignore_errors=True)
        self.log.unlink(missing_ok=True)
        super().cleanup()

    def run(self, *args, owner=None, workspace=None, env=None):
        cmd = [sys.executable, '-B', str(SCRIPTS / 'ouroboros_cli.py'), '--workspace', workspace or str(self.path),
               '--owner', str(owner or self.owner), *args]
        full = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', **self.env, **(env or {})}
        full['PATH'] = f'{self.bin}{os.pathsep}{full.get("PATH", "")}'
        r = subprocess.run(cmd, capture_output=True, text=True, env=full)
        out = json.loads(r.stdout) if r.stdout.strip() else None
        return r.returncode, out

    def argv(self) -> list:
        return json.loads(self.log.read_text())['argv']

    def logged(self) -> dict:
        return json.loads(self.log.read_text())

    def message(self) -> str:
        """The user message the fake received as its first stdin line."""
        return self.logged()['message']

    def turn_file(self, name: str) -> Path:
        return self.private / 'turns' / name

    def answer(self, answers: dict, basis: str | None = None):
        args = ['session-answer', '--answers', self.file(json.dumps(answers), '.json')]
        if basis is not None:
            args += ['--basis', self.file(basis)]
        return self.ok(*args)

    def start(self, kind='ready', text='do the work\n', *extra, env=None):
        return self.ok('session-start', '--skill', kind, '--message', self.file(text), *extra, env=env)

    def send(self, text='continue\n', env=None):
        return self.ok('session-send', '--message', self.file(text), env=env)

    def wait(self, env=None, timeout=None):
        args = ['session-wait'] + (['--timeout', str(timeout)] if timeout is not None else [])
        return self.ok(*args, env=env)


class Base(unittest.TestCase):
    def setUp(self):
        self.ws = HostWorkspace()
        self.addCleanup(self.ws.cleanup)
        self.ws.approve_fresh()
        self.ws.start_cycle()


class ArgvShapeTests(Base):
    def test_first_turn_argv_prefix_allowlist_and_no_bypass(self):
        out = self.ws.start('ready', 'hello world\n')
        self.assertEqual(out['turn'], 1)
        self.assertIsNone(out['session_id'])
        self.ws.wait()
        argv = self.ws.argv()
        self.assertTrue(argv[0].endswith('/claude'))
        # No prompt argument: the message travels on stdin as the first stream-json line.
        self.assertEqual(argv[1:10], ['-p', '--input-format', 'stream-json', '--output-format', 'stream-json',
                                      '--verbose', '--permission-prompt-tool', 'stdio', '--allowedTools'])
        self.assertNotIn('--resume', argv)
        self.assertFalse(any(a.startswith('/dryforge:') for a in argv), argv)
        tools = argv[argv.index('--allowedTools') + 1]
        self.assertEqual(tools, claude_adapter.ALLOWED_TOOLS)
        self.assertEqual(tools.split(','), ['Bash', 'Edit', 'Write', 'Read', 'Glob', 'Grep', 'Agent', 'WebFetch',
                                            'WebSearch', 'NotebookEdit', 'Skill', 'TodoWrite', 'mcp__*'])
        self.assertNotIn('AskUserQuestion', tools)
        self.assertEqual(argv[argv.index('--max-turns') + 1], str(claude_adapter.MAX_TURNS))
        self.assertNotIn('--model', argv)
        for flag in BYPASS:
            self.assertFalse(any(flag in a for a in argv), argv)
        self.assertNotIn('--permission-mode', argv)
        logged = self.ws.logged()
        self.assertEqual(logged['cwd'], str(self.ws.path))
        self.assertEqual(logged['message'], '/dryforge:ready hello world\n')
        self.assertEqual(json.loads(logged['stdin']), dict(type='user', message=dict(role='user', content='/dryforge:ready hello world\n')))
        relay = json.loads(self.ws.turn_file('1.relay.json').read_text())
        self.assertTrue(relay['stdin_devnull'])

    def test_source_has_no_bypass_flags(self):
        src = (SCRIPTS / 'ouroboros/adapters/claude.py').read_text()
        for flag in BYPASS:
            self.assertNotIn(flag, src)

    def test_later_turns_resume_the_recorded_session_verbatim(self):
        self.ws.start('ready', 'first\n', env=dict(FAKE_CLAUDE_SESSION='s-abc'))
        self.ws.wait()
        out = self.ws.send('plain follow-up text\n', env=dict(FAKE_CLAUDE_SESSION='s-abc'))
        self.assertEqual((out['turn'], out['session_id']), (2, 's-abc'))
        self.ws.wait()
        argv = self.ws.argv()
        self.assertEqual(self.ws.message(), 'plain follow-up text\n')
        self.assertEqual(argv[argv.index('--resume') + 1], 's-abc')
        out = self.ws.start('go', 'now go\n', env=dict(FAKE_CLAUDE_SESSION='s-abc'))
        self.assertEqual((out['turn'], out['session_id']), (3, 's-abc'))
        self.ws.wait()
        argv = self.ws.argv()
        self.assertEqual(self.ws.message(), '/dryforge:go now go\n')
        self.assertEqual(argv[argv.index('--resume') + 1], 's-abc')
        for a in argv + [self.ws.logged()['stdin']]:
            for word in ('ouroboros', 'L1', 'run_id', 'approv'):
                self.assertNotIn(word, a.lower() if word != 'L1' else a)

    def test_fresh_starts_without_resume_and_records_session_reason(self):
        self.ws.start('ready', 'a\n', env=dict(FAKE_CLAUDE_SESSION='s-1'))
        self.ws.wait()
        self.assertEqual(self.ws.record()['session']['id'], 's-1')
        out = self.ws.start('migration', 'b\n', '--fresh', '--reason', 'replan', env=dict(FAKE_CLAUDE_SESSION='s-2'))
        self.assertIsNone(out['session_id'])
        run = self.ws.record()
        self.assertEqual((run['session']['id'], run['session']['reason']), (None, 'replan'))
        ev = [e for e in self.ws.events() if e['kind'] == 'session']
        self.assertEqual(ev[-1]['data']['reason'], 'replan')
        self.ws.wait()
        self.assertNotIn('--resume', self.ws.argv())
        self.assertEqual(self.ws.record()['session']['id'], 's-2')


class WaitAndStatusTests(Base):
    def test_wait_returns_complete_with_parsed_keys(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_SESSION='s-9', FAKE_CLAUDE_COST='0.5'))
        run = self.ws.record()
        self.assertEqual(run['turn_count'], 1)
        self.assertEqual({k: run['turn'][k] for k in ('n', 'kind', 'state')}, dict(n=1, kind='ready', state='RUNNING'))
        self.assertEqual(self.ws.events()[-1]['kind'], 'turn')
        self.assertEqual(self.ws.events()[-1]['cycle_id'], 'c1')
        out = self.ws.wait()
        for key in ('state', 'session_id', 'text', 'num_turns', 'cost_usd', 'cost_total_usd', 'permission_denials', 'is_error',
                    'subtype', 'raw_path', 'usage', 'run_status', 'stopped_reason', 'skills', 'auto_allowed',
                    'questions', 'stream_path'):
            self.assertIn(key, out)
        self.assertEqual(out['state'], 'COMPLETE')
        self.assertEqual(out['skills'], ['dryforge:ready', 'dryforge:go', 'dryforge:migration'])
        self.assertEqual((out['auto_allowed'], out['questions']), ([], 0))
        self.assertEqual(Path(out['stream_path']).name, '1.stream.jsonl')
        self.assertTrue(Path(out['stream_path']).is_file())
        self.assertEqual((out['run_status'], out['stopped_reason']), ('ACTIVE', None))
        self.assertEqual(out['usage'], dict(input_tokens=10, cache_read_input_tokens=100,
                                            cache_creation_input_tokens=20, output_tokens=5))
        self.assertEqual(out['session_id'], 's-9')
        self.assertEqual(out['text'], 'echo: /dryforge:ready x\n')
        self.assertEqual((out['num_turns'], out['cost_usd'], out['is_error'], out['subtype']), (3, 0.5, False, 'success'))
        self.assertEqual(out['permission_denials'], [])
        self.assertTrue((self.ws.private / 'turns' / '1.json').is_file())
        self.assertEqual(Path(out['raw_path']).name, '1.json')
        run = self.ws.record()
        self.assertEqual(run['turn']['state'], 'COMPLETE')
        self.assertEqual(run['session']['id'], 's-9')
        self.assertEqual(json.loads((self.ws.private / 'owner.json').read_text())['session_id'], 's-9')
        self.assertEqual(run['cycles'][0]['session_id'], 's-9')
        self.assertEqual(run['turn']['usage']['output_tokens'], 5)
        ev = self.ws.events()[-1]
        self.assertEqual((ev['kind'], ev['actor']), ('turn_result', 'host'))
        self.assertNotIn('text', ev['data'])
        self.assertIn('text_path', ev['data'])
        self.assertEqual(ev['data']['usage']['input_tokens'], 10)

    def test_usage_counts_missing_from_the_result_are_null(self):
        adapter = claude_adapter.ClaudeAdapter()
        raw = self.ws.private / 'turns' / 'probe.json'
        raw.write_text(json.dumps(dict(session_id='s-u', result='x', usage=dict(input_tokens=7, output_tokens='many'))))
        out = adapter.result(ports.Turn(pid=os.getpid(), raw_path=raw))
        self.assertEqual(out['usage'], dict(input_tokens=7, cache_read_input_tokens=None,
                                            cache_creation_input_tokens=None, output_tokens=None))
        raw.write_text(json.dumps(dict(session_id='s-u', result='x')))
        out = adapter.result(ports.Turn(pid=os.getpid(), raw_path=raw))
        self.assertEqual(out['usage'], {k: None for k in claude_adapter.USAGE_KEYS})
        self.assertIn('usage', claude_adapter.RESULT_KEYS)

    def test_turn_files_are_private(self):
        self.ws.start('ready', 'x\n')
        self.ws.wait()
        turns = self.ws.private / 'turns'
        for name in ('1.json', '1.err', '1.exit', '1.txt', '1.msg', '1.stream.jsonl', '1.init.json', '1.relay.json'):
            with self.subTest(name=name):
                self.assertTrue((turns / name).is_file())
                self.assertEqual(stat.S_IMODE((turns / name).stat().st_mode), 0o600)

    def test_second_cycle_records_the_session_it_runs_in(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_SESSION='s-c'))
        self.ws.wait()
        self.ws.evaluate('CONTINUE')
        self.ws.start_cycle()
        run = self.ws.record()
        self.assertEqual([c['session_id'] for c in run['cycles']], ['s-c', 's-c'])
        self.ws.start('ready', 'y\n', env=dict(FAKE_CLAUDE_SESSION='s-c'))
        self.ws.wait()
        self.assertEqual(self.ws.record()['cycles'][1]['session_id'], 's-c')
        # A fresh session inside the cycle replaces the cycle's recorded session once its first turn names one.
        self.ws.evaluate('CONTINUE')
        self.ws.start_cycle()
        self.ws.start('ready', 'z\n', '--fresh', '--reason', 'replan', env=dict(FAKE_CLAUDE_SESSION='s-d'))
        self.assertIsNone(self.ws.record()['cycles'][2]['session_id'])
        self.ws.wait()
        run = self.ws.record()
        self.assertEqual((run['session']['id'], run['cycles'][2]['session_id']), ('s-d', 's-d'))

    def test_interrupted_first_turn_still_records_its_session_id(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_MODE='fail', FAKE_CLAUDE_SESSION='s-i'))
        out = self.ws.wait()
        self.assertEqual((out['state'], out['session_id']), ('INTERRUPTED', 's-i'))
        run = self.ws.record()
        self.assertEqual(run['session']['id'], 's-i')
        self.assertEqual(run['cycles'][0]['session_id'], 's-i')
        self.assertEqual(json.loads((self.ws.private / 'owner.json').read_text())['session_id'], 's-i')
        out = self.ws.send('resume\n', env=dict(FAKE_CLAUDE_SESSION='s-i'))
        self.assertEqual(out['session_id'], 's-i')
        self.ws.wait()
        self.assertEqual(self.ws.argv()[self.ws.argv().index('--resume') + 1], 's-i')

    def test_status_running_while_sleeping_then_complete(self):
        t = time.monotonic()
        out = self.ws.start('ready', 'slow\n', env=dict(FAKE_CLAUDE_SLEEP='1.5'))
        self.assertLess(time.monotonic() - t, 1.0, 'session-start must return before the turn ends')
        st = self.ws.ok('session-status')
        self.assertEqual((st['state'], st['pid'], st['turn']), ('RUNNING', out['pid'], 1))
        w = self.ws.wait(timeout=0.2)
        self.assertEqual(w['state'], 'RUNNING')
        self.assertGreaterEqual(w['waited'], 0.2)
        w = self.ws.wait()
        self.assertEqual(w['state'], 'COMPLETE')
        self.assertEqual(self.ws.ok('session-status')['state'], 'COMPLETE')

    def test_cost_added_exactly_once(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_COST='0.25'))
        self.ws.wait()
        self.ws.ok('session-status'); self.ws.wait(); self.ws.ok('session-status')
        self.assertEqual(self.ws.record()['spent_usd'], 0.25)
        self.assertEqual(sum(1 for k in self.ws.kinds() if k == 'turn_result'), 1)
        self.ws.send('more\n', env=dict(FAKE_CLAUDE_COST='0.5'))
        self.ws.wait(); self.ws.wait()
        self.assertEqual(self.ws.record()['spent_usd'], 0.5)

    def test_cost_is_the_delta_of_the_session_total(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_COST='1.0'))
        out = self.ws.wait()
        self.assertEqual((out['cost_usd'], out['cost_total_usd']), (1.0, 1.0))
        run = self.ws.record()
        self.assertEqual((run['spent_usd'], run['session']['cost_total_usd']), (1.0, 1.0))
        self.ws.send('more\n', env=dict(FAKE_CLAUDE_COST='1.5'))
        out = self.ws.wait()
        self.assertEqual((out['cost_usd'], out['cost_total_usd']), (0.5, 1.5))
        run = self.ws.record()
        self.assertEqual((run['spent_usd'], run['session']['cost_total_usd']), (1.5, 1.5))
        self.assertEqual((run['turn']['cost_usd'], run['turn']['cost_total_usd']), (0.5, 1.5))
        ev = self.ws.events()[-1]
        self.assertEqual((ev['kind'], ev['data']['cost_usd'], ev['data']['cost_total_usd']), ('turn_result', 0.5, 1.5))
        # A fresh session starts from a zero baseline.
        self.ws.start('ready', 'y\n', '--fresh', '--reason', 'replan', env=dict(FAKE_CLAUDE_COST='0.2'))
        out = self.ws.wait()
        self.assertEqual((out['cost_usd'], out['cost_total_usd']), (0.2, 0.2))
        run = self.ws.record()
        self.assertAlmostEqual(run['spent_usd'], 1.7)
        self.assertEqual(run['session']['cost_total_usd'], 0.2)
        # A total below the last one (a host reset) is charged in full and becomes the new baseline.
        self.ws.send('z\n', env=dict(FAKE_CLAUDE_COST='0.1'))
        out = self.ws.wait()
        self.assertEqual(out['cost_usd'], 0.1)
        run = self.ws.record()
        self.assertAlmostEqual(run['spent_usd'], 1.8)
        self.assertEqual(run['session']['cost_total_usd'], 0.1)

    def test_session_id_mismatch_is_an_interrupted_turn(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_SESSION='s-1'))
        self.ws.wait()
        self.ws.send('y\n', env=dict(FAKE_CLAUDE_SESSION='s-2', FAKE_CLAUDE_COST='0.25'))
        out = self.ws.wait()
        self.assertEqual((out['state'], out['reason'], out['session_id']), ('INTERRUPTED', 'session id mismatch', 's-2'))
        run = self.ws.record()
        self.assertEqual(run['session']['id'], 's-1')
        self.assertEqual(run['turn']['state'], 'INTERRUPTED')
        self.assertIn('mismatch', run['turn']['reason'])
        self.assertEqual(self.ws.kinds()[-1], 'interrupt')
        self.assertEqual(self.ws.record()['spent_usd'], 0.25)
        again = self.ws.ok('session-status')
        self.assertEqual(again['state'], 'INTERRUPTED')
        self.assertEqual(self.ws.record()['spent_usd'], 0.25)


class BudgetTests(Base):
    def test_turn_cost_over_budget_stops_the_run(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_COST='10.5'))  # proposal budget is 10
        out = self.ws.wait()
        self.assertEqual(out['state'], 'COMPLETE')
        self.assertEqual((out['run_status'], out['stopped_reason']), ('STOPPED', 'limit:budget'))
        run = self.ws.record()
        self.assertEqual((run['status'], run['stopped_reason'], run['spent_usd']), ('STOPPED', 'limit:budget', 10.5))
        self.assertEqual(run['stopped_at'], dict(cycle_id='c1', stage='ready', checkpoint='a' * 40))
        self.assertEqual(run['turn']['state'], 'COMPLETE')
        self.assertEqual(run['session']['id'], 'sess-fake-1')
        ev = self.ws.events()[-1]
        self.assertEqual((ev['kind'], ev['actor'], ev['cycle_id']), ('stop', 'L1', 'c1'))
        self.assertEqual((ev['data']['reason'], ev['data']['turn'], ev['data']['budget_usd']), ('limit:budget', 1, 10))
        self.assertEqual(self.ws.kinds()[-2], 'turn_result')
        again = self.ws.ok('session-status')
        self.assertEqual((again['state'], again['run_status']), ('COMPLETE', 'STOPPED'))
        self.assertEqual(self.ws.kinds().count('stop'), 1)
        out = self.ws.blocked('session-send', '--message', self.ws.file('more'))
        self.assertIn('STOPPED', out['error'])
        # The user resumes with the same proposal; the budget is still exceeded, so no turn is launched.
        self.ws.ok('approve')
        self.assertEqual(self.ws.record()['status'], 'ACTIVE')
        out = self.ws.blocked('session-send', '--message', self.ws.file('more'))
        self.assertIn('budget', out['error'])
        self.assertEqual(self.ws.record()['turn_count'], 1)
        # Raising the budget lets the run continue.
        self.ws.draft(proposal_text(budget='20'))
        self.ws.ok('shown'); self.ws.ok('approve')
        self.ws.send('more\n', env=dict(FAKE_CLAUDE_COST='11.5'))  # session total; this turn costs 1
        out = self.ws.wait()
        self.assertEqual((out['state'], out['run_status']), ('COMPLETE', 'ACTIVE'))
        self.assertEqual((out['cost_usd'], out['cost_total_usd']), (1.0, 11.5))
        self.assertEqual(self.ws.record()['spent_usd'], 11.5)

    def test_no_cap_budget_never_stops_a_turn(self):
        ws = HostWorkspace()
        self.addCleanup(ws.cleanup)
        ws.approve_fresh(proposal_text(budget='no cap'))
        ws.start_cycle()
        ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_COST='999'))
        out = ws.wait()
        self.assertEqual((out['run_status'], ws.record()['status']), ('ACTIVE', 'ACTIVE'))

    def test_last_allowed_cycle_still_runs_turns(self):
        for _ in range(2):
            self.ws.evaluate('CONTINUE')
            self.ws.start_cycle()
        self.assertEqual(len(self.ws.record()['cycles']), 3)  # max cycles is 3; the open cycle is the last one
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_COST='1'))
        out = self.ws.wait()
        self.assertEqual((out['state'], out['run_status']), ('COMPLETE', 'ACTIVE'))
        self.ws.send('more\n', env=dict(FAKE_CLAUDE_COST='11'))  # session total; the budget is still watched in the last cycle
        out = self.ws.wait()
        self.assertEqual((out['run_status'], out['stopped_reason']), ('STOPPED', 'limit:budget'))
        self.ws.draft(proposal_text(cycles=2, budget='20'))  # a lowered cycle limit the open cycle already exceeds
        self.ws.ok('shown'); self.ws.ok('approve')
        self.assertEqual(self.ws.record()['status'], 'ACTIVE')
        out = self.ws.blocked('session-send', '--message', self.ws.file('x'))
        self.assertIn('cycles', out['error'])

    def test_launch_refuses_once_any_limit_is_exceeded(self):
        self.ws.start('ready', 'x\n')
        self.ws.wait()
        run = self.ws.record()
        run['stalled_cycles'] = 2
        (self.ws.private / 'run.json').write_text(json.dumps(run))
        out = self.ws.blocked('session-send', '--message', self.ws.file('x'))
        self.assertIn('stalled', out['error'])
        self.assertEqual(self.ws.record()['turn_count'], 1)


class GateThreeTests(Base):
    def test_go_fresh_refused_once_ready_ran_in_a_session(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_SESSION='s-r'))
        self.ws.wait()
        self.ws.ok('cycle-stage', '--stage', 'go', '--ready-digest', 'd' * 64)
        out = self.ws.blocked('session-start', '--skill', 'go', '--message', self.ws.file('go'), '--fresh',
                              '--reason', 'try')
        self.assertIn('s-r', out['error'])
        run = self.ws.record()
        self.assertEqual((run['turn_count'], run['session']['id'], run['turn']['state']), (1, 's-r', 'COMPLETE'))
        self.assertEqual(self.ws.kinds().count('session'), 1)  # no fresh session was recorded
        out = self.ws.start('go', 'go\n', env=dict(FAKE_CLAUDE_SESSION='s-r'))
        self.assertEqual(out['session_id'], 's-r')
        self.ws.wait()
        self.assertEqual(self.ws.argv()[self.ws.argv().index('--resume') + 1], 's-r')

    def test_go_fresh_allowed_when_no_ready_session_is_recorded(self):
        self.ws.evaluate('CONTINUE')
        self.ws.start_cycle()
        self.assertIsNone(self.ws.record()['cycles'][1]['session_id'])
        self.ws.ok('cycle-stage', '--stage', 'ready', '--ready-digest', 'd' * 64)
        self.ws.start('go', 'go\n', '--fresh', '--reason', 'no session yet')
        self.ws.wait()


class InterruptedTests(Base):
    def check_interrupted(self, out):
        self.assertEqual(out['state'], 'INTERRUPTED')
        self.assertEqual(self.ws.record()['turn']['state'], 'INTERRUPTED')
        kinds = self.ws.kinds()
        self.assertEqual(kinds[-2:], ['turn_result', 'interrupt'])
        self.assertNotIn('unanswered', kinds)
        ev = self.ws.events()[-1]
        self.assertEqual(ev['actor'], 'host')
        self.assertEqual(ev['cycle_id'], 'c1')

    def test_garbage_output(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_MODE='garbage'))
        out = self.ws.wait()
        self.check_interrupted(out)
        self.assertIsNone(out['session_id'])
        self.assertEqual(out['reason'], 'result file missing')
        self.assertTrue(out['stderr_path'].endswith('1.err'))
        self.assertIsNone(self.ws.record()['session']['id'])
        self.assertEqual(self.ws.turn_file('1.stream.jsonl').read_text(), 'not json at all\n')

    def test_non_zero_exit(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_MODE='fail'))
        out = self.ws.wait()
        self.check_interrupted(out)
        self.assertEqual(out['exit_code'], 1)

    def test_is_error_true(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_MODE='error', FAKE_CLAUDE_COST='0.1'))
        out = self.ws.wait()
        self.check_interrupted(out)
        self.assertTrue(out['is_error'])
        self.assertEqual(out['subtype'], 'error_during_execution')
        self.assertEqual(self.ws.record()['spent_usd'], 0.1)
        self.assertEqual(self.ws.ok('session-status')['state'], 'INTERRUPTED')
        self.assertEqual(self.ws.record()['spent_usd'], 0.1)

    def test_missing_session_id(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_MODE='nosession'))
        out = self.ws.wait()
        self.check_interrupted(out)
        self.assertIsNone(out['session_id'])


class StopTests(Base):
    def test_stop_sleeping_turn(self):
        self.ws.blocked('session-stop')
        out = self.ws.start('ready', 'slow\n', env=dict(FAKE_CLAUDE_SLEEP='30'))
        pid = out['pid']
        self.assertTrue(pid_alive(pid))
        t = time.monotonic()
        st = self.ws.ok('session-stop')
        self.assertLess(time.monotonic() - t, claude_adapter.STOP_GRACE + 3)
        self.assertEqual((st['state'], st['turn']), ('STOPPED', 1))
        deadline = time.monotonic() + 5
        while pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(pid_alive(pid))
        run = self.ws.record()
        self.assertEqual(run['turn']['state'], 'STOPPED')
        ev = self.ws.events()[-1]
        self.assertEqual((ev['kind'], ev['actor'], ev['data']['turn']), ('stop', 'L1', 1))
        self.assertEqual(self.ws.ok('session-status')['state'], 'STOPPED')
        self.assertFalse((self.ws.private / 'turns' / '1.exit').exists())
        self.ws.blocked('session-stop')
        self.ws.start('ready', 'again\n')  # a stopped turn is not RUNNING
        self.ws.wait()

    def test_stop_returns_only_once_the_whole_group_is_gone(self):
        pidfile = self.ws.path.parent / f'fakepid-{self.ws.path.name}'
        self.addCleanup(lambda: pidfile.unlink(missing_ok=True))
        out = self.ws.start('ready', 'slow\n', env=dict(FAKE_CLAUDE_SLEEP='30', FAKE_CLAUDE_PIDFILE=str(pidfile)))
        pid = out['pid']
        deadline = time.monotonic() + 5
        while not (pidfile.exists() and self.ws.turn_file('1.relay.json').exists()) and time.monotonic() < deadline:
            time.sleep(0.05)
        relay_pid = json.loads(self.ws.turn_file('1.relay.json').read_text())['pid']
        self.assertTrue(pid_alive(relay_pid) and pid_alive(int(pidfile.read_text())))
        st = self.ws.ok('session-stop')
        self.assertEqual(st['state'], 'STOPPED')
        # Right after session-stop returns, no member of the turn's process group is left ...
        with self.assertRaises(ProcessLookupError):
            os.killpg(pid, 0)
        # ... so a session-send in this window can never overlap a claude still being taken down.
        self.assertTrue(self.ws.turn_file('1.exit').exists() or not pid_alive(relay_pid))
        self.assertFalse(pid_alive(int(pidfile.read_text())))

    def test_stop_on_an_exited_turn_settles_it_instead(self):
        out = self.ws.start('ready', 'quick\n', env=dict(FAKE_CLAUDE_COST='0.3'))
        deadline = time.monotonic() + 10
        while not (self.ws.private / 'turns' / '1.exit').exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        st = self.ws.ok('session-stop')
        self.assertEqual((st['state'], st['turn'], st['session_id']), ('COMPLETE', 1, 'sess-fake-1'))
        run = self.ws.record()
        self.assertEqual((run['turn']['state'], run['spent_usd']), ('COMPLETE', 0.3))
        self.assertNotIn('stop', self.ws.kinds())
        self.assertEqual(self.ws.kinds()[-1], 'turn_result')

    def test_alive_consults_the_exit_file_before_the_pid(self):
        adapter = claude_adapter.ClaudeAdapter()
        sleeper = subprocess.Popen(['sleep', '30'])
        self.addCleanup(sleeper.kill)
        raw = self.ws.private / 'turns' / 'probe.json'
        turn = ports.Turn(pid=sleeper.pid, raw_path=raw)
        self.assertTrue(adapter.alive(turn))
        raw.with_suffix('.exit').write_text('0\n')
        self.assertFalse(adapter.alive(turn))
        self.assertTrue(pid_alive(sleeper.pid))
        raw.with_suffix('.exit').unlink()
        self.assertTrue(adapter.alive(turn))
        sleeper.kill(); sleeper.wait()
        self.assertFalse(adapter.alive(turn))


class RefusalTests(unittest.TestCase):
    def setUp(self):
        self.ws = HostWorkspace()
        self.addCleanup(self.ws.cleanup)

    def test_status_not_active(self):
        self.ws.draft()
        out = self.ws.blocked('session-start', '--skill', 'ready', '--message', self.ws.file('x'))
        self.assertIn('DRAFT', out['error'])
        self.assertNotIn('turn', self.ws.record())
        self.assertFalse(self.ws.log.exists())
        self.ws.ok('shown'); self.ws.ok('approve')
        self.ws.ok('stop', '--reason', 'abort')
        self.ws.blocked('session-start', '--skill', 'ready', '--message', self.ws.file('x'))
        self.ws.blocked('session-send', '--message', self.ws.file('x'))

    def test_send_without_session_and_bad_skill(self):
        self.ws.approve_fresh()
        self.ws.blocked('session-send', '--message', self.ws.file('x'))
        self.ws.blocked('session-start', '--skill', 'bogus', '--message', self.ws.file('x'))
        self.ws.blocked('session-start', '--skill', 'ready', '--message', str(self.ws.path / 'missing.md'))
        self.ws.blocked('session-wait')
        self.ws.blocked('session-status')
        self.assertEqual(len(self.ws.events()), 3)

    def test_running_turn_blocks_another_start(self):
        self.ws.approve_fresh()
        self.ws.start('ready', 'slow\n', env=dict(FAKE_CLAUDE_SLEEP='2'))
        self.ws.blocked('session-start', '--skill', 'go', '--message', self.ws.file('x'))
        self.ws.blocked('session-send', '--message', self.ws.file('x'))
        self.assertEqual(self.ws.record()['turn_count'], 1)
        self.ws.ok('session-stop')

    def test_live_other_owner_refuses_every_session_command(self):
        self.ws.approve_fresh()
        other = subprocess.Popen(['sleep', '30'])
        self.addCleanup(other.kill)
        (self.ws.private / 'owner.json').write_text(json.dumps(dict(pid=other.pid, started='x')))
        for args in (['session-start', '--skill', 'ready', '--message', self.ws.file('x')],
                     ['session-send', '--message', self.ws.file('x')], ['session-wait'], ['session-status'],
                     ['session-stop']):
            out = self.ws.blocked(*args)
            self.assertIn(str(other.pid), out['error'], args)
        self.assertNotIn('turn', self.ws.record())


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.ws = HostWorkspace()
        self.addCleanup(self.ws.cleanup)

    def test_doctor_with_dryforge_enabled(self):
        out = self.ws.ok('doctor', '--host', 'claude')
        self.assertEqual(out['host'], 'claude')
        self.assertEqual(out['claude'], str(self.ws.bin / 'claude'))
        self.assertEqual(out['version'], '2.1.0 (Claude Code)')
        self.assertEqual(out['dryforge'], dict(installed=True, enabled=True))

    def test_doctor_disabled_and_missing(self):
        out = self.ws.ok('doctor', env=dict(FAKE_CLAUDE_DRYFORGE='disabled'))
        self.assertEqual(out['dryforge'], dict(installed=True, enabled=False))
        out = self.ws.ok('doctor', env=dict(FAKE_CLAUDE_DRYFORGE='missing'))
        self.assertEqual(out['dryforge'], dict(installed=False, enabled=False))

    def test_doctor_without_claude(self):
        (self.ws.bin / 'claude').unlink()
        out = self.ws.ok('doctor', env=dict(PATH=str(self.ws.bin)))
        self.assertIsNone(out['claude'])
        self.assertIsNone(out['version'])
        self.assertEqual(out['dryforge'], dict(installed=False, enabled=False))


class PortTests(unittest.TestCase):
    def test_adapter_satisfies_port_and_registry(self):
        adapter = adapters.for_host('claude')
        self.assertIsInstance(adapter, claude_adapter.ClaudeAdapter)
        for name in ('start', 'send', 'terminate', 'result', 'alive', 'doctor', 'questions', 'answer', 'session_id'):
            self.assertTrue(callable(getattr(ports.HostSession, name)), name)
            self.assertTrue(callable(getattr(adapter, name)), name)
        with self.assertRaises(ValueError):
            adapters.for_host('codex')

    def test_command_line_builder(self):
        argv = claude_adapter.command_line(None)
        self.assertEqual(argv[:9], ['claude', '-p', '--input-format', 'stream-json', '--output-format', 'stream-json',
                                    '--verbose', '--permission-prompt-tool', 'stdio'])
        self.assertNotIn('--resume', argv)
        argv = claude_adapter.command_line('s-1', model='sonnet')
        self.assertEqual(argv[argv.index('--resume') + 1], 's-1')
        self.assertEqual(argv[argv.index('--model') + 1], 'sonnet')
        self.assertNotIn('AskUserQuestion', claude_adapter.ALLOWED_TOOLS)

    def test_question_tool_not_in_allow_list(self):
        self.assertEqual(claude_adapter.QUESTION_TOOL, 'AskUserQuestion')
        self.assertNotIn(claude_adapter.QUESTION_TOOL, claude_adapter.ALLOWED_TOOLS.split(','))
        self.assertNotIn(claude_adapter.QUESTION_TOOL, claude_adapter.ClaudeAdapter().allowed_tools.split(','))

    def test_wire_answers_is_the_adapter_encoding(self):
        self.assertEqual(claude_adapter.wire_answers({'a?': 'Alpha', 'b?': ['Alpha', 'Beta'], 'c?': {'other': 'free text'}}),
                         {'a?': 'Alpha', 'b?': 'Alpha, Beta', 'c?': 'free text'})


class QuestionTests(Base):
    """The structured-question relay: QUESTION state, session-answer, continuation, stop and auto-allow."""

    def test_question_arrives_as_question_state_and_answer_continues_to_complete(self):
        self.ws.start('ready', 'ask me\n', env=dict(FAKE_CLAUDE_QUESTIONS='1', FAKE_CLAUDE_SESSION='s-q'))
        out = self.ws.wait(env=dict(FAKE_CLAUDE_QUESTIONS='1'))
        self.assertEqual((out['state'], out['round'], out['turn'], out['kind']), ('QUESTION', 1, 1, 'ready'))
        self.assertEqual(len(out['questions']), 1)
        q = out['questions'][0]
        self.assertEqual(q['question'], 'Question 1?')
        self.assertEqual([o['label'] for o in q['options']], ['Alpha', 'Beta'])
        self.assertFalse(q['multiSelect'])
        run = self.ws.record()
        self.assertEqual(run['turn']['state'], 'QUESTION')
        self.assertEqual(run['turn']['question'], dict(round=1, questions=out['questions']))
        self.assertEqual(run['session']['id'], 's-q')  # bound early from the init event
        shown = self.ws.ok('show')
        self.assertEqual(shown['turn'], dict(n=1, state='QUESTION', kind='ready', question=run['turn']['question']))
        st = self.ws.ok('session-status')
        self.assertEqual((st['state'], st['round']), ('QUESTION', 1))
        self.assertEqual(stat.S_IMODE(self.ws.turn_file('1.q1.json').stat().st_mode), 0o600)
        bundle = json.loads(self.ws.turn_file('1.q1.json').read_text())
        self.assertEqual((bundle['round'], bundle['request_id'], bundle['tool_use_id']), (1, 'req-1', 'toolu-1'))
        # Refusals name the offending key and leave the question open.
        for answers, needle in (({'Nope?': 'Alpha'}, 'Nope?'), ({'Question 1?': 'Gamma'}, 'Gamma'),
                                ({'Question 1?': ['Alpha']}, 'multiSelect'), ({}, 'Question 1?'),
                                ({'Question 1?': 7}, 'Question 1?'), ({'Question 1?': {'else': 'x'}}, 'Question 1?'),
                                ({'Question 1?': {'other': ''}}, 'Question 1?')):
            with self.subTest(answers=answers):
                err = self.ws.blocked('session-answer', '--answers', self.ws.file(json.dumps(answers), '.json'))
                self.assertIn(needle, err['error'])
        self.ws.blocked('session-answer', '--answers', self.ws.file('[1, 2]', '.json'))
        self.assertFalse(self.ws.turn_file('1.a1.json').exists())
        self.assertEqual(self.ws.record()['turn']['state'], 'QUESTION')
        self.assertNotIn('question', self.ws.kinds())
        out = self.ws.answer({'Question 1?': 'Beta'}, basis='the proposal prefers the second option')
        self.assertEqual((out['state'], out['round'], out['turn']), ('RUNNING', 1, 1))
        self.assertEqual(stat.S_IMODE(self.ws.turn_file('1.a1.json').stat().st_mode), 0o600)
        self.assertEqual(json.loads(self.ws.turn_file('1.a1.json').read_text()), dict(round=1, answers={'Question 1?': 'Beta'}))
        run = self.ws.record()
        self.assertEqual(run['turn']['state'], 'RUNNING')
        self.assertNotIn('question', run['turn'])
        self.assertEqual(run['turn']['questions_answered'], 1)
        events = self.ws.events()
        self.assertEqual([(e['kind'], e['actor'], e['cycle_id']) for e in events[-2:]],
                         [('question', 'L2', 'c1'), ('answer', 'L1', 'c1')])
        self.assertEqual(events[-2]['data'], bundle)
        self.assertEqual(events[-1]['data'], dict(round=1, answers={'Question 1?': 'Beta'},
                                                  basis='the proposal prefers the second option'))
        out = self.ws.wait()
        self.assertEqual(out['state'], 'COMPLETE')
        self.assertEqual(out['text'], 'echo: /dryforge:ready ask me\n | answers: Beta')
        self.assertEqual(out['questions'], 1)
        self.assertEqual(out['session_id'], 's-q')
        self.assertEqual(self.ws.ok('show')['turn']['state'], 'COMPLETE')
        self.assertEqual(stat.S_IMODE(self.ws.turn_file('1.stream.jsonl').stat().st_mode), 0o600)
        stream = [json.loads(l) for l in self.ws.turn_file('1.stream.jsonl').read_text().splitlines()]
        self.assertEqual([e['type'] for e in stream], ['system', 'control_request', 'result'])
        err = self.ws.blocked('session-answer', '--answers', self.ws.file(json.dumps({'Question 1?': 'Beta'}), '.json'))
        self.assertIn('no open question', err['error'])

    def test_two_rounds_with_multi_select_and_other(self):
        env = dict(FAKE_CLAUDE_QUESTIONS='2', FAKE_CLAUDE_MULTI='1')
        self.ws.start('ready', 'twice\n', env=env)
        out = self.ws.wait()
        self.assertEqual((out['state'], out['round']), ('QUESTION', 1))
        self.assertTrue(out['questions'][0]['multiSelect'])
        err = self.ws.blocked('session-answer', '--answers', self.ws.file(json.dumps({'Question 1?': ['Alpha', 'Gamma']}), '.json'))
        self.assertIn('Gamma', err['error'])
        self.ws.blocked('session-answer', '--answers', self.ws.file(json.dumps({'Question 1?': []}), '.json'))
        self.ws.answer({'Question 1?': ['Alpha', 'Beta']})
        out = self.ws.wait()
        self.assertEqual((out['state'], out['round']), ('QUESTION', 2))
        self.assertEqual(out['questions'][0]['question'], 'Question 2?')
        self.assertEqual(self.ws.record()['turn']['question']['round'], 2)
        self.assertTrue(self.ws.turn_file('1.q2.json').is_file())
        out = self.ws.answer({'Question 2?': {'other': 'something else'}})
        self.assertEqual(out['round'], 2)
        # The record keeps L1's structured answers; the adapter writes Claude's wire strings to the relay file.
        self.assertEqual(json.loads(self.ws.turn_file('1.a1.json').read_text())['answers'], {'Question 1?': 'Alpha, Beta'})
        self.assertEqual(json.loads(self.ws.turn_file('1.a2.json').read_text())['answers'], {'Question 2?': 'something else'})
        out = self.ws.wait()
        self.assertEqual(out['state'], 'COMPLETE')
        self.assertEqual(out['text'], 'echo: /dryforge:ready twice\n | answers: Alpha, Beta / something else')
        self.assertEqual(out['questions'], 2)
        self.assertEqual(self.ws.record()['turn']['questions_answered'], 2)
        answers = [e['data']['answers'] for e in self.ws.events() if e['kind'] == 'answer']
        self.assertEqual(answers, [{'Question 1?': ['Alpha', 'Beta']}, {'Question 2?': {'other': 'something else'}}])
        self.assertEqual(self.ws.kinds().count('question'), 2)

    def test_launch_during_question_is_blocked(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_QUESTIONS='1'))
        self.assertEqual(self.ws.wait()['state'], 'QUESTION')
        for args in (['session-start', '--skill', 'go', '--message', self.ws.file('go')],
                     ['session-send', '--message', self.ws.file('more')]):
            err = self.ws.blocked(*args)
            self.assertIn('answer or stop first', err['error'])
        self.assertEqual(self.ws.record()['turn_count'], 1)
        self.ws.ok('session-stop')

    def test_stop_during_question_records_unanswered(self):
        pidfile = self.ws.path.parent / f'fakepid-{self.ws.path.name}'
        self.addCleanup(lambda: pidfile.unlink(missing_ok=True))
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_QUESTIONS='1', FAKE_CLAUDE_PIDFILE=str(pidfile)))
        out = self.ws.wait()
        self.assertEqual(out['state'], 'QUESTION')
        fake_pid = int(pidfile.read_text())
        self.assertTrue(pid_alive(fake_pid))
        st = self.ws.ok('session-stop')
        self.assertEqual((st['state'], st['turn']), ('STOPPED', 1))
        deadline = time.monotonic() + 5
        while pid_alive(fake_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(pid_alive(fake_pid))
        run = self.ws.record()
        self.assertEqual(run['turn']['state'], 'STOPPED')
        self.assertNotIn('question', run['turn'])
        events = self.ws.events()
        self.assertEqual([(e['kind'], e['actor']) for e in events[-3:]],
                         [('question', 'L2'), ('unanswered', 'L1'), ('stop', 'L1')])
        self.assertEqual(events[-3]['data']['round'], 1)
        self.assertEqual(events[-3]['data']['questions'][0]['question'], 'Question 1?')
        self.assertEqual(events[-2]['data'], dict(round=1))
        self.assertEqual(self.ws.ok('session-status')['state'], 'STOPPED')
        self.assertEqual(self.ws.ok('show')['turn']['state'], 'STOPPED')
        self.ws.blocked('session-stop')
        self.ws.start('ready', 'again\n')
        self.assertEqual(self.ws.wait()['state'], 'COMPLETE')

    def test_turn_ending_with_an_open_question_settles_unanswered(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_QUESTIONS='1'))
        out = self.ws.wait()
        self.assertEqual(out['state'], 'QUESTION')
        # The host goes away without an answer: the question is recorded as unanswered at settlement.
        os.killpg(self.ws.record()['turn']['pid'], 9)
        deadline = time.monotonic() + 5
        while pid_alive(self.ws.record()['turn']['pid']) and time.monotonic() < deadline:
            time.sleep(0.05)
        out = self.ws.wait()
        self.assertEqual(out['state'], 'INTERRUPTED')
        kinds = self.ws.kinds()
        self.assertEqual(kinds[-4:], ['question', 'unanswered', 'turn_result', 'interrupt'])
        self.assertNotIn('question', self.ws.record()['turn'])

    def test_permission_request_is_auto_allowed_and_recorded(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_PERMISSION='1'))
        out = self.ws.wait()
        self.assertEqual(out['state'], 'COMPLETE')
        self.assertEqual(out['auto_allowed'], [dict(tool_name='Bash', tool_use_id='toolu-perm')])
        self.assertEqual(out['permission_denials'], [])
        self.assertEqual(out['questions'], 0)
        self.assertEqual(self.ws.record()['turn']['auto_allowed'], out['auto_allowed'])
        self.assertEqual(json.loads(self.ws.turn_file('1.auto.json').read_text()), out['auto_allowed'])
        stream = [json.loads(l) for l in self.ws.turn_file('1.stream.jsonl').read_text().splitlines()]
        self.assertEqual([e['type'] for e in stream], ['system', 'control_request', 'result'])
        self.assertNotIn('question', self.ws.kinds())

    def test_session_id_is_bound_early_from_the_init_event(self):
        self.ws.start('ready', 'slow\n', env=dict(FAKE_CLAUDE_SLEEP='1.5', FAKE_CLAUDE_SESSION='s-early'))
        deadline = time.monotonic() + 5
        while not self.ws.turn_file('1.init.json').exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertIsNone(self.ws.record()['session']['id'])
        st = self.ws.ok('session-status')
        self.assertEqual(st['state'], 'RUNNING')
        run = self.ws.record()
        self.assertEqual((run['session']['id'], run['cycles'][0]['session_id']), ('s-early', 's-early'))
        self.assertEqual(json.loads((self.ws.private / 'owner.json').read_text())['session_id'], 's-early')
        self.assertEqual(json.loads(self.ws.turn_file('1.init.json').read_text())['session_id'], 's-early')
        out = self.ws.wait()
        self.assertEqual((out['state'], out['session_id']), ('COMPLETE', 's-early'))
        self.assertEqual(self.ws.record()['session']['id'], 's-early')
        # A later turn naming a different id is still a mismatch at settlement, never adopted mid-turn.
        self.ws.send('y\n', env=dict(FAKE_CLAUDE_SLEEP='1.5', FAKE_CLAUDE_SESSION='s-other'))
        deadline = time.monotonic() + 5
        while not self.ws.turn_file('2.init.json').exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.ws.ok('session-status')['state'], 'RUNNING')
        self.assertEqual(self.ws.record()['session']['id'], 's-early')
        out = self.ws.wait()
        self.assertEqual((out['state'], out['reason']), ('INTERRUPTED', 'session id mismatch'))
        self.assertEqual(self.ws.record()['session']['id'], 's-early')

    def test_relay_exit_terminates_claude(self):
        pidfile = self.ws.path.parent / f'fakepid-{self.ws.path.name}'
        self.addCleanup(lambda: pidfile.unlink(missing_ok=True))
        self.ws.start('ready', 'slow\n', env=dict(FAKE_CLAUDE_SLEEP='30', FAKE_CLAUDE_PIDFILE=str(pidfile)))
        deadline = time.monotonic() + 5
        while not (pidfile.exists() and self.ws.turn_file('1.relay.json').exists()) and time.monotonic() < deadline:
            time.sleep(0.05)
        fake_pid = int(pidfile.read_text())
        relay_pid = json.loads(self.ws.turn_file('1.relay.json').read_text())['pid']
        self.assertTrue(pid_alive(fake_pid) and pid_alive(relay_pid))
        os.kill(relay_pid, 15)
        deadline = time.monotonic() + 5
        while pid_alive(fake_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(pid_alive(fake_pid), 'claude must not outlive the relay')
        out = self.ws.wait()
        self.assertEqual((out['state'], out['reason']), ('INTERRUPTED', 'result file missing'))
        self.assertNotEqual(out['exit_code'], 0)
        self.assertTrue(self.ws.turn_file('1.exit').is_file())

    def test_session_command_rewrites_a_stale_owner(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_SESSION='s-own'))
        self.ws.wait()
        (self.ws.private / 'owner.json').write_text(json.dumps(dict(pid=2 ** 22 + 7, session_id='s-own', started='x')))
        self.ws.ok('session-status')
        owner = json.loads((self.ws.private / 'owner.json').read_text())
        self.assertEqual((owner['pid'], owner['session_id']), (self.ws.owner, 's-own'))
        self.ws.blocked('session-answer', '--answers', self.ws.file('{}', '.json'))


if __name__ == '__main__':
    unittest.main()
