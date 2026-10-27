#!/usr/bin/env python3
"""Relay between one detached turn and a `claude` stream-json session. Standard library only, run by path.

    relay.py --turn N --dir TURNS_DIR --message MSG_FILE -- <claude argv...>

The relay spawns `claude` as its child (stdin and stdout piped, stderr inherited), sends the message file's
text as the first user line, mirrors every stdout line verbatim to `N.stream.jsonl`, and reacts to events:
  system/init          → `N.init.json` {session_id, slash_commands, tools}
  control_request      → AskUserQuestion: `N.q<k>.json` is written and the relay waits (no time limit, no
                         tokens) for `N.a<k>.json`, then forwards its `answers` in the allow response;
                         any other tool: allowed at once and appended to `N.auto.json`
  result               → written to `N.json` (the old JSON output shape); claude's stdin is closed
The relay exits with claude's exit code (1 when claude ends without a result event). If the relay ends for
any other reason (signal, exception) it terminates its child first. Every file it creates is 0600.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time

ANSWER_POLL = 0.2      # seconds between checks for the answer file
KILL_GRACE = 2.0       # seconds between SIGTERM and SIGKILL when the relay takes claude down


class Interrupted(Exception):
    """Raised inside the signal handler so a blocking read unwinds to the cleanup."""


def write_json(path: str, obj) -> None:
    tmp = path + '.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def read_json(path: str):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def stdin_is_devnull() -> bool:
    try:
        return os.fstat(0).st_rdev == os.stat('/dev/null').st_rdev
    except OSError:
        return False


def send(proc: subprocess.Popen, obj) -> None:
    try:
        proc.stdin.write((json.dumps(obj, ensure_ascii=False) + '\n').encode('utf-8'))
        proc.stdin.flush()
    except (BrokenPipeError, OSError, ValueError):
        pass  # claude is gone; the stream loop sees EOF next


def close_stdin(proc: subprocess.Popen) -> None:
    try:
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
    except OSError:
        pass


def respond(proc: subprocess.Popen, request_id, updated_input) -> None:
    send(proc, dict(type='control_response',
                    response=dict(subtype='success', request_id=request_id,
                                  response=dict(behavior='allow', updatedInput=updated_input))))


def wait_for_answer(proc: subprocess.Popen, path: str) -> dict | None:
    """Poll for the answer file; None once claude has exited without one."""
    while True:
        if os.path.exists(path):
            try:
                data = read_json(path)
            except ValueError:
                data = None  # written half-way; look again
            if isinstance(data, dict) and isinstance(data.get('answers'), dict):
                return data['answers']
        if proc.poll() is not None:
            return None
        time.sleep(ANSWER_POLL)


def take_down(proc: subprocess.Popen | None) -> None:
    """Stop the child. Only claude's own pid is signalled, not the group: claude shares the wrapper's process
    group, and a group kill would take the `/bin/sh` wrapper with it and lose the `.exit` file. `session-stop`
    is the one that kills the whole group."""
    if proc is None or proc.poll() is not None:
        return
    for sig, grace in ((signal.SIGTERM, KILL_GRACE), (signal.SIGKILL, 1.0)):
        try:
            proc.send_signal(sig)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + grace
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if proc.poll() is not None:
            return


def parse_args(argv: list) -> tuple[dict, list]:
    try:
        split = argv.index('--')
    except ValueError:
        raise SystemExit('relay: missing `--` before the claude argv')
    opts, i = {}, 0
    head = argv[:split]
    while i < len(head):
        if head[i] in ('--turn', '--dir', '--message') and i + 1 < len(head):
            opts[head[i][2:]] = head[i + 1]
            i += 2
        else:
            raise SystemExit(f'relay: unexpected argument {head[i]!r}')
    missing = [k for k in ('turn', 'dir', 'message') if k not in opts]
    if missing or not argv[split + 1:]:
        raise SystemExit('relay: usage: --turn N --dir DIR --message FILE -- <claude argv>')
    return opts, argv[split + 1:]


def run(opts: dict, claude_argv: list) -> int:
    turn, turns_dir = opts['turn'], opts['dir']

    def path(suffix: str) -> str:
        return os.path.join(turns_dir, f'{turn}.{suffix}')

    write_json(path('relay.json'), dict(stdin_devnull=stdin_is_devnull(), pid=os.getpid()))
    with open(opts['message'], encoding='utf-8') as f:
        message = f.read()
    stream_fd = os.open(path('stream.jsonl'), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    stream = os.fdopen(stream_fd, 'ab')

    def on_signal(signum, frame):
        raise Interrupted(signum)

    # Handlers go in before the child exists so a signal in the gap cannot orphan it.
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, on_signal)

    proc: subprocess.Popen | None = None
    result = None
    rounds = 0
    auto: list = []
    try:
        proc = subprocess.Popen(claude_argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
                                start_new_session=False, close_fds=True)
        send(proc, dict(type='user', message=dict(role='user', content=message)))
        for raw in proc.stdout:
            stream.write(raw if raw.endswith(b'\n') else raw + b'\n')
            stream.flush()
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            kind = event.get('type')
            if kind == 'system' and event.get('subtype') == 'init':
                write_json(path('init.json'), dict(session_id=event.get('session_id'),
                                                   slash_commands=event.get('slash_commands') or [],
                                                   tools=event.get('tools') or []))
            elif kind == 'control_request':
                request = event.get('request') or {}
                if request.get('subtype') != 'can_use_tool':
                    continue
                request_id = event.get('request_id')
                tool_input = request.get('input') if isinstance(request.get('input'), dict) else {}
                if request.get('tool_name') == 'AskUserQuestion':
                    rounds += 1
                    write_json(path(f'q{rounds}.json'), dict(round=rounds, request_id=request_id,
                                                              tool_use_id=request.get('tool_use_id'),
                                                              questions=tool_input.get('questions') or []))
                    answers = wait_for_answer(proc, path(f'a{rounds}.json'))
                    if answers is None:
                        continue  # claude exited while waiting; drain the stream and finish
                    respond(proc, request_id, dict(tool_input, answers=answers))
                else:
                    auto.append(dict(tool_name=request.get('tool_name'), tool_use_id=request.get('tool_use_id')))
                    write_json(path('auto.json'), auto)
                    respond(proc, request_id, tool_input)
            elif kind == 'result':
                result = event
                write_json(path('json'), event)
                close_stdin(proc)  # the turn is over; keep draining the stream until claude exits
        close_stdin(proc)
        code = proc.wait()
        return code if result is not None else (code or 1)
    except Interrupted as exc:
        take_down(proc)
        return 128 + int(exc.args[0])
    except BaseException:
        take_down(proc)
        raise
    finally:
        take_down(proc)
        stream.close()


def main(argv: list) -> int:
    opts, claude_argv = parse_args(argv)
    return run(opts, claude_argv)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
