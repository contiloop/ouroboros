"""Scoped L1 tool approvals; not authentication or a sandbox for hostile project code.

Only the human grants/revokes a policy. L1 still decides each exact request. Shell
composition, unknown actions and unverifiable paths fail closed to human review.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess

OPERATIONS = {'git_add', 'git_commit', 'workspace_edit', 'verify'}
PROTECTED = {'.git', '.dryforge', '.claude', '.codex', '.agents'}
SHELLS = {'sh', 'bash', 'zsh', '/bin/sh', '/bin/bash', '/bin/zsh', '/usr/bin/bash', '/usr/bin/zsh'}
GIT = {'git', '/usr/bin/git', '/bin/git'}


class PolicyError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PolicyError(message)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def nonempty(value):
    return isinstance(value, str) and bool(value.strip()) and not any(ord(c) < 32 for c in value)


def relative_scope(value):
    require(nonempty(value), 'scope must be a nonempty relative path')
    p = PurePosixPath(value)
    require(not p.is_absolute() and '..' not in p.parts and
            not any(c in value for c in '*?[]{}:~\\') and
            not any(x in PROTECTED for x in p.parts), 'invalid/protected scope')
    return p


def validate_policy(policy):
    require(isinstance(policy, dict) and set(policy) == {
        'version', 'operations', 'paths', 'verification_commands', 'trust_workspace_code'},
        'runtime policy has missing or unknown fields')
    require(type(policy['version']) is int and policy['version'] == 1, 'unsupported runtime policy')
    ops, paths, commands = policy['operations'], policy['paths'], policy['verification_commands']
    require(isinstance(ops, list) and bool(ops) and all(isinstance(x, str) for x in ops)
            and len(set(ops)) == len(ops) and set(ops) <= OPERATIONS, 'invalid delegated operations')
    require(isinstance(paths, list) and bool(paths) and len(paths) <= 128, 'paths are required')
    for p in paths:
        relative_scope(p)
    require(len(set(paths)) == len(paths), 'duplicate paths')
    require(type(policy['trust_workspace_code']) is bool, 'project-code trust must be explicit')
    if set(ops) & {'git_add', 'git_commit', 'verify'}:
        require(policy['trust_workspace_code'], 'Git filters/hooks and verification may execute project code; explicit trust required')
    require(isinstance(commands, list) and len(commands) <= 64, 'verification_commands must be a bounded list')
    require(('verify' in ops) == bool(commands), 'verify needs explicit commands, and commands need verify')
    for argv in commands:
        require(isinstance(argv, list) and bool(argv) and all(nonempty(x) for x in argv), 'verification command must be argv')
        # Exact, recognized verification entrypoints only; this is NOT a proof of their effects.
        exe = Path(argv[0]).name
        valid = ((exe in ('python', 'python3', 'python3.11', 'python3.12', 'python3.13')
                  and argv[1:3] in (['-m', 'unittest'], ['-m', 'pytest'], ['-m', 'compileall']))
                 or exe in ('pytest', 'pytest-3')
                 or (exe in ('npm', 'pnpm', 'yarn') and len(argv) >= 2 and argv[1] == 'test'))
        require(valid, 'only explicit verification entrypoints can be delegated')
        require(all(not any(c in x for c in '$`\n\r;|&<>') for x in argv), 'compound verification command')
    return policy


def scoped_path(value, workspace, scopes):
    require(nonempty(value) and not value.startswith('-') and
            not any(c in value for c in '*?[]{}:~\\'), 'path must be literal, not an option/pathspec')
    raw = Path(value)
    require('..' not in raw.parts, 'parent traversal is not delegated')
    root = Path(workspace).resolve(strict=True)
    target = raw if raw.is_absolute() else root / raw
    require(target.is_relative_to(root), 'path is outside the approved workspace')
    relative = target.relative_to(root)
    require(relative.parts and not any(x in PROTECTED for x in relative.parts), 'runtime/security metadata is not delegated')
    for path in (target, *target.parents):
        if path == root:
            break
        require(not path.is_symlink(), 'symlink path requires human review')
        require(not (path != target and (path / '.git').exists()), 'nested repository requires human review')
    require(target.resolve().is_relative_to(root), 'resolved path escapes workspace')
    allowed = [PurePosixPath(x) for x in scopes]
    rel = PurePosixPath(relative.as_posix())
    require(any(rel == s or rel.is_relative_to(s) for s in allowed), 'path is outside delegated paths')
    return relative.as_posix()


def command_argv(command):
    require(isinstance(command, str) and command.strip(), 'host command is missing')
    try:
        outer = shlex.split(command)
    except ValueError as exc:
        raise PolicyError('malformed shell command') from exc
    if outer and outer[0] in SHELLS:
        require(len(outer) == 3 and outer[1] in ('-c', '-lc'), 'unsupported shell wrapper')
        command = outer[2]
    # Reject even quoted metacharacters rather than guess about shell semantics.
    require(not any(c in command for c in '$`;|&<>\n\r\x00'), 'compound/expanding shell input requires human review')
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise PolicyError('malformed command') from exc
    require(bool(argv) and argv[0] not in SHELLS, 'nested shell not delegated')
    return argv


def git_read(workspace, *args):
    # Fixed read-only invocations only; never execute the submitted shell command.
    try:
        import os
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        env['GIT_OPTIONAL_LOCKS'] = '0'
        run = subprocess.run(['git', '--no-pager', '-C', str(workspace), *args],
                             capture_output=True, timeout=10, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PolicyError('could not inspect Git state') from exc
    require(run.returncode == 0, 'Git state could not be verified')
    return run.stdout


def classify(payload, workspace, policy):
    """Return operation + observable scope, or refuse. Does not execute any request."""
    validate_policy(policy)
    root = Path(workspace).resolve(strict=True)
    require(isinstance(payload, dict), 'malformed host request')
    method = payload.get('method')
    cwd, command, changes = None, None, None
    if method == 'item/commandExecution/requestApproval':
        p = payload.get('params', {})
        require(isinstance(p, dict), 'malformed Codex request')
        require(not p.get('networkApprovalContext') and not p.get('additionalPermissions'),
                'network/permission expansion is not delegated')
        command, cwd = p.get('command'), p.get('cwd')
    elif method == 'item/fileChange/requestApproval':
        p = payload.get('params', {})
        require(not p.get('grantRoot') and not p.get('additionalPermissions'), 'permission expansion not delegated')
        # Only a read-back from the matching host turn/item is accepted, not model prose.
        changes = payload.get('observed_changes')
        require(isinstance(changes, list) and bool(changes), 'host file-change paths were not observed')
    elif method is not None:
        raise PolicyError('this host operation requires a human')
    elif payload.get('tool') == 'Bash':
        command = payload.get('input', {}).get('command')
        # Claude Bash has no trusted cwd in this callback. Require explicit git -C.
    elif payload.get('tool') in ('Write', 'Edit', 'MultiEdit'):
        inputs = payload.get('input', {})
        require(isinstance(inputs, dict), 'malformed file tool input')
        path = inputs.get('file_path')
        require(isinstance(path, str) and Path(path).is_absolute(), 'file tool needs absolute path')
        changes = [{'path': path, 'kind': {'type': 'update'}}]
    else:
        raise PolicyError('tool is outside delegated operations')

    if changes is not None:
        paths = []
        for change in changes:
            require(isinstance(change, dict), 'unknown file change shape')
            kind = change.get('kind')
            require(isinstance(kind, dict) and kind.get('type') in ('add', 'update') and
                    not kind.get('move_path') and not kind.get('movePath'), 'deletion/move is not delegated')
            path = change.get('path')
            require(isinstance(path, str) and Path(path).is_absolute(), 'host file path must be absolute')
            paths.append(scoped_path(path, root, policy['paths']))
        require('workspace_edit' in policy['operations'], 'workspace edits not delegated')
        return {'operation': 'workspace_edit', 'paths': paths}

    argv = command_argv(command)
    is_git = argv[0] in GIT
    if is_git and argv[1:2] == ['-C']:
        require(len(argv) >= 4 and Path(argv[2]).is_absolute() and Path(argv[2]).resolve() == root,
                'Git -C targets another workspace')
        argv = [argv[0], *argv[3:]]
        cwd = str(root)
    require(isinstance(cwd, str) and Path(cwd).is_absolute() and Path(cwd).resolve() == root,
            'command needs an observed or explicit workspace-root cwd')
    require(not Path(cwd).is_symlink(), 'symlink cwd is not delegated')
    if is_git:
        require((root / '.git').is_dir() and not (root / '.git').is_symlink(),
                'linked worktrees/alternate Git metadata need a separate human decision')
        require(not (root / '.git' / 'commondir').exists(), 'shared Git directory requires human review')
        require(git_read(root, 'rev-parse', '--show-toplevel').decode().strip() == str(root), 'Git root mismatch')
        if argv[1:2] == ['add']:
            paths = argv[2:]
            if paths[:1] == ['--']:
                paths = paths[1:]
            require(bool(paths), 'git add needs explicit paths')
            # Explicit files, not directory-wide staging; avoid hidden .git/.dryforge descendants.
            resolved = [scoped_path(p, root, policy['paths']) for p in paths]
            require(all((root / p).is_file() for p in resolved), 'git add delegation is for existing explicit files only')
            operation = 'git_add'
        elif len(argv) == 4 and argv[1:3] == ['commit', '-m'] and nonempty(argv[3]):
            raw = git_read(root, 'diff', '--cached', '--name-status', '-z', '--no-renames', '--no-ext-diff')
            parts = raw.split(b'\0'); resolved = []
            for i in range(0, len(parts) - 1, 2):
                require(i + 1 < len(parts) - 1 and parts[i] in (b'A', b'M'), 'staged deletion/type change is not delegated')
                resolved.append(scoped_path(parts[i+1].decode('utf-8'), root, policy['paths']))
            require(bool(resolved), 'no verified staged changes')
            operation = 'git_commit'
        else:
            raise PolicyError('Git operation/options are not delegated')
        require(operation in policy['operations'], f'{operation} is not delegated')
        return {'operation': operation, 'paths': resolved,
                'index_digest': hashlib.sha256((root / '.git' / 'index').read_bytes()).hexdigest()
                if operation == 'git_commit' else None}

    require('verify' in policy['operations'] and argv in policy['verification_commands'],
            'command is not an exact approved verification argv')
    return {'operation': 'verify', 'argv': argv, 'cwd': str(root)}
