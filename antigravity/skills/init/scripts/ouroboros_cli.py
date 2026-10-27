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
from ouroboros.store import Store, _write_bytes, check_owner  # noqa: E402

SKILLS = ('ready', 'go', 'migration')
LIVE_STATES = ('RUNNING', 'QUESTION')
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
    """Create the DRAFT, or revise the proposal of the current DRAFT, ACTIVE or STOPPED run (the revision must be
    shown and approved again). A COMPLETE run is archived first and a new run starts."""
    data = Path(a.proposal).read_bytes() if Path(a.proposal).is_file() else None
    require(data is not None, f'proposal file not found: {a.proposal}')
    store.ensure_dir()
    with store.transaction():
        check_owner(store, a.owner)
        run = store.read_run() if store.has_run() else None
        if run is not None and run['status'] == 'COMPLETE':
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
        store.write_approved(raw)
        store.write_run(run)
        store.append_event('human', 'amend' if action == 'amended' else 'approve', None,
                           dict(digest=current, limits=run['limits'], action=action))
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
    """The live turn (RUNNING or QUESTION), else None."""
    turn = run.get('turn')
    return turn if turn and turn.get('state') in LIVE_STATES else None


def _claim(store: Store, a, run: dict) -> None:
    """After `check_owner` passed: make `--owner` the recorded owner when a different (dead or absent) pid is
    recorded, carrying the session id forward. Called only on paths that go on to write."""
    owner = store.read_owner()
    if owner is None or owner.get('pid') != a.owner:
        store.write_owner(a.owner, session_id=run['session']['id'])


def _bind_session_early(store: Store, a, run: dict, host, handle: Turn) -> bool:
    """Record the session id a live turn has already announced, only while none is recorded. A later
    mismatch is handled at settlement, never mid-turn. Returns True when the record changed."""
    if run['session']['id'] is not None:
        return False
    sid = host.session_id(handle)
    if not sid:
        return False
    run['session']['id'] = sid
    store.write_owner(a.owner, session_id=sid)
    cycle = core.open_cycle(run)
    if cycle and cycle.get('session_id') is None:
        cycle['session_id'] = sid
    return True


def _question_events(store: Store, run: dict, bundle: dict) -> None:
    """A bundle the turn leaves open is recorded as asked (L2) and unanswered (L1)."""
    cycle = core.open_cycle(run)
    cycle_id = cycle['id'] if cycle else None
    store.append_event('L2', 'question', cycle_id, bundle)
    store.append_event('L1', 'unanswered', cycle_id, dict(round=bundle['round']))


def _launch(store: Store, a, message: str, kind: str, fresh: bool, reason: str | None) -> dict:
    """Shared by session-start and session-send: validate, launch detached, then record the turn."""
    with store.transaction():
        check_owner(store, a.owner)
        run = store.read_run()
        require(run['status'] == 'ACTIVE', f'run is {run["status"]}, not ACTIVE')
        which = core.limit_exceeded(run, mid_cycle=True)
        require(which is None, f'limit already exceeded: {which}')
        running = _running(run)
        if running is not None and running['state'] == 'QUESTION':
            raise RecordError(f'turn {running["n"]} has an open question; answer or stop first', turn=running['n'],
                              round=(running.get('question') or {}).get('round'))
        require(running is None, f'turn {running["n"] if running else ""} is still RUNNING; wait for it or stop it')
        session_id = run['session']['id']
        if kind == 'message':
            require(session_id is not None, 'no session recorded; start one with session-start')
        elif session_id is None:
            fresh = True
        cycle = core.open_cycle(run)
        cycle_id = cycle['id'] if cycle else None
        # Gate 3: Go runs in the session where this cycle's Ready ran, never in a fresh one.
        require(not (kind == 'go' and fresh and cycle and cycle.get('session_id')),
                f'go must run in the session of this cycle\'s Ready ({cycle.get("session_id") if cycle else None}); '
                'drop --fresh, or run ready in a fresh session first')
        host = _host(run)
        store.ensure_dir()
        _claim(store, a, run)
        n = int(run.get('turn_count', 0)) + 1
        raw_path = store.turns_dir / f'{n}.json'
        try:
            if fresh:
                handle = host.start(store.workspace, message, raw_path)
            else:
                handle = host.send(store.workspace, session_id, message, raw_path)
        except (OSError, ValueError) as exc:
            raise RecordError(f'could not launch the host session: {exc}')
        started = now()
        if fresh:
            run['session'] = dict(id=None, started=started, reason=reason or 'first', cost_total_usd=0)
            session_id = None
            if cycle:
                cycle['session_id'] = None  # the cycle's session is the one its turns actually run in
        run['turn_count'] = n
        run['turn'] = dict(n=n, pid=handle.pid, started=started, kind=kind, state='RUNNING', cost_recorded=False,
                           questions_answered=0)
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


def _stored_result(store: Store, run: dict) -> dict:
    """The recorded result of the last turn plus the run status it left behind (a budget stop shows here)."""
    turn = run['turn']
    out = {k: turn.get(k) for k in ('state', 'session_id', 'num_turns', 'cost_usd', 'cost_total_usd', 'usage', 'permission_denials',
                                    'is_error', 'subtype', 'raw_path', 'stderr_path', 'exit_code', 'reason', 'text_path',
                                    'skills', 'auto_allowed', 'questions', 'stream_path')}
    text_path = turn.get('text_path')
    out['text'] = (store.dir / text_path).read_text(encoding='utf-8') if text_path and (store.dir / text_path).is_file() else None
    return dict(out, turn=turn['n'], pid=turn['pid'], kind=turn['kind'], run_status=run['status'],
                stopped_reason=run['stopped_reason'])


def _live_status(store: Store, a, run: dict, host, handle: Turn) -> dict:
    """The live turn's state: QUESTION with the open bundle (recorded in run.json) or RUNNING. Binds the
    session id early when the host has announced it."""
    turn = run['turn']
    changed = _bind_session_early(store, a, run, host, handle)
    bundle = host.questions(handle)
    if bundle is not None:
        question = dict(round=bundle['round'], questions=bundle['questions'])
        if turn['state'] != 'QUESTION' or turn.get('question') != question:
            turn.update(state='QUESTION', question=question)
            changed = True
    elif turn['state'] != 'RUNNING':
        turn['state'] = 'RUNNING'
        turn.pop('question', None)
        changed = True
    if changed:
        store.write_run(run)
    out = dict(state=turn['state'], pid=turn['pid'], turn=turn['n'], kind=turn['kind'])
    if bundle is not None:
        out.update(round=bundle['round'], questions=bundle['questions'])
    return out


def _settle(store: Store, a) -> dict:
    """Parse the exited turn once: record session id, add cost once, store the result, append events. A live
    turn is reported as RUNNING or QUESTION instead. The host's `total_cost_usd` is cumulative over a resumed
    session, so the turn is charged the delta against the last total recorded for the session."""
    with store.transaction():
        check_owner(store, a.owner)
        run = store.read_run()
        turn = run.get('turn')
        require(turn is not None, 'no turn has been started')
        if turn['state'] not in LIVE_STATES:
            _claim(store, a, run)
            return _stored_result(store, run)
        host = _host(run)
        handle = _turn_handle(store, turn)
        _claim(store, a, run)
        if host.alive(handle):
            return _live_status(store, a, run, host, handle)
        parsed = host.result(handle)
        cycle = core.open_cycle(run)
        cycle_id = cycle['id'] if cycle else None
        open_bundle = host.questions(handle)
        turn.pop('question', None)
        recorded = run['session']['id']
        sid = parsed['session_id']
        if isinstance(sid, str) and sid:
            # Any turn that names a session binds it (an INTERRUPTED first turn included); a different id is
            # never adopted, the turn is recorded as INTERRUPTED instead.
            if recorded is None:
                run['session']['id'] = sid
                store.write_owner(a.owner, session_id=sid)
            elif recorded != sid:
                parsed.update(state='INTERRUPTED', reason='session id mismatch')
            if run['session']['id'] == sid and cycle and cycle.get('session_id') is None:
                cycle['session_id'] = sid
        text = parsed.pop('text')
        text_path = None
        if text is not None:
            text_path = f"turns/{turn['n']}.txt"
            _write_bytes(store.dir / text_path, text.encode('utf-8'))
        total = parsed['cost_total_usd']
        previous = run['session'].get('cost_total_usd') or 0
        # A total below the last one (a host reset) is charged in full and becomes the new baseline; a result
        # that carried no figure (total 0) charges nothing and keeps the baseline.
        parsed['cost_usd'] = total - previous if total >= previous else total
        if not turn.get('cost_recorded'):
            if total > 0:
                run['session']['cost_total_usd'] = total
            run = core.add_spent(run, parsed['cost_usd'])
            turn = run['turn']
            turn['cost_recorded'] = True
        turn.update(parsed, text_path=text_path, finished=now())
        stop_event = None
        if run['status'] == 'ACTIVE' and core.limit_exceeded(run, mid_cycle=True) == 'budget':
            run = core.stop(run, 'limit:budget')
            turn = run['turn']
            stop_event = dict(reason=run['stopped_reason'], stopped_at=run['stopped_at'], turn=turn['n'],
                              spent_usd=run['spent_usd'], budget_usd=run['limits']['budget_usd'])
        store.write_run(run)
        if open_bundle is not None:
            _question_events(store, run, open_bundle)
        store.append_event('host', 'turn_result', cycle_id, dict(parsed, turn=turn['n'], text_path=text_path))
        if parsed['state'] == 'INTERRUPTED':
            store.append_event('host', 'interrupt', cycle_id, dict(turn=turn['n'], reason=parsed['reason'],
                                                                   raw_path=parsed['raw_path']))
        if stop_event is not None:
            store.append_event('L1', 'stop', cycle_id, stop_event)
        return _stored_result(store, run)


def cmd_session_wait(store: Store, a) -> dict:
    """Block (without the record lock) until the live turn exits or opens a question, then settle or report it."""
    run = store.read_run()
    check_owner(store, a.owner)
    turn = _running(run)
    waited = None
    if turn is not None:
        host, handle = _host(run), _turn_handle(store, turn)
        t0 = time.monotonic()
        deadline = None if a.timeout is None else t0 + a.timeout
        while host.alive(handle) and host.questions(handle) is None and (deadline is None or time.monotonic() < deadline):
            time.sleep(WAIT_POLL)
        waited = round(time.monotonic() - t0, 3)
    out = _settle(store, a)
    if waited is not None and out.get('state') in LIVE_STATES:
        out['waited'] = waited
    return out


def cmd_session_status(store: Store, a) -> dict:
    return _settle(store, a)


def cmd_session_stop(store: Store, a) -> dict:
    """Terminate the live (RUNNING or QUESTION) turn and record it STOPPED; an open question is recorded as
    unanswered. A turn that has already exited is settled (parsed) instead. The signal is sent outside the
    record lock; the record is updated in a second transaction."""
    with store.transaction():
        check_owner(store, a.owner)
        run = store.read_run()
        turn = _running(run)
        require(turn is not None, 'no turn is RUNNING')
        host, handle, n = _host(run), _turn_handle(store, turn), turn['n']
        exited = not host.alive(handle)
    if exited:
        return _settle(store, a)
    host.terminate(handle)
    with store.transaction():
        check_owner(store, a.owner)
        run = store.read_run()
        turn = run.get('turn')
        if turn is not None and turn['n'] == n and turn['state'] not in LIVE_STATES:
            return _stored_result(store, run)  # settled by another command meanwhile
        require(turn is not None and turn['n'] == n, f'turn {n} is no longer the current turn')
        _claim(store, a, run)
        cycle = core.open_cycle(run)
        open_bundle = host.questions(handle)
        turn.pop('question', None)
        turn.update(state='STOPPED', finished=now())
        store.write_run(run)
        if open_bundle is not None:
            _question_events(store, run, open_bundle)
        store.append_event('L1', 'stop', cycle['id'] if cycle else None,
                           dict(turn=turn['n'], pid=turn['pid'], kind=turn['kind']))
        return dict(state='STOPPED', turn=turn['n'], pid=turn['pid'], kind=turn['kind'], run_status=run['status'],
                    stopped_reason=run['stopped_reason'])


def _validate_answers(questions: list, answers) -> dict:
    """Validate L1's answers against the open bundle and return them in the structured form the port takes
    (question → a label, a list of labels for a multiSelect question, or {"other": text}); the adapter encodes
    its host's wire form. Refuses on the first offending key without applying anything."""
    require(isinstance(answers, dict), 'answers must be a JSON object mapping question text to an answer')
    by_text = {}
    for q in questions:
        if isinstance(q, dict) and isinstance(q.get('question'), str):
            by_text[q['question']] = q
    for key in answers:
        require(key in by_text, f'unknown question: {key!r}', question=key)
    valid = {}
    for text, q in by_text.items():
        require(text in answers, f'missing answer for question: {text!r}', question=text)
        value = answers[text]
        labels = [o.get('label') for o in (q.get('options') or []) if isinstance(o, dict)]
        if isinstance(value, str):
            require(value in labels, f'answer for {text!r} is not one of its options: {value!r}',
                    question=text, options=labels)
            valid[text] = value
        elif isinstance(value, list):
            require(bool(q.get('multiSelect')), f'answer for {text!r} is a list but the question is not multiSelect',
                    question=text)
            require(bool(value) and all(isinstance(v, str) for v in value), f'answer for {text!r} must list option labels',
                    question=text)
            bad = [v for v in value if v not in labels]
            require(not bad, f'answer for {text!r} names options that do not exist: {bad!r}', question=text, options=labels)
            valid[text] = value
        elif isinstance(value, dict):
            require(set(value) == {'other'} and isinstance(value.get('other'), str) and value['other'].strip() != '',
                    f'answer for {text!r} must be a label, a list of labels or {{"other": "<text>"}}', question=text)
            valid[text] = value
        else:
            raise RecordError(f'answer for {text!r} must be a label, a list of labels or {{"other": "<text>"}}',
                              question=text)
    return valid


def cmd_session_answer(store: Store, a) -> dict:
    """Answer the open question bundle of the live turn on L1's authority and let the turn continue."""
    raw = read_text(a.answers)
    basis = read_text(a.basis) if a.basis is not None else None
    try:
        answers = json.loads(raw)
    except ValueError as exc:
        raise RecordError(f'answers file is not JSON: {exc}')
    with store.transaction():
        check_owner(store, a.owner)
        run = store.read_run()
        turn = _running(run)
        require(turn is not None, 'no open question: no turn is live')
        host, handle = _host(run), _turn_handle(store, turn)
        require(host.alive(handle), f'turn {turn["n"]} has exited; settle it with session-wait')
        bundle = host.questions(handle)
        require(bundle is not None, f'turn {turn["n"]} has no open question')
        valid = _validate_answers(bundle['questions'], answers)
        _claim(store, a, run)
        host.answer(handle, bundle['round'], valid)
        turn.update(state='RUNNING', questions_answered=int(turn.get('questions_answered', 0)) + 1)
        turn.pop('question', None)
        store.write_run(run)
        cycle = core.open_cycle(run)
        cycle_id = cycle['id'] if cycle else None
        store.append_event('L2', 'question', cycle_id, bundle)
        store.append_event('L1', 'answer', cycle_id, dict(round=bundle['round'], answers=answers, basis=basis))
        return dict(state='RUNNING', turn=turn['n'], pid=turn['pid'], kind=turn['kind'], round=bundle['round'],
                    answers=valid)


def add_commands(sub) -> dict:
    """Register the run-record commands; returns name → handler. Session commands register alongside."""
    handlers = {}

    def cmd(name, fn, help_text):
        p = sub.add_parser(name, help=help_text)
        handlers[name] = fn
        return p

    cmd('doctor', cmd_doctor, 'report host prerequisites').add_argument('--host', default='claude', choices=['claude'])
    cmd('draft', cmd_draft, 'create the DRAFT proposal or revise the current run\'s proposal').add_argument('--proposal', required=True)
    cmd('shown', cmd_shown, 'record the current proposal digest as shown')
    cmd('show', cmd_show, 'print the run summary')
    cmd('approve', cmd_approve, 'approve the proposal exactly as shown (activate, resume or amend the run)')
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
    cmd('session-wait', cmd_session_wait, 'block until the live turn exits or asks a question, then print its result or the question').add_argument('--timeout', type=float)
    cmd('session-status', cmd_session_status, 'RUNNING, QUESTION (with the open question) or the parsed result of the last turn (non-blocking)')
    p = cmd('session-answer', cmd_session_answer, 'answer the open question bundle of the live turn and let it continue')
    p.add_argument('--answers', required=True, help='JSON object: question text → label | [labels] (multiSelect) | {"other": text}')
    p.add_argument('--basis', help='text file with the reasoning behind the answers (recorded with the answer event)')
    cmd('session-stop', cmd_session_stop, 'terminate the live turn (SIGTERM, then SIGKILL) and record it; settles an exited one')
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
