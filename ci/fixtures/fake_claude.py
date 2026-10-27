#!/usr/bin/env python3
"""Deterministic stand-in for the `claude` CLI used by ci/test_claude_adapter.py. Never a backend.

With `--input-format stream-json` it speaks the stream protocol the relay expects: the user message is the first
stdin line, a `system/init` event opens the stream, question and permission requests are `control_request`
events answered through stdin, and a `result` event ends the turn.

Modes (environment):
  FAKE_CLAUDE_LOG         file that receives {"argv", "cwd", "stdin", "message", "model_flag", "effort_flag",
                          "subagent_model"} for every `-p` call (stdin = the first stdin line verbatim, message =
                          its user content, model_flag / effort_flag = the `--model` / `--effort` value or null,
                          subagent_model = CLAUDE_CODE_SUBAGENT_MODEL as seen by the process or null when absent)
  FAKE_CLAUDE_SLEEP       seconds to sleep after the init event, before answering
  FAKE_CLAUDE_MODE        ok (default) | garbage (non-JSON stdout, exit 0) | fail (result, exit 1)
                          | error (result with is_error true, exit 1) | nosession (no session_id anywhere)
  FAKE_CLAUDE_SESSION     session id put in the init and result events (default sess-fake-1)
  FAKE_CLAUDE_COST        total_cost_usd put in the result (default 0.125); like the real host this is the
                          session's cumulative total, so a later turn of one session reports a higher figure
  FAKE_CLAUDE_QUESTIONS   number of AskUserQuestion rounds to ask before the result (default 0)
  FAKE_CLAUDE_MULTI       1 → every question is multiSelect
  FAKE_CLAUDE_PERMISSION  1 → one `can_use_tool` request for Bash before the result
  FAKE_CLAUDE_PIDFILE     file that receives this process's pid (to assert it was terminated)
  FAKE_CLAUDE_DRYFORGE    enabled (default) | disabled | missing — shape of `plugin list`
"""
import json
import os
import sys
import time

SLASH_COMMANDS = ['dryforge:ready', 'dryforge:go', 'dryforge:migration', 'other:thing']
TOOLS = ['Bash', 'Edit', 'Read', 'AskUserQuestion']


def plugin_list() -> str:
    mode = os.environ.get('FAKE_CLAUDE_DRYFORGE', 'enabled')
    lines = ['Installed plugins:', '']
    lines += ['  other-tool@community', '    Version: 0.3.1', '    Scope: user', '    Status: ✔ enabled', '']
    if mode != 'missing':
        status = '✔ enabled' if mode == 'enabled' else '✘ disabled'
        lines += ['  dryforge@dryforge', '    Version: 1.4.0', '    Scope: user', f'    Status: {status}', '']
    return '\n'.join(lines) + '\n'


def emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event) + '\n')
    sys.stdout.flush()


def read_line() -> str | None:
    line = sys.stdin.readline()
    return line if line else None


def control(request_id: str, tool_name: str, tool_use_id: str, tool_input: dict) -> dict | None:
    """Emit one `can_use_tool` request and return the matching response's `updatedInput` (None on EOF)."""
    emit(dict(type='control_request', request_id=request_id,
              request=dict(subtype='can_use_tool', tool_name=tool_name, input=tool_input, tool_use_id=tool_use_id,
                           requires_user_interaction=tool_name == 'AskUserQuestion')))
    line = read_line()
    if line is None:
        return None
    response = json.loads(line)
    if response.get('type') != 'control_response' or response['response'].get('request_id') != request_id:
        sys.stderr.write(f'fake claude: unexpected control response {line!r}\n')
        return None
    inner = response['response'].get('response') or {}
    if inner.get('behavior') != 'allow':
        return None
    return inner.get('updatedInput') or {}


def result_event(message: str, answers: list) -> dict:
    text = 'echo: ' + message
    if answers:
        text += ' | answers: ' + ' / '.join(answers)
    event = dict(type='result', subtype='success', is_error=False, duration_ms=10, duration_api_ms=5, num_turns=3,
                 result=text, session_id=os.environ.get('FAKE_CLAUDE_SESSION', 'sess-fake-1'),
                 total_cost_usd=float(os.environ.get('FAKE_CLAUDE_COST', '0.125')),
                 usage=dict(input_tokens=10, cache_read_input_tokens=100, cache_creation_input_tokens=20,
                            output_tokens=5, server_tool_use=dict(web_search_requests=0)),
                 permission_denials=[])
    return event


def stream_mode(argv: list) -> int:
    pidfile = os.environ.get('FAKE_CLAUDE_PIDFILE')
    if pidfile:
        with open(pidfile, 'w', encoding='utf-8') as f:
            f.write(str(os.getpid()))
    first = read_line() or ''
    try:
        message = json.loads(first)['message']['content']
    except (ValueError, KeyError, TypeError):
        message = ''
    log = os.environ.get('FAKE_CLAUDE_LOG')
    if log:
        with open(log, 'w', encoding='utf-8') as f:
            model_flag = argv[argv.index('--model') + 1] if '--model' in argv else None
            effort_flag = argv[argv.index('--effort') + 1] if '--effort' in argv else None
            json.dump(dict(argv=argv, cwd=os.getcwd(), stdin=first, message=message, model_flag=model_flag,
                           effort_flag=effort_flag, subagent_model=os.environ.get('CLAUDE_CODE_SUBAGENT_MODEL')), f)
    mode = os.environ.get('FAKE_CLAUDE_MODE', 'ok')
    if mode == 'garbage':
        sys.stdout.write('not json at all\n')
        sys.stdout.flush()
        sys.stderr.write('fake claude: garbage mode\n')
        return 0
    init = dict(type='system', subtype='init', session_id=os.environ.get('FAKE_CLAUDE_SESSION', 'sess-fake-1'),
                tools=TOOLS, slash_commands=SLASH_COMMANDS, cwd=os.getcwd())
    if mode == 'nosession':
        del init['session_id']
    emit(init)
    sleep = float(os.environ.get('FAKE_CLAUDE_SLEEP', '0') or 0)
    if sleep:
        time.sleep(sleep)
    answers = []
    multi = os.environ.get('FAKE_CLAUDE_MULTI') == '1'
    for k in range(1, int(os.environ.get('FAKE_CLAUDE_QUESTIONS', '0') or 0) + 1):
        question = dict(question=f'Question {k}?', header='Choice',
                        options=[dict(label='Alpha', description='the first option'),
                                 dict(label='Beta', description='the second option')], multiSelect=multi)
        updated = control(f'req-{k}', 'AskUserQuestion', f'toolu-{k}', dict(questions=[question]))
        if updated is None:
            return 1
        answers.append(str((updated.get('answers') or {}).get(question['question'])))
    if os.environ.get('FAKE_CLAUDE_PERMISSION') == '1':
        if control('req-perm', 'Bash', 'toolu-perm', dict(command='ls')) is None:
            return 1
    result = result_event(message, answers)
    code = 0
    if mode == 'error':
        result.update(is_error=True, subtype='error_during_execution', result='something broke')
        code = 1
    elif mode == 'fail':
        code = 1
    elif mode == 'nosession':
        del result['session_id']
    emit(result)
    return code


def main(argv: list) -> int:
    if argv[1:2] == ['--version']:
        print('2.1.0 (Claude Code)')
        return 0
    if argv[1:3] == ['plugin', 'list']:
        sys.stdout.write(plugin_list())
        return 0
    if '-p' in argv and '--input-format' in argv and argv[argv.index('--input-format') + 1] == 'stream-json':
        return stream_mode(argv)
    sys.stderr.write('fake claude: unsupported invocation\n')
    return 64


if __name__ == '__main__':
    sys.exit(main(sys.argv))
