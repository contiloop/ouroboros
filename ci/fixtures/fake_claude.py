#!/usr/bin/env python3
"""Deterministic stand-in for the `claude` CLI used by ci/test_claude_adapter.py. Never a backend.

Modes (environment):
  FAKE_CLAUDE_LOG       file that receives {"argv", "cwd", "stdin", "stdin_devnull"} for every `-p` call
  FAKE_CLAUDE_SLEEP     seconds to sleep before answering a `-p` call
  FAKE_CLAUDE_MODE      ok (default) | garbage (non-JSON stdout, exit 0) | fail (JSON, exit 1)
                        | error (JSON with is_error true, exit 1) | nosession (JSON without session_id)
  FAKE_CLAUDE_SESSION   session id put in the JSON result (default sess-fake-1)
  FAKE_CLAUDE_COST      total_cost_usd put in the JSON result (default 0.125)
  FAKE_CLAUDE_DRYFORGE  enabled (default) | disabled | missing — shape of `plugin list`
"""
import json
import os
import sys
import time


def plugin_list() -> str:
    mode = os.environ.get('FAKE_CLAUDE_DRYFORGE', 'enabled')
    lines = ['Installed plugins:', '']
    lines += ['  other-tool@community', '    Version: 0.3.1', '    Scope: user', '    Status: ✔ enabled', '']
    if mode != 'missing':
        status = '✔ enabled' if mode == 'enabled' else '✘ disabled'
        lines += ['  dryforge@dryforge', '    Version: 1.4.0', '    Scope: user', f'    Status: {status}', '']
    return '\n'.join(lines) + '\n'


def print_mode(argv: list) -> int:
    log = os.environ.get('FAKE_CLAUDE_LOG')
    stdin_text = sys.stdin.read() if not sys.stdin.isatty() else '<tty>'
    devnull = False
    try:
        devnull = os.fstat(0).st_rdev == os.stat('/dev/null').st_rdev
    except OSError:
        pass
    if log:
        with open(log, 'w', encoding='utf-8') as f:
            json.dump(dict(argv=argv, cwd=os.getcwd(), stdin=stdin_text, stdin_devnull=devnull), f)
    sleep = float(os.environ.get('FAKE_CLAUDE_SLEEP', '0') or 0)
    if sleep:
        time.sleep(sleep)
    message = argv[argv.index('-p') + 1] if '-p' in argv and argv.index('-p') + 1 < len(argv) else ''
    mode = os.environ.get('FAKE_CLAUDE_MODE', 'ok')
    if mode == 'garbage':
        sys.stdout.write('not json at all\n')
        sys.stderr.write('fake claude: garbage mode\n')
        return 0
    result = dict(type='result', subtype='success', is_error=False, duration_ms=10, duration_api_ms=5,
                  num_turns=3, result='echo: ' + message, session_id=os.environ.get('FAKE_CLAUDE_SESSION', 'sess-fake-1'),
                  total_cost_usd=float(os.environ.get('FAKE_CLAUDE_COST', '0.125')),
                  usage=dict(input_tokens=10, output_tokens=5), permission_denials=[])
    code = 0
    if mode == 'error':
        result.update(is_error=True, subtype='error_during_execution', result='something broke')
        code = 1
    elif mode == 'fail':
        code = 1
    elif mode == 'nosession':
        del result['session_id']
    sys.stdout.write(json.dumps(result) + '\n')
    return code


def main(argv: list) -> int:
    if argv[1:2] == ['--version']:
        print('2.1.0 (Claude Code)')
        return 0
    if argv[1:3] == ['plugin', 'list']:
        sys.stdout.write(plugin_list())
        return 0
    if '-p' in argv:
        return print_mode(argv)
    sys.stderr.write('fake claude: unsupported invocation\n')
    return 64


if __name__ == '__main__':
    sys.exit(main(sys.argv))
