"""Dryforge migration documentation boundaries; no model calls or execution authority."""
import hashlib
from pathlib import Path, PurePosixPath


def documentation_path(value):
    if not isinstance(value, str) or not value or '\\' in value:
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or path.as_posix() != value:
        return False
    if any(p.startswith('.') for p in path.parts):
        return value == '.gitignore'
    return (path.name in {'AGENTS.md', 'CLAUDE.md'} or
            (path.parts[0] == 'docs' and path.suffix == '.md'))


def artifact_digest(workspace, paths):
    if (not isinstance(paths, list) or not paths or len(paths) > 4096 or
            not all(isinstance(p, str) for p in paths) or len(set(paths)) != len(paths)):
        raise ValueError('migration needs a bounded list of distinct artifact paths')
    if not {'AGENTS.md', 'CLAUDE.md', '.dryforge/status.json'} <= set(paths):
        raise ValueError('migration requires root entry documents and the completion marker')
    if not any(p.startswith('docs/') and p.endswith('.md') for p in paths):
        raise ValueError('migration project docs are missing')
    root = Path(workspace).resolve(strict=True)
    h = hashlib.sha256()
    for name in sorted(paths):
        if name != '.dryforge/status.json' and not documentation_path(name):
            raise ValueError('not a migration artifact: '+name)
        target = root / name
        for candidate in (target, *target.parents):
            if candidate == root:
                break
            if candidate.is_symlink():
                raise ValueError('migration artifact path is symlinked')
            if candidate != target and (candidate / '.git').exists():
                raise ValueError('migration artifact belongs to a nested repository')
        if not target.is_file():
            raise ValueError('migration artifact is missing: '+name)
        data = target.read_bytes()
        h.update(name.encode() + b'\0' + str(len(data)).encode() + b'\0' + data)
    return h.hexdigest()
