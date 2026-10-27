#!/usr/bin/env python3
"""Ouroboros run-record CLI. JSON on stdout, exit 0; refusals print {"status":"BLOCKED",...}, exit 2, change nothing.

Every command takes --workspace <absolute git root> and --owner <pid of the L1 host process>.
Run as: python3 -B ouroboros_cli.py --workspace W --owner PID <command> [args]
"""
from __future__ import annotations

import argparse
import difflib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ouroboros import core  # noqa: E402
from ouroboros.core import RecordError, require  # noqa: E402
from ouroboros.store import Store, check_owner  # noqa: E402


def read_text(path: str) -> str:
    p = Path(path)
    require(p.is_file(), f'file not found: {path}')
    return p.read_text(encoding='utf-8')


def summary(store: Store) -> dict:
    run = store.read_run()
    raw = store.read_proposal()
    return core.summary(run, core.digest(raw) if raw is not None else None, store.event_count())


# ── commands ──────────────────────────────────────────────────────────────

def cmd_doctor(store: Store, a) -> dict:
    """Minimal: reports whether `claude` is on PATH. T3 completes it (version, dryforge plugin)."""
    return dict(host=a.host, claude=shutil.which('claude'))


def cmd_draft(store: Store, a) -> dict:
    data = Path(a.proposal).read_bytes() if Path(a.proposal).is_file() else None
    require(data is not None, f'proposal file not found: {a.proposal}')
    store.ensure_dir()
    with store.transaction():
        check_owner(store, a.owner)
        run = store.read_run() if store.has_run() else None
        if run is not None and run['status'] in ('COMPLETE', 'STOPPED'):
            store.archive(run)
            run = None
        if run is not None:
            run = core.redraft(run)
            if store.shown_path.exists():
                store.shown_path.unlink()
        else:
            run = core.new_run(str(store.workspace))
        store.write_owner(a.owner)
        store.write_proposal(data)
        store.write_run(run)
        store.append_event('human', 'draft', None, dict(run_id=run['run_id'], proposal_digest=core.digest(data)))
        return summary(store)


def cmd_shown(store: Store, a) -> dict:
    with store.transaction():
        run = store.read_run()
        raw = store.read_proposal()
        require(raw is not None, 'nothing proposed')
        d = core.digest(raw)
        store.write_shown(raw)
        store.write_run(core.record_shown(run, d))
        store.append_event('L1', 'shown', None, dict(digest=d))
        return summary(store)


def cmd_show(store: Store, a) -> dict:
    return summary(store)


def cmd_approve(store: Store, a) -> dict:
    raw = store.read_proposal()
    require(raw is not None, 'nothing proposed')
    with store.transaction():
        check_owner(store, a.owner)
        run = store.read_run()
        current = core.digest(raw)
        try:
            run, action = core.approve(run, current, raw.decode('utf-8'))
        except RecordError as exc:
            if 'shown_digest' in exc.details:
                shown = (store.read_shown() or b'').decode('utf-8', 'replace')
                exc.details['diff'] = ''.join(difflib.unified_diff(
                    shown.splitlines(True), raw.decode('utf-8', 'replace').splitlines(True),
                    'proposal.shown.md', 'proposal.md'))
            raise
        if action == 'unchanged':
            return summary(store)
        store.write_owner(a.owner)
        store.write_run(run)
        store.append_event('human', 'approve' if action == 'activated' else 'amend', None,
                           dict(digest=current, limits=run['limits']))
        return dict(summary(store), approval=action)


def cmd_cycle_start(store: Store, a) -> dict:
    goal = read_text(a.goal)
    with store.transaction():
        run = core.cycle_start(store.read_run(), a.kind, goal, a.checkpoint)
        cycle = run['cycles'][-1]
        store.write_run(run)
        store.append_event('L1', 'cycle_start', cycle['id'],
                           dict(kind=a.kind, checkpoint_before=a.checkpoint, goal_digest=core.digest(goal.encode())))
        return summary(store)


def cmd_cycle_stage(store: Store, a) -> dict:
    with store.transaction():
        run = core.cycle_stage(store.read_run(), a.stage, a.ready_digest, a.checkpoint)
        cycle = core.open_cycle(run)
        store.write_run(run)
        store.append_event('L1', 'cycle_stage', cycle['id'],
                           dict(stage=a.stage, ready_digest=cycle['ready_digest'], checkpoint_after=cycle['checkpoint_after']))
        return summary(store)


def cmd_evaluate(store: Store, a) -> dict:
    basis = read_text(a.basis)
    with store.transaction():
        before = store.read_run()
        run, extra = core.evaluate(before, a.decision)
        cycle_id = run['cycles'][-1]['id']
        store.write_run(run)
        store.append_event('L1', 'evaluate', cycle_id, dict(decision=a.decision, basis=basis))
        for e in extra:
            store.append_event(e['actor'], e['kind'], e['cycle_id'], e['data'])
        return summary(store)


def cmd_event(store: Store, a) -> dict:
    require(a.actor in core.ACTORS, f'actor must be one of {", ".join(core.ACTORS)}')
    require(bool(a.kind.strip()), 'kind is empty')
    source = Path(a.data)
    require(source.is_file(), f'data file not found: {a.data}')
    with store.transaction():
        run = store.read_run()
        if a.cycle is not None:
            require(any(c['id'] == a.cycle for c in run['cycles']), f'unknown cycle: {a.cycle}')
        store.append_event(a.actor, a.kind, a.cycle, store.event_data(source))
        return summary(store)


def cmd_stop(store: Store, a) -> dict:
    with store.transaction():
        run = core.stop(store.read_run(), a.reason)
        cycle = core.open_cycle(run)
        store.write_run(run)
        store.append_event('human' if a.reason == 'abort' else 'L1', 'stop', cycle['id'] if cycle else None,
                           dict(reason=a.reason, stage=cycle['stage'] if cycle else None))
        return summary(store)


def cmd_archive(store: Store, a) -> dict:
    with store.transaction():
        run = store.read_run()
        dest = store.archive(run)
        return dict(archived=run['run_id'], path=str(dest))


def add_commands(sub) -> dict:
    """Register the run-record commands; returns name → handler. Session commands register alongside."""
    handlers = {}

    def cmd(name, fn, help_text):
        p = sub.add_parser(name, help=help_text)
        handlers[name] = fn
        return p

    cmd('doctor', cmd_doctor, 'report host prerequisites').add_argument('--host', default='claude', choices=['claude'])
    cmd('draft', cmd_draft, 'create or replace the DRAFT proposal').add_argument('--proposal', required=True)
    cmd('shown', cmd_shown, 'record the current proposal digest as shown')
    cmd('show', cmd_show, 'print the run summary')
    cmd('approve', cmd_approve, 'approve the proposal exactly as shown')
    p = cmd('cycle-start', cmd_cycle_start, 'open a cycle')
    p.add_argument('--kind', required=True)
    p.add_argument('--goal', required=True)
    p.add_argument('--checkpoint', required=True)
    p = cmd('cycle-stage', cmd_cycle_stage, 'advance the open cycle')
    p.add_argument('--stage', required=True)
    p.add_argument('--ready-digest')
    p.add_argument('--checkpoint')
    p = cmd('evaluate', cmd_evaluate, 'close the open cycle with a decision')
    p.add_argument('--decision', required=True)
    p.add_argument('--basis', required=True)
    p = cmd('event', cmd_event, 'append one event')
    p.add_argument('--actor', required=True)
    p.add_argument('--kind', required=True)
    p.add_argument('--cycle')
    p.add_argument('--data', required=True)
    cmd('stop', cmd_stop, 'set the run STOPPED').add_argument('--reason', required=True)
    cmd('archive', cmd_archive, 'move a finished run under archive/')
    return handlers


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--workspace', required=True, help='absolute path of the target git root')
    p.add_argument('--owner', required=True, type=int, help='pid of the L1 host process')
    sub = p.add_subparsers(dest='command', required=True)
    return p, add_commands(sub)


def main(argv=None) -> int:
    parser, handlers = build_parser()
    a = parser.parse_args(argv)
    try:
        out = handlers[a.command](Store(a.workspace), a)
    except RecordError as exc:
        print(json.dumps(dict(status='BLOCKED', error=str(exc), **exc.details), ensure_ascii=False))
        return 2
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
