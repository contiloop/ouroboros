"""Private run store: `<workspace>/.dryforge/ouroboros/` with a transactional lock, owner record and archive.

Directory 0700, files 0600. Writes refuse unless the workspace is a git root whose .gitignore ignores
`.dryforge/`. Everything a command writes happens inside one `Store.transaction()`.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .core import digest, now, require

LOCK_TIMEOUT = 5.0
EMBED_LIMIT = 8 * 1024
RUN_FILES = ('proposal.md', 'proposal.shown.md', 'run.json', 'events.jsonl', 'turns')


def private_dir(workspace: Path | str) -> Path:
    return Path(workspace) / '.dryforge' / 'ouroboros'


def check_workspace(workspace: Path) -> None:
    """Refuse before any write: absolute git root with `.dryforge/` ignored."""
    require(workspace.is_absolute(), 'workspace must be an absolute path')
    require(workspace.is_dir(), f'workspace does not exist: {workspace}')
    top = subprocess.run(['git', '-C', str(workspace), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    require(top.returncode == 0 and Path(top.stdout.strip()).resolve() == workspace.resolve(),
            f'workspace is not a git repository root: {workspace}')
    ignored = subprocess.run(['git', '-C', str(workspace), 'check-ignore', '-q', '.dryforge/ouroboros/run.json'],
                             capture_output=True)
    require(ignored.returncode == 0, 'the workspace .gitignore does not ignore `.dryforge/`; add that line first')


def _mkdir(path: Path) -> None:
    path.mkdir(mode=0o700, exist_ok=True)
    path.chmod(0o700)


def _write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _append(path: Path, line: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, 'a', encoding='utf-8') as f:
        f.write(line)


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Store:
    def __init__(self, workspace: Path | str):
        self.workspace = Path(workspace)
        self.dir = private_dir(self.workspace)
        self.run_path = self.dir / 'run.json'
        self.events_path = self.dir / 'events.jsonl'
        self.proposal_path = self.dir / 'proposal.md'
        self.shown_path = self.dir / 'proposal.shown.md'
        self.owner_path = self.dir / 'owner.json'
        self.lock_path = self.dir / 'lock'
        self.turns_dir = self.dir / 'turns'
        self.archive_dir = self.dir / 'archive'

    # ── directory and lock ──────────────────────────────────────────────
    def ensure_dir(self) -> None:
        check_workspace(self.workspace)
        (self.workspace / '.dryforge').mkdir(exist_ok=True)
        _mkdir(self.dir)
        _mkdir(self.turns_dir)

    @contextlib.contextmanager
    def transaction(self, timeout: float = LOCK_TIMEOUT):
        """Exclusive flock on `lock`; refuses after `timeout` seconds. Callers validate before writing."""
        require(self.dir.is_dir(), 'no run record in this workspace')
        check_workspace(self.workspace)
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    require(time.monotonic() < deadline, 'run record lock is held by another command')
                    time.sleep(0.05)
            yield self
        finally:
            os.close(fd)

    # ── owner ───────────────────────────────────────────────────────────
    def read_owner(self) -> dict | None:
        if not self.owner_path.is_file():
            return None
        try:
            return json.loads(self.owner_path.read_text(encoding='utf-8'))
        except ValueError:
            return None

    def write_owner(self, pid: int) -> None:
        _write_bytes(self.owner_path, json.dumps(dict(pid=pid, started=now())).encode())

    # ── record ──────────────────────────────────────────────────────────
    def has_run(self) -> bool:
        return self.run_path.is_file()

    def read_run(self) -> dict:
        require(self.has_run(), 'no run record in this workspace')
        return json.loads(self.run_path.read_text(encoding='utf-8'))

    def write_run(self, run: dict) -> None:
        _write_bytes(self.run_path, json.dumps(run, indent=1, ensure_ascii=False).encode())

    def read_proposal(self) -> bytes | None:
        return self.proposal_path.read_bytes() if self.proposal_path.is_file() else None

    def write_proposal(self, data: bytes) -> None:
        _write_bytes(self.proposal_path, data)

    def write_shown(self, data: bytes) -> None:
        _write_bytes(self.shown_path, data)

    def read_shown(self) -> bytes | None:
        return self.shown_path.read_bytes() if self.shown_path.is_file() else None

    # ── events ──────────────────────────────────────────────────────────
    def event_count(self) -> int:
        if not self.events_path.is_file():
            return 0
        return sum(1 for line in self.events_path.read_text(encoding='utf-8').splitlines() if line.strip())

    def append_event(self, actor: str, kind: str, cycle_id: str | None, data) -> dict:
        event = dict(time=now(), actor=actor, kind=kind, cycle_id=cycle_id, data=data)
        _append(self.events_path, json.dumps(event, ensure_ascii=False) + '\n')
        return event

    def event_data(self, source: Path) -> dict | list | str | int | float | bool | None:
        """Embed small valid JSON; otherwise copy under turns/ and reference by relative path."""
        require(source.is_file(), f'data file not found: {source}')
        raw = source.read_bytes()
        if len(raw) <= EMBED_LIMIT:
            try:
                return json.loads(raw.decode('utf-8'))
            except ValueError:
                pass
        n = 1 + sum(1 for p in self.turns_dir.glob('event-*'))
        ext = source.suffix.lstrip('.') or 'bin'
        target = self.turns_dir / f'event-{n}.{ext}'
        _write_bytes(target, raw)
        return dict(file=f'turns/{target.name}', sha256=digest(raw), size=len(raw))

    # ── archive ─────────────────────────────────────────────────────────
    def archive(self, run: dict, actor: str = 'L1') -> Path:
        """Move the finished run's files under archive/<run_id>/ (the archive event goes with them)."""
        require(run['status'] in ('COMPLETE', 'STOPPED'), f'run is {run["status"]}; only COMPLETE or STOPPED runs are archived')
        dest = self.archive_dir / run['run_id']
        require(not dest.exists(), f'archive already exists: {dest}')
        _mkdir(self.archive_dir)
        self.append_event(actor, 'archive', None, dict(run_id=run['run_id'], path=f'archive/{run["run_id"]}'))
        _mkdir(dest)
        for name in RUN_FILES:
            src = self.dir / name
            if src.exists():
                shutil.move(str(src), str(dest / name))
        _mkdir(self.turns_dir)
        return dest


def check_owner(store: Store, pid: int) -> None:
    """Refuse while a live owner other than `pid` holds the workspace; a dead owner is stale."""
    owner = store.read_owner()
    if owner is None or owner.get('pid') == pid:
        return
    other = owner.get('pid')
    require(not (isinstance(other, int) and pid_alive(other)),
            f'another L1 (pid {other}) owns this workspace run; stop it or wait for it to exit')
