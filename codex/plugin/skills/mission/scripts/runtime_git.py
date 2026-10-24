"""Read-only scope inspection for explicitly delegated local Go integration.

The host executes the original request. These observations are compared again
when consuming approval; they do not turn trusted Git hooks into a sandbox.
"""
import hashlib
from pathlib import Path
import re

from runtime_permissions import (GO_OPERATIONS, _git_path, _known_worktree,
                                git_read, nonempty, require, scoped_path)


def branch_name(value):
    return (nonempty(value) and not value.startswith(('-', '/')) and
            not value.endswith(('/', '.')) and
            not any(x in value for x in ('..', '@{', '//')) and
            not any(c in value for c in ' ~^:?*[\\') and
            all(not p.startswith('.') and not p.endswith('.lock') for p in value.split('/')))


def validate_workflow(policy):
    workflow = policy['go_workflow']
    if workflow is None:
        require(not set(policy['operations']) & GO_OPERATIONS, 'Go lifecycle needs a workflow grant')
        return
    require(isinstance(workflow, dict) and set(workflow) == {'base_branch', 'branch_prefix'},
            'Go workflow needs base_branch and branch_prefix')
    prefix = workflow['branch_prefix']
    require(branch_name(workflow['base_branch']) and isinstance(prefix, str) and
            prefix.endswith('/') and branch_name(prefix + 'task'), 'invalid Go branch scope')
    require(not workflow['base_branch'].startswith(prefix), 'base branch cannot be a task branch')
    require(policy['go_worktrees'] and policy['trust_workspace_code'],
            'Go lifecycle requires worktree and code-trust grants')


def head(root):
    return git_read(root, 'rev-parse', '--verify', 'HEAD').decode().strip()


def branch(root):
    return git_read(root, 'symbolic-ref', '--quiet', '--short', 'HEAD').decode().strip()


def clean(root, *, remove=False):
    args = ['status', '--porcelain=v1', '-z', '--untracked-files=all']
    if remove:
        args.append('--ignored')
    require(not git_read(root, *args), 'checkout contains changes or data that must be preserved')
    for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply'):
        require(not _git_path(root, marker).exists(), 'Git operation already in progress')


def registrations(root):
    records = []
    for raw in git_read(root, 'worktree', 'list', '--porcelain', '-z').split(b'\0\0'):
        record = {}
        for field in raw.split(b'\0'):
            key, _, value = field.partition(b' ')
            if key:
                record[key.decode()] = value.decode()
        if record:
            records.append(record)
    return records


def pool_path(value, root):
    raw = Path(value)
    target = raw if raw.is_absolute() else root / raw
    pool = root / '.dryforge' / 'worktrees'
    require('..' not in raw.parts and target.parent == pool and
            re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', target.name), 'invalid Go worktree destination')
    for p in (root / '.dryforge', pool, target):
        require(not p.is_symlink(), 'symlinked Go destination')
    return target


def ancestor(root, older, newer):
    require(git_read(root, 'merge-base', older, newer).decode().strip() == older,
            'task is not safely based on or integrated into the approved base')


def classify_lifecycle(argv, root, policy):
    require(policy['version'] == 3 and policy['go_workflow'] is not None,
            'Go lifecycle requires an explicit policy v3 grant')
    workflow = policy['go_workflow']
    base, prefix = workflow['base_branch'], workflow['branch_prefix']
    require(branch(root) == base, 'base checkout is on a different branch')
    clean(root)
    base_head = head(root)
    snapshot = {'base_head': base_head, 'base_branch': base,
                'index_digest': hashlib.sha256(_git_path(root, 'index').read_bytes()).hexdigest()}
    records = registrations(root)
    if len(argv) == 7 and argv[1:4] == ['worktree', 'add', '-b']:
        name, destination, start = argv[4:]
        require(branch_name(name) and name.startswith(prefix), 'task branch is outside grant')
        require(start in (base, base_head), 'task must start from the current approved base')
        existing = git_read(root, 'for-each-ref', '--format=%(refname)', 'refs/heads/').decode().splitlines()
        require('refs/heads/' + name not in existing, 'task branch already exists')
        target = pool_path(destination, root)
        require(not target.exists() and not any(r.get('worktree') == str(target) for r in records),
                'worktree destination already exists or is registered')
        snapshot.update(operation='git_worktree_add', branch=name, worktree=str(target))
    elif len(argv) == 6 and argv[1:3] == ['merge', '--no-ff'] and argv[4] == '-m' and nonempty(argv[5]):
        ref = argv[3]
        candidates = [r for r in records if r.get('branch', '').startswith('refs/heads/' + prefix)
                      and ref in (r.get('HEAD'), r.get('branch', '')[11:])]
        require(len(candidates) == 1, 'merge target must identify one registered Go task')
        record = candidates[0]
        target = Path(record['worktree'])
        _known_worktree(root, target, policy)
        clean(target)
        task_head = head(target)
        require(task_head == record['HEAD'] and task_head != base_head, 'task head mismatch or empty integration')
        ancestor(root, base_head, task_head)
        raw = git_read(root, 'diff', '--raw', '-z', '--no-renames', '--no-ext-diff', base_head, task_head).split(b'\0')
        paths = []
        for i in range(0, len(raw) - 1, 2):
            fields = raw[i].split()
            require(len(fields) == 5 and fields[4] in (b'A', b'M') and fields[1] in (b'100644', b'100755'),
                    'merge contains deletion, type change or non-regular file')
            paths.append(scoped_path(raw[i + 1].decode(), root, policy['paths']))
        require(bool(paths), 'merge has no scoped changes')
        snapshot.update(operation='git_merge', worktree=str(target), task_head=task_head,
                        branch=record['branch'], paths=paths)
    elif len(argv) == 4 and argv[1:3] == ['worktree', 'remove']:
        target = pool_path(argv[3], root)
        _known_worktree(root, target, policy)
        name = branch(target)
        require(name.startswith(prefix), 'task branch is outside grant')
        clean(target, remove=True)
        task_head = head(target)
        ancestor(root, task_head, base_head)
        snapshot.update(operation='git_worktree_remove', worktree=str(target), branch=name, task_head=task_head)
    elif len(argv) == 4 and argv[1:3] == ['branch', '-d']:
        name = argv[3]
        require(branch_name(name) and name.startswith(prefix), 'task branch is outside grant')
        require(not any(r.get('branch') == 'refs/heads/' + name for r in records), 'branch is still checked out')
        task_head = git_read(root, 'rev-parse', '--verify', 'refs/heads/' + name).decode().strip()
        ancestor(root, task_head, base_head)
        snapshot.update(operation='git_branch_delete', branch=name, task_head=task_head)
    else:
        require(False, 'Git operation/options are not delegated')
    require(snapshot['operation'] in policy['operations'], 'Go operation is not delegated')
    return snapshot
