"""Read-only preflight for a separately delegated exact-commit Go integration.

The human grants this scope through a v3 runtime-policy event. This module
does not run the requested merge, authorize a deployment, or trust L2 prose.
"""
from __future__ import annotations

from pathlib import Path
import re


def inspect_merge(root, argv, policy, git_read, known_worktree, scoped_path, require):
    require(len(argv) == 6 and argv[1:3] == ['merge', '--no-ff'] and argv[4] == '-m'
            and bool(argv[5].strip()),
            'only an exact git merge --no-ff <SHA> -m <message> is delegated')
    sha = argv[3]
    require(re.fullmatch(r'[a-f0-9]{40}', sha) is not None,
            'merge source must be a pinned full commit SHA')
    require(policy['version'] == 3 and policy['go_worktrees'] and
            'git_merge' in policy['operations'],
            'merge requires a separately approved v3 integration policy')
    branch = policy['integration_branch']
    require(git_read(root, 'symbolic-ref', '--short', 'HEAD').decode().strip() == branch,
            'merge destination branch does not match the approved branch')
    require(not git_read(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all'),
            'merge requires a completely clean destination')
    head = git_read(root, 'rev-parse', 'HEAD').decode().strip()
    require(head != sha, 'source and destination are identical')
    git_read(root, 'merge-base', '--is-ancestor', head, sha)

    pool = root / '.dryforge' / 'worktrees'
    require(pool.is_dir() and not pool.is_symlink(), 'Go worktree pool missing or unsafe')
    candidates = list(pool.iterdir())
    require(len(candidates) <= 128, 'too many worktrees to establish identity')
    matching = []
    for wt in candidates:
        if not wt.is_dir() or not (wt / '.git').is_file():
            continue
        try:
            info = known_worktree(root, wt, policy)
            wt_sha = git_read(wt, 'rev-parse', 'HEAD').decode().strip()
            task_branch = git_read(wt, 'symbolic-ref', '--short', 'HEAD').decode().strip()
        except (OSError, ValueError):
            continue
        if wt_sha != sha:
            continue
        require(re.fullmatch(r'dryforge/[A-Za-z0-9][A-Za-z0-9_./-]{0,95}', task_branch) is not None
                and '..' not in task_branch and '//' not in task_branch,
                'merge source must be a named Dryforge task branch')
        require(not git_read(wt, 'status', '--porcelain=v1', '-z', '--untracked-files=no'),
                'task worktree has tracked modifications')
        matching.append((info, task_branch))
    require(len(matching) == 1, 'merge source must uniquely match a registered Go worktree')

    delta = git_read(root, 'diff', '--no-ext-diff', '--name-status', '-z', '--no-renames', head, sha)
    chunks = delta.split(b'\0')
    require(chunks[-1:] == [b''], 'malformed Git path list')
    chunks = chunks[:-1]
    require(len(chunks) > 0 and len(chunks) % 2 == 0, 'merge has no valid inspected changes')
    paths = []
    for i in range(0, len(chunks), 2):
        require(chunks[i] in (b'A', b'M'), 'merge contains a deletion, rename or type change')
        name = chunks[i + 1].decode('utf-8')
        path = scoped_path(name, root, policy['paths'])
        entry = git_read(root, 'ls-tree', '-z', sha, '--', name).rstrip(b'\0')
        require(entry and b'\t' in entry and entry.split(b'\t', 1)[1] == chunks[i + 1],
                'merge path not independently verified in source tree')
        mode_type = entry.split(b'\t', 1)[0].split(b' ', 2)
        require(len(mode_type) == 3 and mode_type[0] in (b'100644', b'100755') and
                mode_type[1] == b'blob',
                'merge changes a symlink, submodule or unsupported mode')
        paths.append(path)
    return {'operation': 'git_merge', 'paths': paths, 'merge_source': sha,
            'merge_base_head': head, 'merge_destination': branch,
            'merge_task_branch': matching[0][1],
            'merge_task_worktree': matching[0][0]['root']}
