"""Read-only Git checks for a human grant narrowed to one L1-assigned cycle.

The integration branch, cycle branch and task branches have different roles.
Bindings select exact targets; they never add operations or paths to a grant.
"""
import hashlib
from pathlib import Path
import re

from runtime_permissions import (_git_path, _known_worktree, fingerprint, git_read,
                                 nonempty, require, scoped_path)
from runtime_git import ancestor, branch, branch_name, clean, head, pool_path, registrations


def tip(root, name):
    require(branch_name(name), 'invalid branch name')
    return git_read(root, 'rev-parse', '--verify', 'refs/heads/' + name).decode().strip()


def branches(root):
    return git_read(root, 'for-each-ref', '--format=%(refname:strip=2)', 'refs/heads/').decode().splitlines()


def validate_workflow(policy):
    w = policy['go_workflow']
    require(isinstance(w, dict) and set(w) ==
            {'integration_branch', 'cycle_branch_prefix', 'task_branch_prefix'},
            'v4 workflow needs integration_branch, cycle_branch_prefix and task_branch_prefix')
    require(branch_name(w['integration_branch']), 'invalid integration branch')
    for key in ('cycle_branch_prefix', 'task_branch_prefix'):
        p = w[key]
        require(nonempty(p) and p.endswith(('/', '-')) and branch_name(p + 'task'),
                'branch prefix must end in / or -')
        require(not w['integration_branch'].startswith(p), 'integration branch overlaps branch scope')
    require(policy['go_worktrees'] and policy['trust_workspace_code'],
            'cycle workflow requires worktree and code-trust grants')


def targets(policy, value):
    require(isinstance(value, dict) and set(value) == {'cycle_branch', 'tasks', 'archive_dir'},
            'binding needs cycle_branch, tasks and archive_dir')
    w = policy['go_workflow']; feature = value['cycle_branch']; tasks = value['tasks']
    require(branch_name(feature) and (feature == w['integration_branch'] or
            feature.startswith(w['cycle_branch_prefix'])), 'cycle branch outside grant')
    require(isinstance(tasks, dict) and len(tasks) <= 128, 'tasks must map pool IDs to branch names')
    for task, name in tasks.items():
        require(isinstance(task, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', task),
                'invalid worktree ID')
        require(branch_name(name) and name.startswith(w['task_branch_prefix']) and
                name not in (feature, w['integration_branch']), 'task branch outside grant or overlaps another role')
    require(len(set(tasks.values())) == len(tasks), 'task branches must be unique')
    require(isinstance(value['archive_dir'], str) and
            re.fullmatch(r'\.dryforge/[0-9]{3,}', value['archive_dir']), 'invalid archive directory')


def create_binding(root, authority, cycle, value):
    policy = authority['policy']
    require(policy['version'] == 4, 'cycle targets need an explicit v4 grant')
    targets(policy, value)
    clean(root)
    require((root/'.git').is_dir() and not (root/'.git').is_symlink(), 'binding needs the ordinary Git root')
    require(not (root/'.dryforge').is_symlink(), 'symlinked cycle metadata')
    integration = policy['go_workflow']['integration_branch']; feature = value['cycle_branch']
    initial = tip(root, integration)
    require(branch(root) in (integration, feature) and head(root) == initial,
            'bind before implementation from the unchanged integration tip')
    existing = branches(root)
    require(feature not in existing or tip(root, feature) == initial,
            'existing cycle branch has work; reconcile it before assigning')
    require(not set(value['tasks'].values()) & set(existing), 'task branches already exist')
    require(not (root/value['archive_dir']).exists(), 'archive destination already exists')
    for task in value['tasks']:
        require(not pool_path(str(root/'.dryforge/worktrees'/task), root).exists(), 'task destination already exists')
    return dict(value, integration_branch=integration, integration_head=initial,
                policy_digest=fingerprint(authority), docs_digest=cycle['approved_digest'])


def validate_binding(root, policy, cycle):
    require(isinstance(cycle, dict) and isinstance(cycle.get('runtime_binding'), dict),
            'L1 must bind this cycle to concrete execution targets')
    b = cycle['runtime_binding']
    targets(policy, {k:b[k] for k in ('cycle_branch', 'tasks', 'archive_dir')})
    require(b['integration_branch'] == policy['go_workflow']['integration_branch'] and
            b['docs_digest'] == cycle['approved_digest'] == cycle['digest'], 'stale cycle binding')
    archive = root/b['archive_dir']
    require(not (root/'.dryforge').is_symlink() and not archive.is_symlink(), 'symlinked archive')


def extend_tasks(root, authority, cycle, additions):
    """L1 may assign a new repair task without changing existing identities."""
    policy = authority['policy']; b = cycle['runtime_binding']
    require(b['policy_digest'] == fingerprint(authority), 'cycle binding uses a stale runtime grant')
    validate_binding(root, policy, cycle)
    require(isinstance(additions, dict) and additions and not set(additions) & set(b['tasks']),
            'add only new task IDs; existing assignments are immutable')
    proposed = dict(cycle_branch=b['cycle_branch'], tasks=dict(b['tasks'], **additions), archive_dir=b['archive_dir'])
    targets(policy, proposed)
    clean(root); check_checkout(root, root, cycle)
    existing = branches(root)
    for task, name in additions.items():
        require(name not in existing and not pool_path(str(root/'.dryforge/worktrees'/task),root).exists(),
                'new task branch or worktree already exists')
    return dict(b, tasks=proposed['tasks'])


def check_checkout(root, effective, cycle, *, verify=False):
    b = cycle['runtime_binding']; current = branch(effective)
    if effective == root:
        allowed = {b['cycle_branch']}
        if verify and cycle['stage'] == 'ACCEPTED':
            allowed.add(b['integration_branch'])
        require(current in allowed, 'operation is not on the assigned cycle branch')
    else:
        require(b['tasks'].get(effective.name) == current, 'worktree is not assigned to this cycle')
    ancestor(root, b['integration_head'], head(effective))


def approved_documents(root, cycle):
    """Accept only the pinned archive, and only after result acceptance.

    During a move each file may exist in either location; duplicate copies must
    agree. Never search older archives for a digest that happens to match.
    """
    from mission_state import document_digest
    b = cycle.get('runtime_binding')
    if not b or cycle['stage'] != 'ACCEPTED':
        return document_digest(root/'.dryforge')
    h = hashlib.sha256()
    for name in ('handoff.md', 'spec.md', 'plan.md'):
        options = [root/'.dryforge'/name, root/b['archive_dir']/name]
        require(all(not p.is_symlink() for p in options), 'symlinked approved document')
        copies = [p.read_bytes() for p in options if p.is_file()]
        require(copies and all(data == copies[0] for data in copies), 'missing or conflicting approved documents')
        data = copies[0]
        h.update(name.encode() + b'\0' + str(len(data)).encode() + b'\0' + data)
    return h.hexdigest()


def delta(root, older, newer, policy):
    raw = git_read(root, 'diff', '--raw', '-z', '--no-renames', '--no-ext-diff', older, newer).split(b'\0')
    paths = []
    for i in range(0, len(raw)-1, 2):
        fields = raw[i].split()
        require(len(fields) == 5 and fields[4] in (b'A', b'M') and fields[1] in (b'100644', b'100755'),
                'merge contains deletion, type change or non-regular file')
        paths.append(scoped_path(raw[i+1].decode(), root, policy['paths']))
    require(paths, 'merge has no scoped changes')
    return paths


def classify_lifecycle(argv, root, policy, cycle):
    validate_binding(root, policy, cycle)
    b = cycle['runtime_binding']; feature = b['cycle_branch']; integration = b['integration_branch']
    current = branch(root); current_head = head(root); clean(root)
    require(current in (feature, integration), 'checkout is outside assigned branches')
    ancestor(root, b['integration_head'], current_head)
    if cycle['stage'] == 'ACCEPTED' and current == feature:
        require(current_head == cycle['result']['commit'], 'accepted cycle branch changed')
    snapshot = dict(base_branch=current, base_head=current_head,
                    index_digest=hashlib.sha256(_git_path(root, 'index').read_bytes()).hexdigest())
    records = registrations(root)
    if argv[1:2] == ['checkout']:
        require('git_checkout' in policy['operations'], 'checkout not delegated')
        if len(argv) == 4 and argv[2] == '-b':
            require(cycle['stage'] == 'GO' and argv[3] == feature != integration and
                    current == integration and current_head == b['integration_head'] and
                    feature not in branches(root), 'not a new assigned cycle branch')
            target = feature; target_head = current_head
        else:
            require(len(argv) == 3, 'checkout options are not delegated')
            target = argv[2]; target_head = tip(root, target)
            if target == feature and current == integration and cycle['stage'] == 'GO':
                require(target_head == current_head == b['integration_head'], 'cycle start has changed')
            else:
                require(cycle['stage'] == 'ACCEPTED' and current == feature and target == integration and
                        target_head == b['integration_head'] and current_head == cycle['result']['commit'],
                        'return to integration requires the accepted feature result and unchanged target')
        snapshot.update(operation='git_checkout', branch=target, target_head=target_head)
    elif len(argv) == 7 and argv[1:4] == ['worktree', 'add', '-b']:
        name, destination, start = argv[4:]; target = pool_path(destination, root)
        require(cycle['stage'] == 'GO' and current == feature, 'tasks start from the assigned cycle branch during Go')
        require(b['tasks'].get(target.name) == name, 'task branch/path is not assigned')
        require(start in (feature, current_head), 'task must start from the cycle tip')
        require(name not in branches(root) and not target.exists() and
                not any(r.get('worktree') == str(target) for r in records), 'task branch or worktree already exists')
        snapshot.update(operation='git_worktree_add', branch=name, worktree=str(target))
    elif len(argv) == 6 and argv[1:3] == ['merge', '--no-ff'] and argv[4] == '-m' and nonempty(argv[5]):
        ref = argv[3]
        if current == integration and feature != integration:
            require(cycle['stage'] == 'ACCEPTED' and current_head == b['integration_head'],
                    'final integration needs acceptance and an unchanged integration target')
            source = tip(root, feature)
            require(source == cycle['result']['commit'] and ref in (feature, source),
                    'integration source is not the accepted cycle commit')
            source_branch = feature
        else:
            require(current == feature and cycle['stage'] == 'GO', 'task integration requires Go on the cycle branch')
            candidates = [r for r in records if r.get('branch', '')[11:] in b['tasks'].values()
                          and ref in (r.get('HEAD'), r.get('branch', '')[11:])]
            require(len(candidates) == 1, 'merge source must be one assigned registered task')
            record = candidates[0]; target = Path(record['worktree'])
            _known_worktree(root, target, policy); check_checkout(root, target, cycle); clean(target)
            source = head(target); source_branch = branch(target)
            require(source == record['HEAD'], 'task registration changed')
            snapshot['worktree'] = str(target)
        merge_base = git_read(root, 'merge-base', current_head, source).decode().strip()
        ancestor(root, b['integration_head'], merge_base)
        if current == integration and feature != integration:
            ancestor(root, current_head, source)
        elif merge_base != current_head:
            # Sibling tasks start at the same cycle tip. Permit disjoint parallel
            # changes; overlapping divergence needs explicit conflict handling.
            ours = set(git_read(root, 'diff', '--name-only', '-z', merge_base, current_head).split(b'\0')) - {b''}
            theirs = set(git_read(root, 'diff', '--name-only', '-z', merge_base, source).split(b'\0')) - {b''}
            require(not ours & theirs, 'diverged task touches already changed paths; reconcile before merge')
        snapshot.update(operation='git_merge', task_head=source, branch=source_branch,
                        paths=delta(root, merge_base, source, policy))
    elif len(argv) == 4 and argv[1:3] == ['worktree', 'remove']:
        target = pool_path(argv[3], root); _known_worktree(root, target, policy)
        name = branch(target); source = head(target)
        require(b['tasks'].get(target.name) == name, 'worktree is not assigned to this cycle')
        clean(target, remove=True); ancestor(root, source, current_head)
        snapshot.update(operation='git_worktree_remove', worktree=str(target), branch=name, task_head=source)
    elif len(argv) == 4 and argv[1:3] == ['branch', '-d']:
        name = argv[3]
        allowed = set(b['tasks'].values())
        if cycle['stage'] == 'ACCEPTED' and current == integration and feature != integration:
            allowed.add(feature)
        require(name in allowed, 'branch is outside this cycle')
        require(not any(r.get('branch') == 'refs/heads/' + name for r in records), 'branch is still checked out')
        source = tip(root, name); ancestor(root, source, current_head)
        if name == feature:
            require(source == cycle['result']['commit'], 'feature cleanup is not the accepted result')
        snapshot.update(operation='git_branch_delete', branch=name, task_head=source)
    else:
        require(False, 'Git operation/options are not delegated')
    require(snapshot['operation'] in policy['operations'], 'operation not delegated')
    return snapshot
