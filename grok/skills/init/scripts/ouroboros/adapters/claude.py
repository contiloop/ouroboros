"""Claude Code adapter: drives the headless `claude` CLI (print mode, JSON output) as the L2 host session.

Each turn is a detached process group started through `/bin/sh` so its exit code survives the short-lived
CLI that launched it: stdout → `<n>.json`, stderr → `<n>.err`, exit code → `<n>.exit` next to it. Tool
access is an allow-list (`--allowedTools`); the host's own deny rules still apply, and no bypass of the
permission system is ever requested.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import time
from pathlib import Path

from ..ports import Turn

EXECUTABLE = 'claude'
# Tunable defaults. The allow-list is one comma-separated argument: the built-in tools plus every MCP tool.
ALLOWED_TOOLS = 'Bash,Edit,Write,Read,Glob,Grep,Agent,WebFetch,WebSearch,NotebookEdit,Skill,TodoWrite,mcp__*'
MAX_TURNS = 200
MODEL: str | None = None
STOP_GRACE = 5.0           # seconds between SIGTERM and SIGKILL in terminate()
DOCTOR_TIMEOUT = 20.0      # seconds allowed for `claude --version` / `claude plugin list`
RESULT_KEYS = ('session_id', 'text', 'num_turns', 'cost_usd', 'permission_denials', 'is_error', 'subtype')


def command_line(message: str, session_id: str | None, *, allowed_tools: str = ALLOWED_TOOLS,
                 max_turns: int = MAX_TURNS, model: str | None = MODEL, executable: str = EXECUTABLE) -> list:
    """The exact argv of one turn. `message` is the user message verbatim; nothing is added to it."""
    argv = [executable, '-p', message, '--output-format', 'json']
    if session_id is not None:
        argv += ['--resume', session_id]
    argv += ['--allowedTools', allowed_tools, '--max-turns', str(max_turns)]
    if model is not None:
        argv += ['--model', model]
    return argv


def side_paths(raw_path: Path) -> tuple[Path, Path]:
    """(stderr file, exit-code file) of a turn whose stdout goes to `raw_path`."""
    return raw_path.with_suffix('.err'), raw_path.with_suffix('.exit')


def _exit_code(raw_path: Path) -> int | None:
    _, exit_path = side_paths(raw_path)
    try:
        return int(exit_path.read_text().strip())
    except (OSError, ValueError):
        return None


class ClaudeAdapter:
    def __init__(self, allowed_tools: str = ALLOWED_TOOLS, max_turns: int = MAX_TURNS, model: str | None = MODEL,
                 stop_grace: float = STOP_GRACE):
        self.allowed_tools = allowed_tools
        self.max_turns = max_turns
        self.model = model
        self.stop_grace = stop_grace

    # ── launch ───────────────────────────────────────────────────────────
    def executable(self) -> str | None:
        return shutil.which(EXECUTABLE)

    def _launch(self, workspace: Path, message: str, session_id: str | None, raw_path: Path) -> Turn:
        exe = self.executable()
        if exe is None:
            raise FileNotFoundError(f'{EXECUTABLE} is not on PATH')
        argv = command_line(message, session_id, allowed_tools=self.allowed_tools, max_turns=self.max_turns,
                            model=self.model, executable=exe)
        err_path, exit_path = side_paths(raw_path)
        for p in (raw_path, err_path, exit_path):
            p.unlink(missing_ok=True)
        # `"$@"` carries the argv untouched; the wrapper only redirects and records the exit code.
        script = (f'{shlex.quote(exe)} "$@" >{shlex.quote(str(raw_path))} 2>{shlex.quote(str(err_path))}; '
                  f'echo $? >{shlex.quote(str(exit_path))}')
        proc = subprocess.Popen(['/bin/sh', '-c', script, 'sh', *argv[1:]], cwd=str(workspace),
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True, close_fds=True)
        return Turn(pid=proc.pid, raw_path=raw_path)

    def start(self, workspace: Path, message: str, raw_path: Path) -> Turn:
        return self._launch(workspace, message, None, raw_path)

    def send(self, workspace: Path, session_id: str, message: str, raw_path: Path) -> Turn:
        if not session_id:
            raise ValueError('send requires a session id')
        return self._launch(workspace, message, session_id, raw_path)

    # ── liveness and termination ─────────────────────────────────────────
    def alive(self, turn: Turn) -> bool:
        try:
            pid, _ = os.waitpid(turn.pid, os.WNOHANG)  # reaps the wrapper if it happens to be our child
            if pid == turn.pid:
                return False
        except ChildProcessError:
            pass
        try:
            os.kill(turn.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def terminate(self, turn: Turn) -> None:
        for sig, grace in ((signal.SIGTERM, self.stop_grace), (signal.SIGKILL, 1.0)):
            if not self.alive(turn):
                return
            try:
                os.killpg(turn.pid, sig)
            except ProcessLookupError:
                return
            deadline = time.monotonic() + grace
            while self.alive(turn) and time.monotonic() < deadline:
                time.sleep(0.05)

    # ── result ───────────────────────────────────────────────────────────
    def result(self, turn: Turn) -> dict:
        err_path, _ = side_paths(turn.raw_path)
        out = dict(state='INTERRUPTED', session_id=None, text=None, num_turns=None, cost_usd=0, permission_denials=[],
                   is_error=None, subtype=None, raw_path=str(turn.raw_path), stderr_path=str(err_path),
                   exit_code=_exit_code(turn.raw_path), reason=None)
        try:
            raw = turn.raw_path.read_text(encoding='utf-8')
        except OSError:
            out['reason'] = 'result file missing'
            return out
        if not raw.strip():
            out['reason'] = 'result file empty'
            return out
        try:
            data = json.loads(raw)
        except ValueError:
            out['reason'] = 'result is not JSON'
            return out
        if not isinstance(data, dict):
            out['reason'] = 'result is not a JSON object'
            return out
        cost = data.get('total_cost_usd')
        out.update(session_id=data.get('session_id'), text=data.get('result'), num_turns=data.get('num_turns'),
                   cost_usd=cost if isinstance(cost, (int, float)) and cost >= 0 else 0,
                   permission_denials=data.get('permission_denials') or [], is_error=bool(data.get('is_error')),
                   subtype=data.get('subtype'))
        if not isinstance(out['session_id'], str) or not out['session_id']:
            out.update(session_id=None, reason='result has no session_id')
        elif out['is_error']:
            out['reason'] = f'host reported is_error ({out["subtype"]})'
        elif out['exit_code'] not in (0, None):
            out['reason'] = f'host exited with code {out["exit_code"]}'
        else:
            out.update(state='COMPLETE', reason=None)
        return out

    # ── prerequisites ────────────────────────────────────────────────────
    def doctor(self) -> dict:
        exe = self.executable()
        report = dict(host='claude', claude=exe, version=None, dryforge=dict(installed=False, enabled=False))
        if exe is None:
            return report
        version = _capture([exe, '--version'])
        report['version'] = version.strip() or None if version is not None else None
        listing = _capture([exe, 'plugin', 'list'])
        if listing is not None:
            report['dryforge'] = parse_plugin_list(listing)
        return report


def _capture(argv: list) -> str | None:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=DOCTOR_TIMEOUT, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def parse_plugin_list(text: str) -> dict:
    """`dryforge@…` entry followed by its `Status:` line (enabled unless it says disabled)."""
    installed = enabled = False
    in_entry = False
    for line in text.splitlines():
        stripped = line.strip()
        if 'dryforge@' in stripped:
            installed, in_entry = True, True
            continue
        if in_entry and '@' in stripped and not stripped.startswith(('Status', 'Version', 'Scope')):
            in_entry = False
        if in_entry and stripped.lower().startswith('status'):
            low = stripped.lower()
            enabled = 'enabled' in low and 'disabled' not in low
            in_entry = False
    return dict(installed=installed, enabled=enabled)
