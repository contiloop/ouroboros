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

BASE_OPERATIONS = {'git_add', 'git_commit', 'workspace_edit', 'verify'}
GO_OPERATIONS = {'git_worktree_add', 'git_merge', 'git_worktree_remove', 'git_branch_delete'}
OPERATIONS = BASE_OPERATIONS | GO_OPERATIONS
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
    require(isinstance(policy, dict), 'runtime policy must be an object')
    version = policy.get('version')
    require(type(version) is int and version in (1, 2, 3), 'unsupported runtime policy')
    fields = {'version', 'operations', 'paths', 'verification_commands', 'trust_workspace_code'}
    if version >= 2:
        fields.add('go_worktrees')
    if version == 3:
        fields.add('go_workflow')
    require(set(policy) == fields, 'runtime policy has missing or unknown fields')
    if version >= 2:
        require(type(policy['go_worktrees']) is bool, 'go_worktrees must be an explicit boolean grant')
    ops, paths, commands = policy['operations'], policy['paths'], policy['verification_commands']
    require(isinstance(ops, list) and bool(ops) and all(isinstance(x, str) for x in ops)
            and len(set(ops)) == len(ops) and set(ops) <= (OPERATIONS if version == 3 else BASE_OPERATIONS), 'invalid delegated operations')
    require(isinstance(paths, list) and bool(paths) and len(paths) <= 128, 'paths are required')
    for p in paths:
        relative_scope(p)
    require(len(set(paths)) == len(paths), 'duplicate paths')
    require(type(policy['trust_workspace_code']) is bool, 'project-code trust must be explicit')
    if version >= 2 and policy['go_worktrees']:
        require(policy['trust_workspace_code'], 'worktree delegation requires explicit project-code trust')
        require(bool(set(ops) & OPERATIONS),
                'worktree delegation requires a scoped operation')
    if version == 3:
        from runtime_git import validate_workflow
        validate_workflow(policy)
    if set(ops) & ({'git_add', 'git_commit', 'verify'} | GO_OPERATIONS):
        require(policy['trust_workspace_code'], 'Git filters/hooks and verification may execute project code; explicit trust required')
    require(isinstance(commands, list) and len(commands) <= 64, 'verification_commands must be a bounded list')
    require(('verify' in ops) == bool(commands), 'verify needs explicit commands, and commands need verify')
    for argv in commands:
        require(isinstance(argv, list) and bool(argv) and all(nonempty(x) for x in argv), 'verification command must be argv')
        # Exact, recognized verification entrypoints only; this is NOT a proof of their effects.
        exe = Path(argv[0]).name
        module_args = argv[2:] if argv[1:2] == ['-B'] else argv[1:]
        valid = ((re.fullmatch(r'python(?:3(?:\.[0-9]+)?)?', exe)
                  and module_args[:2] in (['-m', 'unittest'], ['-m', 'pytest'], ['-m', 'compileall']))
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


def _git_path(root, name):
    """Read the effective Git metadata path, including linked worktree indexes."""
    reported = git_read(root, 'rev-parse', '--git-path', name).decode('utf-8').strip()
    require(bool(reported), 'Git metadata path is missing')
    path = Path(reported)
    return (path if path.is_absolute() else root / path).resolve()


def _known_worktree(base, wt, policy):
    """Recognize only a registered Go task worktree belonging to the approved Git root.

    Neither a matching directory name nor a user-supplied .git pointer alone is proof.
    This is an authorization guard within a trusted checkout, not a security sandbox.
    """
    require(policy['version'] >= 2 and policy['go_worktrees'],
            'linked worktree requires a human-approved policy v2 go_worktrees grant')
    pool = base / '.dryforge' / 'worktrees'
    require(wt.parent == pool and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', wt.name),
            'not a named direct child of the Go worktree pool')
    for p in (base / '.dryforge', pool, wt, wt / '.git', base / '.git', base / '.git' / 'worktrees'):
        require(not p.is_symlink(), 'symlinked worktree or Git metadata is not delegated')
    require(wt.is_dir() and (wt / '.git').is_file() and (base / '.git').is_dir(),
            'registered worktree or Git metadata missing')
    pointer = (wt / '.git').read_text(encoding='utf-8').splitlines()
    require(len(pointer) == 1 and pointer[0].startswith('gitdir: '), 'malformed linked .git pointer')
    raw_dir = Path(pointer[0][8:])
    git_dir = (raw_dir if raw_dir.is_absolute() else wt / raw_dir).resolve(strict=True)
    require(git_dir.parent == base / '.git' / 'worktrees' and git_dir.is_dir() and
            not git_dir.is_symlink(), 'worktree metadata is outside approved Git directory')
    back = Path((git_dir / 'gitdir').read_text(encoding='utf-8').strip())
    require((back if back.is_absolute() else git_dir / back).resolve() == wt / '.git',
            'Git metadata does not point back to this worktree')
    require(git_read(wt, 'rev-parse', '--show-toplevel').decode().strip() == str(wt),
            'Git reports a different worktree root')
    require(git_read(wt, 'rev-parse', '--absolute-git-dir').decode().strip() == str(git_dir),
            'Git reports a different linked metadata directory')
    common = git_read(wt, 'rev-parse', '--git-common-dir').decode().strip()
    common_path = Path(common)
    require((common_path if common_path.is_absolute() else wt / common_path).resolve() == base / '.git',
            'linked worktree is not associated with approved Git repository')
    require(_git_path(wt, 'index') == git_dir / 'index', 'linked index path mismatch')
    registration = git_read(base, 'worktree', 'list', '--porcelain', '-z').split(b'\0')
    require(b'worktree ' + str(wt).encode('utf-8') in registration,
            'worktree is not registered by the approved repository')
    return {'task_id': wt.name, 'root': str(wt)}


def _effective_root(path, base, policy, *, file_target=False):
    """Resolve host-observed cwd or file path, rejecting worktree impersonation."""
    require(isinstance(path, str) and Path(path).is_absolute(),
            'host must provide an absolute cwd or file path')
    raw = Path(path)
    require('..' not in raw.parts and raw.is_relative_to(base),
            'path is outside the approved repository or traverses parents')
    parts = raw.relative_to(base).parts
    if raw == base or (file_target and parts[:2] != ('.dryforge', 'worktrees')):
        return base, None
    require(parts[:2] == ('.dryforge', 'worktrees') and
            len(parts) >= (4 if file_target else 3), 'not a Go worktree root')
    worktree = base.joinpath(*parts[:3])
    if not file_target:
        require(raw == worktree, 'command cwd must be exactly the worktree root')
    return worktree, _known_worktree(base, worktree, policy)


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
        paths, selected = [], None
        for change in changes:
            require(isinstance(change, dict), 'unknown file change shape')
            kind = change.get('kind')
            require(isinstance(kind, dict) and kind.get('type') in ('add', 'update') and
                    not kind.get('move_path') and not kind.get('movePath'), 'deletion/move is not delegated')
            path = change.get('path')
            effective, info = _effective_root(path, root, policy, file_target=True)
            identity = info['root'] if info else str(root)
            if selected is None:
                selected = identity
            require(selected == identity, 'mixed base/worktree file changes need human review')
            paths.append(scoped_path(path, effective, policy['paths']))
        require('workspace_edit' in policy['operations'], 'workspace edits not delegated')
        return {'operation': 'workspace_edit', 'paths': paths,
                'worktree': selected if selected != str(root) else None}

    argv = command_argv(command)
    is_git = argv[0] in GIT
    if is_git and argv[1:2] == ['-C']:
        require(len(argv) >= 4 and Path(argv[2]).is_absolute(),
                'Git -C needs an absolute approved workspace/worktree root')
        cwd = argv[2]
        argv = [argv[0], *argv[3:]]
    effective, worktree = _effective_root(cwd, root, policy)
    require(not Path(cwd).is_symlink(), 'symlink cwd is not delegated')
    if is_git:
        if worktree is None:
            require((effective / '.git').is_dir() and not (effective / '.git').is_symlink(),
                    'alternate Git metadata requires human review')
            require(not (effective / '.git' / 'commondir').exists(), 'unexpected shared Git metadata')
            require(git_read(effective, 'rev-parse', '--show-toplevel').decode().strip() == str(effective),
                    'Git root mismatch')
        if argv[1:2] == ['add']:
            paths = argv[2:]
            if paths[:1] == ['--']:
                paths = paths[1:]
            require(bool(paths), 'git add needs explicit paths')
            # Explicit files, not directory-wide staging; avoid hidden .git/.dryforge descendants.
            resolved = [scoped_path(p, effective, policy['paths']) for p in paths]
            require(all((effective / p).is_file() for p in resolved), 'git add delegation is for existing explicit files only')
            operation = 'git_add'
        elif len(argv) == 4 and argv[1:3] == ['commit', '-m'] and nonempty(argv[3]):
            raw = git_read(effective, 'diff', '--cached', '--name-status', '-z', '--no-renames', '--no-ext-diff')
            parts = raw.split(b'\0'); resolved = []
            for i in range(0, len(parts) - 1, 2):
                require(i + 1 < len(parts) - 1 and parts[i] in (b'A', b'M'), 'staged deletion/type change is not delegated')
                resolved.append(scoped_path(parts[i+1].decode('utf-8'), effective, policy['paths']))
            require(bool(resolved), 'no verified staged changes')
            operation = 'git_commit'
        else:
            from runtime_git import classify_lifecycle
            require(worktree is None, 'Go lifecycle commands require the base checkout')
            return classify_lifecycle(argv, root, policy)
        require(operation in policy['operations'], f'{operation} is not delegated')
        return {'operation': operation, 'paths': resolved,
                'worktree': worktree['root'] if worktree else None,
                'index_digest': hashlib.sha256(_git_path(effective, 'index').read_bytes()).hexdigest()
                if operation == 'git_commit' else None}

    require('verify' in policy['operations'] and argv in policy['verification_commands'],
            'command is not an exact approved verification argv')
    return {'operation': 'verify', 'argv': argv, 'cwd': str(effective),
            'worktree': worktree['root'] if worktree else None}
