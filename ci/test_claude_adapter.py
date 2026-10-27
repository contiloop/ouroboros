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
from test_run_record import Workspace  # noqa: E402
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
        if turn and turn.get('state') == 'RUNNING':
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
        self.assertEqual(argv[1:4], ['-p', '/dryforge:ready hello world\n', '--output-format'])
        self.assertEqual(argv[4], 'json')
        self.assertNotIn('--resume', argv)
        i = argv.index('--allowedTools')
        tools = argv[i + 1]
        self.assertEqual(tools, claude_adapter.ALLOWED_TOOLS)
        self.assertEqual(tools.split(','), ['Bash', 'Edit', 'Write', 'Read', 'Glob', 'Grep', 'Agent', 'WebFetch',
                                            'WebSearch', 'NotebookEdit', 'Skill', 'TodoWrite', 'mcp__*'])
        self.assertEqual(argv[argv.index('--max-turns') + 1], str(claude_adapter.MAX_TURNS))
        self.assertNotIn('--model', argv)
        for flag in BYPASS:
            self.assertFalse(any(flag in a for a in argv), argv)
        self.assertNotIn('--permission-mode', argv)
        logged = self.ws.logged()
        self.assertEqual(logged['cwd'], str(self.ws.path))
        self.assertEqual(logged['stdin'], '')
        self.assertTrue(logged['stdin_devnull'])

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
        self.assertEqual(argv[argv.index('-p') + 1], 'plain follow-up text\n')
        self.assertEqual(argv[argv.index('--resume') + 1], 's-abc')
        out = self.ws.start('go', 'now go\n', env=dict(FAKE_CLAUDE_SESSION='s-abc'))
        self.assertEqual((out['turn'], out['session_id']), (3, 's-abc'))
        self.ws.wait()
        argv = self.ws.argv()
        self.assertEqual(argv[argv.index('-p') + 1], '/dryforge:go now go\n')
        self.assertEqual(argv[argv.index('--resume') + 1], 's-abc')
        for a in argv:
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
        for key in ('state', 'session_id', 'text', 'num_turns', 'cost_usd', 'permission_denials', 'is_error',
                    'subtype', 'raw_path'):
            self.assertIn(key, out)
        self.assertEqual(out['state'], 'COMPLETE')
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
        ev = self.ws.events()[-1]
        self.assertEqual((ev['kind'], ev['actor']), ('turn_result', 'host'))
        self.assertNotIn('text', ev['data'])
        self.assertIn('text_path', ev['data'])

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
        self.ws.send('more\n', env=dict(FAKE_CLAUDE_COST='0.25'))
        self.ws.wait(); self.ws.wait()
        self.assertEqual(self.ws.record()['spent_usd'], 0.5)

    def test_session_id_mismatch_is_an_interrupted_turn(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_SESSION='s-1'))
        self.ws.wait()
        self.ws.send('y\n', env=dict(FAKE_CLAUDE_SESSION='s-2'))
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


class InterruptedTests(Base):
    def check_interrupted(self, out):
        self.assertEqual(out['state'], 'INTERRUPTED')
        self.assertEqual(self.ws.record()['turn']['state'], 'INTERRUPTED')
        kinds = self.ws.kinds()
        self.assertEqual(kinds[-2:], ['turn_result', 'interrupt'])
        ev = self.ws.events()[-1]
        self.assertEqual(ev['actor'], 'host')
        self.assertEqual(ev['cycle_id'], 'c1')

    def test_garbage_output(self):
        self.ws.start('ready', 'x\n', env=dict(FAKE_CLAUDE_MODE='garbage'))
        out = self.ws.wait()
        self.check_interrupted(out)
        self.assertIsNone(out['session_id'])
        self.assertTrue(out['stderr_path'].endswith('1.err'))
        self.assertIsNone(self.ws.record()['session']['id'])

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
        self.assertEqual((ev['kind'], ev['actor'], ev['data']['turn']), ('stop', 'human', 1))
        self.assertEqual(self.ws.ok('session-status')['state'], 'STOPPED')
        self.ws.blocked('session-stop')
        self.ws.start('ready', 'again\n')  # a stopped turn is not RUNNING
        self.ws.wait()


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
        for name in ('start', 'send', 'terminate', 'result', 'alive', 'doctor'):
            self.assertTrue(callable(getattr(ports.HostSession, name)), name)
            self.assertTrue(callable(getattr(adapter, name)), name)
        with self.assertRaises(ValueError):
            adapters.for_host('codex')

    def test_command_line_builder(self):
        argv = claude_adapter.command_line('/dryforge:ready hi', None)
        self.assertEqual(argv[:4], ['claude', '-p', '/dryforge:ready hi', '--output-format'])
        self.assertNotIn('--resume', argv)
        argv = claude_adapter.command_line('hi', 's-1', model='sonnet')
        self.assertEqual(argv[argv.index('--resume') + 1], 's-1')
        self.assertEqual(argv[argv.index('--model') + 1], 'sonnet')


if __name__ == '__main__':
    unittest.main()
