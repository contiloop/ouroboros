#!/usr/bin/env python3
"""Ouroboros run-record CLI. JSON on stdout, exit 0; refusals print {"status":"BLOCKED",...}, exit 2, change nothing.

Every command takes --workspace <absolute git root> and --owner <pid of the L1 host process>.
Run as: python3 -B ouroboros_cli.py --workspace W --owner PID <command> [args]
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ouroboros import adapters, core  # noqa: E402
from ouroboros.core import RecordError, now, require  # noqa: E402
from ouroboros.ports import Turn  # noqa: E402
from ouroboros.store import Store, check_owner  # noqa: E402

SKILLS = ('ready', 'go', 'migration')
WAIT_POLL = 0.05


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
    """Reports the host prerequisites; a missing executable or plugin is reported, never a refusal."""
    return adapters.for_host(a.host).doctor()


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
    require(store.has_run(), 'nothing proposed')
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
    require(store.has_run() and store.proposal_path.is_file(), 'nothing proposed')
    with store.transaction():
        check_owner(store, a.owner)
        run = store.read_run()
        raw = store.read_proposal()
        require(raw is not None, 'nothing proposed')
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
        run, extra = core.cycle_start(store.read_run(), a.kind, goal, a.checkpoint)
        cycle = run['cycles'][-1]
        store.write_run(run)
        store.append_event('L1', 'cycle_start', cycle['id'],
                           dict(kind=a.kind, checkpoint_before=a.checkpoint, goal_digest=core.digest(goal.encode())))
        for e in extra:
            store.append_event(e['actor'], e['kind'], e['cycle_id'], e['data'])
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
        run, extra = core.evaluate(store.read_run(), a.decision, basis)
        cycle_id = run['cycles'][-1]['id']
        store.write_run(run)
        store.append_event('L1', 'evaluate', cycle_id,
                           dict(decision=a.decision, basis=store.event_data(Path(a.basis), text=True)))
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
                           dict(reason=a.reason, stopped_at=run['stopped_at']))
        return summary(store)


def cmd_archive(store: Store, a) -> dict:
    with store.transaction():
        run = store.read_run()
        dest = store.archive(run)
        return dict(archived=run['run_id'], path=str(dest))


# ── session commands (through the host-session port) ─────────────────────

def _host(run: dict):
    try:
        return adapters.for_host(run['host'])
    except ValueError as exc:
        raise RecordError(str(exc))


def _turn_handle(store: Store, turn: dict) -> Turn:
    return Turn(pid=int(turn['pid']), raw_path=store.turns_dir / f"{turn['n']}.json")


def _running(run: dict) -> dict | None:
    turn = run.get('turn')
    return turn if turn and turn.get('state') == 'RUNNING' else None


def _launch(store: Store, a, message: str, kind: str, fresh: bool, reason: str | None) -> dict:
    """Shared by session-start and session-send: validate, launch detached, then record the turn."""
    with store.transaction():
        check_owner(store, a.owner)
        run = store.read_run()
        require(run['status'] == 'ACTIVE', f'run is {run["status"]}, not ACTIVE')
        running = _running(run)
        require(running is None, f'turn {running["n"] if running else ""} is still RUNNING; wait for it or stop it')
        session_id = run['session']['id']
        if kind == 'message':
            require(session_id is not None, 'no session recorded; start one with session-start')
        elif session_id is None:
            fresh = True
        host = _host(run)
        store.ensure_dir()
        n = int(run.get('turn_count', 0)) + 1
        raw_path = store.turns_dir / f'{n}.json'
        try:
            if fresh:
                handle = host.start(store.workspace, message, raw_path)
            else:
                handle = host.send(store.workspace, session_id, message, raw_path)
        except (OSError, ValueError) as exc:
            raise RecordError(f'could not launch the host session: {exc}')
        cycle = core.open_cycle(run)
        cycle_id = cycle['id'] if cycle else None
        started = now()
        if fresh:
            run['session'] = dict(id=None, started=started, reason=reason or 'first')
            session_id = None
        run['turn_count'] = n
        run['turn'] = dict(n=n, pid=handle.pid, started=started, kind=kind, state='RUNNING', cost_recorded=False)
        store.write_run(run)
        if fresh:
            store.append_event('L1', 'session', cycle_id, dict(reason=run['session']['reason'], turn=n))
        store.append_event('L1', 'turn', cycle_id, dict(turn=n, pid=handle.pid, kind=kind, session_id=session_id,
                                                        resumed=not fresh, raw_path=str(raw_path)))
        return dict(turn=n, pid=handle.pid, session_id=session_id)


def cmd_session_start(store: Store, a) -> dict:
    require(a.skill in SKILLS, f'skill must be one of {", ".join(SKILLS)}')
    require(a.fresh or a.reason is None, '--reason only applies with --fresh')
    text = read_text(a.message)
    return _launch(store, a, f'/dryforge:{a.skill} ' + text, a.skill, bool(a.fresh), a.reason)


def cmd_session_send(store: Store, a) -> dict:
    text = read_text(a.message)
    return _launch(store, a, text, 'message', False, None)


def _stored_result(store: Store, turn: dict) -> dict:
    out = {k: turn.get(k) for k in ('state', 'session_id', 'num_turns', 'cost_usd', 'permission_denials', 'is_error',
                                    'subtype', 'raw_path', 'stderr_path', 'exit_code', 'reason', 'text_path')}
    text_path = turn.get('text_path')
    out['text'] = (store.dir / text_path).read_text(encoding='utf-8') if text_path and (store.dir / text_path).is_file() else None
    return dict(out, turn=turn['n'], pid=turn['pid'], kind=turn['kind'])


def _settle(store: Store, a) -> dict:
    """Parse the exited turn once: record session id, add cost once, store the result, append events."""
    with store.transaction():
        check_owner(store, a.owner)
        run = store.read_run()
        turn = run.get('turn')
        require(turn is not None, 'no turn has been started')
        if turn['state'] != 'RUNNING':
            return _stored_result(store, turn)
        host = _host(run)
        handle = _turn_handle(store, turn)
        if host.alive(handle):
            return dict(state='RUNNING', pid=turn['pid'], turn=turn['n'], kind=turn['kind'])
        parsed = host.result(handle)
        cycle = core.open_cycle(run)
        cycle_id = cycle['id'] if cycle else None
        recorded = run['session']['id']
        if parsed['state'] == 'COMPLETE':
            if recorded is None:
                run['session']['id'] = parsed['session_id']
                store.write_owner(a.owner, session_id=parsed['session_id'])
                if cycle and cycle.get('session_id') is None:
                    cycle['session_id'] = parsed['session_id']
            elif recorded != parsed['session_id']:
                parsed.update(state='INTERRUPTED', reason='session id mismatch')
        text = parsed.pop('text')
        text_path = None
        if text is not None:
            text_path = f"turns/{turn['n']}.txt"
            (store.dir / text_path).write_text(text, encoding='utf-8')
            (store.dir / text_path).chmod(0o600)
        if not turn.get('cost_recorded'):
            run = core.add_spent(run, parsed['cost_usd'])
            turn = run['turn']
            turn['cost_recorded'] = True
        turn.update(parsed, text_path=text_path, finished=now())
        store.write_run(run)
        store.append_event('host', 'turn_result', cycle_id, dict(parsed, turn=turn['n'], text_path=text_path))
        if parsed['state'] == 'INTERRUPTED':
            store.append_event('host', 'interrupt', cycle_id, dict(turn=turn['n'], reason=parsed['reason'],
                                                                   raw_path=parsed['raw_path']))
        return _stored_result(store, turn)


def cmd_session_wait(store: Store, a) -> dict:
    run = store.read_run()
    check_owner(store, a.owner)
    turn = _running(run)
    if turn is not None:
        host, handle = _host(run), _turn_handle(store, turn)
        t0 = time.monotonic()
        deadline = None if a.timeout is None else t0 + a.timeout
        while host.alive(handle) and (deadline is None or time.monotonic() < deadline):
            time.sleep(WAIT_POLL)
        if host.alive(handle):
            return dict(state='RUNNING', waited=round(time.monotonic() - t0, 3), pid=turn['pid'], turn=turn['n'],
                        kind=turn['kind'])
    return _settle(store, a)


def cmd_session_status(store: Store, a) -> dict:
    return _settle(store, a)


def cmd_session_stop(store: Store, a) -> dict:
    with store.transaction():
        check_owner(store, a.owner)
        run = store.read_run()
        turn = _running(run)
        require(turn is not None, 'no turn is RUNNING')
        host = _host(run)
        host.terminate(_turn_handle(store, turn))
        cycle = core.open_cycle(run)
        turn.update(state='STOPPED', finished=now())
        store.write_run(run)
        store.append_event('human', 'stop', cycle['id'] if cycle else None,
                           dict(turn=turn['n'], pid=turn['pid'], kind=turn['kind']))
        return dict(state='STOPPED', turn=turn['n'], pid=turn['pid'], kind=turn['kind'])


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
    p = cmd('session-start', cmd_session_start, 'launch a detached /dryforge:<skill> turn (resume or fresh session)')
    p.add_argument('--skill', required=True)
    p.add_argument('--message', required=True)
    p.add_argument('--fresh', action='store_true')
    p.add_argument('--reason')
    cmd('session-send', cmd_session_send, 'launch a detached turn on the recorded session').add_argument('--message', required=True)
    cmd('session-wait', cmd_session_wait, 'block until the running turn exits, then print its parsed result').add_argument('--timeout', type=float)
    cmd('session-status', cmd_session_status, 'RUNNING or the parsed result of the last turn (non-blocking)')
    cmd('session-stop', cmd_session_stop, 'terminate the running turn (SIGTERM, then SIGKILL) and record it')
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
