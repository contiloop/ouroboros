"""Claude Code adapter: drives the headless `claude` CLI (print mode, stream-json in and out) as the L2 host session.

Each turn is a detached process group started through `/bin/sh` so its exit code survives the short-lived
CLI that launched it. The shell runs `ouroboros/relay.py`, which owns the `claude` child: it feeds the
message, mirrors the event stream to `<n>.stream.jsonl`, relays the question tool through `<n>.q<k>.json` /
`<n>.a<k>.json`, allows every other permission request at once (`<n>.auto.json`) and writes the final
result to `<n>.json`. stderr → `<n>.err`, exit code → `<n>.exit`. Tool access is an allow-list
(`--allowedTools`); the host's own deny rules still apply, and no bypass of the permission system is
ever requested.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from ..ports import Turn

EXECUTABLE = 'claude'
RELAY = Path(__file__).resolve().parent.parent / 'relay.py'
# Tunable defaults. The allow-list is one comma-separated argument: the built-in tools plus every MCP tool.
# `AskUserQuestion` must never be listed here: an allow-listed tool runs without a permission request, so
# its questions would never reach the relay channel that hands them to L1.
ALLOWED_TOOLS = 'Bash,Edit,Write,Read,Glob,Grep,Agent,WebFetch,WebSearch,NotebookEdit,Skill,TodoWrite,mcp__*'
QUESTION_TOOL = 'AskUserQuestion'   # the relay keeps its own literal: it must stay import-free
assert QUESTION_TOOL not in ALLOWED_TOOLS.split(','), 'the question tool must never be allow-listed'
MAX_TURNS = 200
MODEL: str | None = None
STOP_GRACE = 5.0           # seconds between SIGTERM and SIGKILL in terminate()
DOCTOR_TIMEOUT = 20.0      # seconds allowed for `claude --version` / `claude plugin list`
RESULT_KEYS = ('session_id', 'text', 'num_turns', 'cost_usd', 'cost_total_usd', 'permission_denials', 'is_error', 'subtype', 'usage',
               'skills', 'auto_allowed', 'questions', 'stream_path')
USAGE_KEYS = ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens', 'output_tokens')
SKILL_PREFIX = 'dryforge:'


def command_line(session_id: str | None, *, allowed_tools: str = ALLOWED_TOOLS, max_turns: int = MAX_TURNS,
                 model: str | None = MODEL, executable: str = EXECUTABLE) -> list:
    """The exact argv of one turn. There is no prompt argument: the relay sends the user message on stdin as
    the first stream-json line, and `--permission-prompt-tool stdio` routes tool requests to the same channel."""
    argv = [executable, '-p', '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose',
            '--permission-prompt-tool', 'stdio']
    if session_id is not None:
        argv += ['--resume', session_id]
    argv += ['--allowedTools', allowed_tools, '--max-turns', str(max_turns)]
    if model is not None:
        argv += ['--model', model]
    return argv


def side_paths(raw_path: Path) -> tuple[Path, Path]:
    """(stderr file, exit-code file) of a turn whose result goes to `raw_path`."""
    return raw_path.with_suffix('.err'), raw_path.with_suffix('.exit')


def aux_path(raw_path: Path, suffix: str) -> Path:
    """`turns/<n>.<suffix>` beside the result file `turns/<n>.json`."""
    return raw_path.with_name(f'{raw_path.stem}.{suffix}')


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, obj) -> None:
    tmp = path.with_name(path.name + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _bundles(raw_path: Path) -> list:
    """Every question bundle of the turn in order: (round, bundle dict, answered?)."""
    out = []
    k = 1
    while True:
        q_path = aux_path(raw_path, f'q{k}.json')
        if not q_path.exists():
            return out
        bundle = _read_json(q_path)
        out.append((k, bundle if isinstance(bundle, dict) else None, aux_path(raw_path, f'a{k}.json').exists()))
        k += 1


def _exit_code(raw_path: Path) -> int | None:
    _, exit_path = side_paths(raw_path)
    try:
        return int(exit_path.read_text().strip())
    except (OSError, ValueError):
        return None


def wire_answers(answers: dict) -> dict:
    """Claude's wire form of structured answers (question → string): a label as is, a list of labels joined
    with ", ", {"other": text} as its text. The caller has validated the structure."""
    wire = {}
    for text, value in answers.items():
        if isinstance(value, list):
            wire[text] = ', '.join(value)
        elif isinstance(value, dict):
            wire[text] = value['other']
        else:
            wire[text] = value
    return wire


def parse_usage(data) -> dict:
    """The token counts of a result's `usage` block; a missing or non-numeric count is null."""
    usage = data if isinstance(data, dict) else {}
    return {k: (usage[k] if isinstance(usage.get(k), (int, float)) and not isinstance(usage.get(k), bool) else None)
            for k in USAGE_KEYS}


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
        argv = command_line(session_id, allowed_tools=self.allowed_tools, max_turns=self.max_turns,
                            model=self.model, executable=exe)
        err_path, exit_path = side_paths(raw_path)
        for p in raw_path.parent.glob(f'{raw_path.stem}.*'):
            p.unlink(missing_ok=True)  # the result, .err, .exit and every relay file of a reused turn number
        msg_path = aux_path(raw_path, 'msg')
        fd = os.open(msg_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(message)
        # `"$@"` carries the claude argv untouched to the relay; the wrapper only collects stderr and records
        # the exit code. The relay is the only writer of `<n>.json`; its stdout is not redirected anywhere.
        # The umask keeps every file created under turns/ private (0600) like the rest of the record.
        relay = [sys.executable, '-B', str(RELAY), '--turn', raw_path.stem, '--dir', str(raw_path.parent),
                 '--message', str(msg_path), '--']
        script = (f'umask 077; {" ".join(shlex.quote(a) for a in relay)} "$@" 2>>{shlex.quote(str(err_path))}; '
                  f'echo $? >{shlex.quote(str(exit_path))}')
        # The detached group is intentionally never reaped here: the CLI exits long before the turn ends and
        # `.exit` is the end-of-turn signal (hence the ResourceWarning about a running child in tests).
        proc = subprocess.Popen(['/bin/sh', '-c', script, 'sh', *argv], cwd=str(workspace),
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
        """False once the wrapper has written the exit file (the authoritative end of a turn). Without it, the turn
        is alive while the wrapper pid or any other member of its process group exists: after a group SIGTERM
        the `/bin/sh` wrapper dies at once (no `.exit`) while the relay is still taking `claude` down, and a
        turn reported dead in that window would let a second `claude --resume` start concurrently."""
        _, exit_path = side_paths(turn.raw_path)
        if exit_path.exists():
            return False
        try:
            os.waitpid(turn.pid, os.WNOHANG)  # reaps the wrapper if it happens to be our child
        except ChildProcessError:
            pass
        for probe in (os.kill, os.killpg):  # the wrapper pid, then its whole group (same id: it leads the group)
            try:
                probe(turn.pid, 0)
            except ProcessLookupError:
                continue
            except PermissionError:
                return True
            return True
        return False

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

    # ── questions (the relay channel) ───────────────────────────────────
    def questions(self, turn: Turn) -> dict | None:
        """The open question bundle {round, questions, request_id} (its `q<k>` file has no `a<k>`), else None."""
        for k, bundle, answered in _bundles(turn.raw_path):
            if not answered and bundle is not None:
                return dict(round=k, questions=bundle.get('questions') or [], request_id=bundle.get('request_id'),
                            tool_use_id=bundle.get('tool_use_id'))
        return None

    def answer(self, turn: Turn, round_: int, answers: dict) -> None:
        """Encode the validated answers of bundle `round_` into Claude's wire form and hand them to the relay."""
        _write_json(aux_path(turn.raw_path, f'a{round_}.json'), dict(round=round_, answers=wire_answers(answers)))

    def session_id(self, turn: Turn) -> str | None:
        """The session id of the turn's init event as soon as the relay has recorded it, else None."""
        init = _read_json(aux_path(turn.raw_path, 'init.json'))
        sid = init.get('session_id') if isinstance(init, dict) else None
        return sid if isinstance(sid, str) and sid else None

    # ── result ───────────────────────────────────────────────────────────
    def result(self, turn: Turn) -> dict:
        err_path, _ = side_paths(turn.raw_path)
        init = _read_json(aux_path(turn.raw_path, 'init.json'))
        commands = init.get('slash_commands') if isinstance(init, dict) else None
        auto = _read_json(aux_path(turn.raw_path, 'auto.json'))
        out = dict(state='INTERRUPTED', session_id=None, text=None, num_turns=None, cost_usd=0, cost_total_usd=0, permission_denials=[],
                   is_error=None, subtype=None, usage=parse_usage(None), raw_path=str(turn.raw_path),
                   stderr_path=str(err_path), exit_code=_exit_code(turn.raw_path), reason=None,
                   skills=[c for c in (commands if isinstance(commands, list) else []) if isinstance(c, str) and c.startswith(SKILL_PREFIX)],
                   auto_allowed=auto if isinstance(auto, list) else [],
                   questions=sum(1 for _, _, answered in _bundles(turn.raw_path) if answered),
                   stream_path=str(aux_path(turn.raw_path, 'stream.jsonl')))
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
        # `total_cost_usd` is the session's cumulative total; the caller charges this turn's delta as cost_usd.
        cost = data.get('total_cost_usd')
        cost = cost if isinstance(cost, (int, float)) and cost >= 0 else 0
        out.update(session_id=data.get('session_id'), text=data.get('result'), num_turns=data.get('num_turns'),
                   cost_usd=cost, cost_total_usd=cost,
                   permission_denials=data.get('permission_denials') or [], is_error=bool(data.get('is_error')),
                   subtype=data.get('subtype'), usage=parse_usage(data.get('usage')))
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
